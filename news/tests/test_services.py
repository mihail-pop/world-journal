from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from django.core.cache.backends.locmem import LocMemCache
from django.test import SimpleTestCase, override_settings

from news.services.country_news import CountryNotFoundError, get_country_news
from news.services.fetch import FeedFetchError, FeedResponse, fetch_feed


FIXTURES = Path(__file__).parent / "fixtures"
PUBLIC_RESOLVER = lambda hostname: ("142.250.72.206",)


class SafeFeedFetcherTests(SimpleTestCase):
    def test_sends_conditionals_and_returns_bounded_response(self):
        def handler(request):
            self.assertEqual(request.headers["If-None-Match"], '"feed-v1"')
            self.assertEqual(request.headers["If-Modified-Since"], "Sun, 30 Aug 2026 09:00:00 GMT")
            return httpx.Response(200, content=b"<rss />", headers={"ETag": '"feed-v2"'})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            response = fetch_feed(
                "https://news.google.com/rss/search?q=Romania",
                allowed_hosts={"news.google.com"},
                etag='"feed-v1"',
                last_modified="Sun, 30 Aug 2026 09:00:00 GMT",
                client=client,
                resolver=PUBLIC_RESOLVER,
            )

        self.assertEqual(response.body, b"<rss />")
        self.assertEqual(response.etag, '"feed-v2"')

    def test_rejects_unregistered_redirect_host(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(302, headers={"Location": "https://example.com/feed.xml"})
        )
        with httpx.Client(transport=transport) as client:
            with self.assertRaisesRegex(FeedFetchError, "not an allowed HTTPS source"):
                fetch_feed(
                    "https://news.google.com/rss/search?q=Romania",
                    allowed_hosts={"news.google.com"},
                    client=client,
                    resolver=PUBLIC_RESOLVER,
                )

    def test_rejects_private_resolution(self):
        with self.assertRaisesRegex(FeedFetchError, "non-public address"):
            fetch_feed(
                "https://news.google.com/rss/search?q=Romania",
                allowed_hosts={"news.google.com"},
                resolver=lambda hostname: ("127.0.0.1",),
            )

    @override_settings(NEWS_HTTP_MAX_BYTES=4)
    def test_rejects_oversized_response(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"12345"))
        with httpx.Client(transport=transport) as client:
            with self.assertRaisesRegex(FeedFetchError, "size limit"):
                fetch_feed(
                    "https://news.google.com/rss/search?q=Romania",
                    allowed_hosts={"news.google.com"},
                    client=client,
                    resolver=PUBLIC_RESOLVER,
                )


class CountryNewsServiceTests(SimpleTestCase):
    def setUp(self):
        self.cache = LocMemCache("country-news-tests", {})
        self.cache.clear()
        self.payload = (FIXTURES / "google_news.xml").read_bytes()
        self.now = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)

    def test_fresh_snapshot_avoids_second_fetch(self):
        calls = []

        def fetcher(*args, **kwargs):
            calls.append((args, kwargs))
            return FeedResponse(self.payload, '"v1"', "Sun, 30 Aug 2026 09:00:00 GMT")

        first = get_country_news("RO", cache_backend=self.cache, fetcher=fetcher, now=self.now)
        second = get_country_news("RO", cache_backend=self.cache, fetcher=fetcher, now=self.now + timedelta(minutes=5))

        self.assertEqual(len(calls), 1)
        self.assertEqual(first.items, second.items)
        self.assertFalse(second.is_stale)

    def test_stale_snapshot_is_served_after_refresh_failure_with_backoff(self):
        calls = []

        def successful_fetcher(*args, **kwargs):
            calls.append("success")
            return FeedResponse(self.payload, '"v1"', None)

        get_country_news("RO", cache_backend=self.cache, fetcher=successful_fetcher, now=self.now)

        def failed_fetcher(*args, **kwargs):
            calls.append("failure")
            raise FeedFetchError("simulated provider failure")

        stale = get_country_news(
            "RO",
            cache_backend=self.cache,
            fetcher=failed_fetcher,
            now=self.now + timedelta(seconds=901),
        )
        backed_off = get_country_news(
            "RO",
            cache_backend=self.cache,
            fetcher=failed_fetcher,
            now=self.now + timedelta(seconds=920),
        )

        self.assertEqual(calls, ["success", "failure"])
        self.assertTrue(stale.is_stale)
        self.assertTrue(backed_off.is_stale)
        self.assertEqual(len(stale.items), 2)
        self.assertIn("cached results", stale.warning)

    def test_invalid_country_is_rejected_before_fetch(self):
        with self.assertRaises(CountryNotFoundError):
            get_country_news("ZZ", cache_backend=self.cache, fetcher=lambda *args, **kwargs: None)