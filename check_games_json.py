#!/usr/bin/env python
"""
Check what score data is available in games.json
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
    
    games_data = json.load(zip_file.open('games.json'))['games']
    
    # Find games from 2026 with scores
    games_2026_with_scores = []
    for game in games_data:
        if game.get('season') == 2026 and (game.get('home_score') is not None or game.get('away_score') is not None):
            games_2026_with_scores.append(game)
    
    print(f"Total games in games.json: {len(games_data)}")
    print(f"Games from 2026: {len([g for g in games_data if g.get('season') == 2026])}")
    print(f"Games from 2026 with scores: {len(games_2026_with_scores)}")
    
    if games_2026_with_scores:
        print("\nFirst 5 games with scores:")
        for game in games_2026_with_scores[:5]:
            print(f"\n  Game ID {game.get('id')}:")
            print(f"    Season: {game.get('season')}")
            print(f"    Home: {game.get('home')} Score: {game.get('home_score')}")
            print(f"    Away: {game.get('away')} Score: {game.get('away_score')}")
            print(f"    Winner: {game.get('winner')}, Loser: {game.get('loser')}")
            print(f"    Date: {game.get('dt')}")
            print(f"    All keys: {list(game.keys())}")
    else:
        print("\nNo games with scores found in games.json for 2026")
        # Show sample structure
        sample_games = [g for g in games_data if g.get('season') == 2026]
        if sample_games:
            print("\nSample 2026 game from games.json:")
            for key in sample_games[0]:
                print(f"  {key}: {sample_games[0][key]}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
