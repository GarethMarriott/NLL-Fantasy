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
import pytz

from .models import Player, Team, Week, Game, ChatMessage, FantasyTeamOwner, League, Roster, PlayerGameStat, WaiverClaim, Draft, DraftPosition, DraftPick, Trade, TradePlayer
from .forms import UserRegistrationForm, LeagueCreateForm, TeamCreateForm, LeagueSettingsForm, TeamSettingsForm, PasswordResetForm, SetPasswordForm
from .tasks import send_password_reset_email
from django.views.decorators.http import require_POST


# NLL Team abbreviations mapping
TEAM_ABBREVIATIONS = {
    "Toronto Rock": "TOR",
    "Calgary Roughnecks": "CGY",
    "Saskatchewan Rush": "SAS",
    "Winnipeg MIL": "WIN",
    "Buffalo Bandits": "BUF",
    "New York Riptide": "NYR",
    "Vancouver Warriors": "VAN",
    "Edmonton Oil Kings": "EDM",
    "Ottawa Black Bears": "OTT",
    "Panther City Lacrosse Club": "PAN",
    "Las Vegas Desert Dogs": "LV",
    "Oshawa FireWolves": "OSH",
    "Halifax Thunderbirds": "HAL",
    "Rochester Knighthawks": "ROC",
}


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
        'O': team.league.roster_forwards,
        'D': team.league.roster_defense,
        'G': team.league.roster_goalies
    }
    max_allowed = max_slots.get(position, 0)
    
    return position_count < max_allowed, position_count, max_allowed


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
    
    # Find the week we're currently in or just finished
    # This is the week whose start_date has passed
    # Cache all weeks for the season to avoid multiple queries
    all_weeks_for_season = Week.objects.filter(season=league_season).order_by('week_number')
    
    current_date = timezone.now().date()
    current_time = timezone.now()
    
    # First priority: Use league's current_week if it's set (updated automatically every Monday 9am PT)
    if league.current_week:
        default_week_num = league.current_week.week_number
    else:
        # Fallback: Find the currently active week (games in progress)
        # This is where start_date <= now <= end_date
        current_active_week = Week.objects.filter(
            season=league_season,
            start_date__lte=current_date,
            end_date__gte=current_date
        ).order_by('week_number').first()
        
        # Determine default week to display
        if current_active_week:
            # Show the active week (games in progress)
            default_week_num = current_active_week.week_number
        else:
            # No active week - show the most recently completed week
            most_recent_week = Week.objects.filter(
                season=league_season,
                start_date__lte=current_date
            ).order_by('-week_number').first()
            
            if most_recent_week:
                default_week_num = most_recent_week.week_number
            else:
                # No past weeks - fall back to first future week
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
    
    print(f"DEBUG team_detail: selected_week_num={selected_week_num}, default_week_num={default_week_num}")
    
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
    # Best-ball fantasy scoring derived from the raw stat fields
    def fantasy_points(stat_obj, player=None):
        if stat_obj is None:
            return None
        # Goalie scoring using league settings
        if player and player.position == "G":
            return (
                stat_obj.wins * float(league.scoring_goalie_wins)
                + stat_obj.saves * float(league.scoring_goalie_saves)
                + stat_obj.goals_against * float(league.scoring_goalie_goals_against)
                + stat_obj.goals * float(league.scoring_goalie_goals)
                + stat_obj.assists * float(league.scoring_goalie_assists)
            )
        # Field player scoring using league settings
        return (
            stat_obj.goals * float(league.scoring_goals)
            + stat_obj.assists * float(league.scoring_assists)
            + stat_obj.loose_balls * float(league.scoring_loose_balls)
            + stat_obj.caused_turnovers * float(league.scoring_caused_turnovers)
            + stat_obj.blocked_shots * float(league.scoring_blocked_shots)
            + stat_obj.turnovers * float(league.scoring_turnovers)
        )

    # determine most recent season available for weekly breakdown
    recent_week = Week.objects.order_by("-season", "-week_number").first()
    season = recent_week.season if recent_week else None

    # Keep players in order of when they were (last) assigned, not alphabetically
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
    
    for roster_entry in roster:
        p = roster_entry.player
        # Use per-game stats
        game_stats = list(p.game_stats.filter(game__week__season=season)) if season is not None else []
        # Find latest stat (most recent game)
        latest = max(game_stats, key=lambda s: (s.game.date, s.game.id), default=None)

        # Group PlayerGameStat objects by week_number for this player/season
        stats_by_week = {}
        for s in game_stats:
            wk_num = s.game.week.week_number
            stats_by_week.setdefault(wk_num, []).append(s)

        weekly_points = []
        total_points = 0
        for wk in range(1, 19):
            stats_list = stats_by_week.get(wk, [])
            if not stats_list:
                weekly_points.append(None)
                continue
            pts_list = [fantasy_points(st, p) for st in stats_list if st is not None]
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
        if p.nll_team:
            # Map team names to team IDs
            team_name_to_id = {
                "Vancouver Warriors": "867",
                "San Diego Seals": "868",
                "Colorado Mammoth": "870",
                "Calgary Roughnecks": "874",
                "Saskatchewan Rush": "879",
                "Philadelphia Wings": "880",
                "Buffalo Bandits": "888",
                "Georgia Swarm": "890",
                "Toronto Rock": "896",
                "Halifax Thunderbirds": "912",
                "Panther City Lacrosse Club": "913",
                "Albany FireWolves": "914",
                "Las Vegas Desert Dogs": "915",
                "New York Riptide": "911",
                "Ottawa Black Bears": "917",
                "Oshawa FireWolves": "918",
                "Rochester Knighthawks": "910",
            }
            player_team_id = team_name_to_id.get(p.nll_team)
            if player_team_id:
                # Find the game for this week
                game = Game.objects.filter(
                    week__week_number=selected_week_num,
                    week__season=league_season
                ).filter(
                    Q(home_team=player_team_id) | Q(away_team=player_team_id)
                ).first()
                if game:
                    # Map IDs back to team names
                    team_id_to_name = {
                        "867": "Vancouver Warriors",
                        "868": "San Diego Seals",
                        "870": "Colorado Mammoth",
                        "874": "Calgary Roughnecks",
                        "879": "Saskatchewan Rush",
                        "880": "Philadelphia Wings",
                        "888": "Buffalo Bandits",
                        "890": "Georgia Swarm",
                        "896": "Toronto Rock",
                        "910": "Rochester Knighthawks",
                        "911": "New York Riptide",
                        "912": "Halifax Thunderbirds",
                        "913": "Panther City Lacrosse Club",
                        "914": "Albany FireWolves",
                        "915": "Las Vegas Desert Dogs",
                        "917": "Ottawa Black Bears",
                        "918": "Oshawa FireWolves",
                    }
                    opponent = f"{team_id_to_name.get(game.home_team, game.home_team)} @ {team_id_to_name.get(game.away_team, game.away_team)}"
        
        entry = {"player": p, "latest_stat": latest, "weekly_points": weekly_points, "weeks_total": total_points, "counts_for_total": [False] * 18, "selected_week_points": weekly_points[selected_week_num - 1] if selected_week_num <= len(weekly_points) else None, "opponent": opponent}

        pos = getattr(p, "position", None)
        side = getattr(p, "assigned_side", None)
        target = side or ("O" if pos == "T" else pos)
        if target in players_by_position:
            players_by_position[target].append(entry)
        else:
            players_by_position["O"].append(entry)

    # Build slots - T players are already placed in their target pool by assigned_side
    offence_pool = players_by_position["O"]
    defence_pool = players_by_position["D"]
    goalie_pool = players_by_position["G"]

    offence_slots = offence_pool[:6]
    defence_slots = defence_pool[:6]
    goalie_slots = goalie_pool[:2]

    while len(offence_slots) < 6:
        offence_slots.append(None)
    while len(defence_slots) < 6:
        defence_slots.append(None)
    while len(goalie_slots) < 2:
        goalie_slots.append(None)

    # For traditional leagues, mark which players are starters and separate them
    is_traditional = league.roster_format == 'traditional'
    if is_traditional:
        # Get roster entries with slot assignments
        roster_with_slots = team.roster_entries.select_related('player').filter(
            Q(week_dropped__isnull=True) | Q(week_dropped__gt=selected_week_num),
            player__active=True
        ).filter(
            Q(week_added__isnull=True) | Q(week_added__lte=selected_week_num)
        )
        
        # Create a mapping of player_id to slot_assignment
        player_to_slot = {entry.player_id: entry.slot_assignment for entry in roster_with_slots}
        
        # Mark starter status on each slot
        for slot_group in [offence_slots, defence_slots, goalie_slots]:
            for slot in slot_group:
                if slot:
                    player_id = slot['player'].id
                    slot_assignment = player_to_slot.get(player_id, 'bench')
                    slot['is_starter'] = slot_assignment.startswith('starter_') if slot_assignment else False
                    slot['slot_assignment'] = slot_assignment
    else:
        # For best ball, all players are "starters" (all count)
        for slot_group in [offence_slots, defence_slots, goalie_slots]:
            for slot in slot_group:
                if slot:
                    slot['is_starter'] = True
                    slot['slot_assignment'] = 'bestball'

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
        # Get the 3 assigned offense starters
        starter_offense = [slot for slot in offence_slots if slot and slot.get('is_starter')][:3]
        starter_defense = [slot for slot in defence_slots if slot and slot.get('is_starter')][:3]
        starter_goalie = [slot for slot in goalie_slots if slot and slot.get('is_starter')][:1]
        
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
            # For traditional, sum all starter scores across all weeks
            starter_offense_all = [slot for slot in offence_slots if slot and slot.get('is_starter') and slot.get("weekly_points") and week_idx_all < len(slot["weekly_points"]) and slot["weekly_points"][week_idx_all] is not None][:3]
            starter_defense_all = [slot for slot in defence_slots if slot and slot.get('is_starter') and slot.get("weekly_points") and week_idx_all < len(slot["weekly_points"]) and slot["weekly_points"][week_idx_all] is not None][:3]
            starter_goalie_all = [slot for slot in goalie_slots if slot and slot.get('is_starter') and slot.get("weekly_points") and week_idx_all < len(slot["weekly_points"]) and slot["weekly_points"][week_idx_all] is not None][:1]
            
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
            'players__player', 'players__from_team'
        ).order_by('-created_at')
        pending_changes_count = pending_waiver_claims.count() + pending_trades.count()
    else:
        pending_waiver_claims = []
        pending_trades = []
        pending_changes_count = 0
    use_waivers = team.league.use_waivers if hasattr(team.league, 'use_waivers') else False

    # Get taxi squad for dynasty leagues
    taxi_squad_entries = []
    is_dynasty = league.league_type == 'dynasty' if hasattr(league, 'league_type') else False
    if is_dynasty:
        from web.models import TaxiSquad
        taxi_squad_entries = list(TaxiSquad.objects.filter(team=team).select_related('player').order_by('slot_number'))
    
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
            "week_range": [selected_week_num],  # Only show selected week
            "selected_week": selected_week_num,
            "selected_week_obj": selected_week_obj,
            "available_weeks": available_weeks,
            "current_week": default_week_num,
            "selected_week_total": selected_week_total,
            "overall_total": overall_total,
            "players_for_select": players_with_teams,
            "roster_status": team.can_make_roster_changes(),
            "is_viewing_past_week": is_viewing_past_week,
            "pending_waiver_claims": pending_waiver_claims,
            "pending_trades": pending_trades,
            "pending_changes_count": pending_changes_count,
            "use_waivers": use_waivers,
            "is_traditional": is_traditional,
            "is_dynasty": is_dynasty,
            "taxi_squad_entries": taxi_squad_entries,
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
        
        if starter_slots != 7:
            messages.error(request, "You must have exactly 7 starters (3 Offense, 3 Defense, 1 Goalie).")
            return redirect('manage_lineup', team_id=team_id)
        
        messages.success(request, "Lineup updated successfully!")
        return redirect('team_detail', team_id=team_id)
    
    # GET request - show lineup management page
    roster_items = Roster.objects.filter(team=team).select_related('player')
    
    # Separate players by slot assignment
    starter_offense = roster_items.filter(slot_assignment__in=['starter_o1', 'starter_o2', 'starter_o3'])
    starter_defense = roster_items.filter(slot_assignment__in=['starter_d1', 'starter_d2', 'starter_d3'])
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
    print(f"DEBUG assign_player: action={action}, player_id={player_id}")
    
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
        Roster.objects.create(
            player=player,
            team=team,
            league=team.league,
            week_added=next_week_number
        )
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
        
        messages.success(request, f"Swapped {drop_player.first_name} {drop_player.last_name} for {player.first_name} {player.last_name}")
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
    elif action == "drop":
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


