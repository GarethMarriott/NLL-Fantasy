import os
import sys
import django

sys.path.insert(0, '/opt/shamrock-fantasy')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Disable silk temporarily
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django.conf
if 'silk' in django.conf.settings.INSTALLED_APPS:
    django.conf.settings.INSTALLED_APPS = tuple(
        app for app in django.conf.settings.INSTALLED_APPS if app != 'silk'
    )

django.setup()

from web.models import Trade, Team

# Get last 10 trades
trades = Trade.objects.all().order_by('-created_at')[:10]

print("Recent trades on live server:")
print()

for trade in trades:
    print(f"Trade {trade.id}:")
    print(f"  Proposing team ID: {trade.proposing_team_id}")
    print(f"  Receiving team ID: {trade.receiving_team_id}")
    print(f"  Status: {trade.status}")
    print(f"  Executed at: {trade.executed_at}")
    print()

# Also check for any stuck trades (ACCEPTED but not executed)
stuck = Trade.objects.filter(status='ACCEPTED', executed_at__isnull=True)
print(f"\nTrades ACCEPTED but NOT EXECUTED: {stuck.count()}")
for trade in stuck:
    try:
        prop = trade.proposing_team
        recv = trade.receiving_team
        print(f"  Trade {trade.id}: {prop.name} -> {recv.name}")
        print(f"    Players: {trade.players.count()}, Picks: {trade.picks.count()}")
    except:
        print(f"  Trade {trade.id}: (error loading teams)")
