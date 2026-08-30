from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse
from django.views.decorators.cache import cache_control


@cache_control(public=True, max_age=86400)
def country_metadata(request: HttpRequest) -> HttpResponse:
    return FileResponse(
        (settings.BASE_DIR / "data" / "countries.json").open("rb"),
        content_type="application/json",
    )