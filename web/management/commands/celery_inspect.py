"""
Management command to inspect active Celery tasks and worker status
"""

from django.core.management.base import BaseCommand
from celery import current_app
from celery.app.control import Inspect


class Command(BaseCommand):
    help = 'Inspect Celery workers and active tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--active',
            action='store_true',
            help='Show active tasks',
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show worker stats',
        )
        parser.add_argument(
            '--scheduled',
            action='store_true',
            help='Show scheduled tasks (Beat schedule)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Show all information',
        )

    def handle(self, *args, **options):
        app = current_app
        inspector = Inspect(app=app)

        show_active = options['active'] or options['all']
        show_stats = options['stats'] or options['all']
        show_scheduled = options['scheduled'] or options['all']
        
        # If no options specified, show all
        if not (show_active or show_stats or show_scheduled):
            show_active = show_stats = show_scheduled = True

        self.stdout.write('\n' + '='*70)
        self.stdout.write('CELERY MONITORING')
        self.stdout.write('='*70 + '\n')

        # Show active tasks
        if show_active:
            self.stdout.write(self.style.SUCCESS('ACTIVE TASKS:'))
            try:
                active = inspector.active()
                if active:
                    for worker_name, tasks in active.items():
                        self.stdout.write(f'\n  Worker: {worker_name}')
                        if tasks:
                            for task in tasks:
                                self.stdout.write(f'    - {task["name"]} (ID: {task["id"][:8]}...)')
                                self.stdout.write(f'      Args: {task.get("args", [])}')
                        else:
                            self.stdout.write('    (no active tasks)')
                else:
                    self.stdout.write(self.style.WARNING('  No workers found! Celery worker may not be running.'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error: {e}'))

        # Show worker stats
        if show_stats:
            self.stdout.write('\n' + self.style.SUCCESS('WORKER STATS:'))
            try:
                stats = inspector.stats()
                if stats:
                    for worker_name, worker_stats in stats.items():
                        self.stdout.write(f'\n  Worker: {worker_name}')
                        self.stdout.write(f'    - Celery version: {worker_stats.get("celery", {}).get("version", "N/A")}')
                        self.stdout.write(f'    - Pool: {worker_stats.get("pool", {}).get("implementation", "N/A")}')
                        self.stdout.write(f'    - Max concurrency: {worker_stats.get("pool", {}).get("max-concurrency", "N/A")}')
                else:
                    self.stdout.write(self.style.WARNING('  No workers found!'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error: {e}'))

        # Show Beat schedule
        if show_scheduled:
            self.stdout.write('\n' + self.style.SUCCESS('BEAT SCHEDULE:'))
            beat_schedule = app.conf.get('beat_schedule', {})
            if beat_schedule:
                for task_name, config in beat_schedule.items():
                    self.stdout.write(f'\n  {task_name}')
                    self.stdout.write(f'    - Task: {config.get("task")}')
                    self.stdout.write(f'    - Schedule: {config.get("schedule")}')
                    if 'unlock_rosters' in config.get('task', ''):
                        self.stdout.write(self.style.SUCCESS('    ✓ Waiver processing task'))
            else:
                self.stdout.write(self.style.WARNING('  No tasks scheduled!'))

        self.stdout.write('\n' + '='*70 + '\n')
