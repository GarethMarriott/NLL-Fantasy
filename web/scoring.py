"""
NLL Fantasy - Scoring Utilities

This module contains shared scoring calculations used across views.
"""

from .models import League


def calculate_fantasy_points(stat_obj, player=None, league=None):
    """
    Calculate fantasy points for a player stat object.
    
    Args:
        stat_obj: PlayerGameStat object (can be None)
        player: Player object (None for manual position inference)
        league: League object with scoring settings (defaults to League if None)
    
    Returns:
        Float representing fantasy points, or None if stat_obj is None
    """
    if stat_obj is None:
        return None
    
    # Use provided league or get default league
    if league is None:
        league = League.objects.first()
    
    if league is None:
        # Fallback: create a temporary League object with defaults
        league = League()
    
    # Goalie scoring
    if player and player.position == "G":
        return (
            stat_obj.wins * float(league.scoring_goalie_wins)
            + stat_obj.saves * float(league.scoring_goalie_saves)
            + stat_obj.goals_against * float(league.scoring_goalie_goals_against)
            + stat_obj.goals * float(league.scoring_goalie_goals)
            + stat_obj.assists * float(league.scoring_goalie_assists)
        )
    
    # Field player scoring (O, D, or T)
    return (
        stat_obj.goals * float(league.scoring_goals)
        + stat_obj.assists * float(league.scoring_assists)
        + stat_obj.loose_balls * float(league.scoring_loose_balls)
        + stat_obj.caused_turnovers * float(league.scoring_caused_turnovers)
        + stat_obj.blocked_shots * float(league.scoring_blocked_shots)
        + stat_obj.turnovers * float(league.scoring_turnovers)
    )
