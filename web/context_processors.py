from .models import League


def selected_league(request):
    """Add selected league to template context"""
    selected_league_id = request.session.get('selected_league_id')
    league = None
    
    if selected_league_id:
        try:
            league = League.objects.get(id=selected_league_id)
        except League.DoesNotExist:
            pass
    
    return {
        'selected_league': league
    }
