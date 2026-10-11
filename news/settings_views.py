import json
from datetime import UTC, datetime
from urllib.parse import urlencode

from django.contrib import messages
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.views import render_page
from countries.models import Country

from .forms import NewsPreferencesForm
from .preferences import effective_registry, freshness_seconds, source_choices
from .registry import get_source_registry
from .services.cache import fixed_feed_cache_key, google_cache_key, parse_datetime, youtube_cache_key
from .services.country_news import get_country_news
from .services.regional_news import get_fixed_feed
from .services.youtube_news import get_youtube_feed
from .types import SourceKind


REGION_LABELS = {
    "middle_east": "Middle East", "asia_pacific": "Asia-Pacific", "europe": "Europe",
    "africa": "Africa", "north_america": "North America",
    "latin_america_caribbean": "Latin America and Caribbean",
}


def _country(request):
    code = request.POST.get("country", request.GET.get("country", "RO")).upper()
    return Country.objects.filter(pk=code).first() or Country.objects.first()


def _destination(country):
    return reverse("news:settings") + ("?" + urlencode({"country": country.pk}) if country else "")


def _navigate(request, country):
    url = _destination(country)
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse()
        response.headers["HX-Location"] = json.dumps({"path": url, "target": "#app-content", "swap": "innerHTML"})
        return response
    return redirect(url)


def _health(snapshot, enabled, fresh_seconds):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    attempted = parse_datetime(snapshot.get("last_attempt_at"))
    successful = parse_datetime(snapshot.get("fetched_at")) if snapshot.get("last_success_at") else None
    items = snapshot.get("items")
    count = len(items) if successful and isinstance(items, list) else None
    failed = bool(snapshot.get("last_error"))
    if not enabled:
        label = "Off"
    elif failed:
        label = "Last refresh failed" + (" · cached results retained" if successful else "")
    elif successful:
        age = (datetime.now(UTC) - successful).total_seconds()
        label = "Fresh cache" if age < fresh_seconds else "Refresh due"
        if count == 0:
            label += " · empty feed"
    else:
        label = "No retained check"
    return {
        "label": label, "failed": failed and enabled,
        "last_attempt": attempted, "last_success": successful, "item_count": count,
        "error_detail": snapshot.get("last_error_detail", "") if failed else "",
    }


def _context(registry, choices, form, country, fresh_seconds):
    effective = effective_registry(registry, choices)
    enabled = {item.id: item.enabled_by_default for item in (*effective.sources, *effective.providers, *effective.feeds)}
    keys = {feed.id: fixed_feed_cache_key(feed) for feed in registry.feeds}
    for source in registry.sources:
        if source.kind is SourceKind.YOUTUBE:
            keys[source.id] = youtube_cache_key(source)
        elif source.kind is SourceKind.DYNAMIC_COUNTRY_RSS and country:
            keys[source.id] = google_cache_key(source, country.pk)
    snapshots = cache.get_many(list(keys.values()))

    def row(item):
        return {
            "id": item.id, "toggle": form[f"enabled_{item.id}"],
            "name": getattr(item, "display_name", getattr(item, "section_label", item.id)),
            "homepage": getattr(item, "homepage_url", ""),
            "feed_url": item.youtube_feed_url if getattr(item, "kind", None) is SourceKind.YOUTUBE else getattr(item, "feed_url", ""),
            "notes": getattr(item, "operational_notes", ""),
            "region": REGION_LABELS.get(getattr(item, "editorial_region", ""), ""),
            "verification_date": getattr(item, "verification_date", None),
            "disabled_reason": getattr(item, "disabled_reason", "") or ("Unavailable in the curated configuration." if not item.enabled_by_default else ""),
            "enabled": enabled[item.id],
            "health": _health(snapshots.get(keys.get(item.id)), enabled[item.id], fresh_seconds),
        }

    providers = []
    for provider in sorted(registry.providers, key=lambda item: (item.display_priority, item.id)):
        provider_row = row(provider)
        provider_row["feeds"] = [row(feed) for feed in registry.feeds if feed.provider_id == provider.id]
        provider_row["enabled_feed_count"] = sum(feed["enabled"] for feed in provider_row["feeds"])
        providers.append(provider_row)
    return {
        "form": form, "country": country, "countries": Country.objects.all(),
        "google_sources": [row(source) for source in registry.sources if source.kind is SourceKind.DYNAMIC_COUNTRY_RSS],
        "youtube_sources": [row(source) for source in registry.sources if source.kind is SourceKind.YOUTUBE],
        "providers": providers,
    }


@never_cache
@require_http_methods(["GET", "POST"])
def source_settings(request):
    registry, choices, fresh_seconds = get_source_registry(), source_choices(), freshness_seconds()
    country = _country(request)
    form = NewsPreferencesForm(
        request.POST if request.method == "POST" else None,
        registry=registry, choices=choices, freshness=fresh_seconds,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        from .services.background import feed_warmer

        feed_warmer.rescan()
        messages.success(request, "News-source preferences saved. Background refresh and cached results now use these choices.")
        return _navigate(request, country)
    return render_page(request, "settings", page_template="news/settings.html", context=_context(registry, choices, form, country, fresh_seconds))


@never_cache
@require_http_methods(["POST"])
def refresh_source(request, source_id):
    registry = effective_registry()
    country = _country(request)
    sources = {source.id: source for source in registry.sources}
    feeds = {feed.id: feed for feed in registry.feeds}
    item = sources.get(source_id) or feeds.get(source_id)
    if item is None:
        raise Http404("Unknown source")
    if not item.enabled_by_default:
        messages.warning(request, "This source is switched off or unavailable. Save an enabled choice before refreshing it.")
        return _navigate(request, country)
    options = {"force_refresh": True, "fresh_seconds": freshness_seconds()}
    if source_id in feeds:
        result = get_fixed_feed(item, registry.get_provider(item.provider_id), **options)
        name = f"{registry.get_provider(item.provider_id).display_name} — {item.section_label}"
    elif item.kind is SourceKind.YOUTUBE:
        result = get_youtube_feed(item, **options)
        name = item.display_name
    elif item.kind is SourceKind.DYNAMIC_COUNTRY_RSS and country:
        result = get_country_news(country.pk, registry=registry, **options)
        name = f"{item.display_name} — {country.name}"
    else:
        raise Http404("Source cannot be refreshed here")
    error = result.error or getattr(result, "warning", "")
    if error or getattr(result, "refresh_failed", False):
        messages.warning(request, f"{name}: refresh failed. Previously cached results are kept where available.")
    else:
        messages.success(request, f"{name}: feed checked; {len(result.items)} entries cached.")
    return _navigate(request, country)
