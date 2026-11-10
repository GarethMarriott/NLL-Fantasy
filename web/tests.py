from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .draft_history import archive_draft, archive_rookie_draft
from .models import ChatMessage, Draft, DraftHistory, DraftPick, DraftPosition, FantasyTeamOwner, FutureRookiePick, League, Player, RookieDraft, RookieDraftPick, Roster, Team
from .tasks import create_future_rookie_picks, create_rookie_draft


class DynastyStartupDraftTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username="commissioner",
			password="test-password",
		)
		self.client.force_login(self.user)

	def test_new_dynasty_league_requires_a_startup_draft(self):
		response = self.client.post(reverse("league_create"), {
			"name": "New Dynasty League",
			"description": "",
			"max_teams": 4,
			"roster_format": "bestball",
			"league_type": "dynasty",
		})

		self.assertRedirects(response, reverse("league_detail", args=[League.objects.get(name="New Dynasty League").id]))
		league = League.objects.get(name="New Dynasty League")
		self.assertFalse(league.startup_draft_completed)

	def test_rookie_draft_is_blocked_until_startup_draft_completes(self):
		league = League.objects.create(
			name="Pending Startup League",
			commissioner=self.user,
			startup_draft_completed=False,
		)

		self.assertIsNone(create_rookie_draft(league.id, league.season))

	def test_startup_draft_uses_the_regular_all_player_draft(self):
		league = League.objects.create(
			name="Full Startup League",
			commissioner=self.user,
			league_type="dynasty",
			max_teams=4,
			roster_size=14,
			startup_draft_completed=False,
		)
		Team.objects.bulk_create([
			Team(name=f"Team {number}", league=league, season_year=league.season)
			for number in range(1, 5)
		])
		session = self.client.session
		session["selected_league_id"] = league.id
		session.save()

		response = self.client.post(reverse("create_draft_preview"), {
			"order_type": Draft.DraftOrderType.RANDOM,
			"draft_style": Draft.DraftStyle.SNAKE,
		})

		self.assertRedirects(response, reverse("draft_room"))
		draft = Draft.objects.get(league=league)
		self.assertEqual(draft.draft_type, Draft.DraftType.STARTUP)
		self.assertEqual(draft.total_rounds, league.roster_size)

	def test_startup_draft_preview_can_be_created_before_league_is_full(self):
		league = League.objects.create(
			name="Partial Startup League",
			commissioner=self.user,
			league_type="dynasty",
			max_teams=4,
			startup_draft_completed=False,
		)
		Team.objects.create(name="Only Team", league=league, season_year=league.season)
		session = self.client.session
		session["selected_league_id"] = league.id
		session.save()

		response = self.client.post(reverse("create_draft_preview"), {
			"order_type": Draft.DraftOrderType.RANDOM,
			"draft_style": Draft.DraftStyle.SNAKE,
		})

		self.assertRedirects(response, reverse("draft_room"), fetch_redirect_response=False)
		self.assertTrue(Draft.objects.filter(league=league).exists())

	def test_incomplete_league_cannot_activate_a_draft_preview(self):
		league = League.objects.create(
			name="Incomplete Draft League",
			commissioner=self.user,
			max_teams=4,
		)
		team = Team.objects.create(name="Only Team", league=league, season_year=league.season)
		Draft.objects.create(league=league, total_rounds=1)
		session = self.client.session
		session["selected_league_id"] = league.id
		session.save()

		response = self.client.post(reverse("set_draft_order"), {
			"team_order": f"[{team.id}]",
			"activate": "true",
		})

		self.assertEqual(response.status_code, 400)
		self.assertIn("must be full", response.json()["error"])
		self.assertFalse(Draft.objects.get(league=league).is_active)

	def test_commissioner_can_reset_dynasty_league_for_a_new_startup_draft(self):
		league = League.objects.create(
			name="Restart Dynasty League",
			commissioner=self.user,
			league_type="dynasty",
			startup_draft_completed=True,
		)
		team = Team.objects.create(name="Restart Team", league=league, season_year=league.season)
		FantasyTeamOwner.objects.create(user=self.user, team=team)
		player = Player.objects.create(first_name="Reset", last_name="Player", position="O")
		roster = Roster.objects.create(team=team, player=player, league=league, season=league.season)
		Draft.objects.create(league=league, completed=True)

		response = self.client.post(reverse("reset_dynasty_for_startup_draft", args=[league.id]))

		self.assertRedirects(response, reverse("draft_room"), fetch_redirect_response=False)
		league.refresh_from_db()
		roster.refresh_from_db()
		self.assertFalse(league.startup_draft_completed)
		self.assertTrue(league.draft_locked)
		self.assertEqual(roster.week_dropped, 0)
		self.assertFalse(Draft.objects.filter(league=league).exists())


class LeagueNavigationTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(username="navigation-user", password="test-password")
		self.league = League.objects.create(name="Navigation League", commissioner=self.user)
		team = Team.objects.create(name="Navigation Team", league=self.league, season_year=self.league.season)
		FantasyTeamOwner.objects.create(user=self.user, team=team)
		self.client.force_login(self.user)

	def test_home_exits_the_selected_league(self):
		session = self.client.session
		session["selected_league_id"] = self.league.id
		session.save()

		response = self.client.get(reverse("home"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Welcome to NLL Fantasy")
		self.assertNotIn("selected_league_id", self.client.session)

	def test_league_list_exits_the_selected_league(self):
		session = self.client.session
		session["selected_league_id"] = self.league.id
		session.save()

		response = self.client.get(reverse("league_list"))

		self.assertEqual(response.status_code, 200)
		self.assertNotIn("selected_league_id", self.client.session)
		self.assertContains(response, reverse("select_league", args=[self.league.id]))

	def test_selecting_a_league_enters_its_team_view(self):
		response = self.client.get(reverse("select_league", args=[self.league.id]))

		self.assertRedirects(response, reverse("my_team"), fetch_redirect_response=False)
		self.assertEqual(self.client.session["selected_league_id"], self.league.id)

	def test_settings_header_shows_league_code(self):
		response = self.client.get(reverse("league_settings", args=[self.league.id]))

		self.assertContains(response, f"Code: {self.league.unique_id}")

	def test_private_full_league_can_be_found_by_join_code(self):
		other_user = get_user_model().objects.create_user(username="private-commissioner", password="test-password")
		private_league = League.objects.create(
			name="Private Code League",
			commissioner=other_user,
			is_public=False,
			max_teams=2,
		)
		Team.objects.create(name="Private Team 1", league=private_league, season_year=private_league.season)
		Team.objects.create(name="Private Team 2", league=private_league, season_year=private_league.season)

		response = self.client.get(reverse("league_list"), {
			"search": private_league.unique_id.lower(),
			"search_type": "code",
		})

		self.assertContains(response, private_league.name)
		self.assertContains(response, "League Full")

	def test_commissioner_can_delete_league_from_operations(self):
		team = Team.objects.get(league=self.league)
		archive = DraftHistory.objects.create(
			league=self.league,
			draft_type=DraftHistory.DraftType.REDRAFT,
			season_year=self.league.season,
			total_rounds=1,
			source_model="Draft",
			source_draft_id=1,
			results=[],
		)
		session = self.client.session
		session["selected_league_id"] = self.league.id
		session.save()

		response = self.client.get(reverse("league_settings_section", args=[self.league.id, "operations"]))

		self.assertContains(response, reverse("delete_league", args=[self.league.id]))
		response = self.client.post(reverse("delete_league", args=[self.league.id]))

		self.assertRedirects(response, reverse("league_list"))
		self.assertFalse(League.objects.filter(id=self.league.id).exists())
		self.assertFalse(Team.objects.filter(id=team.id).exists())
		self.assertFalse(FantasyTeamOwner.objects.filter(user=self.user).exists())
		self.assertFalse(DraftHistory.objects.filter(id=archive.id).exists())
		self.assertTrue(get_user_model().objects.filter(id=self.user.id).exists())
		self.assertNotIn("selected_league_id", self.client.session)

	def test_delete_confirmation_discards_stale_activity_messages(self):
		Draft.objects.create(league=self.league)
		session = self.client.session
		session["selected_league_id"] = self.league.id
		session.save()

		self.client.post(reverse("cancel_draft"))
		response = self.client.get(reverse("delete_league", args=[self.league.id]))

		self.assertNotContains(response, "Draft cancelled.")
		self.assertContains(response, 'id="delete-confirmation-modal"')
		self.assertContains(response, "Are you absolutely sure?")

	def test_operations_lists_member_removal_for_commissioner_only(self):
		member = get_user_model().objects.create_user(username="removal-member", password="test-password")
		member_team = Team.objects.create(
			name="Removal Member Team",
			league=self.league,
			season_year=self.league.season,
		)
		FantasyTeamOwner.objects.create(user=member, team=member_team)

		response = self.client.get(reverse("league_settings_section", args=[self.league.id, "operations"]))

		self.assertContains(response, "Manage Members")
		self.assertContains(response, reverse("remove_team_from_league", args=[self.league.id, member_team.id]))

		self.client.force_login(member)
		response = self.client.get(reverse("league_settings_section", args=[self.league.id, "operations"]))

		self.assertNotContains(response, "Manage Members")


class RenewedLeagueRepairTests(TestCase):
	def test_repair_restores_missing_current_season_teams_and_priorities(self):
		commissioner = get_user_model().objects.create_user(username="renewal-commissioner")
		member = get_user_model().objects.create_user(username="renewal-member")
		league = League.objects.create(
			name="Partially Renewed League",
			commissioner=commissioner,
			season=2027,
		)
		commissioner_team = Team.objects.create(
			name="Commissioner Team", league=league, season_year=2026, waiver_priority=2,
		)
		member_team = Team.objects.create(
			name="Member Team", league=league, season_year=2026, waiver_priority=1,
		)
		FantasyTeamOwner.objects.create(user=commissioner, team=commissioner_team)
		FantasyTeamOwner.objects.create(user=member, team=member_team)
		Team.objects.create(
			name="Commissioner Team", league=league, season_year=2027, waiver_priority=0,
		)

		call_command("repair_active_league_teams", league_id=league.id)

		teams = Team.objects.filter(league=league, season_year=2027).order_by("waiver_priority")
		self.assertEqual(list(teams.values_list("name", flat=True)), ["Member Team", "Commissioner Team"])
		self.assertEqual(list(teams.values_list("waiver_priority", flat=True)), [1, 2])
		self.assertTrue(FantasyTeamOwner.objects.filter(user=member, team__season_year=2027).exists())


class DraftHistoryTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(username="history-user", password="test-password")
		self.league = League.objects.create(name="Draft Archive League", commissioner=self.user)
		self.team = Team.objects.create(name="Archive Team", league=self.league, season_year=self.league.season)
		FantasyTeamOwner.objects.create(user=self.user, team=self.team)
		self.player = Player.objects.create(
			first_name="Archive",
			last_name="Player",
			position=Player.Position.OFFENCE,
			nll_team="Halifax Thunderbirds",
		)
		self.client.force_login(self.user)

	def test_regular_draft_is_archived_idempotently_and_visible_in_history(self):
		draft = Draft.objects.create(
			league=self.league,
			draft_type=Draft.DraftType.REDRAFT,
			completed=True,
			total_rounds=1,
		)
		DraftPick.objects.create(draft=draft, round=1, pick_number=1, overall_pick=1, team=self.team, player=self.player)

		archive_draft(draft, season_year=2026)
		archive_draft(draft, season_year=2026)

		self.assertEqual(DraftHistory.objects.count(), 1)
		archive = DraftHistory.objects.get()
		self.assertEqual(archive.draft_type, DraftHistory.DraftType.REDRAFT)
		self.assertEqual(archive.season_year, 2026)
		self.assertEqual(archive.results[0]["player_name"], "Archive Player")
		response = self.client.get(reverse("league_history", args=[self.league.id]))
		self.assertContains(response, "Re-Draft Draft")
		self.assertContains(response, reverse("league_history_draft", args=[self.league.id, archive.id]))
		response = self.client.get(reverse("league_history_draft", args=[self.league.id, archive.id]))
		self.assertContains(response, "Archive Player")

	def test_rookie_draft_is_archived_with_its_season(self):
		rookie_draft = RookieDraft.objects.create(
			league=self.league,
			season_year=2027,
			completed=True,
		)
		RookieDraftPick.objects.create(
			draft=rookie_draft,
			round=1,
			pick_number=1,
			overall_pick=1,
			team=self.team,
			player=self.player,
		)

		archive_rookie_draft(rookie_draft)

		archive = DraftHistory.objects.get()
		self.assertEqual(archive.draft_type, DraftHistory.DraftType.ROOKIE)
		self.assertEqual(archive.season_year, 2027)
		self.assertEqual(archive.total_rounds, 1)


class DraftRoomTests(TestCase):
	def test_draft_enforces_turn_order_and_shows_personal_board(self):
		first_user = get_user_model().objects.create_user(username="first-drafter", password="test-password")
		second_user = get_user_model().objects.create_user(username="second-drafter", password="test-password")
		league = League.objects.create(name="Ordered Draft League", commissioner=first_user)
		first_team = Team.objects.create(name="First Team", league=league, season_year=league.season)
		second_team = Team.objects.create(name="Second Team", league=league, season_year=league.season)
		FantasyTeamOwner.objects.create(user=first_user, team=first_team)
		FantasyTeamOwner.objects.create(user=second_user, team=second_team)
		draft = Draft.objects.create(league=league, is_active=True, total_rounds=2)
		DraftPosition.objects.create(draft=draft, team=first_team, position=1)
		DraftPosition.objects.create(draft=draft, team=second_team, position=2)
		first_pick = DraftPick.objects.create(draft=draft, round=1, pick_number=1, overall_pick=1, team=first_team)
		second_pick = DraftPick.objects.create(draft=draft, round=1, pick_number=2, overall_pick=2, team=second_team)
		DraftPick.objects.create(draft=draft, round=2, pick_number=1, overall_pick=3, team=second_team)
		future_first_pick = DraftPick.objects.create(draft=draft, round=2, pick_number=2, overall_pick=4, team=first_team)
		first_player = Player.objects.create(first_name="First", last_name="Target", position=Player.Position.OFFENCE)
		second_player = Player.objects.create(first_name="Second", last_name="Target", position=Player.Position.DEFENCE)

		self.client.force_login(second_user)
		response = self.client.post(reverse("make_draft_pick", args=[draft.id]), {"player_id": second_player.id})

		self.assertRedirects(response, reverse("draft_room"), fetch_redirect_response=False)
		self.assertIsNone(DraftPick.objects.get(id=second_pick.id).player)

		self.client.force_login(first_user)
		self.client.post(reverse("make_draft_pick", args=[draft.id]), {"player_id": first_player.id})
		draft.refresh_from_db()
		self.assertEqual(draft.current_pick, 2)
		self.assertTrue(ChatMessage.objects.filter(
			league=league,
			message="[Draft] First Team selected First Target (Round 1)",
		).exists())

		self.client.force_login(second_user)
		response = self.client.post(reverse("make_draft_pick", args=[draft.id]), {"player_id": second_player.id})

		self.assertRedirects(response, reverse("draft_room"), fetch_redirect_response=False)
		self.assertEqual(DraftPick.objects.get(id=first_pick.id).player, first_player)
		self.assertEqual(DraftPick.objects.get(id=second_pick.id).player, second_player)

		self.client.force_login(first_user)
		session = self.client.session
		session["selected_league_id"] = league.id
		session.save()
		response = self.client.get(reverse("draft_room"))

		self.assertContains(response, "Your Draft Board (2 picks)")
		self.assertEqual(
			list(response.context["user_picks"].values_list("id", flat=True)),
			[first_pick.id, future_first_pick.id],
		)

	def test_draft_pick_uses_the_team_on_the_clock_after_rollover(self):
		user = get_user_model().objects.create_user(username="rollover-drafter", password="test-password")
		league = League.objects.create(name="Rollover Draft League", commissioner=user)
		legacy_team = Team.objects.create(name="Legacy Team", league=league, season_year=league.season - 1)
		current_team = Team.objects.create(name="Current Team", league=league, season_year=league.season)
		FantasyTeamOwner.objects.create(user=user, team=legacy_team)
		FantasyTeamOwner.objects.create(user=user, team=current_team)
		draft = Draft.objects.create(league=league, is_active=True, total_rounds=1)
		DraftPosition.objects.create(draft=draft, team=current_team, position=1)
		DraftPick.objects.create(draft=draft, round=1, pick_number=1, overall_pick=1, team=current_team)
		player = Player.objects.create(first_name="Draft", last_name="Target", position=Player.Position.OFFENCE)
		self.client.force_login(user)

		response = self.client.post(reverse("make_draft_pick", args=[draft.id]), {"player_id": player.id})

		self.assertRedirects(response, reverse("draft_room"), fetch_redirect_response=False)
		self.assertEqual(DraftPick.objects.get(draft=draft).player, player)

	def test_rookie_draft_room_does_not_read_regular_draft_type(self):
		user = get_user_model().objects.create_user(username="rookie-draft-user", password="test-password")
		league = League.objects.create(
			name="Rookie Draft League",
			commissioner=user,
			league_type="dynasty",
			startup_draft_completed=True,
		)
		team = Team.objects.create(name="Rookie Draft Team", league=league, season_year=league.season)
		FantasyTeamOwner.objects.create(user=user, team=team)
		RookieDraft.objects.create(league=league, season_year=league.season)
		self.client.force_login(user)
		session = self.client.session
		session["selected_league_id"] = league.id
		session.save()

		response = self.client.get(reverse("draft_room"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Rookie Draft Room")


class FutureRookiePickTests(TestCase):
	def test_future_picks_exclude_legacy_teams(self):
		user = get_user_model().objects.create_user(username="future-pick-user", password="test-password")
		league = League.objects.create(
			name="Future Pick League",
			commissioner=user,
			league_type="dynasty",
			season=2027,
			startup_draft_completed=True,
		)
		Team.objects.create(name="Legacy Team", league=league)
		current_team = Team.objects.create(name="Current Team", league=league, season_year=2027)

		success, _, _ = create_future_rookie_picks(league.id, years_ahead=1, num_rounds=1)

		self.assertTrue(success)
		self.assertEqual(FutureRookiePick.objects.filter(league=league).count(), 1)
		self.assertEqual(FutureRookiePick.objects.get(league=league).team, current_team)


class ChatViewTests(TestCase):
	def test_chat_view_prefetches_sender_fantasy_teams(self):
		user = get_user_model().objects.create_user(username="chat-user", password="test-password")
		league = League.objects.create(name="Chat League", commissioner=user)
		team = Team.objects.create(name="Chat Team", league=league, season_year=league.season)
		FantasyTeamOwner.objects.create(user=user, team=team)
		ChatMessage.objects.create(league=league, sender=user, message="Chat prefetch works")
		self.client.force_login(user)
		session = self.client.session
		session["selected_league_id"] = league.id
		session.save()

		response = self.client.get(reverse("chat"))

		self.assertContains(response, "Chat prefetch works")
		self.assertContains(response, "Chat Team")

	def test_chat_view_resolves_a_prior_season_team_id(self):
		user = get_user_model().objects.create_user(username="season-chat-user", password="test-password")
		league = League.objects.create(name="Season Chat League", commissioner=user, season=2027)
		user_team = Team.objects.create(name="Current User Team", league=league, season_year=2027)
		previous_team = Team.objects.create(name="Other Team", league=league, season_year=2026)
		current_team = Team.objects.create(name="Other Team", league=league, season_year=2027)
		FantasyTeamOwner.objects.create(user=user, team=user_team)
		self.client.force_login(user)
		session = self.client.session
		session["selected_league_id"] = league.id
		session.save()

		response = self.client.get(reverse("chat"), {
			"chat_type": "team",
			"team_chat_id": previous_team.id,
		})

		self.assertContains(response, current_team.name)

	def test_legacy_team_chat_can_be_opened_and_sent(self):
		user = get_user_model().objects.create_user(username="legacy-chat-user", password="test-password")
		other_user = get_user_model().objects.create_user(username="legacy-chat-other", password="test-password")
		league = League.objects.create(name="Legacy Chat League", commissioner=user, season=2027)
		user_team = Team.objects.create(name="Legacy User Team", league=league)
		other_team = Team.objects.create(name="Legacy Other Team", league=league)
		FantasyTeamOwner.objects.create(user=user, team=user_team)
		FantasyTeamOwner.objects.create(user=other_user, team=other_team)
		self.client.force_login(user)
		session = self.client.session
		session["selected_league_id"] = league.id
		session.save()

		response = self.client.get(reverse("chat"), {
			"chat_type": "team",
			"team_chat_id": other_team.id,
		})
		self.assertContains(response, other_team.name)

		response = self.client.post(reverse("chat_post"), {
			"chat_type": "team",
			"team_chat_id": other_team.id,
			"message": "Legacy private chat works",
		})
		self.assertTrue(response.json()["success"])


class LeagueAutoSelectionTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(username="matchups-user", password="test-password")
		self.league = League.objects.create(name="Auto Select League", commissioner=self.user)
		team = Team.objects.create(name="Auto Select Team", league=self.league, season_year=self.league.season)
		FantasyTeamOwner.objects.create(user=self.user, team=team)
		self.client.force_login(self.user)

	def test_matchups_auto_selects_the_users_league(self):
		response = self.client.get(reverse("matchups"))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.client.session["selected_league_id"], self.league.id)

	def test_standings_auto_selects_the_users_league(self):
		response = self.client.get(reverse("standings"))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.client.session["selected_league_id"], self.league.id)


class LeagueTeamCountTests(TestCase):
	def test_my_leagues_counts_only_the_current_season_teams(self):
		user = get_user_model().objects.create_user(username="league-count-user", password="test-password")
		league = League.objects.create(name="Rollover League", commissioner=user, max_teams=6, season=2027)
		for season_year in (2026, 2027):
			for number in range(1, 7):
				Team.objects.create(name=f"Team {number}", league=league, season_year=season_year)
		self.client.force_login(user)

		response = self.client.get(reverse("league_list"))

		self.assertEqual(league.active_team_count, 6)
		self.assertContains(response, "6/6 teams")
		self.assertNotContains(response, "12/6 teams")


class LeagueJoinTests(TestCase):
	def test_joining_after_a_rollover_uses_current_season_capacity(self):
		commissioner = get_user_model().objects.create_user(username="join-commissioner", password="test-password")
		user = get_user_model().objects.create_user(username="joining-user", password="test-password")
		league = League.objects.create(name="Open Rollover League", commissioner=commissioner, max_teams=6, season=2027)
		for number in range(1, 7):
			Team.objects.create(name=f"Previous Team {number}", league=league, season_year=2026)
		self.client.force_login(user)

		response = self.client.get(reverse("team_create", args=[league.id]))

		self.assertContains(response, "Current Teams:</strong> 0/6")

		response = self.client.post(reverse("team_create", args=[league.id]), {"name": "New Season Team"})

		self.assertRedirects(response, reverse("league_detail", args=[league.id]))
		self.assertTrue(FantasyTeamOwner.objects.filter(user=user, team__name="New Season Team").exists())
		self.assertTrue(Team.objects.filter(name="New Season Team", league=league, season_year=2027).exists())
		self.assertEqual(self.client.session["selected_league_id"], league.id)


class LeaveLeagueTests(TestCase):
	def setUp(self):
		self.commissioner = get_user_model().objects.create_user(username="leave-commissioner", password="test-password")
		self.user = get_user_model().objects.create_user(username="leaving-user", password="test-password")
		self.league = League.objects.create(name="Leave League", commissioner=self.commissioner)
		self.team = Team.objects.create(name="Leaving Team", league=self.league, season_year=self.league.season)
		FantasyTeamOwner.objects.create(user=self.user, team=self.team)
		self.client.force_login(self.user)

	def test_member_can_leave_and_returns_to_home(self):
		session = self.client.session
		session["selected_league_id"] = self.league.id
		session.save()

		response = self.client.post(reverse("leave_league", args=[self.league.id]))

		self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
		self.assertFalse(Team.objects.filter(id=self.team.id).exists())
		self.assertNotIn("selected_league_id", self.client.session)

	def test_commissioner_cannot_leave(self):
		commissioner_team = Team.objects.create(
			name="Commissioner Team", league=self.league, season_year=self.league.season,
		)
		FantasyTeamOwner.objects.create(user=self.commissioner, team=commissioner_team)
		self.client.force_login(self.commissioner)

		response = self.client.post(reverse("leave_league", args=[self.league.id]))

		self.assertRedirects(response, reverse("league_settings_section", args=[self.league.id, "operations"]))
		self.assertTrue(Team.objects.filter(id=commissioner_team.id).exists())
