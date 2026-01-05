from django.shortcuts import render, get_object_or_404

from .models import Player, Team, Week
from django.shortcuts import redirect
from django.views.decorators.http import require_POST


def home(request):
    teams = Team.objects.all().order_by("name")
    return render(request, "web/index.html", {"teams": teams})


def about(request):
    return render(request, "web/about.html")


def teams(request):
    teams = (
        Team.objects.all().prefetch_related("players__weekly_stats__week")
    )

    # Build list of teams with players and each player's latest stat
    teams_data = []
    for t in teams:
        players = []
        for p in t.players.filter(active=True).order_by("last_name", "first_name"):
            weekly = list(p.weekly_stats.all())
            latest = None
            if weekly:
                latest = max(weekly, key=lambda s: (s.week.season, s.week.week_number))
            players.append({"player": p, "latest_stat": latest})
        teams_data.append({"team": t, "players": players})

    return render(request, "web/teams.html", {"teams": teams_data})


def team_detail(request, team_id):
    team = get_object_or_404(Team, id=team_id)

    players_by_position = {"O": [], "D": [], "G": [], "T": []}
    # Best-ball fantasy scoring derived from the raw stat fields
    def fantasy_points(stat_obj):
        if stat_obj is None:
            return None
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

    for p in team.players.filter(active=True).order_by("last_name", "first_name"):
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
                pts = fantasy_points(st)
                weekly_points.append(pts)
                if pts is not None:
                    total_points += pts
        else:
            weekly_points = [None] * 18

        entry = {"player": p, "latest_stat": latest, "weekly_points": weekly_points, "weeks_total": total_points}
        pos = getattr(p, "position", None)
        if pos in players_by_position:
            players_by_position[pos].append(entry)
        else:
            players_by_position["O"].append(entry)

    # Build slots with Transition eligible for both F and D
    offence_pool = players_by_position["O"]
    defence_pool = players_by_position["D"]
    transition_pool = players_by_position["T"]

    offence_slots = (offence_pool + transition_pool)[:6]
    remaining_transition = transition_pool[max(0, 6 - len(offence_pool)) :]
    defence_slots = (defence_pool + remaining_transition)[:6]
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
            "players_for_select": Player.objects.filter(active=True).order_by("last_name", "first_name"),
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

    if action == "add":
        player.team = team
        player.save()
    elif action == "drop":
        # only drop if the player is currently on this team
        if getattr(player, "team_id", None) == team.id:
            player.team = None
            player.save()

    return redirect("team_detail", team_id=team.id)


def players(request):
    """Render players list with their latest weekly stats (if any)."""
    qs = (
        Player.objects.filter(active=True)
        .order_by("last_name", "first_name")
        .prefetch_related("weekly_stats__week")
    )

    def fantasy_points(stat_obj):
        if stat_obj is None:
            return None
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
    if request.GET.get("week_id"):
        try:
            selected_week = Week.objects.get(id=int(request.GET["week_id"]))
        except (Week.DoesNotExist, ValueError):
            selected_week = None
    if selected_week is None:
        selected_week = Week.objects.order_by("-season", "-week_number").first()

    week_options = list(Week.objects.order_by("-season", "-week_number"))

    sort_field = request.GET.get("sort", "name")
    sort_dir = request.GET.get("dir", "asc")

    players_with_stats = []
    for p in qs:
        weekly = list(p.weekly_stats.all())
        latest = None
        if weekly:
            latest = max(weekly, key=lambda s: (s.week.season, s.week.week_number))
        stat_for_view = None
        if selected_week is not None:
            stat_for_view = next((s for s in weekly if s.week_id == selected_week.id), None)
        if stat_for_view is None:
            stat_for_view = latest

        players_with_stats.append({
            "player": p,
            "latest_stat": stat_for_view,
            "fantasy_points": fantasy_points(stat_for_view),
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
    teams = list(Team.objects.order_by("id"))
    team_ids = [t.id for t in teams]
    weeks = _build_schedule(team_ids)

    id_to_team = {t.id: t for t in teams}

    def fantasy_points(stat_obj):
        if stat_obj is None:
            return None
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
        roster = []
        for p in team.players.filter(active=True).order_by("last_name", "first_name"):
            stat = None
            if week_obj:
                stat = p.weekly_stats.filter(week=week_obj).first()
                if stat is None:
                    stat = p.weekly_stats.filter(week__week_number=selected_week_number).order_by("-week__season").first()
            fpts = fantasy_points(stat)
            roster.append({"player": p, "stat": stat, "fantasy_points": fpts})
        team_rosters[team.id] = roster
        team_totals[team.id] = sum((r["fantasy_points"] or 0) for r in roster if r["fantasy_points"] is not None)

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
    teams = list(Team.objects.order_by("name"))
    team_ids = [t.id for t in teams]
    weeks = _build_schedule(team_ids)

    def fantasy_points(stat_obj):
        if stat_obj is None:
            return None
        return (
            stat_obj.goals * 4
            + stat_obj.assists * 2
            + stat_obj.loose_balls * 2
            + stat_obj.caused_turnovers * 3
            + stat_obj.blocked_shots * 2
            - stat_obj.turnovers
        )

    # prefetch players once
    from collections import defaultdict

    players = (
        Player.objects.filter(active=True, team__in=teams)
        .select_related("team")
        .prefetch_related("weekly_stats__week")
    )
    players_by_team = defaultdict(list)
    for p in players:
        players_by_team[p.team_id].append(p)

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
            pts = fantasy_points(stat)
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

    return render(
        request,
        "web/standings.html",
        {
            "standings": standings_list,
        },
    )