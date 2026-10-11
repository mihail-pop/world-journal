"""User feeds join the existing registry, matching, cache and background queue."""
from dataclasses import replace
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit, urlunsplit
from xml.etree import ElementTree

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from news.adapters.rss import FeedParseError, _plain_text, normalize_feed
from news.adapters.youtube import ATOM_NAMESPACE, YouTubeFeedParseError, normalize_youtube_feed
from news.models import CustomSource
from news.registry import ROUTING_REGIONS, SourceRegistry, YOUTUBE_CHANNEL_PATTERN, get_source_registry
from news.types import FeedType, NewsFeed, NewsProvider, NewsSource, SourceKind

from .cache import fixed_feed_cache_key, youtube_cache_key
from .fetch import FeedFetchError, fetch_feed


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
FORMAT_LABELS = {"rss20": "RSS 2.0", "rss10": "RSS 1.0 / RDF", "atom10": "Atom 1.0", "atom03": "Atom 0.3"}


def format_label(value):
    return FORMAT_LABELS.get(value, value.upper() if value else "Not detected")


def normalize_location(value, kind):
    value = value.strip()
    if kind == CustomSource.Kind.YOUTUBE:
        if YOUTUBE_CHANNEL_PATTERN.fullmatch(value):
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={value}"
        if value.startswith("@"):
            value = f"https://www.youtube.com/{value}"
        elif value.startswith(("youtube.com/", "www.youtube.com/")):
            value = f"https://{value}"
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError
    except ValueError as error:
        raise FeedFetchError("Use a public HTTPS feed URL." if kind == "rss" else "Use a YouTube channel link, @handle, channel ID or channel feed URL.") from error
    if kind == CustomSource.Kind.YOUTUBE and parsed.hostname.lower() not in YOUTUBE_HOSTS:
        raise FeedFetchError("The channel link must belong to youtube.com.")
    return urlunsplit(("https", parsed.hostname.lower(), parsed.path or "/", parsed.query, ""))


class _ChannelPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.channel_ids = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "link" and values.get("type") == "application/rss+xml":
            channel = parse_qs(urlsplit(values.get("href", "")).query).get("channel_id", [""])[0]
        elif tag == "meta" and values.get("itemprop") == "channelId":
            channel = values.get("content", "")
        elif tag == "link" and values.get("rel") == "canonical":
            path = urlsplit(values.get("href", "")).path
            channel = path.removeprefix("/channel/") if path.startswith("/channel/") else ""
        else:
            return
        if YOUTUBE_CHANNEL_PATTERN.fullmatch(channel):
            self.channel_ids.append(channel)


def _channel_id(location):
    parsed = urlsplit(location)
    if parsed.path.rstrip("/") == "/feeds/videos.xml":
        candidate = parse_qs(parsed.query).get("channel_id", [""])[0]
    elif parsed.path.startswith("/channel/"):
        candidate = parsed.path.split("/")[2]
    elif parsed.path.startswith("/@"):
        # Read only public channel metadata, then verify the resulting Atom identity.
        channel_url = f"https://www.youtube.com/{parsed.path.split('/')[1]}"
        response = fetch_feed(channel_url, allowed_hosts=YOUTUBE_HOSTS)
        page = _ChannelPage()
        page.feed(response.body.decode("utf-8", errors="replace"))
        candidates = set(page.channel_ids)
        if len(candidates) != 1:
            raise FeedFetchError("Could not resolve this handle. Paste its channel ID or channel RSS URL instead.")
        candidate = candidates.pop()
    else:
        raise FeedFetchError("Paste a channel link or feed, rather than an individual video or playlist.")
    if not YOUTUBE_CHANNEL_PATTERN.fullmatch(candidate):
        raise FeedFetchError("The link does not contain a valid YouTube channel ID.")
    return candidate


def registry_items(record):
    identity = record.registry_id
    name = record.name or urlsplit(record.url).hostname or "Custom source"
    enabled = record.verified_at is not None
    reviewed = record.verified_at.date() if enabled else None
    if record.kind == CustomSource.Kind.YOUTUBE:
        return NewsSource(
            id=identity, kind=SourceKind.YOUTUBE, display_name=name,
            homepage_url=f"https://www.youtube.com/channel/{record.channel_id}" if record.channel_id else record.url,
            language="und", enabled_by_default=enabled, youtube_channel_id=record.channel_id,
            coverage_regions=tuple(sorted(ROUTING_REGIONS)), allowed_hosts=tuple(sorted(YOUTUBE_HOSTS)),
            verification_date=reviewed, display_priority=100,
        ), None
    host = urlsplit(record.url).hostname
    parent = record.parent if record.parent_id else record
    publisher_name = parent.name or urlsplit(parent.url).hostname or "Custom source"
    provider = NewsProvider(parent.registry_id, publisher_name, f"https://{urlsplit(parent.url).hostname}/", "und", None, "global", (), 100, enabled)
    feed = NewsFeed(
        id=f"{identity}_feed", provider_id=parent.registry_id, section_label=name if record.parent_id else "Articles",
        feed_url=record.url, source_type=FeedType.RSS, language="und",
        enabled_by_default=enabled, allowed_hosts=(host,), verification_date=reviewed,
        allow_public_redirects=True,
    )
    return provider, feed


