from django.urls import path

from . import settings_views, views


app_name = "news"

urlpatterns = [
    path("settings/news/", settings_views.source_settings, name="settings"),
    path("settings/news/<str:source_id>/refresh/", settings_views.refresh_source, name="source_refresh"),
    path("news/countries/<str:iso2>/", views.country_news, name="country_news"),
    path("news/countries/<str:iso2>/videos/", views.country_videos, name="country_videos"),
]
