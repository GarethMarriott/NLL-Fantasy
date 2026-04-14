#!/usr/bin/env python
"""
Fix Callum Jones transaction that was mislabeled as injured_reserve
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from web.models import NLLTransaction
from datetime import date

# Find and fix Callum Jones's transaction from November 21, 2025
try:
    transaction = NLLTransaction.objects.get(
        player_name='Callum Jones',
        transaction_date=date(2025, 11, 21)
    )
    
    print(f"Found transaction: {transaction}")
    print(f"Current type: {transaction.transaction_type}")
    print(f"Details: {transaction.details[:100]}...")
    
    # Update to 'signed' if it says injured_reserve
    if transaction.transaction_type == 'injured_reserve' and 'signed' in transaction.details.lower():
        transaction.transaction_type = 'signed'
        transaction.save()
        print(f"✓ Updated to: {transaction.transaction_type}")
    else:
        print("Transaction doesn't match expected pattern")
        
except NLLTransaction.DoesNotExist:
    print("Transaction not found")
except Exception as e:
    print(f"Error: {e}")
