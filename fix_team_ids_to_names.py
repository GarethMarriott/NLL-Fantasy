#!/usr/bin/env python
import os
import django
import requests
import json
import io
import zipfile

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Game

# Download NLL teams data from API
zip_url = 'https://nllstats.com/json/jsonfiles.zip'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

try:
    print("Downloading NLL team data from API...")
    response = requests.get(zip_url, headers=headers, timeout=60)
    response.raise_for_status()

    zip_file = zipfile.ZipFile(io.BytesIO(response.content))
    
    # Read teams.json and build ID to name mapping
    with zip_file.open('teams.json') as f:
        content = json.load(f)
        teams_data = content.get('teams', [])
        teams_by_id = {t.get('id'): t.get('team') for t in teams_data}
        print(f"Loaded {len(teams_by_id)} teams from API")
    
    # Update all games that have numeric team IDs
    updated_count = 0
    
    for game in Game.objects.all():
        home_updated = False
        away_updated = False
        
        # Check if home_team is a numeric ID
        if game.home_team and str(game.home_team).isdigit():
            team_id = int(game.home_team)
            if team_id in teams_by_id:
                game.home_team = teams_by_id[team_id]
                home_updated = True
        
        # Check if away_team is a numeric ID
        if game.away_team and str(game.away_team).isdigit():
            team_id = int(game.away_team)
            if team_id in teams_by_id:
                game.away_team = teams_by_id[team_id]
                away_updated = True
        
        # Save if either team was updated
        if home_updated or away_updated:
            game.save()
            updated_count += 1
            print(f"Updated Game {game.id}: {game.away_team} @ {game.home_team}")
    
    print(f"\nTotal games updated: {updated_count}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

