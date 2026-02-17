"""
Management command to monitor standings cache hits and misses.
Usage: python manage.py monitor_standings_cache
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.utils import timezone
from django.db import connection
from web.cache_utils import get_standings_cache_key
import time


class Command(BaseCommand):
    help = 'Monitor standings view cache hits and performance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--duration',
            type=int,
            default=60,
            help='Monitor duration in seconds (default: 60)'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='Check interval in seconds (default: 5)'
        )

    def handle(self, *args, **options):
        duration = options['duration']
        interval = options['interval']
        
        self.stdout.write(self.style.SUCCESS(f'\n=== Monitoring Standings Cache for {duration}s ===\n'))
        
        # Clear standings caches first
        cache_key = get_standings_cache_key(None)
        cache.delete(cache_key)
        self.stdout.write(f'Cleared standings cache: {cache_key}')
        
        # Collect metrics
        checks = []
        start_time = timezone.now()
        elapsed = 0
        
        try:
            while elapsed < duration:
                # Get Redis info for cache metrics
                check_data = self._get_cache_metrics()
                checks.append(check_data)
                
                self.stdout.write(f'\n[{check_data["timestamp"]}] Cache Check:')
                self.stdout.write(f'  Hits: {check_data["hits"]}')
                self.stdout.write(f'  Misses: {check_data["misses"]}')
                self.stdout.write(f'  Hit Rate: {check_data["hit_rate"]:.1%}')
                self.stdout.write(f'  Connections: {check_data["connections"]}')
                
                # Check if standings cache is set
                standings_cached = cache.get(cache_key) is not None
                self.stdout.write(f'  Standings cached: {"✓" if standings_cached else "✗"}')
                
                time.sleep(interval)
                elapsed = (timezone.now() - start_time).total_seconds()
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nMonitoring stopped by user'))
        
        # Show summary
        self._show_summary(checks)
    
    def _get_cache_metrics(self):
        """Get current cache metrics from Redis"""
        timestamp = timezone.now().strftime('%H:%M:%S')
        
        try:
            from django.core.cache.backends.redis import RedisCache
            if isinstance(cache, RedisCache):
                redis_conn = cache._cache
                info = redis_conn.info()
                
                hits = info.get('keyspace_hits', 0)
                misses = info.get('keyspace_misses', 0)
                total = hits + misses
                hit_rate = (hits / total) if total > 0 else 0
                connections = info.get('connected_clients', 0)
                
                return {
                    'timestamp': timestamp,
                    'hits': hits,
                    'misses': misses,
                    'hit_rate': hit_rate,
                    'connections': connections,
                }
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Error getting metrics: {e}'))
        
        return {
            'timestamp': timestamp,
            'hits': 0,
            'misses': 0,
            'hit_rate': 0,
            'connections': 0,
        }
    
    def _show_summary(self, checks):
        """Show monitoring summary"""
        if not checks:
            self.stdout.write(self.style.WARNING('\nNo data collected'))
            return
        
        self.stdout.write(self.style.SUCCESS('\n=== Monitoring Summary ===\n'))
        
        # Get final metrics
        final_check = checks[-1]
        initial_check = checks[0]
        
        self.stdout.write(f'Hits increase: {final_check["hits"] - initial_check["hits"]}')
        self.stdout.write(f'Misses increase: {final_check["misses"] - initial_check["misses"]}')
        self.stdout.write(f'Final hit rate: {final_check["hit_rate"]:.1%}')
        
        # Note: For meaningful cache metrics, you'd need to reset stats before monitoring
        self.stdout.write(self.style.WARNING(
            '\nNote: Redis cumulative stats may include previous operations.'
        ))
        self.stdout.write('For accurate cache testing:')
        self.stdout.write('  1. Run: redis-cli FLUSHDB')
        self.stdout.write('  2. Access standings page multiple times')
        self.stdout.write('  3. Run this command to see cache hit rate')
