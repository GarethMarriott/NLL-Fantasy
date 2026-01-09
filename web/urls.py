from django.urls import path
from .views import (
    home, about, players, schedule, matchups, standings, team_detail, assign_player,
    login_view, logout_view, chat_view, chat_post_message, chat_get_messages,
    register_view, league_list, league_create, league_detail, team_create, select_league, league_settings, team_settings,
    submit_waiver_claim, cancel_waiver_claim
)

urlpatterns = [
    path("", home, name="home"),
    path("about/", about, name="about"),
    path("teams/<int:team_id>/", team_detail, name="team_detail"),
    path("teams/<int:team_id>/assign-player/", assign_player, name="assign_player"),
    path("teams/<int:team_id>/waiver-claim/", submit_waiver_claim, name="submit_waiver_claim"),
    path("waiver-claims/<int:claim_id>/cancel/", cancel_waiver_claim, name="cancel_waiver_claim"),
    path("players/", players, name="players"),
    path("schedule/", schedule, name="schedule"),
    path("matchups/", matchups, name="matchups"),
    path("standings/", standings, name="standings"),
    
    # Authentication
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("register/", register_view, name="register"),
    
    # Chat
    path("chat/", chat_view, name="chat"),
    path("chat/post/", chat_post_message, name="chat_post"),
    path("chat/messages/", chat_get_messages, name="chat_messages"),
    
    # League & Team Management
    path("leagues/", league_list, name="league_list"),
    path("leagues/create/", league_create, name="league_create"),
    path("leagues/<int:league_id>/", league_detail, name="league_detail"),
    path("leagues/<int:league_id>/settings/", league_settings, name="league_settings"),
    path("leagues/<int:league_id>/join/", team_create, name="team_create"),
    path("leagues/<int:league_id>/select/", select_league, name="select_league"),
    path("teams/<int:team_id>/settings/", team_settings, name="team_settings"),
]