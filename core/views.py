from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def render_page(request: HttpRequest, page: str) -> HttpResponse:
    context = {
        "active_page": page,
        "app_display_name": settings.APP_DISPLAY_NAME,
        "page_template": f"core/partials/{page}.html",
    }
    template_name = context["page_template"] if request.headers.get("HX-Request") == "true" else "core/app_shell.html"
    return render(request, template_name, context)


def map_page(request: HttpRequest) -> HttpResponse:
    return render_page(request, "map")


def journal_page(request: HttpRequest) -> HttpResponse:
    return render_page(request, "journal")


def settings_page(request: HttpRequest) -> HttpResponse:
    return render_page(request, "settings")