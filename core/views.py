import json

import httpx
from django.conf import settings
from django.contrib.messages import get_messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from config.version import (
    APP_VERSION,
    CURRENT_RELEASE_URL,
    DISCUSSIONS_URL,
    ISSUES_URL,
    LATEST_RELEASE_API_URL,
    RELEASES_URL,
)
from countries.models import MapPreset, preset_groups

from .models import AppSettings


def render_page(request: HttpRequest, page: str, *, page_template: str | None = None, context: dict | None = None) -> HttpResponse:
    from news.services.background import feed_warmer

    feed_warmer.start()
    saved_theme = AppSettings.objects.filter(pk=1).values_list("theme", flat=True).first()
    page_context = {
        "active_page": page,
        "app_display_name": settings.APP_DISPLAY_NAME,
        "theme": saved_theme or AppSettings.Theme.DARK,
        "map_style_url": settings.MAP_STYLE_URL,
        "map_glyphs_url": settings.MAP_GLYPHS_URL,
        "map_terrain": settings.MAP_TERRAIN_CONFIG,
        "page_template": page_template or f"core/partials/{page}.html",
    }
    page_context.update(context or {})
    notices = [{"kind": message.level_tag, "message": str(message)} for message in get_messages(request)]
    if page_context.get("page_error"):
        notices.append({"kind": "error", "message": page_context["page_error"]})
    # The shell owns messages, including responses rendered during HTMX navigation.
    page_context["messages"] = []
    page_context["app_notices"] = notices
    template_name = page_context["page_template"] if request.headers.get("HX-Request") == "true" else "core/app_shell.html"
    response = render(request, template_name, page_context)
    if notices and request.headers.get("HX-Request") == "true":
        response.headers["HX-Trigger"] = json.dumps({"world-journal:server-notices": {"notices": notices}}, ensure_ascii=True)
    return response


def map_page(request: HttpRequest) -> HttpResponse:
    return render_page(request, "map")


def journal_page(request: HttpRequest) -> HttpResponse:
    from journal.views import index
    return index(request)


def settings_page(request: HttpRequest) -> HttpResponse:
    if request.GET.get("section") == "information":
        return render_page(
            request,
            "settings",
            page_template="core/partials/information.html",
            context={
                "app_version": APP_VERSION,
                "current_release_url": CURRENT_RELEASE_URL,
                "releases_url": RELEASES_URL,
                "issues_url": ISSUES_URL,
                "discussions_url": DISCUSSIONS_URL,
            },
        )
    preset_previews = []
    for preset in MapPreset.objects.prefetch_related("color_groups", "country_colors")[:3]:
        colors = [group["color"] for group in preset_groups(preset)]
        default_color = preset.default_color.lower()
        if default_color and default_color not in colors:
            colors.append(default_color)
        preset_previews.append({"name": preset.name, "colors": colors[:3]})
    return render_page(request, "settings", context={
        "theme_choices": AppSettings.Theme.choices,
        "preset_previews": preset_previews,
    })


@require_POST
def save_theme(request: HttpRequest) -> HttpResponse:
    theme = request.POST.get("theme")
    if theme not in AppSettings.Theme.values:
        return JsonResponse({"error": "Choose an available theme."}, status=400)
    AppSettings.objects.update_or_create(pk=1, defaults={"theme": theme})
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"theme": theme})
    return redirect("core:settings")


def version_info(request: HttpRequest) -> JsonResponse:
    try:
        response = httpx.get(
            LATEST_RELEASE_API_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": settings.NEWS_USER_AGENT},
            timeout=5,
        )
        response.raise_for_status()
        release = response.json()
        latest_version = str(release.get("tag_name") or "").strip()
        if not latest_version:
            raise ValueError("The latest GitHub release has no tag")
        latest_url = str(release.get("html_url") or f"{RELEASES_URL}/tag/{latest_version}")
        return JsonResponse({
            "current_version": APP_VERSION,
            "current_url": CURRENT_RELEASE_URL,
            "latest_version": latest_version,
            "latest_url": latest_url,
            "releases_url": RELEASES_URL,
            "is_latest": APP_VERSION.lstrip("v") == latest_version.lstrip("v"),
        })
    except (httpx.HTTPError, TypeError, ValueError):
        return JsonResponse({
            "current_version": APP_VERSION,
            "current_url": CURRENT_RELEASE_URL,
            "latest_version": None,
            "latest_url": RELEASES_URL,
            "releases_url": RELEASES_URL,
            "is_latest": None,
        })
