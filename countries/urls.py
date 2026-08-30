from django.urls import path

from . import views

app_name = "countries"

urlpatterns = [
    path("data/countries.json", views.country_metadata, name="metadata"),
]