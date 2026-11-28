"""Render country drawers from one cache read, without network calls or feed locks."""
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlencode

from django.core.cache import cache
from django.template.loader import render_to_string
from django.urls import reverse

from news.preferences import effective_registry, freshness_seconds

from .cache import fixed_feed_cache_key, google_cache_key, youtube_cache_key
from .country_news import _country_for_code, get_country_news_page
from .region_routing import eligible_youtube_sources


def country_article_cards(page):
    from .archive import identities

    incoming = [(item, "google") for item in page.google.items] + [(item, "regional") for item in page.regional_items]
    incoming.sort(key=lambda row: row[0].published_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    cards, seen = [], {}
    for item, kind in incoming:
        identity, fingerprint = identities(item, "articles")
        card = seen.get(identity) or seen.get(fingerprint)
        if card is None:
            initial = {"type": "article", "title": item.title, "url": item.link,
                       "source": item.publisher or item.provider_name, "country": page.country_code}
            if item.published_at:
                initial["published"] = item.published_at.isoformat()
            card = {"item": item, "kinds": kind, "via_google": kind == "google",
                    "summary_id": f"country-summary-current-{identity}",
                    "save_url": reverse("journal:new") + "?" + urlencode(initial)}
            cards.append(card)
        else:
            card["kinds"] = " ".join(sorted(set(card["kinds"].split()) | {kind}))
            card["via_google"] |= kind == "google"
        seen[identity] = seen[fingerprint] = card
    return cards


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

    def render(self, code, kind):
        options = {"registry": self.registry, "cache_backend": self, "cache_only": True, "fresh_seconds": self.interval, "now": self.now}
        signature = [feed.id for feed in self.registry.feeds if feed.enabled_by_default] + [source.id for source in self.registry.sources if source.enabled_by_default]
        context = {"feed_pending": self.pending(code, kind), "archive_country":code, "archive_kind":kind,
                   "archive_revision":self.archive_revisions.get(code, ""), "archive_config":sha256(repr(signature).encode()).hexdigest()[:16]}
        if kind == "articles":
            context["news_page"] = get_country_news_page(code, **options)
            context["article_cards"] = country_article_cards(context["news_page"])
            google_key, _ = self.keys[code]
            context["google_pending"] = bool(google_key and self._pending(google_key))
            template = "news/partials/country_news.html"
        else:
            from .world_news import country_video_context
            return render_to_string("news/partials/country_videos.html", country_video_context(code, self.registry))
        return render_to_string(template, context)
