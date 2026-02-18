#!/usr/bin/env python
import requests
import json
import io
import zipfile

# Download the JSON data
zip_url = 'https://nllstats.com/json/jsonfiles.zip'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

try:
    print("Downloading NLL data...")
    response = requests.get(zip_url, headers=headers, timeout=60)
    response.raise_for_status()

    zip_file = zipfile.ZipFile(io.BytesIO(response.content))
    
    # Read teams.json
    with zip_file.open('teams.json') as f:
        content = json.load(f)
        teams = content.get('teams', [])
        
        print(f"\nFound {len(teams)} teams:")
        for team in teams[:5]:
            print(f"  ID: {team.get('id')}, Name: {team.get('name')}, City: {team.get('city')}")
        
        # Check that these IDs match what's in the database
        sample_ids = ['896', '918', '870', '867']
        print(f"\nLooking for teams with IDs: {sample_ids}")
        for team in teams:
            if str(team.get('id')) in sample_ids:
                print(f"  Found: ID {team.get('id')} = {team.get('name')}")
                
except Exception as e:
    print(f"Error: {e}")
