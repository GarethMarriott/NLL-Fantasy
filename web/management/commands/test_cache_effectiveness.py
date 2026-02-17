"""
Management command to test cache effectiveness with simulated production traffic.
Usage: python manage.py test_cache_effectiveness [--views=standings,team_detail,matchups] [--threads=4] [--duration=60] [--host=localhost:8000]
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.utils import timezone
from django.db import connection, reset_queries
from django.conf import settings
import time
import threading
import statistics
from collections import defaultdict
try:
    import requests
except ImportError:
    requests = None


class Command(BaseCommand):
    help = 'Test cache effectiveness by simulating production traffic'

    def add_arguments(self, parser):
        parser.add_argument(
            '--views',
            type=str,
            default='standings,team_detail,matchups,nll_schedule,players,league_detail',
            help='Comma-separated view URLs to test (default: all cached views)'
        )
        parser.add_argument(
            '--host',
            type=str,
            default='http://localhost:8000',
            help='Host to test (default: http://localhost:8000)'
        )
        parser.add_argument(
            '--duration',
            type=int,
            default=30,
            help='Test duration in seconds (default: 30)'
        )
        parser.add_argument(
            '--iterations',
            type=int,
            default=None,
            help='Number of requests per view (overrides duration)'
        )
        parser.add_argument(
            '--skip-redis-check',
            action='store_true',
            help='Skip Redis connectivity check'
        )

    def handle(self, *args, **options):
        if requests is None:
            self.stdout.write(self.style.ERROR('ERROR: requests library not installed'))
            self.stdout.write('Install with: pip install requests')
            return
        
        views = options['views'].split(',')
        host = options['host'].rstrip('/')
        duration = options['duration']
        iterations = options['iterations']
        skip_redis_check = options['skip_redis_check']

        self.stdout.write(self.style.SUCCESS('\n=== Cache Effectiveness Test ===\n'))
        self.stdout.write(f'Target: {host}\n')
        
        # Check Redis connectivity
        if not skip_redis_check:
            if not self._check_redis():
                self.stdout.write(self.style.WARNING('Warning: Redis unavailable, cache may not be working\n'))
        
        # Create test plan
        test_urls = self._prepare_urls(views)
        self.stdout.write(f'Testing {len(test_urls)} views: {", ".join(test_urls.keys())}\n')
        
        # Run cache effectiveness test
        cache_results = self._run_traffic_simulation(
            host, test_urls, duration, iterations
        )
        
        # Display results
        self._display_results(cache_results)
        
        self.stdout.write(self.style.SUCCESS('\n=== Test Complete ===\n'))

    def _prepare_urls(self, view_names):
        """Prepare test URLs for each view"""
        urls = {}
        
        # Map view names to URLs
        view_url_map = {
            'standings': '/standings/',
            'team_detail': '/teams/1/',
            'matchups': '/matchups/',
            'nll_schedule': '/nll-schedule/',
            'players': '/players/',
            'league_detail': '/leagues/1/',
        }
        
        for view in view_names:
            view = view.strip()
            if view in view_url_map:
                urls[view] = view_url_map[view]
        
        return urls

    def _run_traffic_simulation(self, host, urls, duration, iterations):
        """Simulate production traffic and measure cache effectiveness"""
        results = defaultdict(lambda: {
            'requests': 0,
            'response_times': [],
            'errors': 0,
            'total_time_ms': 0,
        })
        
        # Clear cache before starting
        cache.clear()
        self.stdout.write('Cache cleared\n')
        
        # Determine iteration count
        total_iterations = iterations
        start_time = timezone.now()
        request_count = 0
        
        self.stdout.write(f'Starting traffic simulation (30 seconds)...\n')
        
        try:
            while True:
                # Check duration
                elapsed = (timezone.now() - start_time).total_seconds()
                if elapsed > duration:
                    break
                
                # Make requests to each view
                for view_name, url in urls.items():
                    try:
                        full_url = f"{host}{url}"
                        
                        # Make request and time it
                        req_start = time.time()
                        response = requests.get(full_url, timeout=10)
                        req_duration = (time.time() - req_start) * 1000  # Convert to ms
                        
                        # Collect metrics
                        if response.status_code == 200:
                            results[view_name]['requests'] += 1
                            results[view_name]['response_times'].append(req_duration)
                            results[view_name]['total_time_ms'] += req_duration
                            request_count += 1
                        else:
                            results[view_name]['errors'] += 1
                            
                    except Exception as e:
                        results[view_name]['errors'] += 1
                        self.stdout.write(self.style.WARNING(f'  ⚠ {view_name}: {str(e)[:60]}'))
        
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nTest interrupted by user'))
        
        return dict(results)

    def _display_results(self, results):
        """Display test results and effectiveness metrics"""
        self.stdout.write(self.style.SUCCESS('\n=== Test Results ===\n'))
        
        # Display per-view metrics
        overall_response_times = []
        
        for view_name in sorted(results.keys()):
            data = results[view_name]
            
            if data['requests'] == 0:
                self.stdout.write(f'{view_name}: NO DATA')
                continue
            
            # Calculate statistics
            avg_response = statistics.mean(data['response_times'])
            min_response = min(data['response_times'])
            max_response = max(data['response_times'])
            median_response = statistics.median(data['response_times'])
            
            overall_response_times.extend(data['response_times'])
            
            # Display view-specific stats
            self.stdout.write(f'\n{view_name}:')
            self.stdout.write(f'  Requests: {data["requests"]}')
            self.stdout.write(f'  Errors: {data["errors"]}')
            self.stdout.write(f'  Response times:')
            self.stdout.write(f'    Min: {min_response:.1f}ms')
            self.stdout.write(f'    Max: {max_response:.1f}ms')
            self.stdout.write(f'    Avg: {avg_response:.1f}ms')
            self.stdout.write(f'    Median: {median_response:.1f}ms')
        
        # Display overall statistics
        self.stdout.write(self.style.SUCCESS('\n=== Overall Statistics ===\n'))
        
        total_requests = sum(data['requests'] for data in results.values())
        total_errors = sum(data['errors'] for data in results.values())
        success_rate = (total_requests / (total_requests + total_errors) * 100) if (total_requests + total_errors) > 0 else 0
        
        self.stdout.write(f'Total Requests: {total_requests}')
        self.stdout.write(f'Total Errors: {total_errors}')
        self.stdout.write(f'Success Rate: {success_rate:.1f}%')
        
        if overall_response_times:
            self.stdout.write(f'\nAggregate Response Times:')
            self.stdout.write(f'  Min: {min(overall_response_times):.1f}ms')
            self.stdout.write(f'  Max: {max(overall_response_times):.1f}ms')
            self.stdout.write(f'  Avg: {statistics.mean(overall_response_times):.1f}ms')
            self.stdout.write(f'  Median: {statistics.median(overall_response_times):.1f}ms')
            self.stdout.write(f'  95th Percentile: {self._percentile(overall_response_times, 95):.1f}ms')
            self.stdout.write(f'  99th Percentile: {self._percentile(overall_response_times, 99):.1f}ms')
        
        # Display cache stats
        self._display_cache_stats()
    
    def _check_redis(self):
        """Check Redis connectivity"""
        try:
            cache.set('test_key', 'test_value', 10)
            value = cache.get('test_key')
            return value == 'test_value'
        except Exception:
            return False
    
    def _display_cache_stats(self):
        """Display Redis cache statistics"""
        self.stdout.write(self.style.SUCCESS('\n=== Redis Cache Statistics ===\n'))
        
        try:
            from django.core.cache.backends.redis import RedisCache
            if isinstance(cache, RedisCache):
                redis_conn = cache._cache
                info = redis_conn.info()
                
                self.stdout.write(f'Memory used: {info.get("used_memory_human", "N/A")}')
                self.stdout.write(f'Connected clients: {info.get("connected_clients", "N/A")}')
                self.stdout.write(f'Total commands: {info.get("total_commands_processed", "N/A")}')
                
                hits = info.get('keyspace_hits', 0)
                misses = info.get('keyspace_misses', 0)
                total = hits + misses
                hit_rate = (hits / total * 100) if total > 0 else 0
                
                self.stdout.write(f'Cache hits: {hits}')
                self.stdout.write(f'Cache misses: {misses}')
                self.stdout.write(f'Hit rate: {hit_rate:.1f}%')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Could not retrieve Redis stats: {e}'))
    
    def _percentile(self, data, percentile):
        """Calculate percentile from sorted data"""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]
