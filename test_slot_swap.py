#!/usr/bin/env python
"""
Comprehensive test of slot swapping and display ordering
Run with: Get-Content test_slot_swap.py | python manage.py shell
"""

from web.models import Team, League, Player, Roster, Week
from django.utils import timezone
from datetime import datetime, timedelta

def test_comprehensive_swap():
    print("\n=== Comprehensive Slot Swap & Display Test ===\n")
    
    # Get test data
    leagues = League.objects.all()[:1]
    if not leagues:
        print("No leagues found")
        return
    
    league = leagues[0]
    teams = Team.objects.filter(league=league)[:1]
    if not teams:
        print("No teams found")
        return
    
    team = teams[0]
    print(f"Team: {team.name} in League: {league.name} ({league.roster_format} format)\n")
    
    # Get all roster entries
    roster = list(Roster.objects.filter(
        team=team,
        league=league,
        week_dropped__isnull=True
    ).select_related('player').order_by('id'))
    
    print(f"Total roster size: {len(roster)}")
    print("\nBefore swap:")
    print("ID | Name             | Position | Slot        ")
    print("-" * 50)
    for r in roster:
        print(f"{r.id:2d} | {r.player.last_name:15} | {r.player.position:8} | {r.slot_assignment}")
    
    # Find two starter players to swap
    starters = [r for r in roster if r.slot_assignment.startswith('starter_')]
    if len(starters) < 2:
        print("\nNot enough starters to test swap")
        return
    
    player1 = starters[0]
    player2 = starters[1]
    
    print(f"\n\nSwapping:")
    print(f"  {player1.player.last_name} from {player1.slot_assignment}")
    print(f"  {player2.player.last_name} from {player2.slot_assignment}")
    
    # Perform swap
    orig_slot1 = player1.slot_assignment
    orig_slot2 = player2.slot_assignment
    
    player1.slot_assignment = orig_slot2
    player2.slot_assignment = orig_slot1
    player1.save()
    player2.save()
    
    # Verify from DB
    player1_db = Roster.objects.get(id=player1.id)
    player2_db = Roster.objects.get(id=player2.id)
    
    print(f"\n\nAfter swap (from database):")
    print("ID | Name             | Position | Slot        ")
    print("-" * 50)
    for r in list(Roster.objects.filter(
        team=team,
        league=league,
        week_dropped__isnull=True
    ).select_related('player').order_by('id')):
        print(f"{r.id:2d} | {r.player.last_name:15} | {r.player.position:8} | {r.slot_assignment}")
    
    # Verify swap worked
    if (player1_db.slot_assignment == orig_slot2 and 
        player2_db.slot_assignment == orig_slot1):
        print("\n✓ SWAP SUCCESSFUL!")
    else:
        print(f"\n✗ SWAP FAILED - DB shows:")
        print(f"  P1: {player1_db.slot_assignment} (expected {orig_slot2})")
        print(f"  P2: {player2_db.slot_assignment} (expected {orig_slot1})")
    
    # Test ordering with slot assignment case
    from django.db.models import Case, When
    slot_order = [
        'starter_o1', 'starter_o2', 'starter_o3',
        'starter_d1', 'starter_d2', 'starter_d3',
        'starter_g',
        'bench'
    ]
    preserved = Case(*[When(slot_assignment=slot, then=pos) for pos, slot in enumerate(slot_order)])
    
    ordered_roster = list(Roster.objects.filter(
        team=team,
        league=league,
        week_dropped__isnull=True
    ).select_related('player').annotate(
        slot_order_val=preserved
    ).order_by("slot_order_val", "player__id"))
    
    print(f"\n\nOrdered display (after swap):")
    print("Order | Name             | Position | Slot        ")
    print("-" * 50)
    for i, r in enumerate(ordered_roster, 1):
        print(f"{i:5d} | {r.player.last_name:15} | {r.player.position:8} | {r.slot_assignment}")
    
    # Swap back to original
    player1_db.slot_assignment = orig_slot1
    player2_db.slot_assignment = orig_slot2
    player1_db.save()
    player2_db.save()
    print("\n✓ Swapped back to original")

# Run test
test_comprehensive_swap()
