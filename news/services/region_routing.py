from __future__ import annotations

from news.registry import SourceRegistry
from news.registry import ROUTING_REGIONS
from news.types import NewsFeed, NewsProvider, NewsSource, SourceKind


ROUTING_EXCEPTIONS = {
    "CY": frozenset({"europe", "middle_east"}),
    "EG": frozenset({"africa", "middle_east"}),
    "IR": frozenset({"middle_east"}),
    "MX": frozenset({"north_america", "latin_america_caribbean"}),
    "RU": frozenset({"europe", "asia_pacific"}),
    "TR": frozenset({"europe", "middle_east"}),
}


def routing_groups_for_country(country: dict) -> frozenset[str]:
    code = country["iso_a2"]
    if code in ROUTING_EXCEPTIONS:
        return ROUTING_EXCEPTIONS[code]

    region = country["region"]
    subregion = country["subregion"]
    if region == "Europe":
        groups = {"europe"}
    elif region == "Africa":
        groups = {"africa"}
    elif region == "Oceania":
        groups = {"asia_pacific"}
    elif region == "Asia":
        groups = {"middle_east" if subregion == "Western Asia" else "asia_pacific"}
    elif region == "Americas":
        groups = {"north_america" if subregion == "Northern America" else "latin_america_caribbean"}
    else:
        groups = set()
    return frozenset(groups & ROUTING_REGIONS)


def eligible_fixed_feeds(country: dict, registry: SourceRegistry) -> tuple[NewsFeed, ...]:
    del country
    enabled_providers = {
        provider.id: provider
        for provider in registry.providers
        if provider.enabled_by_default
    }
    return tuple(
        sorted(
            (
                feed
                for feed in registry.feeds
                if feed.enabled_by_default and feed.provider_id in enabled_providers
            ),
            key=lambda feed: (
                enabled_providers[feed.provider_id].display_priority,
                feed.provider_id,
                feed.id,
            ),
        )
    )


def has_regional_affinity(country: dict, provider: NewsProvider) -> bool:
    return bool(routing_groups_for_country(country).intersection(provider.coverage_regions))


def eligible_youtube_sources(country: dict, registry: SourceRegistry) -> tuple[NewsSource, ...]:
    routing_groups = routing_groups_for_country(country)
    return tuple(sorted(
        (
            source
            for source in registry.sources
            if source.kind is SourceKind.YOUTUBE
            and source.enabled_by_default
            and routing_groups.intersection(source.coverage_regions)
        ),
        key=lambda source: (source.display_priority, source.id),
    ))