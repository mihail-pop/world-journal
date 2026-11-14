from django.http import Http404, HttpRequest, HttpResponse
from django.views.decorators.http import require_GET

from .services.background import feed_warmer
from .services.country_news import CountryNotFoundError, _country_for_code
from .services.presentation import CachedDrawers


def _country_response(request, iso2, kind):
    try:
        code = _country_for_code(iso2)["iso_a2"]
        feed_warmer.prioritize(code, retry=request.GET.get("refresh") == "failed")
        drawers = CachedDrawers([code])
    except CountryNotFoundError as error:
        raise Http404(str(error)) from error
    response = HttpResponse(drawers.render(code, kind))
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_GET
def country_news(request: HttpRequest, iso2: str) -> HttpResponse:
    return _country_response(request, iso2, "articles")


@require_GET
def country_videos(request: HttpRequest, iso2: str) -> HttpResponse:
    return _country_response(request, iso2, "videos")
