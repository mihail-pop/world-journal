from datetime import UTC, datetime
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from news.registry import load_source_registry
from news.services.country_news import CountryNotFoundError
from news.types import (
    CountryNewsPage,
    CountryNewsResult,
    CountryVideosPage,
    NewsItem,
    RegionalProviderResult,
    VideoItem,
    VideoSourceResult,
)


class CountryNewsViewTests(TestCase):
    def test_country_news_renders_escaped_attributed_links(self):
        source = load_source_registry().get("google_news_country")
        regional_provider = load_source_registry().get_provider("dw")
        google = CountryNewsResult(
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
        regional_item = NewsItem(
            title="Regional <img src=x onerror=alert(1)> headline",
            link="https://example.com/regional",
            publisher="Example Publisher",
            published_at=datetime(2026, 8, 30, 8, 0, tzinfo=UTC),
            provider_id="dw",
            provider_name="DW",
            feed_id="dw_all",
            feed_section="All News",
            contributing_sections=("All News",),
            match_class="headline_country",
        )
        result = CountryNewsPage(
            country_code="RO",
            country_name="Romania",
            google=google,
            regional_items=(regional_item,),
            regional_sources=(RegionalProviderResult(
                regional_provider,
                (regional_item,),
                enabled_feed_count=1,
                successful_feed_count=1,
                failed_feed_count=0,
            ),),
        )

        with patch("news.views.get_country_news_page", return_value=result):
            response = self.client.get(reverse("news:country_news", args=["RO"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;", html=False)
        self.assertNotContains(response, "<script>", html=False)
        self.assertContains(response, "&lt;img src=x onerror=alert(1)&gt;", html=False)
        self.assertContains(response, 'target="_blank" rel="noopener noreferrer"')
        self.assertContains(response, 'role="group" aria-label="Article source filter"')
        self.assertContains(response, 'data-news-filter="all" aria-pressed="true"')
        self.assertContains(response, 'data-news-section="google"')
        self.assertContains(response, 'data-news-section="regional"')
        self.assertContains(response, 'class="news-source-badge">DW</span>')
        self.assertContains(response, 'class="news-section-label">All News</span>')
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_retry_parameter_targets_failed_sources(self):
        with patch("news.views.get_country_news_page") as get_page:
            get_page.return_value = CountryNewsPage(
                country_code="RO",
                country_name="Romania",
                google=CountryNewsResult(
                    "RO", "Romania", load_source_registry().get("google_news_country"), (), None
                ),
                regional_items=(),
                regional_sources=(),
            )

            self.client.get(reverse("news:country_news", args=["RO"]) + "?refresh=failed")

        get_page.assert_called_once_with("RO", retry_failed=True)

    def test_unknown_country_returns_404_without_network_access(self):
        response = self.client.get(reverse("news:country_news", args=["ZZ"]))

        self.assertEqual(response.status_code, 404)


class CountryVideosViewTests(TestCase):
    def setUp(self):
        self.source = load_source_registry().get("youtube_dw_news")
        self.item = VideoItem(
            source_id=self.source.id,
            channel_name='DW News <script>alert("channel")</script>',
            video_id="AbCdEfGhI01",
            title='<script>alert("title")</script> Germany update',
            published_at=datetime(2026, 8, 30, 9, 29, tzinfo=UTC),
            watch_url="https://www.youtube.com/watch?v=AbCdEfGhI01",
            embed_url="https://www.youtube-nocookie.com/embed/AbCdEfGhI01",
            thumbnail_url="https://i.ytimg.com/vi/AbCdEfGhI01/hqdefault.jpg",
        )

    def test_country_videos_renders_escaped_validated_playback_data(self):
        result = CountryVideosPage(
            "DE",
            "Germany",
            (self.item,),
            (VideoSourceResult(self.source, (self.item,), self.item.published_at),),
            "success",
        )

        with patch("news.views.get_country_videos", return_value=result):
            response = self.client.get(reverse("news:country_videos", args=["de"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-video-id="AbCdEfGhI01"')
        self.assertContains(response, "&lt;script&gt;", html=False)
        self.assertNotContains(response, "<script>", html=False)
        self.assertNotContains(response, "youtube-nocookie.com", html=False)
        self.assertContains(response, 'target="_blank" rel="noopener noreferrer"')
        self.assertContains(response, 'referrerpolicy="no-referrer"')
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_invalid_country_returns_404(self):
        with patch("news.views.get_country_videos", side_effect=CountryNotFoundError("unknown")):
            response = self.client.get(reverse("news:country_videos", args=["ZZ"]))

        self.assertEqual(response.status_code, 404)

    def test_country_videos_is_get_only(self):
        response = self.client.post(reverse("news:country_videos", args=["DE"]))

        self.assertEqual(response.status_code, 405)