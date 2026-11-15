from django.urls import path

from . import exports, views

app_name = "journal"

urlpatterns = [
    path("", views.index, name="index"),
    path("all/", views.list_entries, name="list"),
    path("new/", views.edit, name="new"),
    path("quick-save/", views.quick_save, name="quick_save"),
    path("player/<str:video_id>/", views.player_video, name="player_video"),
    path("images/<uuid:attachment_pk>/", views.image, name="image"),
    path("statistics/", views.statistics, name="statistics"),
    path("collections/new/", views.collection_edit, name="collection_new"),
    path("collections/<uuid:pk>/edit/", views.collection_edit, name="collection_edit"),
    path("collections/<uuid:pk>/delete/", views.collection_delete, name="collection_delete"),
    path("<uuid:pk>/", views.detail, name="detail"),
    path("<uuid:pk>/edit/", views.edit, name="edit"),
    path("<uuid:pk>/autosave/", views.autosave, name="autosave"),
    path("<uuid:pk>/delete/", views.delete_entry, name="delete"),
    path("<uuid:pk>/images/", views.upload_attachment, name="upload_attachment"),
    path("<uuid:pk>/export/<str:format>/", exports.export_document, name="export"),
    path("<uuid:pk>/images/<uuid:attachment_pk>/delete/", views.delete_attachment, name="delete_attachment"),
]
