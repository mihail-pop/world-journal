from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings

from .types import NewsSource, SourceKind


SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
YOUTUBE_CHANNEL_PATTERN = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
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
    SourceKind.FIXED_RSS: {"feed_url", "coverage_regions"},
    SourceKind.YOUTUBE: {"youtube_channel_id", "coverage_regions"},
}


class SourceConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SourceRegistry:
    sources: tuple[NewsSource, ...]

    def get(self, source_id: str) -> NewsSource:
        for source in self.sources:
            if source.id == source_id:
                return source
        raise SourceConfigurationError(f"Unknown news source: {source_id}")


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
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise SourceConfigurationError(f"Source {source_id} has invalid coverage_regions")
    return tuple(value)


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
        options["feed_host"] = urlsplit(options["feed_url"]).hostname
        options["coverage_regions"] = _regions(value["coverage_regions"], source_id)
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
    if not isinstance(value, dict) or set(value) != {"schema_version", "sources"} or value["schema_version"] != 1:
        raise SourceConfigurationError("News sources have an unsupported or missing schema")
    if not isinstance(value["sources"], list):
        raise SourceConfigurationError("News sources must be a list")
    sources = tuple(_parse_source(source, index) for index, source in enumerate(value["sources"]))
    source_ids = [source.id for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise SourceConfigurationError("News source ids must be unique")
    channel_ids = [source.youtube_channel_id for source in sources if source.youtube_channel_id]
    if len(channel_ids) != len(set(channel_ids)):
        raise SourceConfigurationError("YouTube channel ids must be unique")
    return SourceRegistry(sources)


@lru_cache(maxsize=1)
def get_source_registry() -> SourceRegistry:
    return load_source_registry()