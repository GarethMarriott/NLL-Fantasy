#!/usr/bin/env python
"""
Fix existing games: replace team IDs with team names
"""
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game

# Team ID to name mapping
TEAMS = {
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

# Convert all team IDs to names
for game in Game.objects.all():
    home_id = int(game.home_team) if game.home_team.isdigit() else None
    away_id = int(game.away_team) if game.away_team.isdigit() else None
    
    changed = False
    if home_id and home_id in TEAMS:
        game.home_team = TEAMS[home_id]
        changed = True
    if away_id and away_id in TEAMS:
        game.away_team = TEAMS[away_id]
        changed = True
    
    if changed:
        try:
            game.save()
            print(f"✓ Updated: {game.away_team} @ {game.home_team}")
        except Exception as e:
            print(f"✗ Error updating game on {game.date}: {e}")
