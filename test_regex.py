import re

# Test with actual transaction texts
test_transactions = [
    "The Buffalo Bandits have placed Nick Weiss and Tehoka Nanticoke on the Injured Reserve List from the Active Roster.",
    "The Buffalo Bandits have placed Connor Farrell on the Active Roster from the Physically Unable to Perform List.",
    "The Colorado Mammoth have released Kai George from the Protected Player List.",
]

def test_pattern():
    for trans in test_transactions:
        print(f"\nText: {trans[:80]}...")
        
        # Try different patterns
        p1 = re.search(r'placed\s+(.+?)\s+on\s+the', trans)
        if p1:
            print(f"  Pattern 1 match: '{p1.group(1)}'")
        
        p2 = re.search(r'released\s+(.+?)\s+from\s+the', trans)
        if p2:
            print(f"  Pattern 2 match: '{p2.group(1)}'")
        
        p3 = re.search(r'placed\s+(.+?)\s+on', trans)
        if p3:
            print(f"  Pattern 3 match: '{p3.group(1)}'")

test_pattern()
