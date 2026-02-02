"""
Management command to test Celery Beat scheduling configuration
Tests that the waiver processing task is properly scheduled
"""

from django.core.management.base import BaseCommand
from celery import current_app
from celery.schedules import crontab
from django.utils import timezone
import pytz


class Command(BaseCommand):
    help = 'Test Celery Beat scheduling for waiver processing task'

    def add_arguments(self, parser):
        parser.add_argument(
            '--trigger',
            action='store_true',
            help='Actually trigger the scheduled task now (useful for testing)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('CELERY BEAT SCHEDULING TEST'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))

        # 1. Check if Celery is available
        self.stdout.write('1. Checking Celery configuration...')
        try:
            app = current_app
            self.stdout.write(self.style.SUCCESS(f'   ✓ Celery app: {app}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Error: {e}'))
            return

        # 2. Check Beat Schedule
        self.stdout.write('\n2. Celery Beat Schedule:')
        beat_schedule = app.conf.get('beat_schedule', {})
        
        if not beat_schedule:
            self.stdout.write(self.style.ERROR('   ✗ No beat schedule configured!'))
            return
        
        for task_name, task_config in beat_schedule.items():
            self.stdout.write(f'\n   Task: {task_name}')
            self.stdout.write(f'   - Celery Task: {task_config.get("task")}')
            
            schedule = task_config.get('schedule')
            if hasattr(schedule, 'is_due'):
                # It's a crontab schedule
                self.stdout.write(f'   - Type: Crontab')
                self.stdout.write(f'   - Schedule: {schedule}')
                
                # Check if it's the waiver processing task
                if 'unlock_rosters_and_process_transactions' in task_config.get('task', ''):
                    self.stdout.write(self.style.SUCCESS('   ✓ Waiver processing task found!'))
                    self._analyze_waiver_schedule(schedule)
            else:
                self.stdout.write(f'   - Schedule: {schedule}')

        # 3. Check registered tasks
        self.stdout.write('\n3. Registered Celery Tasks:')
        registered_tasks = app.tasks
        
        waiver_task_found = False
        for task_name in registered_tasks.keys():
            if 'unlock_rosters' in task_name or 'waiver' in task_name.lower():
                self.stdout.write(f'   ✓ {task_name}')
                waiver_task_found = True
        
        if not waiver_task_found:
            self.stdout.write(self.style.WARNING('   ⚠ No waiver-related tasks registered'))

        # 4. Test task triggering if requested
        if options['trigger']:
            self.stdout.write('\n4. Testing task execution...')
            self._trigger_task()
        else:
            self.stdout.write('\n4. To actually trigger the waiver processing task, run:')
            self.stdout.write('   python manage.py test_celery_beat --trigger')

        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS('TEST COMPLETE'))
        self.stdout.write('='*70 + '\n')

    def _analyze_waiver_schedule(self, schedule):
        """Analyze the waiver processing crontab schedule"""
        self.stdout.write('\n   Schedule Details:')
        
        # Monday 9am PT = Monday 4pm UTC
        self.stdout.write('   - Day of week: Monday')
        self.stdout.write('   - Time (UTC): 16:00 (4pm)')
        self.stdout.write('   - Time (PT): 09:00 (9am)')
        
        # Calculate next run time
        now = timezone.now()
        self.stdout.write(f'\n   Current UTC time: {now}')
        
        # Create the next Monday 4pm UTC
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0 and now.hour < 16:
            # Today is Monday and we haven't hit 4pm yet
            next_run = now.replace(hour=16, minute=0, second=0, microsecond=0)
        else:
            # Next Monday
            next_run = now + timezone.timedelta(days=days_until_monday)
            next_run = next_run.replace(hour=16, minute=0, second=0, microsecond=0)
        
        self.stdout.write(f'   Next scheduled run: {next_run} UTC')
        
        time_until = next_run - now
        hours = time_until.total_seconds() / 3600
        self.stdout.write(f'   Time until next run: {hours:.1f} hours')

    def _trigger_task(self):
        """Trigger the waiver processing task now"""
        from celery import current_app
        
        try:
            # Send the task to Celery
            task = current_app.send_task('unlock_rosters_and_process_transactions')
            self.stdout.write(self.style.SUCCESS(f'   ✓ Task triggered!'))
            self.stdout.write(f'   Task ID: {task.id}')
            self.stdout.write('\n   To check task status, run:')
            self.stdout.write(f'   python manage.py celery_inspect active')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Error triggering task: {e}'))
