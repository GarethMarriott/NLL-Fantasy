#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, '/opt/shamrock-fantasy')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Import Django and set it up, bypassing the silk import issue
import django
from django.conf import settings

# Temporarily remove problematic apps
original_apps = list(settings.INSTALLED_APPS)
settings.INSTALLED_APPS = tuple(
    app for app in settings.INSTALLED_APPS 
    if app not in ['silk', 'django_celery_beat', 'django_celery_results']
)

django.setup()

# Now run migrations
from django.core.management import call_command

try:
    print("Running migrations...")
    call_command('migrate', verbosity=2)
    print("✓ Migrations completed successfully!")
except Exception as e:
    print(f"✗ Migration error: {e}")
    sys.exit(1)
