from django.shortcuts import render, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db import models

from .models import Player, Team, Week, ChatMessage, FantasyTeamOwner, League, Roster, PlayerWeekStat
from .forms import UserRegistrationForm, LeagueCreateForm, TeamCreateForm
from django.shortcuts import redirect
from django.views.decorators.http import require_POST


def home(request):
    context = {}
    
    # Get user's team if they're authenticated and have a team
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
                owner = FantasyTeamOwner.objects.select_related('team', 'team__league').get(
                    user=request.user,
                    team__league_id=selected_league_id
                )
                team = owner.team
                
                # Get all available weeks for this league's season
                league_season = team.league.created_at.year
                available_weeks = list(Week.objects.filter(
                    season=league_season
                ).order_by('week_number'))
                
                # Get the most recent week
                most_recent_week = available_weeks[-1] if available_weeks else None
                
                # Add future week placeholders (up to week 21 for NLL season)
                if most_recent_week:
                    max_week = most_recent_week.week_number
                    for future_week_num in range(max_week + 1, 22):
                        # Create a placeholder dict for future weeks
                        available_weeks.append({
                            'week_number': future_week_num,
                            'season': league_season,
                            'is_future': True
                        })
                
                # Get selected week from query parameter, default to most recent
                selected_week_param = request.GET.get('week')
                selected_week = most_recent_week
                is_future_week = False
                if selected_week_param:
                    try:
                        week_num = int(selected_week_param)
                        # Try to find in actual weeks first
                        selected_week = next((w for w in available_weeks if (w.week_number if hasattr(w, 'week_number') else w['week_number']) == week_num), most_recent_week)
                        # Check if it's a future week
                        if isinstance(selected_week, dict):
                            is_future_week = True
                    except (ValueError, StopIteration):
                        pass
                
                if not most_recent_week:
                    # No weeks available yet
                    context.update({'team': team})
                else:
                    # Get the week number we're looking at
                    selected_week_number = selected_week.week_number if hasattr(selected_week, 'week_number') else selected_week['week_number']
                    
                    # Get roster entries for this team for the selected week
                    # Show players who were on roster during that week
                    # For future weeks, show current roster (week_dropped is None)
                    # Handle NULL week_added (legacy data before week tracking)
                    roster_entries = Roster.objects.filter(
                        team=team,
                        league=team.league,
                    ).filter(
                        models.Q(week_added__isnull=True) | models.Q(week_added__lte=selected_week_number)
                    ).filter(
                        models.Q(week_dropped__isnull=True) |
                        models.Q(week_dropped__gt=selected_week_number)
                    ).select_related('player')
                    
                    # Build slots structure similar to team_detail
                    offence_slots = []
                    defence_slots = []
                    goalie_slots = []
                    
                    # Define fantasy points calculation function
                    def fantasy_points(stat_obj, player=None):
                        if stat_obj is None:
                            return None
                        # Goalie scoring: win=5, save=0.75, goal against=-1, goal=4, assist=2
                        if player and player.position == "G":
                            return (
                                stat_obj.wins * 5
                                + stat_obj.saves * 0.75
                                - stat_obj.goals_against
                                + stat_obj.goals * 4
                                + stat_obj.assists * 2
                            )
                        # Field player scoring
                        return (
                            stat_obj.goals * 4
                            + stat_obj.assists * 2
                            + stat_obj.loose_balls * 2
                            + stat_obj.caused_turnovers * 3
                            + stat_obj.blocked_shots * 2
                            - stat_obj.turnovers
                        )
                    
                    for entry in roster_entries:
                        player = entry.player
                        
                        # Get stat for selected week (only if it's not a future week)
                        stat = None
                        if not is_future_week:
                            stat = PlayerWeekStat.objects.filter(
                                player=player,
                                week=selected_week
                            ).first()
                        
                        pts = fantasy_points(stat, player)
                        
                        slot_data = {
                            'player': player,
                            'week_points': pts,
                            'counts_for_total': False  # Will be set in aggregation
                        }
                        
                        # Assign to appropriate slot group
                        assigned_pos = player.assigned_side or player.position
                        if assigned_pos == 'O':
                            offence_slots.append(slot_data)
                        elif assigned_pos == 'D':
                            defence_slots.append(slot_data)
                        elif assigned_pos == 'G':
                            goalie_slots.append(slot_data)
                    
                    # Pad slots to required counts
                    while len(offence_slots) < 6:
                        offence_slots.append(None)
                    while len(defence_slots) < 6:
                        defence_slots.append(None)
                    while len(goalie_slots) < 2:
                        goalie_slots.append(None)
                    
                    # Calculate weekly total: top 3 offense, top 3 defense, top 1 goalie
                    offense_scores = []
                    for slot in offence_slots[:6]:
                        if slot and slot['week_points'] is not None:
                            offense_scores.append((slot['week_points'], slot))
                    
                    defense_scores = []
                    for slot in defence_slots[:6]:
                        if slot and slot['week_points'] is not None:
                            defense_scores.append((slot['week_points'], slot))
                    
                    goalie_scores = []
                    for slot in goalie_slots[:2]:
                        if slot and slot['week_points'] is not None:
                            goalie_scores.append((slot['week_points'], slot))
                    
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
                    
                    # Calculate weekly total
                    weekly_total = (
                        sum(x[0] for x in offense_scores[:3]) +
                        sum(x[0] for x in defense_scores[:3]) +
                        sum(x[0] for x in goalie_scores[:1])
                    )
                    
                    context.update({
                        'team': team,
                        'current_week': selected_week_number,
                        'selected_week': selected_week,
                        'available_weeks': available_weeks,
                        'is_future_week': is_future_week,
                        'offence_slots': offence_slots[:6],
                        'defence_slots': defence_slots[:6],
                        'goalie_slots': goalie_slots[:2],
                        'weekly_total': weekly_total,
                    })
                
            except FantasyTeamOwner.DoesNotExist:
                pass
    
    return render(request, "web/index.html", context)


