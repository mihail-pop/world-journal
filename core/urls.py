from django.urls import path

from . import backup_views, views

app_name = "core"

urlpatterns = [
    path("", views.map_page, name="map"),
    path("player/", views.player_page, name="player"),
    path("api/place-search/", views.place_search, name="place_search"),
    path("journal/", views.journal_page, name="journal"),
    path("settings/", views.settings_page, name="settings"),
    path("settings/theme/", views.save_theme, name="save_theme"),
    path("settings/preferences/", views.preferences, name="preferences"),
    path("api/version-info/", views.version_info, name="version_info"),
    path("settings/backups/", backup_views.backups, name="backups"),
    path("settings/backups/export/", backup_views.export_backup, name="export_backup"),
]
