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
from web.views import get_cached_schedule  # Import schedule generation


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
    Display historical Fantasy team matchups for a specific league season.
    Shows Fantasy teams vs Fantasy teams with weekly scores following league settings.
    """
    from collections import defaultdict
    
    league = get_object_or_404(League, id=league_id)
    year = int(year)
    
    # Check access
    user_teams = Team.objects.filter(league=league, owner__user=request.user)
    if not user_teams.exists() and league.commissioner != request.user:
        return JsonResponse({'error': 'Not a member of this league'}, status=403)
    
    # Get all Fantasy teams in the league
    teams = list(Team.objects.filter(league=league).order_by('id'))
    if not teams:
        context = {
            'league': league,
            'year': year,
            'matchups_by_week': [],
            'is_historical': True,
        }
        return render(request, 'web/league_history_matchups.html', context)
    
    team_ids = [t.id for t in teams]
    id_to_team = {t.id: t for t in teams}
    
    # Get the schedule for this season
    playoff_weeks = getattr(league, 'playoff_weeks', 2)
    playoff_teams = getattr(league, 'playoff_teams', 4)
    playoff_reseed = getattr(league, 'playoff_reseed', 'fixed')
    all_weeks_schedule = get_cached_schedule(team_ids, playoff_weeks, playoff_teams, playoff_reseed)
    
    # Get all weeks from database for the season
    weeks_in_season = Week.objects.filter(season=year).order_by('week_number')
    week_map = {w.week_number: w for w in weeks_in_season}
    
    # Batch load all rosters for the season with stats
    all_rosters = Roster.objects.filter(
        team__in=teams, season=year
    ).select_related('player').prefetch_related('player__game_stats__game__week')
    
    rosters_by_team = defaultdict(list)
    for roster_entry in all_rosters:
        rosters_by_team[roster_entry.team_id].append(roster_entry)
    
    # Helper to calculate team score for a specific week
    def get_team_week_score(team_id, week_number):
        """Calculate a Fantasy team's score for a specific week, respecting league settings"""
        week_obj = week_map.get(week_number)
        if not week_obj:
            return 0.0
        
        team_rosters = rosters_by_team.get(team_id, [])
        player_scores = []
        
        for roster_entry in team_rosters:
            # Check if player was on roster during this week
            week_added = roster_entry.week_added or 0
            week_dropped = roster_entry.week_dropped or 999
            if week_added <= week_number < week_dropped:
                player = roster_entry.player
                
                # Get stats for this week
                game_stats = [s for s in player.game_stats.all() if s.game.week_id == week_obj.id]
                if game_stats:
                    # Calculate fantasy points for each game
                    pts_list = [calculate_fantasy_points(st, player, league) for st in game_stats if st]
                    if pts_list:
                        # Apply league's multigame_scoring setting (best_ball)
                        multigame_setting = getattr(league, 'multigame_scoring', 'highest')
                        if multigame_setting == "average" and len(pts_list) > 1:
                            fpts = sum(pts_list) / len(pts_list)
                        else:  # Default to highest
                            fpts = max(pts_list)
                        
                        player_scores.append((player, fpts))
        
        # Apply league format (traditional vs best_ball)
        league_format = getattr(league, 'roster_format', 'best_ball')
        
        if league_format == 'traditional':
            # For traditional: only count assigned starters
            slot_assignments = {r.player_id: r.slot_assignment for r in team_rosters}
            
            num_starter_o = getattr(league, 'roster_forwards', 6) or 6
            num_starter_d = getattr(league, 'roster_defense', 6) or 6
            num_starter_g = getattr(league, 'roster_goalies', 2) or 2
            
            starters_o = [s for s in player_scores if slot_assignments.get(s[0].id, '').startswith('starter_o')][:num_starter_o]
            starters_d = [s for s in player_scores if slot_assignments.get(s[0].id, '').startswith('starter_d')][:num_starter_d]
            starters_g = [s for s in player_scores if slot_assignments.get(s[0].id, '').startswith('starter_g')][:num_starter_g]
            
            total = sum(s[1] for s in starters_o + starters_d + starters_g if s[1])
        else:
            # For best_ball: top 3 O, top 3 D, top 1 G
            players_by_side = defaultdict(list)
            for player, points in player_scores:
                side = getattr(player, 'assigned_side', None) or (
                    'D' if getattr(player, 'position', None) == 'D' else 'O'
                )
                if getattr(player, 'position', None) == 'G':
                    side = 'G'
                players_by_side[side].append(points)
            
            off_scores = sorted(players_by_side.get('O', []), reverse=True)[:3]
            def_scores = sorted(players_by_side.get('D', []), reverse=True)[:3]
            goal_scores = sorted(players_by_side.get('G', []), reverse=True)[:1]
            
            total = sum(off_scores) + sum(def_scores) + sum(goal_scores)
        
        return total
    
    # Build matchups by week from the schedule
    matchups_by_week = []
    
    for week_num, games_in_week in enumerate(all_weeks_schedule, start=1):
        if not games_in_week:
            continue
        
        matchups = []
        
        for game in games_in_week:
            # Handle playoff tuples like ('playoff', seed1, seed2, ...)
            if isinstance(game, tuple) and game[0] == 'playoff':
                # Skip playoff formatting for now, just use team IDs
                if len(game) < 3:
                    continue
                home_team_id = game[1]
                away_team_id = game[2]
            else:
                home_team_id, away_team_id = game
            
            # Calculate scores
            home_score = get_team_week_score(home_team_id, week_num)
            away_score = get_team_week_score(away_team_id, week_num)
            
            home_team_obj = id_to_team.get(home_team_id)
            away_team_obj = id_to_team.get(away_team_id)
            
            if home_team_obj and away_team_obj:
                matchups.append({
                    'home_team': home_team_obj,
                    'away_team': away_team_obj,
                    'home_score': home_score,
                    'away_score': away_score,
                    'winner': home_team_obj if home_score > away_score else (
                        away_team_obj if away_score > home_score else None
                    ),
                    'is_tie': home_score == away_score,
                })
        
        if matchups:
            week_obj = week_map.get(week_num)
            matchups_by_week.append({
                'week': week_obj or type('obj', (), {'week_number': week_num})(),
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

