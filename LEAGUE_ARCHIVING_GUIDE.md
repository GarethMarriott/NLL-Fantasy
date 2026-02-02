# League Archiving & Renewal Guide

## Overview

The league archiving and renewal system allows commissioners to:
1. **Archive completed leagues** - Automatically or manually mark seasons as complete
2. **Renew leagues** - Create new seasons with identical settings and members

## How It Works

### Automatic Archiving

**Trigger:** January 1st at midnight (Celery Beat scheduled task)

The `archive_old_leagues()` task:
- Finds all active leagues
- Checks if playoff weeks have completed for the current season
- Sets `is_active = False` for completed leagues
- Preserves all historical data

### Manual League Renewal

**Access:** `/leagues/<league_id>/renew/` (Commissioner only)

The renewal process:
1. Commissioner views archived league
2. Navigates to "Renew League" page
3. Reviews what will be transferred
4. Confirms renewal
5. New league created with:
   - Fresh name: "[Original Name] - 2027"
   - Identical settings and scoring rules
   - New rosters (empty, ready for draft)
   - All previous team owners invited

## Detailed Features

### What Gets Renewed ✓

- **League Settings:**
  - Roster format (Best Ball or Traditional)
  - Max teams, roster size
  - Position slots (forwards, defense, goalies)
  - Playoff configuration (weeks, teams)
  - Waiver system (enabled/disabled)
  - Playoff reseeding rules

- **Scoring Rules:**
  - All player scoring settings (goals, assists, loose balls, etc.)
  - All goalie scoring settings (wins, saves, goals against, etc.)
  - Multi-game week scoring method

- **Members:**
  - All previous team owners invited to new league
  - Commissioner remains the same

### What Doesn't Renew ✗

- Team rosters (cleared for new draft)
- Waiver claims and trades
- Historical scores and statistics
- Current week assignments

### What's Preserved

- Original league remains archived
- All historical data accessible
- Historical statistics remain for reference
- Shows in user's "Archived Leagues" section

## Views and Templates

### Renewal View
- **File:** `web/views.py` - `renew_league()` function
- **Permission:** Commissioner only
- **Template:** `web/templates/web/renew_league.html`
- **Route:** `/leagues/<league_id>/renew/`

**Features:**
- Confirmation form to prevent accidental renewal
- Summary of current league settings
- List of what will be renewed
- Explanation of process

### Updated League List
- **File:** `web/views.py` - `league_list()` function
- **Changes:** 
  - Separates active and archived leagues
  - User's leagues show both active and archived
  - Public browse only shows active leagues
  - Allows searching archived leagues by code

## Code Implementation

### Tasks (`web/tasks.py`)

#### `archive_old_leagues()`
```python
@shared_task
def archive_old_leagues():
    # Marks completed leagues as inactive
    # Called: January 1st (configurable in celery.py)
```

#### `renew_league(old_league_id, new_season=None)`
```python
def renew_league(old_league_id, new_season=None):
    # Creates new league with same settings
    # Called by: renew_league view
    # Returns: New League object or None
```

### Models (`web/models.py`)

**League Model Fields:**
- `is_active` (Boolean) - Tracks if league is active or archived
- All scoring and configuration fields are copied to new leagues

### Forms (`web/forms.py`)

#### `LeagueRenewalForm`
- Single checkbox confirmation field
- Dynamic label showing league name and next season
- Prevents accidental renewals

### URLs (`web/urls.py`)

```python
path('leagues/<int:league_id>/renew/', renew_league, name='renew_league')
```

### Celery Schedule (`config/celery.py`)

```python
'archive-old-leagues': {
    'task': 'web.tasks.archive_old_leagues',
    'schedule': crontab(month_of_year='1', day_of_month=1, hour=0, minute=0),
}
```

## Database Impact

### No Migration Required
The `is_active` field already exists on the League model, so no new migration is needed.

### Data Preservation
- Old leagues remain in database with `is_active=False`
- All foreign keys intact
- Historical rosters, trades, waivers, stats all preserved
- New league has separate primary key

## Testing

### Test Archive Task
```bash
python manage.py shell
from web.tasks import archive_old_leagues
archive_old_leagues()  # Test execution
```

### Test Renewal Function
```bash
python manage.py shell
from web.tasks import renew_league
from web.models import League
old_league = League.objects.first()
new_league = renew_league(old_league.id)
print(f"Created: {new_league.name}")
```

### Test UI
1. Create test league and mark `is_active=False` in admin
2. Log in as commissioner
3. Navigate to archived league
4. Click "Renew League"
5. Fill form and submit
6. Verify new league created with same settings

## Configuration

### Change Archive Schedule
Edit `config/celery.py`:
```python
'archive-old-leagues': {
    'schedule': crontab(month_of_year='1', day_of_month=1, hour=0, minute=0),
}
```

**Examples:**
- First of each month: `crontab(day_of_month=1, hour=0, minute=0)`
- Daily at 2 AM: `crontab(hour=2, minute=0)`
- Specific date: `crontab(month_of_year='1', day_of_month=1, hour=0, minute=0)`

### Automatic Season Year
Renewal defaults to next calendar year. Override in code:
```python
new_league = renew_league(league_id, new_season=2027)
```

## Error Handling

Both functions include comprehensive error logging:
- League not found
- Database errors
- Invalid parameters

Check Celery logs for errors:
```bash
celery -A config worker --loglevel=info
```

## Future Enhancements

Potential improvements:
- UI button on league detail page for commissioners
- Bulk renewal (multiple leagues at once)
- Import team members from previous league (optional checkbox)
- Schedule automatic renewal without commissioner action
- Copy draft settings from previous season
- Pre-populate team names based on historical rosters

## Troubleshooting

### Archive Task Not Running
1. Verify Celery Beat is running: `celery -A config beat`
2. Check logs for errors
3. Manually run: `python manage.py shell` then `from web.tasks import archive_old_leagues; archive_old_leagues()`

### Renewal Creating Duplicate League
- Database transaction issue - check logs
- Verify League with same name doesn't exist
- Check unique_id constraint

### New League Not Showing in UI
- Verify `is_active=True` on new league
- Check filters in league_list view
- Verify user permissions/associations

## Related Documentation

- [League Management](DEPLOYMENT_GUIDE.md#league-management)
- [Celery Tasks](DEPLOYMENT_GUIDE.md#celery-tasks)
- [Database Schema](PRODUCTION_SETUP_COMPLETE.md#database-schema)
