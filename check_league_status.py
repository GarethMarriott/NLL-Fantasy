#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import League

# Check the 5 most recent leagues
leagues = League.objects.all().order_by('-id')[:5]
for league in leagues:
    print(f"{league.name}: status={league.status}")
