#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Game

# Check what's actually in the database
total = Game.objects.count()
print(f"Total games in database: {total}")

if total > 0:
    games = Game.objects.all()[:5]
    for g in games:
        print(f"Game {g.id}: '{g.away_team}' @ '{g.home_team}'")
