#!/usr/bin/env python
"""Fix existing waiver priorities in all leagues - maintain relative order but fix duplicates/gaps."""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Team, League

# For each league, reassign priorities while maintaining relative order
for league in League.objects.all():
    teams = list(league.teams.all().order_by('waiver_priority', 'id'))
    
    if not teams:
        continue
    
    print(f"\nLeague: {league.name} ({len(teams)} teams)")
    
    # Show before
    print("  Before:")
    for team in teams:
        print(f"    {team.name}: {team.waiver_priority}")
    
    # Reassign priorities 1 to N in current order
    for idx, team in enumerate(teams, start=1):
        old_priority = team.waiver_priority
        team.waiver_priority = idx
        team.save()
    
    # Show after
    print("  After:")
    teams = list(league.teams.all().order_by('waiver_priority'))
    for team in teams:
        print(f"    {team.name}: {team.waiver_priority}")

print("\n✓ Waiver priorities fixed!")
