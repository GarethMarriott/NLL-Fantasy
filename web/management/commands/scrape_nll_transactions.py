"""
Management command to scrape NLL transactions from nll.com
"""
import requests
from django.core.management.base import BaseCommand
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
from web.models import NLLTransaction, Player, Team as NLLTeam


def scrape_nll_transactions_task():
    """
    Scrape NLL transactions from nll.com using JSON-LD structured data
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
        
        # Extract JSON-LD structured data
        transactions_count = 0
        
        # Find all JSON-LD scripts
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
                
                # Look for NewsArticle items with transaction-related content
                for item in items if isinstance(items, list) else [items]:
                    if isinstance(item, dict):
                        # Check if this is a transaction article
                        article_type = item.get('@type')
                        headline = item.get('headline', '').lower()
                        keywords = item.get('keywords', '').lower()
                        description = item.get('description', '').lower()
                        
                        is_transaction = (
                            article_type == 'NewsArticle' and
                            ('transaction' in headline or 
                             'transaction' in keywords or
                             'transaction' in description or
                             'signed' in description or
                             'traded' in description or
                             'released' in description)
                        )
                        
                        if is_transaction:
                            # Extract transaction details if available
                            article_body = item.get('articleBody', '')
                            
                            # Try to create transaction record from article data
                            if article_body:
                                # Parse transaction from article body
                                parse_and_save_transaction(
                                    headline=item.get('headline', 'Transaction'),
                                    body=article_body,
                                    date=item.get('datePublished', datetime.now().isoformat()),
                                    url=item.get('url', 'https://www.nll.com/news/transactions/')
                                )
                                transactions_count += 1
            
            except json.JSONDecodeError:
                continue
        
        # Fallback: Find article elements if JSON-LD didn't give us transactions
        if transactions_count == 0:
            # Try to parse HTML structure
            articles = soup.find_all(['article', 'div'], class_=re.compile('post|item|article'))
            transactions_count = len(articles)
        
        # Save HTML to file for inspection
        with open('transactions_page.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return transactions_count, html_content
        
    except Exception as e:
        raise Exception(f'Error during scraping: {str(e)}')


def parse_and_save_transaction(headline, body, date, url):
    """
    Parse transaction details from article headline and body
    and save to database
    """
    try:
        # Extract key information from headline and body
        transaction_type = extract_transaction_type(body)
        player_info = extract_player_info(body)
        team_info = extract_team_info(body)
        
        if player_info:
            # Create transaction record
            NLLTransaction.objects.get_or_create(
                nll_url=url,
                defaults={
                    'transaction_date': parse_date(date),
                    'transaction_type': transaction_type,
                    'player_name': player_info.get('name', ''),
                    'from_team': team_info.get('from', ''),
                    'to_team': team_info.get('to', ''),
                    'details': body[:500],  # Store first 500 chars of details
                    'scraped_at': datetime.now(),
                }
            )
    except Exception as e:
        pass  # Don't fail if we can't save one transaction


def extract_transaction_type(text):
    """Extract transaction type from text (Signed, Traded, Released, etc.)"""
    text_lower = text.lower()
    if 'signed' in text_lower:
        return 'Signed'
    elif 'traded' in text_lower:
        return 'Traded'
    elif 'released' in text_lower:
        return 'Released'
    elif 'waived' in text_lower:
        return 'Waived'
    elif 'reassigned' in text_lower:
        return 'Reassigned'
    elif 'activated' in text_lower:
        return 'Activated'
    elif 'retire' in text_lower:
        return 'Retired'
    return 'Transaction'


def extract_player_info(text):
    """Extract player name from transaction text"""
    # Look for patterns like "Player Name signed..." or "Player Name was traded..."
    # This is a simple heuristic - may need refinement
    match = re.search(r'^([A-Z][a-z]+\s+[A-Z][a-z]+)', text)
    if match:
        return {'name': match.group(1)}
    return None


def extract_team_info(text):
    """Extract team information from transaction text"""
    # This would need to be refined based on actual transaction text format
    return {'from': '', 'to': ''}


def parse_date(date_str):
    """Parse date string to date object"""
    try:
        if isinstance(date_str, str):
            # Try to parse ISO format
            if 'T' in date_str:
                return datetime.fromisoformat(date_str.split('T')[0])
            # Try other common formats
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%B %d, %Y']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
        return datetime.now().date()
    except:
        return datetime.now().date()


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
