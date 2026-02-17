"""
NLL Fantasy - Scoring Utilities

This module contains shared scoring calculations used across views.
"""

from .models import League
from django.core.cache import cache


def calculate_fantasy_points(stat_obj, player=None, league=None):
    """
    Calculate fantasy points for a player stat object.
    Caches results to avoid repeated calculations.
    
    Args:
        stat_obj: PlayerGameStat object (can be None)
        player: Player object (None for manual position inference)
        league: League object with scoring settings (defaults to League if None)
    
    Returns:
        Float representing fantasy points, or None if stat_obj is None
    """
    if stat_obj is None:
        return None
    
    # Generate cache key for this calculation
    stat_id = stat_obj.id if hasattr(stat_obj, 'id') else None
    league_id = league.id if league and hasattr(league, 'id') else None
    player_id = player.id if player and hasattr(player, 'id') else None
    
    cache_key = None
    if stat_id and league_id and player_id:
        cache_key = f"fantasy_points:{league_id}:{player_id}:{stat_id}"
        
        # Try to get from cache
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
    
    # Use provided league or get default league
    if league is None:
        league = League.objects.first()
    
    if league is None:
        # Fallback: create a temporary League object with defaults
        league = League()
    
    # Calculate points
    if player and player.position == "G":
        result = (
            stat_obj.wins * float(league.scoring_goalie_wins)
            + stat_obj.saves * float(league.scoring_goalie_saves)
            + stat_obj.goals_against * float(league.scoring_goalie_goals_against)
            + stat_obj.goals * float(league.scoring_goalie_goals)
            + stat_obj.assists * float(league.scoring_goalie_assists)
        )
    else:
        result = (
            stat_obj.goals * float(league.scoring_goals)
            + stat_obj.assists * float(league.scoring_assists)
            + stat_obj.loose_balls * float(league.scoring_loose_balls)
            + stat_obj.caused_turnovers * float(league.scoring_caused_turnovers)
            + stat_obj.blocked_shots * float(league.scoring_blocked_shots)
            + stat_obj.turnovers * float(league.scoring_turnovers)
        )
    
    # Cache the result (15-minute TTL)
    if cache_key:
        cache.set(cache_key, result, 900)  # 900 seconds = 15 minutes
    
    return result
