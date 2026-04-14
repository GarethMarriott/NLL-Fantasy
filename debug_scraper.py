import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from bs4 import BeautifulSoup
import json

with open('/opt/shamrock-fantasy/transactions_page.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

scripts = soup.find_all('script', {'type': 'application/ld+json'})
print(f'Found {len(scripts)} JSON-LD scripts')

transaction_count = 0
for i, script in enumerate(scripts):
    try:
        data = json.loads(script.string)
        if isinstance(data, dict) and '@graph' in data:
            items = data['@graph']
        elif isinstance(data, list):
            items = data
        else:
            items = [data]
        
        for item in items if isinstance(items, list) else [items]:
            if isinstance(item, dict):
                article_type = item.get('@type')
                headline = item.get('headline', '').lower()
                keywords = item.get('keywords', '').lower()
                
                if article_type == 'NewsArticle':
                    print(f"\nArticle {transaction_count}: {item.get('headline', 'No title')[:60]}")
                    print(f"  Keywords: {keywords[:80]}")
                    print(f"  Has body: {'articleBody' in item}")
                    
                    is_transaction = (
                        'transaction' in headline or 
                        'transaction' in keywords or
                        'signed' in keywords or
                        'traded' in keywords
                    )
                    print(f"  Is transaction match: {is_transaction}")
                    if is_transaction:
                        transaction_count += 1
    except Exception as e:
        print(f"Error parsing script {i}: {e}")

print(f'\nTotal transaction articles found: {transaction_count}')
