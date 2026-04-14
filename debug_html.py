import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from bs4 import BeautifulSoup
import re

with open('transactions_page.html', 'r', encoding='utf-8') as f:
    content = f.read()
    soup = BeautifulSoup(content, 'html.parser')

# Look for news items 
news_items = soup.find_all(class_=re.compile('news-item|article-item|post-item|item-card'))
print(f"Found {len(news_items)} news/article items")
if news_items:
    for i, item in enumerate(news_items[:3]):
        print(f"\nItem {i+1}: {item.get('class')}")
        link = item.find('a')
        if link:
            print(f"  Link: {link.get_text(strip=True)[:80]}")

# Look for specific page structure - maybe in a table or list
# Check for news grid or archive
print(f"\n\nSearching in raw HTML for specific patterns...")
if '>Transactions<' in content:
    print("Found '>Transactions<' text marker")

# Search for specific transaction patterns in page
lines_with_trans = [line for line in content.split('\n') if 'transaction' in line.lower() and ('href' in line or 'title' in line)]
print(f"\nFound {len(lines_with_trans)} lines with 'transaction' and href/title")
for i, line in enumerate(lines_with_trans[:3]):
    print(f"  {i+1}. {line.strip()[:120]}")

# Look for content divs in main area
main = soup.find(class_=re.compile('main-content|page-content|content'))
if main:
    print(f"\nFound main content: {main.get('class')}")
    articles = main.find_all(class_=re.compile('post|article|item'))
    print(f"  Contains {len(articles)} post/article/item elements")
    
    # Look for news grid
    grid = main.find(class_=re.compile('grid|archive|list'))
    if grid:
        print(f"  Has grid/archive/list: {grid.get('class')}")

# Overall structure check
print(f"\n\nPage structure:")
print(f"Total size: {len(content)} bytes")
print(f"Number of <a> tags: {len(soup.find_all('a'))}")
print(f"Number of divs: { len(soup.find_all('div'))}")
print(f"Number of h3: {len(soup.find_all('h3'))}")

# Try finding a specific transaction title pattern
print("\n\nLooking for recent transaction headlines...")
for h3 in soup.find_all('h3')[:10]:
    text = h3.get_text(strip=True)
    if len(text) > 0 and len(text) < 150:
        print(f"  {text[:100]}")
