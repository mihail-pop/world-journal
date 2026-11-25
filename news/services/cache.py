from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import blake2b
from math import ceil
from random import uniform
from threading import Lock

from django.conf import settings
from news.adapters.rss import clean_article_text, is_google_news_link
from news.types import NewsItem, NewsSource, VideoItem


_CACHE_LOCKS: dict[str, Lock] = {}
_CACHE_LOCKS_GUARD = Lock()
logger = logging.getLogger(__name__)


def google_cache_key(source: NewsSource, country_code: str) -> str:
    edition = source.edition_parameters["ceid"].replace(":", "-")
    return f"news:v{settings.NEWS_CACHE_SCHEMA_VERSION}:google_country:{country_code}:{edition}"


def fixed_feed_cache_key(feed) -> str:
    return f"news:v{settings.NEWS_CACHE_SCHEMA_VERSION}:rss:{feed.id}:{feed.language}"


def youtube_cache_key(source: NewsSource) -> str:
    return f"news:v{settings.NEWS_CACHE_SCHEMA_VERSION}:youtube:{source.id}:{source.language}:{source.youtube_channel_id}"


def cache_lock(key: str) -> Lock:
    with _CACHE_LOCKS_GUARD:
        return _CACHE_LOCKS.setdefault(key, Lock())


def parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def age(now: datetime, value: object) -> timedelta | None:
    parsed = parse_datetime(value)
    return now - parsed if parsed else None


def stale_cache_remaining(snapshot: dict, now: datetime, retention: int) -> int:
    if not snapshot.get("last_success_at"):
        return 0
    # A 304 validates the existing body without changing its archive stamp.
    checked_at = parse_datetime(snapshot.get("fetched_at")) or parse_datetime(snapshot.get("last_success_at"))
    return max(0, ceil(retention - (now - checked_at).total_seconds())) if checked_at else 0


def refresh_jitter(job, snapshot):
    """Extend the refresh interval, never the spacing between queued downloads."""
    stamp = snapshot.get("fetched_at")
    if not stamp:
        return 0  # Missing feeds should be prepared immediately.
    seed = repr((job, stamp)).encode()
    minimum = 60
    return minimum + int.from_bytes(blake2b(seed, digest_size=8).digest(), "big") % (settings.NEWS_REFRESH_JITTER_SECONDS - minimum + 1)


def failure_retry_pending(snapshot, now):
    if not snapshot.get("last_error"):
        return False
    deadline = parse_datetime(snapshot.get("retry_after_at"))
    if deadline:
        return now < deadline
    attempted = age(now, snapshot.get("last_attempt_at"))
    return attempted is not None and attempted.total_seconds() < settings.NEWS_FAILURE_BACKOFF_SECONDS


def record_failure(snapshot, now, error):
    count = min(6, int(snapshot.get("consecutive_failures", 0)) + 1)
    delay = min(settings.NEWS_FAILURE_BACKOFF_MAX_SECONDS, settings.NEWS_FAILURE_BACKOFF_SECONDS * 2 ** (count - 1))
    delay = max(delay, getattr(error, "retry_after_seconds", 0) or 0)
    snapshot.update(consecutive_failures=count, retry_after_at=(now + timedelta(seconds=delay)).isoformat())
    return delay + 60  # Keep empty failure records until the next eligible scan.


GOOGLE_COOLDOWN_KEY = "news:google_rate_limit"
_GOOGLE_REQUEST_LOCK = Lock()
_next_google_request_at = 0.0


def _google_pause_until(state, now):
    deadline = parse_datetime(state.get("retry_after_at"))
    return deadline if deadline and now < deadline else None


def google_pause_until(backend, now):
    return _google_pause_until(backend.get(GOOGLE_COOLDOWN_KEY) or {}, now)


def google_request_spacing_range(state):
    baseline = settings.NEWS_GOOGLE_REQUEST_SPACING_SECONDS
    step = settings.NEWS_GOOGLE_REQUEST_SPACING_STEP_SECONDS
    maximum = settings.NEWS_GOOGLE_MAX_REQUEST_SPACING_SECONDS
    # Five-second bands, ending with the wider 110–120-second band.
    final_minimum = maximum - 2 * step
    minimum = min(final_minimum, max(baseline, state.get("request_spacing_seconds", baseline)))
    return minimum, maximum if minimum == final_minimum else minimum + step


def google_request_spacing(state):
    return uniform(*google_request_spacing_range(state))


@contextmanager
def google_request_slot(backend, *, now=None):
    """Serialize automatic and manual requests, with a gap after each response."""
    global _next_google_request_at
    with _GOOGLE_REQUEST_LOCK:
        state = backend.get(GOOGLE_COOLDOWN_KEY) or {}
        if _google_pause_until(state, now or datetime.now(UTC)):
            yield None
            return
        delay = _next_google_request_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        attempted_at = now or datetime.now(UTC)
        # A pause may have been saved while this request waited for its turn.
        state = backend.get(GOOGLE_COOLDOWN_KEY) or {}
        if _google_pause_until(state, attempted_at):
            yield None
            return
        try:
            yield attempted_at
        finally:
            _next_google_request_at = time.monotonic() + google_request_spacing(state)


