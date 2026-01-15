import os
from celery import Celery
from celery.schedules import crontab

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')

# Load configuration from Django settings, all configuration keys will make celery commands by uppercasing them
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all registered Django apps
app.autodiscover_tasks()

# Celery Beat Schedule (Periodic Tasks)
app.conf.beat_schedule = {
    'process-waivers-daily': {
        'task': 'web.tasks.process_waivers',
        'schedule': crontab(hour=23, minute=0),  # Every day at 11 PM
    },
    'check-league-status': {
        'task': 'web.tasks.check_league_status',
        'schedule': crontab(hour='*/6'),  # Every 6 hours
    },
    'cleanup-old-sessions': {
        'task': 'web.tasks.cleanup_old_sessions',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
