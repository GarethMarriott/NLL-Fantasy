#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Player, Roster

# Find Jake Stevens
jake = Player.objects.get(id=52)

# Show all Jake Stevens roster entries
rosters = Roster.objects.filter(player=jake).order_by('-id')
print(f"Jake Stevens roster entries: {rosters.count()}")
for r in rosters:
    print(f"  ID: {r.id}, Team: {r.team.name}, week_added: {r.week_added}, week_dropped: {r.week_dropped}")