def about(request):
    return render(request, "web/about.html")


def team_detail(request, team_id):
    team = get_object_or_404(Team, id=team_id)

    players_by_position = {"O": [], "D": [], "G": [], "T": []}
    # Best-ball fantasy scoring derived from the raw stat fields
    def fantasy_points(stat_obj, player=None):
        if stat_obj is None:
            return None
        # Goalie scoring: win=5, save=0.75, goal against=-1, goal=4, assist=2
        if player and player.position == "G":
            return (
                stat_obj.wins * 5
                + stat_obj.saves * 0.75
                - stat_obj.goals_against
                + stat_obj.goals * 4
                + stat_obj.assists * 2
            )
        # Field player scoring
        return (
            stat_obj.goals * 4
            + stat_obj.assists * 2
            + stat_obj.loose_balls * 2
            + stat_obj.caused_turnovers * 3
            + stat_obj.blocked_shots * 2
            - stat_obj.turnovers
        )

    # determine most recent season available for weekly breakdown
    recent_week = Week.objects.order_by("-season", "-week_number").first()
    season = recent_week.season if recent_week else None

    # Keep players in order of when they were (last) assigned, not alphabetically
    # Get players through roster entries for this team's league - CURRENT ROSTER ONLY
    roster = team.roster_entries.select_related('player').filter(
        player__active=True,
        week_dropped__isnull=True  # Only show players currently on the roster
    ).order_by("player__updated_at", "player__id")
    
    for roster_entry in roster:
        p = roster_entry.player
        weekly = list(p.weekly_stats.all())
        latest = None
        if weekly:
            latest = max(weekly, key=lambda s: (s.week.season, s.week.week_number))

        # build per-week fantasy points for weeks 1..18 for the selected season
        weekly_points = []
        total_points = 0
        if season is not None:
            stats_by_week = {s.week.week_number: s for s in p.weekly_stats.filter(week__season=season)}
            for wk in range(1, 19):
                st = stats_by_week.get(wk)
                pts = fantasy_points(st, p)
                weekly_points.append(pts)
                if pts is not None:
                    total_points += pts
        else:
            weekly_points = [None] * 18

        entry = {"player": p, "latest_stat": latest, "weekly_points": weekly_points, "weeks_total": total_points, "counts_for_total": [False] * 18}
        pos = getattr(p, "position", None)
        side = getattr(p, "assigned_side", None)
        target = side or ("O" if pos == "T" else pos)
        if target in players_by_position:
            players_by_position[target].append(entry)
        else:
            players_by_position["O"].append(entry)

    # Build slots without reshuffling Transition; assigned_side controls placement
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

    # Aggregate weekly totals: top 3 offense, top 3 defense, top 1 goalie
    # Also mark which stats count toward the total
    weekly_totals = []
    for week_idx in range(18):
        # Get all offense scores for this week with slot reference
        offense_scores = []
        for slot in offence_slots:
            if slot and slot.get("weekly_points") and slot["weekly_points"][week_idx] is not None:
                offense_scores.append((slot["weekly_points"][week_idx], slot))
        
        # Get all defense scores for this week with slot reference
        defense_scores = []
        for slot in defence_slots:
            if slot and slot.get("weekly_points") and slot["weekly_points"][week_idx] is not None:
                defense_scores.append((slot["weekly_points"][week_idx], slot))
        
        # Get all goalie scores for this week with slot reference
        goalie_scores = []
        for slot in goalie_slots:
            if slot and slot.get("weekly_points") and slot["weekly_points"][week_idx] is not None:
                goalie_scores.append((slot["weekly_points"][week_idx], slot))
        
        # Sort by score descending
        offense_scores.sort(key=lambda x: x[0], reverse=True)
        defense_scores.sort(key=lambda x: x[0], reverse=True)
        goalie_scores.sort(key=lambda x: x[0], reverse=True)
        
        # Mark top 3 offense as counting
        for score, slot in offense_scores[:3]:
            slot["counts_for_total"][week_idx] = True
        
        # Mark top 3 defense as counting
        for score, slot in defense_scores[:3]:
            slot["counts_for_total"][week_idx] = True
        
        # Mark top 1 goalie as counting
        for score, slot in goalie_scores[:1]:
            slot["counts_for_total"][week_idx] = True
        
        week_total = sum(x[0] for x in offense_scores[:3]) + sum(x[0] for x in defense_scores[:3]) + sum(x[0] for x in goalie_scores[:1])
        weekly_totals.append(week_total)
    
    overall_total = sum(weekly_totals)

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

    return render(
        request,
        "web/team_detail.html",
        {
            "team": team,
            "offence_slots": offence_slots,
            "defence_slots": defence_slots,
            "goalie_slots": goalie_slots,
            "week_range": list(range(1, 19)),
            "weekly_totals": weekly_totals,
            "overall_total": overall_total,
            "players_for_select": players_with_teams,
        },
    )


