from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class SourceKind(StrEnum):
    DYNAMIC_COUNTRY_RSS = "dynamic_country_rss"
    FIXED_RSS = "fixed_rss"
    YOUTUBE = "youtube"


@dataclass(frozen=True, slots=True)
class NewsSource:
    id: str
    kind: SourceKind
    display_name: str
    homepage_url: str
    language: str
    enabled_by_default: bool
    feed_host: str | None = None
    feed_url: str | None = None
    youtube_channel_id: str | None = None
    coverage_regions: tuple[str, ...] = ()
    edition: tuple[tuple[str, str], ...] = ()

    @property
    def edition_parameters(self) -> dict[str, str]:
        return dict(self.edition)


@dataclass(frozen=True, slots=True)
class NewsItem:
    title: str
    link: str
    publisher: str
    published_at: datetime | None
    summary: str = ""

    def as_cache_value(self) -> dict[str, str | None]:
        return {
            "title": self.title,
            "link": self.link,
            "publisher": self.publisher,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class NormalizedFeed:
    items: tuple[NewsItem, ...]
    parser_warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CountryNewsResult:
    country_code: str
    country_name: str
    source: NewsSource
    items: tuple[NewsItem, ...]
    fetched_at: datetime | None
    is_stale: bool = False
    warning: str = ""
    error: str = ""
    parser_warnings: tuple[str, ...] = field(default_factory=tuple)