"""
Management command to scrape NLL transactions from nll.com
"""
import requests
from django.core.management.base import BaseCommand
from bs4 import BeautifulSoup
import re
from datetime import datetime
from web.models import NLLTransaction, Player, Team as NLLTeam


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
        
        # Find transaction articles/items
        transactions = soup.find_all('article', class_=re.compile('article|post|transaction|news'))
        
        if not transactions:
            # Try alternate selectors
            transactions = soup.find_all('div', class_=re.compile('transaction|article-item|news-item'))
        
        if not transactions:
            # Fallback to all articles
            transactions = soup.find_all('article')
        
        count = len(transactions)
        
        # Save HTML to file for inspection
        with open('transactions_page.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return count, html_content
        
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
