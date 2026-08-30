from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from time import monotonic, sleep

from django.conf import settings
from django.core.cache.backends.locmem import LocMemCache
from django.test import SimpleTestCase, override_settings

from news.registry import load_source_registry
from news.services.country_news import _country_for_code, get_country_news_page
from news.services.fetch import FeedFetchError, FeedResponse
from news.services.region_routing import eligible_fixed_feeds
from news.services.regional_news import get_fixed_feed, get_regional_news


FIXTURES = Path(__file__).parent / "fixtures"


def rss(*items: dict[str, str]) -> bytes:
    entries = []
    for item in items:
        summary = item.get("summary", "")
        date = item.get("date", "")
        entries.append(
            "<item>"
            f"<title>{escape(item['title'])}</title>"
            f"<link>{escape(item['link'])}</link>"
            f"<description><![CDATA[{summary}]]></description>"
            f"<pubDate>{escape(date)}</pubDate>"
            "</item>"
        )
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title>'
        + "".join(entries)
        + "</channel></rss>"
    ).encode()


class FixedFeedCacheTests(SimpleTestCase):
    def setUp(self):
        self.registry = load_source_registry()
        self.provider = self.registry.get_provider("dw")
        self.feed = self.registry.get_feed("dw_all")
        self.cache = LocMemCache(f"regional-{id(self)}", {})
        self.payload = (FIXTURES / "regional_europe.xml").read_bytes()
        self.now = datetime(2026, 8, 30, 14, 0, tzinfo=UTC)

    def test_disabled_feed_is_never_fetched(self):
        calls = []
        result = get_fixed_feed(
            self.registry.get_feed("al_arabiya_en_top"),
            self.registry.get_provider("al_arabiya_en"),
            cache_backend=self.cache,
            fetcher=lambda *args, **kwargs: calls.append(args),
            now=self.now,
        )

        self.assertEqual(calls, [])
        self.assertEqual(result.error, "Feed is disabled.")

    def test_explicit_redirect_host_allowlist_is_passed_to_fetcher(self):
        seen = {}

        def fetcher(url, **kwargs):
            seen.update(kwargs)
            return FeedResponse(self.payload, None, None)

        get_fixed_feed(
            self.feed,
            self.provider,
            cache_backend=self.cache,
            fetcher=fetcher,
            now=self.now,
        )

        self.assertEqual(seen["allowed_hosts"], {"rss.dw.com"})

    def test_same_fresh_feed_cache_is_reused_across_two_countries(self):
        calls = []

        def fetcher(*args, **kwargs):
            calls.append(args[0])
            return FeedResponse(self.payload, '"v1"', None)

        first = get_regional_news(
            _country_for_code("FR"),
            (self.provider,),
            (self.feed,),
            cache_backend=self.cache,
            fetcher=fetcher,
            now=self.now,
        )
        second = get_regional_news(
            _country_for_code("DE"),
            (self.provider,),
            (self.feed,),
            cache_backend=self.cache,
            fetcher=fetcher,
            now=self.now + timedelta(minutes=5),
        )

        self.assertEqual(calls, [self.feed.feed_url])
        self.assertEqual([item.title for item in first[0]], ["France announces a new energy plan"])
        self.assertEqual(
            [item.title for item in second[0]],
            ["Romania and Germany sign transport agreement", "Germany updates rail timetable"],
        )

    def test_sibling_feeds_have_independent_cache_keys_and_warm_reuse(self):
        provider = self.registry.get_provider("cgtn")
        feeds = tuple(feed for feed in self.registry.feeds if feed.provider_id == "cgtn")
        calls = []

        def fetcher(url, **kwargs):
            calls.append(url)
            return FeedResponse(self.payload, None, None)

        get_regional_news(
            _country_for_code("RO"),
            (provider,),
            feeds,
            cache_backend=self.cache,
            fetcher=fetcher,
            now=self.now,
        )
        get_regional_news(
            _country_for_code("GB"),
            (provider,),
            feeds,
            cache_backend=self.cache,
            fetcher=fetcher,
            now=self.now + timedelta(minutes=5),
        )

        self.assertCountEqual(calls, [feed.feed_url for feed in feeds])
        for feed in feeds:
            key = f"news:v{settings.NEWS_CACHE_SCHEMA_VERSION}:rss:{feed.id}:{feed.language}"
            self.assertIsNotNone(self.cache.get(key))

    def test_corrupt_cache_is_refetched(self):
        key = f"news:v{settings.NEWS_CACHE_SCHEMA_VERSION}:rss:{self.feed.id}:{self.feed.language}"
        self.cache.set(key, {
            "items": "corrupt",
            "last_success_at": self.now.isoformat(),
            "fetched_at": self.now.isoformat(),
        })
        calls = []

        result = get_fixed_feed(
            self.feed,
            self.provider,
            cache_backend=self.cache,
            fetcher=lambda *args, **kwargs: calls.append(args) or FeedResponse(self.payload, None, None),
            now=self.now,
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(result.items), 5)

    def test_failed_refresh_serves_stale_feed_and_honors_backoff(self):
        calls = []

        def success(*args, **kwargs):
            calls.append("success")
            return FeedResponse(self.payload, None, None)

        get_fixed_feed(self.feed, self.provider, cache_backend=self.cache, fetcher=success, now=self.now)

        def failure(*args, **kwargs):
            calls.append("failure")
            raise FeedFetchError("private detail")

        stale = get_fixed_feed(
            self.feed,
            self.provider,
            cache_backend=self.cache,
            fetcher=failure,
            now=self.now + timedelta(seconds=901),
        )
        backed_off = get_fixed_feed(
            self.feed,
            self.provider,
            cache_backend=self.cache,
            fetcher=failure,
            now=self.now + timedelta(seconds=920),
        )

        self.assertEqual(calls, ["success", "failure"])
        self.assertTrue(stale.is_stale)
        self.assertTrue(stale.refresh_failed)
        self.assertEqual(stale.items, backed_off.items)
        self.assertNotIn("private detail", stale.error)

    def test_malformed_and_valid_empty_feeds_have_distinct_states(self):
        malformed = get_fixed_feed(
            self.feed,
            self.provider,
            cache_backend=self.cache,
            fetcher=lambda *args, **kwargs: FeedResponse(b"<not-a-feed>", None, None),
            now=self.now,
        )
        self.cache.clear()
        empty = get_fixed_feed(
            self.feed,
            self.provider,
            cache_backend=self.cache,
            fetcher=lambda *args, **kwargs: FeedResponse(
                b'<?xml version="1.0"?><rss version="2.0"><channel><title>Empty</title></channel></rss>',
                None,
                None,
            ),
            now=self.now,
        )

        self.assertTrue(malformed.refresh_failed)
        self.assertFalse(empty.refresh_failed)
        self.assertEqual(empty.error, "")


