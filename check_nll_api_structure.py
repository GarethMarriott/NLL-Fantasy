#!/usr/bin/env python
import requests
import json

resp = requests.get("https://nllapiserver.azurewebsites.net/api/schedule?season=2026")
if resp.status_code == 200:
    data = resp.json()
    # Show structure
    if 'schedule' in data and len(data['schedule']) > 0:
        week = data['schedule'][0]
        if 'games' in week and len(week['games']) > 0:
            game = week['games'][0]
            print("First game:")
            print(f"  id: {game.get('id')}")
            print(f"  home: {game.get('home')}")
            print(f"  home_team: {game.get('home_team')}")
            print(f"  away: {game.get('away')}")
            print(f"  away_team: {game.get('away_team')}")
            print(f"  home_score: {game.get('home_score')}")
            print(f"  away_score: {game.get('away_score')}")
            print(f"  winner: {game.get('winner')}")
            print(f"  loser: {game.get('loser')}")
            
            # Count games with scores
            teams_data = data.get('teams', [])
            scored_count = 0
            for w in data.get('schedule', []):
                for g in w.get('games', []):
                    if g.get('home_score') is not None:
                        scored_count += 1
            total_games = sum(len(w.get('games', [])) for w in data.get('schedule', []))
            print(f"\n  Total games: {total_games}")
            print(f"  Games with scores: {scored_count}")
else:
    print(f"API Error: {resp.status_code}")
