from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.map_page, name="map"),
    path("journal/", views.journal_page, name="journal"),
    path("settings/", views.settings_page, name="settings"),
]