#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Player, Roster, Team, League
from django.utils import timezone

# Find Jake Stevens
jake = Player.objects.get(id=52)  # We know this from previous query
print(f"Player: {jake.first_name} {jake.last_name}")

# Find the Goon(er)s team
team = Team.objects.filter(name__icontains="Goon").first()
league = team.league if team else None
print(f"Team: {team.name}, League: {league.name if league else 'None'}")

# Try to create a new roster entry
try:
    new_roster = Roster.objects.create(
        player=jake,
        team=team,
        league=league,
        week_added=11
    )
    print(f"SUCCESS: Created roster entry ID {new_roster.id}")
    
    # Verify it was created
    verify = Roster.objects.filter(player=jake, team=team, league=league, week_added=11).first()
    print(f"Verification: {verify}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
