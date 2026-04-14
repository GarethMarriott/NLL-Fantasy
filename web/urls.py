from django.urls import path
from .views import (
    home, about, players, player_detail_modal, schedule, matchups, standings, team_detail, assign_player, move_transition_player, trade_center, propose_trade, accept_trade, reject_trade, cancel_trade,
    login_view, logout_view, chat_view, chat_post_message, chat_get_messages,
    register_view, league_list, league_create, league_detail, team_create, select_league, league_settings, team_settings, renew_league, remove_team_from_league,
    submit_waiver_claim, cancel_waiver_claim, my_team, draft_room, draft_settings, make_draft_pick, set_draft_order, cancel_draft, reorder_draft_picks,
    nll_schedule, cache_stats, CustomPasswordResetView, CustomPasswordResetDoneView, CustomPasswordResetConfirmView, CustomPasswordResetCompleteView,
    manage_lineup, add_to_taxi, move_from_taxi, get_available_slots, handle_404, handle_500,
    league_offseason, offseason_renew_league, lock_rosters, finalize_draft, crown_champion
)
from .views.history import league_history, league_history_standings, league_history_matchups, league_history_playoffs
from .views.nll_transactions import nll_transactions
from .bug_views import report_bug, bug_list, bug_detail, update_bug_status, add_bug_note, bug_report_api

urlpatterns = [
    path("", home, name="home"),
    path("about/", about, name="about"),
    path("teams/", my_team, name="my_team"),
    path("teams/<int:team_id>/", team_detail, name="team_detail"),
    path("teams/<int:team_id>/assign-player/", assign_player, name="assign_player"),
    path("teams/<int:team_id>/move-transition/", move_transition_player, name="move_transition_player"),
    path("teams/<int:team_id>/available-slots/", get_available_slots, name="get_available_slots"),
    path("teams/<int:team_id>/add-to-taxi/", add_to_taxi, name="add_to_taxi"),
    path("teams/<int:team_id>/move-from-taxi/", move_from_taxi, name="move_from_taxi"),
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
    path("leagues/<int:league_id>/renew/", renew_league, name="renew_league"),
    path("leagues/<int:league_id>/teams/<int:team_id>/remove/", remove_team_from_league, name="remove_team_from_league"),
    path("leagues/<int:league_id>/join/", team_create, name="team_create"),
    path("leagues/<int:league_id>/select/", select_league, name="select_league"),
    path("teams/<int:team_id>/settings/", team_settings, name="team_settings"),
    path("teams/<int:team_id>/lineup/", manage_lineup, name="manage_lineup"),
    
    # Offseason Management
    path("league/<int:league_id>/offseason/", league_offseason, name="league_offseason"),
    path("league/<int:league_id>/renew/", offseason_renew_league, name="league_renew"),
    path("league/<int:league_id>/lock-rosters/", lock_rosters, name="lock_rosters"),
    path("league/<int:league_id>/finalize-draft/", finalize_draft, name="finalize_draft"),
    path("league/<int:league_id>/crown-champion/", crown_champion, name="crown_champion"),
    
    # Historical League Views
    path("league/<int:league_id>/history/", league_history, name="league_history"),
    path("league/<int:league_id>/history/<int:year>/standings/", league_history_standings, name="league_history_standings"),
    path("league/<int:league_id>/history/<int:year>/matchups/", league_history_matchups, name="league_history_matchups"),
    path("league/<int:league_id>/history/<int:year>/playoffs/", league_history_playoffs, name="league_history_playoffs"),
    
    # NLL Information
    path("nll-transactions/", nll_transactions, name="nll_transactions"),
    
    # Draft
    path("draft/", draft_room, name="draft_room"),
    path("draft/settings/", draft_settings, name="draft_settings"),
    path("draft/cancel/", cancel_draft, name="cancel_draft"),
    path("draft/reorder/", reorder_draft_picks, name="reorder_draft_picks"),
    path("draft/<int:draft_id>/pick/", make_draft_pick, name="make_draft_pick"),
    path("draft/set-order/", set_draft_order, name="set_draft_order"),
    
    # Bug Reporting
    path("bugs/report/", report_bug, name="report_bug"),
    path("bugs/", bug_list, name="bug_list"),
    path("bugs/<int:bug_id>/", bug_detail, name="bug_detail"),
    path("bugs/<int:bug_id>/status/", update_bug_status, name="update_bug_status"),
    path("bugs/<int:bug_id>/note/", add_bug_note, name="add_bug_note"),
    path("api/bugs/report/", bug_report_api, name="bug_report_api"),
    
    # Cache Monitoring
    path("admin/cache-stats/", cache_stats, name="cache_stats"),
]

# Custom error handlers
handler404 = "web.views.handle_404"
handler500 = "web.views.handle_500"