from django.core.cache import cache
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
            league_updated = 0
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
                        league_updated += 1
                if league_updated and not options["dry_run"]:
                    cache.delete(f"waiver_priority_order:{league.id}")
                continue

        action = "Would update" if options["dry_run"] else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} {updated} team waiver priorities."))