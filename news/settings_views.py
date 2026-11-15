import json
from urllib.parse import urlencode

from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.database import database_write, write_transaction
from core.views import render_page
from countries.models import Country

from .cache_backend import CacheWriteError
from .forms import AdditionalFeedForm, CustomSourceForm, NewsPreferencesForm, single_feed_providers
from .models import CustomSource, FeedState, NewsPreferences, SourcePreference
from .preferences import effective_registry, freshness_seconds, source_choices
from .registry import get_source_registry
from .services.cache import fixed_feed_cache_key, google_cache_key, parse_datetime, youtube_cache_key
from .services.country_news import get_country_news
from .services.regional_news import get_fixed_feed
from .services.youtube_news import get_youtube_feed
from .services.custom_sources import check_custom_source, registry_items, with_custom_sources
from .services.background import feed_warmer
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


def _refresh_progress():
    feed_warmer.start()
    result = feed_warmer.status()
    if result["busy"]:
        summary = f"Updating news · {result['completed']} of {result['total']}" if result["total"] else "Updating news…"
    elif not result["enabled"]:
        summary = "Choose a source below"
    elif result["failed"]:
        summary = f"{result['failed']} source{' needs' if result['failed'] == 1 else 's need'} attention"
    elif result["missing"]:
        summary = f"Waiting for {result['missing']} update{'s' if result['missing'] != 1 else ''}"
    else:
        summary = "Ready to read"
    return {
        **result, "summary": summary, "progress_max": max(1, result["total"]),
        "progress_value": result["completed"] if result["total"] else int(not result["busy"] and not result["missing"]),
        "current_label": (" · ".join(result["current"]) or "Getting the next update…") if result["busy"] else "",
    }


def _context(registry, choices, form, country):
    effective = effective_registry(registry, choices)
    enabled = {item.id: item.enabled_by_default for item in (*effective.sources, *effective.providers, *effective.feeds)}
    custom_records = list(CustomSource.objects.select_related("parent"))
    custom_keys = {}
    for record in custom_records:
        item, feed = registry_items(record)
        custom_keys[record.pk] = fixed_feed_cache_key(feed) if feed else youtube_cache_key(item)
    attempts = {
        key: parse_datetime(metadata.get("last_attempt_at"))
        for key, metadata in FeedState.objects.filter(
            cache_key__in=custom_keys.values(), expires_at__gt=timezone.now(),
        ).values_list("cache_key", "metadata")
    }

    def check_error(record):
        attempted = attempts.get(custom_keys[record.pk])
        return record.last_error if record.last_error and (
            not attempted or not record.last_checked_at or record.last_checked_at >= attempted
        ) else ""

    def row(item):
        return {
            "id": item.id, "toggle": form[f"enabled_{item.id}"],
            "name": getattr(item, "display_name", getattr(item, "section_label", item.id)),
            "homepage": getattr(item, "homepage_url", ""),
            "region": REGION_LABELS.get(getattr(item, "editorial_region", ""), ""),
            "enabled": enabled[item.id],
            "available": item.enabled_by_default,
        }

    providers = []
    for provider in sorted((provider for provider in registry.providers if not provider.id.startswith("custom_")), key=lambda item: (item.display_priority, item.id)):
        provider_row = row(provider)
        provider_row["feeds"] = [row(feed) for feed in registry.feeds if feed.provider_id == provider.id]
        if len(provider_row["feeds"]) == 1:
            provider_row["enabled"] &= provider_row["feeds"][0]["enabled"]
            provider_row["available"] &= provider_row["feeds"][0]["available"]
        providers.append(provider_row)
    custom_rows = []
    for record in (record for record in custom_records if not record.parent_id):
        item, feed = registry_items(record)
        if feed:
            item = registry.get_provider(item.id)
        source_row = row(item)
        source_row.update(record=record, feeds=[], check_error=check_error(record))
        if feed:
            for child in (child for child in custom_records if child.pk == record.pk or child.parent_id == record.pk):
                _provider, child_feed = registry_items(child)
                feed_row = row(registry.get_feed(child_feed.id))
                feed_row.update(record=child, check_error=check_error(child))
                source_row["feeds"].append(feed_row)
            source_row["add_feed_form"] = AdditionalFeedForm(prefix=f"feed-{record.pk}")
            if len(source_row["feeds"]) == 1:
                source_row["enabled"] &= source_row["feeds"][0]["enabled"]
                source_row["available"] &= source_row["feeds"][0]["available"]
        custom_rows.append(source_row)
    return {
        "refresh_status": _refresh_progress(),
        "form": form, "country": country, "countries": Country.objects.all(),
        "google_sources": [row(source) for source in registry.sources if source.kind is SourceKind.DYNAMIC_COUNTRY_RSS],
        "youtube_sources": [row(source) for source in registry.sources if source.kind is SourceKind.YOUTUBE and not source.id.startswith("custom_")],
        "providers": providers,
        "custom_sources": custom_rows, "custom_form": CustomSourceForm(),
        "custom_news_sources": [row for row in custom_rows if row["record"].kind == CustomSource.Kind.RSS],
        "custom_youtube_sources": [row for row in custom_rows if row["record"].kind == CustomSource.Kind.YOUTUBE],
    }


