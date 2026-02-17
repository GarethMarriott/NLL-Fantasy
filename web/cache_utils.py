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
    'nll_schedule': 86400,  # 24 hours - NLL schedule static seasonal data
    'players': 3600,  # 1 hour - players list with stats
    'league_detail': 3600,  # 1 hour - league settings and teams
    'fantasy_points': 900,  # 15 minutes - calculated fantasy points
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


def get_matchups_cache_key_from_request(request):
    """Generate cache key for matchups view (extracts params from request)"""
    # Get league_id from session
    league_id = request.session.get('selected_league_id', 'default')
    
    # Get week from GET params, default to 1
    try:
        week_num = int(request.GET.get('week', 1))
    except (ValueError, TypeError):
        week_num = 1
    
    return get_matchups_cache_key(league_id, week_num)


def get_schedule_cache_key(team_ids_hash, playoff_weeks=None, playoff_teams=None):
    """Generate cache key for schedule build"""
    key = f"schedule:{team_ids_hash}"
    if playoff_weeks:
        key += f":playoff_{playoff_weeks}_{playoff_teams}"
    return key


def get_nll_schedule_cache_key(request):
    """Generate cache key for NLL schedule (uses request GET params)"""
    season = request.GET.get('season', 2026)
    return f"nll_schedule:{season}"


def get_players_cache_key(request):
    """Generate cache key for players list view (uses request GET params)"""
    # Extract filter parameters from GET params
    season = request.GET.get('season', '')
    position = request.GET.get('position', '')
    stat_type = request.GET.get('stat_type', 'regular')
    search = request.GET.get('search', '')
    
    # Include key filters in cache key to handle different filter combinations
    key = f"players:{season}:{position or 'all'}:{stat_type}:{search or 'none'}"
    return key


def get_league_detail_cache_key(league_id):
    """Generate cache key for league detail view"""
    return f"league_detail:{league_id}"


def get_fantasy_points_cache_key(stat_id, player_id, league_id):
    """Generate cache key for calculated fantasy points (function-level caching)"""
    return f"fantasy_points:{league_id}:{player_id}:{stat_id}"


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


def cache_view_with_request(cache_key_func, ttl_key='standings'):
    """
    Decorator to cache view results when cache key depends on request parameters
    
    Args:
        cache_key_func: Function that takes request and returns cache key
        ttl_key: Key in CACHE_TTL dict for expiration time
    
    Usage:
        @cache_view_with_request(lambda request: f"my_view:{request.GET.get('season')}")
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Generate cache key from request
            cache_key = cache_key_func(request)
            
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


def get_waiver_priority_cache_key(league_id):
    """Generate cache key for waiver priority order"""
    return f"waiver_priority:{league_id}"


def cache_schedule_generation(team_ids, playoff_weeks=2, playoff_teams=4, playoff_reseed="fixed"):
    """
    Cache the result of schedule generation.
    Creates a hash of parameters to use as cache key.
    """
    # Create deterministic hash of parameters
    params = f"{sorted(team_ids)}:{playoff_weeks}:{playoff_teams}:{playoff_reseed}"
    param_hash = hashlib.md5(params.encode()).hexdigest()[:8]
    return f"schedule:{param_hash}"


def get_player_stats_by_position_cache_key(season, position, stat_type):
    """Generate cache key for pre-aggregated player stats by position"""
    return f"player_stats:{season}:{position}:{stat_type}"


def get_waiver_priority_cache_key(league_id):
    """Generate cache key for cached waiver priority order"""
    return f"waiver_priority_order:{league_id}"


def cache_get_waiver_priority_order(league_id):
    """
    Get cached waiver priority order for a league.
    
    This caches the result of sorting teams by waiver_priority to avoid
    repeated database queries during waiver processing.
    
    Args:
        league_id: League ID
    
    Returns:
        List of team IDs ordered by waiver priority
    """
    cache_key = get_waiver_priority_cache_key(league_id)
    
    # Try to get from cache
    cached_order = cache.get(cache_key)
    if cached_order is not None:
        return cached_order
    
    # Not in cache, query database
    from web.models import Team
    teams = Team.objects.filter(league_id=league_id).order_by(
        'waiver_priority'
    ).values_list('id', flat=True)
    team_ids = list(teams)
    
    # Cache for 1 hour (waiver priority changes during processing)
    cache.set(cache_key, team_ids, CACHE_TTL.get('team_roster', 1800))
    
    return team_ids
    """Get cache statistics (for monitoring)"""
    return {
        'backend': 'redis',
        'ttl_config': CACHE_TTL,
        'timestamp': timezone.now().isoformat(),
    }
