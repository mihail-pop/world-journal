"""Rolling metadata history. All collection is from existing cached feed items."""
from hashlib import sha256
import json
import logging
import re
from threading import Lock
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from core.database import write_transaction
from news.models import ArchiveUsage, ArchivedNews, ArchivedNewsCountry, ArchivedNewsSource, FeedState
from news.preferences import archive_storage_bytes, effective_registry
from news.types import SourceKind
from .cache import deserialize_items, deserialize_video_items, fixed_feed_cache_key, google_cache_key, youtube_cache_key
from .country_matcher import match_country_text, match_title

logger = logging.getLogger(__name__)
_write_lock = Lock()
_seen = {}  # One snapshot stamp per configured feed, not one per news item.
_next_cleanup = 0.0
_next_error_log = 0.0
REVISION_KEY = "news:archive:revision"


def revision():
    value = cache.get(REVISION_KEY, {})
    return value.get("world", "") if isinstance(value, dict) else ""


def country_revisions(codes):
    value = cache.get(REVISION_KEY, {})
    countries = value.get("countries", {}) if isinstance(value, dict) else {}
    return {code:countries.get(code, "") for code in codes}


def _changed(codes):
    value = cache.get(REVISION_KEY, {})
    if not isinstance(value, dict):
        value = {}
    token = uuid4().hex
    value["world"] = token
    countries = value.setdefault("countries", {})
    for code in codes:
        countries[code] = token
    cache.set(REVISION_KEY, value, None)


def canonical_link(link):
    parts = urlsplit(link)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.casefold().startswith("utm_") and key.casefold() not in {"fbclid", "gclid"}]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(sorted(query)), ""))


def _hash(text):
    return sha256(text.encode("utf-8")).hexdigest()


def identities(item, kind):
    if kind == "videos":
        key = _hash("video:" + item.video_id)
        return key, key
    normalized = lambda text: " ".join(re.sub(r"[^\w]+", " ", text.casefold()).split())
    # Dated headline/publisher matches also join Google wrappers to direct links.
    stamp = item.published_at.isoformat() if item.published_at else ""
    identity = _hash("article:" + canonical_link(item.link))
    fingerprint = _hash(f"article:{normalized(item.title)}:{normalized(item.publisher)}:{stamp}") if stamp else identity
    return identity, fingerprint


def _cleanup_locked(force=False):
    global _next_cleanup
    if not force and time.monotonic() < _next_cleanup:
        return False, set()
    _next_cleanup = time.monotonic() + settings.NEWS_REFRESH_SECONDS
    budget = archive_storage_bytes()
    count, total = ArchiveUsage.objects.values_list("item_count", "estimated_bytes").get(pk=1)
    if count <= settings.NEWS_ARCHIVE_MAX_ITEMS and total <= budget:
        return False, set()
    target = max(0, budget - settings.NEWS_ARCHIVE_PRUNE_BYTES) if total > budget else budget
    changed, touched = False, set()
    while count > settings.NEWS_ARCHIVE_MAX_ITEMS or total > target:
        ids = list(ArchivedNews.objects.order_by("sort_date", "identity").values_list("pk", flat=True)[:500])
        if not ids:
            break
        touched.update(ArchivedNewsCountry.objects.filter(item_id__in=ids).values_list("country_code", flat=True))
        # Release the writer queue between batches so journal/settings saves
        # can proceed even when the user substantially lowers the budget.
        with write_transaction():
            ArchivedNews.objects.filter(pk__in=ids).delete()
        changed = True
        count, total = ArchiveUsage.objects.values_list("item_count", "estimated_bytes").get(pk=1)
    return changed, touched


def maintain_archive(*, force=False):
    with _write_lock:
        try:
            changed, codes = _cleanup_locked(force=force)
            if changed:
                _changed(codes)
        except DatabaseError as error:
            _log_failure(error)


def _log_failure(error):
    global _next_error_log
    if time.monotonic() >= _next_error_log:
        logger.warning("Could not update the news archive: %s", error)
        _next_error_log = time.monotonic() + 3600


