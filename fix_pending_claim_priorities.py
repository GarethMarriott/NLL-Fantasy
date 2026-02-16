import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import WaiverClaim

# Get all PENDING claims
pending_claims = WaiverClaim.objects.filter(status=WaiverClaim.Status.PENDING)

print(f"Found {pending_claims.count()} pending claims\n")

for claim in pending_claims:
    old_priority = claim.priority
    new_priority = claim.team.waiver_priority
    
    if old_priority != new_priority:
        print(f"Updating {claim}")
        print(f"  Team: {claim.team.name}")
        print(f"  Old priority: {old_priority}")
        print(f"  New priority: {new_priority}")
        claim.priority = new_priority
        claim.save()
    else:
        print(f"OK: {claim.team.name} (priority {claim.priority})")

print("\nDone!")
