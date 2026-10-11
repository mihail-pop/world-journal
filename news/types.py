from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class SourceKind(StrEnum):
    DYNAMIC_COUNTRY_RSS = "dynamic_country_rss"
    FIXED_RSS = "fixed_rss"
    YOUTUBE = "youtube"


class FeedType(StrEnum):
    RSS = "rss"


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
    publisher_country_code: str | None = None
    editorial_region: str | None = None
    allowed_hosts: tuple[str, ...] = ()
    verification_date: date | None = None
    disabled_reason: str = ""
    operational_notes: str = ""
    display_priority: int = 0

    @property
    def edition_parameters(self) -> dict[str, str]:
        return dict(self.edition)

    @property
    def youtube_feed_url(self) -> str | None:
        if self.kind is not SourceKind.YOUTUBE or not self.youtube_channel_id:
            return None
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={self.youtube_channel_id}"


@dataclass(frozen=True, slots=True)
class NewsProvider:
    id: str
    display_name: str
    homepage_url: str
    language: str
    publisher_country_code: str | None
    editorial_region: str
    coverage_regions: tuple[str, ...]
    display_priority: int
    enabled_by_default: bool


@dataclass(frozen=True, slots=True)
class NewsFeed:
    id: str
    provider_id: str
    section_label: str
    feed_url: str
    source_type: FeedType
    language: str
    enabled_by_default: bool
    allowed_hosts: tuple[str, ...]
    verification_date: date
    disabled_reason: str = ""
    operational_notes: str = ""
    allow_public_redirects: bool = False

    @property
    def feed_host(self) -> str:
        from urllib.parse import urlsplit

        return urlsplit(self.feed_url).hostname or ""


@dataclass(frozen=True, slots=True)
class NewsItem:
    title: str
    link: str
    publisher: str
    published_at: datetime | None
    summary: str = ""
    provider_id: str = ""
    provider_name: str = ""
    feed_id: str = ""
    feed_section: str = ""
    contributing_sections: tuple[str, ...] = ()
    source_order: int = 0
    matched_country_codes: tuple[str, ...] = ()
    match_evidence: tuple[str, ...] = ()
    match_class: str = ""
    is_stale: bool = False

    def as_cache_value(self) -> dict[str, str | None]:
        return {
            "title": self.title,
            "link": self.link,
            "publisher": self.publisher,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "summary": self.summary,
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "feed_id": self.feed_id,
            "feed_section": self.feed_section,
            "contributing_sections": list(self.contributing_sections),
            "source_order": self.source_order,
        }


@dataclass(frozen=True, slots=True)
class VideoItem:
    source_id: str
    channel_name: str
    video_id: str
    title: str
    published_at: datetime | None
    watch_url: str
    embed_url: str
    thumbnail_url: str
    source_order: int = 0
    matched_country_codes: tuple[str, ...] = ()
    match_evidence: tuple[str, ...] = ()
    is_stale: bool = False

    def as_cache_value(self) -> dict[str, str | int | None]:
        return {
            "source_id": self.source_id,
            "channel_name": self.channel_name,
            "video_id": self.video_id,
            "title": self.title,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "watch_url": self.watch_url,
            "embed_url": self.embed_url,
            "thumbnail_url": self.thumbnail_url,
            "source_order": self.source_order,
        }


@dataclass(frozen=True, slots=True)
class NormalizedFeed:
    items: tuple[NewsItem, ...]
    parser_warnings: tuple[str, ...] = ()
    feed_format: str = ""
    title: str = ""


@dataclass(frozen=True, slots=True)
class NormalizedVideoFeed:
    items: tuple[VideoItem, ...]


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


@dataclass(frozen=True, slots=True)
class FeedResult:
    feed: NewsFeed
    items: tuple[NewsItem, ...]
    fetched_at: datetime | None
    is_stale: bool = False
    refresh_failed: bool = False
    error: str = ""


@dataclass(frozen=True, slots=True)
class RegionalProviderResult:
    provider: NewsProvider
    items: tuple[NewsItem, ...]
    enabled_feed_count: int
    successful_feed_count: int
    failed_feed_count: int
    is_stale: bool = False
    status: str = "available"


@dataclass(frozen=True, slots=True)
class VideoSourceResult:
    source: NewsSource
    items: tuple[VideoItem, ...]
    fetched_at: datetime | None
    is_stale: bool = False
    refresh_failed: bool = False
    error: str = ""
    status: str = "available"


@dataclass(frozen=True, slots=True)
class CountryVideosPage:
    country_code: str
    country_name: str
    items: tuple[VideoItem, ...]
    sources: tuple[VideoSourceResult, ...]
    status: str
    warning: str = ""


@dataclass(frozen=True, slots=True)
class CountryNewsPage:
    country_code: str
    country_name: str
    google: CountryNewsResult
    regional_items: tuple[NewsItem, ...]
    regional_sources: tuple[RegionalProviderResult, ...]
    regional_warning: str = ""
