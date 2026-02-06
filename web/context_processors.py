from .models import League, FantasyTeamOwner, ChatMessage, TeamChatMessage
from datetime import datetime, timedelta


def selected_league(request):
    """Add selected league to template context"""
    from web.models import Team
    
    selected_league_id = request.session.get('selected_league_id')
    league = None
    
    if selected_league_id:
        try:
            league = League.objects.get(id=selected_league_id)
        except League.DoesNotExist:
            pass
    
    # Check if user is in any league
    user_has_league = False
    if request.user.is_authenticated:
        user_has_league = FantasyTeamOwner.objects.filter(user=request.user).exists()
    
    # Calculate unread chat counts for sidebar badge
    total_unread_chats = 0
    if request.user.is_authenticated and selected_league_id:
        # Initialize chat read tracking in session if needed
        if 'chat_last_read' not in request.session:
            request.session['chat_last_read'] = {}
        
        # Get user's team
        owner = FantasyTeamOwner.objects.filter(
            user=request.user,
            team__league_id=selected_league_id
        ).select_related('team').first()
        
        if owner:
            user_team = owner.team
            chat_last_read = request.session.get('chat_last_read', {})
            
            # Check league chat for unread
            league_chat_key = f"league_{selected_league_id}"
            last_read = chat_last_read.get(league_chat_key)
            if last_read:
                try:
                    last_read_dt = datetime.fromisoformat(last_read)
                    league_unread = ChatMessage.objects.filter(
                        league_id=selected_league_id,
                        created_at__gt=last_read_dt
                    ).count()
                except (ValueError, TypeError):
                    league_unread = 0
            else:
                # Count recent messages (last 7 days)
                cutoff = datetime.now() - timedelta(days=7)
                league_unread = ChatMessage.objects.filter(
                    league_id=selected_league_id,
                    created_at__gt=cutoff
                ).count()
            
            if league_unread > 0:
                total_unread_chats += 1
            
            # Check team chats for unread
            available_team_chats = Team.objects.filter(
                league_id=selected_league_id
            ).exclude(id=user_team.id)
            
            for other_team in available_team_chats:
                team1_id = min(user_team.id, other_team.id)
                team2_id = max(user_team.id, other_team.id)
                chat_key = f"team_{team1_id}_{team2_id}"
                
                last_read = chat_last_read.get(chat_key)
                if last_read:
                    try:
                        last_read_dt = datetime.fromisoformat(last_read)
                        unread = TeamChatMessage.objects.filter(
                            team1_id=team1_id,
                            team2_id=team2_id,
                            created_at__gt=last_read_dt
                        ).count()
                    except (ValueError, TypeError):
                        unread = 0
                else:
                    # Count recent messages (last 7 days)
                    cutoff = datetime.now() - timedelta(days=7)
                    unread = TeamChatMessage.objects.filter(
                        team1_id=team1_id,
                        team2_id=team2_id,
                        created_at__gt=cutoff
                    ).count()
                
                if unread > 0:
                    total_unread_chats += 1
    
    return {
        'selected_league': league,
        'user_has_league': user_has_league,
        'total_unread_chats': total_unread_chats
    }
