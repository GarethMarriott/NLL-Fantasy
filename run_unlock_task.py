#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.tasks import unlock_rosters_and_process_transactions

print("Running unlock_rosters_and_process_transactions task...")
result = unlock_rosters_and_process_transactions()
print(f"Task result: {result}")
