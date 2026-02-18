#!/usr/bin/env python
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game
from datetime import date

total = Game.objects.count()
with_scores = Game.objects.filter(home_score__isnull=False).count()
completed_games = Game.objects.filter(date__lt=date(2026, 2, 17))
completed_count = completed_games.count()
completed_with_scores = completed_games.filter(home_score__isnull=False).count()

print(f"Total games: {total}")
print(f"Completed games (before 2026-02-17): {completed_count}")
print(f"Games with scores: {with_scores}")
print(f"Completed games with scores: {completed_with_scores}")

# Show a sample game
sample = completed_games.first()
if sample:
    print(f"\nSample: {sample.away_team} @ {sample.home_team} on {sample.date}")
    print(f"  Scores: {sample.away_score} - {sample.home_score}")
    print(f"  Winner: {sample.winner}")
