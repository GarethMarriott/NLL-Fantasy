#!/usr/bin/env python
"""
Update game scores directly from NLL API without using update_or_create
This is faster and avoids duplicate games
"""
import os
import sys
import django
import requests
from datetime import datetime, date

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game, Week

# Download the JSON data
def fetch_from_nll():
    try:
        print("Downloading NLL games data...")
        resp = requests.get("https://nllapiserver.azurewebsites.net/api/schedule?season=2026")
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Error downloading: {e}")
    return None

data = fetch_from_nll()
if not data:
    print("Failed to fetch data")
    sys.exit(1)

# Extract team mapping
teams_by_id = {}
if 'teams' in data:
    for team in data['teams']:
        team_id = team.get('id')
        team_name = team.get('team')  # Use 'team' field, not 'name'
        if team_id and team_name:
            teams_by_id[team_id] = team_name
            print(f"  Team ID {team_id}: {team_name}")

# Update each game
updates_made = 0
if 'schedule' in data:
    for week_data in data['schedule']:
        week_num = week_data.get('week')
        games = week_data.get('games', [])
        
        for game in games:
            game_id = game.get('id')
            home_team_id = game.get('home')
            away_team_id = game.get('away')
            date_str = game.get('date')
            home_score = game.get('home_score')
            away_score = game.get('away_score')
            winner_id = game.get('winner')
            loser_id = game.get('loser')
            
            # Convert IDs to names
            home_team_name = teams_by_id.get(home_team_id, str(home_team_id))
            away_team_name = teams_by_id.get(away_team_id, str(away_team_id))
            winner_name = teams_by_id.get(winner_id) if winner_id else None
            loser_name = teams_by_id.get(loser_id) if loser_id else None
            
            # Try to parse date
            game_date = None
            try:
                if date_str and ' ' in date_str and ':' in date_str:
                    date_part = ' '.join(date_str.split()[:3])
                    game_date = datetime.strptime(date_part, '%b %d, %Y').date()
            except:
                pass
            
            # Find games by date and team IDs (since they might currently be stored as IDs)
            # Try to find with team IDs first, then by names
            game_obj = None
            if game_date:
                #  Try matching by date + IDs
                game_obj = Game.objects.filter(
                    date=game_date,
                    home_team__in=[str(home_team_id), home_team_name],
                    away_team__in=[str(away_team_id), away_team_name]
                ).first()
            
            if game_obj:
                # Update the game with scores and names
                game_obj.home_team = home_team_name
                game_obj.away_team = away_team_name
                game_obj.home_score = home_score
                game_obj.away_score = away_score
                game_obj.winner = winner_name
                game_obj.loser = loser_name
                game_obj.save()
                updates_made += 1
                if updates_made <= 5:
                    print(f"✓ Updated: {away_team_name} @ {home_team_name} ({home_score}-{away_score})")

print(f"\nTotal updates: {updates_made}")
