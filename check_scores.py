#!/usr/bin/env python
"""
Check if we have score data in the database
"""
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game

total = Game.objects.count()
with_scores = Game.objects.exclude(home_score__isnull=True, away_score__isnull=True).count()
completed = Game.objects.filter(home_score__isnull=False).count()

print(f"Total games: {total}")
print(f"Games with scores: {with_scores}")
print(f"Games with home_score: {completed}")

if completed > 0:
    print("\nSample completed games:")
    for g in Game.objects.filter(home_score__isnull=False)[:5]:
        print(f"  {g.away_team} {g.away_score} @ {g.home_team} {g.home_score} on {g.date}")
        print(f"    Winner: {g.winner}, Loser: {g.loser}")
else:
    print("\nNo games with scores yet")
