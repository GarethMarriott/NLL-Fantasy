"""
Historical league views for viewing past seasons
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q, Sum, Case, When, Value, IntegerField, F, Prefetch
from django.views.decorators.cache import cache_page
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
    
    # Get all available seasons for this league (cached query is fine here)
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
    Optimized with batch queries and caching.
    """
    league = get_object_or_404(League, id=league_id)
    year = int(year)
    
    # Check access
    user_teams = Team.objects.filter(league=league, owner__user=request.user)
    if not user_teams.exists() and league.commissioner != request.user:
        return JsonResponse({'error': 'Not a member of this league'}, status=403)
    
    # Batch load all games for the season efficiently
    weeks_for_season = Week.objects.filter(season=year, is_playoff=False).values_list('id', flat=True)
    games_for_season = Game.objects.filter(week_id__in=weeks_for_season).select_related('week')
    
    # Batch load all player game stats for the season with related data
    all_stats = PlayerGameStat.objects.filter(
        game__week__season=year
    ).select_related('player', 'game__week').prefetch_related('game')
    
    # Build a fast lookup for matchup results and scores by game
    game_scores = {}
    for stat in all_stats:
        game_id = stat.game_id
        if game_id not in game_scores:
            game_scores[game_id] = {
                stat.player.nll_team: 0.0
            }
        elif stat.player.nll_team not in game_scores[game_id]:
            game_scores[game_id][stat.player.nll_team] = 0.0
        
        points = calculate_fantasy_points(stat, stat.player)
        game_scores[game_id][stat.player.nll_team] += points
    
    # Now build standings
    teams = Team.objects.filter(league=league).order_by('name')
    standings = []
    
    for team in teams:
        wins, losses, ties = 0, 0, 0
        total_points = 0.0
        
        # Check which NLL team this fantasy team is associated with
        team_nll_name = None
        team_players = Roster.objects.filter(team=team, season=year).select_related('player')
        if team_players.exists():
            team_nll_name = team_players.first().player.nll_team
        
        if not team_nll_name:
            # If no players, skip
            continue
        
        # Score this team against all games they competed in
        for game_id, scores_by_team in game_scores.items():
            if team_nll_name not in scores_by_team:
                continue
            
            team_score = scores_by_team[team_nll_name]
            total_points += team_score
            
            # Find opponent and their score
            teams_in_game = set(scores_by_team.keys())
            if len(teams_in_game) == 2:
                opponent_name = [t for t in teams_in_game if t != team_nll_name][0]
                opponent_score = scores_by_team[opponent_name]
                
                if team_score > opponent_score:
                    wins += 1
                elif team_score < opponent_score:
                    losses += 1
                else:
                    ties += 1
        
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
    Optimized with batch queries and minimal database hits.
    """
    league = get_object_or_404(League, id=league_id)
    year = int(year)
    
    # Check access
    user_teams = Team.objects.filter(league=league, owner__user=request.user)
    if not user_teams.exists() and league.commissioner != request.user:
        return JsonResponse({'error': 'Not a member of this league'}, status=403)
    
    # Batch load all weeks, games, and stats for the season in minimal queries
    weeks_qs = Week.objects.filter(season=year).order_by('week_number')
    
    # Prefetch games and stats for all weeks at once
    games_prefetch = Prefetch(
        'games',
        Game.objects.select_related('week')
    )
    weeks_with_games = weeks_qs.prefetch_related(games_prefetch)
    
    # Batch load all player game stats for the entire season
    season_stats = PlayerGameStat.objects.filter(
        game__week__season=year
    ).select_related('player', 'game').values_list('game_id', 'player__nll_team', 'player_id', 'id')
    
    # Build efficient lookup: game_id -> {nll_team -> total_score}
    stats_by_game = {}
    for game_id, nll_team, player_id, stat_id in season_stats:
        if game_id not in stats_by_game:
            stats_by_game[game_id] = {}
        if nll_team not in stats_by_game[game_id]:
            stats_by_game[game_id][nll_team] = 0.0
    
    # Now fetch full stats objects only for calculation (still efficient bulk fetch)
    stat_objects = PlayerGameStat.objects.filter(
        game__week__season=year
    ).select_related('player')
    
    # Calculate scores and update lookup
    for stat in stat_objects:
        if stat.game_id in stats_by_game:
            points = calculate_fantasy_points(stat, stat.player)
            stats_by_game[stat.game_id][stat.player.nll_team] = stats_by_game[stat.game_id].get(stat.player.nll_team, 0.0) + points
    
    # Build matchups_by_week
    matchups_by_week = []
    
    for week in weeks_with_games:
        matchups = []
        
        for game in week.games.all():
            home_nll_team = game.home_team
            away_nll_team = game.away_team
            
            # Get pre-calculated scores
            game_teams_scores = stats_by_game.get(game.id, {})
            home_score = game_teams_scores.get(home_nll_team, 0.0)
            away_score = game_teams_scores.get(away_nll_team, 0.0)
            
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

