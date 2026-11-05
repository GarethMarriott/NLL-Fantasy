from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .draft_history import archive_draft, archive_rookie_draft
from .models import ChatMessage, Draft, DraftHistory, DraftPick, FantasyTeamOwner, League, Player, RookieDraft, RookieDraftPick, Team
from .tasks import create_rookie_draft


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
