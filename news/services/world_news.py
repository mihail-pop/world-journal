"""General news from retained feeds: no country matching or network in rendering."""
from collections import defaultdict, deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from urllib.parse import urlencode

from django.core.cache import cache
from django.core.paginator import Paginator
from django.urls import reverse

from news.preferences import freshness_seconds
from news.types import SourceKind

from .cache import fixed_feed_cache_key, google_cache_key, google_pause_until, youtube_cache_key
from .country_news import _countries_by_code, get_country_news, get_world_news
from .regional_news import get_fixed_feed
from .youtube_news import get_youtube_feed


def page_options(query, registry):
    tab = "videos" if query.get("tab") == "videos" else "articles"
    sources = [("all", "All channels")] if tab == "videos" else [
        ("all", "All articles"), ("google", "Google News"), ("regional", "Regional publishers"),
    ]
    if tab == "videos":
        sources += [(source.id, source.display_name) for source in registry.sources
                    if source.kind is SourceKind.YOUTUBE and source.enabled_by_default]
    else:
        sources += [(provider.id, provider.display_name) for provider in registry.providers if provider.enabled_by_default]
    source = query.get("source", "all")
    if source not in dict(sources):
        source = "all"
    country = query.get("country", "WORLD").upper()
    if country not in _countries_by_code():
        country = "WORLD"
    period = query.get("period", "day")
    if period not in {"day", "week", "all"}:
        period = "day"
    sorts = [("newest", "Newest"), ("views", "Most viewed")] if tab == "videos" else [("top", "Top stories"), ("newest", "Newest")]
    sort = query.get("sort", sorts[0][0])
    if sort not in dict(sorts):
        sort = sorts[0][0]
    return {"tab": tab, "source": source, "country": country, "period": period, "sort": sort,
            "page": query.get("page", "1"), "sources": sources, "sorts": sorts}


def news_url(options, **changes):
    values = {key: options[key] for key in ("tab", "source", "country", "period", "sort")}
    values.update(changes)
    return reverse("news:index") + "?" + urlencode(values)


def _newest(item):
    return item.published_at or datetime.min.replace(tzinfo=UTC)


def _unique_articles(items):
    links, identities, result = set(), set(), []
    for item in items:
        # Keep different publishers' coverage; only collapse clear duplicates.
        identity = (" ".join(item.publisher.casefold().split()), " ".join(item.title.casefold().split()))
        if item.link in links or identity in identities:
            continue
        links.add(item.link)
        identities.add(identity)
        result.append(item)
    return result


def _balanced(items):
    groups = defaultdict(list)
    for item in items:
        groups[item.provider_id].append(item)
    queues = deque(deque(sorted(group, key=_newest, reverse=True)) for group in groups.values())
    result = []
    while queues:
        queue = queues.popleft()
        result.append(queue.popleft())
        if queue:
            queues.append(queue)
    return result


