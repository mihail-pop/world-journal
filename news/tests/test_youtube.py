from dataclasses import replace
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from time import monotonic, sleep

from django.conf import settings
from django.core.cache.backends.locmem import LocMemCache
from django.test import SimpleTestCase, override_settings

from news.adapters.youtube import (
    YouTubeFeedParseError,
    build_embed_url,
    build_thumbnail_url,
    build_watch_url,
    normalize_youtube_feed,
)
from news.registry import load_source_registry
from news.services.fetch import FeedFetchError, FeedResponse
from news.services.region_routing import eligible_youtube_sources
from news.services.country_news import _country_for_code
from news.services.youtube_news import get_country_videos, get_youtube_feed


FIXTURES = Path(__file__).parent / "fixtures"


def youtube_atom(source, *titles, prefix="V"):
    channel = source.youtube_channel_id[2:]
    entries = []
    for index, title in enumerate(titles):
        video_id = f"{prefix}{index:010d}"
        entries.append(
            "<entry>"
            f"<yt:videoId>{video_id}</yt:videoId>"
            f"<yt:channelId>{channel}</yt:channelId>"
            f"<title>{escape(title)}</title>"
            f"<published>2026-08-30T{12 - index:02d}:00:00Z</published>"
            "</entry>"
        )
    return (
        '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:yt="http://www.youtube.com/xml/schemas/2015">'
        f"<yt:channelId>{channel}</yt:channelId>"
        + "".join(entries)
        + "</feed>"
    ).encode()


class YouTubeAdapterTests(SimpleTestCase):
    def setUp(self):
        configured = load_source_registry().get("youtube_al_jazeera_en")
        self.source = replace(
            configured,
            id="youtube_example",
            display_name="Example Channel",
            homepage_url="https://www.youtube.com/channel/UC1234567890123456789012",
            youtube_channel_id="UC1234567890123456789012",
        )
        self.payload = (FIXTURES / "youtube_atom.xml").read_bytes()

    def test_parses_namespaced_atom_and_derives_only_trusted_urls(self):
        feed = normalize_youtube_feed(self.payload, self.source, 10)

        self.assertEqual(len(feed.items), 2)
        first = feed.items[0]
        self.assertEqual(first.video_id, "AbCdEfGhI01")
        self.assertEqual(first.title, "Iran and Romania hold talks")
        self.assertEqual(first.published_at.isoformat(), "2026-08-30T12:00:00+00:00")
        self.assertEqual(first.watch_url, "https://www.youtube.com/watch?v=AbCdEfGhI01")
        self.assertEqual(first.embed_url, "https://www.youtube-nocookie.com/embed/AbCdEfGhI01")
        self.assertEqual(first.thumbnail_url, "https://i.ytimg.com/vi/AbCdEfGhI01/hqdefault.jpg")
        self.assertNotIn("example.invalid", repr(first))

    def test_missing_date_is_safe_and_duplicate_video_id_is_removed(self):
        feed = normalize_youtube_feed(self.payload, self.source, 10)

        self.assertIsNone(feed.items[1].published_at)
        self.assertEqual([item.video_id for item in feed.items], ["AbCdEfGhI01", "ZxYwVuTsR02"])

    def test_feed_level_channel_identity_must_match(self):
        payload = self.payload.replace(
            b"<yt:channelId>1234567890123456789012</yt:channelId>",
            b"<yt:channelId>wrong-channel-identity</yt:channelId>",
            1,
        )

        with self.assertRaisesRegex(YouTubeFeedParseError, "channel identity"):
            normalize_youtube_feed(payload, self.source, 10)

    def test_invalid_and_mismatched_entries_are_rejected(self):
        invalid_video = self.payload.replace(b"ZxYwVuTsR02", b"invalid-id!", 2)
        feed_identity, separator, entries = invalid_video.partition(b"</yt:channelId>")
        mismatched_channel = feed_identity + separator + entries.replace(
            b"<yt:channelId>1234567890123456789012</yt:channelId>",
            b"<yt:channelId>abcdefghijklmnopqrstuv</yt:channelId>",
        )

        feed = normalize_youtube_feed(mismatched_channel, self.source, 10)

        self.assertEqual(feed.items, ())

    def test_url_builders_reject_invalid_video_ids(self):
        for builder in (build_watch_url, build_embed_url, build_thumbnail_url):
            with self.subTest(builder=builder.__name__), self.assertRaises(ValueError):
                builder('bad"><script')


