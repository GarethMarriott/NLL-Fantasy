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
    
    # Read games.json
    with zip_file.open('games.json') as f:
        content = json.load(f)
        games = content.get('games', [])
        
        print(f"\nFound {len(games)} games")
        print("\nSample game structure:")
        if games:
            # Find a completed game to show score structure
            for game in games[:10]:
                print(f"\nGame {game.get('id')}:")
                print(json.dumps(game, indent=2))
                break
                
except Exception as e:
    print(f"Error: {e}")
