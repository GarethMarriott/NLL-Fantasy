"""
Management command to clean up empty game records (games with no player stats).
This prevents duplicate/empty games from inflating player stat views.
"""
from django.core.management.base import BaseCommand
from web.models import Game


class Command(BaseCommand):
    help = 'Delete empty game records (games with no player stats) for a season'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            required=True,
            help='Season to clean up'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without deleting'
        )

    def handle(self, *args, **options):
        season = options['season']
        dry_run = options.get('dry_run', False)
        
        # Find games with no player stats
        empty_games = Game.objects.filter(
            week__season=season,
            player_stats__isnull=True
        )
        
        count = empty_games.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS(f'No empty games found for season {season}'))
            return
        
        if dry_run:
            self.stdout.write(f'[DRY RUN] Would delete {count} empty game records for season {season}')
            
            # Show distribution by week
            from django.db.models import Count
            by_week = (empty_games
                .values('week__week_number')
                .annotate(count=Count('id'))
                .order_by('week__week_number'))
            
            for row in by_week:
                self.stdout.write(f'  Week {row["week__week_number"]}: {row["count"]} games')
        else:
            self.stdout.write(f'Deleting {count} empty game records for season {season}...')
            deleted_count, details = empty_games.delete()
            self.stdout.write(self.style.SUCCESS(f'Deleted {deleted_count} records'))
