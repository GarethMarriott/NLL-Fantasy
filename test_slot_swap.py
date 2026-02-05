#!/usr/bin/env python
"""
Test script to verify actual slot swapping works with proper slot assignments
Run with: Get-Content test_slot_swap.py | python manage.py shell
"""

from web.models import Team, League, Player, Roster, Week
from django.utils import timezone
from datetime import datetime, timedelta

# Setup test data
def test_slot_swap():
    print("\n=== Testing Actual Slot Swapping ===\n")
    
    # Check if we have test data
    leagues = League.objects.all()[:1]
    if not leagues:
        print("No leagues found. Please ensure test data exists.")
        return
    
    league = leagues[0]
    teams = Team.objects.filter(league=league)[:1]
    if not teams:
        print("No teams found. Please ensure test data exists.")
        return
    
    team = teams[0]
    print(f"Testing with Team: {team.name} in League: {league.name}\n")
    
    # First, assign some players to actual slots (not bench)
    roster = Roster.objects.filter(
        team=team,
        league=league,
        week_dropped__isnull=True
    ).select_related('player').order_by('id')
    
    roster_list = list(roster)
    
    # Assign first 7 players to starter slots
    slot_assignments = [
        'starter_o1', 'starter_o2', 'starter_o3',
        'starter_d1', 'starter_d2', 'starter_d3',
        'starter_g'
    ]
    
    for i, (roster_entry, slot) in enumerate(zip(roster_list[:7], slot_assignments)):
        roster_entry.slot_assignment = slot
        roster_entry.save()
    
    # Refresh from DB
    roster = Roster.objects.filter(
        team=team,
        league=league,
        week_dropped__isnull=True
    ).select_related('player').order_by('slot_assignment')
    
    print(f"After assigning starter slots:")
    for r in roster:
        print(f"  - {r.player.last_name} ({r.player.get_position_display()}) in slot {r.slot_assignment}")
    
    # Find two players to swap
    starter_slots = list(Roster.objects.filter(
        team=team,
        league=league,
        week_dropped__isnull=True,
        slot_assignment__startswith='starter_'
    ).select_related('player').order_by('slot_assignment'))[:2]
    
    if len(starter_slots) < 2:
        print("\nNot enough starters to test swap.")
        return
    
    player1 = starter_slots[0]
    player2 = starter_slots[1]
    
    print(f"\nSwapping:")
    print(f"  Player 1: {player1.player.last_name} ({player1.player.position}) from slot {player1.slot_assignment}")
    print(f"  Player 2: {player2.player.last_name} ({player2.player.position}) from slot {player2.slot_assignment}")
    
    # Store original slots
    original_slot1 = player1.slot_assignment
    original_slot2 = player2.slot_assignment
    
    # Perform the swap
    player1.slot_assignment, player2.slot_assignment = player2.slot_assignment, player1.slot_assignment
    player1.save()
    player2.save()
    
    print(f"\nAfter swap (in memory):")
    print(f"  Player 1: {player1.player.last_name} to slot {player1.slot_assignment}")
    print(f"  Player 2: {player2.player.last_name} to slot {player2.slot_assignment}")
    
    # Refresh from database to verify persistence
    player1_db = Roster.objects.get(id=player1.id)
    player2_db = Roster.objects.get(id=player2.id)
    
    print(f"\nAfter swap (from database):")
    print(f"  Player 1: {player1_db.player.last_name} in slot {player1_db.slot_assignment}")
    print(f"  Player 2: {player2_db.player.last_name} in slot {player2_db.slot_assignment}")
    
    # Verify the swap worked
    if player1_db.slot_assignment == original_slot2 and player2_db.slot_assignment == original_slot1:
        print("\n✓ SWAP SUCCESSFUL!")
    else:
        print("\n✗ SWAP FAILED!")
        print(f"  Expected P1 in {original_slot2}, got {player1_db.slot_assignment}")
        print(f"  Expected P2 in {original_slot1}, got {player2_db.slot_assignment}")
    
    # Swap back
    player1_db.slot_assignment, player2_db.slot_assignment = original_slot1, original_slot2
    player1_db.save()
    player2_db.save()
    print("\n✓ Swapped back to original")

# Run the test
test_slot_swap()
