#!/usr/bin/env python
import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import League

# Check league statuses
print("=== League Status Breakdown ===")
statuses = League.objects.values_list('status', flat=True).distinct()
for status in sorted(statuses):
    count = League.objects.filter(status=status).count()
    print(f"{status}: {count}")

print("\n=== Offseason Leagues (should show old renewed leagues) ===")
offseason_leagues = League.objects.filter(status='offseason')
for league in offseason_leagues:
    print(f"  ID: {league.id}, Name: {league.name}")

print("\n=== Season Complete Leagues (awaiting renewal) ===")
season_complete = League.objects.filter(status='season_complete')
print(f"Total: {season_complete.count()}")
for league in season_complete:
    print(f"  ID: {league.id}, Name: {league.name}, Commissioner: {league.commissioner.username if league.commissioner else 'N/A'}")
