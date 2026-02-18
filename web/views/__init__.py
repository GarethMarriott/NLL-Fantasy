from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db import models
from django.db.models import Q
from django.urls import reverse_lazy

from ..models import Player, Team, Week, Game, ChatMessage, FantasyTeamOwner, League, Roster, PlayerGameStat, WaiverClaim, Draft, DraftPosition, DraftPick, Trade, TradePlayer
from ..forms import UserRegistrationForm, LeagueCreateForm, TeamCreateForm, LeagueSettingsForm, TeamSettingsForm, PasswordResetForm, SetPasswordForm
from ..tasks import send_password_reset_email
from ..constants import TEAM_NAME_TO_ID, TEAM_ID_TO_NAME, EXTENDED_TEAM_ID_TO_NAME, TEAM_ABBREVIATIONS
from ..scoring import calculate_fantasy_points
from ..cache_utils import cache_view_result, cache_view_with_request, get_standings_cache_key, get_standings_cache_key_from_request, get_team_detail_cache_key, get_matchups_cache_key, get_matchups_cache_key_from_request, get_nll_schedule_cache_key, get_players_cache_key, get_league_detail_cache_key, invalidate_team_cache, invalidate_league_cache
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache


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
    from ..models import TeamChatMessage
    
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


@login_required
def my_team(request):
    """Redirect to the user's team in the selected league."""
    selected_league_id = request.session.get('selected_league_id')
    
    if not selected_league_id:
        # Auto-select league if user has exactly one
        user_leagues = FantasyTeamOwner.objects.filter(user=request.user).select_related('team__league')
        if user_leagues.count() == 1:
            selected_league_id = user_leagues.first().team.league.id
            request.session['selected_league_id'] = selected_league_id
        else:
            # Redirect to league list if user has multiple leagues or no league
            return redirect('league_list')
    
    try:
        owner = FantasyTeamOwner.objects.select_related('team').get(
            user=request.user,
            team__league_id=selected_league_id
        )
        return redirect('team_detail', team_id=owner.team.id)
    except FantasyTeamOwner.DoesNotExist:
        return redirect('league_list')


def home(request):
    # Redirect to team detail page if user has a selected league
    if request.user.is_authenticated:
        selected_league_id = request.session.get('selected_league_id')
        
        # Auto-select league if user has exactly one
        if not selected_league_id:
            user_leagues = FantasyTeamOwner.objects.filter(user=request.user).select_related('team__league')
            if user_leagues.count() == 1:
                selected_league_id = user_leagues.first().team.league.id
                request.session['selected_league_id'] = selected_league_id
        
        if selected_league_id:
            try:
                owner = FantasyTeamOwner.objects.select_related('team').get(
                    user=request.user,
                    team__league_id=selected_league_id
                )
                # Redirect to team detail page
                return redirect('team_detail', team_id=owner.team.id)
            except FantasyTeamOwner.DoesNotExist:
                pass
    
    # If not authenticated or no team, show a simple landing page
    return render(request, "web/index.html", {})


def about(request):
    return render(request, "web/about.html")


