#!/usr/bin/env python
"""Update roster unlock times from Monday to Tuesday for weeks that need it."""

import os
import django
import pytz

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Week
from datetime import timedelta
from django.utils import timezone

# Get all weeks that have an unlock_time set
weeks = Week.objects.filter(roster_unlock_time__isnull=False).order_by('season', 'week_number')

print(f"Found {weeks.count()} weeks with unlock times")

for week in weeks:
    if week.roster_unlock_time:
        # Get the lock time (Friday first game)
        lock_time = week.roster_lock_time
        unlock_time = week.roster_unlock_time
        
        # If unlock time is on Monday, move it to Tuesday 9am PT (Tuesday 5pm UTC)
        # Monday 9am PT (5pm UTC) is day 0, Tuesday 9am PT is day 1
        # Check if the unlock time is a Monday by looking at the day of week (0=Monday, 1=Tuesday, etc)
        
        unlock_day_of_week = unlock_time.weekday()  # Returns 0-6 (Monday=0, Tuesday=1, etc)
        lock_day_of_week = lock_time.weekday()
        
        # The lock time is Friday 7pm PT (Saturday 2am UTC)
        # The unlock should be Tuesday 9am PT (Tuesday 5pm UTC)
        # Friday to Tuesday going backwards is 3 days
        # Calculate what the unlock time should be: Tuesday 9am PT (Tuesday 5pm UTC)
        if lock_time:
            # Lock time is on the first game day (Friday)
            # Subtract 3 days to get to Tuesday
            expected_unlock_date = lock_time.date() - timedelta(days=3)
            expected_unlock_time = lock_time.replace(
                year=expected_unlock_date.year,
                month=expected_unlock_date.month,
                day=expected_unlock_date.day
            )
            
            if unlock_time != expected_unlock_time:
                print(f"  Week {week.week_number} (Season {week.season}): {unlock_time} -> {expected_unlock_time}")
                week.roster_unlock_time = expected_unlock_time
                week.save()
            else:
                print(f"  Week {week.week_number} (Season {week.season}): OK (already Tuesday)")

print("\nDone!")
