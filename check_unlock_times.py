#!/usr/bin/env python
import os
import django
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Week
from django.utils import timezone

now = timezone.now()
print(f"Current UTC time: {now}")
print(f"\nWeeks around now:")

weeks = Week.objects.filter(season=2026).order_by('week_number')
for week in weeks.filter(week_number__gte=12, week_number__lte=14):
    print(f"\nWeek {week.week_number}:")
    print(f"  Start: {week.start_date}")
    print(f"  End: {week.end_date}")
    print(f"  Lock time: {week.roster_lock_time}")
    print(f"  Unlock time: {week.roster_unlock_time}")
    
    if week.roster_unlock_time and week.roster_lock_time:
        if week.roster_unlock_time <= now < week.roster_lock_time:
            print(f"  Status: UNLOCKED (in unlock window)")
        elif now < week.roster_unlock_time:
            print(f"  Status: Locked (waiting to unlock)")
        elif now >= week.roster_lock_time:
            print(f"  Status: Locked (unlock window passed)")
