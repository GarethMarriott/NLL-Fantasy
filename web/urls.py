from django.urls import path
from .views import home, about, teams, players, schedule, standings, team_detail

urlpatterns = [
    path("", home, name="home"),
    path("about/", about, name="about"),
    path("teams", teams, name="teams"),
    path("teams/<int:team_id>/", team_detail, name="team_detail"),
    path("players/", players, name="players"),
    path("schedule/", schedule, name="schedule"),
    path("standings/", standings, name="standings"),
]