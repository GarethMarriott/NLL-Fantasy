"""
Management command to scrape NLL transactions from nll.com
"""
import requests
from django.core.management.base import BaseCommand
from bs4 import BeautifulSoup
import re
from datetime import datetime
from web.models import NLLTransaction


def scrape_nll_transactions_task():
    """
    Scrape NLL transactions from nll.com using BeautifulSoup
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
        seen_urls = set()
        
        # Find all h3 tags (dates)
        h3_tags = soup.find_all('h3')
        
        for h3 in h3_tags:
            try:
                # Get the date from h3
                date_text = h3.get_text(strip=True)
                transaction_date = parse_date(date_text)
                
                # Find the next p tags after this h3 (transaction details)
                next_elem = h3.find_next_sibling()
                
                while next_elem and next_elem.name == 'p':
                    # Each p tag contains multiple transactions separated by <br>
                    # Split content by <br> to get individual transactions
                    br_parts = next_elem.decode_contents().split('<br />')
                    
                    for part in br_parts:
                        # Clean up the transaction text
                        transaction_text = BeautifulSoup(part, 'html.parser').get_text(strip=True)
                        
                        if not transaction_text or len(transaction_text) < 15:
                            continue
                        
                        # Skip if doesn't look like a transaction
                        if not any(word in transaction_text.lower() for word in ['have', 'placed', 'released', 'signed', 'traded']):
                            continue
                        
                        # Parse transaction details
                        player_names = extract_player_names(transaction_text)
                        
                        # Only process if we found actual player names
                        if not player_names:
                            continue
                        
                        team_names = extract_team_names(transaction_text)
                        transaction_type = extract_transaction_type(transaction_text)
                        
                        # Save each transaction
                        for player_name in player_names:
                            if not player_name:
                                continue
                            
                            # Create unique URL for this transaction
                            url_unique = f"https://www.nll.com/news/transactions/#{transaction_date}_{player_name.replace(' ', '_')}"
                            
                            if url_unique not in seen_urls:
                                seen_urls.add(url_unique)
                                
                                # Get team info
                                from_team, to_team = extract_teams_from_text(transaction_text, team_names)
                                
                                # Create or get transaction
                                transaction, created = NLLTransaction.objects.get_or_create(
                                    nll_url=url_unique,
                                    player_name=player_name,
                                    transaction_date=transaction_date,
                                    defaults={
                                        'transaction_type': transaction_type,
                                        'from_team': from_team,
                                        'to_team': to_team,
                                        'details': transaction_text[:500],
                                        'scraped_at': datetime.now(),
                                    }
                                )
                                
                                if created:
                                    transactions_saved += 1
                    
                    next_elem = next_elem.find_next_sibling()
            
            except Exception as e:
                continue
        
        # Save HTML for inspection
        with open('transactions_page.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return transactions_saved, html_content
        
    except Exception as e:
        raise Exception(f'Error during scraping: {str(e)}')


def extract_player_names(transaction_text):
    """Extract player names from transaction text with robust validation"""
    names = []
    
    # Patterns that capture everything between action and next keyword
    patterns = [
        r'placed\s+(.+?)\s+on\s+(?:the|their)',  # "placed X on the..."
        r'released\s+(.+?)\s+from\s+', # "released X from..."
        r'traded\s+(.+?)\s+(?:to|for|with)',  # "traded X to/for/with..."
        r'signed\s+(.+?)(?:\s+(?:on|to|by|to a)|,|\.)',  # "signed X on/to/by..."
        r'waived\s+(.+?)\s+(?:by|on)',  # "waived X by/on..."
        r'(?:have\s+)?(?:reassigned|activated|recalled|released)\s+(.+?)\s+(?:from|to)',  # reassigned/activated
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, transaction_text, re.IGNORECASE)
        for match in matches:
            # Split by " and " to handle multiple names
            parts = match.split(' and ')
            for part in parts:
                name = clean_and_validate_name(part)
                if name and name not in names:
                    names.append(name)
    
    return names


def clean_and_validate_name(name_str):
    """Clean and validate a potential player name"""
    # Strip whitespace
    name = name_str.strip()
    
    # Remove "Practice Player" prefix and similar identifiers
    name = re.sub(r'^practice\s+player\s+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^injured\s+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^draft\s+list\s+', '', name, flags=re.IGNORECASE)
    
    # Clean up extra spaces
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Filter out common non-name keywords/phrases
    exclude_words = [
        'the', 'a', 'on', 'to', 'from', 'roster', 'list', 'team', 'by',
        'agreement', 'year', 'rights', 'waiver', 'wire', 'draft', 'injured',
        'coach', 'staff', 'assignable', 'player', 'assign', 'one', 'two',
        'three', 'contract', 'claim', 'trade', 'reassign', 'activate', 'recall'
    ]
    
    name_lower = name.lower()
    if name_lower in exclude_words or any(name_lower == word for word in exclude_words):
        return None
    
    # Must have at least 2 parts (first and last name)
    parts = name.split()
    if len(parts) < 2:
        return None
    
    # Each part should start with uppercase or be a single letter
    for part in parts:
        if not part or not part[0].isupper():
            return None
    
    # Must be reasonable length (not too short, not too long)
    if len(name) < 4 or len(name) > 50:
        return None
    
    # Reject if contains numbers (invalid name)
    if any(char.isdigit() for char in name):
        return None
    
    # Reject if contains special characters (except hyphens and apostrophes which are valid in names)
    if not re.match(r"^[a-zA-Z\s\-\']+$", name):
        return None
    
    # Reject if it looks like a sentence fragment (too many words)
    if len(parts) > 4:
        return None
    
    return name


def extract_team_names(transaction_text):
    """Extract team names from transaction text"""
    # Common NLL team names
    nll_teams = [
        'Buffalo Bandits', 'Georgia Swarm', 'Las Vegas Desert Dogs', 'New York Knights',
        'San Diego Seals', 'Toronto Rock', 'Colorado Mammoth', 'Albany FireWolves',
        'Ottawa Titans', 'Calgary Roughnecks', 'Rochester Knighthawks',
    ]
    
    found_teams = []
    for team in nll_teams:
        if team in transaction_text:
            found_teams.append(team)
    
    return found_teams


def extract_teams_from_text(transaction_text, team_list):
    """Extract from_team and to_team based on context"""
    from_team = ''
    to_team = ''
    
    if not team_list:
        return from_team, to_team
    
    # First team mentioned is usually the source team
    if team_list:
        from_team = team_list[0]
    
    # Second team mentioned is usually the destination
    if len(team_list) > 1:
        to_team = team_list[1]
    
    # Handle "to" or "from" keywords
    if ' to ' in transaction_text and len(team_list) > 1:
        parts = transaction_text.split(' to ')
        if len(parts) >= 2:
            to_team = team_list[-1] if team_list else to_team
    
    return from_team, to_team


def extract_transaction_type(text):
    """Extract transaction type from text with more robust pattern matching"""
    text_lower = text.lower()
    
    # Check for different transaction types in order of specificity
    # For placed transactions, check what comes AFTER "placed"
    if 'placed' in text_lower:
        # "placed ON the Active Roster FROM the Injured Reserve" = activation
        if 'placed' in text_lower and 'on the active roster' in text_lower:
            return 'activated'
        # "placed ON the Injured Reserve FROM the Active Roster" = injured reserve
        elif 'placed' in text_lower and ('on the injured reserve' in text_lower or 'on injured reserve' in text_lower):
            return 'injured_reserve'
    
    # Check for other activation keywords
    if any(word in text_lower for word in ['activated', 'recalled', 'returned', 'restored to active']):
        return 'activated'
    
    # Other transaction types
    if 'released' in text_lower:
        return 'released'
    elif 'traded' in text_lower:
        return 'traded'
    elif 'waived' in text_lower:
        return 'waived'
    elif 'reassigned' in text_lower or ('placed' in text_lower and 'nhl' in text_lower):
        return 'reassigned'
    elif 'retired' in text_lower:
        return 'retired'
    elif 'signed' in text_lower:
        return 'signed'
    else:
        return 'other'


def parse_date(date_str):
    """Parse date string to date object"""
    try:
        if not date_str:
            return datetime.now().date()
        
        # Try common formats
        formats = [
            '%B %d, %Y',      # April 11, 2026
            '%b %d, %Y',      # Apr 11, 2026
            '%m/%d/%Y',
            '%m-%d-%Y',
            '%Y-%m-%d',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue
        
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
