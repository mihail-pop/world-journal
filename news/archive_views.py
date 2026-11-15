from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .adapters.youtube import build_thumbnail_url
from .adapters.rss import clean_article_text, is_google_news_link
from .models import ArchivedNews
from .services.archive import archived_items, country_revisions, enabled_feed_ids, identities, revision
from .paging import archive_page, decode_cursor, encode_cursor, NewsCursorError, page_changed, paging_time, result_version, search_archive, search_query
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
    query, at = search_query(request.GET), paging_time(request.GET)
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
        rows = search_archive(rows.filter(first_seen_at__lte=at), query)
        query_signature = result_version([kind, code, category, query,
            enabled_feed_ids(registry, kind, None if code == "WORLD" else code, category)])
        archive_stamp = revision() if code == "WORLD" else country_revisions([code])[code]
        version = result_version([query_signature, archive_stamp, [identities(item, kind) for item in excluded]])
        if page_changed(request, version):
            return HttpResponse(status=409)
        cursor = decode_cursor(request.GET.get("cursor", ""), query_signature)
        batch = archive_page(rows, cursor, settings.NEWS_ARCHIVE_PAGE_SIZE + 1, date_field="sort_date")
        has_next = len(batch) > settings.NEWS_ARCHIVE_PAGE_SIZE
        batch = batch[:settings.NEWS_ARCHIVE_PAGE_SIZE]
        selected = ArchivedNews.objects.in_bulk([identity for identity, date, views in batch])
        cards = []
        for identity, date, views in batch:
            item = selected.get(identity)
            if item is None:
                continue
            if kind == "articles":
                # Display old retained metadata consistently; leave saved Journal
                # entries and the archive's stored identity/fingerprint untouched.
                item.title, item.summary = clean_article_text(
                    item.title, item.publisher, item.summary, google=is_google_news_link(item.link),
                )
            initial = {"type":"youtube" if kind == "videos" else "article", "title":item.title, "source":item.publisher}
            initial["video" if kind == "videos" else "url"] = item.video_id if kind == "videos" else item.link
            if code != "WORLD":
                initial["country"] = code
            if item.published_at:
                initial["published"] = item.published_at.isoformat()
            cards.append({"item":item, "save_url":reverse("journal:new")+"?"+urlencode(initial),
                          "thumbnail_url":build_thumbnail_url(item.video_id) if kind == "videos" else ""})
        def page_url():
            identity, date, views = batch[-1]
            position = {"identity": identity, "published": date.isoformat()}
            return reverse("news:archive") + "?" + urlencode({"country":code, "kind":kind, "source":category,
                "q":query, "cursor":encode_cursor(position, query_signature), "v":version, "at":at.isoformat()})
        context = {"cards":cards, "kind":kind,
                   "query": query, "paging_version": version, "query_signature": query_signature,
                   "refresh_url":reverse("news:archive")+"?"+urlencode({"country":code, "kind":kind, "source":category, "q":query}),
                   "next_url":page_url() if has_next else ""}
    except NewsCursorError:
        return HttpResponse("Refresh these news results to continue.", status=400)
    except DatabaseError:
        context = {"cards":[], "kind":kind, "unavailable":True}
    return render(request, "news/partials/archive_results.html", context)
