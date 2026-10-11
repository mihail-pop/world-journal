from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock

from django.conf import settings
from news.types import NewsItem, NewsSource, VideoItem


_CACHE_LOCKS: dict[str, Lock] = {}
_CACHE_LOCKS_GUARD = Lock()


def google_cache_key(source: NewsSource, country_code: str) -> str:
    edition = source.edition_parameters["ceid"].replace(":", "-")
    return f"news:v{settings.NEWS_CACHE_SCHEMA_VERSION}:google_country:{country_code}:{edition}"


def fixed_feed_cache_key(feed) -> str:
    return f"news:v{settings.NEWS_CACHE_SCHEMA_VERSION}:rss:{feed.id}:{feed.language}"


def youtube_cache_key(source: NewsSource) -> str:
    return f"news:v{settings.NEWS_CACHE_SCHEMA_VERSION}:youtube:{source.id}:{source.language}"


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
        ))
    return tuple(items)
