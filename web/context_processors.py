from .models import League, FantasyTeamOwner


def selected_league(request):
    """Add selected league to template context"""
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
    
    return {
        'selected_league': league,
        'user_has_league': user_has_league
    }
