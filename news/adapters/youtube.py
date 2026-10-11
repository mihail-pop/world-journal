from __future__ import annotations

import re
from datetime import UTC, datetime
from xml.etree import ElementTree

from news.adapters.rss import _plain_text
from news.types import NewsSource, NormalizedVideoFeed, SourceKind, VideoItem


ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"
YOUTUBE_NAMESPACE = "http://www.youtube.com/xml/schemas/2015"
MEDIA_NAMESPACE = "http://search.yahoo.com/mrss/"
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeFeedParseError(ValueError):
    pass


def is_valid_video_id(value: object) -> bool:
    return isinstance(value, str) and VIDEO_ID_PATTERN.fullmatch(value) is not None


def build_watch_url(video_id: str) -> str:
    if not is_valid_video_id(video_id):
        raise ValueError("Invalid YouTube video ID")
    return f"https://www.youtube.com/watch?v={video_id}"


def build_embed_url(video_id: str) -> str:
    if not is_valid_video_id(video_id):
        raise ValueError("Invalid YouTube video ID")
    return f"https://www.youtube-nocookie.com/embed/{video_id}"


def build_thumbnail_url(video_id: str) -> str:
    if not is_valid_video_id(video_id):
        raise ValueError("Invalid YouTube video ID")
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"


def _channel_matches(value: str | None, trusted_channel_id: str) -> bool:
    return value in {trusted_channel_id, trusted_channel_id[2:]}


def _published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _view_count(entry) -> int | None:
    statistics = entry.find(f".//{{{MEDIA_NAMESPACE}}}statistics")
    value = statistics.get("views", "") if statistics is not None else ""
    if not re.fullmatch(r"[0-9]{1,19}", value):
        return None
    return int(value)


def normalize_youtube_feed(
    payload: bytes,
    source: NewsSource,
    max_items: int,
) -> NormalizedVideoFeed:
    if source.kind is not SourceKind.YOUTUBE or not source.youtube_channel_id:
        raise YouTubeFeedParseError("The source is not a configured YouTube channel")
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise YouTubeFeedParseError("The YouTube feed could not be parsed") from error
    if root.tag != f"{{{ATOM_NAMESPACE}}}feed":
        raise YouTubeFeedParseError("The response is not a YouTube Atom feed")

    feed_channel_id = root.findtext(f"{{{YOUTUBE_NAMESPACE}}}channelId")
    if not _channel_matches(feed_channel_id, source.youtube_channel_id):
        raise YouTubeFeedParseError("The YouTube feed channel identity does not match its source")

    items = []
    seen_video_ids: set[str] = set()
    for source_order, entry in enumerate(root.findall(f"{{{ATOM_NAMESPACE}}}entry")):
        entry_channel_id = entry.findtext(f"{{{YOUTUBE_NAMESPACE}}}channelId")
        if not _channel_matches(entry_channel_id, source.youtube_channel_id):
            continue
        video_id = entry.findtext(f"{{{YOUTUBE_NAMESPACE}}}videoId")
        if not is_valid_video_id(video_id) or video_id in seen_video_ids:
            continue
        title = _plain_text(entry.findtext(f"{{{ATOM_NAMESPACE}}}title"))
        if not title:
            continue
        seen_video_ids.add(video_id)
        items.append(VideoItem(
            source_id=source.id,
            channel_name=source.display_name,
            video_id=video_id,
            title=title,
            published_at=_published_at(entry.findtext(f"{{{ATOM_NAMESPACE}}}published")),
            watch_url=build_watch_url(video_id),
            embed_url=build_embed_url(video_id),
            thumbnail_url=build_thumbnail_url(video_id),
            source_order=source_order,
            view_count=_view_count(entry),
        ))
        if len(items) >= max_items:
            break
    return NormalizedVideoFeed(items=tuple(items))