def team_detail(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    
    # Get league for scoring settings
    league = team.league if team.league else League()
    
    # Get all available weeks for dropdown - filter by league's season
    league_season = league.created_at.year if league.created_at else timezone.now().year
    available_weeks = list(Week.objects.filter(season=league_season).order_by('week_number'))
    
    # Add future week placeholders (up to week 20 for NLL season)
    if available_weeks:
        max_week = available_weeks[-1].week_number
        for future_week_num in range(max_week + 1, 21):
            # Create a placeholder dict for future weeks
            available_weeks.append({
                'week_number': future_week_num,
                'season': league_season,
                'is_future': True
            })
    else:
        # No weeks exist yet, create placeholders for weeks 1-20
        for week_num in range(1, 21):
            available_weeks.append({
                'week_number': week_num,
                'season': league_season,
                'is_future': True
            })
    
    # Find the next unlocked week (where roster changes are allowed)
    # This ensures the main pinned week matches the week where roster changes can be made
    current_date = timezone.now().date()
    
    # Find the next unlocked week
    next_unlocked_week = None
    all_weeks = Week.objects.filter(season=league_season).order_by('week_number')
    for w in all_weeks:
        if not w.is_locked():
            next_unlocked_week = w
            break
    
    # Determine default week to display
    if next_unlocked_week:
        # Show the next unlocked week (where roster changes are allowed)
        default_week_num = next_unlocked_week.week_number
    else:
        # No unlocked weeks - fall back to first future week
        future_week = Week.objects.filter(
            season=league_season,
            start_date__gt=current_date
        ).order_by('week_number').first()
        
        if future_week:
            default_week_num = future_week.week_number
        else:
            default_week_num = 1
    
    # Get selected week from query params
    selected_week_num = request.GET.get('week')
    if selected_week_num:
        try:
            selected_week_num = int(selected_week_num)
        except (ValueError, TypeError):
            selected_week_num = default_week_num
    else:
        selected_week_num = default_week_num
    
    # Get the selected week object to check if it's locked
    selected_week_obj = Week.objects.filter(
        season=league_season,
        week_number=selected_week_num
    ).first()
    
    # Determine if viewing a past/locked week (disable buttons)
    # A week is locked if its start_date has already passed
    is_viewing_past_week = False
    if selected_week_obj:
        is_viewing_past_week = selected_week_obj.start_date <= current_date
    elif selected_week_num < default_week_num:
        # If week object doesn't exist but week number is before default, it's a past week
        is_viewing_past_week = True
    
    # Check if the current user owns this team
    user_owns_team = False
    if request.user.is_authenticated:
        user_owns_team = FantasyTeamOwner.objects.filter(
            user=request.user,
            team=team
        ).exists()

    players_by_position = {"O": [], "D": [], "G": [], "T": []}
    
    # determine most recent season available for weekly breakdown
    recent_week = Week.objects.order_by("-season", "-week_number").first()
    season = recent_week.season if recent_week else None

    # Keep players in order of their slot assignment (for traditional leagues)
    # Get players through roster entries for this team's league
    # Filter to show only players who were on the roster during the selected week
    from django.db.models import Q
    
    roster = team.roster_entries.select_related('player').prefetch_related(
        'player__game_stats__game__week'
    ).filter(
        Q(week_dropped__isnull=True) | Q(week_dropped__gt=selected_week_num),
        player__active=True
    ).filter(
        Q(week_added__isnull=True) | Q(week_added__lte=selected_week_num)
    ).order_by("player__updated_at", "player__id")
    
    # OPTIMIZATION: Build stats index once at view level instead of filtering per-player
    # Index stats by (player_id, week_id) for O(1) lookups
    stats_index = {}
    stats_by_player_week_num = {}  # Index by (player_id, week_number) for quicker lookups
    for player in [entry.player for entry in roster]:
        game_stats = [s for s in player.game_stats.all() if season is None or s.game.week.season == season]
        
        # Index by (player_id, week_id) and (player_id, week_number) for fast lookups
        for stat in game_stats:
            week_id = stat.game.week_id
            week_num = stat.game.week.week_number
            
            stats_index.setdefault((player.id, week_id), []).append(stat)
            stats_by_player_week_num.setdefault((player.id, week_num), []).append(stat)
    
    # OPTIMIZATION: Fetch all games for selected week upfront to avoid N+1 queries
    # Build a map of games by team_id for O(1) lookups
    games_by_team_id = {}
    if selected_week_num:
        week_games = Game.objects.filter(
            week__week_number=selected_week_num,
            week__season=league_season
        )
        for game in week_games:
            # Store game keyed by home and away team IDs
            games_by_team_id[game.home_team] = game
            games_by_team_id[game.away_team] = game
    
    for roster_entry in roster:
        p = roster_entry.player
        
        # OPTIMIZATION: Get stats from index instead of filtering/looping
        game_stats = stats_by_player_week_num.get((p.id, 0), [])  # Placeholder for all stats
        # For latest stat, we need all stats regardless of week, so collect them
        all_player_stats = []
        for week_num in range(1, 19):
            all_player_stats.extend(stats_by_player_week_num.get((p.id, week_num), []))
        # Find latest stat (most recent game)
        latest = max(all_player_stats, key=lambda s: (s.game.date, s.game.id), default=None)

        # Calculate weekly points for all 18 weeks
        weekly_points = []
        total_points = 0
        for wk in range(1, 19):
            # OPTIMIZATION: O(1) lookup instead of building dict per-player
            stats_list = stats_by_player_week_num.get((p.id, wk), [])
            if not stats_list:
                weekly_points.append(None)
                continue
            pts_list = [calculate_fantasy_points(st, p, league) for st in stats_list if st is not None]
            if not pts_list:
                weekly_points.append(None)
                continue
            if league.multigame_scoring == "average" and len(pts_list) > 1:
                pts = sum(pts_list) / len(pts_list)
            elif league.multigame_scoring == "highest":
                pts = max(pts_list)
            else:
                pts = max(pts_list)
            weekly_points.append(pts)
            if pts is not None:
                total_points += pts

        # Get opponent for the selected week
        opponent = "BYE"
        player_team_id = TEAM_NAME_TO_ID.get(p.nll_team) if p.nll_team else None
        if p.nll_team and player_team_id:
            # Use pre-fetched games lookup instead of querying for each player
            game = games_by_team_id.get(player_team_id)
            if game:
                opponent = f"{TEAM_ID_TO_NAME.get(game.home_team, game.home_team)} @ {TEAM_ID_TO_NAME.get(game.away_team, game.away_team)}"
        
        entry = {"player": p, "latest_stat": latest, "weekly_points": weekly_points, "weeks_total": total_points, "counts_for_total": [False] * 18, "selected_week_points": weekly_points[selected_week_num - 1] if selected_week_num <= len(weekly_points) else None, "opponent": opponent}

        pos = getattr(p, "position", None)
        side = getattr(p, "assigned_side", None)
        target = side or ("O" if pos == "T" else pos)
        if target in players_by_position:
            players_by_position[target].append(entry)
        else:
            players_by_position["O"].append(entry)

    # Get roster entries with slot assignments for proper ordering
    roster_with_slots = team.roster_entries.select_related('player').filter(
        Q(week_dropped__isnull=True) | Q(week_dropped__gt=selected_week_num),
        player__active=True
    ).filter(
        Q(week_added__isnull=True) | Q(week_added__lte=selected_week_num)
    )
    
    # Create a mapping of player_id to slot_assignment
    player_to_slot = {entry.player_id: entry.slot_assignment for entry in roster_with_slots}
    
    # Check if this league uses starter slots (traditional leagues only)
    # Best ball leagues should NEVER use starter slots, even if somehow a player has one assigned
    is_traditional = league.roster_format == 'traditional' if hasattr(league, 'roster_format') else False
    has_starter_slots = is_traditional and any(slot.startswith('starter_') for slot in player_to_slot.values())
    
    # Get slot counts from league configuration for traditional leagues, use defaults for best ball
    if league.roster_format == 'traditional':
        num_offence = league.roster_forwards or 6
        num_defence = league.roster_defense or 6
        num_goalie = league.roster_goalies or 2
    else:
        # Best ball uses fixed counts
        num_offence = 6
        num_defence = 6
        num_goalie = 2
    
    if has_starter_slots:
        # Reorder pools by slot assignment for leagues with starter slots
        def sort_by_slot_assignment(entries, slot_prefix, max_slots):
            """Sort entries by their slot assignment (e.g., starter_o1, starter_o2, starter_o3)"""
            slots = {}
            bench = []
            for entry in entries:
                player_id = entry['player'].id
                slot = player_to_slot.get(player_id, 'bench')
                if slot.startswith(slot_prefix):
                    # Extract slot number
                    try:
                        slot_num = int(slot.replace(slot_prefix, ''))
                        slots[slot_num] = entry
                    except ValueError:
                        # Handle case where slot is just the prefix (e.g., 'starter_g')
                        slots[1] = entry
                else:
                    bench.append(entry)
            
            # Build ordered list using league-configured max slots, not hardcoded 6
            result = []
            for i in range(1, max_slots + 1):
                if i in slots:
                    result.append(slots[i])
                else:
                    result.append(None)
            result.extend(bench)
            return result
        
        # Sort each position pool by slot assignment using league configuration
        offence_pool = sort_by_slot_assignment(players_by_position["O"], 'starter_o', num_offence)
        defence_pool = sort_by_slot_assignment(players_by_position["D"], 'starter_d', num_defence)
        goalie_pool = sort_by_slot_assignment(players_by_position["G"], 'starter_g', num_goalie)
    else:
        # For leagues without starter slots (best ball), use position pools as-is
        offence_pool = players_by_position["O"]
        defence_pool = players_by_position["D"]
        goalie_pool = players_by_position["G"]

    offence_slots = offence_pool[:num_offence]
    defence_slots = defence_pool[:num_defence]
    goalie_slots = goalie_pool[:num_goalie]

    while len(offence_slots) < num_offence:
        offence_slots.append(None)
    while len(defence_slots) < num_defence:
        defence_slots.append(None)
    while len(goalie_slots) < num_goalie:
        goalie_slots.append(None)

    # Create bench slots for traditional leagues
    bench_slots = []
    if league.roster_format == 'traditional':
        num_bench = league.roster_bench or 6
        # Collect all unassigned players (those in bench position across all position pools)
        bench_players = []
        
        # Get bench players from each position pool (they're appended after starters in sort_by_slot_assignment)
        if has_starter_slots:
            # Bench players are those after the first num_offence/num_defence/num_goalie in the pool
            bench_players.extend(offence_pool[num_offence:])
            bench_players.extend(defence_pool[num_defence:])
            bench_players.extend(goalie_pool[num_goalie:])
        else:
            # No starters, all players could be bench
            bench_players.extend(offence_pool)
            bench_players.extend(defence_pool)
            bench_players.extend(goalie_pool)
        
        # Remove None entries and create bench slots
        bench_players = [p for p in bench_players if p is not None]
        bench_slots = bench_players[:num_bench]
        
        # Pad with None to reach desired bench count
        while len(bench_slots) < num_bench:
            bench_slots.append(None)

    # Mark starter status based on slot assignment for all league types
    for slot_group in [offence_slots, defence_slots, goalie_slots]:
        for slot in slot_group:
            if slot:
                player_id = slot['player'].id
                slot_assignment = player_to_slot.get(player_id, 'bench')
                slot['is_starter'] = slot_assignment.startswith('starter_') if slot_assignment else False
                slot['slot_assignment'] = slot_assignment

    # Aggregate weekly totals: top 3 offense, top 3 defense, top 1 goalie
    # Also mark which stats count toward the total
    # Calculate for the selected week only
    week_idx = selected_week_num - 1  # Convert to 0-indexed
    
    # Get all offense scores for this week with slot reference
    offense_scores = []
    for slot in offence_slots:
        if slot and slot.get("weekly_points") and week_idx < len(slot["weekly_points"]) and slot["weekly_points"][week_idx] is not None:
            offense_scores.append((slot["weekly_points"][week_idx], slot))
    
    # Get all defense scores for this week with slot reference
    defense_scores = []
    for slot in defence_slots:
        if slot and slot.get("weekly_points") and week_idx < len(slot["weekly_points"]) and slot["weekly_points"][week_idx] is not None:
            defense_scores.append((slot["weekly_points"][week_idx], slot))
    
    # Get all goalie scores for this week with slot reference
    goalie_scores = []
    for slot in goalie_slots:
        if slot and slot.get("weekly_points") and week_idx < len(slot["weekly_points"]) and slot["weekly_points"][week_idx] is not None:
            goalie_scores.append((slot["weekly_points"][week_idx], slot))
    
    # Sort by score descending
    offense_scores.sort(key=lambda x: x[0], reverse=True)
    defense_scores.sort(key=lambda x: x[0], reverse=True)
    goalie_scores.sort(key=lambda x: x[0], reverse=True)
    
    if is_traditional:
        # For traditional leagues, only mark assigned starters as counting
        # Use league's configured starter counts
        num_starter_offense = league.roster_forwards or 6
        num_starter_defense = league.roster_defense or 6
        num_starter_goalie = league.roster_goalies or 2
        
        # Get the assigned offense starters
        starter_offense = [slot for slot in offence_slots if slot and slot.get('is_starter')][:num_starter_offense]
        starter_defense = [slot for slot in defence_slots if slot and slot.get('is_starter')][:num_starter_defense]
        starter_goalie = [slot for slot in goalie_slots if slot and slot.get('is_starter')][:num_starter_goalie]
        
        # Mark these specific slots as counting
        for slot in starter_offense + starter_defense + starter_goalie:
            slot["counts_for_total"][week_idx] = True
            slot["selected_week_counts"] = True
        
        # Calculate total only from starters
        selected_week_total = sum(slot['selected_week_points'] for slot in starter_offense + starter_defense + starter_goalie 
                                  if slot and slot['selected_week_points'] is not None)
    else:
        # For best ball, mark top 3 offense, top 3 defense, top 1 goalie as counting
        for score, slot in offense_scores[:3]:
            slot["counts_for_total"][week_idx] = True
            slot["selected_week_counts"] = True
        
        for score, slot in defense_scores[:3]:
            slot["counts_for_total"][week_idx] = True
            slot["selected_week_counts"] = True
        
        for score, slot in goalie_scores[:1]:
            slot["counts_for_total"][week_idx] = True
            slot["selected_week_counts"] = True
        
        # Calculate total for selected week only
        selected_week_total = sum(x[0] for x in offense_scores[:3]) + sum(x[0] for x in defense_scores[:3]) + sum(x[0] for x in goalie_scores[:1])
    
    # Calculate overall total across all weeks (for the Total column)
    overall_total = 0
    for week_idx_all in range(18):
        if is_traditional:
            # For traditional, sum all starter scores across all weeks using league's configured counts
            starter_offense_all = [slot for slot in offence_slots if slot and slot.get('is_starter') and slot.get("weekly_points") and week_idx_all < len(slot["weekly_points"]) and slot["weekly_points"][week_idx_all] is not None][:num_starter_offense]
            starter_defense_all = [slot for slot in defence_slots if slot and slot.get('is_starter') and slot.get("weekly_points") and week_idx_all < len(slot["weekly_points"]) and slot["weekly_points"][week_idx_all] is not None][:num_starter_defense]
            starter_goalie_all = [slot for slot in goalie_slots if slot and slot.get('is_starter') and slot.get("weekly_points") and week_idx_all < len(slot["weekly_points"]) and slot["weekly_points"][week_idx_all] is not None][:num_starter_goalie]
            
            week_total_all = sum(slot["weekly_points"][week_idx_all] for slot in starter_offense_all + starter_defense_all + starter_goalie_all)
        else:
            # For best ball, top 3 of each position
            offense_scores_all = []
            for slot in offence_slots:
                if slot and slot.get("weekly_points") and week_idx_all < len(slot["weekly_points"]) and slot["weekly_points"][week_idx_all] is not None:
                    offense_scores_all.append(slot["weekly_points"][week_idx_all])
            
            defense_scores_all = []
            for slot in defence_slots:
                if slot and slot.get("weekly_points") and week_idx_all < len(slot["weekly_points"]) and slot["weekly_points"][week_idx_all] is not None:
                    defense_scores_all.append(slot["weekly_points"][week_idx_all])
            
            goalie_scores_all = []
            for slot in goalie_slots:
                if slot and slot.get("weekly_points") and week_idx_all < len(slot["weekly_points"]) and slot["weekly_points"][week_idx_all] is not None:
                    goalie_scores_all.append(slot["weekly_points"][week_idx_all])
            
            offense_scores_all.sort(reverse=True)
            defense_scores_all.sort(reverse=True)
            goalie_scores_all.sort(reverse=True)
            
            week_total_all = sum(offense_scores_all[:3]) + sum(defense_scores_all[:3]) + sum(goalie_scores_all[:1])
        
        overall_total += week_total_all

    # Get all players with their team assignment in this league (if any) - CURRENT ROSTER ONLY
    players_with_teams = []
    all_players = Player.objects.filter(active=True).order_by("last_name", "first_name")
    for player in all_players:
        roster_entry = Roster.objects.filter(
            player=player,
            league=team.league,
            week_dropped__isnull=True  # Only check current roster assignments
        ).select_related('team').first()
        players_with_teams.append({
            'player': player,
            'team_in_league': roster_entry.team if roster_entry else None
        })


    # Only show pending waivers/trades to the team owner
    if user_owns_team:
        pending_waiver_claims = team.waiver_claims.filter(
            status=WaiverClaim.Status.PENDING
        ).select_related('player_to_add', 'player_to_drop', 'week').order_by('priority', 'created_at')
        pending_trades = Trade.objects.filter(
            (models.Q(proposing_team=team) | models.Q(receiving_team=team)) &
            (
                models.Q(status=Trade.Status.PENDING) |
                (models.Q(status=Trade.Status.ACCEPTED) & models.Q(executed_at__isnull=True))
            )
        ).select_related('proposing_team', 'receiving_team').prefetch_related(
            'players__player', 'players__from_team', 'picks__future_rookie_pick', 'picks__from_team'
        ).order_by('-created_at')
        pending_changes_count = pending_waiver_claims.count() + pending_trades.count()
    else:
        pending_waiver_claims = []
        pending_trades = []
        pending_changes_count = 0
    use_waivers = team.league.use_waivers if hasattr(team.league, 'use_waivers') else False

    # Get taxi squad for dynasty leagues
    taxi_squad_entries = []
    taxi_squad_size = 0
    use_taxi_squad = False
    is_dynasty = league.league_type == 'dynasty' if hasattr(league, 'league_type') else False
    
    # Get future rookie picks for dynasty leagues
    future_picks = []
    use_future_picks = False
    
    if is_dynasty:
        from ..models import TaxiSquad, FutureRookiePick
        # Get configured taxi squad size (defaults to 3 for dynasty leagues)
        taxi_squad_size = getattr(league, 'taxi_squad_size', 3)
        # Check if taxi squad is enabled (defaults to True for dynasty leagues)
        use_taxi_squad = getattr(league, 'use_taxi_squad', True)
        
        # Only fetch entries if taxi squad is enabled  
        if use_taxi_squad:
            taxi_squad_entries = list(TaxiSquad.objects.filter(team=team).select_related('player').order_by('slot_number'))
        
        # Get future rookie picks (defaults to True for dynasty leagues)
        use_future_picks = getattr(league, 'use_future_rookie_picks', True)
        
        # Only fetch picks if future picks are enabled
        if use_future_picks:
            from django.db.models import F
            # Get all future picks for this team, grouped by year
            picks_queryset = FutureRookiePick.objects.filter(
                team=team,
                league=league
            ).order_by('year', 'round_number', 'pick_number')
            
            # Group by year
            future_picks_by_year = {}
            for pick in picks_queryset:
                if pick.year not in future_picks_by_year:
                    future_picks_by_year[pick.year] = []
                future_picks_by_year[pick.year].append(pick)
            
            future_picks = future_picks_by_year
    else:
        # For non-dynasty leagues, still initialize to empty dict
        from ..models import TaxiSquad

    # Check if team is over roster limit
    current_roster_count, is_over_limit = team.is_over_roster_limit()
    roster_limit = team.league.roster_size if hasattr(team.league, 'roster_size') else 14

    return render(
        request,
        "web/team_detail.html",
        {
            "team": team,
            "league": league,
            "user_owns_team": user_owns_team,
            "offence_slots": offence_slots,
            "defence_slots": defence_slots,
            "goalie_slots": goalie_slots,
            "bench_slots": bench_slots,
            "week_range": [selected_week_num],  # Only show selected week
            "selected_week": selected_week_num,
            "selected_week_obj": selected_week_obj,
            "available_weeks": available_weeks,
            "current_week": default_week_num,
            "selected_week_total": selected_week_total,
            "overall_total": overall_total,
            "players_for_select": players_with_teams,
            "roster_status": team.can_make_roster_changes(selected_week_obj),
            "is_viewing_past_week": is_viewing_past_week,
            "pending_waiver_claims": pending_waiver_claims,
            "pending_trades": pending_trades,
            "pending_changes_count": pending_changes_count,
            "use_waivers": use_waivers,
            "is_traditional": is_traditional,
            "is_dynasty": is_dynasty,
            "taxi_squad_entries": taxi_squad_entries,
            "taxi_squad_size": taxi_squad_size,
            "use_taxi_squad": use_taxi_squad,
            "future_picks": future_picks,
            "use_future_picks": use_future_picks,
            "is_over_roster_limit": is_over_limit,
            "current_roster_count": current_roster_count,
            "roster_limit": roster_limit,
        },
    )


@login_required
def manage_lineup(request, team_id):
    """Manage team lineup for traditional league format"""
    team = get_object_or_404(Team, id=team_id)
    league = team.league
    
    # Check if user owns this team
    if not (hasattr(team, 'owner') and team.owner and team.owner.user == request.user):
        messages.error(request, "You do not have permission to manage this team's lineup.")
        return redirect('team_detail', team_id=team_id)
    
    # Only allow lineup management for traditional leagues
    if league.roster_format != 'traditional':
        messages.error(request, "Lineup management is only available for traditional format leagues.")
        return redirect('team_detail', team_id=team_id)
    
    # Handle form submission
    if request.method == 'POST':
        # Update player slot assignments
        roster_items = Roster.objects.filter(team=team)
        for roster_item in roster_items:
            slot_key = f'player_{roster_item.player.id}_slot'
            if slot_key in request.POST:
                new_slot = request.POST[slot_key]
                # Validate slot value
                valid_slots = [choice[0] for choice in Roster.SLOT_CHOICES]
                if new_slot in valid_slots:
                    roster_item.slot_assignment = new_slot
                    roster_item.save()
        
        # Validate starter slot count
        starter_slots = Roster.objects.filter(
            team=team,
            slot_assignment__startswith='starter_'
        ).count()
        
        required_starters = league.roster_forwards + league.roster_defense + league.roster_goalies
        if starter_slots != required_starters:
            messages.error(request, f"You must have exactly {required_starters} starters ({league.roster_forwards} Offense, {league.roster_defense} Defense, {league.roster_goalies} Goalie).")
            return redirect('manage_lineup', team_id=team_id)
        
        messages.success(request, "Lineup updated successfully!")
        return redirect('team_detail', team_id=team_id)
    
    # GET request - show lineup management page
    roster_items = Roster.objects.filter(team=team).select_related('player')
    
    # Separate players by slot assignment - use league configuration
    offense_slots = [f'starter_o{i}' for i in range(1, league.roster_forwards + 1)]
    defense_slots = [f'starter_d{i}' for i in range(1, league.roster_defense + 1)]
    
    starter_offense = roster_items.filter(slot_assignment__in=offense_slots)
    starter_defense = roster_items.filter(slot_assignment__in=defense_slots)
    starter_goalie = roster_items.filter(slot_assignment='starter_g')
    bench_players = roster_items.filter(slot_assignment='bench')
    
    context = {
        'team': team,
        'league': league,
        'starter_offense': starter_offense,
        'starter_defense': starter_defense,
        'starter_goalie': starter_goalie,
        'bench_players': bench_players,
        'all_roster': roster_items,
        'slot_choices': Roster.SLOT_CHOICES,
    }
    
    return render(request, 'web/manage_lineup.html', context)


@require_POST
def assign_player(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    
    # Check if the user owns this team
    if not request.user.is_authenticated:
        messages.error(request, "You must be logged in to make roster changes.")
        return redirect("team_detail", team_id=team.id)
    
    team_owner = FantasyTeamOwner.objects.filter(
        user=request.user,
        team=team
    ).first()
    
    if not team_owner:
        messages.error(request, "You don't have permission to modify this team.")
        return redirect("team_detail", team_id=team.id)
    
    # Check league settings for waiver status
    use_waivers = team.league.use_waivers if hasattr(team.league, 'use_waivers') else False
    
    # Get action early to check if it's a drop (which bypasses waiver redirect)
    action = request.POST.get("action")
    player_id = request.POST.get("player_id")
    
    import logging
    logger = logging.getLogger('django')
    logger.warning(f"ASSIGN_PLAYER VIEW: action={action}, player_id={player_id}, method={request.method}")
    
    if not player_id:
        messages.error(request, "No player specified.")
        return redirect("team_detail", team_id=team.id)

    try:
        player = Player.objects.get(id=int(player_id))
    except Player.DoesNotExist:
        messages.error(request, "Player not found.")
        return redirect("team_detail", team_id=team.id)
    except (ValueError, TypeError):
        messages.error(request, "Invalid player ID.")
        return redirect("team_detail", team_id=team.id)
    
    # Check if roster changes are allowed - find the next unlocked week
    league_season = team.league.created_at.year if team.league.created_at else timezone.now().year
    
    # Get the current/active week (where today falls between start and end)
    from django.db.models import Q
    today = timezone.now().date()
    
    current_week = Week.objects.filter(
        season=league_season,
        start_date__lte=today,
        end_date__gte=today
    ).first()
    
    # If no week spans today, find the NEXT week (upcoming), not the previous one
    if not current_week:
        current_week = Week.objects.filter(
            season=league_season,
            start_date__gt=today
        ).order_by('week_number').first()
    
    # Find the next unlocked week based on lock/unlock times
    next_unlocked_week = None
    all_weeks = Week.objects.filter(season=league_season).order_by('week_number')
    for w in all_weeks:
        if not w.is_locked():
            next_unlocked_week = w
            break
    
    # Rosters are locked if: we have an unlocked week AND it's a future week (not current)
    # i.e., if the next unlocked week is different from the current week
    rosters_are_locked = next_unlocked_week and (not current_week or next_unlocked_week.week_number > current_week.week_number)
    
    # If rosters are locked and waivers are enabled, redirect to waiver claim process
    # EXCEPT for drop actions, which should always be allowed
    if rosters_are_locked and use_waivers and action != "drop":
        # Redirect to waiver claim submission instead
        return redirect('submit_waiver_claim', team_id=team_id)
    
    if not next_unlocked_week:
        # No unlocked weeks available and no waivers enabled
        messages.error(request, "All weeks are currently locked. No roster changes allowed.")
        return redirect("team_detail", team_id=team.id)
    
    # Verify changes are allowed for this week
    can_change, message, locked_until = team.can_make_roster_changes(next_unlocked_week)
    if not can_change:
        messages.error(request, f"Roster changes not allowed: {message}")
        return redirect("team_detail", team_id=team.id)
    
    # Check if team is over roster limit - if so, only allow drops
    current_count, is_over_limit = team.is_over_roster_limit()
    if is_over_limit and action != "drop":
        roster_limit = team.league.roster_size if hasattr(team.league, 'roster_size') else 14
        messages.error(request, f"Your roster is OVER the limit ({current_count}/{roster_limit}). You can only DROP players until you're back under the limit.")
        return redirect("team_detail", team_id=team.id)

    player_id = request.POST.get("player_id")
    if not player_id:
        return redirect("team_detail", team_id=team.id)

    try:
        player = Player.objects.get(id=int(player_id))
    except Player.DoesNotExist:
        return redirect("team_detail", team_id=team.id)

    next_week_number = next_unlocked_week.week_number
    slot_group = request.POST.get("slot_group")
    
    if action == "swap":
        # Handle swap from players page
        drop_player_id = request.POST.get("drop_player_id")
        if not drop_player_id:
            messages.error(request, "No player selected to drop.")
            return redirect("players")
        
        try:
            drop_player = Player.objects.get(id=int(drop_player_id))
        except Player.DoesNotExist:
            messages.error(request, "Player to drop not found.")
            return redirect("players")
        
        # Verify the drop player is on the user's roster
        drop_roster = Roster.objects.filter(
            player=drop_player,
            team=team,
            league=team.league,
            week_dropped__isnull=True
        ).first()
        
        if not drop_roster:
            messages.error(request, f"{drop_player.first_name} {drop_player.last_name} is not on your roster.")
            return redirect("players")
        
        # Verify positions are compatible
        # Transition players can go in any slot, and can be replaced by anyone
        def positions_compatible(pos1, pos2):
            # Same position is always compatible
            if pos1 == pos2:
                return True
            # Transition player can replace/fill any position
            if pos1 == 'T' or pos2 == 'T':
                return True
            # O and D cannot replace each other (unless one is T)
            return False
        
        if not positions_compatible(player.position, drop_player.position):
            messages.error(request, f"Position mismatch: {player.first_name} {player.last_name} ({player.get_position_display()}) cannot replace {drop_player.first_name} {drop_player.last_name} ({drop_player.get_position_display()})")
            return redirect("players")
        
        # Check if new player is already rostered in this league
        existing_roster = Roster.objects.filter(
            player=player,
            league=team.league,
            week_dropped__isnull=True
        ).select_related('team').first()
        
        if existing_roster:
            messages.error(request, f"{player.first_name} {player.last_name} is not available - already on {existing_roster.team.name}")
            return redirect("players")
        
        # Drop the old player
        drop_roster.week_dropped = next_week_number
        drop_roster.save()
        drop_player.assigned_side = None
        drop_player.save()
        
        # Add the new player
        new_roster = Roster.objects.create(
            player=player,
            team=team,
            league=team.league,
            week_added=next_week_number
        )
        # Auto-assign to starter slot if traditional league
        auto_assign_to_starter_slot(new_roster)
        
        player.assigned_side = drop_player.position  # Use same slot
        player.save()
        
        # Post transaction to league chat
        ChatMessage.objects.create(
            league=team.league,
            sender=request.user,
            message_type=ChatMessage.MessageType.TRADE,
            message=f"{team.name} swapped {drop_player.first_name} {drop_player.last_name} for {player.first_name} {player.last_name}",
            player=player
        )
        
        return redirect("players")
    
    if action == "add":
        # Check roster size limit (total players)
        current_roster_count = Roster.objects.filter(
            team=team,
            league=team.league,
            week_dropped__isnull=True
        ).count()
        
        roster_max = team.league.roster_size if hasattr(team.league, 'roster_size') else 12
        
        if current_roster_count >= roster_max:
            messages.error(request, f"Roster is full. Maximum {roster_max} players allowed per team.")
            return redirect("team_detail", team_id=team.id)
        
        # For bench slots (traditional leagues), skip position validation - just add to roster
        if slot_group != "B":
            # Validate position matches slot type
            if slot_group == "O" and player.position not in ["O", "T"]:
                messages.error(request, f"{player.first_name} {player.last_name} cannot be added to Offence slots (position: {player.get_position_display()})")
                return redirect("team_detail", team_id=team.id)
            elif slot_group == "D" and player.position not in ["D", "T"]:
                messages.error(request, f"{player.first_name} {player.last_name} cannot be added to Defence slots (position: {player.get_position_display()})")
                return redirect("team_detail", team_id=team.id)
            elif slot_group == "G" and player.position != "G":
                messages.error(request, f"{player.first_name} {player.last_name} cannot be added to Goalie slots (position: {player.get_position_display()})")
                return redirect("team_detail", team_id=team.id)
            
            # Check position-specific capacity
            # For traditional leagues, only count players in starter slots (not bench)
            if team.league.roster_format == 'traditional':
                slot_map_starter = {
                    'O': f"starter_o[1-{team.league.roster_forwards}]",
                    'D': f"starter_d[1-{team.league.roster_defense}]",
                    'G': 'starter_g'
                }
                # Build slot list for this position
                if slot_group == 'O':
                    starter_slots = [f'starter_o{i}' for i in range(1, team.league.roster_forwards + 1)]
                elif slot_group == 'D':
                    starter_slots = [f'starter_d{i}' for i in range(1, team.league.roster_defense + 1)]
                elif slot_group == 'G':
                    starter_slots = [f'starter_g{i}' for i in range(1, team.league.roster_goalies + 1)]
                else:
                    starter_slots = []
                
                starter_count = Roster.objects.filter(
                    team=team,
                    league=team.league,
                    week_dropped__isnull=True,
                    slot_assignment__in=starter_slots
                ).count()
                max_pos_slots = len(starter_slots)
                can_add = starter_count < max_pos_slots
                current_pos_count = starter_count
            else:
                # For best ball, use general capacity check
                can_add, current_pos_count, max_pos_slots = check_roster_capacity(team, slot_group)
            
            if not can_add:
                position_name = {'O': 'Offence', 'D': 'Defence', 'G': 'Goalie'}.get(slot_group, 'Unknown')
                messages.error(request, f"Your {position_name} roster is full ({current_pos_count}/{max_pos_slots} spots).")
                return redirect("team_detail", team_id=team.id)
        
        # Check if player is already rostered in this league (active roster only)
        existing_roster = Roster.objects.filter(
            player=player,
            league=team.league,
            week_dropped__isnull=True
        ).select_related('team').first()
        
        if existing_roster:
            messages.error(request, f"{player.first_name} {player.last_name} is not available - already on {existing_roster.team.name}")
            return redirect("team_detail", team_id=team.id)
        
        # Create a roster entry for this player on this team in this league
        try:
            roster = Roster.objects.create(
                player=player,
                team=team,
                league=team.league,
                week_added=next_week_number
            )
            # Auto-assign to starter slot if traditional league
            auto_assign_to_starter_slot(roster)
            
            messages.success(request, f"Added {player.first_name} {player.last_name} to your roster (week {next_week_number})")
        except Exception as e:
            messages.error(request, f"Error adding player: {str(e)}")
            return redirect("team_detail", team_id=team.id)
        # Update assigned_side for slot placement
        if slot_group in {"O", "D", "G"}:
            player.assigned_side = slot_group
            player.save()
        
        # Post transaction to league chat
        ChatMessage.objects.create(
            league=team.league,
            sender=request.user,
            message_type=ChatMessage.MessageType.ADD,
            message=f"{team.name} added {player.first_name} {player.last_name} ({player.get_position_display()})",
            player=player
        )
        
        messages.success(request, f"Added {player.first_name} {player.last_name} to your roster")
    
    if action == "drop":
        # Soft delete: set week_dropped instead of deleting the roster entry
        roster_entry = Roster.objects.filter(
            player=player,
            team=team,
            league=team.league,
            week_dropped__isnull=True
        ).first()
        
        if roster_entry:
            roster_entry.week_dropped = next_week_number
            roster_entry.save()
            # Clear assigned_side when dropping
            player.assigned_side = None
            player.save()
            
            # Post transaction to league chat
            ChatMessage.objects.create(
                league=team.league,
                sender=request.user,
                message_type=ChatMessage.MessageType.DROP,
                message=f"{team.name} dropped {player.first_name} {player.last_name} ({player.get_position_display()})",
                player=player
            )
            
            messages.success(request, f"Dropped {player.first_name} {player.last_name} from your roster")
    
    if action == "swap_slots":
        # Swap a player to another slot (for traditional leagues)
        target_slot = request.POST.get("target_slot")  # Can be a player ID or a slot designation like "O1", "D2", etc.
        
        import logging
        logger = logging.getLogger('django')
        logger.warning(f"SWAP_SLOTS START: playerId={player_id}, targetSlot={target_slot}, league_format={team.league.roster_format}")
        
        # Get the moving player's roster entry
        player_roster = Roster.objects.filter(
            player=player,
            team=team,
            league=team.league,
            week_dropped__isnull=True
        ).first()
        
        if not player_roster:
            logger.warning(f"SWAP_SLOTS: Player roster entry not found")
            messages.error(request, "Player not found on roster.")
            return redirect("team_detail", team_id=team.id)
        
        # Check if target_slot is a player ID (move to occupied slot) or a slot designation (move to empty slot)
        target_roster = None
        target_player = None
        
        try:
            # Try to find a player with this ID
            target_player = Player.objects.get(id=int(target_slot))
            target_roster = Roster.objects.filter(
                player=target_player,
                team=team,
                league=team.league,
                week_dropped__isnull=True
            ).first()
            
            if not target_roster:
                logger.warning(f"SWAP_SLOTS: Target player not found on roster")
                messages.error(request, "Target player not found on roster.")
                return redirect("team_detail", team_id=team.id)
            
            # Swap their slot assignments (for all league types)
            logger.warning(f"SWAP_SLOTS: Before swap - player slot: {player_roster.slot_assignment}, target slot: {target_roster.slot_assignment}")
            player_roster.slot_assignment, target_roster.slot_assignment = target_roster.slot_assignment, player_roster.slot_assignment
            player_roster.save()
            target_roster.save()
            logger.warning(f"SWAP_SLOTS: After swap - player slot: {player_roster.slot_assignment}, target slot: {target_roster.slot_assignment}")
            
            # For Transition players, swap assigned_side if they're moving to different position groups
            if player.position == 'T' and target_player.position == 'T':
                logger.warning(f"SWAP_SLOTS: T-T swap - before assigned_side swap: player={player.assigned_side}, target={target_player.assigned_side}")
                player.assigned_side, target_player.assigned_side = target_player.assigned_side, player.assigned_side
                player.save()
                target_player.save()
                logger.warning(f"SWAP_SLOTS: After assigned_side swap: player={player.assigned_side}, target={target_player.assigned_side}")
            
            # If AJAX request, return JSON so page can update without full reload
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                logger.warning(f"SWAP_SLOTS: Returning JSON response - success")
                return JsonResponse({
                    'success': True,
                    'message': f"Swapped {player.last_name} and {target_player.last_name}",
                    'player_id': player.id,
                    'player_slot': player_roster.slot_assignment,
                    'target_player_id': target_player.id,
                    'target_player_slot': target_roster.slot_assignment
                })
            
        except (Player.DoesNotExist, ValueError, TypeError):
            # Target is a slot designation (empty slot), not a player ID
            # Update the moving player's slot assignment (for all league types)
            old_slot = player_roster.slot_assignment
            logger.warning(f"SWAP_SLOTS (as move): Moving player from {old_slot} to {target_slot}")
            player_roster.slot_assignment = target_slot
            player_roster.save()
            
            # Handle assigned_side updates for Transition players
            if player.position == 'T':
                # In traditional league, update assigned_side based on slot designation
                if team.league.roster_format == 'traditional':
                    if 'starter_o' in target_slot:
                        player.assigned_side = 'O'
                    elif 'starter_d' in target_slot:
                        player.assigned_side = 'D'
                    elif 'starter_g' in target_slot:
                        player.assigned_side = 'G'
                    player.save()
                    logger.warning(f"SWAP_SLOTS (as move): Updated transition player assigned_side to {player.assigned_side}")
                # In best ball league, update assigned_side based on position name (O, D, G)
                elif team.league.roster_format == 'bestball' and target_slot in ['O', 'D', 'G']:
                    player.assigned_side = target_slot
                    player.save()
                    logger.warning(f"SWAP_SLOTS (as move): Updated transition player assigned_side to {player.assigned_side} (best ball)")
            
            logger.warning(f"SWAP_SLOTS (as move): After save - player now in {player_roster.slot_assignment}")
            
            # If AJAX request, return JSON
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                logger.warning(f"SWAP_SLOTS (as move): Returning JSON response - success")
                return JsonResponse({
                    'success': True,
                    'message': f"Moved {player.last_name}",
                    'player_id': player.id,
                    'player_slot': player_roster.slot_assignment
                })
            
            messages.success(request, f"Moved {player.last_name}")
    
    if action == "move_to_empty_slot":
        # Move a player to an empty slot (for traditional leagues)
        target_slot = request.POST.get("target_slot")  # Slot designation like "starter_o1", "starter_d2", etc., or position like "O", "D", "G"
        import logging
        logger = logging.getLogger('django')
        logger.warning(f"MOVE_TO_EMPTY_SLOT START: player={player.last_name}, target_slot={target_slot}, league_format={team.league.roster_format}")
        
        # Get the moving player's roster entry
        player_roster = Roster.objects.filter(
            player=player,
            team=team,
            league=team.league,
            week_dropped__isnull=True
        ).first()
        
        if not player_roster:
            logger.warning(f"MOVE_TO_EMPTY_SLOT: Player roster entry not found for {player.last_name}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Player not found on roster.'}, status=400)
            messages.error(request, "Player not found on roster.")
            return redirect("team_detail", team_id=team.id)
        
        # Check if target position is full (exclude current player from capacity count)
        # Determine target position group from target_slot
        target_position = None
        if team.league.roster_format == 'traditional':
            if 'starter_o' in target_slot:
                target_position = 'O'
            elif 'starter_d' in target_slot:
                target_position = 'D'
            elif 'starter_g' in target_slot:
                target_position = 'G'
        else:  # best ball
            if target_slot in ['O', 'D', 'G']:
                target_position = target_slot
        
        # Check capacity for target position (excluding current player)
        if target_position:
            # For traditional leagues, only count players in starter slots (not bench)
            if team.league.roster_format == 'traditional':
                if 'starter_o' in target_slot:
                    starter_slots = [f'starter_o{i}' for i in range(1, team.league.roster_forwards + 1)]
                elif 'starter_d' in target_slot:
                    starter_slots = [f'starter_d{i}' for i in range(1, team.league.roster_defense + 1)]
                elif 'starter_g' in target_slot:
                    starter_slots = [f'starter_g{i}' for i in range(1, team.league.roster_goalies + 1)]
                else:
                    starter_slots = []
                
                # Count players in starter slots for this position
                starter_count = Roster.objects.filter(
                    team=team,
                    league=team.league,
                    week_dropped__isnull=True,
                    slot_assignment__in=starter_slots
                ).exclude(player=player).count()
                max_allowed = len(starter_slots)
                can_add = starter_count < max_allowed
                current_pos_count = starter_count
            else:
                # For best ball, use general capacity check
                can_add, current_pos_count, max_allowed = check_roster_capacity(team, target_position, exclude_player=player)
            
            if not can_add:
                position_name = {'O': 'Offence', 'D': 'Defence', 'G': 'Goalie'}.get(target_position, 'Unknown')
                error_msg = f"Cannot move {player.first_name} {player.last_name} - {position_name} slots are full ({current_pos_count}/{max_allowed} spots)."
                logger.warning(f"MOVE_TO_EMPTY_SLOT: {position_name} slots are full for {player.last_name}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg}, status=400)
                messages.error(request, error_msg)
                return redirect("team_detail", team_id=team.id)
        
        # Handle traditional league moves (update slot_assignment)
        if team.league.roster_format == 'traditional':
            old_slot = player_roster.slot_assignment
            logger.warning(f"MOVE_TO_EMPTY_SLOT: Before save - {player.last_name} from {old_slot} to {target_slot}")
            player_roster.slot_assignment = target_slot
            player_roster.save()
            
            # If player is a Transition player, update assigned_side based on target slot
            if player.position == 'T':
                # Check if transition player is being moved to goalie slot
                if 'starter_g' in target_slot and not team.league.allow_transition_in_goalies:
                    error_msg = f"Cannot move {player.first_name} {player.last_name} to Goalie slot - Transition (T) players are not allowed in Goalie slots in this league."
                    logger.warning(f"MOVE_TO_EMPTY_SLOT: Transition player cannot be moved to G slot in this league")
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'error': error_msg}, status=400)
                    messages.error(request, error_msg)
                    return redirect("team_detail", team_id=team.id)
                
                if 'starter_o' in target_slot:
                    player.assigned_side = 'O'
                elif 'starter_d' in target_slot:
                    player.assigned_side = 'D'
                elif 'starter_g' in target_slot:
                    player.assigned_side = 'G'
                player.save()
                logger.warning(f"MOVE_TO_EMPTY_SLOT: Updated transition player assigned_side to {player.assigned_side}")
        # Handle best ball league moves (update assigned_side for position moves)
        else:
            if player.position == 'T':
                # Check if transition player is being moved to goalie slot
                if target_slot == 'G' and not team.league.allow_transition_in_goalies:
                    error_msg = f"Cannot move {player.first_name} {player.last_name} to Goalie slot - Transition (T) players are not allowed in Goalie slots in this league."
                    logger.warning(f"MOVE_TO_EMPTY_SLOT: Transition player cannot be moved to G slot in this league")
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'error': error_msg}, status=400)
                    messages.error(request, error_msg)
                    return redirect("team_detail", team_id=team.id)
                
                if target_slot in ['O', 'D', 'G']:
                    logger.warning(f"MOVE_TO_EMPTY_SLOT: Best ball - updating assigned_side to {target_slot}")
                    player.assigned_side = target_slot
                    player.save()
            else:
                logger.warning(f"MOVE_TO_EMPTY_SLOT: Best ball league - no changes needed")
        
        logger.warning(f"MOVE_TO_EMPTY_SLOT: After save - {player.last_name} now in {player_roster.slot_assignment}")
        
        # If AJAX request, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            logger.warning(f"MOVE_TO_EMPTY_SLOT: Returning JSON response - success")
            return JsonResponse({
                'success': True,
                'message': f"Moved {player.last_name}",
                'player_id': player.id,
                'player_slot': player_roster.slot_assignment
            })
        
        messages.success(request, f"Moved {player.last_name}")


    # Invalidate team caches after any roster modification
    invalidate_team_cache(team.id)
    invalidate_league_cache(team.league.id)

    return redirect("team_detail", team_id=team.id)


