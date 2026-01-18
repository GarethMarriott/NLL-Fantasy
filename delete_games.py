#!/usr/bin/env python
"""Delete all games"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import Game

count = Game.objects.count()
Game.objects.all().delete()
print(f'Deleted {count} games')
