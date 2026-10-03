from django.urls import path
from . import views

urlpatterns = [
    path("", views.map_page, name="home"),
    path("map/", views.map_page, name="map"),
    path("api/route/", views.plan_route, name="plan_route"),
]