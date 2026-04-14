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
    Also shows top 10 team and player weekly scores across all seasons.
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
    
    teams = list(league.teams.all())
    team_ids = [t.id for t in teams]
    
    # Calculate top 10 team weekly scores
    from collections import defaultdict
    team_weekly_scores = []
    week_cache = {}
    rosters_by_team_season = defaultdict(list)
    
    # Build roster cache for all seasons
    all_rosters = Roster.objects.filter(
        team__in=teams, league=league, player__active=True
    ).select_related("player", "team").prefetch_related("player__game_stats__game__week")
    
    for roster_entry in all_rosters:
        key = (roster_entry.team_id, roster_entry.season)
        rosters_by_team_season[key].append(roster_entry)
    
    # Get all weeks for this league across all seasons
    all_weeks_obj = Week.objects.filter(season__in=seasons).order_by('season', 'week_number')
    
    for team in teams:
        for season in seasons:
            rosters = rosters_by_team_season.get((team.id, season), [])
            if not rosters:
                continue
            
            weeks_for_season = Week.objects.filter(season=season, is_playoff=False).order_by('week_number')
            
            for week_obj in weeks_for_season:
                total = 0.0
                active_players = []
                
                # Get players active during this week
                for roster_entry in rosters:
                    week_added = roster_entry.week_added or 0
                    week_dropped = roster_entry.week_dropped or 999
                    if week_added <= week_obj.week_number < week_dropped:
                        if league.roster_format == 'traditional':
                            if roster_entry.slot_assignment and roster_entry.slot_assignment.startswith('starter_'):
                                active_players.append(roster_entry.player)
                        else:
                            active_players.append(roster_entry.player)
                
                # Calculate score for this week
                for p in active_players:
                    stat = next((s for s in p.game_stats.all() if s.game.week_id == week_obj.id), None)
                    pts = calculate_fantasy_points(stat, p, league)
                    if pts is not None:
                        total += pts
                
                if total > 0 or active_players:  # Only include if there were players or points
                    team_weekly_scores.append({
                        'team': team,
                        'year': season,
                        'week': week_obj.week_number,
                        'points': total,
                    })
    
    # Sort and get top 10
    team_weekly_scores.sort(key=lambda x: -x['points'])
    top_team_scores = team_weekly_scores[:10]
    
    # Calculate top 10 player weekly scores
    player_weekly_scores = []
    all_player_stats = PlayerGameStat.objects.filter(
        player__active=True,
        game__week__season__in=seasons
    ).select_related('player', 'game__week').prefetch_related('game')
    
    player_rosters_cache = defaultdict(list)
    for roster_entry in all_rosters:
        player_rosters_cache[roster_entry.player_id].append(roster_entry)
    
    for stat in all_player_stats:
        player = stat.player
        week_obj = stat.game.week
        pts = calculate_fantasy_points(stat, player, league)
        
        if pts is not None and pts > 0:
            # Find which fantasy team this player was on during this week
            roster_entries = player_rosters_cache.get(player.id, [])
            fantasy_team = None
            
            for roster_entry in roster_entries:
                if roster_entry.season == week_obj.season:
                    week_added = roster_entry.week_added or 0
                    week_dropped = roster_entry.week_dropped or 999
                    if week_added <= week_obj.week_number < week_dropped:
                        fantasy_team = roster_entry.team
                        break
            
            if fantasy_team:
                player_weekly_scores.append({
                    'player': player,
                    'nll_team': player.nll_team,
                    'fantasy_team': fantasy_team,
                    'year': week_obj.season,
                    'week': week_obj.week_number,
                    'points': pts,
                })
    
    # Sort and get top 10
    player_weekly_scores.sort(key=lambda x: -x['points'])
    top_player_scores = player_weekly_scores[:10]
    
    context = {
        'league': league,
        'seasons': seasons,
        'current_season': current_season,
        'is_commissioner': league.commissioner == request.user,
        'top_team_scores': top_team_scores,
        'top_player_scores': top_player_scores,
    }
    
    return render(request, 'web/league_history.html', context)