@require_POST
def assign_player(request, team_id):
    team = get_object_or_404(Team, id=team_id)
    action = request.POST.get("action")
    player_id = request.POST.get("player_id")
    if not player_id:
        return redirect("team_detail", team_id=team.id)

    try:
        player = Player.objects.get(id=int(player_id))
    except Player.DoesNotExist:
        return redirect("team_detail", team_id=team.id)

    # Determine current week number based on most recent week
    current_week = Week.objects.order_by('-season', '-week_number').first()
    current_week_number = current_week.week_number if current_week else 1

    slot_group = request.POST.get("slot_group")
    if action == "add":
        # Check roster size limit (12 players max)
        current_roster_count = Roster.objects.filter(
            team=team,
            league=team.league,
            week_dropped__isnull=True
        ).count()
        
        if current_roster_count >= 12:
            messages.error(request, "Roster is full. Maximum 12 players allowed per team.")
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
        Roster.objects.create(
            player=player,
            team=team,
            league=team.league,
            week_added=current_week_number
        )
        # Update assigned_side for slot placement
        if slot_group in {"O", "D", "G"}:
            player.assigned_side = slot_group
            player.save()
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
            roster_entry.week_dropped = current_week_number
            roster_entry.save()
            # Clear assigned_side when dropping
            player.assigned_side = None
            player.save()
            messages.success(request, f"Dropped {player.first_name} {player.last_name} from your roster")

    return redirect("team_detail", team_id=team.id)


