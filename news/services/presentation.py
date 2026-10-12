"""Render country drawers from one cache read, without network calls or feed locks."""
from datetime import UTC, datetime
from hashlib import sha256
import json

from django.core.cache import cache
from django.template.loader import render_to_string

from news.preferences import effective_registry, freshness_seconds

from .cache import fixed_feed_cache_key, google_cache_key, youtube_cache_key
from .country_news import _country_for_code, get_country_news_page
from .region_routing import eligible_youtube_sources
from .youtube_news import get_country_videos


class CachedDrawers:
    def __init__(self, codes):
        self.registry = effective_registry()
        self.interval = freshness_seconds()
        self.now = datetime.now(UTC)
        self.google = self.registry.get("google_news_country")
        self.regional_keys = [fixed_feed_cache_key(feed) for feed in self.registry.feeds if feed.enabled_by_default]
        self.keys = {}
        for code in codes:
            country = _country_for_code(code)
            video_keys = [youtube_cache_key(source) for source in eligible_youtube_sources(country, self.registry)]
            google_key = google_cache_key(self.google, code) if self.google.enabled_by_default else None
            self.keys[code] = (google_key, video_keys)
        all_keys = self.regional_keys + [key for google_key, video_keys in self.keys.values() for key in ([google_key] if google_key else []) + video_keys]
        self.snapshots = cache.get_many(all_keys)
        from .archive import country_revisions
        self.archive_revisions = country_revisions(self.keys)

    def get(self, key, default=None):
        return self.snapshots.get(key, default)

    def _pending(self, key):
        snapshot = self.snapshots.get(key)
        return not isinstance(snapshot, dict) or not isinstance(snapshot.get("items"), list) or not (
            snapshot.get("last_success_at") or snapshot.get("last_attempt_at")
        )

    def pending(self, code, kind):
        google_key, video_keys = self.keys[code]
        keys = video_keys if kind == "videos" else self.regional_keys + ([google_key] if google_key else [])
        return any(self._pending(key) for key in keys)

    def version(self, code):
        google_key, video_keys = self.keys[code]
        keys = self.regional_keys + ([google_key] if google_key else []) + video_keys
        stamp = [self.interval, int(self.now.timestamp()) // self.interval, self.google.enabled_by_default, self.archive_revisions.get(code, "")]
        for key in keys:
            snapshot = self.snapshots.get(key)
            snapshot = snapshot if isinstance(snapshot, dict) else {}
            stamp.append((key, snapshot.get("fetched_at"), snapshot.get("last_attempt_at"), snapshot.get("last_error")))
        return sha256(json.dumps(stamp, separators=(",", ":")).encode()).hexdigest()[:20]

    def render(self, code, kind):
        options = {"registry": self.registry, "cache_backend": self, "cache_only": True, "fresh_seconds": self.interval, "now": self.now}
        signature = [feed.id for feed in self.registry.feeds if feed.enabled_by_default] + [source.id for source in self.registry.sources if source.enabled_by_default]
        context = {"feed_pending": self.pending(code, kind), "archive_country":code, "archive_kind":kind,
                   "archive_revision":self.archive_revisions.get(code, ""), "archive_config":sha256(repr(signature).encode()).hexdigest()[:16]}
        if kind == "articles":
            context["news_page"] = get_country_news_page(code, **options)
            context["archive_open"] = not (context["news_page"].google.items or context["news_page"].regional_items)
            google_key, _ = self.keys[code]
            context["google_pending"] = bool(google_key and self._pending(google_key))
            template = "news/partials/country_news.html"
        else:
            context["video_page"] = get_country_videos(code, **options)
            context["archive_open"] = not context["video_page"].items
            template = "news/partials/country_videos.html"
        return render_to_string(template, context)
