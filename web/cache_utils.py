"""
Caching utilities for improving application performance

Provides cache key generation, TTL strategies, and invalidation handles
for expensive database queries and calculations.
"""

from django.core.cache import cache
from django.utils import timezone
from functools import wraps
import hashlib
import json


# Cache TTL (Time to Live) strategies
CACHE_TTL = {
    'standings': 3600,  # 1 hour - recalculate hourly
    'team_detail': 1800,  # 30 minutes - roster data fairly static
    'matchups': 3600,  # 1 hour - schedule doesn't change often
    'player_stats': 900,  # 15 minutes - stats update weekly
    'team_roster': 1800,  # 30 minutes - roster changes via trades/waivers
    'schedule': 86400,  # 24 hours - schedule is static
}


def get_standings_cache_key(league_id, week_num=None):
    """Generate cache key for standings data"""
    key = f"standings:{league_id}"
    if week_num:
        key += f":week_{week_num}"
    return key


def get_team_detail_cache_key(team_id, week_num):
    """Generate cache key for team detail view"""
    return f"team_detail:{team_id}:week_{week_num}"


def get_team_roster_cache_key(team_id):
    """Generate cache key for team roster"""
    return f"team_roster:{team_id}"


def get_matchups_cache_key(league_id, week_num):
    """Generate cache key for matchups"""
    return f"matchups:{league_id}:week_{week_num}"


def get_schedule_cache_key(team_ids_hash, playoff_weeks=None, playoff_teams=None):
    """Generate cache key for schedule build"""
    key = f"schedule:{team_ids_hash}"
    if playoff_weeks:
        key += f":playoff_{playoff_weeks}_{playoff_teams}"
    return key


def invalidate_league_cache(league_id):
    """Invalidate all cached data for a league"""
    # Clear standings for all weeks
    for week in range(0, 19):
        cache_key = get_standings_cache_key(league_id, week)
        cache.delete(cache_key)
    
    # Clear standings without week
    cache_key = get_standings_cache_key(league_id)
    cache.delete(cache_key)


def invalidate_team_cache(team_id):
    """Invalidate all cached data for a team"""
    # Clear roster cache
    cache.delete(get_team_roster_cache_key(team_id))
    
    # Clear team detail for all weeks
    for week in range(0, 19):
        cache_key = get_team_detail_cache_key(team_id, week)
        cache.delete(cache_key)


def invalidate_matchups_cache(league_id):
    """Invalidate matchups cache for a league"""
    for week in range(0, 19):
        cache_key = get_matchups_cache_key(league_id, week)
        cache.delete(cache_key)


def cache_view_result(cache_key_func, ttl_key='standings'):
    """
    Decorator to cache view results
    
    Args:
        cache_key_func: Function that generates cache key from view args/kwargs
        ttl_key: Key in CACHE_TTL dict for expiration time
    
    Usage:
        @cache_view_result(lambda league_id: f"my_view:{league_id}")
        def my_view(request, league_id):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Generate cache key
            cache_key = cache_key_func(*args, **kwargs)
            
            # Try to get from cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Not in cache, call view
            result = view_func(request, *args, **kwargs)
            
            # Cache the result
            ttl = CACHE_TTL.get(ttl_key, 3600)
            cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


def cache_function_result(cache_key_func, ttl_key='standings', use_self=False):
    """
    Decorator to cache function results (non-view functions)
    
    Args:
        cache_key_func: Function that generates cache key from function args
        ttl_key: Key in CACHE_TTL dict for expiration time  
        use_self: If True, skips 'self' argument when building cache key
    
    Usage:
        @cache_function_result(lambda league_id: f"get_standings:{league_id}")
        def get_standings(league_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Handle self argument for methods
            cache_args = args[1:] if use_self else args
            
            # Generate cache key
            cache_key = cache_key_func(*cache_args, **kwargs)
            
            # Try to get from cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Not in cache, call function
            result = func(*args, **kwargs)
            
            # Cache the result
            ttl = CACHE_TTL.get(ttl_key, 3600)
            cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator


def get_cache_stats():
    """Get cache statistics (for monitoring)"""
    return {
        'backend': 'redis',
        'ttl_config': CACHE_TTL,
        'timestamp': timezone.now().isoformat(),
    }