def players(request):
    """Render players list with their latest weekly stats (if any)."""
    # Get position filter
    selected_position = request.GET.get("position", "")
    
    qs = Player.objects.filter(active=True)
    
    # Apply position filter if selected
    if selected_position:
        qs = qs.filter(position=selected_position)
    else:
        # Exclude goalies from "All Positions" view
        qs = qs.exclude(position="G")
    
    qs = qs.order_by("last_name", "first_name").prefetch_related("weekly_stats__week")

    def fantasy_points(stat_obj, player=None):
        if stat_obj is None:
            return None
        # Goalie scoring: win=5, save=0.75, goal against=-1, goal=4, assist=2
        if player and player.position == "G":
            return (
                stat_obj.wins * 5
                + stat_obj.saves * 0.75
                - stat_obj.goals_against
                + stat_obj.goals * 4
                + stat_obj.assists * 2
            )
        # Field player scoring
        return (
            stat_obj.goals * 4
            + stat_obj.assists * 2
            + stat_obj.loose_balls * 2
            + stat_obj.caused_turnovers * 3
            + stat_obj.blocked_shots * 2
            - stat_obj.turnovers
        )

    # Get season and week selection
    selected_season = request.GET.get("season")
    selected_week_num = request.GET.get("week")
    
    # Get available seasons
    seasons = Week.objects.values_list('season', flat=True).distinct().order_by('-season')
    
    # Default to most recent season if none selected
    if not selected_season and seasons:
        selected_season = str(seasons[0])
    
    # Get weeks for selected season
    week_options = []
    if selected_season:
        week_options = list(Week.objects.filter(season=int(selected_season)).order_by('week_number'))

    sort_field = request.GET.get("sort", "name")
    sort_dir = request.GET.get("dir", "asc")

    players_with_stats = []
    for p in qs:
        weekly = list(p.weekly_stats.all())
        
        # Calculate stats based on selection
        if selected_week_num:
            # Show specific week stats
            stat_for_view = None
            if selected_season:
                stat_for_view = next((s for s in weekly if s.week.season == int(selected_season) and s.week.week_number == int(selected_week_num)), None)
            games_played = stat_for_view.games_played if stat_for_view else 0
        else:
            # Show season totals
            season_stats = [s for s in weekly if s.week.season == int(selected_season)] if selected_season else []
            
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
                    'games_played': sum(s.games_played for s in season_stats),
                })()
                games_played = stat_for_view.games_played
            else:
                stat_for_view = None
                games_played = 0

        players_with_stats.append({
            "player": p,
            "latest_stat": stat_for_view,
            "fantasy_points": fantasy_points(stat_for_view, p),
            "games_played": games_played,
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
            "sort_field": sort_field,
            "sort_dir": sort_dir,
        },
    )


def _build_schedule(team_ids):
    teams_local = list(team_ids)
    n = len(teams_local)
    
    # Require even number of teams - no bye weeks allowed
    if n % 2 != 0 or n < 2:
        return []

    anchor = teams_local[0]
    rotate = teams_local[1:]

    def one_round(order_anchor, order_rot):
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

    round1 = one_round(anchor, rotate)
    # second round repeats matchups (order irrelevant since home/away ignored)
    round2 = [list(wk) for wk in round1]
    # add 4 extra repeat weeks from start of round1 to reach 18 total
    schedule_local = round1 + round2 + round1[:4]
    return schedule_local


def schedule(request):
    teams = list(Team.objects.order_by("id"))

    team_ids = [t.id for t in teams]
    weeks = _build_schedule(team_ids)

    # map ids back to team objects for display
    id_to_team = {t.id: t for t in teams}
    schedule_weeks = []
    for idx, games in enumerate(weeks, start=1):
        schedule_weeks.append(
            {
                "week_number": idx,
                "games": [
                    {"home": id_to_team.get(a), "away": id_to_team.get(b)} for (a, b) in games
                ],
            }
        )

    return render(request, "web/schedule.html", {"schedule_weeks": schedule_weeks})


