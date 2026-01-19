#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Week

updated = Week.objects.all().update(roster_lock_time=None, roster_unlock_time=None)
print(f"Cleared lock times for {updated} weeks")
