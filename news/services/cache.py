from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock

from news.types import NewsItem


_CACHE_LOCKS: dict[str, Lock] = {}
_CACHE_LOCKS_GUARD = Lock()


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