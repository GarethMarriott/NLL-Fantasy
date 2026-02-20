#!/usr/bin/env python
"""
Check if the NLL API returns score data
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
    
    schedule_data = json.load(zip_file.open('schedule.json'))['schedule']
    
    # Find games with scores
    games_with_scores = []
    for game in schedule_data:
        if game.get('season') == 2026 and (game.get('home_score') is not None or game.get('away_score') is not None):
            games_with_scores.append(game)
    
    print(f"Total 2026 games: {len([g for g in schedule_data if g.get('season') == 2026])}")
    print(f"Games with scores: {len(games_with_scores)}")
    
    if games_with_scores:
        print("\nFirst 5 games with scores:")
        for game in games_with_scores[:5]:
            print(f"\n  Game ID {game.get('id')}:")
            print(f"    Away: {game.get('away')} Score: {game.get('away_score')}")
            print(f"    Home: {game.get('home')} Score: {game.get('home_score')}")
            print(f"    Winner: {game.get('winner')}, Loser: {game.get('loser')}")
            print(f"    All keys: {list(game.keys())}")
    else:
        print("\nNo games with scores found")
        # Show a sample game to see available fields
        sample_games = [g for g in schedule_data if g.get('season') == 2026]
        if sample_games:
            print("\nSample 2026 game structure:")
            for key in sample_games[0]:
                print(f"  {key}: {sample_games[0][key]}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
