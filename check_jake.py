#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Player, Roster
from django.utils import timezone

# Find Jake Stevens
jake = Player.objects.filter(first_name__icontains='Jake', last_name__icontains='Stevens').first()
if jake:
    print(f"Jake Stevens ID: {jake.id}")
    # Check if he's on any roster
    rosters = Roster.objects.filter(player=jake)
    print(f"Total Roster entries for Jake Stevens: {rosters.count()}")
    for r in rosters:
        print(f"  ID: {r.id}, Team: {r.team.name}, League: {r.league.name}, week_added: {r.week_added}, week_dropped: {r.week_dropped}")
    
    # Check specifically for active entries
    active = Roster.objects.filter(player=jake, week_dropped__isnull=True)
    print(f"\nActive roster entries for Jake Stevens: {active.count()}")
    for r in active:
        print(f"  ID: {r.id}, Team: {r.team.name}, League: {r.league.name}, week_added: {r.week_added}")
else:
    print("Jake Stevens not found")

