from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from .services.background import feed_warmer
from .services.country_news import CountryNotFoundError, _countries_by_code, _country_for_code
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
    response.headers["X-Feed-Version"] = drawers.version(code)
    return response


@require_GET
def country_news(request: HttpRequest, iso2: str) -> HttpResponse:
    return _country_response(request, iso2, "articles")


@require_GET
def country_videos(request: HttpRequest, iso2: str) -> HttpResponse:
    return _country_response(request, iso2, "videos")


@require_GET
def cached_drawers(request: HttpRequest) -> HttpResponse:
    feed_warmer.start()
    codes = list(dict.fromkeys(request.GET.get("countries", "").split(","))) if request.GET.get("countries") else []
    if len(codes) > 20:
        return JsonResponse({"error": "At most 20 countries per request."}, status=400)
    try:
        codes = [_country_for_code(code)["iso_a2"] for code in codes]
        if priority := request.GET.get("priority"):
            feed_warmer.prioritize(priority)
    except CountryNotFoundError as error:
        raise Http404(str(error)) from error
    versions = request.GET.get("versions", "").split(",")
    drawers = CachedDrawers(codes)
    records = {}
    for index, code in enumerate(codes):
        version = drawers.version(code)
        if index < len(versions) and versions[index] == version:
            continue
        records[code] = {
            "version": version,
            "articles": drawers.render(code, "articles"),
            "videos": drawers.render(code, "videos"),
        }
    response = JsonResponse({"countries": list(_countries_by_code()), "records": records, "warming": feed_warmer.busy()})
    response.headers["Cache-Control"] = "private, no-store"
    return response