class YouTubeServiceTests(SimpleTestCase):
    def setUp(self):
        self.registry = load_source_registry()
        self.source = self.registry.get("youtube_al_jazeera_en")
        self.cache = LocMemCache(f"youtube-{id(self)}", {})
        self.now = datetime(2026, 8, 30, 14, 0, tzinfo=UTC)

    def test_disabled_channel_is_never_fetched(self):
        calls = []
        result = get_youtube_feed(
            self.registry.get("youtube_cgtn"),
            cache_backend=self.cache,
            fetcher=lambda *args, **kwargs: calls.append(args),
            now=self.now,
        )

        self.assertEqual(calls, [])
        self.assertEqual(result.status, "disabled")

    def test_routes_only_enabled_channels_for_country_region(self):
        self.assertEqual(
            [source.id for source in eligible_youtube_sources(_country_for_code("IR"), self.registry)],
            ["youtube_al_jazeera_en"],
        )
        self.assertEqual(
            {source.id for source in eligible_youtube_sources(_country_for_code("DE"), self.registry)},
            {"youtube_dw_news", "youtube_france24_en"},
        )
        self.assertEqual(eligible_youtube_sources(_country_for_code("CN"), self.registry), ())

    def test_fresh_channel_cache_is_reused_across_countries(self):
        calls = []
        payload = youtube_atom(self.source, "Iran policy update", "Iraq election update")

        def fetcher(*args, **kwargs):
            calls.append(args[0])
            return FeedResponse(payload, '"v1"', None)

        iran = get_country_videos("IR", cache_backend=self.cache, fetcher=fetcher, now=self.now)
        iraq = get_country_videos(
            "IQ",
            cache_backend=self.cache,
            fetcher=fetcher,
            now=self.now + timedelta(minutes=5),
        )

        self.assertEqual(calls, [self.source.youtube_feed_url])
        self.assertEqual([item.title for item in iran.items], ["Iran policy update"])
        self.assertEqual([item.title for item in iraq.items], ["Iraq election update"])

    def test_lowercase_country_code_is_normalized(self):
        page = get_country_videos(
            "ir",
            cache_backend=self.cache,
            fetcher=lambda *args, **kwargs: FeedResponse(
                youtube_atom(self.source, "Iran update"), None, None
            ),
            now=self.now,
        )

        self.assertEqual(page.country_code, "IR")
        self.assertEqual([item.title for item in page.items], ["Iran update"])

    def test_corrupt_cache_is_refetched(self):
        key = f"news:v{settings.NEWS_CACHE_SCHEMA_VERSION}:youtube:{self.source.id}:{self.source.language}"
        self.cache.set(key, {"items": "corrupt", "last_success_at": self.now.isoformat()})
        calls = []

        result = get_youtube_feed(
            self.source,
            cache_backend=self.cache,
            fetcher=lambda *args, **kwargs: calls.append(args) or FeedResponse(
                youtube_atom(self.source, "Iran update"), None, None
            ),
            now=self.now,
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(result.items), 1)

    def test_failed_refresh_serves_stale_data_and_honors_backoff(self):
        calls = []
        payload = youtube_atom(self.source, "Iran update")
        get_youtube_feed(
            self.source,
            cache_backend=self.cache,
            fetcher=lambda *args, **kwargs: calls.append("success") or FeedResponse(payload, None, None),
            now=self.now,
        )

        def failure(*args, **kwargs):
            calls.append("failure")
            raise FeedFetchError("private detail")

        stale = get_youtube_feed(
            self.source,
            cache_backend=self.cache,
            fetcher=failure,
            now=self.now + timedelta(seconds=901),
        )
        backed_off = get_youtube_feed(
            self.source,
            cache_backend=self.cache,
            fetcher=failure,
            now=self.now + timedelta(seconds=920),
        )

        self.assertEqual(calls, ["success", "failure"])
        self.assertTrue(stale.is_stale)
        self.assertTrue(backed_off.is_stale)
        self.assertNotIn("private detail", stale.error)

        page = get_country_videos(
            "IR",
            cache_backend=self.cache,
            fetcher=failure,
            now=self.now + timedelta(seconds=930),
        )
        self.assertEqual(page.status, "stale")

    def test_partial_channel_failure_keeps_successful_channel(self):
        dw = self.registry.get("youtube_dw_news")
        france24 = self.registry.get("youtube_france24_en")

        def fetcher(url, **kwargs):
            if url == dw.youtube_feed_url:
                raise FeedFetchError("simulated")
            return FeedResponse(youtube_atom(france24, "Germany and France meet", prefix="F"), None, None)

        page = get_country_videos("DE", cache_backend=self.cache, fetcher=fetcher, now=self.now)

        self.assertEqual(page.status, "partial")
        self.assertEqual([item.source_id for item in page.items], [france24.id])
        self.assertIn("1 video channel", page.warning)

    def test_total_channel_failure_has_scoped_unavailable_state(self):
        page = get_country_videos(
            "DE",
            cache_backend=self.cache,
            fetcher=lambda *args, **kwargs: (_ for _ in ()).throw(FeedFetchError("simulated")),
            now=self.now,
        )

        self.assertEqual(page.status, "unavailable")
        self.assertEqual(page.items, ())
        self.assertTrue(all(result.status == "unavailable" for result in page.sources))

    @override_settings(NEWS_YOUTUBE_FETCH_WAIT_SECONDS=0.005, NEWS_YOUTUBE_WORKERS=2)
    def test_overall_cold_fetch_wait_is_bounded(self):
        def slow_fetcher(*args, **kwargs):
            sleep(0.08)
            return FeedResponse(b"", None, None)

        started = monotonic()
        page = get_country_videos(
            "DE",
            cache_backend=self.cache,
            fetcher=slow_fetcher,
            now=self.now,
        )

        self.assertLess(monotonic() - started, 0.06)
        self.assertEqual(page.status, "unavailable")

    @override_settings(NEWS_YOUTUBE_PER_CHANNEL_LIMIT=2, NEWS_YOUTUBE_TOTAL_LIMIT=3)
    def test_per_channel_and_overall_limits(self):
        sources = {
            source.youtube_feed_url: source
            for source in eligible_youtube_sources(_country_for_code("DE"), self.registry)
        }

        def fetcher(url, **kwargs):
            source = sources[url]
            prefix = "D" if source.id == "youtube_dw_news" else "F"
            return FeedResponse(
                youtube_atom(source, *(f"Germany update {index}" for index in range(5)), prefix=prefix),
                None,
                None,
            )

        page = get_country_videos("DE", cache_backend=self.cache, fetcher=fetcher, now=self.now)

        self.assertEqual(len(page.items), 3)
        self.assertLessEqual(max(sum(item.source_id == source.id for item in page.items) for source in sources.values()), 2)