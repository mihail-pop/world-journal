from __future__ import annotations

import logging
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import replace
from datetime import UTC, datetime

from django.conf import settings
from django.core.cache import cache

from news.adapters.rss import FeedParseError, normalize_feed
from news.types import FeedResult, NewsFeed, NewsItem, NewsProvider, RegionalProviderResult

from .cache import age, cache_lock, deserialize_items, fixed_feed_cache_key, parse_datetime
from .country_matcher import MatchClass, match_country_text
from .fetch import FeedFetchError, FeedResponse, fetch_feed
from .region_routing import has_regional_affinity


logger = logging.getLogger(__name__)
_MATCH_RANK = {
    MatchClass.HEADLINE_COUNTRY.value: 0,
    MatchClass.HEADLINE_RELATED.value: 1,
    MatchClass.SUMMARY_COUNTRY.value: 2,
}


def _cache_key(feed: NewsFeed) -> str:
    return fixed_feed_cache_key(feed)


def _feed_result(feed: NewsFeed, snapshot: dict, *, stale: bool = False, failed: bool = False) -> FeedResult:
    items = deserialize_items(snapshot) or ()
    return FeedResult(
        feed=feed,
        items=items,
        fetched_at=parse_datetime(snapshot.get("last_success_at")),
        is_stale=stale,
        refresh_failed=failed,
        error="" if items else snapshot.get("last_error", ""),
    )


