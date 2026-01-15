"""
Management command to create weekly schedule with roster lock/unlock times.
Locks: Friday 5pm PT
Unlocks: Monday 9am PT
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import datetime, timedelta
import pytz
from web.models import Week


class Command(BaseCommand):
    help = 'Create weeks with roster lock/unlock times (Fri 5pm PT / Mon 9am PT)'

    def add_arguments(self, parser):
        parser.add_argument(
            'season',
            type=int,
            help='Season year (e.g., 2026)'
        )
        parser.add_argument(
            '--start-date',
            type=str,
            help='Season start date (YYYY-MM-DD). If not provided, uses Jan 1 of season year.'
        )
        parser.add_argument(
            '--weeks',
            type=int,
            default=18,
            help='Number of weeks in season (default: 18)'
        )

    def handle(self, *args, **options):
        season = options['season']
        num_weeks = options['weeks']
        
        # Parse start date
        if options['start_date']:
            try:
                start_date = datetime.strptime(options['start_date'], '%Y-%m-%d').date()
            except ValueError:
                raise CommandError('Invalid start date format. Use YYYY-MM-DD')
        else:
            start_date = timezone.make_aware(datetime(season, 1, 1)).date()
        
        # Ensure start_date is a Monday (beginning of week)
        days_since_monday = start_date.weekday()
        if days_since_monday != 0:  # If not Monday
            start_date = start_date - timedelta(days=days_since_monday)
            self.stdout.write(
                self.style.WARNING(f'Adjusted start date to Monday: {start_date}')
            )
        
        # Pacific timezone
        pt = pytz.timezone('US/Pacific')
        
        # Create weeks
        created_count = 0
        for week_num in range(1, num_weeks + 1):
            # Calculate week dates (Monday-Sunday)
            week_start = start_date + timedelta(weeks=week_num - 1)
            week_end = week_start + timedelta(days=6)  # Sunday of same week
            
            # Friday of this week at 5pm PT (roster lock)
            friday = week_start + timedelta(days=4)  # Friday is 4 days after Monday
            lock_time_pt = pt.localize(datetime.combine(friday, datetime.min.time().replace(hour=17, minute=0)))
            lock_time_utc = lock_time_pt.astimezone(pytz.UTC)
            
            # Monday of NEXT week at 9am PT (roster unlock)
            next_monday = week_start + timedelta(days=7)
            unlock_time_pt = pt.localize(datetime.combine(next_monday, datetime.min.time().replace(hour=9, minute=0)))
            unlock_time_utc = unlock_time_pt.astimezone(pytz.UTC)
            
            # Create or update week
            week, created = Week.objects.update_or_create(
                season=season,
                week_number=week_num,
                defaults={
                    'start_date': week_start,
                    'end_date': week_end,
                    'roster_lock_time': lock_time_utc,
                    'roster_unlock_time': unlock_time_utc,
                    'is_playoff': False,
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Week {week_num}: {week_start} - {week_end}'
                    )
                )
                self.stdout.write(
                    f'  Lock: Friday {friday} 5pm PT (UTC: {lock_time_utc.strftime("%Y-%m-%d %H:%M")})'
                )
                self.stdout.write(
                    f'  Unlock: Monday {next_monday} 9am PT (UTC: {unlock_time_utc.strftime("%Y-%m-%d %H:%M")})'
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'~ Week {week_num}: Updated (already existed)')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'\n✓ Created {created_count} weeks for {season} season')
        )
