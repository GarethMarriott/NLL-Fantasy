# NLL Fantasy League

Fantasy lacrosse league management system for the National Lacrosse League (NLL).

## Features

- Multi-league support - users can join and manage multiple fantasy leagues
- Player roster management with position validation (Offense, Defense, Goalie)
- Weekly stat tracking with automated imports from nllstats.com
- Fantasy points calculation:
  - **Field Players**: Goals×4 + Assists×2 + Loose Balls×2 + Caused Turnovers×3 + Blocked Shots×2 - Turnovers
  - **Goalies**: Wins×5 + Saves×0.75 - Goals Against
- League chat and transaction notifications
- Team standings and matchups
- Player search and statistics

## Setup

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run database migrations:
   ```bash
   python manage.py migrate
   ```

3. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```

4. Import initial team and player data (CSV format):
   - Teams: Upload via admin interface
   - Players: Upload via admin interface

5. Start the development server:
   ```bash
   python manage.py runserver
   ```

## Importing Weekly Stats

The system can automatically import weekly boxscore data from nllstats.com:

```bash
# Import all weeks for the current season (2026)
python manage.py fetch_nll_stats

# Import specific week
python manage.py fetch_nll_stats --week 1

# Import different season
python manage.py fetch_nll_stats --season 2025 --week 5

# Preview import without saving (dry run)
python manage.py fetch_nll_stats --dry-run --week 1
```

The command downloads data from https://nllstats.com/json/jsonfiles.zip (the same JSON data the website uses) and automatically:
- Creates Week records for each game week
- Imports player stats (goals, assists, loose balls, turnovers, etc.)
- Imports goalie stats (wins, saves, goals against)
- **Auto-creates new players** when they appear in the stats but aren't in the database yet
- Matches players by name to existing database records
- Determines player positions automatically (O/D/T/G) based on nllstats.com data

**Note**: New players are automatically added with their position detected from the stats data. If a player already exists, their stats are updated.

## Usage

1. **Create a League**: Users can create new leagues from the home page
2. **Create Teams**: Each league member creates their fantasy team
3. **Draft Players**: Assign players to roster positions (3 Offense, 3 Defense, 2 Goalies)
4. **Weekly Management**: Add/drop players, view matchups, check standings
5. **Import Stats**: Run the `fetch_nll_stats` command after each game week
6. **View Results**: Fantasy points automatically calculated based on weekly stats

## Admin Tasks

- Import new NLL teams and players via CSV upload in admin interface
- Manually adjust player positions if needed
- Create Week records (or use automated import)
- Monitor transaction notifications and league chat