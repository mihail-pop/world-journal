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