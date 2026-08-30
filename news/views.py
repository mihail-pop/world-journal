from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .services.country_news import CountryNotFoundError, get_country_news_page
from .services.youtube_news import get_country_videos


@require_GET
def country_news(request: HttpRequest, iso2: str) -> HttpResponse:
    try:
        result = get_country_news_page(
            iso2,
            retry_failed=request.GET.get("refresh") == "failed",
        )
    except CountryNotFoundError as error:
        raise Http404(str(error)) from error
    response = render(request, "news/partials/country_news.html", {"news_page": result})
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_GET
def country_videos(request: HttpRequest, iso2: str) -> HttpResponse:
    try:
        result = get_country_videos(
            iso2,
            retry_failed=request.GET.get("refresh") == "failed",
        )
    except CountryNotFoundError as error:
        raise Http404(str(error)) from error
    response = render(request, "news/partials/country_videos.html", {"video_page": result})
    response.headers["Cache-Control"] = "private, no-store"
    return response