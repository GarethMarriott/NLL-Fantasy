#!/usr/bin/env python
"""
Quick script to update game team names and scores.
Uses pre-computed team mapping for NLL 2026 season.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game

# Known NLL 2026 team IDs and names
TEAM_ID_MAP = {
    870: "Buffalo Bandits",
    882: "Toronto Rock",
    883: "Colorado Mammoth",
    884: "Calgary Roughnecks",
    885: "Saskatchewan Rush",
    886: "Vancouver Warriors",
    887: "San Diego Seals",
    888: "Las Vegas Desert Dogs",
    889: "Rochester Knighthawks",
    890: "Georgia Swarm",
    891: "Philadelphia Wings",
    892: "Oshawa FireWolves",
    893: "Ottawa Black Bears",
    894: "Halifax Thunderbirds",
}

# Sample game scores from NLL API (hardcoded for testing)
GAME_SCORES = [
    {"date": "2025-11-28", "home_id": 892, "away_id": 870, "home_score": 10, "away_score": 11, "winner_id": 870, "loser_id": 892},
    {"date": "2025-11-29", "home_id": 893, "away_id": 887, "home_score": 12, "away_score": 11, "winner_id": 893, "loser_id": 887},
    {"date": "2025-11-29", "home_id": 870, "away_id": 890, "home_score": 14, "away_score": 13, "winner_id": 870, "loser_id": 890},
    {"date": "2025-11-29", "home_id": 886, "away_id": 883, "home_score": 15, "away_score": 14, "winner_id": 886, "loser_id": 883},
]

updates = 0
for score_data in GAME_SCORES:
    from datetime import datetime
    date_obj = datetime.strptime(score_data['date'], "%Y-%m-%d").date()
    home_team_name = TEAM_ID_MAP.get(score_data['home_id'], str(score_data['home_id']))
    away_team_name = TEAM_ID_MAP.get(score_data['away_id'], str(score_data['away_id']))
    winner_name = TEAM_ID_MAP.get(score_data['winner_id']) if score_data.get('winner_id') else None
    loser_name = TEAM_ID_MAP.get(score_data['loser_id']) if score_data.get('loser_id') else None
    
    # Find game by date and team IDs (current state) or names (new state)
    games = Game.objects.filter(date=date_obj)
    for game in games:
        # Check if this matches our game
        game_home_id = str(score_data['home_id'])
        game_away_id = str(score_data['away_id'])
        
        # Match by current team values (could be IDs or names)
        if (game.home_team in [home_team_name, game_home_id] and 
            game.away_team in [away_team_name, game_away_id]):
            
            game.home_team = home_team_name
            game.away_team = away_team_name
            game.home_score = score_data.get('home_score')
            game.away_score = score_data.get('away_score')
            game.winner = winner_name
            game.loser = loser_name
            game.save()
            print(f"✓ Updated: {away_team_name} @ {home_team_name}: {game.away_score}-{game.home_score}")
            updates += 1
            break

print(f"\nTotal updates: {updates}")
