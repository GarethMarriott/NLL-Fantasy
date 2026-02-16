#!/usr/bin/env python
"""Fix waiver priorities for all teams in all leagues."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Team, League

# For each league, assign waiver priorities based on team names or IDs
for league in League.objects.all():
    teams = list(league.teams.all().order_by('id'))
    print(f"\nLeague: {league.name}")
    print(f"Teams: {len(teams)}")
    
    for idx, team in enumerate(teams, start=1):
        old_priority = team.waiver_priority
        team.waiver_priority = idx
        team.save()
        print(f"  - {team.name}: {old_priority} -> {idx}")

print("\nWaiver priorities fixed!")
