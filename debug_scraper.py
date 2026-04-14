import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from bs4 import BeautifulSoup
import re

with open('transactions_page.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

# Find h3 tags (dates)
h3_tags = soup.find_all('h3')
print(f"Found {len(h3_tags)} h3 tags")

count = 0
for i, h3 in enumerate(h3_tags[:5]):
    date_text = h3.get_text(strip=True)
    print(f"\n{i+1}. Date: {date_text}")
    
    # Find next sibling
    next_elem = h3.find_next_sibling()
    
    if next_elem:
        print(f"   Next sibling: {next_elem.name} tag")
        if next_elem.name == 'p':
            # Get text from p
            text = next_elem.get_text(strip=True)[:100]
            print(f"   Content: {text}...")
            
            # Try to extract names
            from web.management.commands.scrape_nll_transactions import extract_player_names
            names = extract_player_names(next_elem.get_text())
            print(f"   Extracted names: {names if names else 'NONE'}")
            if names:
                count += 1
    else:
        print("   NO NEXT SIBLING")

print(f"\n\nTotal with extracted names: {count}")
