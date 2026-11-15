from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.views import render_page
from countries.facts import bundled_catalog
from news.preferences import effective_registry
from news.paging import NewsCursorError, page_changed

from .services.background import feed_warmer
from .services.world_news import CachedNews, news_url, page_options


def _board(request):
    registry = effective_registry()
    options = page_options(request.GET, registry)
    if request.headers.get("X-News-Paging") != "1":
        feed_warmer.prioritize_news(country=options["country"], videos=options["tab"] == "videos")
    return options, CachedNews(options, registry)


@never_cache
@require_GET
def index(request):
    options, board = _board(request)
    try:
        context = board.context()
    except NewsCursorError:
        return HttpResponse("Refresh these news results to continue.", status=400)
    if page_changed(request, context["paging_version"]):
        return HttpResponse(status=409)
    if request.headers.get("X-News-Paging") == "1" or request.headers.get("X-News-Filtering") == "1":
        return render(request, "news/partials/board_results.html", context)
    context.update({
        "options": options, "countries": sorted(bundled_catalog()[0].values(), key=lambda country: country["name"]),
        "articles_url": news_url(options, tab="articles", source="all", sort="top"),
        "videos_url": news_url(options, tab="videos", source="all", sort="views"),
    })
    return render_page(request, "news", page_template="news/index.html", context=context)
