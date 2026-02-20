#!/usr/bin/env python
"""
Delete all games that have team IDs instead of names
"""
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game

# Find and delete all games with team IDs
deleted = 0
for game in Game.objects.all():
    if game.home_team.isdigit() or game.away_team.isdigit():
        print(f"Deleting: {game.away_team} @ {game.home_team} on {game.date}")
        game.delete()
        deleted += 1

print(f"\nTotal deleted: {deleted}")

# Verify cleanup
remaining = Game.objects.count()
with_ids = sum(1 for g in Game.objects.all() if g.home_team.isdigit() or g.away_team.isdigit())
print(f"Remaining games: {remaining}")
print(f"Games with IDs remaining: {with_ids}")

if with_ids == 0:
    print("✓ All duplicate games with IDs have been removed!")
