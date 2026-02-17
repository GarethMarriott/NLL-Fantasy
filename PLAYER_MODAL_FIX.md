# Player Modal Schedule Week Ordering Fix

## Issue
The player detail modal (info popup) displayed weeks in incorrect order. Weeks like "Week 10" appeared before "Week 2" due to alphabetical sorting.

## Root Cause
The `player_detail_modal` view in `web/views/__init__.py` was using Python's `sorted()` function directly on the week keys:

```python
for week_key in sorted(stats_by_week.keys()):
```

Week keys are formatted as `"Week 1 (S2026)"`, `"Week 10 (S2026)"`, etc. 

When sorted alphabetically as strings:
- "Week 1..." comes after "Week 10..." because "1" < "10" lexicographically
- Correct order would be: Week 1, Week 2, ... Week 10, Week 11, ...
- Buggy order was: Week 1, Week 10, Week 11, ... Week 19, Week 2, Week 20, ...

## Solution
Modified the sorting to extract and compare week numbers numerically instead:

```python
# Sort by week number (numerically, not alphabetically)
# week_key format: "Week 1 (S2026)" -> extract week number
def extract_week_number(week_key):
    try:
        return int(week_key.split()[1])
    except (IndexError, ValueError):
        return 0

for week_key in sorted(stats_by_week.keys(), key=extract_week_number):
```

## Changes
- **File**: `web/views/__init__.py`
- **Function**: `player_detail_modal` (line 2520+)
- **Lines Modified**: 2520-2531
- **Change Type**: Sorting logic fix

## Testing
- Django system check: PASSED (no errors)
- Code syntax: VALID
- Git commit: `6e3270f` - "FIX: Player modal schedule week ordering - sort weeks numerically not alphabetically"

## Deployment
- Committed locally
- Pushed to GitHub on `main` branch
- **Status**: Ready for deployment to production server

## Expected Behavior After Fix
When opening the player info popup:
1. Weeks now display in chronological order: Week 1, Week 2, Week 3, ... Week 18
2. Playoff weeks appear at the end (if applicable)
3. All schedule data remains unchanged, only ordering fixed

## Notes
- The `extract_week_number()` function handles edge cases (malformed keys return 0)
- Upcoming weeks added after the loop are still in correct order
- The fix is backward compatible - no database changes or migrations needed
