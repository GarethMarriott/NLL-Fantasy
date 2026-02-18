from django.core.management.base import BaseCommand
from django.core.cache import cache


class Command(BaseCommand):
    help = 'Clear NLL schedule cache for all seasons'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            help='Specific season to clear, or all if not specified',
        )

    def handle(self, *args, **options):
        season = options.get('season')
        
        if season:
            cache_key = f'nll_schedule:{season}'
            cache.delete(cache_key)
            self.stdout.write(
                self.style.SUCCESS(f'Cleared cache for season {season}')
            )
        else:
            # Clear all potential nll_schedule cache keys
            # Since Redis doesn't have a direct way to search by pattern without connection,
            # we'll clear the most common ones
            for season in range(2020, 2030):
                cache_key = f'nll_schedule:{season}'
                cache.delete(cache_key)
            
            self.stdout.write(
                self.style.SUCCESS('Cleared NLL schedule cache for all seasons (2020-2029)')
            )
