"""Rolling metadata history. All collection is from existing cached feed items."""
from datetime import timedelta
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
from django.db import DatabaseError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from news.models import ArchivedNews, ArchivedNewsCountry, ArchivedNewsSource
from news.preferences import effective_registry
from news.types import SourceKind
from .cache import deserialize_items, deserialize_video_items
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


def _cleanup_locked(now, force=False):
    global _next_cleanup
    if not force and time.monotonic() < _next_cleanup:
        return False, set()
    _next_cleanup = time.monotonic() + 3600
    changed = False
    touched = set()
    while True:
        expired = list(ArchivedNews.objects.filter(expires_at__lte=now).values_list("pk", flat=True)[:500])
        if not expired:
            break
        touched.update(ArchivedNewsCountry.objects.filter(item_id__in=expired).values_list("country_code", flat=True))
        ArchivedNews.objects.filter(pk__in=expired).delete()
        changed = True
    count = ArchivedNews.objects.count()
    total = ArchivedNews.objects.aggregate(total=Sum("metadata_bytes"))["total"] or 0
    # Fixed overhead includes a conservative allowance for indexes/row storage.
    total += ArchivedNewsSource.objects.count() * 512 + ArchivedNewsCountry.objects.count() * 256
    remove = []
    if count > settings.NEWS_ARCHIVE_MAX_ITEMS or total > settings.NEWS_ARCHIVE_MAX_BYTES:
        for identity, size, origin_count, tag_count in _oldest_sizes():
            if count <= settings.NEWS_ARCHIVE_MAX_ITEMS and total <= settings.NEWS_ARCHIVE_MAX_BYTES:
                break
            remove.append(identity)
            count -= 1
            total -= size + origin_count * 512 + tag_count * 256
        for start in range(0, len(remove), 500):
            touched.update(ArchivedNewsCountry.objects.filter(item_id__in=remove[start:start+500]).values_list("country_code", flat=True))
            ArchivedNews.objects.filter(pk__in=remove[start:start+500]).delete()
        changed = changed or bool(remove)
    return changed, touched


def _oldest_sizes():
    from django.db.models import Count
    cursor = None
    while True:
        rows = ArchivedNews.objects.order_by("sort_date", "identity")
        if cursor:
            rows = rows.filter(Q(sort_date__gt=cursor[0]) | Q(sort_date=cursor[0], identity__gt=cursor[1]))
        batch = list(rows.values_list("identity", "metadata_bytes", "sort_date")[:500])
        if not batch:
            return
        ids = [row[0] for row in batch]
        origins = dict(ArchivedNewsSource.objects.filter(item_id__in=ids).values("item_id").annotate(n=Count("id")).values_list("item_id", "n"))
        tags = dict(ArchivedNewsCountry.objects.filter(item_id__in=ids).values("item_id").annotate(n=Count("id")).values_list("item_id", "n"))
        for identity, size, date in batch:
            yield identity, size, origins.get(identity, 0), tags.get(identity, 0)
        cursor = (batch[-1][2], batch[-1][0])


def maintain_archive():
    with _write_lock:
        try:
            changed, codes = _cleanup_locked(timezone.now())
            if changed:
                _changed(codes)
        except DatabaseError:
            _log_failure()


def _log_failure():
    global _next_error_log
    if time.monotonic() >= _next_error_log:
        logger.warning("News archive is unavailable; current feeds remain available. Apply pending migrations if necessary.")
        _next_error_log = time.monotonic() + 3600


def capture_snapshot(job, snapshot, registry, now=None):
    """Idempotently collect an already-successful cache snapshot, without fetching."""
    if not isinstance(snapshot, dict) or not snapshot.get("last_success_at"):
        return
    stamp = snapshot.get("last_success_at")
    with _write_lock:
        if _seen.get(job) == stamp:
            return
        try:
            _collect(job, snapshot, registry, now or timezone.now())
            _seen[job] = stamp
        except DatabaseError:
            _log_failure()


def forget_removed_jobs(jobs):
    with _write_lock:
        active = set(jobs)
        for job in list(_seen):
            if job not in active:
                del _seen[job]


