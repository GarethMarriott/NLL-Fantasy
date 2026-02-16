import os
import django
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import WaiverClaim

claims = WaiverClaim.objects.filter(created_at__date=date(2026, 2, 14)).order_by('-created_at')
print(f"Found {claims.count()} claims from Feb 14, 2026\n")

for c in claims:
    print(f"Team: {c.team.name}")
    print(f"  Add: {c.player_to_add.first_name} {c.player_to_add.last_name} #{c.player_to_add.number}")
    print(f"  Drop: {c.player_to_drop.first_name if c.player_to_drop else 'None (roster has space)'}")
    print(f"  Claim Priority (snapshot): {c.priority}")
    print(f"  Current Team Priority: {c.team.waiver_priority}")
    print(f"  Status: {c.status}")
    print(f"  Submitted: {c.created_at}")
    print()