def get_player_upcoming_schedule(player, num_weeks=10):
    """
    Get the upcoming schedule for a player.
    
    Returns a list of tuples (week_number, game_count, nll_team_list) for upcoming weeks.
    If a player has no games that week, game_count will be 0 (bye week).
    """
    from django.utils import timezone
    
    today = timezone.now().date()
    schedule = []
    
    try:
        # Get upcoming weeks
        weeks = Week.objects.filter(
            start_date__gte=today
        ).order_by('week_number')[:num_weeks]
        
        for week in weeks:
            # Get games for this week where the player's NLL team plays
            if player.nll_team:
                games = Game.objects.filter(
                    Q(week=week) &
                    (Q(home_team=player.nll_team) | Q(away_team=player.nll_team))
                )
                game_count = games.count()
                
                # Collect opponent teams
                opponent_teams = set()
                for game in games:
                    if game.home_team == player.nll_team:
                        opponent_teams.add(game.away_team)
                    else:
                        opponent_teams.add(game.home_team)
                
                schedule.append({
                    'week_number': week.week_number,
                    'game_count': game_count,
                    'opponents': list(opponent_teams) if opponent_teams else []
                })
            else:
                # Player has no NLL team assigned
                schedule.append({
                    'week_number': week.week_number,
                    'game_count': 0,
                    'opponents': []
                })
    except Exception:
        # If there's any error, return empty schedule
        pass
    
    return schedule


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
    
    # Add schedule data to each player in all rosters
    for roster_entry in user_roster:
        roster_entry.player.upcoming_schedule = get_player_upcoming_schedule(roster_entry.player, num_weeks=5)
    
    for other_team in other_teams:
        for roster_entry in other_team.roster_entries.all():
            roster_entry.player.upcoming_schedule = get_player_upcoming_schedule(roster_entry.player, num_weeks=5)
    
    context = {
        'team': team,
        'league': league,
        'other_teams': other_teams,
        'user_roster': user_roster,
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
    
    # Get player IDs from the request
    import json
    your_player_ids = json.loads(request.POST.get('your_players', '[]'))
    their_player_ids = json.loads(request.POST.get('their_players', '[]'))
    
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
    
    if your_players.count() != len(your_player_ids) or their_players.count() != len(their_player_ids):
        messages.error(request, "Invalid player selection. Please try again.")
        return redirect("trade_center", team_id=team.id)
    
    if your_players.count() == 0 or their_players.count() == 0:
        messages.error(request, "You must select at least one player from each team.")
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
    
    # Post message to team chat
    your_players_str = ", ".join([f"{p.first_name} {p.last_name}" for p in your_players])
    their_players_str = ", ".join([f"{p.first_name} {p.last_name}" for p in their_players])
    message = f"Trade proposed: {team.name} receives ({their_players_str}) and {target_team.name} receives ({your_players_str})"
    post_team_chat_message(team, target_team, message, 
                          message_type='TRADE_PROPOSED', 
                          trade=trade, 
                          sender=request.user)
    
    messages.success(request, f"Trade proposal sent to {target_team.name}!")
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
    
    if not next_week:
        return False, "No future week available for trade execution"
    
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
        Roster.objects.create(
            team=to_team,
            player=player,
            league=trade.league,
            week_added=week_number
        )
    
    # Mark trade as executed
    trade.executed_at = timezone.now()
    trade.save()
    
    # Post notification to league chat
    proposing_players = trade.players.filter(from_team=trade.proposing_team)
    receiving_players = trade.players.filter(from_team=trade.receiving_team)
    
    proposing_names = ", ".join([f"{p.player.first_name} {p.player.last_name}" for p in proposing_players])
    receiving_names = ", ".join([f"{p.player.first_name} {p.player.last_name}" for p in receiving_players])
    
    message_text = f"🤝 Trade completed! {trade.proposing_team.name} receives ({receiving_names}) and {trade.receiving_team.name} receives ({proposing_names})"
    post_league_message(trade.league, message_text)
    
    return True, "Trade executed successfully"


@require_POST
def accept_trade(request, trade_id):
    """Accept a trade offer"""
    from django.utils import timezone
    from web.models import Week
    
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
    
    # Check if current week is locked (rosters locked during games)
    league_season = trade.league.created_at.year if trade.league.created_at else timezone.now().year
    current_week = Week.objects.filter(
        season=league_season,
        start_date__lte=timezone.now().date()
    ).order_by('-week_number').first()
    
    is_locked = current_week and current_week.is_locked()
    
    # Update trade status
    if is_locked:
        # Rosters are locked - trade will execute when rosters unlock (Monday 9 AM)
        trade.status = Trade.Status.ACCEPTED
        trade.save()
        
        # Post message to team chat
        message = f"Trade accepted by {trade.receiving_team.name}. Will execute Monday at 9 AM."
        post_team_chat_message(trade.proposing_team, trade.receiving_team, message,
                              message_type='TRADE_ACCEPTED',
                              trade=trade,
                              sender=request.user)
        
        if current_week:
            messages.success(request, f"Trade accepted! It will be processed on Monday at 9 AM when rosters unlock.")
        else:
            messages.success(request, f"Trade accepted! Waiting for rosters to unlock.")
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
        if success:
            messages.success(request, f"Trade accepted and completed with {trade.proposing_team.name}!")
        else:
            messages.error(request, f"Trade accepted but execution failed: {msg}")
    
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

    def fantasy_points(stat_obj, player=None):
        if stat_obj is None:
            return None
        
        # Use league scoring settings if available, otherwise use defaults
        if selected_league:
            league = selected_league
        else:
            # Use default scoring (create a temporary league object with defaults)
            league = League()
        
        # Goalie scoring
        if player and player.position == "G":
            return (
                stat_obj.wins * float(league.scoring_goalie_wins)
                + stat_obj.saves * float(league.scoring_goalie_saves)
                + stat_obj.goals_against * float(league.scoring_goalie_goals_against)
                + stat_obj.goals * float(league.scoring_goalie_goals)
                + stat_obj.assists * float(league.scoring_goalie_assists)
            )
        # Field player scoring
        return (
            stat_obj.goals * float(league.scoring_goals)
            + stat_obj.assists * float(league.scoring_assists)
            + stat_obj.loose_balls * float(league.scoring_loose_balls)
            + stat_obj.caused_turnovers * float(league.scoring_caused_turnovers)
            + stat_obj.blocked_shots * float(league.scoring_blocked_shots)
            + stat_obj.turnovers * float(league.scoring_turnovers)
        )

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
            # Check if player is on any team in the league
            roster_entry = Roster.objects.filter(
                team__league_id=selected_league_id,
                player=p,
                week_dropped__isnull=True
            ).select_related('team').first()
            
            if roster_entry:
                if roster_entry.team == user_team:
                    roster_status = "on_your_team"
                else:
                    roster_status = "on_other_team"
                    rostered_team = roster_entry.team

        fpts = fantasy_points(stat_for_view, p)
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


def player_detail_modal(request, player_id):
    """AJAX endpoint to get player details for modal popup"""
    from django.http import JsonResponse
    
    try:
        player = Player.objects.get(id=player_id)
    except Player.DoesNotExist:
        return JsonResponse({'error': 'Player not found'}, status=404)
    
    # NLL team name to ID mapping - based on actual games in the database
    # Updated to match player team names with their game IDs
    team_name_to_id = {
        "Vancouver Warriors": "867",
        "San Diego Seals": "868",
        "Colorado Mammoth": "870",
        "Calgary Roughnecks": "874",
        "Saskatchewan Rush": "879",
        "Philadelphia Wings": "880",
        "Buffalo Bandits": "888",
        "Georgia Swarm": "890",
        "Toronto Rock": "896",
        "Halifax Thunderbirds": "912",
        "Panther City Lacrosse Club": "913",
        "Albany FireWolves": "914",
        "Las Vegas Desert Dogs": "915",
        "Ottawa Black Bears": "917",
        "Oshawa FireWolves": "918",
        "Rochester Knighthawks": "910",
        "New York Riptide": "911",
    }
    
    # Reverse mapping for ID to name (only for teams that have games)
    team_id_to_name = {v: k for k, v in team_name_to_id.items() if v is not None}
    
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
    
    def fantasy_points(stat_obj, player=None):
        if stat_obj is None:
            return None
        # Goalie scoring using league settings
        if player and player.position == "G":
            return (
                stat_obj.wins * float(league.scoring_goalie_wins)
                + stat_obj.saves * float(league.scoring_goalie_saves)
                + stat_obj.goals_against * float(league.scoring_goalie_goals_against)
                + stat_obj.goals * float(league.scoring_goalie_goals)
                + stat_obj.assists * float(league.scoring_goalie_assists)
            )
        # Field player scoring using league settings
        return (
            stat_obj.goals * float(league.scoring_goals)
            + stat_obj.assists * float(league.scoring_assists)
            + stat_obj.loose_balls * float(league.scoring_loose_balls)
            + stat_obj.caused_turnovers * float(league.scoring_caused_turnovers)
            + stat_obj.blocked_shots * float(league.scoring_blocked_shots)
            + stat_obj.turnovers * float(league.scoring_turnovers)
        )
    
    for week_key in sorted(stats_by_week.keys()):
        games = stats_by_week[week_key]
        # Calculate fantasy points for each game
        game_points = []
        for stat in game_stats:
            if f"Week {stat.game.week.week_number} (S{stat.game.week.season})" == week_key:
                pts = fantasy_points(stat, player)
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
            'games': games
        }
        week_stats.append(agg_stat)
    
    # Add upcoming weeks (no stats yet)
    today = timezone.now().date()
    upcoming_weeks = Week.objects.filter(
        start_date__gte=today,
        season=2026
    ).order_by('week_number')
    
    # Get player's team ID
    player_team_id = team_name_to_id.get(player.nll_team, None)
    
    for week in upcoming_weeks:
        week_key = f"Week {week.week_number} (S{week.season})"
        # Check if this week already has stats
        if not any(ws['week'] == week_key for ws in week_stats):
            # Get upcoming games for this player's team
            upcoming_games = []
            if player_team_id:
                games = Game.objects.filter(
                    Q(week=week) &
                    (Q(home_team=player_team_id) | Q(away_team=player_team_id))
                )
                upcoming_games = [{
                    'date': game.date.strftime('%Y-%m-%d'),
                    'opponent': f"{team_id_to_name.get(game.home_team, game.home_team)} vs {team_id_to_name.get(game.away_team, game.away_team)}",
                } for game in games]
            
            agg_stat = {
                'week': week_key,
                'games_count': len(upcoming_games),
                'is_upcoming': True,
                'games': upcoming_games
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


def nll_schedule(request):
    """Display all NLL weeks and games (both completed and upcoming)"""
    season = request.GET.get('season', 2026)
    
    try:
        season = int(season)
    except (ValueError, TypeError):
        season = 2026
    
    # NLL team ID to name mapping
    nll_teams = {
        867: "Vancouver Warriors",
        868: "San Diego Seals",
        869: "Vancouver Ravens",
        870: "Colorado Mammoth",
        871: "Arizona Sting",
        872: "Anaheim Storm",
        873: "Ottawa Rebel",
        874: "Calgary Roughnecks",
        875: "Montreal Express",
        876: "New Jersey Storm",
        877: "San Jose Stealth",
        878: "Minnesota Swarm",
        879: "Saskatchewan Rush",
        880: "Philadelphia Wings",
        881: "New Jersey Saints",
        882: "Baltimore Thunder",
        883: "Washington Wave",
        884: "Detroit Turbos",
        885: "Philadelphia Wings[1]",
        886: "New England Blazers",
        887: "New York Saints",
        888: "Buffalo Bandits",
        889: "Pittsburgh Bulls",
        890: "Georgia Swarm",
        891: "New England Black Wolves",
        892: "Rochester Knighthawks[1]",
        893: "Boston Blazers",
        894: "Ontario Raiders",
        895: "Charlotte Cobras",
        896: "Toronto Rock",
        897: "Syracuse Smash",
        898: "Pittsburgh Crossefire",
        899: "Albany Attack",
        900: "Columbus Landsharks",
        901: "Washington Power",
        902: "Portland Lumberjax",
        903: "Edmonton Rush",
        904: "Vancouver Stealth",
        905: "Boston Blazers[1]",
        906: "Washington Stealth",
        907: "Orlando Titans",
        908: "New York Titans",
        909: "Chicago Shamrox",
        910: "Rochester Knighthawks",
        911: "New York Riptide",
        912: "Halifax Thunderbirds",
        913: "Panther City Lacrosse Club",
        914: "Albany FireWolves",
        915: "Las Vegas Desert Dogs",
        917: "Ottawa Black Bears",
        918: "Oshawa FireWolves",
    }
    
    # Get all weeks for this season, ordered by week number
    weeks = Week.objects.filter(season=season).prefetch_related('games').order_by('week_number')
    
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
                # Check if game has stats (completed) vs upcoming
                "is_completed": game.player_stats.exists()
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
    
    # DEBUG: Log the first game's team data
    if schedule_weeks and schedule_weeks[0]['games']:
        first_game = schedule_weeks[0]['games'][0]
        import sys
        print(f"DEBUG: First game - away: {repr(first_game['away_team'])}, home: {repr(first_game['home_team'])}", file=sys.stderr)
    
    return render(request, "web/nll_schedule.html", {
        "schedule_weeks": schedule_weeks,
        "season": season,
        "available_seasons": available_seasons
    })


def schedule(request):
    teams = list(Team.objects.order_by("id"))

    if not teams:
        return render(request, "web/schedule.html", {"schedule_weeks": []})
    
    league = teams[0].league
    team_ids = [t.id for t in teams]
    weeks = _build_schedule(team_ids, league.playoff_weeks, league.playoff_teams, getattr(league, 'playoff_reseed', 'fixed'))

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
        all_weeks = _build_schedule(team_ids, league.playoff_weeks, league.playoff_teams, getattr(league, 'playoff_reseed', 'fixed'))
    else:
        league = League()  # Default scoring
        all_weeks = _build_schedule(team_ids)
    
    # Show all regular season weeks in matchups (filter out playoff weeks for now)
    # TODO: Implement playoff bracket display once regular season completes
    weeks = [w for w in all_weeks if w and all(not (isinstance(g, tuple) and len(g) == 4 and g[0] == 'playoff') for g in w)]

    id_to_team = {t.id: t for t in teams}

    def fantasy_points(stat_obj, player=None):
        if stat_obj is None:
            return None
        # Goalie scoring using league settings
        if player and player.position == "G":
            return (
                stat_obj.wins * float(league.scoring_goalie_wins)
                + stat_obj.saves * float(league.scoring_goalie_saves)
                + stat_obj.goals_against * float(league.scoring_goalie_goals_against)
                + stat_obj.goals * float(league.scoring_goalie_goals)
                + stat_obj.assists * float(league.scoring_goalie_assists)
            )
        # Field player scoring using league settings
        return (
            stat_obj.goals * float(league.scoring_goals)
            + stat_obj.assists * float(league.scoring_assists)
            + stat_obj.loose_balls * float(league.scoring_loose_balls)
            + stat_obj.caused_turnovers * float(league.scoring_caused_turnovers)
            + stat_obj.blocked_shots * float(league.scoring_blocked_shots)
            + stat_obj.turnovers * float(league.scoring_turnovers)
        )

    # determine target week object (same week_number, latest season available)
    selected_week_number = None
    if weeks:
        try:
            selected_week_number = int(request.GET.get("week", 1))
        except ValueError:
            selected_week_number = 1

    week_obj = None
    if selected_week_number is not None:
        # Only get week from current league season, not previous seasons
        week_obj = Week.objects.filter(week_number=selected_week_number, season=league_season).first()

    # Build detailed rosters with slot structure (like team_detail view)
    team_rosters = {}
    team_totals = {}
    for team in teams:
        # Get roster organized by position - FILTERED BY HISTORICAL WEEK
        # Players who were active during the selected week:
        # - week_added <= selected_week_number (or week_added is NULL for legacy data)
        # - AND (week_dropped is NULL OR week_dropped > selected_week_number)
        players_by_position = {"O": [], "D": [], "G": [], "T": []}
        
        roster_query = team.roster_entries.select_related('player').filter(
            player__active=True
        )
        
        # Apply historical filtering based on selected week
        if selected_week_number:
            roster_query = roster_query.filter(
                models.Q(week_added__isnull=True) | models.Q(week_added__lte=selected_week_number)
            ).filter(
                models.Q(week_dropped__isnull=True) | models.Q(week_dropped__gt=selected_week_number)
            )
        else:
            # If no week selected, show current roster only
            roster_query = roster_query.filter(week_dropped__isnull=True)
        
        roster = roster_query.order_by("player__updated_at", "player__id")
        
        for roster_entry in roster:
            p = roster_entry.player
            fpts = None
            if week_obj:
                # Get all stats for this player in the selected week
                game_stats = list(p.game_stats.filter(game__week=week_obj))
                if game_stats:
                    # Calculate fantasy points for each game
                    pts_list = [fantasy_points(st, p) for st in game_stats if st is not None]
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
        all_weeks = _build_schedule(team_ids)
        
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

        def fantasy_points(stat_obj, player=None):
            if stat_obj is None:
                return None
            # Goalie scoring using league settings
            if player and player.position == "G":
                return (
                    stat_obj.wins * float(league.scoring_goalie_wins)
                    + stat_obj.saves * float(league.scoring_goalie_saves)
                    + stat_obj.goals_against * float(league.scoring_goalie_goals_against)
                    + stat_obj.goals * float(league.scoring_goalie_goals)
                    + stat_obj.assists * float(league.scoring_goalie_assists)
                )
            # Field player scoring using league settings
            return (
                stat_obj.goals * float(league.scoring_goals)
                + stat_obj.assists * float(league.scoring_assists)
                + stat_obj.loose_balls * float(league.scoring_loose_balls)
                + stat_obj.caused_turnovers * float(league.scoring_caused_turnovers)
                + stat_obj.blocked_shots * float(league.scoring_blocked_shots)
                + stat_obj.turnovers * float(league.scoring_turnovers)
            )

        # prefetch players once via roster entries
        from collections import defaultdict

        rosters = (
            Roster.objects.filter(team__in=teams, league=league, player__active=True)
            .select_related("player", "team")
            .prefetch_related("player__game_stats__game__week")
        )
        # Store all rosters with their week ranges for historical lookup
        all_rosters = list(rosters)
        
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
            active_players = []
            for roster_entry in all_rosters:
                if roster_entry.team_id == team_id:
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
                pts = fantasy_points(stat, p)
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
    from web.models import TeamChatMessage
    
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
    
    # Determine which chat to display
    chat_type = request.GET.get('chat_type', 'league')  # 'league' or 'team'
    team_chat_id = request.GET.get('team_chat_id', None)  # ID of other team for team chats
    
    messages_list = []
    available_team_chats = []
    current_chat_with = None
    
    if chat_type == 'league':
        # Display league chat
        messages_list = ChatMessage.objects.filter(
            league_id=selected_league_id
        ).select_related(
            'sender', 'player', 'team', 'league'
        ).all()[:100]  # Last 100 messages
    
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
    
    # Get all other teams in the league for chat options
    if user_team:
        # Show all other teams in the league (not just existing chats)
        available_team_chats = Team.objects.filter(
            league_id=selected_league_id
        ).exclude(
            id=user_team.id
        ).order_by('name')
    else:
        available_team_chats = []
    
    return render(request, "web/chat.html", {
        "messages": messages_list,
        "chat_type": chat_type,
        "current_chat_with": current_chat_with,
        "available_team_chats": available_team_chats,
        "user_team": user_team,
        "is_team_chat": chat_type == 'team'
    })


@login_required
@require_POST
def chat_post_message(request):
    """API endpoint to post a new chat message (league or team)"""
    from web.models import TeamChatMessage
    
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
    from web.models import TeamChatMessage
    
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
            messages.success(request, f"League '{league.name}' created successfully!")
            return redirect("league_detail", league_id=league.id)
    else:
        form = LeagueCreateForm()
    
    return render(request, "web/league_create.html", {"form": form})


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
            
            # For dynasty leagues, create taxi squad slots based on league setting
            if hasattr(league, 'league_type') and league.league_type == 'dynasty':
                from web.models import TaxiSquad
                taxi_size = league.taxi_squad_size if hasattr(league, 'taxi_squad_size') else 3
                for slot_num in range(1, taxi_size + 1):
                    TaxiSquad.objects.get_or_create(
                        team=team,
                        slot_number=slot_num,
                        defaults={'player': None}
                    )
            
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
    messages.success(request, f"Viewing data for league: {league.name}")
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
            league_obj.save()
            form.save_m2m() if hasattr(form, 'save_m2m') else None
            messages.success(request, "League settings updated successfully!")
            return redirect("league_detail", league_id=league.id)
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
            from web.tasks import renew_league as renew_league_task
            
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
    }
    
    return render(request, 'web/draft_room.html', context)


