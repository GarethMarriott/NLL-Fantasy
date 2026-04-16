#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import League, Team, LeagueHistory
from django.db.models import Count

# Find leagues that might be duplicates based on name
duplicates_by_name = League.objects.values('name').annotate(count=Count('id')).filter(count__gt=1)
print(f"Leagues with duplicate names: {list(duplicates_by_name)}")

# Find all leagues with LeagueHistory (archives)
archived_leagues = League.objects.filter(season_archives__isnull=False).distinct()
print(f"\nLeagues with archives (LeagueHistory records): {archived_leagues.count()}")
for league in archived_leagues:
    archives = league.season_archives.all()
    print(f"  - {league.name} (ID: {league.id}): {archives.count()} archived seasons")
    for archive in archives:
        print(f"      Season {archive.season_year}: {archive.archived_at}")

# List all leagues
print(f"\nAll Leagues in Database:")
for league in League.objects.all():
    teams = Team.objects.filter(league=league).distinct().count()
    archives = league.season_archives.count()
    print(f"  ID: {league.id}, Name: {league.name}, Commissioner: {league.commissioner.username}, Teams: {teams}, Season: {league.season}, Status: {league.status}, Archives: {archives}")

# Check for leagues with same name but different IDs and commissioners
print(f"\nLeagues grouped by name:")
league_names = {}
for league in League.objects.all():
    if league.name not in league_names:
        league_names[league.name] = []
    league_names[league.name].append(league)

for name, leagues in league_names.items():
    if len(leagues) > 1:
        print(f"\n  '{name}' appears {len(leagues)} times:")
        for l in leagues:
            print(f"    - ID: {l.id}, Commissioner: {l.commissioner.username}, Season: {l.season}, Status: {l.status}, Created: {l.created_at}")
    elif len(leagues) == 1:
        print(f"\n  '{name}' (ID: {leagues[0].id}) - OK")
