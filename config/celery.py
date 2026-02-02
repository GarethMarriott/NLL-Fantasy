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
    'unlock-rosters-monday-9am-PT': {
        'task': 'web.tasks.unlock_rosters_and_process_transactions',
        'schedule': crontab(day_of_week='mon', hour=17, minute=0),  # Monday 9am PT = Monday 5pm UTC (since PT is UTC-8)
    },
    'fetch-stats-friday-night': {
        'task': 'web.tasks.fetch_nll_stats_task',
        'schedule': crontab(day_of_week='fri', hour=6, minute=0),  # Friday 11 PM PT = Saturday 6 AM UTC
    },
    'fetch-stats-saturday-morning': {
        'task': 'web.tasks.fetch_nll_stats_task',
        'schedule': crontab(day_of_week='sat', hour=17, minute=0),  # Saturday 9 AM PT = Saturday 5 PM UTC
    },
    'fetch-stats-saturday-night': {
        'task': 'web.tasks.fetch_nll_stats_task',
        'schedule': crontab(day_of_week='sat', hour=6, minute=0),  # Saturday 11 PM PT = Sunday 6 AM UTC
    },
    'fetch-stats-sunday-morning': {
        'task': 'web.tasks.fetch_nll_stats_task',
        'schedule': crontab(day_of_week='sun', hour=17, minute=0),  # Sunday 9 AM PT = Sunday 5 PM UTC
    },
    'fetch-stats-sunday-night': {
        'task': 'web.tasks.fetch_nll_stats_task',
        'schedule': crontab(day_of_week='sun', hour=6, minute=0),  # Sunday 11 PM PT = Monday 6 AM UTC
    },
    'fetch-stats-monday-retry': {
        'task': 'web.tasks.fetch_nll_stats_task',
        'schedule': crontab(day_of_week='mon', hour=15, minute=0),  # Monday 7 AM PT = Monday 3 PM UTC (retry before unlock)
    },
    'cleanup-old-sessions': {
        'task': 'web.tasks.cleanup_old_sessions',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'archive-old-leagues': {
        'task': 'web.tasks.archive_old_leagues',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM - check if season ended
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
