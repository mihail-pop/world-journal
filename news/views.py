from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .paging import NewsCursorError, page_changed
from .preferences import effective_registry
from .services.background import feed_warmer
from .services.country_news import CountryNotFoundError, _country_for_code
from .services.presentation import CachedDrawers
from .services.world_news import country_video_context


def _country_response(request, iso2, kind):
    try:
        code = _country_for_code(iso2)["iso_a2"]
        if request.headers.get("X-News-Paging") != "1":
            feed_warmer.prioritize(code)
        if kind == "videos":
            context = country_video_context(code, effective_registry(), request.GET)
            if page_changed(request, context["paging_version"]):
                return HttpResponse(status=409)
            response = render(request, "news/partials/country_videos.html", context)
        else:
            response = HttpResponse(CachedDrawers([code]).render(code, kind))
    except CountryNotFoundError as error:
        raise Http404(str(error)) from error
    except NewsCursorError:
        return HttpResponse("Refresh these news results to continue.", status=400)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@require_GET
def country_news(request: HttpRequest, iso2: str) -> HttpResponse:
    return _country_response(request, iso2, "articles")


@require_GET
def country_videos(request: HttpRequest, iso2: str) -> HttpResponse:
    return _country_response(request, iso2, "videos")
