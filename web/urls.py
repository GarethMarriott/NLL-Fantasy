from django.urls import path
from .views import (
    home, about, players, player_detail_modal, schedule, matchups, standings, team_detail, assign_player, move_transition_player, trade_center, propose_trade, accept_trade, reject_trade, cancel_trade,
    login_view, logout_view, chat_view, chat_post_message, chat_get_messages,
    register_view, league_list, league_create, league_detail, team_create, select_league, league_settings, team_settings,
    submit_waiver_claim, cancel_waiver_claim, my_team, draft_room, start_draft, make_draft_pick, set_draft_order, cancel_draft,
    nll_schedule, CustomPasswordResetView, CustomPasswordResetDoneView, CustomPasswordResetConfirmView, CustomPasswordResetCompleteView,
    manage_lineup
)
from .bug_views import report_bug, bug_list, bug_detail, update_bug_status, add_bug_note, bug_report_api

urlpatterns = [
    path("", home, name="home"),
    path("about/", about, name="about"),
    path("teams/", my_team, name="my_team"),
    path("teams/<int:team_id>/", team_detail, name="team_detail"),
    path("teams/<int:team_id>/assign-player/", assign_player, name="assign_player"),
    path("teams/<int:team_id>/move-transition/", move_transition_player, name="move_transition_player"),
    path("teams/<int:team_id>/trades/", trade_center, name="trade_center"),
    path("teams/<int:team_id>/trades/propose/", propose_trade, name="propose_trade"),
    path("trades/<int:trade_id>/accept/", accept_trade, name="accept_trade"),
    path("trades/<int:trade_id>/reject/", reject_trade, name="reject_trade"),
    path("trades/<int:trade_id>/cancel/", cancel_trade, name="cancel_trade"),
    path("teams/<int:team_id>/waiver-claim/", submit_waiver_claim, name="submit_waiver_claim"),
    path("waiver-claims/<int:claim_id>/cancel/", cancel_waiver_claim, name="cancel_waiver_claim"),
    path("players/", players, name="players"),
    path("players/<int:player_id>/modal/", player_detail_modal, name="player_detail_modal"),
    path("schedule/", schedule, name="schedule"),
    path("nll-schedule/", nll_schedule, name="nll_schedule"),
    path("matchups/", matchups, name="matchups"),
    path("standings/", standings, name="standings"),
    
    # Authentication
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("register/", register_view, name="register"),
    path("password-reset/", CustomPasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", CustomPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/", CustomPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password-reset/complete/", CustomPasswordResetCompleteView.as_view(), name="password_reset_complete"),
    
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
    path("teams/<int:team_id>/lineup/", manage_lineup, name="manage_lineup"),
    
    # Draft
    path("draft/", draft_room, name="draft_room"),
    path("draft/start/", start_draft, name="start_draft"),
    path("draft/cancel/", cancel_draft, name="cancel_draft"),
    path("draft/<int:draft_id>/pick/", make_draft_pick, name="make_draft_pick"),
    path("draft/set-order/", set_draft_order, name="set_draft_order"),
    
    # Bug Reporting
    path("bugs/report/", report_bug, name="report_bug"),
    path("bugs/", bug_list, name="bug_list"),
    path("bugs/<int:bug_id>/", bug_detail, name="bug_detail"),
    path("bugs/<int:bug_id>/status/", update_bug_status, name="update_bug_status"),
    path("bugs/<int:bug_id>/note/", add_bug_note, name="add_bug_note"),
    path("api/bugs/report/", bug_report_api, name="bug_report_api"),
]