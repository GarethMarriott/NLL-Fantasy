#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Trade, Team, League
from django.db import models

# Find MAFFL league
league = League.objects.filter(name__icontains='MAFL').first()
print(f'League: {league}')

if league:
    print()
    # Find the teams
    gooners = Team.objects.filter(league=league, name__icontains='gooner').first()
    loose_balls = Team.objects.filter(league=league, name__icontains='loose').first()
    
    print(f'Gooners: {gooners}')
    print(f'Loose Balls: {loose_balls}')
    
    if gooners and loose_balls:
        # Find trades between these teams
        trades = Trade.objects.filter(league=league).filter(
            (models.Q(proposing_team=gooners, receiving_team=loose_balls) |
             models.Q(proposing_team=loose_balls, receiving_team=gooners))
        )
        print(f'\nTrades between them:')
        for trade in trades:
            print(f'  Trade {trade.id}: {trade.proposing_team.name} -> {trade.receiving_team.name}')
            print(f'    Status: {trade.status}')
            print(f'    Executed: {trade.executed_at}')
            print(f'    Players: {trade.players.count()}, Picks: {trade.picks.count()}')
    
    # Also list all PENDING trades in this league
    print(f'\nAll PENDING trades in {league.name}:')
    pending = Trade.objects.filter(league=league, status='PENDING')
    print(f'Count: {pending.count()}')
    for trade in pending:
        print(f'  Trade {trade.id}: {trade.proposing_team.name} -> {trade.receiving_team.name}')
