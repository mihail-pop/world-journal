"""One paged view of current feeds and retained coverage, without feed downloads."""
from collections import defaultdict, deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from django.core.cache import cache
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.urls import reverse
from django.utils.timezone import localtime

from news.adapters.rss import clean_article_text, is_google_news_link
from news.adapters.youtube import build_embed_url, build_thumbnail_url, build_watch_url
from news.models import ArchivedNews, ArchivedNewsSource
from news.preferences import freshness_seconds
from news.paging import archive_page, cursor_date, decode_cursor, encode_cursor, NewsCursorError, paging_time, result_version, search_archive, search_query, search_terms
from news.types import NewsItem, SourceKind, VideoItem
from journal.bookmarks import bookmark_states

from .archive import identities, restrict_origins, revision
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
    return {"tab": tab, "source": source, "country": country, "period": period, "sort": sort,
            "q": search_query(query), "at": paging_time(query),
            "cursor": query.get("cursor", ""), "sources": sources, "sort_label": dict(sorts)[sort],
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
                errors.append(("Google News", f"Refresh is paused until {localtime(pause):%H:%M on %b %d}; cached headlines remain available."))
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
        days = {"day": 1, "week": 7, "month": 30}.get(self.options["period"])
        cutoff = self.now - timedelta(days=days) if days else None
        terms = search_terms(self.options["q"])
        def in_period(item):
            return (item.published_at is None and cutoff is None
                    or bool(item.published_at and item.published_at <= self.now and (cutoff is None or item.published_at >= cutoff)))
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
        query_signature = result_version([
            {key: self.options[key] for key in ("tab", "source", "country", "period", "sort", "q")}, self.keys,
        ])
        cursor = decode_cursor(self.options["cursor"], query_signature)
        items, next_position = self._page(items, current_items, cutoff, cursor)
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
            "next_url": news_url(self.options, cursor=encode_cursor(next_position, query_signature), v=version, at=self.now.isoformat()) if next_position else "",
        }

    def _page(self, current, excluded, cutoff, cursor):
        """Merge one bounded archive page with the small current-feed batch."""
        kind, sort = self.options["tab"], self.options["sort"]
        origins = ArchivedNewsSource.objects.filter(feed_id__in=self.origin_ids)
        rows = ArchivedNews.objects.filter(kind=kind, first_seen_at__lte=self.now).exclude(published_at__gt=self.now)
        if 0 < len(self.options["source"]) < len(self.options["sources"]):
            rows = restrict_origins(rows, origins)
        else:
            rows = rows.filter(Exists(origins.filter(item_id=OuterRef("pk"))))
        if cutoff is not None:
            rows = rows.filter(published_at__gte=cutoff)
        if excluded:
            keys, fingerprints = zip(*(identities(item, kind) for item in excluded))
            rows = rows.exclude(Q(pk__in=set(keys)) | Q(fingerprint__in=set(fingerprints)))
        rows = search_archive(rows, self.options["q"])

        def position(identity, published, views, stage="ranked"):
            return {"stage": stage, "identity": identity,
                    "published": published.isoformat() if published else None, "views": views}

        selected = []
        if kind == "articles" and sort == "top":
            stage = cursor.get("stage") if cursor else "live"
            if stage not in {"live", "archive"}:
                raise NewsCursorError("Invalid news cursor.")
            offset = cursor.get("offset", 0) if cursor else 0
            if type(offset) is not int or not 0 <= offset <= len(current):
                raise NewsCursorError("Invalid news cursor.")
            if stage == "live":
                for index, item in enumerate(current[offset:offset + 31], offset):
                    selected.append((item, None, {"stage": "live", "offset": index + 1}))
            for identity, published, views in archive_page(rows, cursor if stage == "archive" else None, 31-len(selected)):
                selected.append((None, identity, position(identity, published, views, "archive")))
        else:
            videos = kind == "videos"
            ascending = sort == "least_views"

            def rank(identity, published, views):
                date = published or datetime.min.replace(tzinfo=UTC)
                key = (published is None, datetime.max.replace(tzinfo=UTC)-date, identity)
                return (views is None, (views or 0)*(1 if ascending else -1), *key) if videos else key

            boundary = None
            if cursor:
                if cursor.get("stage") != "ranked":
                    raise NewsCursorError("Invalid news cursor.")
                published = cursor_date(cursor.get("published"), cursor.get("identity"))
                views = cursor.get("views")
                if views is not None and (type(views) is not int or not 0 <= views <= 9223372036854775807):
                    raise NewsCursorError("Invalid news cursor.")
                boundary = rank(cursor["identity"], published, views)
            pool = []
            for item in current:
                identity = identities(item, kind)[0]
                views = getattr(item, "view_count", None)
                key = rank(identity, item.published_at, views)
                if boundary is None or key > boundary:
                    pool.append((key, item, None, position(identity, item.published_at, views)))
            pool.sort(key=lambda row: row[0])
            pool = pool[:31]
            for identity, published, views in archive_page(rows, cursor, 31, sort=sort):
                pool.append((rank(identity, published, views), None, identity, position(identity, published, views)))
            pool.sort(key=lambda row: row[0])
            selected = [(item, identity, after) for key, item, identity, after in pool[:31]]
        next_position = selected[29][2] if len(selected) > 30 else None
        selected = selected[:30]
        retained = {item.pk: item for item in ArchivedNews.objects.filter(pk__in=[identity for item, identity, after in selected if item is None])
            .prefetch_related(Prefetch("origins", queryset=origins.order_by("category", "feed_id"), to_attr="board_origins"))}
        result = []
        for item, identity, after in selected:
            if item is None:
                record = retained.get(identity)
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
        return result, next_position
