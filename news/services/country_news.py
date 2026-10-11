from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache

from countries.data import ALPHA_2_PATTERN, load_country_data
from news.adapters.google_news import build_feed_url
from news.adapters.rss import FeedParseError, normalize_feed
from news.preferences import effective_registry, freshness_seconds
from news.registry import SourceRegistry
from news.types import CountryNewsPage, CountryNewsResult, NewsItem

from .cache import age as _age
from .cache import cache_lock as _cache_lock
from .cache import clear_google_pause, deserialize_items, failure_retry_pending, google_cache_key, google_pause_until, pause_google, record_failure, parse_datetime as _parse_datetime
from .fetch import FeedFetchError, FeedResponse, fetch_feed
from .region_routing import eligible_fixed_feeds
from .regional_news import get_regional_news


GOOGLE_SOURCE_ID = "google_news_country"
class CountryNotFoundError(ValueError):
    pass


def _items_from_snapshot(snapshot: dict) -> tuple[NewsItem, ...]:
    return deserialize_items(snapshot) or ()


@lru_cache(maxsize=1)
def _countries_by_code() -> dict[str, dict]:
    metadata, _geometry = load_country_data()
    return {country["iso_a2"]: country for country in metadata["countries"]}


def _country_for_code(iso2: str) -> dict:
    code = iso2.strip().upper()
    if not ALPHA_2_PATTERN.fullmatch(code) or code not in _countries_by_code():
        raise CountryNotFoundError(f"Unknown country code: {iso2}")
    return _countries_by_code()[code]


def _result(country: dict, source, snapshot: dict, *, is_stale: bool = False) -> CountryNewsResult:
    last_success = _parse_datetime(snapshot.get("last_success_at"))
    error = snapshot.get("last_error") if isinstance(snapshot.get("last_error"), str) else ""
    warnings = snapshot.get("parser_warnings", [])
    return CountryNewsResult(
        country_code=country["iso_a2"],
        country_name=country["name"],
        source=source,
        items=_items_from_snapshot(snapshot),
        fetched_at=last_success,
        is_stale=is_stale,
        warning=("Google News could not be refreshed; showing cached results." if error else "Showing saved headlines while the feed refreshes.") if is_stale else "",
        error="" if last_success else error,
        parser_warnings=tuple(item for item in warnings if isinstance(item, str)),
    )


def get_country_news(iso2: str, **options) -> CountryNewsResult:
    return _get_google_news(_country_for_code(iso2), **options)


def get_world_news(**options) -> CountryNewsResult:
    return _get_google_news({"iso_a2": "WORLD", "name": "World"}, **options)


