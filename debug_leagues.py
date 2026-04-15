#!/usr/bin/env python
import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import League
from django.contrib.auth.models import User

print("=== ALL LEAGUES ===")
all_leagues = League.objects.all().order_by('name', '-created_at')
for league in all_leagues:
    commissioner = league.commissioner.username if league.commissioner else 'N/A'
    teams_count = league.teams.count()
    print(f"ID: {league.id:4d} | Status: {league.status:15s} | Name: {league.name:30s} | Commissioner: {commissioner:15s} | Teams: {teams_count}")

print("\n=== STATUS BREAKDOWN ===")
for status in sorted(set(League.objects.values_list('status', flat=True))):
    count = League.objects.filter(status=status).count()
    print(f"{status}: {count}")
