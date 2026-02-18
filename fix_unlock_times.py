#!/usr/bin/env python
"""Update roster unlock times to Tuesday 9am PT (Tuesday 5pm UTC) for all weeks."""

import os
import django
import pytz

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Week
from datetime import timedelta, datetime
from django.utils import timezone

# PT timezone
pt_tz = pytz.timezone('America/Los_Angeles')

# Get all weeks that have a start_date
weeks = Week.objects.filter(start_date__isnull=False).order_by('season', 'week_number')

print(f"Found {weeks.count()} weeks with start dates")

for week in weeks:
    if week.start_date:
        # Calculate the Tuesday before the week starts
        week_start = week.start_date
        
        # Find how many days from Tuesday (weekday=1)
        day_of_week = week_start.weekday()  # 0=Mon, 4=Fri, 6=Sun
        
        # Calculate days to go back to Tuesday
        # If today is Friday (4), Tuesday is (4-1)=3 days before
        # If today is Monday (0), Tuesday is (0-1)%7=6 days before
        days_back = (day_of_week - 1) % 7
        if days_back == 0:  # week_start is Tuesday
            days_back = 7  # Go back to previous Tuesday
        
        tuesday = week_start - timedelta(days=days_back)
        
        # Set unlock time to Tuesday 9am PT
        # Create naive datetime first
        naive_unlock = datetime.combine(tuesday, datetime.min.time()).replace(hour=9, minute=0)
        # Localize to PT timezone
        expected_unlock_time = pt_tz.localize(naive_unlock)
        
        # Convert to UTC for comparison
        expected_unlock_utc = expected_unlock_time.astimezone(pytz.UTC)
        
        current_unlock = week.roster_unlock_time
        
        if current_unlock != expected_unlock_utc:
            print(f"  Week {week.week_number} (Season {week.season}): {current_unlock} -> {expected_unlock_utc}")
            week.roster_unlock_time = expected_unlock_utc
            week.save()
        else:
            print(f"  Week {week.week_number} (Season {week.season}): OK (already correct)")

print("\nDone!")

