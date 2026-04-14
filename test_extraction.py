import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

import re
from bs4 import BeautifulSoup

# Test with actual transaction texts
test_transactions = [
    "The Buffalo Bandits have placed Nick Weiss and Tehoka Nanticoke on the Injured Reserve List from the Active Roster.",
    "The Buffalo Bandits have placed Connor Farrell on the Active Roster from the Physically Unable to Perform List.",
    "The Colorado Mammoth have released Kai George from the Protected Player List.",
]

def extract_player_names(transaction_text):
    """Extract player names from transaction text"""
    names = []
    
    # First, find the section from "placed"/"released"/"signed" to the next key word
    patterns = [
        r'placed\s+([^on]+?)\s+on',  # Capture everything between "placed" and "on"
        r'released\s+([^from]+?)\s+(?:from|on)',  # Capture everything between "released" and "from/on"
        r'traded\s+([^to]+?)\s+to',  # Capture everything between "traded" and "to"
        r'signed\s+([^,\.]+?)(?:,|\.|\s+by|\s+to)',  # Capture everything between "signed" and next marker
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, transaction_text)
        for match in matches:
            # Split by " and " to handle multiple names
            parts = match.split(' and ')
            for part in parts:
                name = part.strip()
                # Clean up any extra spaces
                name = re.sub(r'\s+', ' ', name)
                if name and len(name) > 2 and 'the' not in name.lower() and name not in names:
                    names.append(name)
    
    return names

# Test extraction
for i, trans in enumerate(test_transactions):
    names = extract_player_names(trans)
    print(f"\nTransaction {i+1}: {trans[:80]}...")
    print(f"  Extracted names: {names}")