@login_required
@require_POST
def start_draft(request):
    """Start a draft for the selected league (commissioner only)"""
    selected_league_id = request.session.get('selected_league_id')
    
    if not selected_league_id:
        messages.error(request, "Please select a league first.")
        return redirect('league_list')
    
    league = get_object_or_404(League, id=selected_league_id)
    
    # Check if user is commissioner
    if league.commissioner != request.user:
        messages.error(request, "Only the commissioner can start the draft.")
        return redirect('draft_room')
    
    # Check if league is full
    teams = Team.objects.filter(league=league)
    team_count = teams.count()
    if team_count != league.max_teams:
        messages.error(request, f"League must be full to start draft. Currently {team_count}/{league.max_teams} teams.")
        return redirect('draft_room')
    
    # Check if draft already exists
    if hasattr(league, 'draft'):
        messages.error(request, "Draft already exists for this league.")
        return redirect('draft_room')
    
    # Get draft order type and style
    order_type = request.POST.get('order_type', 'RANDOM')
    draft_style = request.POST.get('draft_style', 'SNAKE')
    
    # For MANUAL order, create draft but don't activate it yet
    is_active = order_type == 'RANDOM'
    started_at = timezone.now() if is_active else None
    
    # Create draft
    draft = Draft.objects.create(
        league=league,
        is_active=is_active,
        draft_order_type=order_type,
        draft_style=draft_style,
        total_rounds=league.roster_size,
        started_at=started_at
    )
    
    # Create draft positions
    teams_list = list(teams)
    
    if order_type == 'RANDOM':
        import random
        random.shuffle(teams_list)
    # If MANUAL, use default order (commissioner will reorder in next step)
    
    for position, team in enumerate(teams_list, start=1):
        DraftPosition.objects.create(
            draft=draft,
            team=team,
            position=position
        )
    
    # Create all draft pick slots
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
    
    if order_type == 'MANUAL':
        messages.info(request, "Draft created! Please arrange the team order.")
    else:
        post_league_message(league, f"🏁 Draft has started! ({draft.get_draft_style_display()})")
        messages.success(request, "Draft started!")
    return redirect('draft_room')


