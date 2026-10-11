from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def render_page(request: HttpRequest, page: str, *, page_template: str | None = None, context: dict | None = None) -> HttpResponse:
    from news.services.background import feed_warmer

    feed_warmer.start()
    page_context = {
        "active_page": page,
        "app_display_name": settings.APP_DISPLAY_NAME,
        "map_style_url": settings.MAP_STYLE_URL,
        "map_glyphs_url": settings.MAP_GLYPHS_URL,
        "map_terrain": settings.MAP_TERRAIN_CONFIG,
        "page_template": page_template or f"core/partials/{page}.html",
    }
    page_context.update(context or {})
    template_name = page_context["page_template"] if request.headers.get("HX-Request") == "true" else "core/app_shell.html"
    return render(request, template_name, page_context)


def map_page(request: HttpRequest) -> HttpResponse:
    return render_page(request, "map")


def journal_page(request: HttpRequest) -> HttpResponse:
    from journal.views import index
    return index(request)


def settings_page(request: HttpRequest) -> HttpResponse:
    if request.GET.get("section") == "information":
        return render_page(request, "settings", page_template="core/partials/information.html")
    return render_page(request, "settings")
