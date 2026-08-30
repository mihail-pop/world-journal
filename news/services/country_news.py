from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from threading import Lock

from django.conf import settings
from django.core.cache import cache

from countries.data import ALPHA_2_PATTERN, load_country_data
from news.adapters.google_news import build_feed_url
from news.adapters.rss import FeedParseError, normalize_feed
from news.registry import SourceRegistry, get_source_registry
from news.types import CountryNewsResult, NewsItem

from .fetch import FeedFetchError, FeedResponse, fetch_feed


GOOGLE_SOURCE_ID = "google_news_country"
_CACHE_LOCKS: dict[str, Lock] = {}
_CACHE_LOCKS_GUARD = Lock()


class CountryNotFoundError(ValueError):
    pass


def _cache_lock(key: str) -> Lock:
    with _CACHE_LOCKS_GUARD:
        return _CACHE_LOCKS.setdefault(key, Lock())


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _items_from_snapshot(snapshot: dict) -> tuple[NewsItem, ...]:
    items = []
    for value in snapshot.get("items", []):
        if not isinstance(value, dict):
            continue
        title = value.get("title")
        link = value.get("link")
        publisher = value.get("publisher")
        summary = value.get("summary", "")
        if not all(isinstance(field, str) for field in (title, link, publisher, summary)):
            continue
        items.append(NewsItem(title, link, publisher, _parse_datetime(value.get("published_at")), summary))
    return tuple(items)


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
        warning="Google News could not be refreshed; showing cached results." if is_stale else "",
        error="" if last_success else error,
        parser_warnings=tuple(item for item in warnings if isinstance(item, str)),
    )


def _age(now: datetime, value: object) -> timedelta | None:
    parsed = _parse_datetime(value)
    return now - parsed if parsed else None


def get_country_news(
    iso2: str,
    *,
    cache_backend=None,
    registry: SourceRegistry | None = None,
    fetcher: Callable[..., FeedResponse] = fetch_feed,
    now: datetime | None = None,
) -> CountryNewsResult:
    country = _country_for_code(iso2)
    source = (registry or get_source_registry()).get(GOOGLE_SOURCE_ID)
    if not source.enabled_by_default or not source.feed_host:
        return CountryNewsResult(
            country["iso_a2"], country["name"], source, (), None,
            error="Google News is not enabled.",
        )
    current_time = now or datetime.now(UTC)
    edition = source.edition_parameters["ceid"].replace(":", "-")
    cache_key = f"news:v{settings.NEWS_CACHE_SCHEMA_VERSION}:google_country:{country['iso_a2']}:{edition}"
    backend = cache_backend or cache

    with _cache_lock(cache_key):
        snapshot = backend.get(cache_key)
        if not isinstance(snapshot, dict):
            snapshot = {}
        success_age = _age(current_time, snapshot.get("fetched_at"))
        if snapshot.get("last_success_at") and success_age is not None and success_age.total_seconds() < settings.NEWS_REFRESH_SECONDS:
            return _result(country, source, snapshot)
        failure_age = _age(current_time, snapshot.get("last_attempt_at"))
        if snapshot.get("last_error") and failure_age is not None and failure_age.total_seconds() < settings.NEWS_FAILURE_BACKOFF_SECONDS:
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
                    "last_attempt_at": current_time.isoformat(),
                })
            else:
                normalized = normalize_feed(response.body, source, settings.NEWS_MAX_ITEMS)
                snapshot = {
                    "items": [item.as_cache_value() for item in normalized.items],
                    "fetched_at": current_time.isoformat(),
                    "last_success_at": current_time.isoformat(),
                    "etag": response.etag,
                    "last_modified": response.last_modified,
                    "last_error": "",
                    "last_attempt_at": current_time.isoformat(),
                    "parser_warnings": list(normalized.parser_warnings),
                }
            backend.set(cache_key, snapshot, settings.NEWS_STALE_SECONDS)
            return _result(country, source, snapshot)
        except (FeedFetchError, FeedParseError) as error:
            snapshot["last_error"] = "Google News is temporarily unavailable."
            snapshot["last_attempt_at"] = current_time.isoformat()
            last_success_age = _age(current_time, snapshot.get("last_success_at"))
            if last_success_age is not None and last_success_age.total_seconds() < settings.NEWS_STALE_SECONDS:
                remaining = max(1, settings.NEWS_STALE_SECONDS - int(last_success_age.total_seconds()))
                backend.set(cache_key, snapshot, remaining)
                return _result(country, source, snapshot, is_stale=True)
            empty_snapshot = {
                "items": [],
                "fetched_at": None,
                "last_success_at": None,
                "etag": None,
                "last_modified": None,
                "last_error": "Google News is temporarily unavailable.",
                "last_attempt_at": current_time.isoformat(),
                "parser_warnings": [],
            }
            backend.set(cache_key, empty_snapshot, settings.NEWS_FAILURE_BACKOFF_SECONDS)
            return _result(country, source, empty_snapshot)