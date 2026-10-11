import json
from datetime import UTC, datetime
from urllib.parse import urlencode

from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.views import render_page
from countries.models import Country

from .forms import AdditionalFeedForm, CustomSourceForm, NewsPreferencesForm
from .models import CustomSource, NewsPreferences, SourcePreference
from .preferences import effective_registry, freshness_seconds, source_choices
from .registry import get_source_registry
from .services.cache import fixed_feed_cache_key, google_cache_key, google_pause_until, parse_datetime, youtube_cache_key
from .services.country_news import get_country_news
from .services.regional_news import get_fixed_feed
from .services.youtube_news import get_youtube_feed
from .services.custom_sources import check_custom_source, format_label, registry_items, with_custom_sources
from .services.background import feed_jobs, feed_warmer
from .services.country_news import _countries_by_code
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
            "available": item.enabled_by_default,
            "health": _health(snapshots.get(keys.get(item.id)), enabled[item.id], fresh_seconds),
        }

    providers = []
    for provider in sorted((provider for provider in registry.providers if not provider.id.startswith("custom_")), key=lambda item: (item.display_priority, item.id)):
        provider_row = row(provider)
        provider_row["feeds"] = [row(feed) for feed in registry.feeds if feed.provider_id == provider.id]
        provider_row["enabled_feed_count"] = sum(feed["enabled"] for feed in provider_row["feeds"])
        providers.append(provider_row)
    custom_rows = []
    custom_records = list(CustomSource.objects.select_related("parent"))
    for record in (record for record in custom_records if not record.parent_id):
        item, feed = registry_items(record)
        if feed:
            item = registry.get_provider(item.id)
        source_row = row(item)
        source_row.update({"record": record, "format": format_label(record.feed_format), "feed_url": record.url, "feeds": []})
        if feed:
            source_row["health"] = _health(snapshots.get(keys[feed.id]), enabled[feed.id], fresh_seconds)
            for child in (child for child in custom_records if child.pk == record.pk or child.parent_id == record.pk):
                _provider, child_feed = registry_items(child)
                feed_row = row(registry.get_feed(child_feed.id))
                child_attempt = feed_row["health"]["last_attempt"]
                child_error = child.last_error if child.last_error and (not child_attempt or not child.last_checked_at or child.last_checked_at >= child_attempt) else ""
                feed_row.update(record=child, format=format_label(child.feed_format), check_error=child_error)
                source_row["feeds"].append(feed_row)
            source_row["add_feed_form"] = AdditionalFeedForm(prefix=f"feed-{record.pk}")
        health = source_row["health"]
        check_error = record.last_error if record.last_error and (
            not health["last_attempt"] or not record.last_checked_at or record.last_checked_at >= health["last_attempt"]
        ) else ""
        source_row["check_error"] = check_error
        if check_error and source_row["enabled"]:
            health.update(label="Last check failed · cached results retained", failed=True)
        if not item.enabled_by_default:
            health.update(label="Check failed · paused", failed=True)
        custom_rows.append(source_row)
    return {
        "form": form, "country": country, "countries": Country.objects.all(),
        "google_sources": [row(source) for source in registry.sources if source.kind is SourceKind.DYNAMIC_COUNTRY_RSS],
        "youtube_sources": [row(source) for source in registry.sources if source.kind is SourceKind.YOUTUBE and not source.id.startswith("custom_")],
        "providers": providers,
        "custom_sources": custom_rows, "custom_form": CustomSourceForm(),
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
        messages.success(request, "News-source preferences saved. Background refresh and cached results now use these choices.")
        return _navigate(request, country)
    return render_page(request, "settings", page_template="news/settings.html", context=_context(registry, choices, form, country, fresh_seconds))


@never_cache
@require_http_methods(["POST"])
def save_preference(request):
    """Persist one control, so quick changes never overwrite unrelated choices."""
    registry = with_custom_sources(get_source_registry())
    if request.POST.get("field") == "freshness_minutes":
        try:
            value = NewsPreferencesForm.base_fields["freshness_minutes"].clean(request.POST.get("value"))
        except ValidationError:
            return JsonResponse({"error": "Choose a refresh interval of 6, 8, 10 or 12 hours."}, status=400)
        NewsPreferences.objects.update_or_create(pk=1, defaults={"freshness_minutes": value})
    else:
        identity = request.POST.get("source_id")
        item = next((item for item in (*registry.sources, *registry.providers, *registry.feeds) if item.id == identity), None)
        if item is None or not item.enabled_by_default:
            return JsonResponse({"error": "Check this source successfully before enabling it."}, status=400)
        value = request.POST.get("value")
        if value not in {"true", "false"}:
            return JsonResponse({"error": "Invalid source choice."}, status=400)
        SourcePreference.objects.update_or_create(source_id=identity, defaults={"enabled": value == "true"})
    from .services.background import feed_warmer

    feed_warmer.rescan()
    choices, interval = source_choices(), freshness_seconds()
    form = NewsPreferencesForm(registry=registry, choices=choices, freshness=interval)
    context = _context(registry, choices, form, _country(request), interval)
    rows = [*context["google_sources"], *context["youtube_sources"], *context["custom_sources"]]
    for source in context["custom_sources"]:
        rows.extend(source["feeds"])
    for provider in context["providers"]:
        rows.extend((provider, *provider["feeds"]))
    return JsonResponse({"states": {row["id"]: {"enabled": row["enabled"], "label": "Connected" if row["enabled"] else "Off", "failed": False} for row in rows}})


@never_cache
@require_http_methods(["GET"])
def refresh_status(request):
    feed_warmer.start()
    registry = effective_registry()
    jobs = tuple(feed_jobs(registry))
    snapshots = cache.get_many([key for _job, key in jobs])
    providers = {provider.id: provider for provider in registry.providers}
    feeds = {feed.id: feed for feed in registry.feeds}
    sources = {source.id: source for source in registry.sources}

    def label(job):
        kind, identity = job
        if kind == "google":
            return "Google News · World headlines" if identity == "WORLD" else f"Google News · {_countries_by_code()[identity]['name']}"
        if kind == "rss" and identity in feeds:
            feed = feeds[identity]
            return f"{providers[feed.provider_id].display_name} · {feed.section_label}"
        if identity in sources:
            return sources[identity].display_name
        return "Updating sources"

    progress = feed_warmer.progress()
    progress["current"] = [label(job) for job in progress.pop("running")]
    errors = []
    paused_until = google_pause_until(cache, datetime.now(UTC))
    if paused_until and registry.get("google_news_country").enabled_by_default:
        errors.append({"name": "Google News", "error": f"Automatic refresh is paused after a rate-limit response. It resumes after {paused_until:%H:%M UTC on %b %d}. Cached headlines remain available."})
    errored_jobs = set()
    for job, key in jobs:
        snapshot = snapshots.get(key)
        if isinstance(snapshot, dict) and snapshot.get("last_error"):
            errors.append({"name": label(job), "error": snapshot.get("last_error_detail") or snapshot["last_error"]})
            errored_jobs.add(job)
    # Also expose unexpected worker failures, but drop them after a later
    # successful check or when the source is disabled/removed.
    keys = dict(jobs)
    started = parse_datetime(progress.pop("started_at"))
    for job in map(tuple, progress.pop("failed_jobs")):
        if job not in keys or job in errored_jobs:
            continue
        snapshot = snapshots.get(keys[job])
        attempted = parse_datetime(snapshot.get("last_attempt_at")) if isinstance(snapshot, dict) else None
        if not attempted or not started or attempted < started:
            errors.append({"name": label(job), "error": "The last check could not be completed; cached results are retained where available."})
    progress["errors"] = errors
    progress["failed"] = len(errors)
    progress["enabled"] = len(jobs)
    return JsonResponse(progress)


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
            messages.warning(request, "Feed saved, but its check failed. See its reason in Feed details.")
        return _navigate(request, _country(request))
    country = _country(request)
    registry, choices, interval = with_custom_sources(get_source_registry()), source_choices(), freshness_seconds()
    preferences_form = NewsPreferencesForm(registry=registry, choices=choices, freshness=interval)
    context = _context(registry, choices, preferences_form, country, interval)
    for row in context["custom_sources"]:
        if row["record"].pk == publisher.pk:
            row["add_feed_form"] = form
            row["details_open"] = True
    return render_page(request, "settings", page_template="news/settings.html", context=context)


@never_cache
@require_http_methods(["POST"])
def add_custom_source(request):
    form = CustomSourceForm(request.POST)
    if not form.is_valid():
        country = _country(request)
        registry, choices, interval = with_custom_sources(get_source_registry()), source_choices(), freshness_seconds()
        preferences_form = NewsPreferencesForm(registry=registry, choices=choices, freshness=interval)
        context = _context(registry, choices, preferences_form, country, interval)
        context["custom_form"] = form
        return render_page(request, "settings", page_template="news/settings.html", context=context)
    record = CustomSource(kind=form.cleaned_data["kind"], url=form.cleaned_data["location"], name=form.cleaned_data["name"])
    success = check_custom_source(record)
    record.save()
    from .services.background import feed_warmer

    feed_warmer.rescan()
    if success:
        messages.success(request, "Source added and checked. Matching items are now available on the map.")
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
        messages.success(request, "Custom source removed. Saved journal entries are kept.")
    elif action == "check":
        success = check_custom_source(record)
        record.save()
        if success:
            messages.success(request, "Source checked; its cache is ready.")
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
