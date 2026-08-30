import json
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from django.test import SimpleTestCase

from news.adapters.google_news import build_feed_url
from news.adapters.rss import normalize_feed
from news.registry import SourceConfigurationError, load_source_registry
from news.types import SourceKind


FIXTURES = Path(__file__).parent / "fixtures"


class SourceRegistryTests(SimpleTestCase):
    def provider(self, **overrides):
        provider = {
            "id": "example_provider",
            "display_name": "Example Provider",
            "homepage_url": "https://example.com/",
            "language": "en",
            "publisher_country_code": "US",
            "editorial_region": "north_america",
            "coverage_regions": ["north_america"],
            "display_priority": 10,
            "enabled_by_default": True,
        }
        provider.update(overrides)
        return provider

    def feed(self, **overrides):
        feed = {
            "id": "example_provider_top",
            "provider_id": "example_provider",
            "section_label": "Top Stories",
            "feed_url": "https://feeds.example.com/news.xml",
            "source_type": "rss",
            "language": "en",
            "enabled_by_default": True,
            "allowed_hosts": ["feeds.example.com"],
            "verification_date": "2026-08-30",
            "disabled_reason": "",
            "operational_notes": "Verified fixture feed.",
        }
        feed.update(overrides)
        return feed

    def youtube_source(self, **overrides):
        source = {
            "id": "youtube_example",
            "kind": "youtube",
            "display_name": "Example Channel",
            "homepage_url": "https://www.youtube.com/channel/UC1234567890123456789012",
            "language": "en",
            "enabled_by_default": True,
            "youtube_channel_id": "UC1234567890123456789012",
            "editorial_region": "north_america",
            "coverage_regions": ["north_america"],
            "allowed_hosts": ["www.youtube.com"],
            "verification_date": "2026-08-30",
            "disabled_reason": "",
            "operational_notes": "Verified fixture channel.",
            "display_priority": 10,
        }
        source.update(overrides)
        return source

    def write_provider_registry(self, directory, *, providers=None, feeds=None):
        path = Path(directory) / "sources.json"
        path.write_text(json.dumps({
            "schema_version": 4,
            "sources": [{
                "id": "google_news_country",
                "kind": "dynamic_country_rss",
                "display_name": "Google News",
                "homepage_url": "https://news.google.com/",
                "language": "en",
                "enabled_by_default": True,
                "feed_host": "news.google.com",
                "edition": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
            }],
            "providers": providers if providers is not None else [self.provider()],
            "feeds": feeds if feeds is not None else [self.feed()],
        }), encoding="utf-8")
        return path

    def write_youtube_registry(self, directory, sources):
        path = self.write_provider_registry(directory, providers=[], feeds=[])
        value = json.loads(path.read_text(encoding="utf-8"))
        value["sources"].extend(sources)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_schema_three_supports_one_provider_with_multiple_feeds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_provider_registry(directory, feeds=[
                self.feed(),
                self.feed(id="example_provider_world", section_label="World", feed_url="https://feeds.example.com/world.xml"),
            ])

            registry = load_source_registry(path)

        self.assertEqual(registry.get_provider("example_provider").display_name, "Example Provider")
        self.assertEqual([feed.section_label for feed in registry.feeds], ["Top Stories", "World"])

    def test_schema_three_rejects_orphan_and_duplicate_feeds(self):
        cases = (
            ([self.feed(provider_id="missing")], "unknown providers"),
            ([self.feed(), self.feed()], "ids must be globally unique"),
            ([self.feed(), self.feed(id="other_feed")], "URLs must be unique"),
        )
        for feeds, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                path = self.write_provider_registry(directory, feeds=feeds)
                with self.assertRaisesRegex(SourceConfigurationError, message):
                    load_source_registry(path)

    def test_schema_three_rejects_invalid_or_incomplete_active_feed(self):
        cases = (
            ({"feed_url": "http://feeds.example.com/news.xml"}, "must be an HTTPS URL"),
            ({"allowed_hosts": ["cdn.example.com"]}, "must include its feed host"),
            ({"verification_date": "not-a-date"}, "invalid verification_date"),
        )
        for overrides, message in cases:
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory() as directory:
                path = self.write_provider_registry(directory, feeds=[self.feed(**overrides)])
                with self.assertRaisesRegex(SourceConfigurationError, message):
                    load_source_registry(path)

    def test_provider_and_feed_enablement_must_be_consistent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_provider_registry(
                directory,
                providers=[self.provider(enabled_by_default=False)],
                feeds=[self.feed()],
            )
            with self.assertRaisesRegex(SourceConfigurationError, "enabled provider"):
                load_source_registry(path)

    def test_registry_contains_google_and_all_audited_fixed_sources(self):
        registry = load_source_registry()

        self.assertEqual(len(registry.sources), 10)
        self.assertTrue(registry.sources[0].enabled_by_default)
        self.assertEqual(registry.sources[0].feed_host, "news.google.com")
        youtube_sources = tuple(source for source in registry.sources if source.kind is SourceKind.YOUTUBE)
        self.assertEqual(len(youtube_sources), 9)
        self.assertEqual(sum(source.enabled_by_default for source in youtube_sources), 5)
        self.assertTrue(all(source.youtube_feed_url for source in youtube_sources))
        self.assertEqual(len(registry.providers), 12)
        self.assertEqual(len(registry.feeds), 18)
        self.assertEqual(sum(provider.enabled_by_default for provider in registry.providers), 11)
        self.assertEqual(sum(feed.enabled_by_default for feed in registry.feeds), 13)
        self.assertEqual(
            {feed.id for feed in registry.feeds if not feed.enabled_by_default},
            {
                "al_arabiya_en_top",
                "al_arabiya_en_news",
                "al_arabiya_en_business",
                "al_arabiya_en_energy",
                "al_arabiya_en_life",
            },
        )
        self.assertEqual(
            {feed.id for feed in registry.feeds if feed.provider_id == "cgtn"},
            {"cgtn_china", "cgtn_world", "cgtn_politics"},
        )

    def test_unknown_fields_fail_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_provider_registry(directory, feeds=[self.feed(unexpected=True)])

            with self.assertRaisesRegex(SourceConfigurationError, "invalid fields"):
                load_source_registry(path)

    def test_non_https_source_url_fails_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_provider_registry(directory, feeds=[self.feed(feed_url="http://feeds.example.com/news.xml")])

            with self.assertRaisesRegex(SourceConfigurationError, "must be an HTTPS URL"):
                load_source_registry(path)

    def test_invalid_region_and_missing_feed_host_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid_region = self.write_provider_registry(directory, providers=[self.provider(coverage_regions=["world"])])
            with self.assertRaisesRegex(SourceConfigurationError, "invalid coverage_regions"):
                load_source_registry(invalid_region)

        with tempfile.TemporaryDirectory() as directory:
            missing_host = self.write_provider_registry(directory, feeds=[self.feed(allowed_hosts=["cdn.example.com"])])
            with self.assertRaisesRegex(SourceConfigurationError, "must include its feed host"):
                load_source_registry(missing_host)

    def test_enabled_source_requires_valid_audit_metadata(self):
        cases = (
            ({"verification_date": "not-a-date"}, "invalid verification_date"),
            ({"disabled_reason": "Not really enabled"}, "cannot have a disabled_reason"),
            ({"operational_notes": ""}, "invalid operational_notes"),
        )
        for overrides, message in cases:
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory() as directory:
                path = self.write_provider_registry(directory, feeds=[self.feed(**overrides)])
                with self.assertRaisesRegex(SourceConfigurationError, message):
                    load_source_registry(path)

    def test_disabled_source_requires_exact_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_provider_registry(directory, feeds=[
                self.feed(enabled_by_default=False, disabled_reason=""),
            ])
            with self.assertRaisesRegex(SourceConfigurationError, "requires a disabled_reason"):
                load_source_registry(path)

    def test_duplicate_source_identifiers_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_provider_registry(directory, feeds=[self.feed(), self.feed()])

            with self.assertRaisesRegex(SourceConfigurationError, "ids must be globally unique"):
                load_source_registry(path)

    def test_youtube_sources_require_unique_channels_and_verified_configuration(self):
        cases = (
            ([self.youtube_source(), self.youtube_source(id="youtube_other")], "channel ids must be unique"),
            ([self.youtube_source(youtube_channel_id="invalid")], "invalid youtube_channel_id"),
            ([self.youtube_source(allowed_hosts=["youtube.com"])], "must include its feed host"),
            ([self.youtube_source(homepage_url="https://www.youtube.com/watch?v=123")], "invalid YouTube homepage_url"),
            ([self.youtube_source(verification_date="invalid")], "invalid verification_date"),
            ([self.youtube_source(operational_notes="")], "invalid operational_notes"),
        )
        for sources, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                path = self.write_youtube_registry(directory, sources)
                with self.assertRaisesRegex(SourceConfigurationError, message):
                    load_source_registry(path)

    def test_disabled_youtube_source_requires_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_youtube_registry(directory, [
                self.youtube_source(enabled_by_default=False, disabled_reason=""),
            ])
            with self.assertRaisesRegex(SourceConfigurationError, "requires a disabled_reason"):
                load_source_registry(path)

    def test_schema_two_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps({"schema_version": 2, "sources": []}), encoding="utf-8")

            with self.assertRaisesRegex(SourceConfigurationError, "unsupported or missing schema"):
                load_source_registry(path)


