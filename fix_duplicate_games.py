#!/usr/bin/env python
"""Remove duplicate games from database"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Game
from django.db.models import Count

# Find duplicate games
dupes = Game.objects.values('week', 'home_team', 'away_team', 'date').annotate(count=Count('id')).filter(count__gt=1)

print(f'Found {len(list(dupes))} sets of duplicate games')

# Delete duplicates (keep first, delete rest)
for dup in dupes:
    games = Game.objects.filter(
        week=dup['week'],
        home_team=dup['home_team'],
        away_team=dup['away_team'],
        date=dup['date']
    ).order_by('id')
    
    if games.count() > 1:
        print(f"Deleting {games.count()-1} duplicate(s) for {dup['home_team']} vs {dup['away_team']} on {dup['date']}")
        # Delete all but the first
        first_id = games.first().id
        Game.objects.filter(
            week=dup['week'],
            home_team=dup['home_team'],
            away_team=dup['away_team'],
            date=dup['date']
        ).exclude(id=first_id).delete()

print('Done - duplicates removed')
