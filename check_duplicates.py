#!/usr/bin/env python
"""
Check for duplicate games with team IDs vs team names
"""
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game
from collections import defaultdict

# Count games by type
total = Game.objects.count()
with_names = sum(1 for g in Game.objects.all() if not g.home_team.isdigit() and not g.away_team.isdigit())
with_ids = sum(1 for g in Game.objects.all() if g.home_team.isdigit() or g.away_team.isdigit())

print(f"Total games: {total}")
print(f"Games with team names: {with_names}")
print(f"Games with team IDs: {with_ids}")
print()

# Show samples of both types
print("Sample games with IDs:")
for g in Game.objects.filter(home_team__regex=r'^\d+$')[:5]:
    print(f"  {g.id}: {g.away_team} @ {g.home_team} on {g.date}")

print()
print("Sample games with names:")
for g in Game.objects.exclude(home_team__regex=r'^\d+$')[:5]:
    print(f"  {g.id}: {g.away_team} @ {g.home_team} on {g.date}")

print()
print("Checking for date+team duplicates:")
# Find potential duplicates by date
date_teams = defaultdict(list)
for g in Game.objects.all():
    key = (g.date, g.away_team, g.home_team)
    date_teams[key].append(g)

duplicates = {k: v for k, v in date_teams.items() if len(v) > 1}
if duplicates:
    print(f"Found {len(duplicates)} potential duplicates:")
    for (date, away, home), games in list(duplicates.items())[:5]:
        print(f"  {away} @ {home} on {date}: {len(games)} games")
        for g in games:
            print(f"    ID {g.id}")
else:
    print("No duplicates found by date+teams")
