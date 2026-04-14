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
    Returns tuple of (count_saved, scraped_html)
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
        
        transactions_saved = 0
        
        # Extract transaction articles from the page
        # Find all article/post elements
        articles = soup.find_all(['article', 'div'], class_=lambda x: x and any(c in str(x) for c in ['post', 'article', 'entry']))
        
        if not articles:
            # Try finding by tag name
            articles = soup.find_all('article')
        
        for article in articles:
            try:
                # Extract title/headline
                title_elem = article.find(['h1', 'h2', 'h3', '.entry-title', '.post-title'])
                if not title_elem:
                    title_elem = article.find(['h1', 'h2', 'h3'])
                
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                
                # Skip if not transaction-related
                if 'transaction' not in title.lower():
                    continue
                
                # Extract date
                date_elem = article.find(['time', '.entry-date', '.post-date', 'span'], class_=lambda x: x and 'date' in str(x).lower())
                if date_elem:
                    date_text = date_elem.get_text(strip=True)
                    transaction_date = parse_date(date_text)
                else:
                    transaction_date = datetime.now().date()
                
                # Extract content/details
                content_elem = article.find(['div', 'p'], class_=lambda x: x and any(c in str(x) for c in ['content', 'entry-content', 'post-content']))
                if not content_elem:
                    content_elem = article.find(['div'])
                
                if content_elem:
                    content = content_elem.get_text(strip=True)
                else:
                    content = title
                
                # Extract transaction details from content
                transaction_type = extract_transaction_type(title, content)
                player_name = extract_player_name(title, content)
                from_team, to_team = extract_teams(content)
                
                # Only save if we found a player name
                if player_name:
                    # Check if already exists
                    article_url = article.find('a')
                    if article_url and article_url.get('href'):
                        nll_url = article_url['href']
                        if not nll_url.startswith('http'):
                            nll_url = 'https://www.nll.com' + nll_url
                    else:
                        nll_url = 'https://www.nll.com/news/transactions/'
                    
                    # Create or update transaction
                    transaction, created = NLLTransaction.objects.update_or_create(
                        nll_url=nll_url,
                        player_name=player_name,
                        transaction_date=transaction_date,
                        defaults={
                            'transaction_type': transaction_type,
                            'from_team': from_team,
                            'to_team': to_team,
                            'details': content[:500],
                            'scraped_at': datetime.now(),
                        }
                    )
                    
                    if created:
                        transactions_saved += 1
            
            except Exception as e:
                continue
        
        # Save HTML for inspection/debugging
        with open('transactions_page.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return transactions_saved, html_content
        
    except Exception as e:
        raise Exception(f'Error during scraping: {str(e)}')


def extract_transaction_type(title, content):
    """Extract transaction type from title and content"""
    text = (title + ' ' + content).lower()
    
    type_mapping = {
        'signed': 'signed',
        'trading': 'traded',
        'traded': 'traded',
        'released': 'released',
        'waived': 'waived',
        'reassigned': 'reassigned',
        'activated': 'activated',
        'retir': 'retired',
    }
    
    for keyword, ttype in type_mapping.items():
        if keyword in text:
            return ttype
    
    return 'other'


def extract_player_name(title, content):
    """Extract player name from title or content"""
    # Try to find player name pattern: Capitalized Word Capitalized Word
    patterns = [
        r'([A-Z][a-z]+\s+[A-Z][a-z]+)',  # First Last
        r'([A-Z][a-z]+)\s+([A-Z])\.?\s+([A-Z][a-z]+)',  # First M. Last
    ]
    
    # Check title first
    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            return match.group(0).strip()
    
    # Then check content
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return match.group(0).strip()
    
    return None


def extract_teams(content):
    """Extract team names from content"""
    # Common NLL team abbreviations and names
    nll_teams = [
        'Buffalo', 'Georgia', 'Las Vegas', 'New York', 'San Diego', 'Toronto',
        'Colorado', 'Albany', 'Bandits', 'Swarm', 'Knights', 'Riptide', 'Seals',
        'Rock', 'Panjas', 'Stealth', 'Mammoth', 'Roughnecks', 'Wings', 'Wings',
        'Blast', 'Faceoff',
    ]
    
    from_team = ''
    to_team = ''
    
    # Simple heuristic: look for team names
    for team in nll_teams:
        if team in content:
            # First occurrence is usually the original team
            if not from_team:
                from_team = team
            elif not to_team and team != from_team:
                to_team = team
    
    return from_team, to_team


def parse_date(date_str):
    """Parse date string to date object"""
    try:
        if not date_str:
            return datetime.now().date()
        
        # Clean up the date string
        date_str = date_str.strip()
        
        # Try common formats
        formats = [
            '%B %d, %Y',      # December 19, 2025
            '%b %d, %Y',      # Dec 19, 2025
            '%m/%d/%Y',       # 12/19/2025
            '%m-%d-%Y',       # 12-19-2025
            '%Y-%m-%d',       # 2025-12-19
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        # Fallback: use today's date
        return datetime.now().date()
    
    except Exception:
        return datetime.now().date()


class Command(BaseCommand):
    help = 'Scrape NLL transactions from nll.com'

    def add_arguments(self, parser):
        pass  # No arguments needed

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting NLL transactions scrape...'))
        
        try:
            count, html = scrape_nll_transactions_task()
            self.stdout.write(self.style.SUCCESS(f'Saved {count} new transaction(s) to database'))
            self.stdout.write(self.style.SUCCESS('Saved page HTML to transactions_page.html for inspection'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during scraping: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())
