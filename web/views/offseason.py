"""
Offseason management views for league renewal, draft finalization, and roster management
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone

from web.models import League, Team, Roster, Player


@login_required
def league_offseason(request, league_id):
    """
    Display offseason options for commissioner.
    Shows:
    - Season winner
    - Option to renew league if season is complete
    - Current roster lock status
    """
    league = get_object_or_404(League, id=league_id)
    
    # Only commissioner can access this
    if league.commissioner != request.user:
        messages.error(request, "Only the league commissioner can access this page.")
        return redirect('home')
    
    context = {
        'league': league,
        'can_renew': league.status == 'season_complete',
        'season_winner': league.season_winner,
    }
    
    return render(request, 'web/league_offseason.html', context)


@login_required
@transaction.atomic
def offseason_renew_league(request, league_id):
    """
    Process league renewal based on league type:
    - Redraft: Clear all rosters, advance season, unlock rosters for draft
    - Dynasty: Keep rosters, advance season, clear draft lock, only rookies enter draft
    
    POST request only
    """
    league = get_object_or_404(League, id=league_id)
    
    # Only commissioner can renew
    if league.commissioner != request.user:
        return JsonResponse({'success': False, 'error': 'Only commissioner can renew league'}, status=403)
    
    # Only can renew if season is complete
    if league.status != 'season_complete':
        return JsonResponse({'success': False, 'error': 'League season is not complete'}, status=400)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST requests allowed'}, status=400)
    
    try:
        # Advance season
        league.season += 1
        league.draft_locked = True  # Lock during draft
        
        # Get all teams in league
        teams = Team.objects.filter(league=league)
        
        if league.league_type == 'redraft':
            # Clear all rosters for redraft leagues
            Roster.objects.filter(league=league, season=league.season - 1).delete()
            messages.success(request, 'All rosters have been cleared. Begin draft!')
            
        elif league.league_type == 'dynasty':
            # For dynasty: update existing rosters to new season, keep players
            old_rosters = Roster.objects.filter(league=league, season=league.season - 1)
            for roster_entry in old_rosters:
                # Copy roster entry to new season
                Roster.objects.create(
                    team=roster_entry.team,
                    player=roster_entry.player,
                    league=league,
                    slot_assignment=roster_entry.slot_assignment,
                    week_added=1,  # Reset to week 1 of new season
                    week_dropped=None,
                    season=league.season,
                    is_locked=False,
                    locked_reason='',
                )
            messages.success(request, 'League renewed! Existing rosters preserved. Draft rookies only.')
            league.draft_locked = False  # Dynasty unlocks immediately
        
        # Update league status
        league.status = 'renewal_complete'
        league.season_winner = None  # Clear previous winner
        league.save()
        
        # Unlock rosters after renewal
        for team in teams:
            Roster.objects.filter(team=team, season=league.season, is_locked=True).update(
                is_locked=False,
                locked_reason=''
            )
        
        return JsonResponse({
            'success': True,
            'message': f'League renewed for season {league.season}',
            'league_type': league.league_type,
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def lock_rosters(request, league_id):
    """
    Lock all rosters in a league for offseason.
    Called automatically when season ends.
    """
    league = get_object_or_404(League, id=league_id)
    
    # Only commissioner
    if league.commissioner != request.user:
        return JsonResponse({'success': False, 'error': 'Only commissioner allowed'}, status=403)
    
    try:
        rosters = Roster.objects.filter(league=league, season=league.season)
        rosters.update(is_locked=True, locked_reason='offseason')
        
        league.status = 'season_complete'
        league.save()
        
        return JsonResponse({'success': True, 'locked_count': rosters.count()})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def finalize_draft(request, league_id):
    """
    Finalize draft for a league.
    - Redraft: Unlock rosters
    - Dynasty: Already unlocked during renewal
    """
    league = get_object_or_404(League, id=league_id)
    
    # Only commissioner
    if league.commissioner != request.user:
        return JsonResponse({'success': False, 'error': 'Only commissioner allowed'}, status=403)
    
    if not league.draft_locked:
        return JsonResponse({'success': False, 'error': 'Draft is not currently locked'}, status=400)
    
    try:
        # Unlock rosters - draft is over
        rosters = Roster.objects.filter(league=league, season=league.season)
        rosters.update(is_locked=False, locked_reason='')
        
        league.draft_locked = False
        league.save()
        
        messages.success(request, 'Draft finalized! Rosters are now unlocked.')
        return JsonResponse({'success': True, 'unlocked_count': rosters.count()})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def crown_champion(request, league_id):
    """
    Crown the championship winner (called from standings view when playoffs complete).
    Identifies the playoff winner and sets them as season_winner.
    """
    league = get_object_or_404(League, id=league_id)
    
    # Get the championship winner from final playoff results
    # This will be the team that won the final week of playoffs
    try:
        from web.views import get_cached_schedule, Week
        
        playoff_start_week = 21 - league.playoff_weeks
        latest_week = Week.objects.order_by('-season', '-week_number').first()
        season = latest_week.season if latest_week else timezone.now().year
        
        # Find championship winner from playoff weeks
        teams = Team.objects.filter(league=league)
        team_ids = [t.id for t in teams]
        schedule = get_cached_schedule(team_ids, league.playoff_weeks, league.playoff_teams)
        
        # The final matchup will be in the last playoff week
        # We'd need to process through all playoff weeks to find winner
        # For now, this would be called with the championship team as POST data
        
        if request.method == 'POST':
            champion_team_id = request.POST.get('champion_team_id')
            if not champion_team_id:
                return JsonResponse({'success': False, 'error': 'No champion specified'}, status=400)
            
            champion = get_object_or_404(Team, id=champion_team_id, league=league)
            league.season_winner = champion
            league.status = 'season_complete'
            league.save()
            
            # Lock all rosters
            Roster.objects.filter(league=league, season=league.season).update(
                is_locked=True,
                locked_reason='offseason'
            )
            
            messages.success(request, f'{champion.name} is the 2025-2026 NLL Fantasy Champion! 🏆')
            return JsonResponse({'success': True, 'champion': champion.name})
        
        return JsonResponse({'success': False, 'error': 'POST required'}, status=400)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
