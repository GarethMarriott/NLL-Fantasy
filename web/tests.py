from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Draft, League, Team
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