def _collect(job, snapshot, registry, now):
    category, identifier = job
    kind = "videos" if category == "youtube" else "articles"
    if category == "rss":
        feed = next((feed for feed in registry.feeds if feed.id == identifier), None)
        if not feed or not feed.enabled_by_default:
            return
        source_id, feed_id = feed.provider_id, feed.id
        items = deserialize_items(snapshot) or ()
        category = "regional"
    elif category == "youtube":
        source = next((source for source in registry.sources if source.id == identifier), None)
        if not source or not source.enabled_by_default:
            return
        source_id = feed_id = source.id
        items = deserialize_video_items(snapshot, source) or ()
        category = "videos"
    else:
        source = registry.get("google_news_country")
        if not source.enabled_by_default:
            return
        source_id, feed_id = source.id, f"{source.id}:{identifier}"
        items = deserialize_items(snapshot) or ()
    cutoff = now - timedelta(days=settings.NEWS_ARCHIVE_DAYS)
    from .country_news import _countries_by_code
    valid_countries = set(_countries_by_code())
    changed = False
    touched = set()
    with transaction.atomic():
        for item in items:
            link = item.watch_url if kind == "videos" else item.link
            if len(link) > 2048:
                continue  # Never truncate an external link into a broken URL.
            published = item.published_at
            if published and published < cutoff:
                continue
            # A future publisher date must not make retention unlimited.
            sort_date = published if published and published <= now else now
            identity, fingerprint = identities(item, kind)
            existing = ArchivedNews.objects.filter(Q(pk=identity) | Q(fingerprint=fingerprint), kind=kind).order_by("first_seen_at").first()
            row = existing or ArchivedNews(identity=identity, fingerprint=fingerprint, kind=kind,
                                           first_seen_at=now, sort_date=sort_date, expires_at=sort_date+timedelta(days=settings.NEWS_ARCHIVE_DAYS))
            if row.expires_at <= now:
                continue
            publisher = item.channel_name if kind == "videos" else item.publisher
            # Prefer the direct publisher link when joining a Google wrapper.
            direct = kind == "articles" and category == "regional" and urlsplit(row.link).hostname == "news.google.com"
            values = {"title":item.title[:300], "link":link[:2048], "publisher":publisher[:200],
                      "summary":item.summary[:2000] if kind == "articles" else "", "video_id":item.video_id if kind == "videos" else ""}
            if not existing or direct:
                for key, value in values.items():
                    setattr(row, key, value)
                row.published_at = published
                row.metadata_bytes = len(json.dumps(values, ensure_ascii=False).encode("utf-8")) + 1024
                row.save()
                changed = True
            origin, created = ArchivedNewsSource.objects.get_or_create(item=row, feed_id=feed_id,
                defaults={"source_id":source_id, "category":category})
            if existing and (direct or created):
                touched.update(row.country_tags.values_list("country_code", flat=True))
            changed = changed or created
            if category == "google":
                codes = {identifier} if identifier in valid_countries else set()
            else:
                evidence = match_title(item.title) if kind == "videos" else match_country_text(item.title, item.summary)
                codes = {match.country_code for match in evidence} & valid_countries
            for code in codes:
                _tag, created = ArchivedNewsCountry.objects.get_or_create(item=row, country_code=code)
                changed = changed or created
            touched.update(codes)
    if changed:
        # Enforce all limits after every changed snapshot, not just daily cleanup.
        _pruned, removed_codes = _cleanup_locked(now, force=True)
        _changed(touched | removed_codes)


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


def archived_items(kind, country_code=None, *, category="all", exclude=(), registry=None):
    registry = registry or effective_registry()
    origins = ArchivedNewsSource.objects.filter(feed_id__in=enabled_feed_ids(registry, kind, country_code, category))
    rows = ArchivedNews.objects.filter(kind=kind, expires_at__gt=timezone.now(), pk__in=origins.values("item_id"))
    if country_code:
        rows = rows.filter(pk__in=ArchivedNewsCountry.objects.filter(country_code=country_code).values("item_id"))
    keys, fingerprints = zip(*(identities(item, kind) for item in exclude)) if exclude else ((), ())
    return rows.exclude(Q(pk__in=keys) | Q(fingerprint__in=fingerprints))


def remove_origins(feed_ids):
    with _write_lock:
        try:
            with transaction.atomic():
                touched = set(ArchivedNewsCountry.objects.filter(item__origins__feed_id__in=feed_ids).values_list("country_code", flat=True))
                ArchivedNewsSource.objects.filter(feed_id__in=feed_ids).delete()
                ArchivedNews.objects.filter(origins__isnull=True).delete()
            _changed(touched)
        except DatabaseError:
            _log_failure()
