from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings

from .types import FeedType, NewsFeed, NewsProvider, NewsSource, SourceKind


SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
YOUTUBE_CHANNEL_PATTERN = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
HOST_PATTERN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")
ROUTING_REGIONS = {
    "middle_east",
    "asia_pacific",
    "europe",
    "africa",
    "north_america",
    "latin_america_caribbean",
}
COMMON_FIELDS = {
    "id",
    "kind",
    "display_name",
    "homepage_url",
    "language",
    "enabled_by_default",
}
KIND_FIELDS = {
    SourceKind.DYNAMIC_COUNTRY_RSS: {"feed_host", "edition"},
    SourceKind.FIXED_RSS: {
        "feed_url",
        "publisher_country_code",
        "editorial_region",
        "coverage_regions",
        "allowed_hosts",
        "verification_date",
        "disabled_reason",
        "operational_notes",
        "display_priority",
    },
    SourceKind.YOUTUBE: {"youtube_channel_id", "coverage_regions"},
}
PROVIDER_FIELDS = {
    "id",
    "display_name",
    "homepage_url",
    "language",
    "publisher_country_code",
    "editorial_region",
    "coverage_regions",
    "display_priority",
    "enabled_by_default",
}
FEED_FIELDS = {
    "id",
    "provider_id",
    "section_label",
    "feed_url",
    "source_type",
    "language",
    "enabled_by_default",
    "allowed_hosts",
    "verification_date",
    "disabled_reason",
    "operational_notes",
}


class SourceConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SourceRegistry:
    sources: tuple[NewsSource, ...]
    providers: tuple[NewsProvider, ...] = ()
    feeds: tuple[NewsFeed, ...] = ()

    def get(self, source_id: str) -> NewsSource:
        for source in self.sources:
            if source.id == source_id:
                return source
        raise SourceConfigurationError(f"Unknown news source: {source_id}")

    def get_provider(self, provider_id: str) -> NewsProvider:
        for provider in self.providers:
            if provider.id == provider_id:
                return provider
        raise SourceConfigurationError(f"Unknown news provider: {provider_id}")

    def get_feed(self, feed_id: str) -> NewsFeed:
        for feed in self.feeds:
            if feed.id == feed_id:
                return feed
        raise SourceConfigurationError(f"Unknown news feed: {feed_id}")


def _https_url(value: object, field: str, source_id: str) -> str:
    if not isinstance(value, str):
        raise SourceConfigurationError(f"Source {source_id} has invalid {field}")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SourceConfigurationError(f"Source {source_id} {field} must be an HTTPS URL")
    return value


def _text(value: object, field: str, source_id: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceConfigurationError(f"Source {source_id} has invalid {field}")
    return value.strip()


def _regions(value: object, source_id: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item in ROUTING_REGIONS for item in value)
        or len(value) != len(set(value))
    ):
        raise SourceConfigurationError(f"Source {source_id} has invalid coverage_regions")
    return tuple(value)