def pause_google(backend, now, error):
    # One blocked country must pause all country queries, including manual sweeps.
    with cache_lock(GOOGLE_COOLDOWN_KEY):
        state = backend.get(GOOGLE_COOLDOWN_KEY) or {}
        spacing, _maximum = google_request_spacing_range(state)
        deadline = parse_datetime(state.get("retry_after_at"))
        last_limited = parse_datetime(state.get("last_rate_limit_at")) or deadline
        # Isolated successes don't prove the limit is lifted for the full sweep.
        # Retain the count across requests/restarts until 24 hours without a 429.
        if (
            last_limited and (not deadline or now >= deadline)
            and (now - last_limited).total_seconds() >= settings.NEWS_GOOGLE_BACKOFF_RESET_SECONDS
        ):
            state = {"request_spacing_seconds": spacing}
        if deadline and now < deadline:
            deadline = max(deadline, now + timedelta(seconds=getattr(error, "retry_after_seconds", 0) or 0))
            state["retry_after_at"] = deadline.isoformat()
        else:
            record_failure(state, now, error)
        state["last_rate_limit_at"] = now.isoformat()
        state["request_spacing_seconds"] = spacing + settings.NEWS_GOOGLE_REQUEST_SPACING_STEP_SECONDS
        minimum, maximum = google_request_spacing_range(state)
        state["request_spacing_seconds"] = minimum
        # Keep the learned pace after the pause expires and across restarts.
        # This single small record changes only when Google returns HTTP 429.
        backend.set(GOOGLE_COOLDOWN_KEY, state, None)
        logger.warning("Google News returned HTTP 429; next request gaps: %s–%s seconds.", minimum, maximum)


def deserialize_items(snapshot: dict) -> tuple[NewsItem, ...] | None:
    values = snapshot.get("items")
    if not isinstance(values, list):
        return None
    items = []
    for value in values:
        if not isinstance(value, dict):
            return None
        title = value.get("title")
        link = value.get("link")
        publisher = value.get("publisher")
        summary = value.get("summary", "")
        provider_id = value.get("provider_id", "")
        provider_name = value.get("provider_name", "")
        feed_id = value.get("feed_id", "")
        feed_section = value.get("feed_section", "")
        contributing_sections = value.get("contributing_sections", [])
        source_order = value.get("source_order", 0)
        if (
            not all(isinstance(field, str) for field in (
                title,
                link,
                publisher,
                summary,
                provider_id,
                provider_name,
                feed_id,
                feed_section,
            ))
            or not isinstance(contributing_sections, list)
            or not all(isinstance(section, str) for section in contributing_sections)
            or not isinstance(source_order, int)
            or isinstance(source_order, bool)
        ):
            return None
        published_at = parse_datetime(value.get("published_at"))
        if value.get("published_at") is not None and published_at is None:
            return None
        # Normalize existing snapshots too, without invalidating or refetching feeds.
        title, summary = clean_article_text(
            title, publisher, summary,
            google=provider_id == "google_news_country" or is_google_news_link(link),
        )
        items.append(NewsItem(
            title=title,
            link=link,
            publisher=publisher,
            published_at=published_at,
            summary=summary,
            provider_id=provider_id,
            provider_name=provider_name,
            feed_id=feed_id,
            feed_section=feed_section,
            contributing_sections=tuple(contributing_sections),
            source_order=source_order,
        ))
    return tuple(items)


def deserialize_video_items(snapshot: dict, source: NewsSource) -> tuple[VideoItem, ...] | None:
    from news.adapters.youtube import (
        build_embed_url,
        build_thumbnail_url,
        build_watch_url,
        is_valid_video_id,
    )

    values = snapshot.get("items")
    if not isinstance(values, list):
        return None
    items = []
    seen_ids: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            return None
        video_id = value.get("video_id")
        title = value.get("title")
        source_order = value.get("source_order", 0)
        view_count = value.get("view_count")
        if type(view_count) is not int or view_count < 0:
            view_count = None
        if (
            not is_valid_video_id(video_id)
            or not isinstance(title, str)
            or not title
            or not isinstance(source_order, int)
            or isinstance(source_order, bool)
        ):
            return None
        published_at = parse_datetime(value.get("published_at"))
        if value.get("published_at") is not None and published_at is None:
            return None
        if video_id in seen_ids:
            continue
        seen_ids.add(video_id)
        items.append(VideoItem(
            source_id=source.id,
            channel_name=source.display_name,
            video_id=video_id,
            title=title,
            published_at=published_at,
            watch_url=build_watch_url(video_id),
            embed_url=build_embed_url(video_id),
            thumbnail_url=build_thumbnail_url(video_id),
            source_order=source_order,
            view_count=view_count,
        ))
    return tuple(items)