@login_required
def league_history_standings(request, league_id, year):
    """
    Display historical standings for a specific league season.
    Read-only view of past standings using league matchup schedule.
    Calculates standings by comparing fantasy team scores in their matchups.
    """
    league = get_object_or_404(League, id=league_id)
    year = int(year)
    
    # Check access
    user_teams = Team.objects.filter(league=league, owner__user=request.user)
    if not user_teams.exists() and league.commissioner != request.user:
        return JsonResponse({'error': 'Not a member of this league'}, status=403)
    
    teams = list(league.teams.order_by("name"))
    if not teams:
        context = {'league': league, 'year': year, 'standings': [], 'is_historical': True}
        return render(request, 'web/league_history_standings.html', context)
    
    # Get the schedule for this league
    team_ids = [t.id for t in teams]
    all_weeks = get_cached_schedule(team_ids, league.playoff_weeks, league.playoff_teams, league.playoff_reseed or "fixed")
    
    # Batch load rosters for this season
    rosters = list(
        Roster.objects.filter(team__in=teams, league=league, season=year, player__active=True)
        .select_related("player", "team")
        .prefetch_related("player__game_stats__game__week")
    )
    
    # Group rosters by team_id for O(1) lookup
    from collections import defaultdict
    rosters_by_team = defaultdict(list)
    for roster_entry in rosters:
        rosters_by_team[roster_entry.team_id].append(roster_entry)
    
    week_cache = {}
    standings_map = {
        t.id: {
            "team": t,
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "total_points": 0.0,
            "points_against": 0.0,
            "games": 0,
        }
        for t in teams
    }
    
    def team_week_total(team_id, week_number):
        """Calculate a team's fantasy points for a specific week"""
        week_obj = week_cache.get(week_number)
        if week_obj is None:
            # Get week from the specific season
            week_obj = Week.objects.filter(week_number=week_number, season=year).first()
            week_cache[week_number] = week_obj
        
        total = 0.0
        
        # Get active players on roster during this week
        active_players = []
        team_rosters = rosters_by_team.get(team_id, [])
        for roster_entry in team_rosters:
            # Check if player was active during this week
            week_added = roster_entry.week_added or 0
            week_dropped = roster_entry.week_dropped or 999
            if week_added <= week_number < week_dropped:
                # For traditional leagues, only count starters
                if league.roster_format == 'traditional':
                    if roster_entry.slot_assignment and roster_entry.slot_assignment.startswith('starter_'):
                        active_players.append(roster_entry.player)
                else:
                    # For best ball, count all players
                    active_players.append(roster_entry.player)
        
        for p in active_players:
            stat = None
            if week_obj:
                stat = next((s for s in p.game_stats.all() if s.game.week_id == week_obj.id), None)
            pts = calculate_fantasy_points(stat, p, league)
            if pts is not None:
                total += pts
        
        return total
    
    # Only process regular season weeks (skip playoff weeks)
    regular_season_weeks = Week.objects.filter(season=year, is_playoff=False).order_by('week_number')
    max_week = regular_season_weeks.last().week_number if regular_season_weeks.exists() else 0
    
    # Go through schedule and calculate matchups
    for idx, games in enumerate(all_weeks[:max_week], start=1):
        for matchup in games:
            # Skip playoff matchups
            if isinstance(matchup, tuple) and len(matchup) == 4 and matchup[0] == 'playoff':
                continue
            
            team_a_id, team_b_id = matchup
            
            # Only count matchups between teams in this league
            if team_a_id not in standings_map or team_b_id not in standings_map:
                continue
            
            home_total = team_week_total(team_a_id, idx)
            away_total = team_week_total(team_b_id, idx)
            
            standings_map[team_a_id]["total_points"] += home_total
            standings_map[team_b_id]["total_points"] += away_total
            standings_map[team_a_id]["points_against"] += away_total
            standings_map[team_b_id]["points_against"] += home_total
            standings_map[team_a_id]["games"] += 1
            standings_map[team_b_id]["games"] += 1
            
            if home_total > away_total:
                standings_map[team_a_id]["wins"] += 1
                standings_map[team_b_id]["losses"] += 1
            elif home_total < away_total:
                standings_map[team_b_id]["wins"] += 1
                standings_map[team_a_id]["losses"] += 1
            else:
                standings_map[team_a_id]["ties"] += 1
                standings_map[team_b_id]["ties"] += 1
    
    # Build final standings list
    standings = list(standings_map.values())
    standings.sort(key=lambda r: (-r["wins"], -r["ties"], -r["total_points"], r["team"].name))
    
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
    from collections import defaultdict
    league = get_object_or_404(League, id=league_id)
    year = int(year)
    
    # Check access
    user_teams = Team.objects.filter(league=league, owner__user=request.user)
    if not user_teams.exists() and league.commissioner != request.user:
        return JsonResponse({'error': 'Not a member of this league'}, status=403)
    
    teams = list(league.teams.order_by("name"))
    if not teams:
        context = {'league': league, 'year': year, 'championship': {}, 'is_historical': True}
        return render(request, 'web/league_history_playoffs.html', context)
    
    # Get the schedule for this league
    team_ids = [t.id for t in teams]
    all_weeks = get_cached_schedule(team_ids, league.playoff_weeks, league.playoff_teams, league.playoff_reseed or "fixed")
    
    # Determine playoff start week from schedule structure (first playoff matchup)
    # Regular season = 18 weeks, playoffs start at week 19
    playoff_start_week = 19
    
    # Batch load rosters for this season
    rosters = list(
        Roster.objects.filter(team__in=teams, league=league, season=year, player__active=True)
        .select_related("player", "team")
        .prefetch_related("player__game_stats__game__week")
    )
    
    # Group rosters by team_id for O(1) lookup
    rosters_by_team = defaultdict(list)
    for roster_entry in rosters:
        rosters_by_team[roster_entry.team_id].append(roster_entry)
    
    week_cache = {}
    
    def calculate_playoff_week_score(team_id, week_number):
        """Calculate a team's fantasy points for a specific week"""
        week_obj = week_cache.get(week_number)
        if week_obj is None:
            week_obj = Week.objects.filter(week_number=week_number, season=year).first()
            week_cache[week_number] = week_obj
        
        total = 0.0
        
        # Get active players on roster during this week
        active_players = []
        team_rosters = rosters_by_team.get(team_id, [])
        for roster_entry in team_rosters:
            week_added = roster_entry.week_added or 0
            week_dropped = roster_entry.week_dropped or 999
            if week_added <= week_number < week_dropped:
                if league.roster_format == 'traditional':
                    if roster_entry.slot_assignment and roster_entry.slot_assignment.startswith('starter_'):
                        active_players.append(roster_entry.player)
                else:
                    active_players.append(roster_entry.player)
        
        for p in active_players:
            stat = None
            if week_obj:
                stat = next((s for s in p.game_stats.all() if s.game.week_id == week_obj.id), None)
            pts = calculate_fantasy_points(stat, p, league)
            if pts is not None:
                total += pts
        
        return total
    
    # Get standings (seeds) for the season from regular season only
    standings_map = {t.id: {'team': t, 'wins': 0, 'losses': 0, 'ties': 0} for t in teams}
    
    # Process regular season only (weeks 1-18)
    for idx, games in enumerate(all_weeks[:18], start=1):
        for matchup in games:
            if isinstance(matchup, tuple) and len(matchup) == 4 and matchup[0] == 'playoff':
                continue  # Skip playoff matchups
            
            team_a_id, team_b_id = matchup
            if team_a_id not in standings_map or team_b_id not in standings_map:
                continue
            
            home_total = team_week_total_history(team_a_id, idx, rosters_by_team, week_cache, year, league)
            away_total = team_week_total_history(team_b_id, idx, rosters_by_team, week_cache, year, league)
            
            if home_total > away_total:
                standings_map[team_a_id]['wins'] += 1
                standings_map[team_b_id]['losses'] += 1
            elif home_total < away_total:
                standings_map[team_b_id]['wins'] += 1
                standings_map[team_a_id]['losses'] += 1
            else:
                standings_map[team_a_id]['ties'] += 1
                standings_map[team_b_id]['ties'] += 1
    
    # Sort for playoff seeds
    standings_list = sorted(
        standings_map.values(),
        key=lambda x: (-x['wins'], -x['ties'], -x['team'].id)
    )
    
    # Assign playoff seeds
    seed_to_team = {}
    for seed, standing in enumerate(standings_list[:league.playoff_teams], start=1):
        standing['playoff_seed'] = seed
        seed_to_team[seed] = standing['team']
    
    # Build playoff bracket by processing playoff weeks from schedule
    playoff_winners = {}
    playoff_losers = {}
    semifinal_matchups = []
    third_place_matchup = None
    final_matchup = None
    champion = None
    
    # First pass: Process playoff weeks and track winners/losers
    winner_index = 1
    for week_idx in range(playoff_start_week - 1, min(21, len(all_weeks))):
        week_matchups = all_weeks[week_idx]
        actual_week_num = week_idx + 1
        
        for matchup in week_matchups:
            if isinstance(matchup, tuple) and len(matchup) == 4 and matchup[0] == 'playoff':
                _, seed1, seed2, round_name = matchup
                
                # Resolve team IDs from seeds or winner references
                def resolve_seed(seed):
                    if isinstance(seed, int):
                        return seed_to_team.get(seed)
                    else:
                        if seed.startswith('L'):
                            return playoff_losers.get(seed)
                        else:
                            return playoff_winners.get(seed)
                
                home_team = resolve_seed(seed1)
                away_team = resolve_seed(seed2)
                
                if home_team and away_team:
                    home_score = calculate_playoff_week_score(home_team.id, actual_week_num)
                    away_score = calculate_playoff_week_score(away_team.id, actual_week_num)
                    
                    # Store winner and loser for future rounds
                    if home_score > away_score:
                        playoff_winners[f'W{winner_index}'] = home_team
                        playoff_losers[f'L{winner_index}'] = away_team
                    elif away_score > home_score:
                        playoff_winners[f'W{winner_index}'] = away_team
                        playoff_losers[f'L{winner_index}'] = home_team
                    else:
                        # Tie - home team wins
                        playoff_winners[f'W{winner_index}'] = home_team
                        playoff_losers[f'L{winner_index}'] = away_team
                    winner_index += 1
    
    # Second pass: Build bracket display with resolved teams and scores
    winner_index = 1
    for week_idx in range(playoff_start_week - 1, min(21, len(all_weeks))):
        week_matchups = all_weeks[week_idx]
        actual_week_num = week_idx + 1
        
        for matchup in week_matchups:
            if isinstance(matchup, tuple) and len(matchup) == 4 and matchup[0] == 'playoff':
                _, seed1, seed2, round_name = matchup
                
                # Resolve team IDs - handle W#, L# placeholders
                def resolve_seed(seed):
                    if isinstance(seed, int):
                        return seed_to_team.get(seed)
                    else:
                        if seed.startswith('L'):
                            return playoff_losers.get(seed)
                        else:
                            return playoff_winners.get(seed)
                
                home_team = resolve_seed(seed1)
                away_team = resolve_seed(seed2)
                
                if home_team and away_team:
                    home_id = home_team.id
                    away_id = away_team.id
                    home_score = calculate_playoff_week_score(home_id, actual_week_num)
                    away_score = calculate_playoff_week_score(away_id, actual_week_num)
                    
                    # Get seeds for display
                    home_seed = next((s for s in standings_list if s['team'].id == home_id), {}).get('playoff_seed', 'N/A')
                    away_seed = next((s for s in standings_list if s['team'].id == away_id), {}).get('playoff_seed', 'N/A')
                    
                    matchup_info = {
                        'team1': home_team,
                        'team1_score': home_score,
                        'team1_seed': home_seed,
                        'team2': away_team,
                        'team2_score': away_score,
                        'team2_seed': away_seed,
                        'winner_id': home_id if home_score > away_score else away_id if away_score > home_score else None,
                    }
                    
                    # Categorize by round
                    if round_name == 'Semifinal':
                        semifinal_matchups.append(matchup_info)
                    elif round_name == 'Third Place':
                        third_place_matchup = matchup_info
                    elif round_name == 'Championship':
                        final_matchup = matchup_info
                        # Track champion
                        if matchup_info['winner_id']:
                            champion = next((t for t in teams if t.id == matchup_info['winner_id']), None)
                    
                    # Update winner and loser tracker for next round
                    if home_score > away_score:
                        playoff_winners[f'W{winner_index}'] = home_team
                        playoff_losers[f'L{winner_index}'] = away_team
                    elif away_score > home_score:
                        playoff_winners[f'W{winner_index}'] = away_team
                        playoff_losers[f'L{winner_index}'] = home_team
                    else:
                        playoff_winners[f'W{winner_index}'] = home_team
                        playoff_losers[f'L{winner_index}'] = away_team
                    winner_index += 1
    
    playoff_bracket = {
        'semifinals': semifinal_matchups,
        'third_place': third_place_matchup,
        'final': final_matchup,
    }
    
    championship_info = {
        'champion': champion,
        'running_for_year': year,
    }
    
    context = {
        'league': league,
        'year': year,
        'championship': championship_info,
        'playoff_bracket': playoff_bracket,
        'is_historical': True,
    }
    
    return render(request, 'web/league_history_playoffs.html', context)


def team_week_total_history(team_id, week_number, rosters_by_team, week_cache, year, league):
    """Calculate a team's fantasy points for a specific week in historical context"""
    week_obj = week_cache.get(week_number)
    if week_obj is None:
        week_obj = Week.objects.filter(week_number=week_number, season=year).first()
        week_cache[week_number] = week_obj
    
    total = 0.0
    
    active_players = []
    team_rosters = rosters_by_team.get(team_id, [])
    for roster_entry in team_rosters:
        week_added = roster_entry.week_added or 0
        week_dropped = roster_entry.week_dropped or 999
        if week_added <= week_number < week_dropped:
            if league.roster_format == 'traditional':
                if roster_entry.slot_assignment and roster_entry.slot_assignment.startswith('starter_'):
                    active_players.append(roster_entry.player)
            else:
                active_players.append(roster_entry.player)
    
    for p in active_players:
        stat = None
        if week_obj:
            stat = next((s for s in p.game_stats.all() if s.game.week_id == week_obj.id), None)
        pts = calculate_fantasy_points(stat, p, league)
        if pts is not None:
            total += pts
    
    return total

