from urllib.parse import urlencode

from django.conf import settings
from django.core.paginator import Paginator
from django.core.cache import cache
from django.db import DatabaseError
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .adapters.youtube import build_thumbnail_url
from .services.archive import archived_items
from .services.cache import deserialize_items, deserialize_video_items, fixed_feed_cache_key, google_cache_key, youtube_cache_key
from .services.country_news import _countries_by_code, get_country_news_page
from .services.presentation import CachedDrawers
from .services.youtube_news import get_country_videos
from .preferences import effective_registry
from .types import SourceKind


@never_cache
@require_GET
def earlier_coverage(request):
    kind = request.GET.get("kind", "articles")
    code = request.GET.get("country", "WORLD").upper()
    category = request.GET.get("source", "all")
    if kind not in {"articles", "videos"} or code != "WORLD" and code not in _countries_by_code():
        raise Http404("Unknown country coverage")
    excluded = ()
    registry = None
    if code != "WORLD":
        # Exclude the cards already shown in the live drawer, not every feed
        # entry: history can expose coverage omitted by the live-card limits.
        drawers = CachedDrawers([code])
        registry = drawers.registry
        options = {"registry":registry, "cache_backend":drawers, "cache_only":True, "now":drawers.now}
        if kind == "articles":
            page = get_country_news_page(code, **options)
            excluded = (*page.google.items, *page.regional_items)
        else:
            excluded = get_country_videos(code, **options).items
    else:
        registry = effective_registry()
        current = []
        if kind == "articles":
            keys = [fixed_feed_cache_key(feed) for feed in registry.feeds if feed.enabled_by_default and category in {"all", "regional", feed.provider_id}]
            google = registry.get("google_news_country")
            if google.enabled_by_default and category in {"all", "google"}:
                keys.append(google_cache_key(google, "WORLD"))
            for snapshot in cache.get_many(keys).values():
                if isinstance(snapshot, dict):
                    current.extend(deserialize_items(snapshot) or ())
        else:
            channels = [source for source in registry.sources if source.enabled_by_default and source.kind is SourceKind.YOUTUBE and category in {"all", source.id}]
            snapshots = cache.get_many([youtube_cache_key(source) for source in channels])
            for source in channels:
                current.extend(deserialize_video_items(snapshots.get(youtube_cache_key(source), {}), source) or ())
        excluded = tuple(current)
    try:
        rows = archived_items(kind, None if code == "WORLD" else code, category=category, exclude=excluded, registry=registry)
        result_page = Paginator(rows, settings.NEWS_ARCHIVE_PAGE_SIZE).get_page(request.GET.get("page", "1"))
        cards = []
        for item in result_page:
            initial = {"type":"youtube" if kind == "videos" else "article", "title":item.title, "source":item.publisher}
            initial["video" if kind == "videos" else "url"] = item.video_id if kind == "videos" else item.link
            if code != "WORLD":
                initial["country"] = code
            if item.published_at:
                initial["published"] = item.published_at.isoformat()
            cards.append({"item":item, "save_url":reverse("journal:new")+"?"+urlencode(initial),
                          "thumbnail_url":build_thumbnail_url(item.video_id) if kind == "videos" else ""})
        def page_url(number):
            return reverse("news:archive") + "?" + urlencode({"country":code, "kind":kind, "source":category, "page":number})
        context = {"cards":cards, "kind":kind, "result_page":result_page,
                   "previous_url":page_url(result_page.previous_page_number()) if result_page.has_previous() else "",
                   "next_url":page_url(result_page.next_page_number()) if result_page.has_next() else ""}
    except DatabaseError:
        context = {"cards":[], "kind":kind, "unavailable":True}
    return render(request, "news/partials/archive_results.html", context)
