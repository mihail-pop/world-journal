from urllib.parse import urlencode
from hashlib import sha256

from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.views import render_page
from news.preferences import effective_registry

from .services.background import feed_warmer
from .services.country_news import _countries_by_code
from .services.world_news import CachedNews, news_url, page_options
from .services.archive import revision


def _board(request):
    registry = effective_registry()
    options = page_options(request.GET, registry)
    feed_warmer.prioritize_news(country=options["country"], videos=options["tab"] == "videos")
    return options, CachedNews(options, registry)


@never_cache
@require_GET
def index(request):
    options, board = _board(request)
    context = board.context()
    context.update({
        "options": options, "countries": sorted(_countries_by_code().values(), key=lambda country: country["name"]),
        "results_query": urlencode({key: options[key] for key in ("tab", "source", "country", "period", "sort", "page")}),
        "articles_url": news_url(options, tab="articles", source="all", sort="top", page=1),
        "videos_url": news_url(options, tab="videos", source="all", sort="newest", page=1),
        "archive_country": options["country"] if options["tab"] == "articles" else "WORLD",
        "archive_kind": options["tab"], "archive_source":options["source"], "archive_revision":revision(),
        "archive_config":sha256(repr(board.keys).encode()).hexdigest()[:16],
    })
    return render_page(request, "news", page_template="news/index.html", context=context)


@never_cache
@require_GET
def results(request):
    _options, board = _board(request)
    version = board.version()
    if request.GET.get("version") == version:
        return JsonResponse({"version": version, "archive_revision":revision()})
    context = board.context()
    return JsonResponse({"version": version, "archive_revision":revision(), "pending": context["pending"],
                         "html": render_to_string("news/partials/board_results.html", context)})
