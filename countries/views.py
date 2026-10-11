from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_http_methods

from .facts import bundled_facts
from .models import Country


@cache_control(public=True, max_age=86400)
def country_metadata(request: HttpRequest) -> HttpResponse:
    return FileResponse(
        (settings.BASE_DIR / "data" / "countries.json").open("rb"),
        content_type="application/json",
    )


@require_http_methods(["GET"])
def country_overview(request, iso2):
    country = get_object_or_404(Country, pk=iso2.upper())
    return render(request, "countries/partials/overview.html", {"facts": bundled_facts(country.pk)})

