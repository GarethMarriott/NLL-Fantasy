from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction

from web.models import FantasyTeamOwner, League, Team


class Command(BaseCommand):
    help = "Restore missing current-season teams and valid waiver priorities in renewed leagues."

    def add_arguments(self, parser):
        parser.add_argument("--league-id", type=int, action="append")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        leagues = League.objects.filter(is_active=True).order_by("id")
        league_ids = options["league_id"]
        if isinstance(league_ids, int):
            league_ids = [league_ids]
        if league_ids:
            leagues = leagues.filter(id__in=league_ids)

        repaired_teams = 0
        updated_priorities = 0
        for league in leagues:
            created, prioritized = self._repair_league(league, options["dry_run"])
            repaired_teams += created
            updated_priorities += prioritized
            if created or prioritized:
                action = "Would repair" if options["dry_run"] else "Repaired"
                self.stdout.write(
                    f"{action} {league.name}: {created} teams added, {prioritized} priorities normalized."
                )

        action = "Would repair" if options["dry_run"] else "Repaired"
        self.stdout.write(self.style.SUCCESS(
            f"{action} {repaired_teams} teams and normalized {updated_priorities} waiver priorities."
        ))

    def _repair_league(self, league, dry_run):
        source_teams = list(Team.objects.filter(
            league=league,
            season_year=league.season - 1,
        ).select_related("owner__user"))
        if not source_teams:
            source_teams = list(Team.objects.filter(
                league=league,
                season_year__isnull=True,
            ).select_related("owner__user"))
        if not source_teams:
            return 0, 0

        with transaction.atomic():
            current_teams = list(Team.objects.filter(
                league=league,
                season_year=league.season,
            ).select_related("owner__user"))
            current_names = {team.name for team in current_teams}
            current_owner_ids = {
                team.owner.user_id for team in current_teams if hasattr(team, "owner")
            }
            created = 0

            for source_team in source_teams:
                owner = getattr(source_team, "owner", None)
                if source_team.name in current_names or (owner and owner.user_id in current_owner_ids):
                    continue

                created += 1
                if not dry_run:
                    team = Team.objects.create(
                        league=league,
                        name=source_team.name,
                        season_year=league.season,
                        waiver_priority=max(source_team.waiver_priority, 1),
                    )
                    if owner:
                        FantasyTeamOwner.objects.create(user=owner.user, team=team)
                    current_teams.append(team)
                current_names.add(source_team.name)
                if owner:
                    current_owner_ids.add(owner.user_id)

            if dry_run:
                current_teams += [
                    source_team for source_team in source_teams
                    if source_team.name not in {team.name for team in current_teams}
                ]

            source_priorities = {
                source_team.owner.user_id: source_team.waiver_priority
                for source_team in source_teams
                if hasattr(source_team, "owner") and source_team.waiver_priority > 0
            }
            ordered_teams = sorted(
                current_teams,
                key=lambda team: (
                    source_priorities.get(
                        getattr(getattr(team, "owner", None), "user_id", None),
                        team.waiver_priority if team.waiver_priority > 0 else len(current_teams) + 1,
                    ),
                    team.created_at,
                    team.id,
                ),
            )
            prioritized = sum(
                team.waiver_priority != priority
                for priority, team in enumerate(ordered_teams, start=1)
            )
            if not dry_run:
                for priority, team in enumerate(ordered_teams, start=1):
                    if team.waiver_priority != priority:
                        team.waiver_priority = priority
                        team.save(update_fields=["waiver_priority"])
                if created or prioritized:
                    cache.delete(f"waiver_priority_order:{league.id}")

        return created, prioritized