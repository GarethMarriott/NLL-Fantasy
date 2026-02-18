#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Game
from web.constants import TEAM_ID_TO_NAME

# Update all games that have numeric team IDs
updated_count = 0

for game in Game.objects.all():
    home_updated = False
    away_updated = False
    
    # Check if home_team is a numeric ID
    if game.home_team and str(game.home_team).isdigit():
        team_id = int(game.home_team)
        if team_id in TEAM_ID_TO_NAME:
            game.home_team = TEAM_ID_TO_NAME[team_id]
            home_updated = True
    
    # Check if away_team is a numeric ID
    if game.away_team and str(game.away_team).isdigit():
        team_id = int(game.away_team)
        if team_id in TEAM_ID_TO_NAME:
            game.away_team = TEAM_ID_TO_NAME[team_id]
            away_updated = True
    
    # Save if either team was updated
    if home_updated or away_updated:
        game.save()
        updated_count += 1
        print(f"Updated Game {game.id}: {game.away_team} @ {game.home_team}")

print(f"\nTotal games updated: {updated_count}")
