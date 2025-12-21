from django.urls import path
from .views import home, about, teams, players, schedule, standings

urlpatterns = [
    path("", home, name="home"),
    path("about/", about, name="about"),
    path("teams", teams, name="teams"),
    path("players/", players, name="players"),
    path("schedule/", schedule, name="schedule"),
    path("standings/", standings, name="standings"),
]