@login_required
def move_transition_player(request, team_id):
    """Move a Transition player between Offense and Defense slots"""
    if request.method != 'POST':
        return redirect("team_detail", team_id=team_id)
    
    team = get_object_or_404(Team, id=team_id)
    
    # Check if the user owns this team
    team_owner = FantasyTeamOwner.objects.filter(
        user=request.user,
        team=team
    ).first()
    
    if not team_owner:
        messages.error(request, "You don't have permission to modify this team.")
        return redirect("team_detail", team_id=team.id)
    
    # Check if roster changes are allowed
    can_change, message, locked_until = team.can_make_roster_changes()
    if not can_change:
        messages.error(request, f"Roster changes not allowed: {message}")
        return redirect("team_detail", team_id=team.id)
    
    player_id = request.POST.get("player_id")
    target_side = request.POST.get("target_side")
    
    if not player_id or target_side not in ['O', 'D', 'G']:
        messages.error(request, "Invalid request.")
        return redirect("team_detail", team_id=team.id)
    
    try:
        player = Player.objects.get(id=int(player_id))
    except Player.DoesNotExist:
        messages.error(request, "Player not found.")
        return redirect("team_detail", team_id=team.id)
    
    # Verify the player is a Transition player
    if player.position != 'T':
        messages.error(request, "Only Transition players can be moved between positions.")
        return redirect("team_detail", team_id=team.id)
    
    # Verify the player is on the team's roster
    roster_entry = Roster.objects.filter(
        player=player,
        team=team,
        league=team.league,
        week_dropped__isnull=True
    ).first()
    
    if not roster_entry:
        messages.error(request, "Player is not on your roster.")
        return redirect("team_detail", team_id=team.id)
    
    # Check if target position is full using the helper function
    # Don't exclude the player - it's not currently occupying a slot in the target position
    can_add, current_pos_count, max_pos_slots = check_roster_capacity(team, target_side)
    
    if not can_add:
        side_name = {'O': 'Offense', 'D': 'Defense', 'G': 'Goalie'}.get(target_side, 'Unknown')
        messages.error(request, f"Your {side_name} roster is full ({current_pos_count}/{max_pos_slots} spots).")
        return redirect("team_detail", team_id=team.id)
    
    # Update the player's assigned_side
    player.assigned_side = target_side
    player.save()
    
    side_names = {
        'O': 'Offense',
        'D': 'Defense',
        'G': 'Goalie'
    }
    side_name = side_names.get(target_side, 'Unknown')
    messages.success(request, f"Moved {player.first_name} {player.last_name} to {side_name}")
    
    return redirect("team_detail", team_id=team.id)


@login_required
def trade_center(request, team_id):
    """Show trade center with other teams and their players"""
    team = get_object_or_404(Team, id=team_id)
    league = team.league
    
    # Check if the user owns this team
    team_owner = FantasyTeamOwner.objects.filter(
        user=request.user,
        team=team
    ).first()
    
    if not team_owner:
        messages.error(request, "You don't have permission to access trades for this team.")
        return redirect("team_detail", team_id=team.id)
    
    # Get all other teams in the league with their players
    other_teams = Team.objects.filter(
        league=league
    ).exclude(
        id=team.id
    ).prefetch_related(
        models.Prefetch(
            'roster_entries',
            queryset=Roster.objects.filter(
                week_dropped__isnull=True
            ).select_related('player')
        )
    )
    
    # Get user's team roster
    user_roster = Roster.objects.filter(
        team=team,
        week_dropped__isnull=True
    ).select_related('player')
    
    # OPTIMIZATION: Batch load all schedules at once instead of per-player queries
    # Get all upcoming weeks once
    from django.utils import timezone
    today = timezone.now().date()
    upcoming_weeks = list(
        Week.objects.filter(start_date__gte=today).order_by('week_number')[:5]
    )
    
    # Get all games for these weeks
    if upcoming_weeks:
        all_games = list(
            Game.objects.filter(week__in=upcoming_weeks).select_related('week')
        )
        
        # Build schedule map by NLL team name
        schedule_by_team = {}
        for week in upcoming_weeks:
            schedule_by_team[week.week_number] = {'week': week, 'games_by_team': {}}
        
        for game in all_games:
            week_num = game.week.week_number
            # Add game for home team
            if game.home_team not in schedule_by_team[week_num]['games_by_team']:
                schedule_by_team[week_num]['games_by_team'][game.home_team] = []
            schedule_by_team[week_num]['games_by_team'][game.home_team].append(game)
            
            # Add game for away team
            if game.away_team not in schedule_by_team[week_num]['games_by_team']:
                schedule_by_team[week_num]['games_by_team'][game.away_team] = []
            schedule_by_team[week_num]['games_by_team'][game.away_team].append(game)
        
        # Assign schedules to players from the map
        def assign_schedule_from_map(roster_entry):
            """Assign upcoming schedule to a player using the precomputed map"""
            schedule = []
            if roster_entry.player.nll_team:
                for week in upcoming_weeks:
                    games_for_team = schedule_by_team[week.week_number]['games_by_team'].get(roster_entry.player.nll_team, [])
                    opponent_teams = set()
                    for game in games_for_team:
                        if game.home_team == roster_entry.player.nll_team:
                            opponent_teams.add(game.away_team)
                        else:
                            opponent_teams.add(game.home_team)
                    
                    schedule.append({
                        'week_number': week.week_number,
                        'game_count': len(games_for_team),
                        'opponents': list(opponent_teams) if opponent_teams else []
                    })
            else:
                # Player has no NLL team, add empty schedule for upcoming weeks
                for week in upcoming_weeks:
                    schedule.append({
                        'week_number': week.week_number,
                        'game_count': 0,
                        'opponents': []
                    })
            return schedule
        
        # Apply schedules to all roster entries
        for roster_entry in user_roster:
            roster_entry.player.upcoming_schedule = assign_schedule_from_map(roster_entry)
        
        for other_team in other_teams:
            for roster_entry in other_team.roster_entries.all():
                roster_entry.player.upcoming_schedule = assign_schedule_from_map(roster_entry)
    else:
        # No upcoming weeks
        for roster_entry in user_roster:
            roster_entry.player.upcoming_schedule = []
        for other_team in other_teams:
            for roster_entry in other_team.roster_entries.all():
                roster_entry.player.upcoming_schedule = []
    
    # Get future picks for dynasty leagues with feature enabled
    user_future_picks = []
    other_teams_future_picks = {}
    use_future_picks = False
    
    if league.league_type == 'dynasty':
        from ..models import FutureRookiePick
        
        use_future_picks = getattr(league, 'use_future_rookie_picks', True)
        
        # Get future picks for user's team
        if use_future_picks:
            user_picks_queryset = FutureRookiePick.objects.filter(
                team=team
            ).select_related('original_owner', 'team').order_by('year', 'round_number', 'pick_number')
            
            user_future_picks_by_year = {}
            for pick in user_picks_queryset:
                if pick.year not in user_future_picks_by_year:
                    user_future_picks_by_year[pick.year] = []
                user_future_picks_by_year[pick.year].append(pick)
            user_future_picks = user_future_picks_by_year
            
            # Get future picks for other teams
            for other_team in other_teams:
                other_picks_queryset = FutureRookiePick.objects.filter(
                    team=other_team
                ).select_related('original_owner', 'team').order_by('year', 'round_number', 'pick_number')
                
                other_picks_by_year = {}
                for pick in other_picks_queryset:
                    if pick.year not in other_picks_by_year:
                        other_picks_by_year[pick.year] = []
                    other_picks_by_year[pick.year].append(pick)
                other_teams_future_picks[other_team.id] = other_picks_by_year
    
    context = {
        'team': team,
        'league': league,
        'other_teams': other_teams,
        'user_roster': user_roster,
        'user_future_picks': user_future_picks,
        'other_teams_future_picks': other_teams_future_picks,
        'use_future_picks': use_future_picks,
    }
    
    return render(request, 'web/trade_center.html', context)


@require_POST
def propose_trade(request, team_id):
    """Handle trade proposal submission"""
    team = get_object_or_404(Team, id=team_id)
    league = team.league
    
    # Check if the user owns this team
    team_owner = FantasyTeamOwner.objects.filter(
        user=request.user,
        team=team
    ).first()
    
    if not team_owner:
        messages.error(request, "You don't have permission to propose trades for this team.")
        return redirect("team_detail", team_id=team.id)
    
    # Get the target team
    target_team_id = request.POST.get('target_team_id')
    target_team = get_object_or_404(Team, id=target_team_id, league=league)
    
    # Get player and pick IDs from the request
    import json
    your_player_ids = json.loads(request.POST.get('your_players', '[]'))
    their_player_ids = json.loads(request.POST.get('their_players', '[]'))
    your_pick_ids = json.loads(request.POST.get('your_picks', '[]'))
    their_pick_ids = json.loads(request.POST.get('their_picks', '[]'))
    
    # Validate that players exist and are on the correct teams
    your_players = Player.objects.filter(
        id__in=your_player_ids,
        roster_entries__team=team,
        roster_entries__league=league,
        roster_entries__week_dropped__isnull=True
    ).distinct()
    
    their_players = Player.objects.filter(
        id__in=their_player_ids,
        roster_entries__team=target_team,
        roster_entries__league=league,
        roster_entries__week_dropped__isnull=True
    ).distinct()
    
    # Validate that picks exist and are owned by the correct teams
    from ..models import FutureRookiePick
    your_picks = FutureRookiePick.objects.filter(
        id__in=your_pick_ids,
        team=team,
        league=league
    )
    
    their_picks = FutureRookiePick.objects.filter(
        id__in=their_pick_ids,
        team=target_team,
        league=league
    )
    
    if your_players.count() != len(your_player_ids) or their_players.count() != len(their_player_ids):
        messages.error(request, "Invalid player selection. Please try again.")
        return redirect("trade_center", team_id=team.id)
    
    if your_picks.count() != len(your_pick_ids) or their_picks.count() != len(their_pick_ids):
        messages.error(request, "Invalid pick selection. Please try again.")
        return redirect("trade_center", team_id=team.id)
    
    if (your_players.count() + your_picks.count()) == 0 or (their_players.count() + their_picks.count()) == 0:
        messages.error(request, "You must select at least one item (player or pick) from each team.")
        return redirect("trade_center", team_id=team.id)
    
    # Create the trade
    trade = Trade.objects.create(
        league=league,
        proposing_team=team,
        receiving_team=target_team,
        status=Trade.Status.PENDING
    )
    
    # Add players to the trade
    for player in your_players:
        TradePlayer.objects.create(
            trade=trade,
            player=player,
            from_team=team
        )
    
    for player in their_players:
        TradePlayer.objects.create(
            trade=trade,
            player=player,
            from_team=target_team
        )
    
    # Add picks to the trade
    from ..models import TradePick
    for pick in your_picks:
        TradePick.objects.create(
            trade=trade,
            future_rookie_pick=pick,
            from_team=team
        )
    
    for pick in their_picks:
        TradePick.objects.create(
            trade=trade,
            future_rookie_pick=pick,
            from_team=target_team
        )
    
    # Post message to team chat
    your_items = []
    for p in your_players:
        your_items.append(f"{p.first_name} {p.last_name}")
    for p in your_picks:
        your_items.append(f"{p.year} R{p.round_number}P{p.pick_number}")
    
    their_items = []
    for p in their_players:
        their_items.append(f"{p.first_name} {p.last_name}")
    for p in their_picks:
        their_items.append(f"{p.year} R{p.round_number}P{p.pick_number}")
    
    your_items_str = ", ".join(your_items)
    their_items_str = ", ".join(their_items)
    message = f"Trade proposed: {team.name} receives ({their_items_str}) and {target_team.name} receives ({your_items_str})"
    post_team_chat_message(team, target_team, message, 
                          message_type='TRADE_PROPOSED', 
                          trade=trade, 
                          sender=request.user)
    
    return redirect("team_detail", team_id=team.id)


def execute_trade(trade):
    """Execute a trade by swapping players between teams"""
    from django.utils import timezone
    
    # Get the next unlocked week (only editable week)
    league_season = trade.league.created_at.year
    current_date = timezone.now().date()
    
    next_week = Week.objects.filter(
        season=league_season,
        start_date__gt=current_date
    ).order_by('week_number').first()
    
    # If no future week, try to use current week. If no current week either, use week 1
    if not next_week:
        current_week = Week.objects.filter(
            season=league_season,
            start_date__lte=current_date
        ).order_by('-week_number').first()
        
        if current_week:
            week_number = current_week.week_number
        else:
            # No weeks exist yet, use week 1 as default
            week_number = 1
    else:
        week_number = next_week.week_number
    
    # Swap players between teams
    for trade_player in trade.players.all():
        player = trade_player.player
        from_team = trade_player.from_team
        to_team = trade.receiving_team if from_team == trade.proposing_team else trade.proposing_team
        
        # Remove player from original team
        old_roster = Roster.objects.filter(
            team=from_team,
            player=player,
            league=trade.league,
            week_dropped__isnull=True
        ).first()
        
        if old_roster:
            old_roster.week_dropped = week_number
            old_roster.save()
        
        # Add player to new team
        new_roster = Roster.objects.create(
            team=to_team,
            player=player,
            league=trade.league,
            week_added=week_number
        )
        # Auto-assign to starter slot if traditional league
        auto_assign_to_starter_slot(new_roster)
    
    # Swap picks between teams
    for trade_pick in trade.picks.all():
        pick = trade_pick.future_rookie_pick
        from_team = trade_pick.from_team
        to_team = trade.receiving_team if from_team == trade.proposing_team else trade.proposing_team
        
        # Update pick ownership
        pick.team = to_team
        pick.save()
    
    # Mark trade as executed
    trade.executed_at = timezone.now()
    trade.save()
    
    # Post notification to league chat
    proposing_players = trade.players.filter(from_team=trade.proposing_team)
    receiving_players = trade.players.filter(from_team=trade.receiving_team)
    proposing_picks = trade.picks.filter(from_team=trade.proposing_team)
    receiving_picks = trade.picks.filter(from_team=trade.receiving_team)
    
    proposing_items = []
    for p in proposing_players:
        proposing_items.append(f"{p.player.first_name} {p.player.last_name}")
    for p in proposing_picks:
        proposing_items.append(f"{p.future_rookie_pick.year} R{p.future_rookie_pick.round_number}P{p.future_rookie_pick.pick_number}")
    
    receiving_items = []
    for p in receiving_players:
        receiving_items.append(f"{p.player.first_name} {p.player.last_name}")
    for p in receiving_picks:
        receiving_items.append(f"{p.future_rookie_pick.year} R{p.future_rookie_pick.round_number}P{p.future_rookie_pick.pick_number}")
    
    proposing_names = ", ".join(proposing_items)
    receiving_names = ", ".join(receiving_items)
    
    message_text = f"ðŸ¤ Trade completed! {trade.proposing_team.name} receives ({receiving_names}) and {trade.receiving_team.name} receives ({proposing_names})"
    post_league_message(trade.league, message_text)
    
    # Invalidate caches for both teams and league standings
    invalidate_team_cache(trade.proposing_team.id)
    invalidate_team_cache(trade.receiving_team.id)
    invalidate_league_cache(trade.league.id)
    
    return True, "Trade executed successfully"


@require_POST
def accept_trade(request, trade_id):
    """Accept a trade offer"""
    from django.utils import timezone
    from ..models import Week
    
    trade = get_object_or_404(Trade, id=trade_id)
    
    # Check if the user owns the receiving team
    team_owner = FantasyTeamOwner.objects.filter(
        user=request.user,
        team=trade.receiving_team
    ).first()
    
    if not team_owner:
        messages.error(request, "You don't have permission to accept this trade.")
        return redirect("team_detail", team_id=request.user.fantasyteamowner_set.first().team.id)
    
    if trade.status != Trade.Status.PENDING:
        messages.error(request, "This trade is no longer pending.")
        return redirect("team_detail", team_id=trade.receiving_team.id)
    
    # Check if rosters are currently locked (games in progress for any week)
    # A week is considered "active" if games have started but next week hasn't unlocked yet
    league_season = trade.league.created_at.year if trade.league.created_at else timezone.now().year
    
    # Check if ANY week is currently active (roster_lock_time <= now < roster_unlock_time)
    any_week_active = Week.objects.filter(
        season=league_season,
        roster_lock_time__lte=timezone.now(),
        roster_unlock_time__gt=timezone.now()
    ).exists()
    
    is_locked = any_week_active
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Trade {trade.id}: any_week_active={any_week_active}, is_locked={is_locked}")
    
    # Update trade status
    if is_locked:
        # Rosters are locked - trade will execute when rosters unlock (next Tuesday 9 AM)
        trade.status = Trade.Status.ACCEPTED
        trade.save()
        
        # Post message to team chat
        message = f"Trade accepted by {trade.receiving_team.name}. Will execute when rosters unlock."
        post_team_chat_message(trade.proposing_team, trade.receiving_team, message,
                              message_type='TRADE_ACCEPTED',
                              trade=trade,
                              sender=request.user)
        
        messages.success(request, f"Trade accepted! It will be processed when rosters unlock.")
    else:
        # Rosters are unlocked - execute trade immediately
        trade.status = Trade.Status.ACCEPTED
        trade.save()
        
        # Post message to team chat
        message = f"Trade accepted and executed by {trade.receiving_team.name}."
        post_team_chat_message(trade.proposing_team, trade.receiving_team, message,
                              message_type='TRADE_EXECUTED',
                              trade=trade,
                              sender=request.user)
        
        success, msg = execute_trade(trade)
        if not success:
            messages.error(request, f"Trade accepted but execution failed: {msg}")
    
    # Invalidate relevant caches after trade status update
    invalidate_team_cache(trade.proposing_team.id)
    invalidate_team_cache(trade.receiving_team.id)
    invalidate_league_cache(trade.league.id)
    
    return redirect("team_detail", team_id=trade.receiving_team.id)


