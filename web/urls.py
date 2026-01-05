from django.urls import path
from .views import (
    home, about, teams, players, schedule, matchups, standings, team_detail, assign_player,
    login_view, logout_view, chat_view, chat_post_message, chat_get_messages
)

urlpatterns = [
    path("", home, name="home"),
    path("about/", about, name="about"),
    path("teams", teams, name="teams"),
    path("teams/<int:team_id>/", team_detail, name="team_detail"),
    path("teams/<int:team_id>/assign-player/", assign_player, name="assign_player"),
    path("players/", players, name="players"),
    path("schedule/", schedule, name="schedule"),
    path("matchups/", matchups, name="matchups"),
    path("standings/", standings, name="standings"),
    
    # Authentication
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    
    # Chat
    path("chat/", chat_view, name="chat"),
    path("chat/post/", chat_post_message, name="chat_post"),
    path("chat/messages/", chat_get_messages, name="chat_messages"),
]