import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from web.models import NLLTransaction

print('ACTIVATED example:')
t = NLLTransaction.objects.filter(transaction_type='activated').first()
if t:
    print(f'  {t.player_name}: {t.details}')
else:
    print('  None found')

print('\nINJURED_RESERVE example:')
ir = NLLTransaction.objects.filter(transaction_type='injured_reserve').first()
if ir:
    print(f'  {ir.player_name}: {ir.details}')
else:
    print('  None found')
