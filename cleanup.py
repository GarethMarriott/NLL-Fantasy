#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Roster

# Delete the test roster entry we just created
Roster.objects.filter(id=61).delete()
print("Deleted test roster entry 61")

# Show all Jake Stevens roster entries again
from web.models import Player
jake = Player.objects.get(id=52)
rosters = Roster.objects.filter(player=jake)
print(f"\nJake Stevens roster entries: {rosters.count()}")
for r in rosters:
    print(f"  ID: {r.id}, Team: {r.team.name}, week_added: {r.week_added}, week_dropped: {r.week_dropped}")
