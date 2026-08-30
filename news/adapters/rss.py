from __future__ import annotations

import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urldefrag, urlsplit, urlunsplit

import feedparser

from news.types import NewsItem, NewsSource, NormalizedFeed


class FeedParseError(ValueError):
    pass


class _PlainTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: object) -> str:
    parser = _PlainTextParser()
    parser.feed(value if isinstance(value, str) else "")
    return " ".join("".join(parser.parts).split())


def _safe_link(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    without_fragment, _fragment = urldefrag(value.strip())
    parsed = urlsplit(without_fragment)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def _published_at(entry: dict) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _publisher(entry: dict, source: NewsSource) -> str:
    item_source = entry.get("source")
    if isinstance(item_source, dict):
        publisher = _plain_text(item_source.get("title"))
        if publisher:
            return publisher
    return source.display_name


def _deduplicate(items: list[NewsItem]) -> tuple[NewsItem, ...]:
    links: set[str] = set()
    identities: set[tuple[str, str]] = set()
    unique_items = []
    for item in items:
        identity = (
            re.sub(r"\s+", " ", item.title).strip().casefold(),
            re.sub(r"\s+", " ", item.publisher).strip().casefold(),
        )
        if item.link in links or identity in identities:
            continue
        links.add(item.link)
        identities.add(identity)
        unique_items.append(item)
    return tuple(unique_items)


def normalize_feed(payload: bytes, source: NewsSource, max_items: int) -> NormalizedFeed:
    parsed = feedparser.parse(payload)
    warnings = ()
    if parsed.bozo:
        warnings = (str(parsed.bozo_exception)[:240],)
    if parsed.bozo and not parsed.entries:
        raise FeedParseError("The feed could not be parsed")

    items = []
    for entry in parsed.entries:
        title = _plain_text(entry.get("title"))
        link = _safe_link(entry.get("link"))
        if not title or not link:
            continue
        publisher = _publisher(entry, source)
        summary = _plain_text(entry.get("summary") or entry.get("description"))
        if summary.casefold() in {title.casefold(), f"{title} {publisher}".casefold()}:
            summary = ""
        items.append(
            NewsItem(
                title=title,
                link=link,
                publisher=publisher,
                published_at=_published_at(entry),
                summary=summary,
            )
        )
        if len(items) >= max_items * 2:
            break
    return NormalizedFeed(items=_deduplicate(items)[:max_items], parser_warnings=warnings)