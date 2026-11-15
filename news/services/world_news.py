"""One paged view of current feeds and retained coverage, without feed downloads."""
from collections import defaultdict, deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from django.core.cache import cache
from django.db.models import F, Prefetch, Q
from django.urls import reverse

from news.adapters.rss import clean_article_text, is_google_news_link
from news.adapters.youtube import build_embed_url, build_thumbnail_url, build_watch_url
from news.models import ArchivedNews, ArchivedNewsSource
from news.preferences import freshness_seconds
from news.paging import paging_time, result_version, search_archive, search_query, search_terms
from news.types import NewsItem, SourceKind, VideoItem
from journal.bookmarks import bookmark_states

from .archive import identities, revision
from .cache import fixed_feed_cache_key, google_cache_key, google_pause_until, youtube_cache_key
from .country_news import _countries_by_code, get_country_news, get_world_news
from .regional_news import get_fixed_feed
from .youtube_news import get_youtube_feed


def page_options(query, registry):
    tab = "videos" if query.get("tab") == "videos" else "articles"
    sources = []
    if tab == "videos":
        sources += [(source.id, source.display_name) for source in registry.sources
                    if source.kind is SourceKind.YOUTUBE and source.enabled_by_default]
    else:
        if registry.get("google_news_country").enabled_by_default:
            sources.append(("google", "Google News"))
        sources += [(provider.id, provider.display_name) for provider in registry.providers if provider.enabled_by_default]
    requested = query.getlist("source") if hasattr(query, "getlist") else query.get("source", ())
    requested = [requested] if isinstance(requested, str) else requested
    if "all" in requested:
        requested = ()
    elif "regional" in requested and tab == "articles":
        requested = [*requested, *(provider.id for provider in registry.providers)]
    source = tuple(value for value, _label in sources if value in requested)
    country = query.get("country", "WORLD").upper()
    if country not in _countries_by_code():
        country = "WORLD"
    period = query.get("period", "day")
    if period not in {"day", "week", "month", "all"}:
        period = "day"
    sorts = [("views", "Most viewed"), ("least_views", "Least viewed")] if tab == "videos" else [("top", "Top stories"), ("newest", "Newest")]
    sort = query.get("sort", sorts[0][0])
    if tab == "videos":
        sort = {"newest": "views", "oldest": "least_views"}.get(sort, sort)
    if sort not in dict(sorts):
        sort = sorts[0][0]
    try:
        page = max(1, min(10000, int(query.get("page", "1"))))
    except (ValueError, TypeError):
        page = 1
    return {"tab": tab, "source": source, "country": country, "period": period, "sort": sort,
            "q": search_query(query), "at": paging_time(query),
            "page": page, "sources": sources, "sort_label": dict(sorts)[sort],
            "sort_next": sorts[1][0] if sort == sorts[0][0] else sorts[0][0],
            "sort_order": "desc" if sort == sorts[0][0] else "asc"}


