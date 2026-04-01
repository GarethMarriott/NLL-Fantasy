#!/usr/bin/env python3
"""Remove duplicate games created with numeric team IDs"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Game

# Find all games
all_games = Game.objects.all().order_by('date')

# Group games by date and scores to find duplicates
game_groups = {}
for game in all_games:
    key = (game.date, game.home_score, game.away_score)
    if key not in game_groups:
        game_groups[key] = []
    game_groups[key].append(game)

# Find and remove duplicates (keep the one with team names)
removed = 0
for key, games in game_groups.items():
    if len(games) > 1:
        # Sort: keep ones with non-numeric team names first
        games_sorted = sorted(games, key=lambda g: (
            str(g.home_team).isdigit(),
            str(g.away_team).isdigit()
        ))
        
        # Keep the first (named) game, remove others
        keeper = games_sorted[0]
        for game_to_delete in games_sorted[1:]:
            print(f"Removing duplicate: {game_to_delete.home_team} @ {game_to_delete.away_team} ({game_to_delete.date}) ID:{game_to_delete.id}")
            game_to_delete.delete()
            removed += 1

print(f"\nCleanup complete: Removed {removed} duplicate games")

# Summary
total = Game.objects.count()
with_names = Game.objects.exclude(home_team__regex=r'^\d+$').count()
with_ids = Game.objects.filter(home_team__regex=r'^\d+$').count()

print(f"\nSummary:")
print(f"  Total games: {total}")
print(f"  Games with team names: {with_names}")
print(f"  Games with numeric IDs: {with_ids}")