@require_POST
def reject_trade(request, trade_id):
    """Reject a trade offer (can be PENDING or ACCEPTED but not executed)"""
    trade = get_object_or_404(Trade, id=trade_id)
    
    # Check if the user owns the receiving team
    team_owner = FantasyTeamOwner.objects.filter(
        user=request.user,
        team=trade.receiving_team
    ).first()
    
    if not team_owner:
        messages.error(request, "You don't have permission to reject this trade.")
        return redirect("team_detail", team_id=request.user.fantasyteamowner_set.first().team.id)
    
    if trade.executed_at:
        messages.error(request, "This trade has already been executed.")
        return redirect("team_detail", team_id=trade.receiving_team.id)
    
    if trade.status in [Trade.Status.REJECTED, Trade.Status.CANCELLED]:
        messages.error(request, f"This trade has already been {trade.status.lower()}.")
        return redirect("team_detail", team_id=trade.receiving_team.id)
    
    trade.status = Trade.Status.REJECTED
    trade.save()
    
    # Post message to team chat
    message = f"Trade rejected by {trade.receiving_team.name}."
    post_team_chat_message(trade.proposing_team, trade.receiving_team, message,
                          message_type='TRADE_REJECTED',
                          trade=trade,
                          sender=request.user)
    
    messages.success(request, f"Trade offer from {trade.proposing_team.name} rejected.")
    return redirect("team_detail", team_id=trade.receiving_team.id)


@require_POST
def cancel_trade(request, trade_id):
    """Cancel a trade offer (proposing team can cancel if not executed or accepted)"""
    trade = get_object_or_404(Trade, id=trade_id)
    
    # Check if the user owns the proposing team
    team_owner = FantasyTeamOwner.objects.filter(
        user=request.user,
        team=trade.proposing_team
    ).first()
    
    if not team_owner:
        messages.error(request, "You don't have permission to cancel this trade.")
        return redirect("team_detail", team_id=request.user.fantasyteamowner_set.first().team.id)
    
    if trade.executed_at:
        messages.error(request, "This trade has already been executed.")
        return redirect("team_detail", team_id=trade.proposing_team.id)
    
    if trade.status == Trade.Status.ACCEPTED:
        messages.error(request, "Cannot cancel an accepted trade. The trade is locked until executed.")
        return redirect("team_detail", team_id=trade.proposing_team.id)
    
    if trade.status in [Trade.Status.REJECTED, Trade.Status.CANCELLED]:
        messages.error(request, f"This trade has already been {trade.status.lower()}.")
        return redirect("team_detail", team_id=trade.proposing_team.id)
    
    trade.status = Trade.Status.CANCELLED
    trade.save()
    
    # Post message to team chat
    message = f"Trade cancelled by {trade.proposing_team.name}."
    post_team_chat_message(trade.proposing_team, trade.receiving_team, message,
                          message_type='TRADE_CANCELLED',
                          trade=trade,
                          sender=request.user)
    
    messages.success(request, f"Trade offer to {trade.receiving_team.name} cancelled.")
    return redirect("team_detail", team_id=trade.proposing_team.id)


@cache_view_with_request(get_players_cache_key, 'players')
def players(request):
    """Render players list with their latest weekly stats (if any)."""
    # Get position filter
    selected_position = request.GET.get("position", "")
    
    # Get search query
    search_query = request.GET.get("search", "").strip()
    
    # Get user's team and league if authenticated
    user_team = None
    selected_league = None
    selected_league_id = None
    if request.user.is_authenticated:
        selected_league_id = request.session.get('selected_league_id')
        if selected_league_id:
            selected_league = League.objects.filter(id=selected_league_id).first()
            team_owner = FantasyTeamOwner.objects.filter(
                user=request.user,
                team__league_id=selected_league_id
            ).select_related('team').first()
            if team_owner:
                user_team = team_owner.team
    
    qs = Player.objects.filter(active=True)
    
    # Apply search filter
    if search_query:
        from django.db.models import Q
        qs = qs.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(middle_name__icontains=search_query)
        )
    
    # Apply position filter if selected
    if selected_position == "R":
        # Filter for rookies only
        qs = qs.filter(is_rookie=True)
    elif selected_position:
        qs = qs.filter(position=selected_position)
    else:
        # Exclude goalies from "All Positions" view
        qs = qs.exclude(position="G")
    
    qs = qs.order_by("last_name", "first_name").prefetch_related("game_stats__game__week")

    # Pre-fetch all roster entries to avoid N+1 queries
    # This will be used in the loop below to check player roster status
    rosters_by_player = {}
    if request.user.is_authenticated and selected_league_id:
        from django.db.models import Q
        selected_league = League.objects.filter(id=selected_league_id).first()
        all_roster_entries = Roster.objects.filter(
            team__league_id=selected_league_id,
            week_dropped__isnull=True
        ).select_related('team')
        for roster_entry in all_roster_entries:
            rosters_by_player[roster_entry.player_id] = roster_entry

    # Get season and week selection
    selected_season = request.GET.get("season")
    selected_week_num = request.GET.get("week")
    selected_stat_type = request.GET.get("stat_type", "regular")  # regular, playoff, or all
    
    # Get available seasons
    seasons = Week.objects.values_list('season', flat=True).distinct().order_by('-season')
    
    # Default to most recent season if none selected
    if not selected_season and seasons:
        selected_season = str(seasons[0])
    
    # Get weeks for selected season
    week_options = []
    if selected_season:
        week_options = list(Week.objects.filter(season=int(selected_season)).order_by('week_number'))

    sort_field = request.GET.get("sort", "fpts")
    sort_dir = request.GET.get("dir", "asc")

    players_with_stats = []
    for p in qs:
        game_stats = list(p.game_stats.all())
        
        # Calculate stats based on selection
        if selected_week_num:
            # Show specific week stats - aggregate all games that week
            stat_for_view = None
            games_played = 0
            if selected_season:
                # Get all games this player played in that week
                week_stats = [s for s in game_stats if s.game.week.season == int(selected_season) and s.game.week.week_number == int(selected_week_num)]
                games_played = len(week_stats)
                # Aggregate all stats from all games that week
                if week_stats:
                    stat_for_view = type('obj', (object,), {
                        'goals': sum(s.goals for s in week_stats),
                        'assists': sum(s.assists for s in week_stats),
                        'loose_balls': sum(s.loose_balls for s in week_stats),
                        'caused_turnovers': sum(s.caused_turnovers for s in week_stats),
                        'blocked_shots': sum(s.blocked_shots for s in week_stats),
                        'turnovers': sum(s.turnovers for s in week_stats),
                        'wins': sum(s.wins for s in week_stats),
                        'saves': sum(s.saves for s in week_stats),
                        'goals_against': sum(s.goals_against for s in week_stats),
                    })()
        else:
            # Show season totals - filter based on stat_type
            if selected_season:
                if selected_stat_type == "playoff":
                    # Only playoff games
                    season_stats = [s for s in game_stats if s.game.week.season == int(selected_season) and s.game.week.is_playoff]
                elif selected_stat_type == "all":
                    # All games (regular + playoff)
                    season_stats = [s for s in game_stats if s.game.week.season == int(selected_season)]
                else:  # regular (default)
                    # Only regular season games
                    season_stats = [s for s in game_stats if s.game.week.season == int(selected_season) and not s.game.week.is_playoff]
            else:
                season_stats = []
            
            # Aggregate season stats
            if season_stats:
                stat_for_view = type('obj', (object,), {
                    'goals': sum(s.goals for s in season_stats),
                    'assists': sum(s.assists for s in season_stats),
                    'loose_balls': sum(s.loose_balls for s in season_stats),
                    'caused_turnovers': sum(s.caused_turnovers for s in season_stats),
                    'blocked_shots': sum(s.blocked_shots for s in season_stats),
                    'turnovers': sum(s.turnovers for s in season_stats),
                    'wins': sum(s.wins for s in season_stats),
                    'saves': sum(s.saves for s in season_stats),
                    'goals_against': sum(s.goals_against for s in season_stats),
                })()
                games_played = len(season_stats)
            else:
                stat_for_view = None
                games_played = 0

        # Check roster status
        roster_status = "available"  # Default
        rostered_team = None
        if user_team and selected_league_id:
            # Use pre-fetched roster data instead of querying for each player
            roster_entry = rosters_by_player.get(p.id)
            
            if roster_entry:
                if roster_entry.team == user_team:
                    roster_status = "on_your_team"
                else:
                    roster_status = "on_other_team"
                    rostered_team = roster_entry.team

        fpts = calculate_fantasy_points(stat_for_view, p, selected_league)
        ppg = (fpts / games_played) if games_played > 0 else None
        
        players_with_stats.append({
            "player": p,
            "latest_stat": stat_for_view,
            "fantasy_points": fpts,
            "ppg": ppg,
            "games_played": games_played,
            "roster_status": roster_status,
            "rostered_team": rostered_team,
        })

    def sort_key(item):
        player = item["player"]
        stat = item["latest_stat"]
        fpts = item["fantasy_points"]
        gp = item["games_played"]

        if sort_field == "number":
            return (player.number is None, player.number or 0, player.last_name, player.first_name)
        if sort_field == "position":
            return (player.position or "", player.last_name, player.first_name)
        if sort_field == "gp":
            return (gp == 0, -gp, player.last_name, player.first_name)
        if sort_field == "fpts":
            return (fpts is None, -(fpts or 0), player.last_name, player.first_name)
        if sort_field == "ppg":
            ppg = item["ppg"]
            return (ppg is None, -(ppg or 0), player.last_name, player.first_name)
        if sort_field == "goals":
            val = stat.goals if stat else None
            return (val is None, -(val or 0), player.last_name, player.first_name)
        if sort_field == "assists":
            val = stat.assists if stat else None
            return (val is None, -(val or 0), player.last_name, player.first_name)
        if sort_field == "loose":
            val = stat.loose_balls if stat else None
            return (val is None, -(val or 0), player.last_name, player.first_name)
        if sort_field == "ct":
            val = stat.caused_turnovers if stat else None
            return (val is None, -(val or 0), player.last_name, player.first_name)
        if sort_field == "bs":
            val = stat.blocked_shots if stat else None
            return (val is None, -(val or 0), player.last_name, player.first_name)
        if sort_field == "to":
            val = stat.turnovers if stat else None
            return (val is None, val or 0, player.last_name, player.first_name)
        # Goalie-specific sorts
        if sort_field == "wins":
            val = stat.wins if stat else None
            return (val is None, -(val or 0), player.last_name, player.first_name)
        if sort_field == "saves":
            val = stat.saves if stat else None
            return (val is None, -(val or 0), player.last_name, player.first_name)
        if sort_field == "ga":
            val = stat.goals_against if stat else None
            return (val is None, val or 0, player.last_name, player.first_name)
        if sort_field == "sv_pct":
            if stat and stat.saves and (stat.saves + stat.goals_against) > 0:
                val = stat.saves / (stat.saves + stat.goals_against)
            else:
                val = None
            return (val is None, -(val or 0), player.last_name, player.first_name)
        # default: name
        return (player.last_name, player.first_name)

    reverse = sort_dir == "desc"
    players_with_stats.sort(key=sort_key, reverse=reverse)

    # Add rank based on current sort
    for rank, item in enumerate(players_with_stats, 1):
        item["rank"] = rank

    # Get user's current roster for replacement options
    user_roster = {}
    user_roster_json = "{}"
    roster_can_change = False
    roster_count = 0
    roster_max = 12
    if user_team:
        current_roster = Roster.objects.filter(
            team=user_team,
            week_dropped__isnull=True
        ).select_related('player')
        
        roster_count = current_roster.count()
        roster_max = user_team.league.roster_size if hasattr(user_team.league, 'roster_size') else 12
        
        # Group by position
        for roster_entry in current_roster:
            pos = roster_entry.player.position
            player_data = {
                'id': roster_entry.player.id,
                'first_name': roster_entry.player.first_name,
                'last_name': roster_entry.player.last_name,
                'position': roster_entry.player.position,
                'number': roster_entry.player.number,
            }
            
            # Add to exact position group
            if pos not in user_roster:
                user_roster[pos] = []
            user_roster[pos].append(player_data)
            
            # Transition players also appear in O and D groups
            if pos == 'T':
                if 'O' not in user_roster:
                    user_roster['O'] = []
                if 'D' not in user_roster:
                    user_roster['D'] = []
                user_roster['O'].append(player_data)
                user_roster['D'].append(player_data)
        
        # Convert to JSON for JavaScript
        import json
        user_roster_json = json.dumps(user_roster)
        
        # Check if roster changes are allowed
        can_change, _, _ = user_team.can_make_roster_changes()
        roster_can_change = can_change
        
        # Check if league uses waivers
        use_waivers = user_team.league.use_waivers if hasattr(user_team.league, 'use_waivers') else False

    return render(
        request,
        "web/players.html",
        {
            "players": players_with_stats,
            "seasons": seasons,
            "selected_season": selected_season,
            "week_options": week_options,
            "selected_week_num": selected_week_num,
            "selected_position": selected_position,
            "selected_stat_type": selected_stat_type,
            "sort_field": sort_field,
            "sort_dir": sort_dir,
            "search_query": search_query,
            "user_team": user_team,
            "user_roster_json": user_roster_json,
            "roster_can_change": roster_can_change,
            "roster_count": roster_count,
            "roster_max": roster_max,
            "use_waivers": use_waivers if user_team else False,
        },
    )


