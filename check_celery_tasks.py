#!/usr/bin/env python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django_celery_beat.models import PeriodicTask

print('\n=== Scheduled Celery Beat Tasks ===\n')
tasks = PeriodicTask.objects.all().order_by('name')
for t in tasks:
    enabled = '✓' if t.enabled else '✗'
    print(f"{enabled} {t.name:50} -> {t.task}")
print(f'\nTotal: {tasks.count()} tasks\n')
