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
        
        if teams:
            print("Sample team structure:")
            print(json.dumps(teams[0], indent=2))
                
except Exception as e:
    print(f"Error: {e}")
