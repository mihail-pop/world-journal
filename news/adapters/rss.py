from __future__ import annotations

import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urldefrag, urlsplit, urlunsplit

import feedparser

from news.types import NewsFeed, NewsItem, NewsProvider, NewsSource, NormalizedFeed, SourceKind


MAX_FEED_ARTICLES = 500
OPEN_NEWS_PUBLISHERS = {
    "africanews": "africanews.com",
    "africanews english": "africanews.com",
    "al jazeera": "aljazeera.com",
    "al jazeera english": "aljazeera.com",
    "ap news": "apnews.com",
    "associated press": "apnews.com",
    "cbc news": "cbc.ca",
    "cbc.ca": "cbc.ca",
    "cgtn": "cgtn.com",
    "channel newsasia": "channelnewsasia.com",
    "cna": "channelnewsasia.com",
    "deutsche welle": "dw.com",
    "dw": "dw.com",
    "dw.com": "dw.com",
    "euronews": "euronews.com",
    "france 24": "france24.com",
    "npr": "npr.org",
    "telesur english": "telesurenglish.net",
}


class FeedParseError(ValueError):
    pass


class _PlainTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style"}:
            self.ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style"} and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)


def _plain_text(value: object) -> str:
    parser = _PlainTextParser()
    parser.feed(value if isinstance(value, str) else "")
    return " ".join("".join(parser.parts).split())


def _safe_link(value: object, *, https_hosts: tuple[str, ...] = ()) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError:
        return None
    if parsed.username or parsed.password:
        return None
    # Reviewed publishers sometimes advertise HTTP links despite serving HTTPS.
    # Upgrade only their own host; never guess HTTPS support for unrelated links.
    if parsed.scheme == "http" and parsed.hostname in https_hosts and port in (None, 80):
        parsed = parsed._replace(scheme="https", netloc=parsed.hostname)
        value = urlunsplit(parsed)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
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


def _publisher(entry: dict, source: NewsSource | NewsProvider) -> str:
    item_source = entry.get("source")
    if isinstance(item_source, dict):
        publisher = _plain_text(item_source.get("title"))
        if publisher:
            return publisher
    return source.display_name


def is_google_news_link(link: str) -> bool:
    try:
        return urlsplit(link).hostname == "news.google.com"
    except ValueError:
        return False


class _RelatedArticlesParser(HTMLParser):
    """Read each Google News list item's linked headline and trailing byline."""

    def __init__(self):
        super().__init__()
        self.articles: list[tuple[str, str, str]] = []
        self._href = None
        self._title = []
        self._byline = []
        self._text = None

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self._href = None
            self._title = []
            self._byline = []
            self._text = self._byline
        elif tag == "a" and self._text is not None:
            if self._href is not None:
                self._text = None  # A row with several links is ambiguous.
            else:
                self._href = dict(attrs).get("href") or ""
                self._text = self._title

    def handle_endtag(self, tag):
        if self._text is None:
            return
        if tag == "a":
            self._text = self._byline
        elif tag == "li":
            if self._href:
                headline = " ".join("".join(self._title).split())
                publisher = " ".join("".join(self._byline).split())
                self.articles.append((headline, self._href, publisher))
            self._text = None

    def handle_data(self, data):
        if self._text is not None:
            self._text.append(data)


def _preferred_google_article(title, link, publisher, description):
    if publisher.casefold() in OPEN_NEWS_PUBLISHERS or not isinstance(description, str) or "<li" not in description:
        return title, link, publisher

    parser = _RelatedArticlesParser()
    parser.feed(description)
    for headline, href, byline in parser.articles:
        domain = OPEN_NEWS_PUBLISHERS.get(byline.casefold())
        if not domain or not headline:
            continue
        alternative = _safe_link(href)
        if not alternative or alternative == link or len(alternative) > 2048:
            continue
        target = urlsplit(alternative)
        if target.scheme != "https" or target.port not in (None, 443) or not target.hostname:
            continue
        if target.hostname == "news.google.com":
            if target.path.startswith("/rss/articles/") and target.path != "/rss/articles/":
                return headline, alternative, byline
        elif target.hostname == domain or target.hostname.endswith("." + domain):
            if target.path.strip("/"):
                return headline, alternative, byline
    return title, link, publisher


def clean_article_text(title: str, publisher: str, summary: str, *, google: bool = False) -> tuple[str, str]:
    """Keep publisher attribution separate and omit descriptions that aren't abstracts."""
    original_title = title
    if publisher.strip():
        # Match the actual byline, not any arbitrary text after a headline dash.
        suffix = r"(?:\s+[-–—]\s*|\s*\|\s*)" + re.escape(publisher.strip()) + r"\s*$"
        headline = re.sub(suffix, "", title, flags=re.IGNORECASE).strip()
        if headline:
            title = headline
    if google:
        # Google's RSS descriptions are headline links/related-story clusters.
        # They aren't publisher summaries; don't label them as article abstracts.
        return title, ""

    def comparable(value):
        return re.sub(r"[\W_]+", "", value.casefold())

    repeated = {comparable(value) for value in (title, original_title, title + publisher, original_title + publisher)}
    if comparable(summary) in repeated:
        summary = ""
    return title, summary


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


def normalize_feed(
    payload: bytes,
    source: NewsSource | NewsProvider,
    max_items: int | None = None,
    *,
    feed: NewsFeed | None = None,
    base_url: str | None = None,
) -> NormalizedFeed:
    location = base_url or (feed.feed_url if feed else "")
    parsed = feedparser.parse(payload, response_headers={"content-location": location} if location else None)
    if not parsed.version:
        raise FeedParseError("The response is not a recognized RSS or Atom feed")
    warnings = ()
    if parsed.bozo:
        warnings = (str(parsed.bozo_exception)[:240],)
    if parsed.bozo and not parsed.entries:
        raise FeedParseError("The feed could not be parsed")

    google_source = isinstance(source, NewsSource) and source.kind is SourceKind.DYNAMIC_COUNTRY_RSS
    items = []
    for source_order, entry in enumerate(parsed.entries):
        title = _plain_text(entry.get("title"))
        link = _safe_link(entry.get("link"), https_hosts=feed.allowed_hosts if feed else ())
        if not title or not link:
            continue
        publisher = _publisher(entry, source)
        description = entry.get("summary") or entry.get("description")
        if google_source:
            title, link, publisher = _preferred_google_article(title, link, publisher, description)
        google = google_source or is_google_news_link(link)
        title, summary = clean_article_text(
            title, publisher, "" if google else _plain_text(description), google=google,
        )
        items.append(
            NewsItem(
                title=title,
                link=link,
                publisher=publisher,
                published_at=_published_at(entry),
                summary=summary,
                provider_id=source.id,
                provider_name=source.display_name,
                feed_id=feed.id if feed else source.id,
                feed_section=feed.section_label if feed else "",
                contributing_sections=(feed.section_label,) if feed else (),
                source_order=source_order,
            )
        )
    if parsed.entries and not items:
        raise FeedParseError("The feed contains entries, but none have a usable title and HTTP(S) link")
    limit = MAX_FEED_ARTICLES if max_items is None else min(max_items, MAX_FEED_ARTICLES)
    return NormalizedFeed(items=_deduplicate(items)[:limit], parser_warnings=warnings,
                          feed_format=parsed.version, title=_plain_text(parsed.feed.get("title")))
