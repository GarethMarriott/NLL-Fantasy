from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from django.utils import timezone


class Command(BaseCommand):
    help = 'Setup Celery Beat periodic tasks in database'

    def handle(self, *args, **options):
        self.stdout.write("Setting up Celery Beat periodic tasks...")
        
        # Define all scheduled tasks
        tasks = [
            {
                'name': 'unlock-rosters-tuesday-9am-PT',
                'task': 'web.tasks.unlock_rosters_and_process_transactions',
                'crontab': {'day_of_week': 'tue', 'hour': 17, 'minute': 0},  # Tuesday 5pm UTC = Tuesday 9am PT
                'description': 'Unlock rosters and process waivers/trades every Tuesday at 9am PT',
            },
            {
                'name': 'fetch-stats-friday-night',
                'task': 'web.tasks.fetch_nll_stats_task',
                'crontab': {'day_of_week': 'fri', 'hour': 6, 'minute': 0},  # Friday 6am UTC = Friday 10pm PT
                'description': 'Fetch NLL stats Friday night',
            },
            {
                'name': 'fetch-stats-saturday-morning',
                'task': 'web.tasks.fetch_nll_stats_task',
                'crontab': {'day_of_week': 'sat', 'hour': 17, 'minute': 0},  # Saturday 5pm UTC = Saturday 9am PT
                'description': 'Fetch NLL stats Saturday morning',
            },
            {
                'name': 'fetch-stats-saturday-night',
                'task': 'web.tasks.fetch_nll_stats_task',
                'crontab': {'day_of_week': 'sat', 'hour': 6, 'minute': 0},  # Saturday 6am UTC = Friday 10pm PT (previous day)
                'description': 'Fetch NLL stats Saturday night',
            },
            {
                'name': 'fetch-stats-sunday-morning',
                'task': 'web.tasks.fetch_nll_stats_task',
                'crontab': {'day_of_week': 'sun', 'hour': 17, 'minute': 0},  # Sunday 5pm UTC = Sunday 9am PT
                'description': 'Fetch NLL stats Sunday morning',
            },
            {
                'name': 'fetch-stats-sunday-night',
                'task': 'web.tasks.fetch_nll_stats_task',
                'crontab': {'day_of_week': 'sun', 'hour': 6, 'minute': 0},  # Sunday 6am UTC = Saturday 10pm PT (previous day)
                'description': 'Fetch NLL stats Sunday night',
            },
            {
                'name': 'fetch-stats-monday-morning',
                'task': 'web.tasks.fetch_nll_stats_task',
                'crontab': {'day_of_week': 'mon', 'hour': 17, 'minute': 0},  # Monday 5pm UTC = Monday 9am PT
                'description': 'Fetch NLL stats Monday morning',
            },
            {
                'name': 'fetch-stats-monday-night',
                'task': 'web.tasks.fetch_nll_stats_task',
                'crontab': {'day_of_week': 'tue', 'hour': 7, 'minute': 0},  # Tuesday 7am UTC = Monday 11pm PT (previous day)
                'description': 'Fetch NLL stats Monday night',
            },
            {
                'name': 'fetch-stats-monday-retry',
                'task': 'web.tasks.fetch_nll_stats_task',
                'crontab': {'day_of_week': 'mon', 'hour': 15, 'minute': 0},  # Monday 3pm UTC = Monday 7am PT
                'description': 'Fetch NLL stats Monday morning retry',
            },
            {
                'name': 'cleanup-old-sessions',
                'task': 'web.tasks.cleanup_old_sessions',
                'crontab': {'hour': 2, 'minute': 0},  # Daily at 2am
                'description': 'Cleanup old sessions daily',
            },
            {
                'name': 'archive-old-leagues',
                'task': 'web.tasks.archive_old_leagues',
                'crontab': {'hour': 3, 'minute': 0},  # Daily at 3am
                'description': 'Archive old leagues daily',
            },
        ]
        
        for task_info in tasks:
            # Create or update crontab schedule
            crontab_kwargs = task_info['crontab']
            crontab_obj, created = CrontabSchedule.objects.get_or_create(**crontab_kwargs)
            
            # Create or update periodic task
            task_obj, created = PeriodicTask.objects.update_or_create(
                name=task_info['name'],
                defaults={
                    'task': task_info['task'],
                    'crontab': crontab_obj,
                    'enabled': True,
                    'description': task_info['description'],
                }
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Created task: {task_info['name']}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"✓ Updated task: {task_info['name']}")
                )
        
        self.stdout.write(self.style.SUCCESS("\nAll periodic tasks configured successfully!"))
        self.stdout.write("Note: Restart Celery Beat to apply changes: sudo systemctl restart celery-beat")
