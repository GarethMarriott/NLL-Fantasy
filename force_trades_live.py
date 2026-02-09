#!/usr/bin/env python3
import os
import sys
import django
from django.conf import settings

sys.path.insert(0, '/opt/shamrock-fantasy')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Patch INSTALLED_APPS to remove problematic apps before setup
from django.conf import settings as conf_settings

original_apps = list(conf_settings.INSTALLED_APPS) if hasattr(conf_settings, 'INSTALLED_APPS') else []
problematic = ['silk', 'django_celery_beat', 'django_celery_results']
filtered_apps = [app for app in original_apps if app not in problematic]

# Modify the setting
if hasattr(django, 'apps'):
    pass  # Will be set up below

import django
from django.apps import apps
from django.conf import settings as django_settings

if not apps.ready:
    # Override INSTALLED_APPS before setup
    django_settings.INSTALLED_APPS = tuple(filtered_apps)

django.setup()

from web.models import Trade, Team
from web.views import execute_trade
from django.utils import timezone

# Check for stuck trades
stuck = Trade.objects.filter(status='ACCEPTED', executed_at__isnull=True)
print(f"\n{'='*60}")
print(f"Stuck trades found: {stuck.count()}")
print(f"{'='*60}\n")

if stuck.count() == 0:
    print("✓ No stuck trades")
    sys.exit(0)

for trade in stuck:
    try:
        print(f"Trade {trade.id}:")
        print(f"  {trade.proposing_team.name} -> {trade.receiving_team.name}")
        print(f"  Players: {trade.players.count()}, Picks: {trade.picks.count()}")
        
        # Force execute
        execute_trade(trade)
        print(f"  ✓ Executed successfully\n")
    except Exception as e:
        print(f"  ✗ Error: {str(e)}\n")

print(f"{'='*60}")
print("Force execution complete!")
print(f"{'='*60}\n")