def with_custom_sources(registry):
    sources, providers, feeds = list(registry.sources), list(registry.providers), list(registry.feeds)
    grouped_providers = {}
    for record in CustomSource.objects.select_related("parent"):
        item, feed = registry_items(record)
        if feed:
            previous = grouped_providers.get(item.id)
            grouped_providers[item.id] = replace(item, enabled_by_default=item.enabled_by_default or bool(previous and previous.enabled_by_default))
            feeds.append(feed)
        else:
            sources.append(item)
    return SourceRegistry(tuple(sources), tuple(providers) + tuple(grouped_providers.values()), tuple(feeds))


def check_custom_source(record):
    """One bounded live check. Failed sources stay visible and can be checked again."""
    now = timezone.now()
    record.last_checked_at = now
    try:
        location = normalize_location(record.url, record.kind)
        curated = get_source_registry()
        if record.kind == CustomSource.Kind.YOUTUBE:
            channel = _channel_id(location)
            location = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel}"
            if any(source.youtube_channel_id == channel for source in curated.sources):
                raise FeedFetchError("This channel is already in the built-in sources.")
            if CustomSource.objects.exclude(pk=record.pk).filter(channel_id=channel, kind="youtube").exists():
                raise FeedFetchError("This channel has already been added.")
            record.channel_id = channel
        elif any(feed.feed_url == location for feed in curated.feeds):
            raise FeedFetchError("This feed is already in the built-in sources.")
        if CustomSource.objects.exclude(pk=record.pk).filter(url=location).exists():
            raise FeedFetchError("This source has already been added.")
        record.url = location
        item, feed = registry_items(record)
        response = fetch_feed(location, allowed_hosts=set(feed.allowed_hosts if feed else item.allowed_hosts), allow_public_redirects=bool(feed))
        if feed:
            if response.final_url:
                if CustomSource.objects.exclude(pk=record.pk).filter(url=response.final_url).exists() or any(feed.feed_url == response.final_url for feed in curated.feeds):
                    raise FeedFetchError("This feed has already been added at its redirected address.")
            normalized = normalize_feed(response.body, item, settings.NEWS_FIXED_FEED_CACHE_ITEMS, feed=feed, base_url=response.final_url)
            # Keep the submitted address on failure, so retry does not get stuck
            # on a publisher's temporary redirect to an error/landing page.
            record.url = response.final_url or location
            record.feed_format = normalized.feed_format
            detected_name = normalized.title
        else:
            normalized = normalize_youtube_feed(response.body, item, settings.NEWS_YOUTUBE_FEED_CACHE_ITEMS)
            record.feed_format = "atom10"
            detected_name = _plain_text(ElementTree.fromstring(response.body).findtext(f"{{{ATOM_NAMESPACE}}}title"))
        if not record.name:
            record.name = (detected_name or urlsplit(location).hostname)[:160]
        record.verified_at, record.last_error = now, ""
        # Normalize with the detected/overridden name before retaining attribution.
        item, feed = registry_items(record)
        if feed:
            normalized = normalize_feed(response.body, item, settings.NEWS_FIXED_FEED_CACHE_ITEMS, feed=feed)
            key, ttl = fixed_feed_cache_key(feed), settings.NEWS_REGIONAL_STALE_SECONDS
        else:
            normalized = normalize_youtube_feed(response.body, item, settings.NEWS_YOUTUBE_FEED_CACHE_ITEMS)
            key, ttl = youtube_cache_key(item), settings.NEWS_YOUTUBE_STALE_SECONDS
        snapshot = {
            "items": [entry.as_cache_value() for entry in normalized.items],
            "fetched_at": now.isoformat(), "last_success_at": now.isoformat(),
            "last_attempt_at": now.isoformat(), "last_error": "", "last_error_detail": "",
            "etag": response.etag, "last_modified": response.last_modified,
            "parser_warnings": list(getattr(normalized, "parser_warnings", ())),
        }
        cache.set(key, snapshot, ttl)
        return True
    except (FeedFetchError, FeedParseError, YouTubeFeedParseError) as error:
        record.last_error = str(error)[:240]
        return False
