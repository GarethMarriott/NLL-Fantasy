import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, "/opt/shamrock-fantasy")
django.setup()
from web.models import League, Team
from django.contrib.auth.models import User

user = User.objects.get(username="ColtGnech")
print("\n=== LEAGUES FOR ColtGnech ===\n")

print("COMMISSIONER OF:")
for l in League.objects.filter(commissioner=user).order_by("id"):
    teams = Team.objects.filter(league=l).count()
    print(f"  ID: {l.id:2d} | {l.name:35s} | Season: {l.season} | Status: {l.status:18s} | Teams: {teams}")

print("\nOWNS TEAM IN:")
for l in League.objects.filter(teams__owner__user=user).distinct().order_by("id"):
    teams = Team.objects.filter(league=l).count()
    print(f"  ID: {l.id:2d} | {l.name:35s} | Season: {l.season} | Status: {l.status:18s} | Teams: {teams}")

print("\n\nALL LEAGUES BY NAME:")
all_names = sorted(set(League.objects.all().values_list("name", flat=True)))
for name in all_names:
    leagues = League.objects.filter(name=name).order_by("id")
    print(f"\n  '{name}':")
    for l in leagues:
        is_comm = "COMM" if l.commissioner == user else ""
        is_team = "TEAM" if League.objects.filter(id=l.id, teams__owner__user=user).exists() else ""
        teams = Team.objects.filter(league=l).count()
        print(f"    ID: {l.id:2d} | Season: {l.season} | Status: {l.status:18s} | Teams: {teams:2d} | {is_comm} {is_team}".strip())