def _build_schedule(team_ids, playoff_weeks=2, playoff_teams=4, playoff_reseed="fixed"):
    """Build 18-week regular season schedule + playoff bracket.
    
    Args:
        team_ids: List of team IDs
        playoff_weeks: Number of playoff weeks (0-4)
        playoff_teams: Number of teams that make playoffs (2, 4, 6, or 8)
    
    Returns:
        List of weeks, each containing matchup tuples.
        Regular season weeks are normal matchups.
        Playoff weeks use special tuples: ('playoff', seed1, seed2, round_name)
    """
    teams_local = list(team_ids)
    n = len(teams_local)
    
    # Require even number of teams - no bye weeks allowed
    if n % 2 != 0 or n < 2:
        return []

    anchor = teams_local[0]
    rotate = teams_local[1:]

    def one_round(order_anchor, order_rot):
        """Generate one full round-robin (each team plays each other once)."""
        weeks = []
        rot = order_rot[:]
        for _ in range(n - 1):
            pairings = []
            pairings.append((order_anchor, rot[-1]))
            for i in range((n // 2) - 1):
                pairings.append((rot[i], rot[-i - 2]))
            weeks.append(pairings)
            rot = [rot[-1]] + rot[:-1]
        return weeks

    # Build 18 regular season weeks
    # For 4 teams: round robin is 3 weeks, so repeat 6 times = 18 weeks
    round1 = one_round(anchor, rotate)
    rounds_needed = 18 // len(round1)
    remainder = 18 % len(round1)
    
    regular_season = []
    for _ in range(rounds_needed):
        regular_season.extend(round1)
    if remainder > 0:
        regular_season.extend(round1[:remainder])
    
    schedule = regular_season[:18]  # Ensure exactly 18 weeks
    
    # Always use 3 weeks for 6-team playoffs (with byes for 1/2 seeds)
    if playoff_teams == 6:
        playoff_weeks = 3
    # Add playoff weeks if configured
    if playoff_weeks > 0 and playoff_teams >= 2:
        # Generate playoff bracket based on seeding
        # For now, use placeholder seeds that will be filled from standings
        
        if playoff_teams == 4:
            # Semifinals: 1v4, 2v3
            schedule.append([
                ('playoff', 1, 4, 'Semifinal'),
                ('playoff', 2, 3, 'Semifinal'),
            ])
            if playoff_weeks >= 2:
                # Finals: winners of semifinals
                schedule.append([
                    ('playoff', 'W1', 'W2', 'Championship'),
                ])
        elif playoff_teams == 6:
            # First round: 3v6, 4v5 (1 and 2 get byes)
            schedule.append([
                ('playoff', 3, 6, 'Quarterfinal'),
                ('playoff', 4, 5, 'Quarterfinal'),
            ])
            if playoff_weeks >= 2:
                if playoff_reseed == "reseed":
                    # Semifinals: 1 seed plays lowest remaining, 2 seed plays other
                    # Use special placeholders for bracket logic
                    schedule.append([
                        ('playoff', 1, 'LOWEST_W', 'Semifinal'),
                        ('playoff', 2, 'OTHER_W', 'Semifinal'),
                    ])
                else:
                    # Semifinals: 1vW(3v6), 2vW(4v5) (fixed)
                    schedule.append([
                        ('playoff', 1, 'W1', 'Semifinal'),
                        ('playoff', 2, 'W2', 'Semifinal'),
                    ])
            if playoff_weeks >= 3:
                # Finals
                schedule.append([
                    ('playoff', 'W3', 'W4', 'Championship'),
                ])
        elif playoff_teams == 8:
            # Quarterfinals: 1v8, 2v7, 3v6, 4v5
            schedule.append([
                ('playoff', 1, 8, 'Quarterfinal'),
                ('playoff', 2, 7, 'Quarterfinal'),
                ('playoff', 3, 6, 'Quarterfinal'),
                ('playoff', 4, 5, 'Quarterfinal'),
            ])
            if playoff_weeks >= 2:
                # Semifinals
                schedule.append([
                    ('playoff', 'W1', 'W2', 'Semifinal'),
                    ('playoff', 'W3', 'W4', 'Semifinal'),
                ])
            if playoff_weeks >= 3:
                # Finals
                schedule.append([
                    ('playoff', 'W5', 'W6', 'Championship'),
                ])
        elif playoff_teams == 2:
            # Direct championship: 1v2
            schedule.append([
                ('playoff', 1, 2, 'Championship'),
            ])
    
    return schedule


def get_cached_schedule(team_ids, playoff_weeks=2, playoff_teams=4, playoff_reseed="fixed"):
    """
    Get schedule with caching to avoid expensive recalculation.
    
    Args:
        team_ids: List of team IDs
        playoff_weeks: Number of playoff weeks (0-4)
        playoff_teams: Number of teams that make playoffs (2, 4, 6, or 8)
        playoff_reseed: Playoff reseed strategy ('fixed' or 'dynamic')
    
    Returns:
        Cached or newly generated schedule
    
    This caches the result of _build_schedule() with 24-hour TTL since the schedule
    is based on league settings which change infrequently.
    """
    from web.cache_utils import cache_schedule_generation, CACHE_TTL
    from django.core.cache import cache
    
    # Generate cache key based on parameters
    cache_key = cache_schedule_generation(team_ids, playoff_weeks, playoff_teams, playoff_reseed)
    
    # Try to get from cache
    cached_schedule = cache.get(cache_key)
    if cached_schedule is not None:
        return cached_schedule
    
    # Not in cache, build schedule
    schedule = _build_schedule(team_ids, playoff_weeks, playoff_teams, playoff_reseed)
    
    # Cache for 24 hours (schedule only changes when league settings change)
    cache.set(cache_key, schedule, CACHE_TTL.get('schedule', 86400))
    
    return schedule


def player_detail_modal(request, player_id):
    """AJAX endpoint to get player details for modal popup"""
    from django.http import JsonResponse
    
    try:
        player = Player.objects.get(id=player_id)
    except Player.DoesNotExist:
        return JsonResponse({'error': 'Player not found'}, status=404)
    
    # Use shared constants (imported at top of file)
    
    # Get player's game stats grouped by week
    from django.db.models import Sum
    
    game_stats = player.game_stats.select_related('game__week').order_by('game__week__season', 'game__week__week_number', 'game__date')
    
    # Group stats by week
    stats_by_week = {}
    for stat in game_stats:
        week_key = f"Week {stat.game.week.week_number} (S{stat.game.week.season})"
        if week_key not in stats_by_week:
            stats_by_week[week_key] = []
        stats_by_week[week_key].append({
            'date': stat.game.date.strftime('%Y-%m-%d'),
            'opponent': f"{stat.game.home_team} vs {stat.game.away_team}",
            'goals': stat.goals,
            'assists': stat.assists,
            'loose_balls': stat.loose_balls,
            'caused_turnovers': stat.caused_turnovers,
            'blocked_shots': stat.blocked_shots,
            'turnovers': stat.turnovers,
            'wins': stat.wins,
            'saves': stat.saves,
            'goals_against': stat.goals_against,
        })
    
    # Format week stats
    week_stats = []
    
    # Get a league to access scoring settings (use any league if available)
    league = League.objects.first()
    if not league:
        league = League()  # Default scoring
    
    # Get all weeks from the season to fill in missing weeks with 0 stats
    from django.utils import timezone
    today = timezone.now().date()
    latest_week = Week.objects.order_by('-season', '-week_number').first()
    season = latest_week.season if latest_week else 2026
    
    all_weeks_in_season = Week.objects.filter(season=season).order_by('week_number')
    
    # Sort by week number (numerically, not alphabetically)
    # week_key format: "Week 1 (S2026)" -> extract week number
    def extract_week_number(week_key):
        try:
            return int(week_key.split()[1])
        except (IndexError, ValueError):
            return 0
    
    # Add stats for all weeks (past and upcoming)
    for week in all_weeks_in_season:
        week_key = f"Week {week.week_number} (S{week.season})"
        is_upcoming = week.start_date > today
        
        if week_key in stats_by_week:
            # Player has stats for this week
            games = stats_by_week[week_key]
            # Calculate fantasy points for each game
            game_points = []
            for stat in game_stats:
                if f"Week {stat.game.week.week_number} (S{stat.game.week.season})" == week_key:
                    pts = calculate_fantasy_points(stat, player, league)
                    if pts is not None:
                        game_points.append(pts)
            
            # Calculate weekly total (sum of all games that week)
            weekly_fpts = sum(game_points) if game_points else 0
            
            # Aggregate stats for the week
            agg_stat = {
                'week': week_key,
                'games_count': len(games),
                'goals': sum(g['goals'] for g in games),
                'assists': sum(g['assists'] for g in games),
                'loose_balls': sum(g['loose_balls'] for g in games),
                'caused_turnovers': sum(g['caused_turnovers'] for g in games),
                'blocked_shots': sum(g['blocked_shots'] for g in games),
                'turnovers': sum(g['turnovers'] for g in games),
                'wins': sum(g['wins'] for g in games),
                'saves': sum(g['saves'] for g in games),
                'goals_against': sum(g['goals_against'] for g in games),
                'fantasy_points': round(weekly_fpts, 1),
                'is_upcoming': is_upcoming,
                'games': games
            }
            week_stats.append(agg_stat)
        else:
            # Player has no stats for this week (didn't play or team had bye)
            # Check if player's team had any games scheduled this week
            player_team_id = TEAM_NAME_TO_ID.get(player.nll_team, None)
            upcoming_games = []
            is_bye_week = True
            
            if player_team_id:
                games = Game.objects.filter(
                    Q(week=week, home_team=player_team_id) | 
                    Q(week=week, away_team=player_team_id)
                )
                upcoming_games = [{
                    'date': game.date.strftime('%Y-%m-%d'),
                    'opponent': f"{TEAM_ID_TO_NAME.get(game.home_team, game.home_team)} vs {TEAM_ID_TO_NAME.get(game.away_team, game.away_team)}",
                } for game in games]
                is_bye_week = len(upcoming_games) == 0
            
            agg_stat = {
                'week': week_key,
                'games_count': len(upcoming_games),
                'goals': 0,
                'assists': 0,
                'loose_balls': 0,
                'caused_turnovers': 0,
                'blocked_shots': 0,
                'turnovers': 0,
                'wins': 0,
                'saves': 0,
                'goals_against': 0,
                'fantasy_points': 0.0,
                'is_no_stats': True,  # Mark as no stats for this week
                'is_bye': is_bye_week,  # True if team didn't play this week
                'is_upcoming': is_upcoming,
                'games': upcoming_games if is_upcoming else []
            }
            week_stats.append(agg_stat)
    
    # Build response data
    data = {
        'player': {
            'name': f"{player.first_name} {player.last_name}",
            'number': player.number,
            'position': player.get_position_display(),
            'nll_team': player.nll_team,
            'shoots': player.shoots or 'Unknown',
            'height': player.height or 'Unknown',
            'weight': player.weight or 'Unknown',
            'hometown': player.hometown or 'Unknown',
            'draft_year': player.draft_year or 'Unknown',
            'birthdate': player.birthdate.strftime('%B %d, %Y') if player.birthdate else 'Unknown',
            'is_rookie': player.is_rookie,
        },
        'week_stats': week_stats
    }
    
    return JsonResponse(data)


def cache_stats(request):
    """Display cache statistics and performance metrics"""
    from django.core.cache import cache
    from django.core.cache.backends.redis import RedisCache
    from django.http import HttpResponse
    
    # Only allow admin users to see cache stats
    if not request.user.is_staff:
        return HttpResponse("Unauthorized", status=403)
    
    stats = {
        'cache_backend': 'Unknown',
        'redis_info': {},
        'cache_keys_monitored': [],
        'status': 'OK',
    }
    
    try:
        if isinstance(cache, RedisCache):
            stats['cache_backend'] = 'Redis'
            redis_conn = cache._cache
            info = redis_conn.info()
            
            stats['redis_info'] = {
                'memory_used': info.get('used_memory_human', 'N/A'),
                'memory_peak': info.get('used_memory_peak_human', 'N/A'),
                'connected_clients': info.get('connected_clients', 0),
                'total_commands': info.get('total_commands_processed', 0),
                'hits': info.get('keyspace_hits', 0),
                'misses': info.get('keyspace_misses', 0),
                'hit_rate': f"{(info.get('keyspace_hits', 0) / (info.get('keyspace_hits', 0) + info.get('keyspace_misses', 1))) * 100:.1f}%",
                'uptime_seconds': info.get('uptime_in_seconds', 0),
                'database_0_keys': info.get('db0', {}).get('keys', 0) if 'db0' in info else 'N/A',
            }
            
            # Check cache keys
            from web.cache_utils import get_standings_cache_key, get_team_detail_cache_key, get_matchups_cache_key
            
            standings_key = get_standings_cache_key(None)
            stats['cache_keys_monitored'].append({
                'key': 'standings (sample)',
                'cached': cache.get(standings_key) is not None,
                'ttl': 'unknown'
            })
    
    except Exception as e:
        stats['status'] = f'Error: {str(e)}'
    
    # Return JSON response
    return JsonResponse(stats, json_dumps_params={'indent': 2})


@never_cache
def nll_schedule(request):
    """Display all NLL weeks and games (both completed and upcoming)"""
    season = request.GET.get('season', 2026)
    
    try:
        season = int(season)
    except (ValueError, TypeError):
        season = 2026
    
    # Use shared extended team mapping (imported at top of file)
    nll_teams = EXTENDED_TEAM_ID_TO_NAME
    
    # Get all weeks for this season, ordered by week number
    # Important: Prefetch player_stats to check completion status without N+1 queries
    from django.db.models import Prefetch
    weeks = Week.objects.filter(season=season).prefetch_related(
        'games',
        Prefetch('games__player_stats')  # Prefetch player_stats for all games
    ).order_by('week_number')
    
    if not weeks.exists():
        return render(request, "web/nll_schedule.html", {
            "schedule_weeks": [],
            "season": season,
            "available_seasons": []
        })
    
    # Build schedule data
    schedule_weeks = []
    for week in weeks:
        games = week.games.all().order_by('date')
        
        week_games = []
        for game in games:
            home_name = game.home_team
            away_name = game.away_team
            
            # Try to convert team IDs to names
            if game.home_team and game.away_team:
                try:
                    home_id = int(game.home_team)
                    home_name = nll_teams.get(home_id, game.home_team)
                except (ValueError, TypeError):
                    pass
                
                try:
                    away_id = int(game.away_team)
                    away_name = nll_teams.get(away_id, game.away_team)
                except (ValueError, TypeError):
                    pass
            
            game_dict = {
                "id": game.id,
                "date": game.date,
                "home_team": home_name,
                "away_team": away_name,
                "nll_game_id": game.nll_game_id,
                # Check if game has stats (completed) vs upcoming - use prefetched data length
                "is_completed": len(game.player_stats.all()) > 0
            }
            week_games.append(game_dict)
        
        week_data = {
            "week_number": week.week_number,
            "start_date": week.start_date,
            "end_date": week.end_date,
            "is_playoff": week.is_playoff,
            "games": week_games
        }
        schedule_weeks.append(week_data)
    
    # Get available seasons from database
    available_seasons = Week.objects.values_list('season', flat=True).distinct().order_by('-season')
    
    return render(request, "web/nll_schedule.html", {
        "schedule_weeks": schedule_weeks,
        "season": season,
        "available_seasons": available_seasons,
    })


def schedule(request):
    teams = list(Team.objects.order_by("id"))

    if not teams:
        return render(request, "web/schedule.html", {"schedule_weeks": []})
    
    league = teams[0].league
    team_ids = [t.id for t in teams]
    weeks = get_cached_schedule(team_ids, league.playoff_weeks, league.playoff_teams, getattr(league, 'playoff_reseed', 'fixed'))

    # map ids back to team objects for display
    id_to_team = {t.id: t for t in teams}
    schedule_weeks = []
    for idx, games in enumerate(weeks, start=1):
        week_games = []
        for game in games:
            if isinstance(game, tuple) and len(game) == 4 and game[0] == 'playoff':
                # Playoff game: ('playoff', seed1, seed2, round_name)
                _, seed1, seed2, round_name = game
                week_games.append({
                    "is_playoff": True,
                    "seed1": seed1,
                    "seed2": seed2,
                    "round_name": round_name,
                    "home": None,
                    "away": None,
                })
            else:
                # Regular season game: (team_id, team_id)
                a, b = game
                week_games.append({
                    "is_playoff": False,
                    "home": id_to_team.get(a),
                    "away": id_to_team.get(b),
                })
        
        schedule_weeks.append({
            "week_number": idx,
            "games": week_games,
        })

    return render(request, "web/schedule.html", {"schedule_weeks": schedule_weeks})


def matchups(request):
    # Get selected league from session
    selected_league_id = request.session.get('selected_league_id')
    
    if selected_league_id:
        teams = list(Team.objects.filter(league_id=selected_league_id).order_by("id"))
        # Use the most recent season (not league creation year)
        latest_week = Week.objects.order_by('-season', '-week_number').first()
        league_season = latest_week.season if latest_week else timezone.now().year
    else:
        teams = list(Team.objects.filter(league__is_active=True).order_by("id"))
        # Use the most recent season
        latest_week = Week.objects.order_by('-season', '-week_number').first()
        league_season = latest_week.season if latest_week else timezone.now().year
    
    # Get actual weeks that exist for this season
    actual_weeks = Week.objects.filter(season=league_season).order_by('week_number')
    # Only count weeks where games have been completed (end_date has passed)
    completed_weeks = actual_weeks.filter(end_date__lt=timezone.now())
    max_week = completed_weeks.last().week_number if completed_weeks.exists() else 0
    
    # IMPORTANT: Keep teams sorted by ID (do NOT reorder by user team position)
    # The schedule algorithm uses team order as the anchor for round-robin rotation.
    # Changing the order would generate different matchups for different users!
    # teams.sort(key=lambda t: t.id)  # Already sorted from query above
    
    team_ids = [t.id for t in teams]
    
    # Get league to access playoff settings
    if teams:
        league = teams[0].league
        all_weeks = get_cached_schedule(team_ids, league.playoff_weeks, league.playoff_teams, getattr(league, 'playoff_reseed', 'fixed'))
    else:
        league = League()  # Default scoring
        all_weeks = get_cached_schedule(team_ids)
    
    # Show all regular season weeks in matchups (filter out playoff weeks for now)
    # TODO: Implement playoff bracket display once regular season completes
    weeks = [w for w in all_weeks if w and all(not (isinstance(g, tuple) and len(g) == 4 and g[0] == 'playoff') for g in w)]

    id_to_team = {t.id: t for t in teams}

    # determine target week object (same week_number, latest season available)
    selected_week_number = None
    if weeks:
        # Get the current/active week (where today falls between start and end)
        today = timezone.now().date()
        current_week_obj = Week.objects.filter(
            season=league_season,
            start_date__lte=today,
            end_date__gte=today
        ).first()
        
        if current_week_obj:
            # Week is currently active
            default_week = current_week_obj.week_number
        else:
            # No active week - find the next upcoming week
            next_week_obj = Week.objects.filter(
                season=league_season,
                start_date__gt=today
            ).order_by('week_number').first()
            
            if next_week_obj:
                # Show the next upcoming week
                default_week = next_week_obj.week_number
            else:
                # No future week - use Week 1 (season hasn't started yet or is over)
                default_week = 1
        
        try:
            selected_week_number = int(request.GET.get("week", default_week))
        except ValueError:
            selected_week_number = default_week

    week_obj = None
    if selected_week_number is not None:
        # Only get week from current league season, not previous seasons
        week_obj = Week.objects.filter(week_number=selected_week_number, season=league_season).first()

    # Build detailed rosters with slot structure (like team_detail view)
    # OPTIMIZATION: Fetch all rosters once instead of per-team, then group by team_id
    from collections import defaultdict
    
    # Get filter criteria for historical week lookup
    week_filter_q = models.Q(player__active=True)
    if selected_week_number:
        week_filter_q &= (
            models.Q(week_added__isnull=True) | models.Q(week_added__lte=selected_week_number)
        )
        week_filter_q &= (
            models.Q(week_dropped__isnull=True) | models.Q(week_dropped__gt=selected_week_number)
        )
    else:
        # If no week selected, show current roster only
        week_filter_q &= models.Q(week_dropped__isnull=True)
    
    # Get all rosters for all teams at once with prefetch
    all_rosters_list = list(
        Roster.objects.filter(team__in=teams).filter(week_filter_q)
        .select_related('player')
        .prefetch_related('player__game_stats__game__week')
        .order_by("player__updated_at", "player__id")
    )
    
    # Group rosters by team_id for O(1) lookup
    rosters_by_team = defaultdict(list)
    for roster_entry in all_rosters_list:
        rosters_by_team[roster_entry.team_id].append(roster_entry)
    
    team_rosters = {}
    team_totals = {}
    for team in teams:
        # OPTIMIZATION: Get rosters from grouped data instead of per-team database query
        players_by_position = {"O": [], "D": [], "G": [], "T": []}
        
        # Access only this team's rosters from the grouping
        roster = rosters_by_team.get(team.id, [])
        
        for roster_entry in roster:
            p = roster_entry.player
            fpts = None
            if week_obj:
                # OPTIMIZATION: Iterate through prefetched game_stats instead of filtering
                game_stats = [s for s in p.game_stats.all() if s.game.week_id == week_obj.id]
                if game_stats:
                    # Calculate fantasy points for each game
                    pts_list = [calculate_fantasy_points(st, p, league) for st in game_stats if st is not None]
                    if pts_list:
                        # Apply league's multigame_scoring setting
                        if league.multigame_scoring == "average" and len(pts_list) > 1:
                            fpts = sum(pts_list) / len(pts_list)
                        elif league.multigame_scoring == "highest":
                            fpts = max(pts_list)
                        else:
                            # Default to highest
                            fpts = max(pts_list)
            
            entry = {"player": p, "fantasy_points": fpts}
            pos = getattr(p, "position", None)
            side = getattr(p, "assigned_side", None)
            target = side or ("O" if pos == "T" else pos)
            if target in players_by_position:
                players_by_position[target].append(entry)
            else:
                players_by_position["O"].append(entry)
        
        # Build slots
        offence_pool = players_by_position["O"]
        defence_pool = players_by_position["D"]
        
        offence_slots = offence_pool[:6]
        defence_slots = defence_pool[:6]
        goalie_slots = players_by_position["G"][:2]
        
        while len(offence_slots) < 6:
            offence_slots.append(None)
        while len(defence_slots) < 6:
            defence_slots.append(None)
        while len(goalie_slots) < 2:
            goalie_slots.append(None)
        
        # Calculate totals based on best-ball: top 3 offense, top 3 defense, top 1 goalie
        offense_scores = []
        for slot in offence_slots:
            if slot and slot["fantasy_points"] is not None:
                offense_scores.append((slot["fantasy_points"], slot))
        
        defense_scores = []
        for slot in defence_slots:
            if slot and slot["fantasy_points"] is not None:
                defense_scores.append((slot["fantasy_points"], slot))
        
        goalie_scores = []
        for slot in goalie_slots:
            if slot and slot["fantasy_points"] is not None:
                goalie_scores.append((slot["fantasy_points"], slot))
        
        # Sort by score descending
        offense_scores.sort(key=lambda x: x[0], reverse=True)
        defense_scores.sort(key=lambda x: x[0], reverse=True)
        goalie_scores.sort(key=lambda x: x[0], reverse=True)
        
        # Mark top scorers
        for score, slot in offense_scores[:3]:
            slot['counts_for_total'] = True
        for score, slot in defense_scores[:3]:
            slot['counts_for_total'] = True
        for score, slot in goalie_scores[:1]:
            slot['counts_for_total'] = True
        
        week_total = sum(x[0] for x in offense_scores[:3]) + sum(x[0] for x in defense_scores[:3]) + sum(x[0] for x in goalie_scores[:1])
        
        team_rosters[team.id] = {
            "offence_slots": offence_slots,
            "defence_slots": defence_slots,
            "goalie_slots": goalie_slots,
        }
        team_totals[team.id] = week_total

    schedule_weeks = []
    for idx, games in enumerate(weeks, start=1):
        schedule_weeks.append(
            {
                "week_number": idx,
                "games": [
                    {
                        "home": id_to_team.get(a),
                        "away": id_to_team.get(b),
                        "home_roster": team_rosters.get(a, {}),
                        "away_roster": team_rosters.get(b, {}),
                        "home_total": team_totals.get(a, 0),
                        "away_total": team_totals.get(b, 0),
                        "home_result": (
                            "W" if team_totals.get(a, 0) > team_totals.get(b, 0)
                            else "L" if team_totals.get(a, 0) < team_totals.get(b, 0)
                            else "T"
                        ),
                        "away_result": (
                            "W" if team_totals.get(b, 0) > team_totals.get(a, 0)
                            else "L" if team_totals.get(b, 0) < team_totals.get(a, 0)
                            else "T"
                        ),
                    }
                    for (a, b) in games
                ],
            }
        )

    selected_week = None
    if schedule_weeks and selected_week_number is not None:
        selected_week = next((w for w in schedule_weeks if w["week_number"] == selected_week_number), None)

    return render(
        request,
        "web/matchups.html",
        {
            "schedule_weeks": schedule_weeks,
            "selected_week": selected_week,
            "selected_week_number": selected_week_number,
        },
    )


@cache_view_with_request(get_standings_cache_key_from_request, 'standings')
def standings(request):
    # Get selected league from session
    selected_league_id = request.session.get('selected_league_id')
    
    if selected_league_id:
        leagues = League.objects.filter(id=selected_league_id).prefetch_related('teams')
    else:
        # Get all active leagues
        leagues = League.objects.filter(is_active=True).prefetch_related('teams')
    
    all_league_standings = []
    
    for league in leagues:
        teams = list(league.teams.order_by("name"))
        if not teams:
            continue
            
        team_ids = [t.id for t in teams]
        all_weeks = get_cached_schedule(team_ids)
        
        # Get current season and only process completed weeks (end_date has passed)
        latest_week = Week.objects.order_by('-season', '-week_number').first()
        league_season = latest_week.season if latest_week else timezone.now().year
        # Only include weeks where end_date has passed (week is complete)
        # Compare dates properly: end_date is a DateField, so use date() for timezone.now()
        today = timezone.now().date()
        completed_weeks = Week.objects.filter(season=league_season, end_date__lt=today).order_by('week_number')
        max_week = completed_weeks.last().week_number if completed_weeks.exists() else 0
        # Only process completed weeks in the standings
        weeks = all_weeks[:max_week] if max_week > 0 else []

        # prefetch players once via roster entries
        from collections import defaultdict

        rosters = (
            Roster.objects.filter(team__in=teams, league=league, player__active=True)
            .select_related("player", "team")
            .prefetch_related("player__game_stats__game__week")
        )
        # Store all rosters with their week ranges for historical lookup
        all_rosters = list(rosters)
        
        # OPTIMIZATION: Group rosters by team_id for O(1) lookup instead of looping all rosters
        rosters_by_team = defaultdict(list)
        for roster_entry in all_rosters:
            rosters_by_team[roster_entry.team_id].append(roster_entry)
        
        week_cache = {}
        standings_map = {
            t.id: {
                "team": t,
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "total_points": 0,
                "points_against": 0,
                "games": 0,
            }
            for t in teams
        }

        def team_week_total(team_id, week_number):
            week_obj = week_cache.get(week_number)
            if week_obj is None:
                # Only get weeks from current season
                week_obj = Week.objects.filter(week_number=week_number, season=league_season).first()
                week_cache[week_number] = week_obj
            total = 0
            
            # Get players who were on the roster during this specific week
            # OPTIMIZATION: Access only this team's rosters (12-14 items) instead of all rosters (140+ items)
            active_players = []
            team_rosters = rosters_by_team.get(team_id, [])
            for roster_entry in team_rosters:
                # Check if player was active during this week
                week_added = roster_entry.week_added or 0  # Treat NULL as week 0 (always active)
                week_dropped = roster_entry.week_dropped or 999  # Treat NULL as week 999 (still active)
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
                    # Only get stats from the actual week object (no fallback to other seasons)
                    stat = next((s for s in p.game_stats.all() if s.game.week_id == week_obj.id), None)
                pts = calculate_fantasy_points(stat, p, league)
                if pts is not None:
                    total += pts
            return total

        for idx, games in enumerate(weeks, start=1):
            for (a, b) in games:
                home_total = team_week_total(a, idx)
                away_total = team_week_total(b, idx)

                standings_map[a]["total_points"] += home_total
                standings_map[b]["total_points"] += away_total
                standings_map[a]["points_against"] += away_total
                standings_map[b]["points_against"] += home_total
                standings_map[a]["games"] += 1
                standings_map[b]["games"] += 1

                if home_total > away_total:
                    standings_map[a]["wins"] += 1
                    standings_map[b]["losses"] += 1
                elif home_total < away_total:
                    standings_map[b]["wins"] += 1
                    standings_map[a]["losses"] += 1
                else:
                    standings_map[a]["ties"] += 1
                    standings_map[b]["ties"] += 1

        standings_list = list(standings_map.values())
        standings_list.sort(key=lambda r: (-r["wins"], -r["total_points"], r["team"].name))
        
        all_league_standings.append({
            'league': league,
            'standings': standings_list
        })

    return render(
        request,
        "web/standings.html",
        {
            "league_standings": all_league_standings,
        },
    )


# ============ AUTHENTICATION VIEWS ============

def login_view(request):
    """User login"""
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            return redirect("home")
        else:
            messages.error(request, "Invalid username or password.")
    
    return render(request, "web/login.html")


def logout_view(request):
    """User logout"""
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("home")


# ============ CHAT VIEWS ============

@login_required
def chat_view(request):
    """Display chat with option to view league chat or team chats"""
    from ..models import TeamChatMessage
    from datetime import datetime, timedelta
    
    selected_league_id = request.session.get('selected_league_id')
    
    # Auto-select league if user has exactly one
    if not selected_league_id and request.user.is_authenticated:
        user_leagues = FantasyTeamOwner.objects.filter(user=request.user).select_related('team__league')
        if user_leagues.count() == 1:
            selected_league_id = user_leagues.first().team.league.id
            request.session['selected_league_id'] = selected_league_id
    
    if not selected_league_id:
        messages.warning(request, "Please select a league to view chat.")
        return redirect('league_list')
    
    # Get the user's team(s) in this league
    user_team = None
    if request.user.is_authenticated:
        owner = FantasyTeamOwner.objects.filter(
            user=request.user,
            team__league_id=selected_league_id
        ).select_related('team').first()
        if owner:
            user_team = owner.team
    
    # Initialize chat read tracking in session
    if 'chat_last_read' not in request.session:
        request.session['chat_last_read'] = {}
    
    # Determine which chat to display
    chat_type = request.GET.get('chat_type', 'league')  # 'league' or 'team'
    team_chat_id = request.GET.get('team_chat_id', None)  # ID of other team for team chats
    
    messages_list = []
    available_team_chats = []
    current_chat_with = None
    chat_key_viewed = f"league_{selected_league_id}"  # Default to league chat
    
    if chat_type == 'league':
        # Display league chat
        messages_list = ChatMessage.objects.filter(
            league_id=selected_league_id
        ).select_related(
            'sender', 'player', 'team', 'league'
        ).all()[:100]  # Last 100 messages
        chat_key_viewed = f"league_{selected_league_id}"
    
    elif chat_type == 'team' and team_chat_id and user_team:
        # Display team-to-team chat
        other_team_id = int(team_chat_id)
        # Ensure consistent ordering (lower ID first)
        team1_id = min(user_team.id, other_team_id)
        team2_id = max(user_team.id, other_team_id)
        
        messages_list = TeamChatMessage.objects.filter(
            team1_id=team1_id,
            team2_id=team2_id
        ).select_related(
            'sender', 'team1', 'team2', 'trade'
        ).all()[:100]  # Last 100 messages
        
        # Get the other team
        current_chat_with = Team.objects.get(id=other_team_id)
        chat_key_viewed = f"team_{team1_id}_{team2_id}"
    
    # Get all other teams in the league for chat options
    team_unread_counts = {}
    if user_team:
        # Show all other teams in the league (not just existing chats)
        available_team_chats = Team.objects.filter(
            league_id=selected_league_id
        ).exclude(
            id=user_team.id
        ).order_by('name')
        
        # Calculate unread counts for each team chat
        for other_team in available_team_chats:
            team1_id = min(user_team.id, other_team.id)
            team2_id = max(user_team.id, other_team.id)
            chat_key = f"team_{team1_id}_{team2_id}"
            
            last_read = request.session['chat_last_read'].get(chat_key)
            if last_read:
                # Count messages after last read time
                last_read_dt = datetime.fromisoformat(last_read)
                unread = TeamChatMessage.objects.filter(
                    team1_id=team1_id,
                    team2_id=team2_id,
                    created_at__gt=last_read_dt
                ).count()
            else:
                # No read history, count recent messages (last 7 days)
                cutoff = datetime.now() - timedelta(days=7)
                unread = TeamChatMessage.objects.filter(
                    team1_id=team1_id,
                    team2_id=team2_id,
                    created_at__gt=cutoff
                ).count()
            
            team_unread_counts[other_team.id] = unread
    else:
        available_team_chats = []
    
    # Calculate unread count for league chat
    league_unread = 0
    league_chat_key = f"league_{selected_league_id}"
    last_read = request.session['chat_last_read'].get(league_chat_key)
    if last_read:
        last_read_dt = datetime.fromisoformat(last_read)
        league_unread = ChatMessage.objects.filter(
            league_id=selected_league_id,
            created_at__gt=last_read_dt
        ).count()
    
    # Mark current chat as read by updating session
    if messages_list:
        request.session['chat_last_read'][chat_key_viewed] = datetime.now().isoformat()
        request.session.modified = True
    
    # Calculate total unread chats for badge
    total_chats_with_unread = (1 if league_unread > 0 else 0) + sum(1 for count in team_unread_counts.values() if count > 0)
    
    return render(request, "web/chat.html", {
        "messages": messages_list,
        "chat_type": chat_type,
        "current_chat_with": current_chat_with,
        "available_team_chats": available_team_chats,
        "user_team": user_team,
        "is_team_chat": chat_type == 'team',
        "league_unread": league_unread,
        "team_unread_counts": team_unread_counts,
        "total_chats_with_unread": total_chats_with_unread,
    })


@login_required
@require_POST
def chat_post_message(request):
    """API endpoint to post a new chat message (league or team)"""
    from ..models import TeamChatMessage
    
    selected_league_id = request.session.get('selected_league_id')
    
    if not selected_league_id:
        return JsonResponse({"error": "No league selected"}, status=400)
    
    try:
        league = League.objects.get(id=selected_league_id)
    except League.DoesNotExist:
        return JsonResponse({"error": "League not found"}, status=404)
    
    # Verify user is a member of this league
    owner = FantasyTeamOwner.objects.filter(user=request.user, team__league=league).first()
    if not owner:
        return JsonResponse({"error": "You are not a member of this league"}, status=403)
    
    message_text = request.POST.get("message", "").strip()
    chat_type = request.POST.get("chat_type", "league")
    team_chat_id = request.POST.get("team_chat_id", None)
    
    if not message_text:
        return JsonResponse({"error": "Message cannot be empty"}, status=400)
    
    if len(message_text) > 1000:
        return JsonResponse({"error": "Message too long (max 1000 characters)"}, status=400)
    
    # Create the appropriate chat message
    if chat_type == 'league':
        # League chat
        chat_msg = ChatMessage.objects.create(
            league=league,
            sender=request.user,
            message_type=ChatMessage.MessageType.CHAT,
            message=message_text
        )
    elif chat_type == 'team' and team_chat_id:
        # Team-to-team chat
        other_team_id = int(team_chat_id)
        other_team = Team.objects.get(id=other_team_id, league=league)
        
        # Create message using the helper function
        post_team_chat_message(
            owner.team, 
            other_team, 
            message_text,
            sender=request.user
        )
        
        # Get the message we just created
        team1_id = min(owner.team.id, other_team_id)
        team2_id = max(owner.team.id, other_team_id)
        chat_msg = TeamChatMessage.objects.filter(
            team1_id=team1_id,
            team2_id=team2_id
        ).order_by('-created_at').first()
    else:
        return JsonResponse({"error": "Invalid chat type or team"}, status=400)
    
    return JsonResponse({
        "success": True,
        "message_id": chat_msg.id,
        "created_at": chat_msg.created_at.isoformat()
    })


@login_required
def chat_get_messages(request):
    """API endpoint to fetch new chat messages (for auto-refresh)"""
    from ..models import TeamChatMessage
    
    selected_league_id = request.session.get('selected_league_id')
    
    if not selected_league_id:
        return JsonResponse({"messages": []})
    
    since_id = request.GET.get("since", 0)
    chat_type = request.GET.get("chat_type", "league")
    team_chat_id = request.GET.get("team_chat_id", None)
    
    data = []
    
    if chat_type == 'league':
        # League chat messages
        messages_list = ChatMessage.objects.filter(
            league_id=selected_league_id,
            id__gt=since_id
        ).select_related(
            'sender', 'player', 'player_dropped', 'team'
        ).order_by('created_at')[:50]
        
        for msg in messages_list:
            sender_name = msg.sender.username if msg.sender else "System"
            team_names = []
            
            # Get team names if sender is a team owner
            if msg.sender:
                team_names = [
                    owner.team.name 
                    for owner in msg.sender.fantasy_teams.filter(team__league_id=selected_league_id)
                ]
            
            # For transaction messages (ADD/DROP/TRADE), use the team name if available
            if msg.message_type in [ChatMessage.MessageType.ADD, ChatMessage.MessageType.DROP] and msg.team:
                sender_name = msg.team.name
            
            player_name = None
            if msg.player:
                player_name = f"{msg.player.first_name} {msg.player.last_name}"
            
            player_dropped_name = None
            if msg.player_dropped:
                player_dropped_name = f"{msg.player_dropped.first_name} {msg.player_dropped.last_name}"
            
            data.append({
                "id": msg.id,
                "sender": sender_name,
                "teams": team_names,
                "message": msg.message,
                "message_type": msg.message_type,
                "player": player_name,
                "player_dropped": player_dropped_name,
                "created_at": msg.created_at.isoformat(),
                "is_system": msg.sender is None
            })
    
    elif chat_type == 'team' and team_chat_id:
        # Team chat messages
        user_team = FantasyTeamOwner.objects.filter(
            user=request.user,
            team__league_id=selected_league_id
        ).select_related('team').first()
        
        if user_team:
            other_team_id = int(team_chat_id)
            team1_id = min(user_team.team.id, other_team_id)
            team2_id = max(user_team.team.id, other_team_id)
            
            messages_list = TeamChatMessage.objects.filter(
                team1_id=team1_id,
                team2_id=team2_id,
                id__gt=since_id
            ).select_related(
                'sender', 'team1', 'team2'
            ).order_by('created_at')[:50]
            
            for msg in messages_list:
                sender_name = msg.sender.username if msg.sender else "System"
                
                data.append({
                    "id": msg.id,
                    "sender": sender_name,
                    "message": msg.message,
                    "message_type": msg.message_type,
                    "created_at": msg.created_at.isoformat(),
                    "is_system": msg.sender is None
                })
    
    return JsonResponse({"messages": data})


def create_transaction_notification(transaction_type, team, player, user=None):
    """Helper function to create add/drop notifications"""
    if not team or not team.league:
        return
        
    if transaction_type == "ADD":
        message = f"added {player} to their roster"
        msg_type = ChatMessage.MessageType.ADD
    elif transaction_type == "DROP":
        message = f"dropped {player} from their roster"
        msg_type = ChatMessage.MessageType.DROP
    else:
        return
    
    ChatMessage.objects.create(
        league=team.league,
        sender=user,
        message_type=msg_type,
        message=message,
        player=player,
        team=team
    )


# ============ REGISTRATION & LEAGUE/TEAM MANAGEMENT ============

def register_view(request):
    """User registration"""
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome {user.username}! Account created successfully.")
            return redirect("league_list")
    else:
        form = UserRegistrationForm()
    
    return render(request, "web/register.html", {"form": form})


@login_required
def league_list(request):
    """List all active leagues and user's leagues (including archived) with search functionality"""
    search_query = request.GET.get('search', '').strip()
    search_type = request.GET.get('search_type', 'name')
    
    # Leagues the user is commissioner of (include archived for reference)
    my_leagues = League.objects.filter(commissioner=request.user)
    
    # Leagues where user owns a team (include archived for reference)
    my_team_leagues = League.objects.filter(
        teams__owner__user=request.user
    ).distinct()
    
    # All other ACTIVE leagues only
    other_leagues = League.objects.filter(is_active=True).exclude(
        id__in=my_leagues.values_list('id', flat=True)
    ).exclude(
        id__in=my_team_leagues.values_list('id', flat=True)
    )
    
    # Apply search filter and privacy rules
    if search_query:
        # When searching, show both public and private leagues that match
        if search_type == 'code':
            # Search by unique ID (case-insensitive exact match)
            other_leagues = other_leagues.filter(unique_id__iexact=search_query)
        else:
            # Search by name (case-insensitive contains)
            other_leagues = other_leagues.filter(name__icontains=search_query)
    else:
        # Without search, only show public leagues
        other_leagues = other_leagues.filter(is_public=True)
    
    # Separate user's active and archived leagues
    my_active = my_leagues.filter(is_active=True)
    my_archived = my_leagues.filter(is_active=False)
    
    my_team_active = my_team_leagues.filter(is_active=True)
    my_team_archived = my_team_leagues.filter(is_active=False)
    
    return render(request, "web/league_list.html", {
        "my_active_leagues": my_active,
        "my_archived_leagues": my_archived,
        "my_team_active_leagues": my_team_active,
        "my_team_archived_leagues": my_team_archived,
        "other_leagues": other_leagues,
        "search_query": search_query,
        "search_type": search_type,
    })


@login_required
def league_create(request):
    """Create a new league"""
    if request.method == "POST":
        form = LeagueCreateForm(request.POST)
        if form.is_valid():
            league = form.save(commit=False)
            league.commissioner = request.user
            league.save()
            
            # Set the default current_week to the first available week of the season
            current_year = timezone.now().year
            first_week = Week.objects.filter(season=current_year).order_by('week_number').first()
            if first_week:
                league.current_week = first_week
                league.save()
            
            messages.success(request, f"League '{league.name}' created successfully!")
            return redirect("league_detail", league_id=league.id)
    else:
        form = LeagueCreateForm()
    
    return render(request, "web/league_create.html", {"form": form})


@cache_view_result(lambda league_id: get_league_detail_cache_key(league_id), 'league_detail')
@login_required
def league_detail(request, league_id):
    """View league details and teams"""
    league = get_object_or_404(League, id=league_id)
    teams = league.teams.select_related('owner__user').all()
    
    # Check if user owns a team in this league
    user_team = None
    try:
        user_team = teams.get(owner__user=request.user)
    except Team.DoesNotExist:
        pass
    
    is_commissioner = league.commissioner == request.user
    can_join = not user_team and teams.count() < league.max_teams
    can_renew = is_commissioner and not league.is_active  # Show renewal button for archived leagues
    
    return render(request, "web/league_detail.html", {
        "league": league,
        "teams": teams,
        "user_team": user_team,
        "is_commissioner": is_commissioner,
        "can_join": can_join,
        "can_renew": can_renew
    })


@login_required
def team_create(request, league_id):
    """Create a team in a league and join as owner"""
    league = get_object_or_404(League, id=league_id)
    
    # Check if user already has a team in this league
    if FantasyTeamOwner.objects.filter(user=request.user, team__league=league).exists():
        messages.error(request, "You already have a team in this league.")
        return redirect("league_detail", league_id=league.id)
    
    # Check if league is full
    current_team_count = league.teams.count()
    if current_team_count >= league.max_teams:
        messages.error(request, "This league is full.")
        return redirect("league_detail", league_id=league.id)
    
    # Prevent odd number of teams - if we're at max_teams - 1 and max_teams is even,
    # warn that one more team is needed
    if current_team_count == league.max_teams - 1:
        messages.info(request, f"Note: This league needs {league.max_teams} teams (even number). One more team needed after yours!")
    
    if request.method == "POST":
        form = TeamCreateForm(request.POST, league=league)
        if form.is_valid():
            team = form.save()
            
            # Create FantasyTeamOwner to link user to team
            FantasyTeamOwner.objects.create(user=request.user, team=team)
            
            # For dynasty leagues with taxi squad enabled, create taxi squad slots
            if hasattr(league, 'league_type') and league.league_type == 'dynasty':
                use_taxi = getattr(league, 'use_taxi_squad', True)
                if use_taxi:
                    from ..models import TaxiSquad
                    taxi_size = league.taxi_squad_size if hasattr(league, 'taxi_squad_size') else 3
                    for slot_num in range(1, taxi_size + 1):
                        TaxiSquad.objects.get_or_create(
                            team=team,
                            slot_number=slot_num,
                            defaults={'player': None}
                        )
                
                # For dynasty leagues with future picks enabled, create future picks for this team
                use_future_picks = getattr(league, 'use_future_rookie_picks', True)
                if use_future_picks:
                    from ..tasks import create_future_rookie_picks
                    # Get configured num_rounds from league draft, or use default
                    num_rounds = None
                    if hasattr(league, 'draft') and league.draft:
                        num_rounds = league.draft.total_rounds
                    create_future_rookie_picks(league.id, team=team, years_ahead=5, num_rounds=num_rounds)
            
            messages.success(request, f"Team '{team.name}' created! You've joined {league.name}.")
            return redirect("league_detail", league_id=league.id)
    else:
        form = TeamCreateForm(league=league)
    
    return render(request, "web/team_create.html", {
        "form": form,
        "league": league
    })


@login_required
def select_league(request, league_id):
    """Set the selected league in session"""
    league = get_object_or_404(League, id=league_id)
    request.session['selected_league_id'] = league_id
    return redirect('home')


@login_required
def league_settings(request, league_id):
    """League settings page - view for all, edit for commissioner only"""
    league = get_object_or_404(League, id=league_id)
    
    # Check if user is in this league
    user_in_league = FantasyTeamOwner.objects.filter(
        user=request.user, 
        team__league=league
    ).exists()
    
    is_commissioner = league.commissioner == request.user
    
    # Allow viewing if user is commissioner or has a team in the league
    if not is_commissioner and not user_in_league:
        messages.error(request, "You must be a member of this league to view settings.")
        return redirect("league_detail", league_id=league.id)
    
    # Only commissioner can edit
    if request.method == "POST":
        if not is_commissioner:
            messages.error(request, "Only the league commissioner can edit settings.")
            return redirect("league_settings", league_id=league.id)
        form = LeagueSettingsForm(request.POST, instance=league)
        if form.is_valid():
            league_obj = form.save(commit=False)
            # Force correct playoff weeks for 4 or 6 playoff teams
            if int(form.cleaned_data.get('playoff_teams', 0)) == 6:
                league_obj.playoff_weeks = 3
            elif int(form.cleaned_data.get('playoff_teams', 0)) == 4:
                league_obj.playoff_weeks = 2
            # For best ball leagues, automatically set roster_size as sum of position allocations
            if league_obj.roster_format == 'bestball':
                league_obj.roster_size = (
                    (league_obj.roster_forwards or 0) +
                    (league_obj.roster_defense or 0) +
                    (league_obj.roster_goalies or 0)
                )
            league_obj.save()
            form.save_m2m() if hasattr(form, 'save_m2m') else None
            
            # Note: Schedule cache has 24-hour TTL and will auto-refresh when settings change
            # This is acceptable since league settings don't change frequently
            
            return redirect("league_detail", league_id=league.id)
        else:
            # Form is not valid - show the errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = LeagueSettingsForm(instance=league)
    
    return render(request, "web/league_settings.html", {
        "form": form,
        "league": league,
        "is_commissioner": is_commissioner,
    })


@login_required
def renew_league(request, league_id):
    """Renew a completed league for the next season with same settings and members"""
    league = get_object_or_404(League, id=league_id)
    
    # Only commissioner can renew
    if league.commissioner != request.user:
        messages.error(request, "Only the league commissioner can renew the league.")
        return redirect("league_detail", league_id=league.id)
    
    # Can only renew archived leagues
    if league.is_active:
        messages.warning(request, "This league is still active. Wait until the season ends to renew.")
        return redirect("league_detail", league_id=league.id)
    
    if request.method == "POST":
        form = LeagueRenewalForm(league=league, data=request.POST)
        if form.is_valid():
            from ..tasks import renew_league as renew_league_task
            
            new_league = renew_league_task(league.id)
            
            if new_league:
                messages.success(
                    request, 
                    f"League renewed successfully! Visit the new league at /leagues/{new_league.id}/"
                )
                return redirect("league_detail", league_id=new_league.id)
            else:
                messages.error(request, "Failed to renew league. Please try again.")
                return redirect("league_detail", league_id=league.id)
    else:
        form = LeagueRenewalForm(league=league)
    
    return render(request, "web/renew_league.html", {
        "league": league,
        "form": form,
        "next_season": timezone.now().year + 1,
    })


@login_required
def team_settings(request, team_id):
    """Team owner settings page (change team name)"""
    team = get_object_or_404(Team, id=team_id)
    
    # Only team owner can access
    if not hasattr(team, 'owner') or team.owner.user != request.user:
        messages.error(request, "Only the team owner can access settings.")
        return redirect('home')
    
    if request.method == 'POST':
        form = TeamSettingsForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, 'Team name updated successfully!')
            return redirect('home')
    else:
        form = TeamSettingsForm(instance=team)
    
    return render(request, 'web/team_settings.html', {
        'team': team,
        'form': form,
    })


@login_required
@login_required
def submit_waiver_claim(request, team_id):
    """Submit a waiver claim for a player"""
    if request.method != 'POST':
        return redirect('team_detail', team_id=team_id)
    
    team = get_object_or_404(Team, id=team_id)
    
    # Check team ownership
    team_owner = FantasyTeamOwner.objects.filter(
        user=request.user,
        team=team
    ).first()
    
    if not team_owner:
        messages.error(request, "You don't have permission to submit waiver claims for this team.")
        return redirect('team_detail', team_id=team.id)
    
    # Check if waivers are enabled
    if not team.league.use_waivers:
        messages.error(request, "Waiver claims are not enabled for this league.")
        return redirect('team_detail', team_id=team.id)
    
    # Get player to add - accept both parameter names for compatibility
    player_id = request.POST.get('player_to_add_id') or request.POST.get('player_id')
    if not player_id:
        messages.error(request, "No player selected.")
        return redirect('team_detail', team_id=team.id)
    
    try:
        player = Player.objects.get(id=int(player_id))
    except Player.DoesNotExist:
        messages.error(request, "Player not found.")
        return redirect('team_detail', team_id=team.id)
    
    # Get player to drop (if any) - accept both parameter names
    drop_player_id = request.POST.get('player_to_drop_id') or request.POST.get('drop_player_id')
    drop_player = None
    if drop_player_id:
        try:
            drop_player = Player.objects.get(id=int(drop_player_id))
        except Player.DoesNotExist:
            pass
    
    # Get current week
    current_week = Week.objects.order_by('-season', '-week_number').first()
    if not current_week:
        messages.error(request, "No active week found.")
        return redirect('team_detail', team_id=team.id)
    
    # Calculate waiver priority (based on reverse standings - worst team gets priority 1)
    # For now, simple implementation based on total points
    standings = []
    for league_team in team.league.teams.all():
        total_points = 0
        for roster_entry in Roster.objects.filter(
            team=league_team,
            league=team.league,
            week_dropped__isnull=True
        ).select_related('player'):
            player_stats = PlayerGameStat.objects.filter(
                player=roster_entry.player
            ).aggregate(
                total=models.Sum('points')
            )
            total_points += player_stats['total'] or 0
        standings.append((league_team.id, total_points))
    
    # Sort by points (ascending - lowest points gets best priority)
    standings.sort(key=lambda x: x[1])
    priority_map = {team_id: idx + 1 for idx, (team_id, _) in enumerate(standings)}
    priority = priority_map.get(team.id, 999)
    
    # Check for existing pending claim for same player
    existing_claim = WaiverClaim.objects.filter(
        team=team,
        player_to_add=player,
        status=WaiverClaim.Status.PENDING
    ).first()
    
    if existing_claim:
        messages.warning(request, f"You already have a pending claim for {player.first_name} {player.last_name}")
        return redirect('team_detail', team_id=team.id)
    
    # Create the waiver claim
    WaiverClaim.objects.create(
        league=team.league,
        team=team,
        player_to_add=player,
        player_to_drop=drop_player,
        week=current_week,
        priority=priority
    )
    
    if drop_player:
        messages.success(request, f"Waiver claim: {player.first_name} {player.last_name} (drop {drop_player.first_name} {drop_player.last_name})")
    else:
        messages.success(request, f"Waiver claim: {player.first_name} {player.last_name}")
    
    return redirect('team_detail', team_id=team.id)


@login_required
def cancel_waiver_claim(request, claim_id):
    """Cancel a pending waiver claim"""
    claim = get_object_or_404(WaiverClaim, id=claim_id)
    
    # Check team ownership
    team_owner = FantasyTeamOwner.objects.filter(
        user=request.user,
        team=claim.team
    ).first()
    
    if not team_owner:
        messages.error(request, "You don't have permission to cancel this claim.")
        return redirect('home')
    
    if claim.status != WaiverClaim.Status.PENDING:
        messages.error(request, "Can only cancel pending claims.")
        return redirect('team_detail', team_id=claim.team.id)
    
    claim.status = WaiverClaim.Status.CANCELLED
    claim.save()
    
    messages.success(request, f"Waiver claim cancelled")
    return redirect('team_detail', team_id=claim.team.id)


@login_required
def draft_room(request):
    """View the draft room for the selected league"""
    selected_league_id = request.session.get('selected_league_id')
    
    if not selected_league_id:
        messages.error(request, "Please select a league first.")
        return redirect('league_list')
    
    league = get_object_or_404(League, id=selected_league_id)
    
    # Get or check draft
    try:
        draft = Draft.objects.prefetch_related(
            'draft_positions__team',
            'picks__team',
            'picks__player'
        ).get(league=league)
    except Draft.DoesNotExist:
        draft = None
    
    # Get user's team in this league
    try:
        owner = FantasyTeamOwner.objects.select_related('team').get(
            user=request.user,
            team__league=league
        )
        user_team = owner.team
    except FantasyTeamOwner.DoesNotExist:
        user_team = None
    
    # Check if user is commissioner
    is_commissioner = league.commissioner == request.user
    
    # Get all teams in league
    teams = Team.objects.filter(league=league).select_related('league')
    team_count = teams.count()
    league_is_full = team_count == league.max_teams

    # Lock draft if any team has players on their roster
    draft_locked = Roster.objects.filter(league=league, week_dropped__isnull=True).exists()

    # Get available players (not on any roster in this league and not drafted)
    drafted_player_ids = []
    if draft:
        drafted_player_ids = list(
            DraftPick.objects.filter(draft=draft, player__isnull=False).values_list('player_id', flat=True)
        )
    
    rostered_player_ids = list(
        Roster.objects.filter(
            league=league,
            week_dropped__isnull=True
        ).values_list('player_id', flat=True)
    )

    excluded_ids = set(drafted_player_ids + rostered_player_ids)
    
    # Get sort parameters
    sort_by = request.GET.get('sort_by', 'prev_year_points')
    sort_dir = request.GET.get('sort_dir', 'desc')
    
    # Map sort fields
    sort_field_map = {
        'name': 'last_name',
        'position': 'position',
        'nll_team': 'nll_team',
        'number': 'number',
        'prev_year_points': 'prev_year_points'
    }
    
    sort_field = sort_field_map.get(sort_by, 'last_name')
    if sort_dir == 'desc':
        sort_field = '-' + sort_field
    
    from django.db.models import Sum, Q, F, Value, FloatField, DecimalField, Case, When
    from django.db.models.functions import Coalesce, Cast
    
    # Calculate fantasy points based on league scoring settings
    # For non-goalies: goals, assists, loose balls, caused turnovers, blocked shots, turnovers
    # For goalies: wins, saves, goals against, goals, assists
    available_players = Player.objects.exclude(
        id__in=excluded_ids
    ).annotate(
        prev_year_points=Coalesce(
            Sum(
                Case(
                    # For goalies (position G)
                    When(
                        position='G',
                        then=(
                            F('game_stats__wins') * league.scoring_goalie_wins +
                            F('game_stats__saves') * league.scoring_goalie_saves +
                            F('game_stats__goals_against') * league.scoring_goalie_goals_against +
                            F('game_stats__goals') * league.scoring_goalie_goals +
                            F('game_stats__assists') * league.scoring_goalie_assists
                        )
                    ),
                    # For non-goalies
                    default=(
                        F('game_stats__goals') * league.scoring_goals +
                        F('game_stats__assists') * league.scoring_assists +
                        F('game_stats__loose_balls') * league.scoring_loose_balls +
                        F('game_stats__caused_turnovers') * league.scoring_caused_turnovers +
                        F('game_stats__blocked_shots') * league.scoring_blocked_shots +
                        F('game_stats__turnovers') * league.scoring_turnovers
                    ),
                    output_field=FloatField()
                ),
                filter=Q(game_stats__game__week__season=2025)
            ),
            Value(0.0),
            output_field=FloatField()
        )
    ).order_by(sort_field, 'last_name', 'first_name')
    
    # Get current pick team
    current_team = None
    is_user_turn = False
    if draft and draft.is_active:
        current_team = draft.get_current_team()
        if current_team and user_team:
            is_user_turn = current_team.id == user_team.id
    
    # Get draft board data
    draft_board = []
    if draft:
        draft_positions = draft.get_draft_order()
        for round_num in range(1, draft.total_rounds + 1):
            round_picks = []
            for position in draft_positions:
                # Determine pick number based on draft style
                if draft.draft_style == 'SNAKE':
                    if round_num % 2 == 1:  # Odd round
                        pick_in_round = position.position
                    else:  # Even round
                        pick_in_round = team_count - position.position + 1
                else:  # LINEAR
                    pick_in_round = position.position
                
                # Find the pick
                pick = DraftPick.objects.filter(
                    draft=draft,
                    round=round_num,
                    pick_number=pick_in_round
                ).select_related('team', 'player').first()
                
                round_picks.append({
                    'team': position.team,
                    'pick': pick,
                    'position': pick_in_round,
                })
            
            # Sort picks by position to display top-down consistently
            round_picks.sort(key=lambda x: x['position'])
            
            draft_board.append({
                'round': round_num,
                'picks': round_picks
            })
    
    # Get user's draft picks so far
    user_picks = []
    if draft and user_team:
        user_picks = DraftPick.objects.filter(
            draft=draft,
            team=user_team,
            player__isnull=False
        ).select_related('player').order_by('round', 'pick_number')
    
    # Get future picks organized by year
    future_picks_by_year = {}
    if getattr(league, 'use_future_rookie_picks', False):
        from ..models import FutureRookiePick
        future_picks = FutureRookiePick.objects.filter(league=league).select_related(
            'team', 'original_owner'
        ).order_by('year', 'round_number', 'pick_number')
        
        for pick in future_picks:
            if pick.year not in future_picks_by_year:
                future_picks_by_year[pick.year] = []
            future_picks_by_year[pick.year].append(pick)
    
    context = {
        'league': league,
        'draft': draft,
        'user_team': user_team,
        'is_commissioner': is_commissioner,
        'teams': teams,
        'team_count': team_count,
        'league_is_full': league_is_full,
        'available_players': available_players,
        'current_team': current_team,
        'is_user_turn': is_user_turn,
        'draft_board': draft_board,
        'sort_by': sort_by,
        'sort_dir': sort_dir,
        'user_picks': user_picks,
        'draft_locked': draft_locked,
        'future_picks_by_year': future_picks_by_year,
    }
    
    return render(request, 'web/draft_room.html', context)


@login_required
def draft_settings(request):
    """View to configure draft settings (future picks for dynasty, basic settings for redraft)"""
    selected_league_id = request.session.get('selected_league_id')
    
    if not selected_league_id:
        messages.error(request, "Please select a league first.")
        return redirect('league_list')
    
    league = get_object_or_404(League, id=selected_league_id)
    draft = getattr(league, 'draft', None)
    
    # For redraft leagues: only allow access before draft starts
    # For dynasty leagues: always allow access
    if league.league_type != 'dynasty' and draft and draft.is_active:
        messages.error(request, "Draft settings cannot be modified after the draft has started.")
        return redirect('draft_room')
    
    # Check if user is commissioner (for POST requests)
    is_commissioner = league.commissioner == request.user
    
    if request.method == 'POST':
        # Only commissioner can modify settings
        if not is_commissioner:
            messages.error(request, "Only the commissioner can modify draft settings.")
            return redirect('draft_room')
        
        # Handle dynasty league future picks
        if league.league_type == 'dynasty':
            from ..forms import DraftSettingsForm
            form = DraftSettingsForm(request.POST, league=league)
            if form.is_valid():
                years_ahead = form.cleaned_data['years_ahead']
                num_rounds = form.cleaned_data['num_rounds']
                
                # Update draft total_rounds if draft exists
                if draft:
                    draft.total_rounds = num_rounds
                    draft.save()
                    logger.info(f"Updated draft rounds to {num_rounds} for {league.name}")
                
                # Delete existing future picks and recreate with new settings
                from ..models import FutureRookiePick
                FutureRookiePick.objects.filter(league=league).delete()
                
                # Create future picks with new settings
                from ..tasks import create_future_rookie_picks
                success, message, picks_created = create_future_rookie_picks(
                    league.id,
                    years_ahead=years_ahead,
                    num_rounds=num_rounds
                )
                
                if success:
                    post_league_message(league, f"📋 Commissioner updated draft settings: {years_ahead} years of picks, {num_rounds} rounds each")
                else:
                    messages.error(request, f"✘ Error updating settings: {message}")
                
                return redirect('draft_room')
        else:
            # Handle redraft league draft configuration
            if draft and not draft.is_active:
                total_rounds = request.POST.get('total_rounds')
                if total_rounds:
                    try:
                        draft.total_rounds = int(total_rounds)
                        draft.save()
                        messages.success(request, f"Draft rounds updated to {total_rounds}")
                        post_league_message(league, f"📋 Commissioner updated draft rounds to {total_rounds}")
                    except (ValueError, TypeError):
                        messages.error(request, "Invalid number of rounds")
            
            return redirect('draft_room')
    else:
        form = None
        if league.league_type == 'dynasty':
            from ..forms import DraftSettingsForm
            form = DraftSettingsForm(league=league)
    
    return render(request, 'web/draft_settings.html', {
        'league': league,
        'form': form,
        'draft': draft,
        'is_commissioner': is_commissioner,
    })


@login_required
@require_POST
def reorder_draft_picks(request):
    """Commissioner endpoint to manually reorder draft picks"""
    selected_league_id = request.session.get('selected_league_id')
    
    if not selected_league_id:
        return JsonResponse({'success': False, 'error': 'Please select a league first.'}, status=400)
    
    league = get_object_or_404(League, id=selected_league_id)
    
    # Check if user is commissioner
    if league.commissioner != request.user:
        return JsonResponse({'success': False, 'error': 'Only the commissioner can reorder picks.'}, status=403)
    
    # Get new order from request
    try:
        import json
        data = json.loads(request.body)
        new_team_order = data.get('team_order', [])
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid request format.'}, status=400)
    
    if not new_team_order or len(new_team_order) == 0:
        return JsonResponse({'success': False, 'error': 'No teams provided.'}, status=400)
    
    # Get draft
    draft = getattr(league, 'draft', None)
    if not draft:
        return JsonResponse({'success': False, 'error': 'No draft exists for this league.'}, status=400)
    
    # Check if draft has started
    if draft.is_active:
        return JsonResponse({'success': False, 'error': 'Cannot reorder picks - draft is already in progress.'}, status=400)
    
    # Reorder using task function
    from ..tasks import reorder_rookie_draft_picks
    success, message = reorder_rookie_draft_picks(draft.id, new_team_order)

    if success:
        messages.success(request, message)
        post_league_message(league, f"📋 Commissioner reordered draft picks")
    else:
        messages.error(request, message)
    
    return JsonResponse({'success': success, 'message': message})


@login_required
@require_POST
def make_draft_pick(request, draft_id):
    """Make a draft pick (handles both regular and rookie drafts)"""
    # First try to get as a regular draft, then as a rookie draft
    draft = None
    is_rookie_draft = False
    
    try:
        draft = Draft.objects.get(id=draft_id)
    except Draft.DoesNotExist:
        try:
            from ..models import RookieDraft
            draft = RookieDraft.objects.get(id=draft_id)
            is_rookie_draft = True
        except RookieDraft.DoesNotExist:
            messages.error(request, "Draft not found.")
            return redirect('draft_room')
    
    # Get user's team
    try:
        owner = FantasyTeamOwner.objects.select_related('team').get(
            user=request.user,
            team__league=draft.league
        )
        user_team = owner.team
    except FantasyTeamOwner.DoesNotExist:
        messages.error(request, "You don't have a team in this league.")
        return redirect('draft_room')
    
    # Check if draft is active
    if not draft.is_active or draft.completed:
        messages.error(request, "Draft is not currently active.")
        return redirect('draft_room')
    
    # Check if it's user's turn
    current_team = draft.get_current_team()
    if not current_team or current_team.id != user_team.id:
        messages.error(request, "It's not your turn to pick.")
        return redirect('draft_room')
    
    # Get selected player
    player_id = request.POST.get('player_id')
    if not player_id:
        messages.error(request, "Please select a player.")
        return redirect('draft_room')
    
    player = get_object_or_404(Player, id=player_id)
    
    # Get the current pick and update it
    if is_rookie_draft:
        from ..models import RookieDraftPick
        # Check if player is already drafted
        if RookieDraftPick.objects.filter(draft=draft, player=player).exists():
            messages.error(request, "Player has already been drafted.")
            return redirect('draft_room')
        
        # Check if player is already on a roster or taxi squad
        if Roster.objects.filter(league=draft.league, player=player, week_dropped__isnull=True).exists():
            messages.error(request, "Player is already on a roster.")
            return redirect('draft_room')
        from ..models import TaxiSquad
        if TaxiSquad.objects.filter(team__league=draft.league, player=player).exists():
            messages.error(request, "Player is already in a taxi squad.")
            return redirect('draft_room')
        
        # Get the current pick
        current_pick = RookieDraftPick.objects.filter(
            draft=draft,
            round=draft.current_round,
            team=user_team
        ).first()
        
        if not current_pick:
            messages.error(request, "Could not find current pick.")
            return redirect('draft_room')
        
        # Make the pick
        current_pick.player = player
        current_pick.save()
    else:
        # Regular draft logic
        # Check if player is already drafted
        if DraftPick.objects.filter(draft=draft, player=player).exists():
            messages.error(request, "Player has already been drafted.")
            return redirect('draft_room')
        
        # Check if player is already on a roster
        if Roster.objects.filter(league=draft.league, player=player, week_dropped__isnull=True).exists():
            messages.error(request, "Player is already on a roster.")
            return redirect('draft_room')
        
        # Get the current pick
        current_pick = DraftPick.objects.filter(
            draft=draft,
            round=draft.current_round,
            team=user_team
        ).first()
        
        if not current_pick:
            messages.error(request, "Could not find current pick.")
            return redirect('draft_room')
        
        # Make the pick
        current_pick.player = player
        current_pick.save()
    
    # Advance to next pick
    draft.advance_pick()
    
    # If draft is complete, add all players to rosters (or taxi squad for rookie drafts)
    if draft.completed:
        if is_rookie_draft:
            from ..models import RookieDraftPick, TaxiSquad
            all_picks = RookieDraftPick.objects.filter(draft=draft, player__isnull=False).select_related('team', 'player')
            
            # Check if taxi squad is enabled for this league
            if draft.league.use_taxi_squad:
                # Add rookie draft picks to taxi squad
                for pick in all_picks:
                    # Find or create empty taxi squad slot
                    taxi_entry = TaxiSquad.objects.filter(team=pick.team, player__isnull=True).first()
                    if not taxi_entry:
                        # Get next available slot number
                        max_slot = TaxiSquad.objects.filter(team=pick.team).aggregate(models.Max('slot_number'))['slot_number__max'] or 0
                        if max_slot < (draft.league.taxi_squad_size if hasattr(draft.league, 'taxi_squad_size') else 3):
                            taxi_entry = TaxiSquad.objects.create(
                                team=pick.team,
                                slot_number=max_slot + 1,
                                player=pick.player
                            )
                        else:
                            post_league_message(draft.league, f"âš ï¸ Draft error: {pick.team.name} taxi squad is full")
                            messages.error(request, f"Draft error: taxi squad full for {pick.team.name}")
                            return redirect('draft_room')
                    else:
                        taxi_entry.player = pick.player
                        taxi_entry.save()
                
                post_league_message(draft.league, f"ðŸŽ‰ Rookie draft completed! All rookies have been added to taxi squads.")
            else:
                # Add rookie draft picks to main roster (taxi squad disabled)
                for pick in all_picks:
                    # Check total roster capacity
                    current_roster_count = Roster.objects.filter(
                        team=pick.team,
                        league=draft.league,
                        week_dropped__isnull=True
                    ).count()
                    
                    if current_roster_count >= draft.league.roster_size:
                        post_league_message(draft.league, f"âš ï¸ Draft error: {pick.team.name} roster would exceed capacity")
                        messages.error(request, f"Draft error: roster capacity exceeded for {pick.team.name}")
                        return redirect('draft_room')
                    
                    # Check position-specific capacity
                    player_position = pick.player.assigned_side if pick.player.assigned_side else pick.player.position
                    can_add, current_pos_count, max_pos_slots = check_roster_capacity(pick.team, player_position)
                    if not can_add:
                        pos_name = {'O': 'Offence', 'D': 'Defence', 'G': 'Goalie'}.get(player_position, 'Unknown')
                        post_league_message(draft.league, f"âš ï¸ Draft error: {pick.team.name} {pos_name} roster full")
                        messages.error(request, f"Draft error: {pos_name} roster full for {pick.team.name}")
                        return redirect('draft_room')
                    
                    draft_roster = Roster.objects.create(
                        team=pick.team,
                        player=pick.player,
                        league=draft.league,
                        week_added=1  # Assume draft happens before season
                    )
                    # Auto-assign to starter slot if traditional league
                    auto_assign_to_starter_slot(draft_roster)
                
                post_league_message(draft.league, f"ðŸŽ‰ Rookie draft completed! All rookies have been added to rosters.")
            
            messages.success(request, f"You selected {player.first_name} {player.last_name}!")
        else:
            # Add regular draft picks to main roster
            all_picks = DraftPick.objects.filter(draft=draft, player__isnull=False).select_related('team', 'player')
            for pick in all_picks:
                # Check total roster capacity
                current_roster_count = Roster.objects.filter(
                    team=pick.team,
                    league=draft.league,
                    week_dropped__isnull=True
                ).count()
                
                if current_roster_count >= draft.league.roster_size:
                    post_league_message(draft.league, f"âš ï¸ Draft error: {pick.team.name} roster would exceed capacity")
                    messages.error(request, f"Draft error: roster capacity exceeded for {pick.team.name}")
                    return redirect('draft_room')
                
                # Check position-specific capacity
                player_position = pick.player.assigned_side if pick.player.assigned_side else pick.player.position
                can_add, current_pos_count, max_pos_slots = check_roster_capacity(pick.team, player_position)
                if not can_add:
                    pos_name = {'O': 'Offence', 'D': 'Defence', 'G': 'Goalie'}.get(player_position, 'Unknown')
                    post_league_message(draft.league, f"âš ï¸ Draft error: {pick.team.name} {pos_name} roster full")
                    messages.error(request, f"Draft error: {pos_name} roster full for {pick.team.name}")
                    return redirect('draft_room')
                
                draft_roster = Roster.objects.create(
                    team=pick.team,
                    player=pick.player,
                    league=draft.league,
                    week_added=1  # Assume draft happens before season
                )
                # Auto-assign to starter slot if traditional league
                auto_assign_to_starter_slot(draft_roster)
            post_league_message(draft.league, f"ðŸŽ‰ Draft completed! All players have been added to rosters.")
            messages.success(request, f"You selected {player.first_name} {player.last_name}!")
    else:
        post_league_message(draft.league, f"ðŸ“‹ {user_team.name} selected {player.first_name} {player.last_name} (Round {draft.current_round})")
        messages.success(request, f"You selected {player.first_name} {player.last_name}!")
    
    return redirect('draft_room')


@login_required
@require_POST
def set_draft_order(request):
    """Set manual draft order and optionally activate draft (commissioner only)"""
    selected_league_id = request.session.get('selected_league_id')
    
    if not selected_league_id:
        return JsonResponse({'error': 'No league selected'}, status=400)
    
    league = get_object_or_404(League, id=selected_league_id)
    
    # Check if user is commissioner
    if league.commissioner != request.user:
        return JsonResponse({'error': 'Only commissioner can set draft order'}, status=403)
    
    # Get draft (must not be active or completed)
    try:
        draft = Draft.objects.get(league=league)
        if draft.is_active or draft.completed:
            return JsonResponse({'error': 'Cannot change order of active/completed draft'}, status=400)
    except Draft.DoesNotExist:
        return JsonResponse({'error': 'No draft exists'}, status=404)
    
    # Get team order from POST data
    import json
    team_order = json.loads(request.POST.get('team_order', '[]'))
    
    if not team_order:
        return JsonResponse({'error': 'No team order provided'}, status=400)
    
    # Update draft positions
    DraftPosition.objects.filter(draft=draft).delete()
    
    for position, team_id in enumerate(team_order, start=1):
        team = get_object_or_404(Team, id=team_id, league=league)
        DraftPosition.objects.create(
            draft=draft,
            team=team,
            position=position
        )
    
    # Recreate all draft pick slots with new order
    DraftPick.objects.filter(draft=draft).delete()
    
    team_count = len(team_order)
    overall_pick = 1
    for round_num in range(1, draft.total_rounds + 1):
        for pick_num in range(1, team_count + 1):
            # Determine which team picks based on draft style
            if draft.draft_style == 'SNAKE':
                if round_num % 2 == 1:  # Odd round
                    position = pick_num
                else:  # Even round
                    position = team_count - pick_num + 1
            else:  # LINEAR
                position = pick_num
            
            # Find team at this position
            draft_pos = DraftPosition.objects.get(draft=draft, position=position)
            
            DraftPick.objects.create(
                draft=draft,
                round=round_num,
                pick_number=pick_num,
                overall_pick=overall_pick,
                team=draft_pos.team
            )
            overall_pick += 1
    
    # Activate draft if requested
    activate = request.POST.get('activate', 'false') == 'true'
    if activate:
        draft.is_active = True
        draft.started_at = timezone.now()
        draft.save()
        return JsonResponse({'success': True, 'message': 'Draft order set and draft activated!'})
    
    return JsonResponse({'success': True, 'message': 'Draft order updated'})


@login_required
@require_POST
def cancel_draft(request):
    """Cancel an active draft (commissioner only)"""
    selected_league_id = request.session.get('selected_league_id')
    
    if not selected_league_id:
        messages.error(request, "Please select a league first.")
        return redirect('league_list')
    
    league = get_object_or_404(League, id=selected_league_id)
    
    # Check if user is commissioner
    if league.commissioner != request.user:
        messages.error(request, "Only the commissioner can cancel the draft.")
        return redirect('draft_room')
    
    # Get draft
    try:
        draft = Draft.objects.get(league=league)
    except Draft.DoesNotExist:
        messages.error(request, "No draft exists for this league.")
        return redirect('draft_room')
    
    # Check if draft is already completed
    if draft.completed:
        messages.error(request, "Cannot cancel a completed draft.")
        return redirect('draft_room')
    
    # Delete the draft (this will cascade delete positions and picks)
    draft.delete()
    
    post_league_message(league, "âŒ The draft has been cancelled by the commissioner.")
    messages.info(request, "Draft cancelled.")
    return redirect('draft_room')


# ===== Taxi Squad Views (Dynasty Leagues) =====

@login_required
def add_to_taxi(request, team_id):
    """Add a rookie player to taxi squad (only during off-season)"""
    team = get_object_or_404(Team, id=team_id)
    
    # Check if user owns this team
    if not (hasattr(team, 'owner') and team.owner and team.owner.user == request.user):
        messages.error(request, "You don't have permission to modify this team.")
        return redirect('team_detail', team_id=team_id)
    
    # Check if league is dynasty
    if not hasattr(team.league, 'league_type') or team.league.league_type != 'dynasty':
        messages.error(request, "Taxi squad is only available in Dynasty leagues.")
        return redirect('team_detail', team_id=team_id)
    
    # Check if taxi squad is enabled for this league
    if not team.league.use_taxi_squad:
        return redirect('team_detail', team_id=team_id)
    
    # Check if season has started - prevent adding to taxi squad once season starts
    league_season = team.league.created_at.year if team.league.created_at else timezone.now().year
    first_game = Game.objects.filter(season=league_season).order_by('date').first()
    if first_game and timezone.now() >= first_game.date:
        messages.error(request, "Cannot add to taxi squad after season starts. You can only move players FROM taxi squad to main roster during the season.")
        return redirect('team_detail', team_id=team_id)
    
    if request.method == 'POST':
        from ..models import TaxiSquad
        player_id = request.POST.get('player_id')
        slot_number = request.POST.get('slot_number')
        
        if not player_id or not slot_number:
            messages.error(request, "Missing player or slot information.")
            return redirect('team_detail', team_id=team_id)
        
        try:
            player = Player.objects.get(id=int(player_id))
            slot_number = int(slot_number)
        except (Player.DoesNotExist, ValueError):
            messages.error(request, "Invalid player or slot.")
            return redirect('team_detail', team_id=team_id)
        
        # Validate: Only rookies allowed in taxi squad
        if not player.is_rookie:
            messages.error(request, f"{player.get_full_name()} is not a rookie and cannot be added to taxi squad.")
            return redirect('team_detail', team_id=team_id)
        
        # Validate: Player not already on roster
        existing_roster = Roster.objects.filter(
            player=player,
            league=team.league,
            week_dropped__isnull=True
        ).exists()
        if existing_roster:
            messages.error(request, f"{player.get_full_name()} is already on your main roster.")
            return redirect('team_detail', team_id=team_id)
        
        # Validate: Player not already in taxi squad
        if TaxiSquad.objects.filter(team=team, player=player).exists():
            messages.error(request, f"{player.get_full_name()} is already in your taxi squad.")
            return redirect('team_detail', team_id=team_id)
        
        # Get existing slot entry or create new one (keep slots persistent)
        taxi_slot, created = TaxiSquad.objects.get_or_create(
            team=team,
            slot_number=slot_number,
            defaults={'player': player}
        )
        
        if not created and taxi_slot.player is not None:
            messages.error(request, f"Taxi slot {slot_number} is already filled.")
            return redirect('team_detail', team_id=team_id)
        
        # Add to taxi squad
        taxi_slot.player = player
        taxi_slot.save()
        
        messages.success(request, f"{player.get_full_name()} added to taxi squad slot {slot_number}.")
    
    return redirect('team_detail', team_id=team_id)


@login_required
def move_from_taxi(request, team_id):
    """Move a player from taxi squad to main roster"""
    team = get_object_or_404(Team, id=team_id)
    
    # Check if user owns this team
    if not (hasattr(team, 'owner') and team.owner and team.owner.user == request.user):
        messages.error(request, "You don't have permission to modify this team.")
        return redirect('team_detail', team_id=team_id)
    
    # Check if league is dynasty
    if not hasattr(team.league, 'league_type') or team.league.league_type != 'dynasty':
        messages.error(request, "Taxi squad is only available in Dynasty leagues.")
        return redirect('team_detail', team_id=team_id)
    
    # Check if taxi squad is enabled for this league
    if not team.league.use_taxi_squad:
        return redirect('team_detail', team_id=team_id)
    
    if request.method == 'POST':
        from ..models import TaxiSquad
        player_id = request.POST.get('player_id')
        
        if not player_id:
            messages.error(request, "No player specified.")
            return redirect('team_detail', team_id=team_id)
        
        try:
            player = Player.objects.get(id=int(player_id))
        except Player.DoesNotExist:
            messages.error(request, "Player not found.")
            return redirect('team_detail', team_id=team_id)
        
        # Get taxi squad entry
        taxi_entry = TaxiSquad.objects.filter(team=team, player=player).first()
        if not taxi_entry:
            messages.error(request, f"{player.get_full_name()} is not in your taxi squad.")
            return redirect('team_detail', team_id=team_id)
        
        # Check if taxi squad is locked
        if taxi_entry.is_locked:
            messages.error(request, f"Taxi squad is locked. Cannot move {player.get_full_name()}.")
            return redirect('team_detail', team_id=team_id)
        
        # Add to main roster (ALLOW even if over limit)
        league_season = team.league.created_at.year if team.league.created_at else timezone.now().year
        current_week = Week.objects.filter(
            season=league_season,
            start_date__lte=timezone.now().date(),
            end_date__gte=timezone.now().date()
        ).first() or Week.objects.filter(
            season=league_season,
            start_date__gt=timezone.now().date()
        ).order_by('week_number').first()
        
        week_added = current_week.week_number if current_week else 1
        
        taxi_roster = Roster.objects.create(
            team=team,
            player=player,
            league=team.league,
            week_added=week_added,
            slot_assignment='bench'
        )
        # For dynasty taxi squad, may want to auto-assign - but default is bench
        # auto_assign_to_starter_slot(taxi_roster)  # Commented - keep taxi on bench by default
        
        # Clear player from taxi squad but keep the slot
        taxi_entry.player = None
        taxi_entry.save()
        
        # Check if now over roster limit and warn user
        current_count, is_over = team.is_over_roster_limit()
        roster_limit = team.league.roster_size if hasattr(team.league, 'roster_size') else 14
        
        if is_over:
            messages.warning(request, f"{player.get_full_name()} moved to main roster. âš ï¸ Your roster is now OVER the limit ({current_count}/{roster_limit}). You must drop players to get back under the limit.")
        else:
            messages.success(request, f"{player.get_full_name()} moved from taxi squad to main roster.")
    
    return redirect('team_detail', team_id=team_id)


# ===== Password Reset Views =====

class CustomPasswordResetView(PasswordResetView):
    """Custom password reset view with async email task"""
    form_class = PasswordResetForm
    template_name = 'web/password_reset_form.html'
    success_url = reverse_lazy('password_reset_done')
    email_template_name = 'emails/password_reset_email.html'
    subject_template_name = 'emails/password_reset_subject.txt'
    
    def form_valid(self, form):
        """Override to use async email task"""
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        
        email = form.cleaned_data['email']
        users = form.get_users(email)
        
        # Get the request's protocol and domain for correct reset URL
        protocol = 'https' if self.request.is_secure() else 'http'
        domain = self.request.get_host()
        
        for user_obj in users:
            # Generate token using Django's default token generator
            token = default_token_generator.make_token(user_obj)
            uid = urlsafe_base64_encode(force_bytes(user_obj.pk))
            
            # Queue async email task
            send_password_reset_email.delay(
                user_id=user_obj.id,
                uid=uid,
                token=token,
                protocol=protocol,
                domain=domain,
            )
        
        # Return done response instead of calling super()
        # to avoid the default email sending
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(self.get_success_url())


class CustomPasswordResetDoneView(PasswordResetDoneView):
    """Confirmation page after password reset email is sent"""
    template_name = 'web/password_reset_done.html'


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    """View for entering new password after clicking reset link"""
    form_class = SetPasswordForm
    template_name = 'web/password_reset_confirm.html'
    success_url = reverse_lazy('password_reset_complete')


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    """Success page after password has been reset"""
    template_name = 'web/password_reset_complete.html'


def get_available_slots(request, team_id):
    """JSON endpoint returning all players and empty slots for a position that can be swapped with"""
    from django.http import JsonResponse
    import sys
    
    try:
        team = get_object_or_404(Team, id=team_id)
        slot_position = request.GET.get('position', 'O')  # O, D, G, or B (slot position)
        current_player_id = int(request.GET.get('current_player_id', 0))
        
        # Get the league for roster info
        league = team.league
        is_best_ball = league.roster_format == 'bestball'
        is_dynasty = league.league_type == 'dynasty' if hasattr(league, 'league_type') else False
        print(f"DEBUG: get_available_slots called - league={league.name}, is_best_ball={is_best_ball}, is_dynasty={is_dynasty}, current_player_id={current_player_id}", file=sys.stderr)
        
        # First, get the current player to determine what positions they can fill
        current_player = Player.objects.get(id=current_player_id)
        player_position = current_player.position  # O, D, T, or G
        
        # Determine which positions this player can move to
        # O and T players can move to O slots
        # D and T players can move to D slots
        # G and T players can move to G slots
        can_move_to = set()
        if player_position in ['O', 'T']:
            can_move_to.add('O')
        if player_position in ['D', 'T']:
            can_move_to.add('D')
        if player_position in ['G', 'T']:
            # For T players, check if league allows T in G slots
            if player_position == 'G' or league.allow_transition_in_goalies:
                can_move_to.add('G')
        
        # Build the response with sections for each slot type
        response_data = {
            'swap_options': [],  # List of players to swap with
            'empty_slot_options': {}  # Dict: slot_type -> list of slot designations
        }
        
        # Get all roster entries for this team and league (active only)
        all_active_roster = Roster.objects.filter(
            team=team,
            league=league,
            week_dropped__isnull=True
        ).select_related('player')
        
        if is_best_ball:
            print(f"DEBUG: Entering best ball logic for player {current_player_id} with position {player_position}, is_dynasty={is_dynasty}", file=sys.stderr)
            # For best ball leagues, list players that can be swapped based on position compatibility
            # T players can ONLY swap with other T players
            # O players can swap with O and T players
            # D players can swap with D and T players  
            # G players can swap with G and T players
            eligible_positions = set()
            if player_position == 'T':
                # T players only swap with T players
                eligible_positions.add('T')
            elif player_position == 'O':
                # O players can swap with O and T players
                eligible_positions.add('O')
                eligible_positions.add('T')
            elif player_position == 'D':
                # D players can swap with D and T players
                eligible_positions.add('D')
                eligible_positions.add('T')
            elif player_position == 'G':
                # G players can swap with G and T players
                eligible_positions.add('G')
                eligible_positions.add('T')
            
            for roster_entry in all_active_roster:
                if str(roster_entry.player.id) != str(current_player_id) and roster_entry.player.position in eligible_positions:
                    response_data['swap_options'].append({
                        'player_id': roster_entry.player.id,
                        'player_name': f"{roster_entry.player.last_name}, {roster_entry.player.first_name}",
                        'slot_type': roster_entry.player.position,
                        'slot_assignment': roster_entry.slot_assignment
                    })
            
            # For best ball, also show "empty slot" options for eligible positions
            # Only apply capacity limits for dynasty leagues - redraft leagues don't have position restrictions
            if is_dynasty:
                # Count players currently assigned to each position (excluding the current player)
                # Need to count both base position (O, D, G) AND T players assigned to that position
                # Capacity: 3 for O, 3 for D, 1 for G
                
                # Count O position players: pure O players + T players assigned to O
                from django.db.models import Q
                o_count = all_active_roster.exclude(player_id=current_player_id).filter(
                    Q(player__position='O') | Q(player__position='T', player__assigned_side='O')
                ).count()
                
                # Count D position players: pure D players + T players assigned to D
                d_count = all_active_roster.exclude(player_id=current_player_id).filter(
                    Q(player__position='D') | Q(player__position='T', player__assigned_side='D')
                ).count()
                
                # Count G position players: pure G players + T players assigned to G
                g_count = all_active_roster.exclude(player_id=current_player_id).filter(
                    Q(player__position='G') | Q(player__position='T', player__assigned_side='G')
                ).count()
                
                
                print(f"DEBUG best ball (dynasty): player_position={player_position}, o_count={o_count}, d_count={d_count}, g_count={g_count}", file=sys.stderr)
                
                if player_position == 'T':
                    # T players can move to O, D, or G positions - show options only if there are empty slots
                    # But first check if league allows T in G slots
                    print(f"  T player: checking O({o_count}<{league.roster_forwards}), D({d_count}<{league.roster_defense}), G({g_count}<{league.roster_goalies})", file=sys.stderr)
                    if o_count < league.roster_forwards:
                        response_data['empty_slot_options']['O'] = ['O']  # Empty slot exists
                        print(f"    Added O slot option", file=sys.stderr)
                    if d_count < league.roster_defense:
                        response_data['empty_slot_options']['D'] = ['D']  # Empty slot exists
                        print(f"    Added D slot option", file=sys.stderr)
                    if g_count < league.roster_goalies and league.allow_transition_in_goalies:
                        response_data['empty_slot_options']['G'] = ['G']  # Empty slot exists
                        print(f"    Added G slot option", file=sys.stderr)
                    elif g_count < league.roster_goalies:
                        print(f"    G slot would be available but T players not allowed in G slots", file=sys.stderr)
                elif player_position == 'O':
                    # O players can stay in O position if there's an empty slot
                    if o_count < league.roster_forwards:
                        response_data['empty_slot_options']['O'] = ['O']  # Empty slot exists
                elif player_position == 'D':
                    # D players can stay in D position if there's an empty slot
                    if d_count < league.roster_defense:
                        response_data['empty_slot_options']['D'] = ['D']  # Empty slot exists
                elif player_position == 'G':
                    # G players can stay in G position if there's an empty slot
                    if g_count < league.roster_goalies:
                        response_data['empty_slot_options']['G'] = ['G']  # Empty slot exists
            else:
                # For redraft best ball leagues, show all position moves without capacity restrictions
                # Redraft leagues don't enforce position-based roster limits
                # (3-3-1 is only for scoring, not roster capacity)
                print(f"DEBUG best ball (redraft): allowing all position moves", file=sys.stderr)
                if player_position == 'T':
                    # T players can move to O, D, or G - but check if league allows T in G slots
                    response_data['empty_slot_options']['O'] = ['O']
                    response_data['empty_slot_options']['D'] = ['D']
                    if league.allow_transition_in_goalies:
                        response_data['empty_slot_options']['G'] = ['G']
                    print(f"    Added O, D slot options for T player, G={'included' if league.allow_transition_in_goalies else 'excluded'}", file=sys.stderr)
                elif player_position == 'O':
                    # O players can stay in O position
                    response_data['empty_slot_options']['O'] = ['O']
                elif player_position == 'D':
                    # D players can stay in D position
                    response_data['empty_slot_options']['D'] = ['D']
                elif player_position == 'G':
                    # G players can stay in G position
                    response_data['empty_slot_options']['G'] = ['G']
        else:
            # For traditional leagues, find starter slots
            # Only show swap options for players in the SAME slot type (same position)
            # Only show empty slots for other positions the player can move to
            
            # First, determine what slot the moving player is currently in
            player_roster = Roster.objects.filter(
                player=current_player,
                team=team,
                league=league,
                week_dropped__isnull=True
            ).first()
            
            if player_roster:
                current_slot = player_roster.slot_assignment
                # Determine the slot type from the current slot assignment
                if 'starter_o' in current_slot:
                    current_slot_type = 'O'
                elif 'starter_d' in current_slot:
                    current_slot_type = 'D'
                elif 'starter_g' in current_slot:
                    current_slot_type = 'G'
                else:
                    current_slot_type = None
                
                print(f"  Current player in slot: {current_slot}, slot_type: {current_slot_type}")
            else:
                current_slot_type = None
            
            # For each position the player can move to, find swap and empty slot options
            for slot_type in ['O', 'D', 'G']:
                if slot_type not in can_move_to:
                    continue
                
                # Determine slot designations for this type using league configuration
                if slot_type == 'O':
                    num_slots = league.roster_forwards
                    slot_designations = [f'starter_o{i}' for i in range(1, num_slots + 1)]
                    slot_prefix = 'starter_o'
                elif slot_type == 'D':
                    num_slots = league.roster_defense
                    slot_designations = [f'starter_d{i}' for i in range(1, num_slots + 1)]
                    slot_prefix = 'starter_d'
                else:  # G
                    num_slots = league.roster_goalies
                    slot_designations = [f'starter_g{i}' for i in range(1, num_slots + 1)]
                    slot_prefix = 'starter_g'
                
                # Get players currently in these slots
                roster_in_slots = all_active_roster.filter(
                    slot_assignment__in=slot_designations
                ).order_by('slot_assignment')
                
                print(f"  {slot_type} slots: found {roster_in_slots.count()} players")
                
                # Add swap options based on player position and current location
                # Case 1: Player is in a starter slot - can swap within same position
                if slot_type == current_slot_type:
                    for roster_entry in roster_in_slots:
                        if str(roster_entry.player.id) != str(current_player_id):
                            response_data['swap_options'].append({
                                'player_id': roster_entry.player.id,
                                'player_name': f"{roster_entry.player.last_name}, {roster_entry.player.first_name}",
                                'slot_type': slot_type,
                                'slot_assignment': roster_entry.slot_assignment
                            })
                            print(f"    Swap option: {roster_entry.player.last_name} in {roster_entry.slot_assignment}")
                # Case 2: T players can swap with other T players in any position group
                elif current_player.position == 'T':
                    for roster_entry in roster_in_slots:
                        if str(roster_entry.player.id) != str(current_player_id) and roster_entry.player.position == 'T':
                            response_data['swap_options'].append({
                                'player_id': roster_entry.player.id,
                                'player_name': f"{roster_entry.player.last_name}, {roster_entry.player.first_name}",
                                'slot_type': slot_type,
                                'slot_assignment': roster_entry.slot_assignment
                            })
                            print(f"    Swap option (T-T cross-group): {roster_entry.player.last_name} in {roster_entry.slot_assignment}")
                # Case 3: Bench players can swap with any position they're moving to
                elif current_slot_type is None:
                    for roster_entry in roster_in_slots:
                        if str(roster_entry.player.id) != str(current_player_id):
                            response_data['swap_options'].append({
                                'player_id': roster_entry.player.id,
                                'player_name': f"{roster_entry.player.last_name}, {roster_entry.player.first_name}",
                                'slot_type': slot_type,
                                'slot_assignment': roster_entry.slot_assignment
                            })
                            print(f"    Swap option (from bench): {roster_entry.player.last_name} in {roster_entry.slot_assignment}")
                else:
                    print(f"  Skipping {slot_type} slots for swap options (current player in {current_slot_type})")
                
                # Find empty slots for this type
                # Only show them if empty slots actually exist for this position
                empty_slots = []
                
                # Find which slots are filled
                filled_slot_numbers = set()
                for roster_entry in roster_in_slots:
                    slot_assign = roster_entry.slot_assignment
                    if slot_type == 'G' and slot_assign == 'starter_g':
                        filled_slot_numbers.add(1)
                    elif slot_assign.startswith(slot_prefix) and len(slot_assign) > len(slot_prefix):
                        try:
                            slot_num = int(slot_assign[len(slot_prefix):])
                            filled_slot_numbers.add(slot_num)
                        except ValueError:
                            pass
                
                # Add empty slots only if they exist
                for i in range(1, num_slots + 1):
                    if i not in filled_slot_numbers:
                        if slot_type == 'G':
                            slot_designation = 'starter_g'
                        else:
                            slot_designation = f"{slot_prefix}{i}"
                        empty_slots.append(slot_designation)
                
                response_data['empty_slot_options'][slot_type] = empty_slots
            
            # Also check if bench is available (always available as a move destination)
            bench_count = all_active_roster.filter(slot_assignment='bench').count()
            # Bench is always available as a destination
            if 'bench' not in response_data['empty_slot_options']:
                response_data['empty_slot_options']['Bench'] = ['bench']
        
        print(f"DEBUG: Returning response_data: {response_data}", file=sys.stderr)
        print(f"DEBUG: Returning {len(response_data['swap_options'])} swap options, empty_slot_options={response_data.get('empty_slot_options', {})}", file=sys.stderr)
        return JsonResponse(response_data)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
