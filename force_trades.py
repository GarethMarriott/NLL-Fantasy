#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Trade, Week
from web.views import execute_trade
from django.utils import timezone

# Find all pending trades (accepted but not executed)
pending_trades = Trade.objects.filter(
    status=Trade.Status.ACCEPTED,
    executed_at__isnull=True
)

print(f"\n{'='*60}")
print(f"Found {pending_trades.count()} pending trades")
print(f"{'='*60}\n")

if pending_trades.count() == 0:
    print("✓ No pending trades to process")
    sys.exit(0)

for trade in pending_trades:
    print(f"Processing Trade {trade.id}:")
    print(f"  {trade.proposing_team.name} ↔ {trade.receiving_team.name}")
    print(f"  Players: {trade.players.count()}, Picks: {trade.picks.count()}")
    
    try:
        execute_trade(trade)
        print(f"  ✓ Trade executed successfully")
        print()
    except Exception as e:
        print(f"  ✗ Error: {str(e)}")
        print()

print(f"{'='*60}")
print("Force processing complete!")
print(f"{'='*60}\n")
