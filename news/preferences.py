from dataclasses import replace

from django.conf import settings

from .models import NewsPreferences, SourcePreference
from .registry import SourceRegistry, get_source_registry


def source_choices():
    return dict(SourcePreference.objects.values_list("source_id", "enabled"))


def refresh_preferences():
    row = NewsPreferences.objects.filter(pk=1).values_list("freshness_minutes", "google_pacing").first()
    return (row[0] * 60, row[1] or {}) if row else (settings.NEWS_REFRESH_SECONDS, {})


def freshness_seconds():
    minutes = NewsPreferences.objects.filter(pk=1).values_list("freshness_minutes", flat=True).first()
    return minutes * 60 if minutes is not None else settings.NEWS_REFRESH_SECONDS


def archive_storage_bytes():
    megabytes = NewsPreferences.objects.filter(pk=1).values_list("archive_storage_mb", flat=True).first()
    return megabytes * 1_000_000 if megabytes is not None else settings.NEWS_ARCHIVE_DEFAULT_BYTES


def effective_registry(registry=None, choices=None):
    if registry is None:
        from .services.custom_sources import with_custom_sources

        registry = with_custom_sources(get_source_registry())
    choices = source_choices() if choices is None else choices

    def enabled(item):
        # A preference can switch off a reviewed endpoint, never unlock a bad ID.
        return item.enabled_by_default and choices.get(item.id, True)

    providers = tuple(replace(provider, enabled_by_default=enabled(provider)) for provider in registry.providers)
    active_providers = {provider.id for provider in providers if provider.enabled_by_default}
    return SourceRegistry(
        sources=tuple(replace(source, enabled_by_default=enabled(source)) for source in registry.sources),
        providers=providers,
        feeds=tuple(replace(feed, enabled_by_default=enabled(feed) and feed.provider_id in active_providers) for feed in registry.feeds),
    )