@never_cache
@require_http_methods(["GET", "POST"])
def source_settings(request):
    registry, choices, fresh_seconds = with_custom_sources(get_source_registry()), source_choices(), freshness_seconds()
    country = _country(request)
    form = NewsPreferencesForm(
        request.POST if request.method == "POST" else None,
        registry=registry, choices=choices, freshness=fresh_seconds,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        from .services.background import feed_warmer

        feed_warmer.rescan()
        feed_warmer.trim_archive()
        messages.success(request, "News-source preferences saved. Background refresh and cached results now use these choices.")
        return _navigate(request, country)
    return render_page(request, "settings", page_template="news/settings.html", context=_context(registry, choices, form, country))


@never_cache
@require_http_methods(["POST"])
def save_preference(request):
    """Persist one control, so quick changes never overwrite unrelated choices."""
    registry = with_custom_sources(get_source_registry())
    preference = request.POST.get("field")
    if preference in {"freshness_minutes", "archive_storage_mb"}:
        try:
            value = NewsPreferencesForm.base_fields[preference].clean(request.POST.get("value"))
        except ValidationError:
            message = "Choose 500 MB, 1 GB or 2 GB." if preference == "archive_storage_mb" else "Choose a refresh interval of 2, 4, 6, 8, 10 or 12 hours."
            return JsonResponse({"error": message}, status=400)
        with database_write():
            NewsPreferences.objects.update_or_create(pk=1, defaults={preference: value})
    else:
        identity = request.POST.get("source_id")
        item = next((item for item in (*registry.sources, *registry.providers, *registry.feeds) if item.id == identity), None)
        if item is None or not item.enabled_by_default:
            return JsonResponse({"error": "Check this source successfully before enabling it."}, status=400)
        value = request.POST.get("value")
        if value not in {"true", "false"}:
            return JsonResponse({"error": "Invalid source choice."}, status=400)
        related_feed_id = single_feed_providers(registry).get(identity)
        if related_feed_id and not registry.get_feed(related_feed_id).enabled_by_default:
            return JsonResponse({"error": "This source is not available right now."}, status=400)
        with write_transaction():
            SourcePreference.objects.update_or_create(source_id=identity, defaults={"enabled": value == "true"})
            if related_feed_id:
                SourcePreference.objects.update_or_create(source_id=related_feed_id, defaults={"enabled": value == "true"})
    from .services.background import feed_warmer

    if preference == "archive_storage_mb":
        feed_warmer.trim_archive()
    else:
        feed_warmer.rescan()
    choices, interval = source_choices(), freshness_seconds()
    form = NewsPreferencesForm(registry=registry, choices=choices, freshness=interval)
    context = _context(registry, choices, form, _country(request))
    rows = [*context["google_sources"], *context["youtube_sources"], *context["custom_sources"]]
    for source in context["custom_sources"]:
        rows.extend(source["feeds"])
    for provider in context["providers"]:
        rows.extend((provider, *provider["feeds"]))
    return JsonResponse({"states": {row["id"]: {"enabled": row["enabled"], "label": "Connected" if row["enabled"] else "Off", "failed": False} for row in rows}})


@never_cache
@require_http_methods(["GET"])
def refresh_status(request):
    return JsonResponse(_refresh_progress())


@never_cache
@require_http_methods(["POST"])
def refresh_all(request):
    feed_warmer.refresh_all()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"queued": True})
    messages.success(request, "All enabled feeds are refreshing in the background.")
    return _navigate(request, _country(request))


