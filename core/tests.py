from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse


class ShellNavigationTests(TestCase):
    routes = (
        ("core:map", "map"),
        ("core:journal", "journal"),
        ("core:settings", "settings"),
    )

    def test_direct_requests_return_complete_documents(self):
        for route_name, page in self.routes:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "core/app_shell.html")
                self.assertTemplateUsed(response, f"core/partials/{page}.html")
                self.assertContains(response, "<!doctype html>", html=False)
                self.assertContains(response, 'data-app-name="World Journal"')
                self.assertContains(response, 'id="app-content"')
                self.assertContains(response, 'id="persistent-player"')
                self.assertContains(response, f'data-page="{page}"')

    def test_htmx_requests_return_only_page_partials(self):
        for route_name, page in self.routes:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name), headers={"HX-Request": "true"})

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, f"core/partials/{page}.html")
                self.assertTemplateNotUsed(response, "core/app_shell.html")
                self.assertContains(response, f'data-page="{page}"')
                self.assertNotContains(response, "<!doctype html>", html=False)
                self.assertNotContains(response, 'id="app-content"')
                self.assertNotContains(response, 'id="persistent-player"')

    def test_shell_navigation_supports_htmx_and_normal_links(self):
        response = self.client.get(reverse("core:map"))

        self.assertContains(response, 'hx-boost="true"')
        self.assertContains(response, 'hx-target="#app-content"')
        self.assertContains(response, 'hx-push-url="true"')
        self.assertContains(response, "hx-history-elt")
        for route_name, _page in self.routes:
            self.assertContains(response, f'href="{reverse(route_name)}"')

    def test_map_page_references_local_map_assets_and_configured_provider(self):
        response = self.client.get(reverse("core:map") + "?country=RO")

        self.assertContains(response, "/static/vendor/maplibre-gl/maplibre-gl.css")
        self.assertContains(response, "/static/data/countries.geojson")
        self.assertContains(response, "/static/data/capitals.geojson")
        self.assertContains(response, "/data/countries.json")
        self.assertContains(response, 'data-country-news-url-template="/news/countries/COUNTRY_CODE/"')
        self.assertContains(response, 'data-map-style-url="https://tiles.openfreemap.org/styles/liberty"')
        self.assertContains(response, 'data-map-glyphs-url="https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf"')
        self.assertContains(response, 'data-terrain-available="false"')
        self.assertContains(response, 'id="world-map"')
        self.assertContains(response, "data-country-drawer")
        self.assertContains(response, "data-country-news-content")
        self.assertContains(response, "Loading current English-language headlines")
        self.assertContains(response, "data-home-view")
        self.assertContains(response, "data-map-controls-toggle")
        self.assertContains(response, 'data-map-preference="simpleMode"')

    def test_htmx_map_response_keeps_map_markup_inside_partial_boundary(self):
        response = self.client.get(reverse("core:map"), headers={"HX-Request": "true"})

        self.assertContains(response, 'id="world-map"')
        self.assertContains(response, "/static/data/countries.geojson")
        self.assertNotContains(response, "/static/vendor/maplibre-gl/maplibre-gl.css")
        self.assertNotContains(response, 'id="app-content"')

    def test_settings_page_renders_home_country_from_canonical_metadata(self):
        response = self.client.get(reverse("core:settings"))

        self.assertContains(response, 'data-page="settings"')
        self.assertContains(response, 'data-country-metadata-url="/data/countries.json"')
        self.assertContains(response, 'data-home-country-select')
        self.assertContains(response, '<option value="">No home country</option>', html=True)

    def test_htmx_settings_response_preserves_home_country_configuration(self):
        response = self.client.get(
            reverse("core:settings"), headers={"HX-Request": "true"}
        )

        self.assertContains(response, 'data-home-country-select')
        self.assertNotContains(response, "<!doctype html>", html=False)

    def test_all_map_browser_assets_are_local(self):
        assets = (
            "js/map_preferences.js",
            "js/pages/map.js",
            "js/pages/settings.js",
            "data/countries.geojson",
            "data/capitals.geojson",
            "vendor/maplibre-gl/maplibre-gl.mjs",
            "vendor/maplibre-gl/maplibre-gl-shared.mjs",
            "vendor/maplibre-gl/maplibre-gl-worker.mjs",
            "vendor/maplibre-gl/maplibre-gl.css",
            "vendor/maplibre-gl/LICENSE.txt",
            "vendor/maplibre-gl/VERSION.txt",
        )

        for asset in assets:
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(asset))