def _get_google_news(
    country: dict,
    *,
    cache_backend=None,
    registry: SourceRegistry | None = None,
    fetcher: Callable[..., FeedResponse] = fetch_feed,
    now: datetime | None = None,
    retry_failed: bool = False,
    force_refresh: bool = False,
    fresh_seconds: int | None = None,
    cache_only: bool = False,
) -> CountryNewsResult:
    source = (registry or effective_registry()).get(GOOGLE_SOURCE_ID)
    if not source.enabled_by_default or not source.feed_host:
        return CountryNewsResult(
            country["iso_a2"], country["name"], source, (), None,
            error="Google News is not enabled.",
        )
    current_time = now or datetime.now(UTC)
    cache_key = google_cache_key(source, country["iso_a2"])
    if fresh_seconds is None:
        fresh_seconds = freshness_seconds() if registry is None else settings.NEWS_REFRESH_SECONDS
    backend = cache_backend or cache

    if cache_only:
        snapshot = backend.get(cache_key)
        if not isinstance(snapshot, dict) or deserialize_items(snapshot) is None:
            snapshot = {}
        success_age = _age(current_time, snapshot.get("fetched_at"))
        return _result(country, source, snapshot, is_stale=bool(
            snapshot.get("last_success_at") and (
                snapshot.get("last_error") or success_age is None or success_age.total_seconds() >= fresh_seconds
            )
        ))

    with _cache_lock(cache_key):
        snapshot = backend.get(cache_key)
        if not isinstance(snapshot, dict):
            snapshot = {}
        if google_pause_until(backend, current_time):
            paused = {**snapshot, "last_error": "Google News refresh is paused after a rate-limit response; it will resume automatically."}
            return _result(country, source, paused, is_stale=bool(snapshot.get("last_success_at")))
        retrying_failure = retry_failed and bool(snapshot.get("last_error"))
        success_age = _age(current_time, snapshot.get("fetched_at"))
        if not force_refresh and not retrying_failure and not snapshot.get("last_error") and snapshot.get("last_success_at") and success_age is not None and success_age.total_seconds() < fresh_seconds:
            return _result(country, source, snapshot)
        if not force_refresh and not retrying_failure and failure_retry_pending(snapshot, current_time):
            return _result(country, source, snapshot, is_stale=bool(snapshot.get("last_success_at")))

        try:
            response = fetcher(
                build_feed_url(source, country),
                allowed_hosts={source.feed_host},
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
                    "consecutive_failures": 0,
                    "retry_after_at": None,
                })
            else:
                limit = settings.NEWS_WORLD_MAX_ITEMS if country["iso_a2"] == "WORLD" else settings.NEWS_MAX_ITEMS
                normalized = normalize_feed(response.body, source, limit)
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
            clear_google_pause(backend, current_time)
            backend.set(cache_key, snapshot, settings.NEWS_STALE_SECONDS)
            return _result(country, source, snapshot)
        except (FeedFetchError, FeedParseError) as error:
            if getattr(error, "status_code", None) == 429:
                pause_google(backend, current_time, error)
            failure_ttl = record_failure(snapshot, current_time, error)
            snapshot["last_error"] = "Google News is temporarily unavailable."
            snapshot["last_error_detail"] = str(error)[:240]
            snapshot["last_attempt_at"] = current_time.isoformat()
            last_success_age = _age(current_time, snapshot.get("last_success_at"))
            if last_success_age is not None and last_success_age.total_seconds() < settings.NEWS_STALE_SECONDS:
                remaining = max(1, settings.NEWS_STALE_SECONDS - int(last_success_age.total_seconds()))
                backend.set(cache_key, snapshot, max(remaining, failure_ttl))
                return _result(country, source, snapshot, is_stale=True)
            empty_snapshot = {
                "items": [],
                "fetched_at": None,
                "last_success_at": None,
                "etag": None,
                "last_modified": None,
                "last_error": "Google News is temporarily unavailable.",
                "last_error_detail": str(error)[:240],
                "last_attempt_at": current_time.isoformat(),
                "parser_warnings": [],
                "consecutive_failures": snapshot["consecutive_failures"],
                "retry_after_at": snapshot["retry_after_at"],
            }
            backend.set(cache_key, empty_snapshot, failure_ttl)
            return _result(country, source, empty_snapshot)


def get_country_news_page(
    iso2: str,
    *,
    cache_backend=None,
    registry: SourceRegistry | None = None,
    fetcher: Callable[..., FeedResponse] = fetch_feed,
    now: datetime | None = None,
    retry_failed: bool = False,
    cache_only: bool = False,
    fresh_seconds: int | None = None,
) -> CountryNewsPage:
    country = _country_for_code(iso2)
    source_registry = registry or effective_registry()
    if fresh_seconds is None:
        fresh_seconds = freshness_seconds() if registry is None else settings.NEWS_REFRESH_SECONDS
    google = get_country_news(
        iso2,
        cache_backend=cache_backend,
        registry=source_registry,
        fetcher=fetcher,
        now=now,
        retry_failed=retry_failed,
        fresh_seconds=fresh_seconds,
        cache_only=cache_only,
    )
    fixed_feeds = eligible_fixed_feeds(country, source_registry)
    regional_items, regional_sources, regional_warning = get_regional_news(
        country,
        tuple(provider for provider in source_registry.providers if provider.enabled_by_default),
        fixed_feeds,
        cache_backend=cache_backend,
        fetcher=fetcher,
        now=now,
        retry_failed=retry_failed,
        fresh_seconds=fresh_seconds,
        cache_only=cache_only,
    )
    return CountryNewsPage(
        country_code=country["iso_a2"],
        country_name=country["name"],
        google=google,
        regional_items=regional_items,
        regional_sources=regional_sources,
        regional_warning=regional_warning,
    )
