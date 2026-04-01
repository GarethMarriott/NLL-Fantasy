#!/usr/bin/env python
"""Debug MAFFL playoff display."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import League, Week
from django.utils import timezone

league = League.objects.filter(name__iexact='MAFFL').first() or League.objects.filter(name__iexact='MAFLL').first()
if league:
    print(f'League: {league.name}')
    print(f'Playoff weeks: {league.playoff_weeks}')
    print(f'Playoff teams: {league.playoff_teams}')
    print(f'Playoff start week: {league.get_playoff_start_week()}')
    
    # Check how many weeks have been completed
    lat_week = Week.objects.order_by('-season', '-week_number').first()
    season = lat_week.season if lat_week else 2026
    print(f'Current season: {season}')
    
    today = timezone.now().date()
    completed = Week.objects.filter(season=season, end_date__lt=today).order_by('week_number')
    if completed.exists():
        max_week = completed.last().week_number
        print(f'Completed weeks: 1-{max_week}')
        print(f'Regular season ends at week: {21 - league.playoff_weeks}')
        season_ended = max_week >= (21 - league.playoff_weeks)
        print(f'Season ended: {season_ended}')
    else:
        print('No completed weeks yet')
else:
    print('MAFFL league not found')
