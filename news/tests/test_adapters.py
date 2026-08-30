import json
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from django.test import SimpleTestCase

from news.adapters.google_news import build_feed_url
from news.adapters.rss import normalize_feed
from news.registry import SourceConfigurationError, load_source_registry


FIXTURES = Path(__file__).parent / "fixtures"


class SourceRegistryTests(SimpleTestCase):
    def test_active_registry_contains_only_google_country_rss(self):
        registry = load_source_registry()

        self.assertEqual([source.id for source in registry.sources], ["google_news_country"])
        self.assertTrue(registry.sources[0].enabled_by_default)
        self.assertEqual(registry.sources[0].feed_host, "news.google.com")

    def test_unknown_fields_fail_validation(self):
        value = {
            "schema_version": 1,
            "sources": [{
                "id": "bad_source",
                "kind": "fixed_rss",
                "display_name": "Bad",
                "homepage_url": "https://example.com/",
                "feed_url": "https://example.com/feed.xml",
                "coverage_regions": ["europe"],
                "language": "en",
                "enabled_by_default": False,
                "unexpected": True,
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaisesRegex(SourceConfigurationError, "invalid fields"):
                load_source_registry(path)

    def test_non_https_source_url_fails_validation(self):
        value = {
            "schema_version": 1,
            "sources": [{
                "id": "bad_source",
                "kind": "fixed_rss",
                "display_name": "Bad",
                "homepage_url": "https://example.com/",
                "feed_url": "http://example.com/feed.xml",
                "coverage_regions": ["europe"],
                "language": "en",
                "enabled_by_default": False,
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaisesRegex(SourceConfigurationError, "must be an HTTPS URL"):
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