def news_url(options, **changes):
    values = {key: options[key] for key in ("tab", "source", "country", "period", "sort", "q")}
    values.update(changes)
    return reverse("news:index") + "?" + urlencode(values, doseq=True)


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
        self.interval, self.now = freshness_seconds(), options["at"]
        self.google = registry.get("google_news_country")
        selected = options["source"]
        self.google_enabled = options["tab"] == "articles" and (not selected or "google" in selected) and self.google.enabled_by_default
        self.feeds = [feed for feed in registry.feeds if feed.enabled_by_default and options["tab"] == "articles"
                      and (not selected or feed.provider_id in selected)]
        self.channels = [source for source in registry.sources if source.enabled_by_default and source.kind is SourceKind.YOUTUBE
                         and options["tab"] == "videos" and (not selected or source.id in selected)]
        self.keys = [fixed_feed_cache_key(feed) for feed in self.feeds] + [youtube_cache_key(source) for source in self.channels]
        self.origin_ids = [feed.id for feed in self.feeds] + [source.id for source in self.channels]
        if self.google_enabled:
            self.keys.append(google_cache_key(self.google, options["country"]))
            self.origin_ids.append(f"{self.google.id}:{options['country']}")
        self.snapshots = cache.get_many(self.keys)

    def get(self, key, default=None):
        return self.snapshots.get(key, default)

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

        unknown_views = [item for item in video_items if item.view_count is None]
        if unknown_views:
            retained_counts = dict(ArchivedNews.objects.filter(
                pk__in=[identities(item, "videos")[0] for item in unknown_views], view_count__isnull=False,
            ).values_list("video_id", "view_count"))
            video_items = [replace(item, view_count=retained_counts.get(item.video_id)) if item.view_count is None else item
                           for item in video_items]
        current_items = google_items + regional_items + video_items
        days = {"day": 1, "week": 7, "month": 30, "all": 90}[self.options["period"]]
        cutoff = self.now - timedelta(days=days)
        terms = search_terms(self.options["q"])
        def in_period(item):
            return (self.options["period"] == "all" and item.published_at is None
                    or bool(item.published_at and cutoff <= item.published_at <= self.now))
        def matches(item):
            fields = [item.title, getattr(item, "publisher", ""), getattr(item, "provider_name", ""),
                      getattr(item, "channel_name", ""), getattr(item, "summary", "")]
            text = " ".join(fields).casefold()
            return in_period(item) and all(term in text for term in terms)
        google_items = [item for item in google_items if matches(item)]
        regional_items = [item for item in regional_items if matches(item)]
        video_items = [item for item in video_items if matches(item)]
        if self.options["tab"] == "articles":
            items = _unique_articles(google_items + _balanced(_unique_articles(regional_items)))
            if self.options["sort"] == "newest":
                items.sort(key=_newest, reverse=True)
        else:
            items = list({item.video_id: item for item in video_items}.values())
        items, has_next = self._page(items, current_items, cutoff)
        query_signature = result_version([
            {key: self.options[key] for key in ("tab", "source", "country", "period", "sort", "q")}, self.keys,
        ])
        version = result_version([query_signature, revision(), [
            (item.video_id if self.options["tab"] == "videos" else item.link, item.published_at, getattr(item, "view_count", None))
            for item in google_items + regional_items + video_items
        ]])
        cards = []
        bookmarks = bookmark_states(
            videos=[item.video_id for item in items] if self.options["tab"] == "videos" else (),
            urls=[item.link for item in items] if self.options["tab"] == "articles" else (),
        )
        for item in items:
            video = self.options["tab"] == "videos"
            initial = {"type": "youtube" if video else "article", "title": item.title,
                       "source": item.channel_name if video else item.publisher}
            initial["video" if video else "url"] = item.video_id if video else item.link
            if item.published_at:
                initial["published"] = item.published_at.isoformat()
            if not video and item.provider_id == self.google.id and self.options["country"] != "WORLD":
                initial["country"] = [self.options["country"]]
            elif item.matched_country_codes:
                initial["country"] = item.matched_country_codes
            cards.append({"item": item, "google": not video and item.provider_id == self.google.id,
                          "bookmark": bookmarks.get(f"video:{item.video_id}" if video else f"article:{item.link}"),
                          "save_url": reverse("journal:new") + "?" + urlencode(initial, doseq=True)})
        pending = sum(not isinstance(snapshot := self.get(key), dict) or not isinstance(snapshot.get("items"), list)
                      or not (snapshot.get("last_success_at") or snapshot.get("last_attempt_at")) for key in self.keys)
        return {
            "cards": cards, "tab": self.options["tab"], "pending": pending,
            "query": self.options["q"], "paging_version": version, "query_signature": query_signature,
            "refresh_url": news_url(self.options),
            "errors": errors, "enabled_count": len(self.keys),
            "next_url": news_url(self.options, page=self.options["page"] + 1, v=version, at=self.now.isoformat()) if has_next else "",
        }

    def _page(self, current, excluded, cutoff):
        """Rank lightweight archive IDs, then read metadata for just this batch."""
        kind = self.options["tab"]
        origins = ArchivedNewsSource.objects.filter(feed_id__in=self.origin_ids)
        rows = ArchivedNews.objects.filter(kind=kind, expires_at__gt=datetime.now(UTC),
            first_seen_at__lte=self.now, pk__in=origins.values("item_id"))
        if self.options["period"] == "all":
            rows = rows.filter(Q(published_at__isnull=True) | Q(published_at__gte=cutoff, published_at__lte=self.now))
        else:
            rows = rows.filter(published_at__gte=cutoff, published_at__lte=self.now)
        rows = search_archive(rows, self.options["q"])
        if excluded:
            keys, fingerprints = zip(*(identities(item, kind) for item in excluded))
            rows = rows.exclude(Q(pk__in=set(keys)) | Q(fingerprint__in=set(fingerprints)))
        start, end = (self.options["page"] - 1) * 30, self.options["page"] * 30
        videos = kind == "videos"
        ascending = self.options["sort"] == "least_views"
        ordering = [F("view_count").asc(nulls_last=True) if ascending else F("view_count").desc(nulls_last=True)] if videos else []
        archived = rows.order_by(*ordering, F("published_at").desc(nulls_last=True), "identity").values_list("identity", "published_at", "view_count")
        if kind == "articles" and self.options["sort"] == "top":
            selected = [(None, item) for item in current[start:end + 1]]
            needed = end + 1 - max(start, len(current))
            if needed > 0:
                offset = max(0, start - len(current))
                selected.extend((identity, None) for identity, _date, _views in archived[offset:offset + needed])
        else:
            # Only IDs/dates are needed to interleave archive results with feeds.
            pool = [(identities(item, kind)[0], item.published_at, getattr(item, "view_count", None), item) for item in current]
            pool.extend((identity, date, views, None) for identity, date, views in archived[:end + 1])
            def key(row):
                date = row[1] or datetime.min.replace(tzinfo=UTC)
                chronological = (row[1] is None, datetime.max.replace(tzinfo=UTC) - date, row[0])
                if videos:
                    return (row[2] is None, (row[2] or 0) * (1 if ascending else -1), *chronological)
                return chronological
            pool.sort(key=key)
            selected = [(identity, item) for identity, _date, _views, item in pool[start:end + 1]]
        has_next = len(selected) > 30
        selected = selected[:30]
        saved = {item.pk: item for item in rows.filter(pk__in=[identity for identity, item in selected if item is None])
            .prefetch_related(Prefetch("origins", queryset=origins.order_by("category", "feed_id"), to_attr="board_origins"))}
        result = []
        for identity, item in selected:
            if item is None:
                record = saved.get(identity)
                if not record or not record.board_origins:
                    continue
                origin = record.board_origins[0]
                if kind == "videos":
                    source = self.registry.get(origin.source_id)
                    item = VideoItem(source_id=source.id, channel_name=source.display_name,
                        video_id=record.video_id, title=record.title, published_at=record.published_at,
                        watch_url=build_watch_url(record.video_id), embed_url=build_embed_url(record.video_id),
                        thumbnail_url=build_thumbnail_url(record.video_id), view_count=record.view_count)
                else:
                    name = self.google.display_name if origin.source_id == self.google.id else self.registry.get_provider(origin.source_id).display_name
                    title, summary = clean_article_text(record.title, record.publisher, record.summary, google=is_google_news_link(record.link))
                    item = NewsItem(title=title, summary=summary, publisher=record.publisher, link=record.link,
                        published_at=record.published_at, provider_id=origin.source_id, provider_name=name, feed_id=origin.feed_id)
            result.append(item)
        return result, has_next
