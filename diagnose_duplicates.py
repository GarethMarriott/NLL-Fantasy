#!/usr/bin/env python
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game
from collections import Counter

# Count games by home team type
home_teams = Counter()
away_teams = Counter()
total_by_type = {"names": 0, "ids": 0}

for game in Game.objects.all():
    home_teams[game.home_team] += 1
    away_teams[game.away_team] += 1
    
    if game.home_team.isdigit() or game.away_team.isdigit():
        total_by_type["ids"] += 1
    else:
        total_by_type["names"] += 1

print("Total games by type:")
print(f"  With team names: {total_by_type['names']}")
print(f"  With team IDs: {total_by_type['ids']}")

print(f"\nUnique home teams: {len(home_teams)}")
print("Top 10 most common home teams:")
for team, count in home_teams.most_common(10):
    team_type = "ID" if team.isdigit() else "NAME"
    print(f"  {team} ({team_type}): {count}")
