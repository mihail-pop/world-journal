from decimal import Decimal
import unicodedata
from urllib.parse import urlencode

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_http_methods

from core.views import render_page
from .facts import bundled_catalog, bundled_facts, local_snapshot, quantity_values
from .models import Country, CountryFavorite


def search_name(value):
    return "".join(char for char in unicodedata.normalize("NFD", value.casefold()) if not unicodedata.combining(char))


@require_http_methods(["GET"])
def index(request):
    catalog, _source = bundled_catalog()
    snapshot = local_snapshot()["countries"]
    favorites = set(CountryFavorite.objects.values_list("country_id", flat=True))
    options = {
        "q": request.GET.get("q", "")[:160],
        "sort": request.GET.get("sort", "name"),
        "order": request.GET.get("order", "asc"),
        "tab": request.GET.get("tab", "overview"),
        "country": request.GET.get("country", "").upper(),
    }
    if options["sort"] not in {"name", "population", "area"}:
        options["sort"] = "name"
    if options["order"] not in {"asc", "desc"}:
        options["order"] = "asc"
    if options["tab"] not in {"overview", "articles", "videos", "notes"}:
        options["tab"] = "overview"
    if options["country"] and options["country"] not in catalog:
        raise Http404("Country is not in the bundled catalog")
    rows = []
    for code, metadata in catalog.items():
        record = snapshot.get(code, {})
        row = {key: metadata[key] for key in ("iso_a2", "iso_a3", "name", "flag", "region", "subregion")}
        row["favorite"] = code in favorites
        for field in ("population", "area"):
            values = quantity_values(record, field)
            row[field] = float(Decimal(values[0]["amount"])) if values else None
            row[field + "_display"] = values[0]["display"] if values else ""
        rows.append(row)
    matching = [row for row in rows if search_name(options["q"]).strip() in search_name(f"{row['name']} {row['iso_a2']} {row['iso_a3']}")]
    matching.sort(key=lambda row: (row["name"].casefold(), row["iso_a2"]))
    if options["sort"] == "name":
        matching.sort(key=lambda row: row["name"].casefold(), reverse=options["order"] == "desc")
    else:
        known = [row for row in matching if row[options["sort"]] is not None]
        unknown = [row for row in matching if row[options["sort"]] is None]
        known.sort(key=lambda row: row[options["sort"]], reverse=options["order"] == "desc")
        matching = known + unknown
    directory_path = reverse("countries:index")
    for row in matching:
        row["directory_url"] = directory_path + "?" + urlencode({**options, "country": row["iso_a2"]})
    selected = catalog.get(options["country"])
    content = ""
    if selected:
        code, tab = options["country"], options["tab"]
        if tab == "overview":
            content = render_to_string("countries/partials/overview.html", {"facts": bundled_facts(code)}, request=request)
        elif tab == "notes":
            from .personal_views import country_notes_context
            content = render_to_string("countries/partials/notes.html", country_notes_context(get_object_or_404(Country, pk=code)), request=request)
        else:
            from news.services.background import feed_warmer
            from news.services.presentation import CachedDrawers
            feed_warmer.prioritize(code)
            content = CachedDrawers([code]).render(code, tab)
    return render_page(request, "countries", page_template="countries/index.html", context={
        "catalog": rows, "country_rows": matching,
        "favorite_rows": [row for row in matching if row["favorite"]], "has_favorites": bool(favorites),
        "options": options, "selected_country": selected,
        "selected_favorite": options["country"] in favorites, "country_content": mark_safe(content),
    })


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