def capture_snapshot(job, snapshot, registry, now=None):
    """Idempotently collect an already-successful cache snapshot, without fetching."""
    if not isinstance(snapshot, dict) or not snapshot.get("last_success_at"):
        return False
    stamp = snapshot.get("last_success_at")
    category, identifier = job
    if category == "rss":
        feed = next((feed for feed in registry.feeds if feed.id == identifier), None)
        if feed is None:
            return False
        key = fixed_feed_cache_key(feed)
    elif category == "youtube":
        key = youtube_cache_key(registry.get(identifier))
    else:
        key = google_cache_key(registry.get("google_news_country"), identifier)
    with _write_lock:
        if _seen.get(job) == stamp:
            return True
        try:
            if FeedState.objects.filter(pk=key, archive_stamp=stamp).exists():
                _seen[job] = stamp
                return True
            if not _collect(job, snapshot, registry, now or timezone.now(), key, stamp):
                return False
            _seen[job] = stamp
            return True
        except DatabaseError as error:
            _log_failure(error)
            return False


def _collect(job, snapshot, registry, now, cache_key, stamp):
    category, identifier = job
    kind = "videos" if category == "youtube" else "articles"
    if category == "rss":
        feed = next((feed for feed in registry.feeds if feed.id == identifier), None)
        if not feed or not feed.enabled_by_default:
            return False
        source_id, feed_id = feed.provider_id, feed.id
        items = deserialize_items(snapshot) or ()
        category = "regional"
    elif category == "youtube":
        source = next((source for source in registry.sources if source.id == identifier), None)
        if not source or not source.enabled_by_default:
            return False
        source_id = feed_id = source.id
        items = deserialize_video_items(snapshot, source) or ()
        category = "videos"
    else:
        source = registry.get("google_news_country")
        if not source.enabled_by_default:
            return False
        source_id, feed_id = source.id, f"{source.id}:{identifier}"
        items = deserialize_items(snapshot) or ()
    from .country_news import _countries_by_code
    valid_countries = set(_countries_by_code())
    prepared = []
    # Country matching can be slow on a cold start. Finish it before asking
    # SQLite for the writer lock so a user save can run during preparation.
    for item in items:
        link = item.watch_url if kind == "videos" else item.link
        if len(link) > 2048:
            continue
        if category == "google":
            codes = {identifier} if identifier in valid_countries else set()
        else:
            evidence = match_title(item.title) if kind == "videos" else match_country_text(item.title, item.summary)
            codes = {match.country_code for match in evidence} & valid_countries
        prepared.append((item, link, codes, *identities(item, kind)))

    # Separate indexed lookups avoid SQLite choosing a scan of every article
    # for an identity OR fingerprint query. Finish reads before reserving a writer.
    by_id = ArchivedNews.objects.in_bulk({row[3] for row in prepared})
    by_fingerprint = {}
    fingerprints = {row[4] for row in prepared}
    for row in ArchivedNews.objects.filter(fingerprint__in=fingerprints).order_by("first_seen_at"):
        if row.kind == kind:
            by_fingerprint.setdefault(row.fingerprint, row)
    new_rows, updates, selected, touched = {}, {}, {}, set()
    for item, link, codes, identity, fingerprint in prepared:
        candidates = [row for row in (by_id.get(identity), by_fingerprint.get(fingerprint)) if row is not None]
        row = min(candidates, key=lambda row: row.first_seen_at) if candidates else None
        created = row is None
        sort_date = item.published_at if item.published_at and item.published_at <= now else now
        if created:
            row = ArchivedNews(identity=identity, fingerprint=fingerprint, kind=kind, first_seen_at=now, sort_date=sort_date)
            new_rows[row.pk] = row
            by_id[identity] = row
            by_fingerprint.setdefault(fingerprint, row)
        direct = kind == "articles" and category == "regional" and urlsplit(row.link).hostname == "news.google.com"
        if created or direct:
            values = {"title":item.title[:300], "link":link[:2048],
                      "publisher":(item.channel_name if kind == "videos" else item.publisher)[:200],
                      "summary":item.summary[:2000] if kind == "articles" else "",
                      "video_id":item.video_id if kind == "videos" else "",
                      "view_count":(item.view_count if item.view_count is not None else row.view_count) if kind == "videos" else None}
            for name, value in values.items():
                setattr(row, name, value)
            row.published_at = item.published_at
            row.metadata_bytes = len(json.dumps(values, ensure_ascii=False).encode("utf-8")) + 1024
            if not created:
                updates[row.pk] = row
        elif kind == "videos" and item.view_count is not None and item.view_count != row.view_count:
            row.view_count = item.view_count
            values = {name: getattr(row, name) for name in ("title", "link", "publisher", "summary", "video_id", "view_count")}
            row.metadata_bytes = len(json.dumps(values, ensure_ascii=False).encode("utf-8")) + 1024
            updates[row.pk] = row
        selected.setdefault(row.pk, set()).update(codes)

    row_ids = set(selected)
    origins = set(ArchivedNewsSource.objects.filter(feed_id=feed_id, item_id__in=row_ids).values_list("item_id", flat=True))
    tags = set(ArchivedNewsCountry.objects.filter(item_id__in=row_ids).values_list("item_id", "country_code"))
    missing_origins = row_ids - origins
    missing_tags = {(identity, code) for identity, codes in selected.items() for code in codes} - tags
    for identity, code in tags | missing_tags:
        if identity in missing_origins or identity in updates or (identity, code) in missing_tags:
            touched.add(code)
    changed = bool(new_rows or updates or missing_origins or missing_tags)
    with write_transaction():
        if new_rows:
            ArchivedNews.objects.bulk_create(new_rows.values(), ignore_conflicts=True)
        if updates:
            ArchivedNews.objects.bulk_update(updates.values(), ["title", "link", "publisher", "summary", "video_id", "view_count", "published_at", "metadata_bytes"])
        if missing_origins:
            ArchivedNewsSource.objects.bulk_create([ArchivedNewsSource(item_id=identity, feed_id=feed_id,
                source_id=source_id, category=category) for identity in missing_origins], ignore_conflicts=True)
        if missing_tags:
            ArchivedNewsCountry.objects.bulk_create([ArchivedNewsCountry(item_id=identity, country_code=code)
                for identity, code in missing_tags], ignore_conflicts=True)
        FeedState.objects.filter(pk=cache_key).update(archive_stamp=stamp)
        if changed:
            _changed(touched)
    return True


