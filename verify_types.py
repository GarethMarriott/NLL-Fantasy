import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from web.models import NLLTransaction
from django.db.models import Count

type_counts = NLLTransaction.objects.values('transaction_type').annotate(count=Count('id')).order_by('-count')
print('Transaction type breakdown:')
for t in list(type_counts):
    print(f"  {t['transaction_type']}: {t['count']}")

print('\nSample ACTIVATED (placed on Active Roster):')
for t in list(NLLTransaction.objects.filter(transaction_type='activated').values('player_name', 'details')[:3]):
    print(f"  {t['player_name']}: {t['details'][:75]}...")

print('\nSample INJURED_RESERVE (placed on Injured Reserve):')
for t in list(NLLTransaction.objects.filter(transaction_type='injured_reserve').values('player_name', 'details')[:3]):
    print(f"  {t['player_name']}: {t['details'][:75]}...")
