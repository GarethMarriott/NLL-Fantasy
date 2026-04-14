import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from web.management.commands.scrape_nll_transactions import scrape_nll_transactions_task
from web.models import NLLTransaction

# Run scraper
count, html = scrape_nll_transactions_task()
print(f"Scraper returned: {count} saved")

# Check database
db_count = NLLTransaction.objects.count()
print(f"Total in database: {db_count}")

# Show recent
if db_count > 0:
    print("\nRecent transactions:")
    for t in NLLTransaction.objects.order_by('-scraped_at')[:5]:
        print(f"  {t.transaction_date} | {t.player_name} | {t.transaction_type}")
else:
    print("\nNo transactions in database")