class CachedNews:
    def __init__(self, options, registry):
        self.options, self.registry = options, registry
        self.interval, self.now = freshness_seconds(), datetime.now(UTC)
        self.google = registry.get("google_news_country")
        selected = options["source"]
        self.google_enabled = options["tab"] == "articles" and selected in {"all", "google"} and self.google.enabled_by_default
        self.feeds = [feed for feed in registry.feeds if feed.enabled_by_default and options["tab"] == "articles"
                      and (selected in {"all", "regional"} or selected == feed.provider_id)]
        self.channels = [source for source in registry.sources if source.enabled_by_default and source.kind is SourceKind.YOUTUBE
                         and options["tab"] == "videos" and selected in {"all", source.id}]
        self.keys = [fixed_feed_cache_key(feed) for feed in self.feeds] + [youtube_cache_key(source) for source in self.channels]
        if self.google_enabled:
            self.keys.append(google_cache_key(self.google, options["country"]))
        self.snapshots = cache.get_many(self.keys)

    def get(self, key, default=None):
        return self.snapshots.get(key, default)

    def version(self):
        # Include time so rolling date filters age out even without a feed change.
        stamp = ["article-text-v2", self.options, self.interval, int(self.now.timestamp()) // 60]
        for key in self.keys:
            snapshot = self.get(key)
            snapshot = snapshot if isinstance(snapshot, dict) else {}
            stamp.append((key, snapshot.get("fetched_at"), snapshot.get("last_attempt_at"), snapshot.get("last_error")))
        return sha256(json.dumps(stamp, separators=(",", ":")).encode()).hexdigest()[:20]

    def context(self):
        google_items, regional_items, video_items, errors = [], [], [], []
        options = {"cache_backend": self, "cache_only": True, "fresh_seconds": self.interval, "now": self.now}
        if self.google_enabled:
            result = get_world_news(registry=self.registry, **options) if self.options["country"] == "WORLD" else get_country_news(self.options["country"], registry=self.registry, **options)
            google_items = [replace(item, is_stale=result.is_stale) for item in result.items]
            if result.warning or result.error:
                errors.append(("Google News", result.warning or result.error))
            if pause := google_pause_until(cache, self.now):
                errors.append(("Google News", f"Refresh is paused until {pause:%H:%M UTC on %b %d}; cached headlines remain available."))
        for feed in self.feeds:
            provider = self.registry.get_provider(feed.provider_id)
            result = get_fixed_feed(feed, provider, **options)
            regional_items += [replace(item, is_stale=result.is_stale) for item in result.items]
            if result.refresh_failed:
                errors.append((f"{provider.display_name} · {feed.section_label}", "Showing cached articles." if result.items else result.error or "Feed temporarily unavailable."))
        for source in self.channels:
            result = get_youtube_feed(source, **options)
            video_items += [replace(item, is_stale=result.is_stale) for item in result.items]
            if result.refresh_failed:
                errors.append((source.display_name, "Showing cached videos." if result.items else result.error or "Channel temporarily unavailable."))

        cutoff = self.now - timedelta(days=1 if self.options["period"] == "day" else 7)
        def in_period(item):
            return self.options["period"] == "all" or bool(item.published_at and cutoff <= item.published_at <= self.now)
        google_items = [item for item in google_items if in_period(item)]
        regional_items = [item for item in regional_items if in_period(item)]
        video_items = [item for item in video_items if in_period(item)]
        if self.options["tab"] == "articles":
            items = _unique_articles(google_items + _balanced(_unique_articles(regional_items)))
            if self.options["sort"] == "newest":
                items.sort(key=_newest, reverse=True)
        else:
            items = list({item.video_id: item for item in video_items}.values())
            if self.options["sort"] == "views":
                items.sort(key=lambda item: (item.view_count is not None, item.view_count or 0, _newest(item)), reverse=True)
            else:
                items.sort(key=_newest, reverse=True)
        page = Paginator(items, 30).get_page(self.options["page"])
        cards = []
        for item in page:
            video = self.options["tab"] == "videos"
            initial = {"type": "youtube" if video else "article", "title": item.title,
                       "source": item.channel_name if video else item.publisher}
            initial["video" if video else "url"] = item.video_id if video else item.link
            if item.published_at:
                initial["published"] = item.published_at.isoformat()
            if not video and item.provider_id == self.google.id and self.options["country"] != "WORLD":
                initial["country"] = self.options["country"]
            cards.append({"item": item, "google": not video and item.provider_id == self.google.id,
                          "save_url": reverse("journal:new") + "?" + urlencode(initial)})
        pending = sum(not isinstance(snapshot := self.get(key), dict) or not isinstance(snapshot.get("items"), list)
                      or not (snapshot.get("last_success_at") or snapshot.get("last_attempt_at")) for key in self.keys)
        return {
            "cards": cards, "tab": self.options["tab"], "version": self.version(), "pending": pending,
            "errors": errors, "enabled_count": len(self.keys), "total": len(items), "result_page": page,
            "previous_url": news_url(self.options, page=page.previous_page_number()) if page.has_previous() else "",
            "next_url": news_url(self.options, page=page.next_page_number()) if page.has_next() else "",
            "missing_views": self.options["tab"] == "videos" and self.options["sort"] == "views" and any(item.view_count is None for item in items),
        }
