from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .services.country_news import CountryNotFoundError, get_country_news


@require_GET
def country_news(request: HttpRequest, iso2: str) -> HttpResponse:
    try:
        result = get_country_news(iso2)
    except CountryNotFoundError as error:
        raise Http404(str(error)) from error
    response = render(request, "news/partials/country_news.html", {"news": result})
    response.headers["Cache-Control"] = "private, no-store"
    return response