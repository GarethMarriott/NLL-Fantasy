#!/usr/bin/env python
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game
from datetime import date

# Count games by type
games_by_home_team = {}
for game in Game.objects.all():
    if game.home_team not in games_by_home_team:
        games_by_home_team[game.home_team] = 0
    games_by_home_team[game.home_team] += 1

print("Games grouped by home_team:")
for team, count in sorted(games_by_home_team.items(), key=lambda x: x[1], reverse=True)[:20]:
    print(f"  {team}: {count}")

# Check for duplicate games on same date
from django.db.models import Count
duplicates = Game.objects.values('date', 'home_team', 'away_team').annotate(count=Count('id')).filter(count__gt=1)
print(f"\nDuplicate games (same date/teams): {duplicates.count()}")
for dup in duplicates[:5]:
    print(f"  {dup}")

# Check for games with scores
scored = Game.objects.filter(home_score__isnull=False).count()
print(f"\nGames with home_score set: {scored}")

# Check sample game details
first_with_id = Game.objects.filter(home_team__regex=r'^\d+$').first()
if first_with_id:
    print(f"\nFirst game with team ID: {first_with_id.away_team} @ {first_with_id.home_team} on {first_with_id.date}")
    print(f"  nll_game_id: {first_with_id.nll_game_id}")
    print(f"  Scores: {first_with_id.away_score}-{first_with_id.home_score}")

first_with_name = Game.objects.filter(home_team='Toronto Rock').first()
if first_with_name:
    print(f"\nFirst game with team name: {first_with_name.away_team} @ {first_with_name.home_team} on {first_with_name.date}")
    print(f"  nll_game_id: {first_with_name.nll_game_id}")
    print(f"  Scores: {first_with_name.away_score}-{first_with_name.home_score}")
