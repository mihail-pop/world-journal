from django.urls import path

from . import settings_views, views


app_name = "news"

urlpatterns = [
    path("news/cache/", views.cached_drawers, name="cached_drawers"),
    path("settings/news/", settings_views.source_settings, name="settings"),
    path("settings/news/preference/", settings_views.save_preference, name="save_preference"),
    path("settings/news/status/", settings_views.refresh_status, name="refresh_status"),
    path("settings/news/refresh-all/", settings_views.refresh_all, name="refresh_all"),
    path("settings/news/custom/add/", settings_views.add_custom_source, name="custom_add"),
    path("settings/news/custom/<uuid:source_id>/feeds/add/", settings_views.add_publisher_feed, name="custom_feed_add"),
    path("settings/news/custom/<uuid:source_id>/<str:action>/", settings_views.custom_source_action, name="custom_action"),
    path("settings/news/<str:source_id>/refresh/", settings_views.refresh_source, name="source_refresh"),
    path("news/countries/<str:iso2>/", views.country_news, name="country_news"),
    path("news/countries/<str:iso2>/videos/", views.country_videos, name="country_videos"),
]