def enabled_feed_ids(registry, kind, country_code=None, category="all"):
    ids = []
    if kind == "articles":
        google = registry.get("google_news_country")
        if google.enabled_by_default and category in {"all", "google"}:
            ids.append(f"{google.id}:{country_code or 'WORLD'}")
        ids += [feed.id for feed in registry.feeds if feed.enabled_by_default and category in {"all", "regional", feed.provider_id}]
    else:
        sources = registry.sources
        if country_code:
            from .country_news import _country_for_code
            from .region_routing import eligible_youtube_sources
            sources = eligible_youtube_sources(_country_for_code(country_code), registry)
        ids += [source.id for source in sources if source.enabled_by_default and source.kind is SourceKind.YOUTUBE and category in {"all", source.id}]
    return ids


def restrict_origins(rows, origins):
    # Materialize only small source selections. SQLite otherwise sometimes
    # scans the whole date index even for a feed with just a few saved items.
    small = list(origins.order_by().values_list("item_id", flat=True)[:257])
    return rows.filter(pk__in=small if len(small) <= 256 else origins.values("item_id"))


def archived_items(kind, country_code=None, *, category="all", exclude=(), registry=None):
    registry = registry or effective_registry()
    origins = ArchivedNewsSource.objects.filter(feed_id__in=enabled_feed_ids(registry, kind, country_code, category))
    rows = ArchivedNews.objects.filter(kind=kind)
    if category != "all" and not country_code:
        rows = restrict_origins(rows, origins)
    else:
        rows = rows.filter(Exists(origins.filter(item_id=OuterRef("pk"))))
    if country_code:
        rows = rows.filter(pk__in=ArchivedNewsCountry.objects.filter(country_code=country_code).values("item_id"))
    keys, fingerprints = zip(*(identities(item, kind) for item in exclude)) if exclude else ((), ())
    return rows.exclude(Q(pk__in=keys) | Q(fingerprint__in=fingerprints))


def remove_origins(feed_ids):
    with _write_lock:
        try:
            with write_transaction():
                touched = set(ArchivedNewsCountry.objects.filter(item__origins__feed_id__in=feed_ids).values_list("country_code", flat=True))
                ArchivedNewsSource.objects.filter(feed_id__in=feed_ids).delete()
                ArchivedNews.objects.filter(origins__isnull=True).delete()
            _changed(touched)
        except DatabaseError as error:
            _log_failure(error)
