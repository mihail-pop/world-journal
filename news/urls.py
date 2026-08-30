from django.urls import path

from . import views


app_name = "news"

urlpatterns = [
    path("news/countries/<str:iso2>/", views.country_news, name="country_news"),
]