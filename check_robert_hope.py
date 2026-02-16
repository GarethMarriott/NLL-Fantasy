import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import WaiverClaim, Player

p = Player.objects.filter(first_name='Robert', last_name='Hope', number=18).first()

if p:
    claims = WaiverClaim.objects.filter(player_to_add=p).order_by('-created_at')
    print(f"Found {claims.count()} claims for Robert Hope #18\n")
    for c in claims[:5]:
        current_priority = c.team.waiver_priority
        print(f"Team: {c.team.name}")
        print(f"  League: {c.league.name}")
        print(f"  Claim Priority (snapshot): {c.priority}")
        print(f"  Current Priority: {current_priority}")
        print(f"  Status: {c.status}")
        print(f"  Submitted: {c.created_at}")
        print()
else:
    print('Player not found')
