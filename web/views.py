from django.shortcuts import render

from .models import Player


def home(request):
    return render(request, "web/index.html")


def about(request):
    return render(request, "web/about.html")


def teams(request):
    return render(request, "web/teams.html")


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