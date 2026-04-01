#!/usr/bin/env python3
"""Remove all games with numeric team IDs"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Game

# Remove all games with numeric IDs
id_games = Game.objects.filter(home_team__regex=r'^\d+$')
count = id_games.count()

print(f"Removing {count} games with numeric team IDs...")
for game in id_games:
    print(f"  Deleting: {game.home_team} @ {game.away_team} ({game.date})")
    game.delete()

print(f"\nCleanup complete: Removed {count} games")

# Summary
total = Game.objects.count()
with_ids = Game.objects.filter(home_team__regex=r'^\d+$').count()

print(f"\nSummary:")
print(f"  Total games remaining: {total}")
print(f"  Games still with numeric IDs: {with_ids}")