@never_cache
@require_http_methods(["POST"])
def add_publisher_feed(request, source_id):
    publisher = get_object_or_404(CustomSource, pk=source_id, kind=CustomSource.Kind.RSS, parent=None)
    form = AdditionalFeedForm(request.POST, prefix=f"feed-{publisher.pk}")
    if form.is_valid():
        record = CustomSource(parent=publisher, kind=CustomSource.Kind.RSS, url=form.cleaned_data["location"], name=form.cleaned_data["name"])
        success = check_custom_source(record)
        record.save()
        feed_warmer.rescan()
        if success:
            messages.success(request, "Feed added to this publisher and checked.")
        else:
            messages.warning(request, "Feed saved, but it could not be reached. Check the message below and try again.")
        return _navigate(request, _country(request))
    country = _country(request)
    registry, choices, interval = with_custom_sources(get_source_registry()), source_choices(), freshness_seconds()
    preferences_form = NewsPreferencesForm(registry=registry, choices=choices, freshness=interval)
    context = _context(registry, choices, preferences_form, country)
    for row in context["custom_sources"]:
        if row["record"].pk == publisher.pk:
            row["add_feed_form"] = form
    return render_page(request, "settings", page_template="news/settings.html", context=context)


@never_cache
@require_http_methods(["POST"])
def add_custom_source(request):
    form = CustomSourceForm(request.POST)
    if not form.is_valid():
        country = _country(request)
        registry, choices, interval = with_custom_sources(get_source_registry()), source_choices(), freshness_seconds()
        preferences_form = NewsPreferencesForm(registry=registry, choices=choices, freshness=interval)
        context = _context(registry, choices, preferences_form, country)
        context["custom_form"] = form
        return render_page(request, "settings", page_template="news/settings.html", context=context)
    record = CustomSource(kind=form.cleaned_data["kind"], url=form.cleaned_data["location"], name=form.cleaned_data["name"])
    success = check_custom_source(record)
    record.save()
    from .services.background import feed_warmer

    feed_warmer.rescan()
    if success:
        messages.success(request, "Source added and checked.")
    else:
        messages.warning(request, "Source saved, but its check failed. See the reason below; it stays paused until a successful check.")
    return _navigate(request, _country(request))


@never_cache
@require_http_methods(["POST"])
def custom_source_action(request, source_id, action):
    record = get_object_or_404(CustomSource, pk=source_id)
    from .services.background import feed_warmer

    if action == "remove":
        records = [record, *record.extra_feeds.all()]
        identities, keys = [], []
        for removed in records:
            item, feed = registry_items(removed)
            identities.extend((removed.registry_id, f"{removed.registry_id}_feed"))
            keys.append(fixed_feed_cache_key(feed) if feed else youtube_cache_key(item))
        SourcePreference.objects.filter(source_id__in=identities).delete()
        record.delete()
        cache.delete_many(keys)
        with database_write():
            FeedState.objects.filter(cache_key__in=keys).delete()
        from .services.archive import remove_origins
        remove_origins(identities)
        messages.success(request, "Custom source removed. Saved journal entries are kept.")
    elif action == "check":
        success = check_custom_source(record)
        record.save()
        if success:
            messages.success(request, "Source checked.")
        else:
            messages.warning(request, f"Source check failed: {record.last_error}")
    else:
        raise Http404("Unknown source action")
    feed_warmer.rescan()
    return _navigate(request, _country(request))


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
        messages.warning(request, "This source is switched off or unavailable. Turn it on before refreshing it.")
        return _navigate(request, country)
    options = {"force_refresh": True, "fresh_seconds": freshness_seconds()}
    try:
        if source_id in feeds:
            provider = registry.get_provider(item.provider_id)
            result = get_fixed_feed(item, provider, **options)
            name = f"{provider.display_name} — {item.section_label}"
        elif item.kind is SourceKind.YOUTUBE:
            result = get_youtube_feed(item, **options)
            name = item.display_name
        elif item.kind is SourceKind.DYNAMIC_COUNTRY_RSS and country:
            result = get_country_news(country.pk, registry=registry, **options)
            name = f"{item.display_name} — {country.name}"
        else:
            raise Http404("Source cannot be refreshed here")
    except CacheWriteError:
        messages.warning(request, "The feed cache could not be saved. Try refreshing again in a moment.")
        return _navigate(request, country)
    if source_id in feeds:
        job, key = ("rss", source_id), fixed_feed_cache_key(item)
    elif item.kind is SourceKind.YOUTUBE:
        job, key = ("youtube", source_id), youtube_cache_key(item)
    else:
        job, key = ("google", country.pk), google_cache_key(item, country.pk)
    from .services.archive import capture_snapshot
    capture_snapshot(job, cache.get(key), registry)
    feed_warmer.rescan()
    error = result.error or getattr(result, "warning", "")
    if error or getattr(result, "refresh_failed", False):
        messages.warning(request, f"{name}: refresh failed. Previously cached results are kept where available.")
    else:
        messages.success(request, f"{name}: feed checked; {len(result.items)} entries cached.")
    return _navigate(request, country)