@login_required
@require_POST
def make_draft_pick(request, draft_id):
    """Make a draft pick"""
    draft = get_object_or_404(Draft, id=draft_id)
    
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
    
    # If draft is complete, add all players to rosters
    if draft.completed:
        all_picks = DraftPick.objects.filter(draft=draft, player__isnull=False).select_related('team', 'player')
        for pick in all_picks:
            # Check total roster capacity
            current_roster_count = Roster.objects.filter(
                team=pick.team,
                league=draft.league,
                week_dropped__isnull=True
            ).count()
            
            if current_roster_count >= draft.league.roster_size:
                post_league_message(draft.league, f"⚠️ Draft error: {pick.team.name} roster would exceed capacity")
                messages.error(request, f"Draft error: roster capacity exceeded for {pick.team.name}")
                return redirect('draft_room')
            
            # Check position-specific capacity
            player_position = pick.player.assigned_side if pick.player.assigned_side else pick.player.position
            can_add, current_pos_count, max_pos_slots = check_roster_capacity(pick.team, player_position)
            if not can_add:
                pos_name = {'O': 'Offence', 'D': 'Defence', 'G': 'Goalie'}.get(player_position, 'Unknown')
                post_league_message(draft.league, f"⚠️ Draft error: {pick.team.name} {pos_name} roster full")
                messages.error(request, f"Draft error: {pos_name} roster full for {pick.team.name}")
                return redirect('draft_room')
            
            Roster.objects.create(
                team=pick.team,
                player=pick.player,
                league=draft.league,
                week_added=1  # Assume draft happens before season
            )
        post_league_message(draft.league, f"🎉 Draft completed! All players have been added to rosters.")
        messages.success(request, f"You selected {player.first_name} {player.last_name}!")
    else:
        post_league_message(draft.league, f"📋 {user_team.name} selected {player.first_name} {player.last_name} (Round {draft.current_round})")
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
    
    post_league_message(league, "❌ The draft has been cancelled by the commissioner.")
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
    
    # Check if season has started - prevent adding to taxi squad once season starts
    league_season = team.league.created_at.year if team.league.created_at else timezone.now().year
    first_game = Game.objects.filter(season=league_season).order_by('date').first()
    if first_game and timezone.now() >= first_game.date:
        messages.error(request, "Cannot add to taxi squad after season starts. You can only move players FROM taxi squad to main roster during the season.")
        return redirect('team_detail', team_id=team_id)
    
    if request.method == 'POST':
        from web.models import TaxiSquad
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
    
    if request.method == 'POST':
        from web.models import TaxiSquad
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
        
        Roster.objects.create(
            team=team,
            player=player,
            league=team.league,
            week_added=week_added,
            slot_assignment='bench'
        )
        
        # Clear player from taxi squad but keep the slot
        taxi_entry.player = None
        taxi_entry.save()
        
        # Check if now over roster limit and warn user
        current_count, is_over = team.is_over_roster_limit()
        roster_limit = team.league.roster_size if hasattr(team.league, 'roster_size') else 14
        
        if is_over:
            messages.warning(request, f"{player.get_full_name()} moved to main roster. ⚠️ Your roster is now OVER the limit ({current_count}/{roster_limit}). You must drop players to get back under the limit.")
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