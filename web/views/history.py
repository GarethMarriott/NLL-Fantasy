"""
Historical league views for viewing past seasons
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q, Sum, Case, When, Value, IntegerField, F
from web.models import League, Team, Roster, Week, Game, PlayerGameStat
from web.scoring import calculate_fantasy_points
from web.cache_utils import get_standings_cache_key


@login_required
def league_history(request, league_id):
    """
    Display available historical seasons for a league.
    Shows list of past years with links to view each season's data.
    """
    league = get_object_or_404(League, id=league_id)
    
    # Check if user is member of league
    user_teams = Team.objects.filter(league=league, owner__user=request.user)
    if not user_teams.exists() and league.commissioner != request.user:
        return JsonResponse({'error': 'Not a member of this league'}, status=403)
    
    # Get all available seasons for this league
    available_seasons = Roster.objects.filter(
        league=league
    ).values('season').distinct().order_by('-season')
    
    seasons = [s['season'] for s in available_seasons]
    current_season = league.season
    
    context = {
        'league': league,
        'seasons': seasons,
        'current_season': current_season,
        'is_commissioner': league.commissioner == request.user,
    }
    
    return render(request, 'web/league_history.html', context)


@login_required
def league_history_standings(request, league_id, year):
    """
    Display historical standings for a specific league season.
    Read-only view of past standings.
    """
    league = get_object_or_404(League, id=league_id)
    year = int(year)
    
    # Check access
    user_teams = Team.objects.filter(league=league, owner__user=request.user)
    if not user_teams.exists() and league.commissioner != request.user:
        return JsonResponse({'error': 'Not a member of this league'}, status=403)
    
    # Build historical standings
    teams = Team.objects.filter(league=league).order_by('name')
    standings = []
    
    for team in teams:
        # Get all matchups for this team in the specified year
        weeks = Week.objects.filter(season=year).order_by('week_number')
        wins, losses, ties = 0, 0, 0
        total_points = 0.0
        
        for week in weeks:
            if week.is_playoff:
                continue  # Skip playoff calculation for standings
            
            # Get this team's score for the week
            team_a_rosters = Roster.objects.filter(
                team=team, league=league, season=year
            )
            team_a_score = 0.0
            for roster in team_a_rosters:
                stat = roster.player.game_stats.filter(game__week=week).first()
                if stat:
                    team_a_score += calculate_fantasy_points(stat, roster.player)
            
            # Find opponent and their score
            try:
                schedule = Week.objects.get(season=year, week_number=week.week_number)
                # Try to find the matchup from game results
                games = Game.objects.filter(week=week)
                opponent = None
                team_b_score = 0.0
                
                for game in games:
                    if game.home_team.id == team.id or game.away_team.id == team.id:
                        opponent = game.away_team if game.home_team.id == team.id else game.home_team
                        
                        # Calculate opponent score
                        opponent_rosters = Roster.objects.filter(
                            team=opponent, league=league, season=year
                        )
                        for roster in opponent_rosters:
                            stat = roster.player.game_stats.filter(game__week=week).first()
                            if stat:
                                team_b_score += calculate_fantasy_points(stat, roster.player)
                        break
                
                if opponent:
                    if team_a_score > team_b_score:
                        wins += 1
                    elif team_a_score < team_b_score:
                        losses += 1
                    else:
                        ties += 1
                    total_points += team_a_score
            except:
                pass
        
        standings.append({
            'team': team,
            'wins': wins,
            'losses': losses,
            'ties': ties,
            'points': total_points,
        })
    
    # Sort standings
    standings.sort(key=lambda x: (-x['wins'], -x['points']))
    
    context = {
        'league': league,
        'year': year,
        'standings': standings,
        'is_historical': True,
    }
    
    return render(request, 'web/league_history_standings.html', context)


@login_required
def league_history_matchups(request, league_id, year):
    """
    Display historical matchups for a specific league season.
    Read-only view of past matchups and scores.
    """
    league = get_object_or_404(League, id=league_id)
    year = int(year)
    
    # Check access
    user_teams = Team.objects.filter(league=league, owner__user=request.user)
    if not user_teams.exists() and league.commissioner != request.user:
        return JsonResponse({'error': 'Not a member of this league'}, status=403)
    
    # Get all weeks for this year
    weeks = Week.objects.filter(season=year).order_by('week_number')
    matchups_by_week = []
    
    for week in weeks:
        matchups = []
        games = Game.objects.filter(week=week)
        
        for game in games:
            home_nll_team = game.home_team  # NLL team name string
            away_nll_team = game.away_team   # NLL team name string
            
            # Get all game stats for this game and calculate scores by team
            game_stats = PlayerGameStat.objects.filter(game=game)
            
            home_score = 0.0
            away_score = 0.0
            
            for stat in game_stats:
                # Sum points by NLL team
                points = calculate_fantasy_points(stat, stat.player)
                
                if stat.player.nll_team == home_nll_team:
                    home_score += points
                elif stat.player.nll_team == away_nll_team:
                    away_score += points
            
            matchups.append({
                'home_team': home_nll_team,
                'away_team': away_nll_team,
                'home_score': home_score,
                'away_score': away_score,
                'winner': home_nll_team if home_score > away_score else (away_nll_team if away_score > home_score else None),
                'is_tie': home_score == away_score,
            })
        
        if matchups:
            matchups_by_week.append({
                'week': week,
                'matchups': matchups,
            })
    
    context = {
        'league': league,
        'year': year,
        'matchups_by_week': matchups_by_week,
        'is_historical': True,
    }
    
    return render(request, 'web/league_history_matchups.html', context)


@login_required
def league_history_playoffs(request, league_id, year):
    """
    Display historical playoff bracket and results for a specific league season.
    Shows championship winner and bracket progression.
    """
    league = get_object_or_404(League, id=league_id)
    year = int(year)
    
    # Check access
    user_teams = Team.objects.filter(league=league, owner__user=request.user)
    if not user_teams.exists() and league.commissioner != request.user:
        return JsonResponse({'error': 'Not a member of this league'}, status=403)
    
    # Find the champion for this year
    # This would need playoff bracket data stored - for now, show champion if available
    championship_info = {
        'champion': None,
        'running_for_year': year,
    }
    
    # TODO: Implement playoff bracket display from historical data
    # This would need to store playoff bracket structure and results
    
    context = {
        'league': league,
        'year': year,
        'championship': championship_info,
        'is_historical': True,
    }
    
    return render(request, 'web/league_history_playoffs.html', context)
