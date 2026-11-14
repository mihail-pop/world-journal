import json

import httpx
from django.conf import settings
from django.contrib.messages import get_messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

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
from .preferences import preferences_snapshot, save_preferences, validate_preferences


def render_page(request: HttpRequest, page: str, *, page_template: str | None = None, context: dict | None = None) -> HttpResponse:
    from news.services.background import feed_warmer

    feed_warmer.start()
    preferences = preferences_snapshot()
    page_context = {
        "active_page": page,
        "app_display_name": settings.APP_DISPLAY_NAME,
        "theme": preferences["theme"],
        "app_font": preferences["font"],
        "app_preferences": preferences,
        "map_style_url": settings.MAP_STYLE_URL,
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
    if request.headers.get("HX-Request") == "true":
        response.headers["HX-Trigger-After-Swap"] = json.dumps({"world-journal:app-preferences-loaded": preferences})
    return response


@never_cache
def player_page(request: HttpRequest) -> HttpResponse:
    return render(request, "core/player.html")


def map_page(request: HttpRequest) -> HttpResponse:
    from .place_search import map_search_target

    target = map_search_target(request.GET.get("place", ""), request.GET.get("country", ""))
    return render_page(request, "map", context={"map_search_target": target})


@require_GET
def place_search(request: HttpRequest) -> JsonResponse:
    from .place_search import search_places

    category = request.GET.get("type", "all")
    if category not in {"all", "countries", "capitals", "cities"}:
        return JsonResponse({"error": "Choose an available place type."}, status=400)
    return JsonResponse({"results": search_places(request.GET.get("q", ""), category)})


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
    saved = save_preferences({"theme": theme})
    if request.headers.get("Accept") == "application/json":
        return JsonResponse(preferences_snapshot(saved))
    return redirect("core:settings")


@never_cache
@require_http_methods(["GET", "POST"])
def preferences(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse(preferences_snapshot())
    try:
        values = validate_preferences(json.loads(request.body))
    except (ValueError, UnicodeDecodeError) as error:
        return JsonResponse({"error": str(error) or "Preferences could not be read."}, status=400)
    return JsonResponse(preferences_snapshot(save_preferences(values)))


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
