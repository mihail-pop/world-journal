from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import blake2b
from math import ceil
from random import uniform
from threading import Lock

from django.conf import settings
from django.utils.timezone import localtime
from news.adapters.rss import clean_article_text, is_google_news_link
from news.google_pacing import maximum_gap
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


def next_refresh(started_at, interval):
    jitter = refresh_jitter("cycle", {"fetched_at": started_at.isoformat()})
    return started_at + timedelta(seconds=interval + jitter)


def feed_snapshot(backend, key):
    snapshot = backend.get(key)
    if isinstance(snapshot, dict):
        return snapshot
    restore = getattr(backend, "feed_failure_metadata", None)
    # Response bodies may expire while the server is stopped. Their compact
    # failure state still owns the retry deadline.
    return {"items": [], **(restore(key) or {})} if restore else {}


def failure_deadline(snapshot, interval):
    failed = parse_datetime(snapshot.get("failed_at")) or parse_datetime(snapshot.get("last_attempt_at"))
    publisher_deadline = parse_datetime(snapshot.get("server_retry_at"))
    if not snapshot.get("failed_at"):  # Older snapshots did not store Retry-After separately.
        publisher_deadline = parse_datetime(snapshot.get("retry_after_at"))
    return max((value for value in (next_refresh(failed, interval) if failed else None, publisher_deadline) if value), default=None)


def failure_retry_pending(snapshot, now, interval):
    if not snapshot.get("last_error"):
        return False
    deadline = failure_deadline(snapshot, interval)
    return bool(deadline and now < deadline)


def publisher_retry_pending(snapshot, now):
    deadline = parse_datetime(snapshot.get("server_retry_at"))
    return bool(deadline and now < deadline)


def record_failure(snapshot, now, error, interval):
    retry_after = getattr(error, "retry_after_seconds", None)
    publisher_deadline = now + timedelta(seconds=retry_after) if retry_after else None
    snapshot.update(failed_at=now.isoformat(), server_retry_at=publisher_deadline.isoformat() if publisher_deadline else None)
    deadline = failure_deadline(snapshot, interval)
    snapshot["retry_after_at"] = deadline.isoformat()
    return ceil((deadline - now).total_seconds()) + 60


GOOGLE_COOLDOWN_KEY = "news:google_rate_limit"
_GOOGLE_REQUEST_LOCK = Lock()
_next_google_request_at = 0.0
_google_deadline_loaded = False


@dataclass
class GoogleRequest:
    attempted_at: datetime
    spacing: tuple[int, int]
    gap_seconds: float
    ready_at: datetime | None = None

    def metadata(self, completed_at):
        self.ready_at = completed_at + timedelta(seconds=self.gap_seconds)
        return {"google_spacing_seconds": self.spacing[0], "google_spacing_max_seconds": self.spacing[1],
                "google_request_ready_at": self.ready_at.isoformat()}


def _google_pause_until(state, now):
    deadline = parse_datetime(state.get("retry_after_at"))
    return deadline if deadline and now < deadline else None


def google_pause_until(backend, now):
    return _google_pause_until(backend.get(GOOGLE_COOLDOWN_KEY) or {}, now)


def google_request_spacing_range(state, pacing):
    if fixed := pacing.get("fixed"):
        return tuple(fixed)
    baseline = settings.NEWS_GOOGLE_REQUEST_SPACING_SECONDS
    step = settings.NEWS_GOOGLE_REQUEST_SPACING_STEP_SECONDS
    ceiling = maximum_gap(pacing)
    minimum = baseline
    if state.get("adaptive_token") == pacing.get("adaptive_token"):
        saved = state.get("request_spacing_seconds", baseline)
        # Finish the existing 35–40-second trial before switching to the new floor.
        minimum = saved if saved == 35 and "adaptive_token" not in state else max(baseline, saved)
    return ceiling if minimum >= ceiling[0] else (minimum, min(minimum + step, ceiling[1]))


@contextmanager
def google_request_slot(backend, pacing, *, now=None):
    """Serialize automatic and manual requests, with a gap after each response."""
    global _next_google_request_at, _google_deadline_loaded
    with _GOOGLE_REQUEST_LOCK:
        state = backend.get(GOOGLE_COOLDOWN_KEY) or {}
        if _google_pause_until(state, now or datetime.now(UTC)):
            yield None
            return
        if not _google_deadline_loaded:
            restore = getattr(backend, "google_request_deadline", None)
            deadline = restore() if restore else None
            if deadline:
                remaining = max(0, (deadline - (now or datetime.now(UTC))).total_seconds())
                _next_google_request_at = max(_next_google_request_at, time.monotonic() + remaining)
            _google_deadline_loaded = True
        delay = _next_google_request_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)
            # A pause may have been saved while waiting for this request's turn.
            state = backend.get(GOOGLE_COOLDOWN_KEY) or {}
        attempted_at = now or datetime.now(UTC)
        if _google_pause_until(state, attempted_at):
            yield None
            return
        spacing = google_request_spacing_range(state, pacing)
        day = localtime(attempted_at).date().isoformat()
        history = state.get("gap_history", {})
        if history.get(day) != spacing:
            history = {**history, day: spacing}
            state["gap_history"] = dict(sorted(history.items())[-2:])
            backend.set(GOOGLE_COOLDOWN_KEY, state, None)
        request = GoogleRequest(attempted_at, spacing, uniform(*spacing))
        try:
            yield request
        finally:
            completed_at = now or datetime.now(UTC)
            if request.ready_at is None:
                request.metadata(completed_at)
            _next_google_request_at = time.monotonic() + max(0, (request.ready_at - completed_at).total_seconds())


def pause_google(backend, now, error, country, pacing, spacing):
    # One blocked country must pause all country queries, including manual sweeps.
    with cache_lock(GOOGLE_COOLDOWN_KEY):
        state = backend.get(GOOGLE_COOLDOWN_KEY) or {}
        deadline = parse_datetime(state.get("retry_after_at"))
        record_failure(state, now, error, settings.NEWS_GOOGLE_REFRESH_SECONDS)
        if deadline and now < deadline:
            state["retry_after_at"] = max(deadline, parse_datetime(state["retry_after_at"])).isoformat()
        elif not pacing.get("fixed"):
            floor = settings.NEWS_GOOGLE_REQUEST_SPACING_SECONDS
            step = settings.NEWS_GOOGLE_REQUEST_SPACING_STEP_SECONDS
            state["request_spacing_seconds"] = min(maximum_gap(pacing)[0], max(floor, spacing[0] + step))
            state["adaptive_token"] = pacing.get("adaptive_token")
        state["last_rate_limit_at"] = now.isoformat()
        state["resume_country"] = country
        minimum, maximum = google_request_spacing_range(state, pacing)
        backend.set(GOOGLE_COOLDOWN_KEY, state, None)
        logger.warning("Google News returned HTTP 429 for %s; resuming after %s with %s–%s-second gaps.",
                       country, state["retry_after_at"], minimum, maximum)


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
