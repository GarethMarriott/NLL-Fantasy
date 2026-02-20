#!/usr/bin/env python
"""
Check if all schedule team IDs exist in teams mapping
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
    response = requests.get(zip_url, headers=headers, timeout=60)
    response.raise_for_status()
    zip_file = zipfile.ZipFile(io.BytesIO(response.content))
    
    teams_data = json.load(zip_file.open('teams.json'))['teams']
    schedule_data = json.load(zip_file.open('schedule.json'))['schedule']
    
    # Create teams_by_id mapping like the code does
    teams_by_id = {t.get('id'): t.get('team') for t in teams_data}
    
    print(f"Teams in mapping: {len(teams_by_id)}")
    print(f"Team IDs: {sorted(teams_by_id.keys())}")
    
    # Get unique team IDs from 2026 schedule
    games_2026 = [g for g in schedule_data if g.get('season') == 2026]
    schedule_team_ids = set()
    for game in games_2026:
        home_id = game.get('home')
        away_id = game.get('away')
        if home_id:
            schedule_team_ids.add(home_id)
        if away_id:
            schedule_team_ids.add(away_id)
    
    print(f"\nTeam IDs in 2026 schedule: {sorted(schedule_team_ids)}")
    
    # Check which schedule IDs are NOT in teams mapping
    missing = schedule_team_ids - set(teams_by_id.keys())
    if missing:
        print(f"\nMISSING from teams mapping: {sorted(missing)}")
    else:
        print("\n✓ All schedule team IDs are in teams mapping")
    
    # Show what happens when we try to lookup a missing ID
    if missing:
        missing_id = list(missing)[0]
        print(f"\nExample lookup for missing ID {missing_id}:")
        result = teams_by_id.get(missing_id, missing_id)
        print(f"  teams_by_id.get({missing_id}, {missing_id}) = {result}")
        print(f"  → When converted: home_team = {result} (still an ID!)")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
