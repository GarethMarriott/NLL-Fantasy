from django.shortcuts import render, get_object_or_404

from .models import Player, Team, Week


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

    players_by_position = {"O": [], "D": [], "G": []}
    # determine most recent season available for weekly breakdown
    recent_week = Week.objects.order_by("-season", "-week_number").first()
    season = recent_week.season if recent_week else None

    for p in team.players.filter(active=True).order_by("last_name", "first_name"):
        weekly = list(p.weekly_stats.all())
        latest = None
        if weekly:
            latest = max(weekly, key=lambda s: (s.week.season, s.week.week_number))

        # build per-week points for weeks 1..18 for the selected season
        weekly_points = []
        total_points = 0
        if season is not None:
            stats_by_week = {s.week.week_number: s for s in p.weekly_stats.filter(week__season=season)}
            for wk in range(1, 19):
                st = stats_by_week.get(wk)
                pts = st.points if st is not None else None
                weekly_points.append(pts)
                if pts:
                    total_points += pts
        else:
            weekly_points = [None] * 18

        entry = {"player": p, "latest_stat": latest, "weekly_points": weekly_points, "weeks_total": total_points}
        pos = getattr(p, "position", None)
        if pos in players_by_position:
            players_by_position[pos].append(entry)
        else:
            players_by_position["O"].append(entry)

    # Pad to fixed slot counts
    offence_slots = players_by_position["O"][:5]
    defence_slots = players_by_position["D"][:5]
    goalie_slots = players_by_position["G"][:2]

    while len(offence_slots) < 5:
        offence_slots.append(None)
    while len(defence_slots) < 5:
        defence_slots.append(None)
    while len(goalie_slots) < 2:
        goalie_slots.append(None)

    return render(
        request,
        "web/team_detail.html",
        {
            "team": team,
            "offence_slots": offence_slots,
            "defence_slots": defence_slots,
            "goalie_slots": goalie_slots,
            "week_range": list(range(1, 19)),
        },
    )


def players(request):
    """Render players list with their latest weekly stats (if any)."""
    qs = (
        Player.objects.filter(active=True)
        .order_by("last_name", "first_name")
        .prefetch_related("weekly_stats__week")
    )

    players_with_stats = []
    for p in qs:
        weekly = list(p.weekly_stats.all())
        latest = None
        if weekly:
            latest = max(weekly, key=lambda s: (s.week.season, s.week.week_number))
        players_with_stats.append({"player": p, "latest_stat": latest})

    return render(request, "web/players.html", {"players": players_with_stats})


def schedule(request):
    return render(request, "web/schedule.html")


def standings(request):
    return render(request, "web/standings.html")