class GoogleNewsAdapterTests(SimpleTestCase):
    def setUp(self):
        self.source = load_source_registry().get("google_news_country")

    def test_url_encodes_canonical_name_and_global_english_edition(self):
        url = build_feed_url(self.source, {"iso_a2": "RO", "name": "Romania"})
        parsed = urlsplit(url)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.hostname, "news.google.com")
        self.assertEqual(parse_qs(parsed.query), {
            "q": ['"Romania"'],
            "hl": ["en-US"],
            "gl": ["US"],
            "ceid": ["US:en"],
        })

    def test_ambiguous_name_uses_reviewed_country_query(self):
        url = build_feed_url(self.source, {"iso_a2": "GE", "name": "Georgia"})

        self.assertEqual(parse_qs(urlsplit(url).query)["q"], ['"Georgia" country'])


class RssAdapterTests(SimpleTestCase):
    def test_normalizes_plain_text_dates_publishers_and_safe_links(self):
        source = load_source_registry().get("google_news_country")
        feed = normalize_feed((FIXTURES / "google_news.xml").read_bytes(), source, max_items=10)

        self.assertEqual(len(feed.items), 2)
        self.assertEqual(feed.items[0].publisher, "Example Wire")
        self.assertEqual(feed.items[0].link, "https://news.google.com/rss/articles/first")
        self.assertEqual(feed.items[0].published_at.isoformat(), "2026-08-30T09:29:15+00:00")
        self.assertNotIn("<", feed.items[1].summary)
        self.assertEqual(feed.items[1].summary, "A short feed-provided summary.")

    def test_respects_item_limit(self):
        source = load_source_registry().get("google_news_country")
        feed = normalize_feed((FIXTURES / "google_news.xml").read_bytes(), source, max_items=1)

        self.assertEqual(len(feed.items), 1)

    def test_normalizes_atom_and_distinguishes_feed_source_from_item_publisher(self):
        registry = load_source_registry()
        provider = registry.get_provider("dw")
        source_feed = registry.get_feed("dw_all")
        feed = normalize_feed(
            (FIXTURES / "sample_atom.xml").read_bytes(),
            provider,
            max_items=10,
            feed=source_feed,
        )

        self.assertEqual(feed.items[0].provider_id, "dw")
        self.assertEqual(feed.items[0].provider_name, "DW")
        self.assertEqual(feed.items[0].feed_id, "dw_all")
        self.assertEqual(feed.items[0].contributing_sections, ("All News",))
        self.assertEqual(feed.items[0].publisher, "Item Publisher")
        self.assertEqual(feed.items[0].summary, "A short update.")

    def test_normalizes_rdf_and_uses_feed_source_as_publisher_fallback(self):
        registry = load_source_registry()
        provider = registry.get_provider("dw")
        feed = normalize_feed((FIXTURES / "sample_rdf.xml").read_bytes(), provider, max_items=10)

        self.assertEqual(len(feed.items), 1)
        self.assertEqual(feed.items[0].publisher, "DW")
        self.assertEqual(feed.items[0].published_at.isoformat(), "2026-08-30T08:00:00+00:00")

    def test_unsafe_summary_elements_do_not_contribute_text(self):
        source = load_source_registry().get("google_news_country")
        payload = b'''<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title><item>
            <title>Markets update</title><link>https://example.com/story</link>
            <description><![CDATA[Visible context.<script>Iran</script><style>UK</style>]]></description>
        </item></channel></rss>'''

        item = normalize_feed(payload, source, max_items=10).items[0]

        self.assertEqual(item.summary, "Visible context.")

    def test_raw_cache_value_excludes_country_specific_match_state(self):
        source = load_source_registry().get("google_news_country")
        item = normalize_feed((FIXTURES / "google_news.xml").read_bytes(), source, max_items=1).items[0]

        self.assertNotIn("matched_country_codes", item.as_cache_value())
        self.assertNotIn("match_evidence", item.as_cache_value())
        self.assertNotIn("match_class", item.as_cache_value())
        self.assertNotIn("is_stale", item.as_cache_value())