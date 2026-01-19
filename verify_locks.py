#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Week

for week_num in [1, 9, 10, 21]:
    try:
        w = Week.objects.get(week_number=week_num, season=2026)
        print(f"Week {week_num}: Lock={w.roster_lock_time}, Unlock={w.roster_unlock_time}")
    except Week.DoesNotExist:
        print(f"Week {week_num}: Not found")
