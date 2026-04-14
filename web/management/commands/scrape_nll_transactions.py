"""
Management command to scrape NLL transactions from nll.com
"""
import requests
from django.core.management.base import BaseCommand
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
from web.models import NLLTransaction


def scrape_nll_transactions_task():
    """
    Scrape NLL transactions from nll.com
    Returns tuple of (count, scraped_html)
    """
    try:
        # Fetch the transactions page
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(
            'https://www.nll.com/news/transactions/',
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract JSON-LD structured data for all news articles
        transactions_found = []
        scripts = soup.find_all('script', {'type': 'application/ld+json'})
        
        for script in scripts:
            try:
                data = json.loads(script.string)
                
                # Handle graph format
                if isinstance(data, dict) and '@graph' in data:
                    items = data['@graph']
                elif isinstance(data, list):
                    items = data
                else:
                    items = [data]
                
                # Look for NewsArticle items
                items_list = items if isinstance(items, list) else [items]
                for item in items_list:
                    if isinstance(item, dict) and item.get('@type') == 'NewsArticle':
                        headline = item.get('headline', '').lower()
                        keywords = item.get('keywords', '').lower()
                        
                        # Check if this is a transaction-related article
                        if 'transaction' in headline or 'transaction' in keywords:
                            transactions_found.append(item)
            
            except (json.JSONDecodeError, AttributeError):
                continue
        
        # Save HTML for inspection
        with open('transactions_page.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return len(transactions_found), html_content
        
    except Exception as e:
        raise Exception(f'Error during scraping: {str(e)}')


class Command(BaseCommand):
    help = 'Scrape NLL transactions from nll.com'

    def add_arguments(self, parser):
        pass  # No arguments needed

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting NLL transactions scrape...'))
        
        try:
            count, html = scrape_nll_transactions_task()
            self.stdout.write(self.style.SUCCESS(f'Scraped {count} transaction articles'))
            self.stdout.write(self.style.SUCCESS('Saved page HTML to transactions_page.html for inspection'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during scraping: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())
