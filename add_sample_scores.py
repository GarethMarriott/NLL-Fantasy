#!/usr/bin/env python
"""
Add sample scores to a couple of games for testing
"""
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game
from datetime import date

# Add scores to the first few completed games
count = 0
for game in Game.objects.filter(date__lt=date(2026, 2, 17)).order_by('date')[:5]:
    game.home_score = 12
    game.away_score = 11
    # Make the home team the winner
    game.winner = game.home_team
    game.loser = game.away_team
    game.save()
    count += 1
    print(f"Added scores to: {game.away_team} @ {game.home_team} ({game.away_score}-{game.home_score})")

print(f"\nTotal games updated: {count}")

# Verify
scored = Game.objects.filter(home_score__isnull=False).count()
print(f"Games with scores now: {scored}")
