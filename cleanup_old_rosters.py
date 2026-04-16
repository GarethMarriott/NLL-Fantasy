#!/usr/bin/env python
import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, "/opt/shamrock-fantasy")
django.setup()

from web.models import League, Team, Roster
from django.utils import timezone

print("\n=== CLEANING UP OLD ROSTERS FOR REDRAFT LEAGUES ===\n")

# Find redraft leagues that were renewed (status = active)
redraft_leagues = League.objects.filter(league_type='redraft', status='active')

for league in redraft_leagues:
    print(f"\nProcessing: {league.name} (ID: {league.id}, Current Season: {league.season})")
    print(f"  League Type: {league.league_type}")
    
    # Get all teams for this league
    all_teams = Team.objects.filter(league=league)
    print(f"  Total teams in league: {all_teams.count()}")
    
    # Find old season teams (those with season_year < current season, or NULL if current season is > 1)
    old_teams = Team.objects.filter(
        league=league
    ).exclude(
        season_year=league.season
    )
    
    print(f"  Teams not in current season: {old_teams.count()}")
    
    # Delete rosters from old season teams
    for team in old_teams:
        rosters = Roster.objects.filter(team=team)
        if rosters.exists():
            count = rosters.count()
            rosters.delete()
            print(f"    ✓ Deleted {count} rosters from '{team.name}' (Season {team.season_year})")
        else:
            print(f"    ✓ No rosters to delete from '{team.name}' (Season {team.season_year})")

print("\n=== CLEANUP COMPLETE ===\n")

# Show current state
print("=== CURRENT STATE ===\n")
for league in League.objects.filter(league_type='redraft', status='active'):
    print(f"\n{league.name} (ID: {league.id}, Season: {league.season})")
    for team in Team.objects.filter(league=league):
        rosters = Roster.objects.filter(team=team).count()
        print(f"  Team '{team.name}' (Season {team.season_year}): {rosters} rosters")