def get_fixed_feed(
    feed: NewsFeed,
    provider: NewsProvider,
    *,
    cache_backend=None,
    fetcher: Callable[..., FeedResponse] = fetch_feed,
    now: datetime | None = None,
    retry_failed: bool = False,
    force_refresh: bool = False,
    fresh_seconds: int | None = None,
) -> FeedResult:
    if not provider.enabled_by_default or not feed.enabled_by_default:
        return FeedResult(feed, (), None, error="Feed is disabled.")
    if feed.provider_id != provider.id or not feed.allowed_hosts:
        return FeedResult(feed, (), None, error="Feed configuration is unavailable.")
    backend = cache_backend or cache
    current_time = now or datetime.now(UTC)
    fresh_seconds = settings.NEWS_REFRESH_SECONDS if fresh_seconds is None else fresh_seconds
    key = _cache_key(feed)
    with cache_lock(key):
        snapshot = backend.get(key)
        if not isinstance(snapshot, dict) or deserialize_items(snapshot) is None:
            snapshot = {}
        retrying_failure = retry_failed and bool(snapshot.get("last_error"))
        success_age = age(current_time, snapshot.get("fetched_at"))
        if (
            not force_refresh and not retrying_failure
            and snapshot.get("last_success_at")
            and success_age is not None
            and success_age.total_seconds() < fresh_seconds
        ):
            return _feed_result(feed, snapshot)
        failure_age = age(current_time, snapshot.get("last_attempt_at"))
        if (
            not force_refresh and not retrying_failure
            and snapshot.get("last_error")
            and failure_age is not None
            and failure_age.total_seconds() < settings.NEWS_FAILURE_BACKOFF_SECONDS
        ):
            return _feed_result(
                feed,
                snapshot,
                stale=bool(snapshot.get("last_success_at")),
                failed=True,
            )

        try:
            response = fetcher(
                feed.feed_url,
                allowed_hosts=set(feed.allowed_hosts),
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
                normalized = normalize_feed(
                    response.body,
                    provider,
                    settings.NEWS_FIXED_FEED_CACHE_ITEMS,
                    feed=feed,
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
                    "parser_warnings": list(normalized.parser_warnings),
                }
            backend.set(key, snapshot, settings.NEWS_REGIONAL_STALE_SECONDS)
            return _feed_result(feed, snapshot)
        except (FeedFetchError, FeedParseError) as error:
            snapshot["last_error"] = "This regional feed is temporarily unavailable."
            snapshot["last_error_detail"] = str(error)[:240]
            snapshot["last_attempt_at"] = current_time.isoformat()
            last_success_age = age(current_time, snapshot.get("last_success_at"))
            if (
                last_success_age is not None
                and last_success_age.total_seconds() < settings.NEWS_REGIONAL_STALE_SECONDS
            ):
                remaining = max(
                    1,
                    settings.NEWS_REGIONAL_STALE_SECONDS - int(last_success_age.total_seconds()),
                )
                backend.set(key, snapshot, remaining)
                return _feed_result(feed, snapshot, stale=True, failed=True)
            empty = {
                "items": [],
                "fetched_at": None,
                "last_success_at": None,
                "etag": None,
                "last_modified": None,
                "last_error": "This regional feed is temporarily unavailable.",
                "last_error_detail": str(error)[:240],
                "last_attempt_at": current_time.isoformat(),
                "parser_warnings": [],
            }
            backend.set(key, empty, settings.NEWS_FAILURE_BACKOFF_SECONDS)
            return _feed_result(feed, empty, failed=True)


def _normalized_identity(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def _metadata_score(item: NewsItem) -> tuple[int, int, int]:
    return (
        int(bool(item.summary)),
        int(item.published_at is not None),
        int(bool(item.publisher) and item.publisher != item.provider_name),
    )


def _same_item(left: NewsItem, right: NewsItem) -> bool:
    if left.link == right.link:
        return True
    same_title = _normalized_identity(left.title) == _normalized_identity(right.title)
    if same_title and left.provider_id == right.provider_id:
        return True
    return bool(
        same_title
        and left.published_at
        and left.published_at == right.published_at
        and _normalized_identity(left.publisher) == _normalized_identity(right.publisher)
    )


def _merge_item(left: NewsItem, right: NewsItem) -> NewsItem:
    preferred = right if _metadata_score(right) > _metadata_score(left) else left
    sections = tuple(dict.fromkeys((*left.contributing_sections, *right.contributing_sections)))
    if left.provider_id != right.provider_id:
        sections = preferred.contributing_sections
    return replace(
        preferred,
        contributing_sections=sections,
        is_stale=left.is_stale and right.is_stale,
    )


def _deduplicate(items: list[NewsItem]) -> list[NewsItem]:
    unique: list[NewsItem] = []
    for item in items:
        duplicate_index = next(
            (index for index, current in enumerate(unique) if _same_item(current, item)),
            None,
        )
        if duplicate_index is None:
            unique.append(item)
        else:
            unique[duplicate_index] = _merge_item(unique[duplicate_index], item)
    return unique


def _ordered_limited(
    items: list[NewsItem],
    country: dict,
    providers: dict[str, NewsProvider],
) -> tuple[NewsItem, ...]:
    ordered = sorted(
        _deduplicate(items),
        key=lambda item: (
            _MATCH_RANK[item.match_class],
            not has_regional_affinity(country, providers[item.provider_id]),
            item.published_at is None,
            -(item.published_at.timestamp()) if item.published_at else 0,
            providers[item.provider_id].display_priority,
            item.source_order,
            item.provider_id,
            item.feed_id,
        ),
    )
    feed_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    output = []
    for item in ordered:
        if feed_counts.get(item.feed_id, 0) >= settings.NEWS_REGIONAL_PER_FEED_LIMIT:
            continue
        if provider_counts.get(item.provider_id, 0) >= settings.NEWS_REGIONAL_PER_PROVIDER_LIMIT:
            continue
        feed_counts[item.feed_id] = feed_counts.get(item.feed_id, 0) + 1
        provider_counts[item.provider_id] = provider_counts.get(item.provider_id, 0) + 1
        output.append(item)
        if len(output) >= settings.NEWS_REGIONAL_TOTAL_LIMIT:
            break
    return tuple(output)


def _failed_feed(feed: NewsFeed) -> FeedResult:
    return FeedResult(
        feed,
        (),
        None,
        refresh_failed=True,
        error="This regional feed is temporarily unavailable.",
    )


def get_regional_news(
    country: dict,
    providers: tuple[NewsProvider, ...],
    feeds: tuple[NewsFeed, ...],
    *,
    cache_backend=None,
    fetcher: Callable[..., FeedResponse] = fetch_feed,
    now: datetime | None = None,
    retry_failed: bool = False,
    fresh_seconds: int | None = None,
) -> tuple[tuple[NewsItem, ...], tuple[RegionalProviderResult, ...], str]:
    provider_map = {
        provider.id: provider
        for provider in providers
        if provider.enabled_by_default
    }
    enabled_feeds = tuple(
        feed
        for feed in feeds
        if feed.enabled_by_default and feed.provider_id in provider_map
    )
    if not enabled_feeds:
        return (), (), ""

    def load(feed: NewsFeed) -> FeedResult:
        try:
            return get_fixed_feed(
                feed,
                provider_map[feed.provider_id],
                cache_backend=cache_backend,
                fetcher=fetcher,
                now=now,
                retry_failed=retry_failed,
                fresh_seconds=fresh_seconds,
            )
        except Exception as error:
            logger.warning("Regional feed %s failed with %s", feed.id, type(error).__name__)
            return _failed_feed(feed)

    executor = ThreadPoolExecutor(max_workers=min(settings.NEWS_REGIONAL_WORKERS, len(enabled_feeds)))
    futures = {executor.submit(load, feed): feed for feed in enabled_feeds}
    done, pending = wait(futures, timeout=settings.NEWS_REGIONAL_FETCH_WAIT_SECONDS)
    result_by_feed = {futures[future].id: future.result() for future in done}
    for future in pending:
        future.cancel()
        feed = futures[future]
        result_by_feed[feed.id] = _failed_feed(feed)
    executor.shutdown(wait=False, cancel_futures=True)
    feed_results = tuple(result_by_feed[feed.id] for feed in enabled_feeds)

    provider_results = []
    matched_items = []
    for provider in sorted(provider_map.values(), key=lambda value: (value.display_priority, value.id)):
        sibling_results = tuple(
            result for result in feed_results if result.feed.provider_id == provider.id
        )
        if not sibling_results:
            continue
        raw_items = _deduplicate([
            replace(item, is_stale=result.is_stale)
            for result in sibling_results
            for item in result.items
        ])
        provider_matches = []
        for item in raw_items:
            evidence = match_country_text(item.title, item.summary)
            country_evidence = tuple(
                match for match in evidence if match.country_code == country["iso_a2"]
            )
            if not country_evidence:
                continue
            match_class = min(
                (match.match_class.value for match in country_evidence),
                key=_MATCH_RANK.__getitem__,
            )
            matched = replace(
                item,
                matched_country_codes=tuple(sorted({match.country_code for match in evidence})),
                match_evidence=tuple(
                    f"{match.match_class.value}:{match.country_code}:{match.alias}"
                    for match in evidence
                ),
                match_class=match_class,
            )
            provider_matches.append(matched)
            matched_items.append(matched)
        failed_count = sum(result.refresh_failed for result in sibling_results)
        usable_count = sum(not result.refresh_failed or bool(result.items) for result in sibling_results)
        if not usable_count:
            status = "unavailable"
        elif failed_count:
            status = "partial"
        else:
            status = "available"
        provider_results.append(RegionalProviderResult(
            provider=provider,
            items=tuple(provider_matches),
            enabled_feed_count=len(sibling_results),
            successful_feed_count=usable_count,
            failed_feed_count=failed_count,
            is_stale=any(result.is_stale for result in sibling_results),
            status=status,
        ))

    ordered_items = _ordered_limited(matched_items, country, provider_map)
    visible_by_provider = {
        provider_id: tuple(item for item in ordered_items if item.provider_id == provider_id)
        for provider_id in provider_map
    }
    provider_results = [
        replace(result, items=visible_by_provider[result.provider.id])
        for result in provider_results
    ]
    affected = sum(result.status != "available" for result in provider_results)
    warning = ""
    if affected:
        noun = "provider has" if affected == 1 else "providers have"
        warning = (
            f"{affected} regional {noun} feed availability issues; "
            "cached results are shown where available."
        )
    return ordered_items, tuple(provider_results), warning