def matchups(request):
    # Get selected league from session
    selected_league_id = request.session.get('selected_league_id')
    
    if selected_league_id:
        teams = list(Team.objects.filter(league_id=selected_league_id).order_by("id"))
        # Get the league to determine its season
        league = League.objects.get(id=selected_league_id)
        league_season = league.created_at.year
    else:
        teams = list(Team.objects.filter(league__is_active=True).order_by("id"))
        # Use the most recent season
        latest_week = Week.objects.order_by('-season', '-week_number').first()
        league_season = latest_week.season if latest_week else timezone.now().year
    
    # Get actual weeks that exist for this season
    actual_weeks = Week.objects.filter(season=league_season).order_by('week_number')
    max_week = actual_weeks.last().week_number if actual_weeks.exists() else 0
    
    # Move current user's team to the front (anchor position) if logged in
    if request.user.is_authenticated and selected_league_id:
        user_team_owner = FantasyTeamOwner.objects.filter(
            user=request.user, 
            team__league_id=selected_league_id
        ).select_related('team').first()
        
        if user_team_owner:
            user_team = user_team_owner.team
            # Remove user's team from list and add it to the front
            teams = [t for t in teams if t.id != user_team.id]
            teams.insert(0, user_team)
    
    team_ids = [t.id for t in teams]
    all_weeks = _build_schedule(team_ids)
    
    # Limit to only weeks that have been played (or are in the current week)
    weeks = all_weeks[:max_week] if max_week > 0 else []

    id_to_team = {t.id: t for t in teams}

    def fantasy_points(stat_obj, player=None):
        if stat_obj is None:
            return None
        # Goalie scoring: win=5, save=0.75, goal against=-1, goal=4, assist=2
        if player and player.position == "G":
            return (
                stat_obj.wins * 5
                + stat_obj.saves * 0.75
                - stat_obj.goals_against
                + stat_obj.goals * 4
                + stat_obj.assists * 2
            )
        # Field player scoring
        return (
            stat_obj.goals * 4
            + stat_obj.assists * 2
            + stat_obj.loose_balls * 2
            + stat_obj.caused_turnovers * 3
            + stat_obj.blocked_shots * 2
            - stat_obj.turnovers
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
        week_obj = Week.objects.filter(week_number=selected_week_number).order_by("-season").first()

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
            stat = None
            if week_obj:
                stat = p.weekly_stats.filter(week=week_obj).first()
                if stat is None:
                    stat = p.weekly_stats.filter(week__week_number=selected_week_number).order_by("-week__season").first()
            fpts = fantasy_points(stat, p)
            
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
        offense_scores = [slot["fantasy_points"] for slot in offence_slots if slot and slot["fantasy_points"] is not None]
        defense_scores = [slot["fantasy_points"] for slot in defence_slots if slot and slot["fantasy_points"] is not None]
        goalie_scores = [slot["fantasy_points"] for slot in goalie_slots if slot and slot["fantasy_points"] is not None]
        
        offense_scores.sort(reverse=True)
        defense_scores.sort(reverse=True)
        goalie_scores.sort(reverse=True)
        
        week_total = sum(offense_scores[:3]) + sum(defense_scores[:3]) + sum(goalie_scores[:1])
        
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
        weeks = _build_schedule(team_ids)

        def fantasy_points(stat_obj, player=None):
            if stat_obj is None:
                return None
            # Goalie scoring: win=5, save=0.75, goal against=-1, goal=4, assist=2
            if player and player.position == "G":
                return (
                    stat_obj.wins * 5
                    + stat_obj.saves * 0.75
                    - stat_obj.goals_against
                    + stat_obj.goals * 4
                    + stat_obj.assists * 2
                )
            # Field player scoring
            return (
                stat_obj.goals * 4
                + stat_obj.assists * 2
                + stat_obj.loose_balls * 2
                + stat_obj.caused_turnovers * 3
                + stat_obj.blocked_shots * 2
                - stat_obj.turnovers
            )

        # prefetch players once via roster entries
        from collections import defaultdict

        rosters = (
            Roster.objects.filter(team__in=teams, league=league, player__active=True)
            .select_related("player", "team")
            .prefetch_related("player__weekly_stats__week")
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
                week_obj = Week.objects.filter(week_number=week_number).order_by("-season").first()
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
                        active_players.append(roster_entry.player)
            
            for p in active_players:
                stat = None
                if week_obj:
                    stat = next((s for s in p.weekly_stats.all() if s.week_id == week_obj.id), None)
                if stat is None:
                    stat = next((s for s in p.weekly_stats.all() if s.week.week_number == week_number), None)
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
    """Display chat modal page"""
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
    
    messages_list = ChatMessage.objects.filter(
        league_id=selected_league_id
    ).select_related(
        'sender', 'player', 'team', 'league'
    ).all()[:100]  # Last 100 messages
    
    return render(request, "web/chat.html", {
        "messages": messages_list
    })


@login_required
@require_POST
def chat_post_message(request):
    """API endpoint to post a new chat message"""
    selected_league_id = request.session.get('selected_league_id')
    
    if not selected_league_id:
        return JsonResponse({"error": "No league selected"}, status=400)
    
    try:
        league = League.objects.get(id=selected_league_id)
    except League.DoesNotExist:
        return JsonResponse({"error": "League not found"}, status=404)
    
    # Verify user is a member of this league
    if not FantasyTeamOwner.objects.filter(user=request.user, team__league=league).exists():
        return JsonResponse({"error": "You are not a member of this league"}, status=403)
    
    message_text = request.POST.get("message", "").strip()
    
    if not message_text:
        return JsonResponse({"error": "Message cannot be empty"}, status=400)
    
    if len(message_text) > 1000:
        return JsonResponse({"error": "Message too long (max 1000 characters)"}, status=400)
    
    # Create the chat message
    chat_msg = ChatMessage.objects.create(
        league=league,
        sender=request.user,
        message_type=ChatMessage.MessageType.CHAT,
        message=message_text
    )
    
    return JsonResponse({
        "success": True,
        "message_id": chat_msg.id,
        "created_at": chat_msg.created_at.isoformat()
    })


@login_required
def chat_get_messages(request):
    """API endpoint to fetch new chat messages (for auto-refresh)"""
    selected_league_id = request.session.get('selected_league_id')
    
    if not selected_league_id:
        return JsonResponse({"messages": []})
    
    since_id = request.GET.get("since", 0)
    
    messages_list = ChatMessage.objects.filter(
        league_id=selected_league_id,
        id__gt=since_id
    ).select_related(
        'sender', 'player', 'team'
    ).order_by('created_at')[:50]
    
    data = []
    for msg in messages_list:
        sender_name = msg.sender.username if msg.sender else "System"
        team_names = []
        
        # Get team names if sender is a team owner
        if msg.sender:
            team_names = [
                owner.team.name 
                for owner in msg.sender.fantasy_teams.filter(team__league_id=selected_league_id)
            ]
        
        data.append({
            "id": msg.id,
            "sender": sender_name,
            "teams": team_names,
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
    """List all leagues and user's leagues"""
    # Leagues the user is commissioner of
    my_leagues = League.objects.filter(commissioner=request.user)
    
    # Leagues where user owns a team
    my_team_leagues = League.objects.filter(
        teams__owner__user=request.user
    ).distinct()
    
    # All other active leagues
    other_leagues = League.objects.filter(is_active=True).exclude(
        id__in=my_leagues.values_list('id', flat=True)
    ).exclude(
        id__in=my_team_leagues.values_list('id', flat=True)
    )
    
    return render(request, "web/league_list.html", {
        "my_leagues": my_leagues,
        "my_team_leagues": my_team_leagues,
        "other_leagues": other_leagues
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
    
    return render(request, "web/league_detail.html", {
        "league": league,
        "teams": teams,
        "user_team": user_team,
        "is_commissioner": is_commissioner,
        "can_join": can_join
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
