from datetime import UTC, datetime
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from news.registry import load_source_registry
from news.types import CountryNewsResult, NewsItem


class CountryNewsViewTests(TestCase):
    def test_country_news_renders_escaped_attributed_links(self):
        source = load_source_registry().get("google_news_country")
        result = CountryNewsResult(
            country_code="RO",
            country_name="Romania",
            source=source,
            items=(NewsItem(
                title='<script>alert("x")</script> Headline',
                link="https://news.google.com/rss/articles/example",
                publisher="Example Wire",
                published_at=datetime(2026, 8, 30, 9, 29, tzinfo=UTC),
                summary="A plain summary.",
            ),),
            fetched_at=datetime(2026, 8, 30, 10, 0, tzinfo=UTC),
        )

        with patch("news.views.get_country_news", return_value=result):
            response = self.client.get(reverse("news:country_news", args=["RO"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;", html=False)
        self.assertNotContains(response, "<script>", html=False)
        self.assertContains(response, 'target="_blank" rel="noopener noreferrer"')
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_unknown_country_returns_404_without_network_access(self):
        response = self.client.get(reverse("news:country_news", args=["ZZ"]))

        self.assertEqual(response.status_code, 404)