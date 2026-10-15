from django.core.management.base import BaseCommand

from web.models import League, Team


class Command(BaseCommand):
    help = "Restore waiver priorities in renewed leagues from the preceding season."

    def add_arguments(self, parser):
        parser.add_argument("--league-id", type=int, action="append")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        leagues = League.objects.filter(use_waivers=True)
        if options["league_id"]:
            leagues = leagues.filter(id__in=options["league_id"])

        updated = 0
        for league in leagues.order_by("id"):
            current_teams = list(Team.objects.filter(
                league=league,
                season_year=league.season,
            ).order_by("created_at", "id"))
            if not current_teams:
                continue

            current_priorities = {team.waiver_priority for team in current_teams}
            if len(current_priorities) == 1:
                total_teams = len(current_teams)
                for index, team in enumerate(current_teams, start=1):
                    priority = total_teams - index + 1
                    if team.waiver_priority != priority:
                        self.stdout.write(
                            f"{league.name}: {team.name} {team.waiver_priority} -> {priority}"
                        )
                        if not options["dry_run"]:
                            team.waiver_priority = priority
                            team.save(update_fields=["waiver_priority"])
                        updated += 1
                continue

            previous_team_queryset = Team.objects.filter(
                league=league,
                season_year=league.season - 1,
            )
            if not previous_team_queryset.exists():
                previous_team_queryset = Team.objects.filter(
                    league=league,
                    season_year__isnull=True,
                )

            previous_teams = {
                team.name: team
                for team in previous_team_queryset
            }

            for team in current_teams:
                previous_team = previous_teams.get(team.name)
                if previous_team and team.waiver_priority != previous_team.waiver_priority:
                    self.stdout.write(
                        f"{league.name}: {team.name} {team.waiver_priority} -> "
                        f"{previous_team.waiver_priority}"
                    )
                    if not options["dry_run"]:
                        team.waiver_priority = previous_team.waiver_priority
                        team.save(update_fields=["waiver_priority"])
                    updated += 1

        action = "Would update" if options["dry_run"] else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} {updated} team waiver priorities."))