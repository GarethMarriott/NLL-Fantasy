#!/usr/bin/env python
"""
Clean up duplicate games - remove games with team ID values
"""
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from web.models import Game

# Find and delete all games that have team IDs instead of names
team_names = {
    "Buffalo Bandits", "Toronto Rock", "Colorado Mammoth", "Calgary Roughnecks",
    "Saskatchewan Rush", "Vancouver Warriors", "San Diego Seals", "Las Vegas Desert Dogs",
    "Rochester Knighthawks", "Georgia Swarm", "Philadelphia Wings", "Oshawa FireWolves",
    "Ottawa Black Bears", "Halifax Thunderbirds"
}

deleted_count = 0
for game in Game.objects.all():
    # If either team is all digits (ID), delete it
    if (game.home_team and game.home_team.isdigit()) or (game.away_team and game.away_team.isdigit()):
        print(f"Deleting: {game.away_team} @ {game.home_team} on {game.date}")
        game.delete()
        deleted_count += 1

print(f"\nTotal deleted: {deleted_count}")

# Check remaining games
remaining = Game.objects.count()
print(f"Remaining games: {remaining}")

# Show first game
first = Game.objects.first()
if first:
    print(f"Sample: {first.away_team} @ {first.home_team}")