def _allowed_hosts(value: object, feed_host: str, source_id: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise SourceConfigurationError(f"Source {source_id} has invalid allowed_hosts")
    hosts = tuple(item.lower() for item in value if isinstance(item, str))
    if len(hosts) != len(value) or len(hosts) != len(set(hosts)) or any(not HOST_PATTERN.fullmatch(host) for host in hosts):
        raise SourceConfigurationError(f"Source {source_id} has invalid allowed_hosts")
    if feed_host not in hosts:
        raise SourceConfigurationError(f"Source {source_id} allowed_hosts must include its feed host")
    return hosts


def _verification_date(value: object, source_id: str) -> date:
    if not isinstance(value, str):
        raise SourceConfigurationError(f"Source {source_id} has invalid verification_date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise SourceConfigurationError(f"Source {source_id} has invalid verification_date") from error


def _enabled(value: object, owner_id: str) -> bool:
    if not isinstance(value, bool):
        raise SourceConfigurationError(f"{owner_id} has invalid enabled_by_default")
    return value


def _priority(value: object, owner_id: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SourceConfigurationError(f"{owner_id} has invalid display_priority")
    return value


def _publisher_country_code(value: object, owner_id: str) -> str | None:
    if value is not None and (
        not isinstance(value, str)
        or not COUNTRY_CODE_PATTERN.fullmatch(value)
    ):
        raise SourceConfigurationError(f"{owner_id} has invalid publisher_country_code")
    return value


def _editorial_region(value: object, owner_id: str) -> str:
    if not isinstance(value, str) or value not in ROUTING_REGIONS:
        raise SourceConfigurationError(f"{owner_id} has invalid editorial_region")
    return value


def _parse_provider(value: object, index: int) -> NewsProvider:
    if not isinstance(value, dict) or set(value) != PROVIDER_FIELDS:
        raise SourceConfigurationError(f"News provider {index} has invalid fields")
    provider_id = value.get("id")
    if not isinstance(provider_id, str) or not SOURCE_ID_PATTERN.fullmatch(provider_id):
        raise SourceConfigurationError(f"News provider {index} has an invalid id")
    return NewsProvider(
        id=provider_id,
        display_name=_text(value["display_name"], "display_name", provider_id),
        homepage_url=_https_url(value["homepage_url"], "homepage_url", provider_id),
        language=_text(value["language"], "language", provider_id),
        publisher_country_code=_publisher_country_code(value["publisher_country_code"], provider_id),
        editorial_region=_editorial_region(value["editorial_region"], provider_id),
        coverage_regions=_regions(value["coverage_regions"], provider_id),
        display_priority=_priority(value["display_priority"], provider_id),
        enabled_by_default=_enabled(value["enabled_by_default"], provider_id),
    )


def _parse_feed(value: object, index: int) -> NewsFeed:
    if not isinstance(value, dict) or set(value) != FEED_FIELDS:
        raise SourceConfigurationError(f"News feed {index} has invalid fields")
    feed_id = value.get("id")
    if not isinstance(feed_id, str) or not SOURCE_ID_PATTERN.fullmatch(feed_id):
        raise SourceConfigurationError(f"News feed {index} has an invalid id")
    provider_id = value.get("provider_id")
    if not isinstance(provider_id, str) or not SOURCE_ID_PATTERN.fullmatch(provider_id):
        raise SourceConfigurationError(f"Feed {feed_id} has an invalid provider_id")
    try:
        source_type = FeedType(value.get("source_type"))
    except ValueError as error:
        raise SourceConfigurationError(f"Feed {feed_id} has an invalid source_type") from error
    feed_url = _https_url(value["feed_url"], "feed_url", feed_id)
    feed_host = urlsplit(feed_url).hostname
    enabled = _enabled(value["enabled_by_default"], feed_id)
    disabled_reason = value["disabled_reason"]
    if not isinstance(disabled_reason, str):
        raise SourceConfigurationError(f"Feed {feed_id} has invalid disabled_reason")
    if enabled and disabled_reason:
        raise SourceConfigurationError(f"Enabled feed {feed_id} cannot have a disabled_reason")
    if not enabled and not disabled_reason.strip():
        raise SourceConfigurationError(f"Disabled feed {feed_id} requires a disabled_reason")
    operational_notes = _text(value["operational_notes"], "operational_notes", feed_id)
    return NewsFeed(
        id=feed_id,
        provider_id=provider_id,
        section_label=_text(value["section_label"], "section_label", feed_id),
        feed_url=feed_url,
        source_type=source_type,
        language=_text(value["language"], "language", feed_id),
        enabled_by_default=enabled,
        allowed_hosts=_allowed_hosts(value["allowed_hosts"], feed_host, feed_id),
        verification_date=_verification_date(value["verification_date"], feed_id),
        disabled_reason=disabled_reason.strip(),
        operational_notes=operational_notes,
    )


def _parse_source(value: object, index: int) -> NewsSource:
    if not isinstance(value, dict):
        raise SourceConfigurationError(f"News source {index} must be an object")
    source_id = value.get("id")
    if not isinstance(source_id, str) or not SOURCE_ID_PATTERN.fullmatch(source_id):
        raise SourceConfigurationError(f"News source {index} has an invalid id")
    try:
        kind = SourceKind(value.get("kind"))
    except ValueError as error:
        raise SourceConfigurationError(f"Source {source_id} has an invalid kind") from error
    expected_fields = COMMON_FIELDS | KIND_FIELDS[kind]
    if set(value) != expected_fields:
        raise SourceConfigurationError(f"Source {source_id} has invalid fields")
    enabled = value["enabled_by_default"]
    if not isinstance(enabled, bool):
        raise SourceConfigurationError(f"Source {source_id} has invalid enabled_by_default")

    options: dict[str, object] = {}
    if kind is SourceKind.DYNAMIC_COUNTRY_RSS:
        feed_host = _text(value["feed_host"], "feed_host", source_id).lower()
        if ":" in feed_host or "/" in feed_host:
            raise SourceConfigurationError(f"Source {source_id} has invalid feed_host")
        edition = value["edition"]
        if not isinstance(edition, dict) or set(edition) != {"hl", "gl", "ceid"}:
            raise SourceConfigurationError(f"Source {source_id} has invalid edition")
        options["feed_host"] = feed_host
        options["edition"] = tuple(
            (key, _text(edition[key], f"edition.{key}", source_id))
            for key in ("hl", "gl", "ceid")
        )
    elif kind is SourceKind.FIXED_RSS:
        options["feed_url"] = _https_url(value["feed_url"], "feed_url", source_id)
        feed_host = urlsplit(options["feed_url"]).hostname
        options["feed_host"] = feed_host
        options["coverage_regions"] = _regions(value["coverage_regions"], source_id)
        options["allowed_hosts"] = _allowed_hosts(value["allowed_hosts"], feed_host, source_id)
        publisher_country_code = value["publisher_country_code"]
        if publisher_country_code is not None and (
            not isinstance(publisher_country_code, str)
            or not COUNTRY_CODE_PATTERN.fullmatch(publisher_country_code)
        ):
            raise SourceConfigurationError(f"Source {source_id} has invalid publisher_country_code")
        editorial_region = value["editorial_region"]
        if not isinstance(editorial_region, str) or editorial_region not in ROUTING_REGIONS:
            raise SourceConfigurationError(f"Source {source_id} has invalid editorial_region")
        disabled_reason = value["disabled_reason"]
        if not isinstance(disabled_reason, str):
            raise SourceConfigurationError(f"Source {source_id} has invalid disabled_reason")
        if enabled and disabled_reason:
            raise SourceConfigurationError(f"Enabled source {source_id} cannot have a disabled_reason")
        if not enabled and not disabled_reason.strip():
            raise SourceConfigurationError(f"Disabled source {source_id} requires a disabled_reason")
        operational_notes = value["operational_notes"]
        if not isinstance(operational_notes, str):
            raise SourceConfigurationError(f"Source {source_id} has invalid operational_notes")
        display_priority = value["display_priority"]
        if not isinstance(display_priority, int) or isinstance(display_priority, bool) or display_priority < 0:
            raise SourceConfigurationError(f"Source {source_id} has invalid display_priority")
        options.update({
            "publisher_country_code": publisher_country_code,
            "editorial_region": editorial_region,
            "verification_date": _verification_date(value["verification_date"], source_id),
            "disabled_reason": disabled_reason.strip(),
            "operational_notes": operational_notes.strip(),
            "display_priority": display_priority,
        })
    else:
        channel_id = _text(value["youtube_channel_id"], "youtube_channel_id", source_id)
        if not YOUTUBE_CHANNEL_PATTERN.fullmatch(channel_id):
            raise SourceConfigurationError(f"Source {source_id} has invalid youtube_channel_id")
        options["youtube_channel_id"] = channel_id
        options["coverage_regions"] = _regions(value["coverage_regions"], source_id)

    return NewsSource(
        id=source_id,
        kind=kind,
        display_name=_text(value["display_name"], "display_name", source_id),
        homepage_url=_https_url(value["homepage_url"], "homepage_url", source_id),
        language=_text(value["language"], "language", source_id),
        enabled_by_default=enabled,
        **options,
    )


def load_source_registry(path: Path | None = None) -> SourceRegistry:
    path = path or settings.NEWS_SOURCE_CONFIG_PATH
    try:
        with path.open(encoding="utf-8") as source_file:
            value = json.load(source_file)
    except (OSError, json.JSONDecodeError) as error:
        raise SourceConfigurationError(f"Could not read valid news sources from {path}: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 3:
        raise SourceConfigurationError("News sources have an unsupported or missing schema")
    if set(value) != {"schema_version", "sources", "providers", "feeds"}:
        raise SourceConfigurationError("News sources have invalid top-level fields")
    if not all(isinstance(value[field], list) for field in ("sources", "providers", "feeds")):
        raise SourceConfigurationError("News sources, providers, and feeds must be lists")
    sources = tuple(_parse_source(source, index) for index, source in enumerate(value["sources"]))
    if any(source.kind is not SourceKind.DYNAMIC_COUNTRY_RSS for source in sources):
        raise SourceConfigurationError("Schema 3 sources must contain only dynamic providers")
    providers = tuple(_parse_provider(provider, index) for index, provider in enumerate(value["providers"]))
    feeds = tuple(_parse_feed(feed, index) for index, feed in enumerate(value["feeds"]))
    all_ids = [source.id for source in sources] + [provider.id for provider in providers] + [feed.id for feed in feeds]
    if len(all_ids) != len(set(all_ids)):
        raise SourceConfigurationError("News source, provider, and feed ids must be globally unique")
    provider_ids = {provider.id for provider in providers}
    orphan_ids = sorted({feed.provider_id for feed in feeds} - provider_ids)
    if orphan_ids:
        raise SourceConfigurationError(f"News feeds reference unknown providers: {', '.join(orphan_ids)}")
    feed_urls = [feed.feed_url for feed in feeds]
    if len(feed_urls) != len(set(feed_urls)):
        raise SourceConfigurationError("News feed URLs must be unique")
    enabled_providers = {provider.id for provider in providers if provider.enabled_by_default}
    if any(feed.enabled_by_default and feed.provider_id not in enabled_providers for feed in feeds):
        raise SourceConfigurationError("Enabled feeds require an enabled provider")
    providers_with_feeds = {feed.provider_id for feed in feeds}
    if providers_with_feeds != provider_ids:
        raise SourceConfigurationError("Every news provider must own at least one feed")
    providers_with_enabled_feeds = {feed.provider_id for feed in feeds if feed.enabled_by_default}
    if not enabled_providers.issubset(providers_with_enabled_feeds):
        raise SourceConfigurationError("Every enabled provider must own an enabled feed")
    return SourceRegistry(sources=sources, providers=providers, feeds=feeds)


@lru_cache(maxsize=1)
def get_source_registry() -> SourceRegistry:
    return load_source_registry()