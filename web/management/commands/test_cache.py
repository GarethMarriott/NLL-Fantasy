"""
Management command to test Redis cache connectivity and performance.
Usage: python manage.py test_cache
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.utils import timezone
import time


class Command(BaseCommand):
    help = 'Test Redis cache connectivity and performance'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n=== Starting Cache Tests ===\n'))
        
        # Test 1: Basic connectivity
        self.test_connectivity()
        
        # Test 2: Set/Get operations
        self.test_set_get()
        
        # Test 3: Cache expiration
        self.test_expiration()
        
        # Test 4: Large data
        self.test_large_data()
        
        # Test 5: Display cache info
        self.display_cache_info()
        
        self.stdout.write(self.style.SUCCESS('\n=== All Cache Tests Complete ===\n'))
    
    def test_connectivity(self):
        """Test basic Redis connectivity"""
        self.stdout.write('\n1. Testing Redis Connectivity...')
        try:
            cache.set('test_key', 'test_value', 10)
            value = cache.get('test_key')
            if value == 'test_value':
                self.stdout.write(self.style.SUCCESS('   ✓ Redis connection successful'))
            else:
                self.stdout.write(self.style.ERROR('   ✗ Cache returned wrong value'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Redis connection failed: {e}'))
    
    def test_set_get(self):
        """Test set and get operations"""
        self.stdout.write('\n2. Testing Set/Get Operations...')
        test_data = {
            'league_id': 1,
            'standings': [
                {'team': 'Team A', 'wins': 5, 'losses': 2},
                {'team': 'Team B', 'wins': 4, 'losses': 3},
            ]
        }
        
        try:
            # Set
            cache.set('test_standings', test_data, 300)
            # Get
            retrieved = cache.get('test_standings')
            
            if retrieved == test_data:
                self.stdout.write(self.style.SUCCESS('   ✓ Set/Get operations working'))
            else:
                self.stdout.write(self.style.ERROR('   ✗ Data mismatch'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Set/Get failed: {e}'))
    
    def test_expiration(self):
        """Test cache expiration"""
        self.stdout.write('\n3. Testing Cache Expiration...')
        try:
            # Set with 1 second TTL
            cache.set('expiring_key', 'value', 1)
            
            # Should exist immediately
            if cache.get('expiring_key') == 'value':
                self.stdout.write('   - Key exists after set: ✓')
            else:
                self.stdout.write(self.style.ERROR('   ✗ Key missing immediately after set'))
                return
            
            # Wait for expiration
            time.sleep(2)
            
            # Should be gone
            if cache.get('expiring_key') is None:
                self.stdout.write(self.style.SUCCESS('   ✓ Cache expiration working'))
            else:
                self.stdout.write(self.style.WARNING('   ⚠ Key still exists after expiration'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Expiration test failed: {e}'))
    
    def test_large_data(self):
        """Test caching large data structures"""
        self.stdout.write('\n4. Testing Large Data Caching...')
        try:
            # Create a large standings structure (simulate 100 teams)
            large_data = {
                'league_id': 1,
                'cached_at': timezone.now().isoformat(),
                'standings': [
                    {
                        'team_id': i,
                        'team_name': f'Team {i}',
                        'wins': 10 - (i % 5),
                        'losses': i % 5,
                        'ties': i % 2,
                        'points_for': 1000 + (i * 10),
                        'points_against': 1000 + (i * 5),
                    }
                    for i in range(100)
                ]
            }
            
            cache.set('large_standings', large_data, 3600)
            retrieved = cache.get('large_standings')
            
            if retrieved and len(retrieved.get('standings', [])) == 100:
                self.stdout.write(self.style.SUCCESS('   ✓ Large data caching working'))
                data_size = len(str(large_data)) / 1024  # KB
                self.stdout.write(f'   - Cached {data_size:.1f} KB of data')
            else:
                self.stdout.write(self.style.ERROR('   ✗ Large data retrieval incomplete'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Large data test failed: {e}'))
    
    def display_cache_info(self):
        """Display cache configuration"""
        self.stdout.write('\n5. Cache Configuration:')
        try:
            from django.conf import settings
            cache_config = settings.CACHES.get('default', {})
            
            self.stdout.write(f'   Backend: {cache_config.get("BACKEND", "Not configured")}')
            self.stdout.write(f'   Location: {cache_config.get("LOCATION", "Not configured")}')
            
            # Try to get cache version (if available)
            try:
                # List some cache keys
                from django.core.cache.backends.redis import RedisCache
                if isinstance(cache, RedisCache):
                    self.stdout.write('   ✓ Redis backend detected')
                    
                    # Show cache statistics
                    redis_conn = cache._cache
                    info = redis_conn.info()
                    self.stdout.write(f'\n   Redis Statistics:')
                    self.stdout.write(f'   - Memory used: {info.get("used_memory_human", "N/A")}')
                    self.stdout.write(f'   - Connected clients: {info.get("connected_clients", "N/A")}')
                    self.stdout.write(f'   - Total commands: {info.get("total_commands_processed", "N/A")}')
            except Exception as e:
                self.stdout.write(f'   ⚠ Could not retrieve Redis stats: {e}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Configuration display failed: {e}'))
