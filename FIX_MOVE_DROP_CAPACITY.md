# Fix: Restore Player Move/Drop Functionality

## Problem
Users reported being unable to move or drop players from full position groups. The issue occurred after adding position capacity validation.

## Root Causes

1. **Best Ball Redraft Leagues**: The `get_available_slots` view was showing all position options (O, D, G) without checking if positions were full, but the backend validation in `move_to_empty_slot` was rejecting moves to full positions
   - Result: Modal showed invalid options that backend would reject

2. **Transition Player Rule Not Applied**: The `allow_transition_in_goalies` league setting wasn't being checked in `get_available_slots`, only in the backend `move_to_empty_slot` action
   - Result: T players could see G slot option in modal even when not allowed, then backend rejects

3. **Unused Context Variable**: Code was calculating `position_capacities` and passing to template, but template wasn't using it (already reverted badge disable logic)

## Solution

### Changes to `web/views.py`

#### 1. Fixed Best Ball Redraft Capacity Check (lines 4599-4637)
- **Before**: Showed all position options (O, D, G) regardless of capacity
- **After**: Added capacity counting logic to only show positions with available slots
- **Impact**: Move modal now correctly excludes full positions for redraft best ball leagues

#### 2. Added Transition Rule to all League Types
- **Best Ball Dynasty** (lines 4571-4576): When showing G option for T players, now checks `league.allow_transition_in_goalies`
- **Best Ball Redraft** (lines 4619-4624): Same logic applied to redraft
- **Traditional** (lines 4496-4505): Updated `can_move_to` set logic to exclude G for T players when not allowed
- **Impact**: T players no longer see G slot option when league doesn't allow it

#### 3. Cleaned Up Unused Code (lines 729-773)
- Removed `position_capacities` calculation from context (lines 729-737)
- Removed `position_capacities` from render context (line 773)
- **Impact**: Reduces template context bloat, all capacity logic now in backend endpoint

#### 4. Kept Backend Validation
- `move_to_empty_slot` (lines 1271-1278) still validates capacity before accepting moves
- `check_roster_capacity` function correctly excludes current player from count
- **Impact**: Defense-in-depth - modal restricts options AND backend validates moves

## Technical Details

### How Capacity Checking Works
1. **get_available_slots endpoint**: 
   - Counts active players in each position (O: 3, D: 3, G: 1 max)
   - Excludes current player from count
   - Only shows position options with available slots

2. **move_to_empty_slot backend**:
   - Calls `check_roster_capacity(team, target_position, exclude_player=player)`
   - Uses `assigned_side` if set (for T players), otherwise `player.position`
   - Rejects move if target position is full

### Transition Player Logic
- **Default**: T players NOT allowed in G slots (`league.allow_transition_in_goalies=False`)
- **Allow_in GS → True**: T players can move to O, D, or G positions
- **Allow_in_G → False**: T players can only move to O or D positions
- Checked in both modal options (`get_available_slots`) and backend action validation

## Testing Plan

1. **Best Ball Redraft**: Try moving players to full positions
   - ✅ Modal should not show full positions
   - ✅ If somehow submitted, backend rejects with error

2. **Transition Restrictions**:
   - With `allow_transition_in_goalies=False`:
     - ✅ T player modal should NOT show G slot
     - ✅ Backend should reject G slot move
   - With `allow_transition_in_goalies=True`:
     - ✅ T player modal SHOULD show G slot (if room available)
     - ✅ Backend should accept G slot move

3. **Traditional Leagues**: Verify slot assignments still work correctly

4. **Swap vs Empty Slot**: Verify both swap options and empty slot options work

## Deployment
- Commit: `5fce8b7` - "Fix: Restore player move/drop functionality with proper capacity checks"
- No database migrations needed
- No template changes needed (reverted earlier)
- Ready for production deployment

## Related Context
- Issue: User couldn't move/drop players after capacity validation added
- Solution: Properly restrict modal options before reaching backend validation
- Key principle: Frontend modal should only show valid options, backend validates as safety layer
