from django.shortcuts import render, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db import models

from .models import Player, Team, Week, ChatMessage, FantasyTeamOwner, League, Roster
from .forms import UserRegistrationForm, LeagueCreateForm, TeamCreateForm
from django.shortcuts import redirect
from django.views.decorators.http import require_POST


def home(request):
    teams = Team.objects.all().order_by("name")
    return render(request, "web/index.html", {"teams": teams})


def about(request):
    return render(request, "web/about.html")


def teams(request):
    # Get selected league from session
    selected_league_id = request.session.get('selected_league_id')
    
    if selected_league_id:
        teams = (
            Team.objects.filter(league_id=selected_league_id)
            .prefetch_related(
                "roster_entries__player__weekly_stats__week",
                "roster_entries__player",
                "league"
            )
        )
    else:
        # Default to active leagues if no selection
        teams = (
            Team.objects.filter(league__is_active=True)
            .prefetch_related(
                "roster_entries__player__weekly_stats__week",
                "roster_entries__player",
                "league"
            )
        )

    def fantasy_points(stat_obj, player=None):
        if stat_obj is None:
            return None
        # Goalie scoring: win=5, save=0.75, goal against=-1
        if player and player.position == "G":
            return (
                stat_obj.wins * 5
                + stat_obj.saves * 0.75
                - stat_obj.goals_against
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

    # Determine most recent season for calculating totals
    recent_week = Week.objects.order_by("-season", "-week_number").first()
    season = recent_week.season if recent_week else None

    # Build list of teams with players and calculate total fantasy points
    teams_data = []
    for t in teams:
        players = []
        roster = t.roster_entries.select_related('player').filter(player__active=True)
        for roster_entry in roster.order_by("player__last_name", "player__first_name"):
            p = roster_entry.player
            weekly = list(p.weekly_stats.all())
            latest = None
            if weekly:
                latest = max(weekly, key=lambda s: (s.week.season, s.week.week_number))
            
            # Calculate total fantasy points for this player
            total_points = 0
            if season is not None:
                stats_by_week = {s.week.week_number: s for s in p.weekly_stats.filter(week__season=season)}
                for wk in range(1, 19):
                    st = stats_by_week.get(wk)
                    pts = fantasy_points(st, p)
                    if pts is not None:
                        total_points += pts
            
            players.append({"player": p, "latest_stat": latest, "total_fantasy_points": total_points})
        teams_data.append({"team": t, "players": players})

    return render(request, "web/teams.html", {"teams": teams_data})


def team_detail(request, team_id):
    team = get_object_or_404(Team, id=team_id)

    players_by_position = {"O": [], "D": [], "G": [], "T": []}
    # Best-ball fantasy scoring derived from the raw stat fields
    def fantasy_points(stat_obj, player=None):
        if stat_obj is None:
            return None
        # Goalie scoring: win=5, save=0.75, goal against=-1
        if player and player.position == "G":
            return (
                stat_obj.wins * 5
                + stat_obj.saves * 0.75
                - stat_obj.goals_against
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
    # Get players through roster entries for this team's league
    roster = team.roster_entries.select_related('player').filter(
        player__active=True
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

        entry = {"player": p, "latest_stat": latest, "weekly_points": weekly_points, "weeks_total": total_points}
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

    # Aggregate weekly totals across all roster slots
    weekly_totals = [0] * 18
    for slot in offence_slots + defence_slots + goalie_slots:
        if slot and slot.get("weekly_points"):
            for idx, pts in enumerate(slot["weekly_points"]):
                if pts is not None:
                    weekly_totals[idx] += pts
    overall_total = sum(weekly_totals)

    # Get all players with their team assignment in this league (if any)
    players_with_teams = []
    all_players = Player.objects.filter(active=True).order_by("last_name", "first_name")
    for player in all_players:
        roster_entry = Roster.objects.filter(
            player=player,
            league=team.league
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

    slot_group = request.POST.get("slot_group")
    if action == "add":
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
        
        # Check if player is already rostered in this league
        existing_roster = Roster.objects.filter(
            player=player,
            league=team.league
        ).select_related('team').first()
        
        if existing_roster:
            messages.error(request, f"{player.first_name} {player.last_name} is not available - already on {existing_roster.team.name}")
            return redirect("team_detail", team_id=team.id)
        
        # Create a roster entry for this player on this team in this league
        Roster.objects.create(
            player=player,
            team=team,
            league=team.league
        )
        # Update assigned_side for slot placement
        if slot_group in {"O", "D", "G"}:
            player.assigned_side = slot_group
            player.save()
        messages.success(request, f"Added {player.first_name} {player.last_name} to your roster")
    elif action == "drop":
        # Remove the roster entry for this player on this team in this league
        Roster.objects.filter(
            player=player,
            team=team,
            league=team.league
        ).delete()
        # Clear assigned_side when dropping
        player.assigned_side = None
        player.save()

    return redirect("team_detail", team_id=team.id)


def players(request):
    """Render players list with their latest weekly stats (if any)."""
    qs = (
        Player.objects.filter(active=True)
        .order_by("last_name", "first_name")
        .prefetch_related("weekly_stats__week")
    )

    def fantasy_points(stat_obj, player=None):
        if stat_obj is None:
            return None
        # Goalie scoring: win=5, save=0.75, goal against=-1
        if player and player.position == "G":
            return (
                stat_obj.wins * 5
                + stat_obj.saves * 0.75
                - stat_obj.goals_against
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

    # Determine which week to show: selected via query param, else most recent available
    selected_week = None
    week_id_param = request.GET.get("week_id")
    if week_id_param:
        try:
            selected_week = Week.objects.get(id=int(week_id_param))
        except (Week.DoesNotExist, ValueError):
            pass
    
    # If no valid week selected, default to most recent
    if selected_week is None:
        selected_week = Week.objects.order_by("-season", "-week_number").first()

    week_options = list(Week.objects.order_by("-season", "-week_number"))

    sort_field = request.GET.get("sort", "name")
    sort_dir = request.GET.get("dir", "asc")

    players_with_stats = []
    for p in qs:
        weekly = list(p.weekly_stats.all())
        
        # Find stat for the selected week (if any)
        stat_for_view = None
        if selected_week is not None:
            stat_for_view = next((s for s in weekly if s.week.id == selected_week.id), None)

        players_with_stats.append({
            "player": p,
            "latest_stat": stat_for_view,
            "fantasy_points": fantasy_points(stat_for_view, p),
        })

    def sort_key(item):
        player = item["player"]
        stat = item["latest_stat"]
        fpts = item["fantasy_points"]

        if sort_field == "number":
            return (player.number is None, player.number or 0, player.last_name, player.first_name)
        if sort_field == "position":
            return (player.position or "", player.last_name, player.first_name)
        if sort_field == "season":
            season_val = stat.week.season if stat else -1
            return (season_val, player.last_name, player.first_name)
        if sort_field == "week":
            week_val = stat.week.week_number if stat else -1
            season_val = stat.week.season if stat else -1
            return (season_val, week_val, player.last_name, player.first_name)
        if sort_field == "gp":
            val = stat.games_played if stat else None
            return (val is None, -(val or 0), player.last_name, player.first_name)
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
        # default: name
        return (player.last_name, player.first_name)

    reverse = sort_dir == "desc"
    players_with_stats.sort(key=sort_key, reverse=reverse)

    return render(
        request,
        "web/players.html",
        {
            "players": players_with_stats,
            "week_options": week_options,
            "selected_week": selected_week,
            "sort_field": sort_field,
            "sort_dir": sort_dir,
        },
    )


def _build_schedule(team_ids):
    teams_local = list(team_ids)
    n = len(teams_local)
    if n % 2 != 0:
        return []

    anchor = teams_local[0]
    rotate = teams_local[1:]

    def one_round(order_anchor, order_rot):
        weeks = []
        rot = order_rot[:]
        m = len(rot)
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
    else:
        teams = list(Team.objects.filter(league__is_active=True).order_by("id"))
    
    team_ids = [t.id for t in teams]
    weeks = _build_schedule(team_ids)

    id_to_team = {t.id: t for t in teams}

    def fantasy_points(stat_obj, player=None):
        if stat_obj is None:
            return None
        # Goalie scoring: win=5, save=0.75, goal against=-1
        if player and player.position == "G":
            return (
                stat_obj.wins * 5
                + stat_obj.saves * 0.75
                - stat_obj.goals_against
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

    # build rosters with fantasy points for the selected week
    team_rosters = {}
    team_totals = {}
    for team in teams:
        roster = team.roster_entries.select_related('player').filter(
            player__active=True
        ).order_by("player__last_name", "player__first_name")
        
        roster_data = []
        for roster_entry in roster:
            p = roster_entry.player
            stat = None
            if week_obj:
                stat = p.weekly_stats.filter(week=week_obj).first()
                if stat is None:
                    stat = p.weekly_stats.filter(week__week_number=selected_week_number).order_by("-week__season").first()
            fpts = fantasy_points(stat, p)
            roster_data.append({"player": p, "stat": stat, "fantasy_points": fpts})
        team_rosters[team.id] = roster_data
        team_totals[team.id] = sum((r["fantasy_points"] or 0) for r in roster_data if r["fantasy_points"] is not None)

    schedule_weeks = []
    for idx, games in enumerate(weeks, start=1):
        schedule_weeks.append(
            {
                "week_number": idx,
                "games": [
                    {
                        "home": id_to_team.get(a),
                        "away": id_to_team.get(b),
                        "home_roster": team_rosters.get(a, []),
                        "away_roster": team_rosters.get(b, []),
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
            # Goalie scoring: win=5, save=0.75, goal against=-1
            if player and player.position == "G":
                return (
                    stat_obj.wins * 5
                    + stat_obj.saves * 0.75
                    - stat_obj.goals_against
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
        players_by_team = defaultdict(list)
        for roster_entry in rosters:
            players_by_team[roster_entry.team_id].append(roster_entry.player)

        week_cache = {}
        standings_map = {
            t.id: {
                "team": t,
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "total_points": 0,
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
            for p in players_by_team.get(team_id, []):
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
    if league.teams.count() >= league.max_teams:
        messages.error(request, "This league is full.")
        return redirect("league_detail", league_id=league.id)
    
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
