# Game Scores Display - Implementation Complete

## Status
✅ **Template**: Fixed and displaying scores
✅ **View Logic**: Updated to pass scores to template
✅ **Database Schema**: Migration applied (0065_add_game_scores)
✅ **Fetch Logic**: Updated to extract and save scores

## What's Working
- Template correctly displays final scores for completed games
- Winning team score shown in green, losing team in gray
- Fallback to "Home @ Away" format for games without scores
- Status badge shows "Final" vs "Upcoming"

## Current Issue
⚠️ **Production games don't have scores** because:
1. Games were created with team IDs (896, 918) instead of names
2. Production fetch_nll_stats couldn't access NLL API to get scores
3. Cleanup worked locally but needs to run on production

## Solution Steps Completed
1. ✅ Created updated fetch_nll_stats logic to find and update existing games by:
   - First trying NLL game ID match
   - Then trying date + team name match
   - Finally trying date + team ID match (for old games)
2. ✅ Fixed template to display scores when available
3. ✅ Created utilities to convert team IDs to names and clean up duplicates
4. ✅ Deployed all code to production

## What Still Needs to Happen on Production

```bash
# 1. Update game team names (convert IDs to names)
cd /opt/shamrock-fantasy
./venv/bin/python fix_team_ids.py

# 2. Clean up any duplicate games
./venv/bin/python cleanup_games.py

# 3. Fetch NLL data with scores
./venv/bin/python manage.py fetch_nll_stats --season 2026

# 4. Restart Django
systemctl restart gunicorn
```

## Local Testing
All features tested and working correctly:
- Scores display properly when present
- Fallback to team matchup format when scores are None
- Winner/loser highlighting works
- Status badges display correctly

## Files Modified
- web/models.py - Added 4 score fields to Game model
- web/migrations/0065_add_game_scores.py - Schema migration
- web/management/commands/fetch_nll_stats.py - Enhanced game lookup and score extraction
- web/views/__init__.py - Added score fields to context
- web/templates/web/nll_schedule.html - Added score display logic
- Helper scripts:  fix_team_ids.py, cleanup_games.py, add_sample_scores.py
