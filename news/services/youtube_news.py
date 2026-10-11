from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import replace
from datetime import UTC, datetime

from django.conf import settings
from django.core.cache import cache

from news.adapters.youtube import YouTubeFeedParseError, normalize_youtube_feed
from news.preferences import effective_registry, freshness_seconds
from news.registry import SourceRegistry
from news.types import CountryVideosPage, NewsSource, VideoItem, VideoSourceResult

from .cache import age, cache_lock, deserialize_video_items, parse_datetime, youtube_cache_key
from .country_matcher import match_title
from .country_news import _country_for_code
from .fetch import FeedFetchError, FeedResponse, fetch_feed
from .region_routing import eligible_youtube_sources


logger = logging.getLogger(__name__)


def _cache_key(source: NewsSource) -> str:
    return youtube_cache_key(source)


def _source_result(
    source: NewsSource,
    snapshot: dict,
    *,
    stale: bool = False,
    failed: bool = False,
) -> VideoSourceResult:
    items = deserialize_video_items(snapshot, source) or ()
    if failed and not items:
        status = "unavailable"
    elif stale:
        status = "stale"
    else:
        status = "available"
    return VideoSourceResult(
        source=source,
        items=items,
        fetched_at=parse_datetime(snapshot.get("last_success_at")),
        is_stale=stale,
        refresh_failed=failed,
        error="" if items else snapshot.get("last_error", ""),
        status=status,
    )


def get_youtube_feed(
    source: NewsSource,
    *,
    cache_backend=None,
    fetcher: Callable[..., FeedResponse] = fetch_feed,
    now: datetime | None = None,
    retry_failed: bool = False,
    force_refresh: bool = False,
    fresh_seconds: int | None = None,
) -> VideoSourceResult:
    feed_url = source.youtube_feed_url
    if not source.enabled_by_default:
        return VideoSourceResult(source, (), None, error="Channel is disabled.", status="disabled")
    if not feed_url or not source.allowed_hosts:
        return VideoSourceResult(source, (), None, error="Channel configuration is unavailable.", status="unavailable")

    backend = cache_backend or cache
    current_time = now or datetime.now(UTC)
    fresh_seconds = settings.NEWS_REFRESH_SECONDS if fresh_seconds is None else fresh_seconds
    key = _cache_key(source)
    with cache_lock(key):
        snapshot = backend.get(key)
        if not isinstance(snapshot, dict) or deserialize_video_items(snapshot, source) is None:
            snapshot = {}
        retrying_failure = retry_failed and bool(snapshot.get("last_error"))
        success_age = age(current_time, snapshot.get("fetched_at"))
        if (
            not force_refresh and not retrying_failure
            and snapshot.get("last_success_at")
            and success_age is not None
            and success_age.total_seconds() < fresh_seconds
        ):
            return _source_result(source, snapshot)
        failure_age = age(current_time, snapshot.get("last_attempt_at"))
        if (
            not force_refresh and not retrying_failure
            and snapshot.get("last_error")
            and failure_age is not None
            and failure_age.total_seconds() < settings.NEWS_YOUTUBE_FAILURE_BACKOFF_SECONDS
        ):
            return _source_result(
                source,
                snapshot,
                stale=bool(snapshot.get("last_success_at")),
                failed=True,
            )

        try:
            response = fetcher(
                feed_url,
                allowed_hosts=set(source.allowed_hosts),
                etag=snapshot.get("etag"),
                last_modified=snapshot.get("last_modified"),
            )
            if response.not_modified:
                if not snapshot.get("last_success_at"):
                    raise FeedFetchError("The feed returned not-modified without cached content")
                snapshot.update({
                    "fetched_at": current_time.isoformat(),
                    "etag": response.etag,
                    "last_modified": response.last_modified,
                    "last_error": "",
                    "last_error_detail": "",
                    "last_attempt_at": current_time.isoformat(),
                })
            else:
                normalized = normalize_youtube_feed(
                    response.body,
                    source,
                    settings.NEWS_YOUTUBE_FEED_CACHE_ITEMS,
                )
                snapshot = {
                    "items": [item.as_cache_value() for item in normalized.items],
                    "fetched_at": current_time.isoformat(),
                    "last_success_at": current_time.isoformat(),
                    "etag": response.etag,
                    "last_modified": response.last_modified,
                    "last_error": "",
                    "last_error_detail": "",
                    "last_attempt_at": current_time.isoformat(),
                }
            backend.set(key, snapshot, settings.NEWS_YOUTUBE_STALE_SECONDS)
            return _source_result(source, snapshot)
        except (FeedFetchError, YouTubeFeedParseError) as error:
            snapshot["last_error"] = "This video channel is temporarily unavailable."
            snapshot["last_error_detail"] = str(error)[:240]
            snapshot["last_attempt_at"] = current_time.isoformat()
            last_success_age = age(current_time, snapshot.get("last_success_at"))
            if (
                last_success_age is not None
                and last_success_age.total_seconds() < settings.NEWS_YOUTUBE_STALE_SECONDS
            ):
                remaining = max(
                    1,
                    settings.NEWS_YOUTUBE_STALE_SECONDS - int(last_success_age.total_seconds()),
                )
                backend.set(key, snapshot, remaining)
                return _source_result(source, snapshot, stale=True, failed=True)
            empty = {
                "items": [],
                "fetched_at": None,
                "last_success_at": None,
                "etag": None,
                "last_modified": None,
                "last_error": "This video channel is temporarily unavailable.",
                "last_error_detail": str(error)[:240],
                "last_attempt_at": current_time.isoformat(),
            }
            backend.set(key, empty, settings.NEWS_YOUTUBE_FAILURE_BACKOFF_SECONDS)
            return _source_result(source, empty, failed=True)