class RegionalAggregationTests(SimpleTestCase):
    def setUp(self):
        self.registry = load_source_registry()
        self.cache = LocMemCache(f"aggregate-{id(self)}", {})
        self.payload = (FIXTURES / "regional_europe.xml").read_bytes()
        self.now = datetime(2026, 8, 30, 14, 0, tzinfo=UTC)

    def provider_feeds(self, provider_id):
        provider = self.registry.get_provider(provider_id)
        feeds = tuple(
            feed
            for feed in self.registry.feeds
            if feed.provider_id == provider_id and feed.enabled_by_default
        )
        return provider, feeds

    def test_all_enabled_feeds_are_eligible_for_every_country(self):
        expected = {feed.id for feed in self.registry.feeds if feed.enabled_by_default}

        for code in ("IR", "GB", "BR"):
            with self.subTest(code=code):
                self.assertEqual(
                    {feed.id for feed in eligible_fixed_feeds(_country_for_code(code), self.registry)},
                    expected,
                )

    def test_one_failed_sibling_makes_provider_partial_but_usable(self):
        provider, feeds = self.provider_feeds("cgtn")

        def fetcher(url, **kwargs):
            if "politics" in url:
                raise FeedFetchError("simulated")
            return FeedResponse(self.payload, None, None)

        items, results, warning = get_regional_news(
            _country_for_code("RO"),
            (provider,),
            feeds,
            cache_backend=self.cache,
            fetcher=fetcher,
            now=self.now,
        )

        self.assertTrue(items)
        self.assertEqual(results[0].status, "partial")
        self.assertEqual(results[0].failed_feed_count, 1)
        self.assertEqual(results[0].successful_feed_count, 2)
        self.assertIn("1 regional provider", warning)

    def test_all_failed_siblings_make_provider_unavailable(self):
        provider, feeds = self.provider_feeds("cgtn")

        _items, results, warning = get_regional_news(
            _country_for_code("RO"),
            (provider,),
            feeds,
            cache_backend=self.cache,
            fetcher=lambda *args, **kwargs: (_ for _ in ()).throw(FeedFetchError("simulated")),
            now=self.now,
        )

        self.assertEqual(results[0].status, "unavailable")
        self.assertEqual(results[0].failed_feed_count, 3)
        self.assertIn("1 regional provider", warning)

    def test_sibling_duplicates_merge_sections_and_prefer_complete_metadata(self):
        provider, feeds = self.provider_feeds("cgtn")
        feeds = feeds[:2]
        sparse = rss({"title": "Iran reaches agreement", "link": "https://example.com/sparse"})
        rich = rss({
            "title": "Iran reaches agreement",
            "link": "https://example.com/rich",
            "summary": "Full context.",
            "date": "Sun, 30 Aug 2026 12:00:00 GMT",
        })

        items, _results, _warning = get_regional_news(
            _country_for_code("IR"),
            (provider,),
            feeds,
            cache_backend=self.cache,
            fetcher=lambda url, **kwargs: FeedResponse(rich if "world" in url else sparse, None, None),
            now=self.now,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].feed_id, "cgtn_world")
        self.assertEqual(items[0].summary, "Full context.")
        self.assertEqual(items[0].contributing_sections, ("China", "World"))

    def test_match_class_precedes_affinity_recency_and_registry_priority(self):
        al_jazeera, al_jazeera_feeds = self.provider_feeds("al_jazeera_en")
        dw, dw_feeds = self.provider_feeds("dw")
        payloads = {
            al_jazeera_feeds[0].feed_url: rss({
                "title": "Markets update",
                "link": "https://example.com/summary",
                "summary": "Iran sees policy change.",
                "date": "Sun, 30 Aug 2026 13:00:00 GMT",
            }),
            dw_feeds[0].feed_url: rss({
                "title": "Iran policy changes",
                "link": "https://example.com/headline",
                "date": "Sun, 30 Aug 2026 10:00:00 GMT",
            }),
        }

        items, _results, _warning = get_regional_news(
            _country_for_code("IR"),
            (al_jazeera, dw),
            (*al_jazeera_feeds, *dw_feeds),
            cache_backend=self.cache,
            fetcher=lambda url, **kwargs: FeedResponse(payloads[url], None, None),
            now=self.now,
        )

        self.assertEqual([item.match_class for item in items], ["headline_country", "summary_country"])
        self.assertEqual(items[0].provider_id, "dw")

    def test_affinity_breaks_ties_without_excluding_cross_region_provider(self):
        cgtn, cgtn_feeds = self.provider_feeds("cgtn")
        dw, dw_feeds = self.provider_feeds("dw")
        same_date = "Sun, 30 Aug 2026 12:00:00 GMT"

        items, _results, _warning = get_regional_news(
            _country_for_code("IR"),
            (cgtn, dw),
            (cgtn_feeds[0], *dw_feeds),
            cache_backend=self.cache,
            fetcher=lambda url, **kwargs: FeedResponse(rss({
                "title": f"Iran report from {url}",
                "link": url.replace("/rss/", "/article/"),
                "date": same_date,
            }), None, None),
            now=self.now,
        )

        self.assertEqual({item.provider_id for item in items}, {"cgtn", "dw"})
        self.assertEqual(items[0].provider_id, "cgtn")

    def test_safe_summary_matches_uk_but_not_script_only_iran_and_reuses_feed(self):
        provider, feeds = self.provider_feeds("telesur_en")
        payload = rss({
            "title": "Markets update",
            "link": "https://example.com/markets",
            "summary": "British outlook improves.<script>Iran</script>",
        })
        calls = []

        def fetcher(url, **kwargs):
            calls.append(url)
            return FeedResponse(payload, None, None)

        uk_items = get_regional_news(
            _country_for_code("GB"),
            (provider,),
            feeds,
            cache_backend=self.cache,
            fetcher=fetcher,
            now=self.now,
        )[0]
        iran_items = get_regional_news(
            _country_for_code("IR"),
            (provider,),
            feeds,
            cache_backend=self.cache,
            fetcher=fetcher,
            now=self.now + timedelta(minutes=5),
        )[0]

        self.assertEqual(len(uk_items), 1)
        self.assertEqual(uk_items[0].match_class, "summary_country")
        self.assertEqual(iran_items, ())
        self.assertEqual(calls, [feeds[0].feed_url])

    @override_settings(
        NEWS_REGIONAL_PER_FEED_LIMIT=2,
        NEWS_REGIONAL_PER_PROVIDER_LIMIT=3,
        NEWS_REGIONAL_TOTAL_LIMIT=4,
    )
    def test_feed_provider_and_overall_limits(self):
        cgtn, cgtn_feeds = self.provider_feeds("cgtn")
        dw, dw_feeds = self.provider_feeds("dw")

        def payload(url):
            return rss(*(
                {
                    "title": f"China update {index} from {url}",
                    "link": f"https://example.com/{abs(hash(url))}/{index}",
                    "date": f"Sun, 30 Aug 2026 {12 - index:02d}:00:00 GMT",
                }
                for index in range(5)
            ))

        items, _results, _warning = get_regional_news(
            _country_for_code("CN"),
            (cgtn, dw),
            (*cgtn_feeds, *dw_feeds),
            cache_backend=self.cache,
            fetcher=lambda url, **kwargs: FeedResponse(payload(url), None, None),
            now=self.now,
        )

        self.assertEqual(len(items), 4)
        self.assertLessEqual(max(sum(item.feed_id == feed.id for item in items) for feed in (*cgtn_feeds, *dw_feeds)), 2)
        self.assertEqual(sum(item.provider_id == "cgtn" for item in items), 3)

    @override_settings(NEWS_REGIONAL_FETCH_WAIT_SECONDS=0.005, NEWS_REGIONAL_WORKERS=2)
    def test_overall_cold_fetch_wait_is_bounded(self):
        provider, feeds = self.provider_feeds("cgtn")

        def slow_fetcher(*args, **kwargs):
            sleep(0.08)
            return FeedResponse(self.payload, None, None)

        started = monotonic()
        _items, results, _warning = get_regional_news(
            _country_for_code("RO"),
            (provider,),
            feeds,
            cache_backend=self.cache,
            fetcher=slow_fetcher,
            now=self.now,
        )

        self.assertLess(monotonic() - started, 0.06)
        self.assertEqual(results[0].status, "unavailable")

    def test_google_remains_available_when_a_regional_provider_fails(self):
        google_payload = (FIXTURES / "google_news.xml").read_bytes()

        def fetcher(url, **kwargs):
            if "news.google.com" in url:
                return FeedResponse(google_payload, None, None)
            if "cgtn.com" in url:
                raise FeedFetchError("simulated")
            return FeedResponse(self.payload, None, None)

        page = get_country_news_page(
            "RO",
            cache_backend=self.cache,
            registry=self.registry,
            fetcher=fetcher,
            now=self.now,
        )

        self.assertEqual(len(page.google.items), 2)
        self.assertTrue(page.regional_items)
        self.assertIn("regional provider", page.regional_warning)

    def test_no_country_match_is_a_normal_empty_result(self):
        provider, feeds = self.provider_feeds("dw")
        items, results, warning = get_regional_news(
            _country_for_code("ES"),
            (provider,),
            feeds,
            cache_backend=self.cache,
            fetcher=lambda *args, **kwargs: FeedResponse(self.payload, None, None),
            now=self.now,
        )

        self.assertEqual(items, ())
        self.assertEqual(results[0].status, "available")
        self.assertEqual(warning, "")
