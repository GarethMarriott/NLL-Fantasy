#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Game

# Check what's stored in Game model
games = Game.objects.all()[:10]
print("Sample games from database:")
for g in games:
    print(f"  {g.id}: '{g.away_team}' @ '{g.home_team}'")

# Check if they're numeric
if games:
    first = games[0]
    print(f"\nFirst game away_team type: {type(first.away_team)}")
    print(f"First game away_team value: '{first.away_team}'")
    print(f"Is digit: {first.away_team.isdigit() if isinstance(first.away_team, str) else 'N/A'}")