def _failed_source(source: NewsSource) -> VideoSourceResult:
    return VideoSourceResult(
        source,
        (),
        None,
        refresh_failed=True,
        error="This video channel is temporarily unavailable.",
        status="unavailable",
    )


def _newest_key(item: VideoItem, sources: dict[str, NewsSource]) -> tuple:
    return (
        item.published_at is None,
        -(item.published_at.timestamp()) if item.published_at else 0,
        sources[item.source_id].display_priority,
        item.source_order,
        item.source_id,
    )


def get_country_videos(
    iso2: str,
    *,
    cache_backend=None,
    registry: SourceRegistry | None = None,
    fetcher: Callable[..., FeedResponse] = fetch_feed,
    now: datetime | None = None,
    retry_failed: bool = False,
) -> CountryVideosPage:
    country = _country_for_code(iso2)
    source_registry = registry or effective_registry()
    fresh_seconds = freshness_seconds() if registry is None else settings.NEWS_REFRESH_SECONDS
    sources = eligible_youtube_sources(country, source_registry)
    if not sources:
        return CountryVideosPage(country["iso_a2"], country["name"], (), (), "empty")

    def load(source: NewsSource) -> VideoSourceResult:
        try:
            return get_youtube_feed(
                source,
                cache_backend=cache_backend,
                fetcher=fetcher,
                now=now,
                retry_failed=retry_failed,
                fresh_seconds=fresh_seconds,
            )
        except Exception as error:
            logger.warning("YouTube feed %s failed with %s", source.id, type(error).__name__)
            return _failed_source(source)

    executor = ThreadPoolExecutor(max_workers=min(settings.NEWS_YOUTUBE_WORKERS, len(sources)))
    futures = {executor.submit(load, source): source for source in sources}
    done, pending = wait(futures, timeout=settings.NEWS_YOUTUBE_FETCH_WAIT_SECONDS)
    result_by_source = {futures[future].id: future.result() for future in done}
    for future in pending:
        future.cancel()
        source = futures[future]
        result_by_source[source.id] = _failed_source(source)
    executor.shutdown(wait=False, cancel_futures=True)
    source_results = tuple(result_by_source[source.id] for source in sources)

    source_map = {source.id: source for source in sources}
    matched_by_source: dict[str, tuple[VideoItem, ...]] = {}
    for result in source_results:
        matches = []
        for item in result.items:
            evidence = match_title(item.title)
            if country["iso_a2"] not in {match.country_code for match in evidence}:
                continue
            matches.append(replace(
                item,
                matched_country_codes=tuple(sorted({match.country_code for match in evidence})),
                match_evidence=tuple(
                    f"{match.match_class.value}:{match.country_code}:{match.alias}"
                    for match in evidence
                ),
                is_stale=result.is_stale,
            ))
        matched_by_source[result.source.id] = tuple(sorted(
            matches,
            key=lambda item: _newest_key(item, source_map),
        )[:settings.NEWS_YOUTUBE_PER_CHANNEL_LIMIT])

    unique_items = []
    seen_ids: set[str] = set()
    for item in sorted(
        (item for items in matched_by_source.values() for item in items),
        key=lambda item: _newest_key(item, source_map),
    ):
        if item.video_id in seen_ids:
            continue
        seen_ids.add(item.video_id)
        unique_items.append(item)
        if len(unique_items) >= settings.NEWS_YOUTUBE_TOTAL_LIMIT:
            break
    visible_ids = {item.video_id for item in unique_items}
    source_results = tuple(
        replace(
            result,
            items=tuple(item for item in matched_by_source[result.source.id] if item.video_id in visible_ids),
        )
        for result in source_results
    )

    failed_count = sum(result.refresh_failed for result in source_results)
    has_stale = any(result.is_stale for result in source_results)
    if failed_count == len(source_results) and not any(result.items for result in source_results):
        status = "unavailable"
        warning = "Video channels are temporarily unavailable."
    elif failed_count == len(source_results) and has_stale:
        status = "stale"
        warning = "Video results are cached because the channel could not be refreshed."
    elif failed_count:
        status = "partial"
        warning = f"{failed_count} video channel{'s' if failed_count != 1 else ''} could not be refreshed; cached results are shown where available."
    elif has_stale:
        status = "stale"
        warning = "Some video results are cached because a channel could not be refreshed."
    else:
        status = "success" if unique_items else "empty"
        warning = ""
    return CountryVideosPage(
        country["iso_a2"],
        country["name"],
        tuple(unique_items),
        source_results,
        status,
        warning,
    )
