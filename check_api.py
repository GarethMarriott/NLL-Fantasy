#!/usr/bin/env python
"""
Check if NLL API returns score data
"""
import requests

resp = requests.get("https://nllapiserver.azurewebsites.net/api/schedule?season=2026")
data = resp.json()

if 'schedule' in data:
    for week in data['schedule'][:1]:  # Just check first week
        print(f"Week {week.get('week')} games:")
        for game in week.get('games', [])[:3]:
            print(f"  Game ID {game.get('id')} on {game.get('date')}")
            print(f"    Home: {game.get('home')} ({game.get('home_team', 'N/A')})")
            print(f"    Away: {game.get('away')} ({game.get('away_team', 'N/A')})")
            print(f"    Scores: {game.get('home_score', 'NONE')} - {game.get('away_score', 'NONE')}")
            print(f"    Winner: {game.get('winner')}, Loser: {game.get('loser')}")
            print()
