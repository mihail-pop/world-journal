from decimal import Decimal
import unicodedata
from urllib.parse import urlencode

from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
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
        row = {key: metadata[key] for key in ("iso_a2", "iso_a3", "name", "flag", "flag_url", "flag_label", "region", "subregion")}
        row["is_custom"] = metadata.get("is_custom", False)
        row["favorite"] = code in favorites
        for field in ("population", "area"):
            values = quantity_values(record, field)
            row[field] = float(Decimal(values[0]["amount"])) if values else None
            row[field + "_display"] = values[0]["display"] if values else ""
        rows.append(row)
    sort = options["sort"]
    descending = options["order"] == "desc"
    rows.sort(key=lambda row: (search_name(row["name"]), row["iso_a2"]), reverse=sort == "name" and descending)
    if sort != "name":
        known = [row for row in rows if row[sort] is not None]
        unknown = [row for row in rows if row[sort] is None]
        known.sort(key=lambda row: row[sort], reverse=descending)
        rows = known + unknown
    query = search_name(options["q"]).strip()
    matching = [row for row in rows if query in search_name(f"{row['name']} {row['iso_a2']} {row['iso_a3']}")]
    candidates = matching or rows
    if not options["country"] and candidates:
        first = next((row for row in candidates if row["favorite"]), candidates[0])
        options["country"] = first["iso_a2"]
    directory_path = reverse("countries:index")
    for row in matching:
        row["directory_url"] = directory_path + "?" + urlencode({**options, "country": row["iso_a2"]})
    selected = catalog.get(options["country"])
    content = ""
    if selected:
        code, tab = options["country"], options["tab"]
        if tab == "overview":
            content = render_to_string("countries/partials/overview.html", overview_context(get_object_or_404(Country, pk=code)), request=request)
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
        "favorite_rows": [row for row in matching if row["favorite"]],
        "options": options, "selected_country": selected,
        "selected_favorite": options["country"] in favorites, "country_content": mark_safe(content),
    })


@never_cache
def country_metadata(request: HttpRequest) -> HttpResponse:
    catalog, source = bundled_catalog()
    snapshot = local_snapshot()["countries"]
    for code, row in catalog.items():
        if not row.get("is_custom"):
            continue
        for field in ("population", "area"):
            values = quantity_values(snapshot.get(code, {}), field)
            row[field] = float(Decimal(values[0]["amount"])) if values else None
            row[field + "_display"] = values[0]["display"] if values else ""
    return JsonResponse({"schema_version": 1, "source": source, "countries": list(catalog.values())})


@require_http_methods(["GET"])
@never_cache
def country_overview(request, iso2):
    country = get_object_or_404(Country, pk=iso2.upper())
    return render(request, "countries/partials/overview.html", overview_context(country))


def overview_context(country):
    from .personal_views import country_overview_context
    return {"facts": bundled_facts(country.pk), **country_overview_context(country)}

