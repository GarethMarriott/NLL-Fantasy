#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import League, Team, LeagueHistory
from django.db.models import Count

# Find leagues that might be duplicates based on name
duplicates_by_name = League.objects.values('name').annotate(count=Count('id')).filter(count__gt=1)
print("Leagues with duplicate names:", list(duplicates_by_name))

# Find all leagues with LeagueHistory (archives)
archived_leagues = League.objects.filter(season_archives__isnull=False).distinct()
print("\nLeagues with archives (LeagueHistory records):", archived_leagues.count())
for league in archived_leagues:
    archives = league.season_archives.all()
    print(f"  - {league.name} (ID: {league.id}): {archives.count()} archived seasons")
    for archive in archives:
        print(f"      Season {archive.season_year}: {archive.archived_at}")

# List all leagues
print("\nAll Leagues in Production Database:")
for league in League.objects.all().order_by('name', 'created_at'):
    teams = Team.objects.filter(league=league).distinct().count()
    print(f"  ID: {league.id}, Name: {league.name}, Commissioner: {league.commissioner.username}, Season: {league.season}, Status: {league.status}, Created: {league.created_at}")

# Check for leagues with same name but different IDs
print("\n\nLeagues grouped by name:")
league_names = {}
for league in League.objects.all():
    if league.name not in league_names:
        league_names[league.name] = []
    league_names[league.name].append(league)

for name, leagues in sorted(league_names.items()):
    if len(leagues) > 1:
        print(f"\n  WARNING: '{name}' appears {len(leagues)} times:")
        for l in sorted(leagues, key=lambda x: x.created_at):
            print(f"    - ID: {l.id}, Commissioner: {l.commissioner.username}, Season: {l.season}, Status: {l.status}, Created: {l.created_at}")
