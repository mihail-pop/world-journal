from django.urls import path

from . import personal_views, views

app_name = "countries"

urlpatterns = [
    path("data/map-personal.json", personal_views.personal_data, name="personal_data"),
    path("countries/<str:iso2>/favorite/", personal_views.favorite, name="favorite"),
    path("countries/<str:iso2>/notes/", personal_views.country_notes, name="notes"),
    path("countries/<str:iso2>/overview/", personal_views.profile_edit, name="profile_edit"),
    path("countries/<str:iso2>/overview/new/", personal_views.profile_create, name="profile_create"),
    path("map-presets/", personal_views.preset_list, name="preset_list"),
    path("map-presets/new/", personal_views.preset_edit, name="preset_new"),
    path("map-presets/clear/", personal_views.preset_activate, name="preset_clear"),
    path("map-presets/<uuid:pk>/edit/", personal_views.preset_edit, name="preset_edit"),
    path("map-presets/<uuid:pk>/activate/", personal_views.preset_activate, name="preset_activate"),
    path("map-presets/<uuid:pk>/duplicate/", personal_views.preset_duplicate, name="preset_duplicate"),
    path("map-presets/<uuid:pk>/delete/", personal_views.preset_delete, name="preset_delete"),
    path("data/countries.json", views.country_metadata, name="metadata"),
]