#!/usr/bin/env python
import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import League

# Delete the 4 duplicate leagues with 0 teams
print("=== DELETING DUPLICATE LEAGUES ===")
dup_leagues = League.objects.filter(id__in=[5, 6, 7, 8])
for league in dup_leagues:
    print(f"Deleting league ID {league.id}: {league.name}")
    league.delete()

print("\n=== REMAINING LEAGUES ===")
for league in League.objects.all().order_by('name'):
    print(f"ID: {league.id:4d} | Status: {league.status:15s} | Name: {league.name}")
