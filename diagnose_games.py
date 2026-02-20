#!/usr/bin/env python
"""
Check for games with numeric team IDs vs names
"""
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game

total = Game.objects.count()
with_names = sum(1 for g in Game.objects.all() if not g.home_team.isdigit() and not g.away_team.isdigit())
with_ids = sum(1 for g in Game.objects.all() if g.home_team.isdigit() or g.away_team.isdigit())

print(f"Total games: {total}")
print(f"Games with team names: {with_names}")
print(f"Games with team IDs: {with_ids}")

if with_ids > 0:
    print("\nGames with IDs (sample):")
    for g in Game.objects.filter(home_team__regex=r'^\d+$')[:5]:
        print(f"  {g.id}: {g.away_team} @ {g.home_team} on {g.date} (Score: {g.away_score} @ {g.home_score})")
