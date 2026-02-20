#!/usr/bin/env python
"""
Diagnose current game state and duplicates
"""
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game
from collections import defaultdict

# Count total games
total = Game.objects.count()
print(f"Total games: {total}\n")

# Find duplicates - same date, same teams
game_keys = defaultdict(list)
for game in Game.objects.all().order_by('date', 'home_team', 'away_team'):
    key = (game.date, game.home_team, game.away_team)
    game_keys[key].append({
        'id': game.id,
        'home': game.home_team,
        'away': game.away_team,
        'date': game.date,
        'nll_game_id': game.nll_game_id,
        'home_score': game.home_score,
        'away_score': game.away_score
    })

# Report duplicates
duplicates = {k: v for k, v in game_keys.items() if len(v) > 1}
if duplicates:
    print(f"Found {len(duplicates)} duplicate game matchups:\n")
    for (date, home, away), games_list in list(duplicates.items())[:5]:
        print(f"{away} @ {home} on {date}:")
        for game in games_list:
            print(f"  ID {game['id']}: nll_game_id={game['nll_game_id']}, scores={game['away_score']}-{game['home_score']}")
        print()
    if len(duplicates) > 5:
        print(f"... and {len(duplicates) - 5} more duplicates")
else:
    print("No duplicate game matchups found")

# Check for games with numeric team IDs
numeric_teams = sum(1 for g in Game.objects.all() if g.home_team.isdigit() or g.away_team.isdigit())
print(f"\nGames with numeric team IDs: {numeric_teams}")

# Sample some games
print("\nSample games:")
for game in Game.objects.all().order_by('date')[:5]:
    print(f"  {game.away_team} @ {game.home_team} on {game.date} (nll_id={game.nll_game_id})")
