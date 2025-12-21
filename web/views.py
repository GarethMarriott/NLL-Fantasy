from django.shortcuts import render

def home(request):
    return render(request, "web/index.html")

def about(request):
    return render(request, "web/about.html")

def teams(request):
    return render(request, "web/teams.html")

def players(request):
    return render(request, "web/players.html")

def schedule(request):
    return render(request, "web/schedule.html")

def standings(request):
    return render(request, "web/standings.html")