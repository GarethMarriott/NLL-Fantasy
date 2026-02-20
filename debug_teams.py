#!/usr/bin/env python
"""
Debug script to check what team data looks like from nllstats API
"""
import requests
import json
import io
import zipfile

zip_url = 'https://nllstats.com/json/jsonfiles.zip'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

try:
    print('Downloading data from nllstats...')
    response = requests.get(zip_url, headers=headers, timeout=60)
    response.raise_for_status()

    zip_file = zipfile.ZipFile(io.BytesIO(response.content))
    
    # Check teams.json
    with zip_file.open('teams.json') as f:
        teams_data = json.load(f)['teams']
    
    print("\n=== TEAMS DATA STRUCTURE ===")
    if teams_data:
        print(f"Total teams: {len(teams_data)}")
        print("\nFirst 5 teams:")
        for team in teams_data[:5]:
            print(f"  {team}")
    
    # Check schedule.json
    with zip_file.open('schedule.json') as f:
        schedule_data = json.load(f)['schedule']
    
    print("\n=== SCHEDULE DATA STRUCTURE (2026) ===")
    games_2026 = [g for g in schedule_data if g.get('season') == 2026]
    if games_2026:
        print(f"Total 2026 games: {len(games_2026)}")
        print("\nFirst game structure:")
        game = games_2026[0]
        for key in game:
            print(f"  {key}: {game[key]}")
    else:
        print("No 2026 games found")
        print("\nAvailable seasons:", set(g.get('season') for g in schedule_data))

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
