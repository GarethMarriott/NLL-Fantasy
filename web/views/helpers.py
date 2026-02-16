"""
Helper functions for views
"""
from django.utils import timezone
from ..models import ChatMessage, Roster, TeamChatMessage
from ..constants import TEAM_ABBREVIATIONS


def get_team_abbr(team_name):
    """Get team abbreviation from full team name"""
    return TEAM_ABBREVIATIONS.get(team_name, team_name[:3].upper() if team_name else "")


def post_league_message(league, message_text):
    """Post a system message to league chat"""
    ChatMessage.objects.create(
        league=league,
        sender=None,  # System message
        message=message_text,
        message_type=ChatMessage.MessageType.SYSTEM
    )


def post_team_chat_message(team1, team2, message_text, message_type=None, trade=None, sender=None):
    """Post a message to team-to-team chat"""
    from web.models import TeamChatMessage
    
    # Ensure consistent team ordering (team1 < team2 by ID)
    if team1.id > team2.id:
        team1, team2 = team2, team1
    
    if message_type is None:
        message_type = TeamChatMessage.MessageType.CHAT
    
    TeamChatMessage.objects.create(
        team1=team1,
        team2=team2,
        sender=sender,
        message=message_text,
        message_type=message_type,
        trade=trade
    )


def check_roster_capacity(team, position, exclude_player=None):
    """
    Check if a team has room to add a player to a specific position.
    
    Args:
        team: Team object
        position: Position to check ('O', 'D', 'G')
        exclude_player: Optional player to exclude from count (for swaps)
    
    Returns:
        Tuple of (can_add: bool, current_count: int, max_allowed: int)
    """
    # Count active players in this position
    query = Roster.objects.filter(
        team=team,
        league=team.league,
        week_dropped__isnull=True
    ).select_related('player')
    
    if exclude_player:
        query = query.exclude(player=exclude_player)
    
    # Filter by position - need to check assigned_side if set, otherwise check player position
    players = list(query)
    
    # Count players by their assigned position or natural position
    position_count = 0
    for roster in players:
        # Use assigned_side if set (for transition players), otherwise use natural position
        player_assigned = roster.player.assigned_side if roster.player.assigned_side else roster.player.position
        
        # Count if this player is assigned to the target position
        if player_assigned == position:
            position_count += 1
    
    # Get max slots for this position
    max_slots = {
        'O': team.league.roster_forwards or 6,
        'D': team.league.roster_defense or 6,
        'G': team.league.roster_goalies or 2
    }
    max_allowed = max_slots.get(position, 0)
    
    return position_count < max_allowed, position_count, max_allowed


def auto_assign_to_starter_slot(roster_entry):
    """
    For traditional leagues, automatically assign a player to the first available starter slot.
    For best ball leagues, keep them on bench.
    """
    league = roster_entry.league
    
    # Only auto-assign for traditional leagues with starter slots
    if league.roster_format != 'traditional':
        return
    
    player = roster_entry.player
    team = roster_entry.team
    
    # Determine which position this player occupies
    if player.assigned_side:
        position = player.assigned_side
    else:
        position = player.position
    
    # Map position to slot prefix and max slots (use league configuration)
    slot_map = {
        'O': ('starter_o', league.roster_forwards or 6),
        'D': ('starter_d', league.roster_defense or 6),
        'G': ('starter_g', league.roster_goalies or 2),
        'T': (None, 0),  # Transition players need assigned_side
    }
    
    if position not in slot_map or slot_map[position][0] is None:
        return
    
    slot_prefix, max_slots = slot_map[position]
    
    # Find which starter slots are already filled for this position
    filled_slots = set()
    existing_roster = Roster.objects.filter(
        team=team,
        league=league,
        week_dropped__isnull=True
    ).select_related('player').exclude(id=roster_entry.id)
    
    for entry in existing_roster:
        if entry.slot_assignment.startswith(slot_prefix):
            try:
                if slot_prefix == 'starter_g':
                    filled_slots.add(1)
                else:
                    slot_num = int(entry.slot_assignment.replace(slot_prefix, ''))
                    filled_slots.add(slot_num)
            except ValueError:
                pass
    
    # Find first available slot
    for slot_num in range(1, max_slots + 1):
        if slot_num not in filled_slots:
            if slot_prefix == 'starter_g':
                roster_entry.slot_assignment = slot_prefix
            else:
                roster_entry.slot_assignment = f"{slot_prefix}{slot_num}"
            roster_entry.save()
            break


def create_transaction_notification(transaction_type, team, player, user=None):
    """Create a notification for a transaction (pickup, drop, trade)"""
    from web.models import Notification
    if user:
        Notification.objects.create(
            user=user,
            notification_type=transaction_type,
            team=team,
            player=player
        )
