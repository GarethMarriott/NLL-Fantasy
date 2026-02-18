"""
Django management command to fetch NLL player stats from nllstats.com JSON data

Usage:
    python manage.py fetch_nll_stats --season 2026 --week 1
    python manage.py fetch_nll_stats --season 2026  # fetches all weeks
    python manage.py fetch_nll_stats --dry-run  # preview without saving
"""

import requests
import json
import io
import zipfile
from datetime import datetime, timedelta
import pytz
from django.core.management.base import BaseCommand
from web.models import Player, Week, Game, PlayerGameStat


class Command(BaseCommand):
    help = 'Fetch NLL player statistics from nllstats.com JSON data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            default=2026,
            help='Season year (default: 2026)'
        )
        parser.add_argument(
            '--week',
            type=int,
            help='Specific week number to fetch (default: all weeks)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without saving to database'
        )

    def handle(self, *args, **options):
        season = options['season']
        week_filter = options['week']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        # Download the JSON data ZIP file (same source the website uses)
        zip_url = 'https://nllstats.com/json/jsonfiles.zip'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        try:
            self.stdout.write(f'Downloading data from {zip_url}...')
            response = requests.get(zip_url, headers=headers, timeout=60)
            response.raise_for_status()

            # Extract ZIP file in memory
            self.stdout.write('Extracting JSON files from ZIP...')
            zip_file = zipfile.ZipFile(io.BytesIO(response.content))

            # Read the necessary JSON files
            data = {}
            required_files = ['games.json', 'player_seasons.json', 'players.json', 'teams.json', 'game_scoring.json', 'jerseynumbers.json', 'schedule.json']
            
            for filename in zip_file.namelist():
                if filename in required_files:
                    with zip_file.open(filename) as f:
                        content = json.load(f)
                        # JSON structure: {"now": "timestamp", "games": [...]}
                        data_key = filename.replace('.json', '')
                        data[data_key] = content.get(data_key, [])
                        self.stdout.write(f'  * Loaded {len(data[data_key])} {data_key} records')
            
            # Check if we got the data we need
            if 'games' not in data or 'player_seasons' not in data:
                self.stdout.write(self.style.ERROR('Required data files not found in ZIP'))
                return

            # Process the stats
            stats_result = self.process_stats(data, season, week_filter, dry_run)
            
            # Process schedule (upcoming games)
            schedule_result = self.process_schedule(data, season, week_filter, dry_run)
            
            self.stdout.write(self.style.SUCCESS(
                f'\nStats - Created: {stats_result["created"]}, Updated: {stats_result["updated"]}, Skipped: {stats_result["skipped"]}'
            ))
            self.stdout.write(self.style.SUCCESS(
                f'Schedule - Created: {schedule_result["created"]}, Updated: {schedule_result["updated"]}'
            ))

        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f'Error fetching data: {e}'))
        except zipfile.BadZipFile as e:
            self.stdout.write(self.style.ERROR(f'Error extracting ZIP file: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Unexpected error: {e}'))
            import traceback
            traceback.print_exc()

    def process_stats(self, data, season_filter, week_filter, dry_run):
        """Process game and player data to create weekly stats"""
        stats_created = 0
        stats_updated = 0
        stats_skipped = 0

        # Filter games by season
        games = [g for g in data['games'] if g.get('season') == season_filter]
        self.stdout.write(f'\nProcessing {len(games)} games from {season_filter} season...')

        # Build player lookup dictionary by root_player_id
        players_by_id = {p['id']: p for p in data.get('players', [])}
        
        # Build team lookup dictionary by ID
        teams_by_id = {t['id']: t for t in data.get('teams', [])}
        
        # Build jersey number lookup dictionary by player_id
        jersey_numbers = {}
        for jersey in data.get('jerseynumbers', []):
            player_id = jersey.get('player_id')
            number = jersey.get('jersey_num')
            if player_id and number is not None:
                jersey_numbers[player_id] = number
        
        # Build rookie status lookup from player_seasons data
        # player_seasons is indexed by (player_id, season) and has a 'rookie' field
        rookie_by_player_season = {}
        for season_data in data.get('player_seasons', []):
            player_id = season_data.get('player_id')
            season = season_data.get('season')
            is_rookie = season_data.get('rookie', False)
            if player_id and season:
                rookie_by_player_season[(player_id, season)] = is_rookie
        
        self.stdout.write(f'Loaded rookie status for {len(rookie_by_player_season)} player-season combinations')

        # Process game_scoring data (this has individual player stats per game)
        game_scoring = data.get('game_scoring', [])
        
        if not game_scoring:
            self.stdout.write(self.style.WARNING('No game_scoring data found - stats may be incomplete'))
        else:
            self.stdout.write(f'Found {len(game_scoring)} total player stat records')
        
        # Group game_scoring by game_id and filter by season
        stats_by_game = {}
        for stat in game_scoring:
            # Only include stats for the target season
            if stat.get('season') != season_filter:
                continue
            
            game_id = stat.get('game_id')
            if game_id not in stats_by_game:
                stats_by_game[game_id] = []
            stats_by_game[game_id].append(stat)
        
        self.stdout.write(f'Found stats for {len(stats_by_game)} games in {season_filter} season')

        # Separate regular season and playoff games
        regular_games = [g for g in games if not g.get('playoffs')]
        playoff_games = [g for g in games if g.get('playoffs')]
        
        # Find the max regular season week to offset playoff weeks
        max_regular_week = max([g.get('week', 0) for g in regular_games]) if regular_games else 0
        
        self.stdout.write(f'Regular season weeks: 1-{max_regular_week}')
        if playoff_games:
            self.stdout.write(f'Playoff games found: {len(playoff_games)} games')

        # Group games by week to calculate week date ranges
        games_by_week = {}
        for game in games:
            week_number = game.get('week', 1)
            is_playoff = game.get('playoffs', False)
            
            # Offset playoff week numbers to come after regular season
            if is_playoff:
                week_number = max_regular_week + week_number
            
            if week_number not in games_by_week:
                games_by_week[week_number] = []
            games_by_week[week_number].append(game)

        # Create Week objects with proper date ranges
        weeks_created = {}
        if not dry_run:
            for week_number, week_games in games_by_week.items():
                # Parse game dates to find start and end of week
                game_dates = []
                # Check if any game in this week is a playoff game
                is_playoff_week = False
                for game in week_games:
                    date_str = game.get('dt')
                    if date_str:
                        try:
                            game_date = datetime.strptime(date_str, '%b %d, %Y %H:%M:%S').date()
                            game_dates.append(game_date)
                        except ValueError:
                            pass
                    
                    # Check for playoff indicators in the game data
                    # The 'playoffs' field is the definitive indicator
                    if game.get('playoffs') == True:
                        is_playoff_week = True
                
                if game_dates:
                    start_date = min(game_dates)
                    end_date = max(game_dates)
                else:
                    # Fallback if no dates found
                    start_date = datetime(season_filter, 1, 1).date()
                    end_date = start_date + timedelta(days=7)
                
                week, created = Week.objects.get_or_create(
                    season=season_filter,
                    week_number=week_number,
                    defaults={
                        'start_date': start_date,
                        'end_date': end_date,
                        'is_playoff': is_playoff_week
                    }
                )
                
                # Update is_playoff field for existing weeks if it changed
                if not created and week.is_playoff != is_playoff_week:
                    week.is_playoff = is_playoff_week
                    week.save()
                
                weeks_created[week_number] = week
                playoff_indicator = " (PLAYOFF)" if is_playoff_week else ""
                if created:
                    self.stdout.write(f'Created Week {week_number}: {start_date} to {end_date}{playoff_indicator}')
                elif week.is_playoff != is_playoff_week:
                    self.stdout.write(f'Updated Week {week_number} playoff status{playoff_indicator}')

        # Process each game and create per-game stats
        for game in games:
            game_id = game.get('id')
            week_number = game.get('week', 1)
            is_playoff = game.get('playoffs', False)
            
            # Offset playoff week numbers to match what we stored
            if is_playoff:
                week_number = max_regular_week + week_number
            game_date_str = game.get('dt')
            
            # Skip if filtering by week and this isn't it
            if week_filter and week_number != week_filter:
                continue

            # Get Week object and create Game object
            if not dry_run:
                week = weeks_created.get(week_number)
                if not week:
                    continue
                
                # Parse game date
                try:
                    game_date = datetime.strptime(game_date_str, '%b %d, %Y %H:%M:%S').date()
                except (ValueError, TypeError):
                    game_date = week.start_date
                
                # Create or get Game for this specific game
                home_team = game.get('home', 'TBA')
                away_team = game.get('away', 'TBA')
                try:
                    game_obj, _ = Game.objects.get_or_create(
                        week=week,
                        nll_game_id=str(game_id),
                        defaults={
                            'date': game_date,
                            'home_team': home_team,
                            'away_team': away_team,
                        }
                    )
                except Exception as e:
                    # If game already exists with same date/teams, try to get it by those fields
                    try:
                        game_obj = Game.objects.get(
                            date=game_date,
                            home_team=home_team,
                            away_team=away_team
                        )
                    except:
                        # If we can't find or create, skip this game's stats
                        game_obj = None
            else:
                week = None
                game_obj = None

            # Get stats for this game
            game_stats_list = stats_by_game.get(game_id, [])
            
            if not game_stats_list:
                continue

            # Determine winning team (for goalie wins)
            winner_team_id = game.get('winner')
            
            # Process each player's stats for this specific game
            for stat in game_stats_list:
                # Use root_player_id to look up player info
                root_player_id = stat.get('root_player_id')
                player_data = players_by_id.get(root_player_id)
                
                if not player_data:
                    stats_skipped += 1
                    continue

                # Find or create player in our database
                jersey_number = jersey_numbers.get(root_player_id)
                
                # Get team name for this player
                team_id = stat.get('team_id')
                team_name = None
                if team_id and team_id in teams_by_id:
                    team_name = teams_by_id[team_id].get('team')
                
                # Get rookie status for this player in this season
                is_rookie = rookie_by_player_season.get((root_player_id, season_filter), False)
                
                player = self.find_or_create_player(player_data, stat, jersey_number, team_name, is_rookie, season_filter, dry_run)
                
                if not player:
                    stats_skipped += 1
                    continue

                if not dry_run and not game_obj:
                    stats_skipped += 1
                    continue
                
                # Create PlayerGameStat for this specific game
                if not dry_run:
                    stat_data = {
                        'goals': stat.get('goals', 0) or 0,
                        'assists': stat.get('assists', 0) or 0,
                        'loose_balls': stat.get('lb', 0) or 0,
                        'turnovers': stat.get('turnovers', 0) or 0,
                        'caused_turnovers': stat.get('cto', 0) or 0,
                        'blocked_shots': stat.get('blocked', 0) or 0,
                        'wins': stat.get('win', 0) or 0,
                        'saves': stat.get('sv', 0) or 0,
                        'goals_against': stat.get('ga', 0) or 0,
                    }
                    
                    game_stat_obj, created = PlayerGameStat.objects.update_or_create(
                        player=player,
                        game=game_obj,
                        defaults=stat_data
                    )
                    
                    if created:
                        stats_created += 1
                    else:
                        stats_updated += 1
                else:
                    stats_created += 1

        return {
            'created': stats_created,
            'updated': stats_updated,
            'skipped': stats_skipped
        }

    def find_or_create_player(self, player_data, stat, jersey_number, team_name, is_rookie, season, dry_run):
        """Find a player in our database by NLL stats ID, or create if not found"""
        # Get NLL stats player ID
        nll_player_id = player_data.get('id')
        if not nll_player_id:
            return None
        
        # Convert to string for external_id field
        external_id = str(nll_player_id)
        
        # Parse name from "First Last" or "First Middle Last" format
        full_name = player_data.get('name', '').strip()
        
        if not full_name:
            return None

        # Split name into parts
        name_parts = full_name.split()
        if len(name_parts) < 2:
            return None
        
        first_name = name_parts[0]
        last_name = ' '.join(name_parts[1:])  # Handle middle names and multi-word last names
        middle_name = name_parts[1] if len(name_parts) == 3 else ''
        
        # Try to find by external_id first (most reliable)
        try:
            player = Player.objects.get(external_id=external_id)
            
            # Update name, jersey number, or team if changed
            needs_update = False
            if player.first_name != first_name or player.last_name != last_name:
                player.first_name = first_name
                player.last_name = last_name
                if middle_name and not player.middle_name:
                    player.middle_name = middle_name
                needs_update = True
            
            if jersey_number is not None and player.number != jersey_number:
                player.number = jersey_number
                needs_update = True
            
            if team_name and player.nll_team != team_name:
                player.nll_team = team_name
                needs_update = True
            
            # Update biography fields from player_data
            if player_data.get('shoots') and player.shoots != player_data.get('shoots'):
                player.shoots = player_data.get('shoots')
                needs_update = True
            if player_data.get('height') and player.height != player_data.get('height'):
                player.height = player_data.get('height')
                needs_update = True
            if player_data.get('weight') and player.weight != player_data.get('weight'):
                player.weight = player_data.get('weight')
                needs_update = True
            if player_data.get('hometown') and player.hometown != player_data.get('hometown'):
                player.hometown = player_data.get('hometown')
                needs_update = True
            if player_data.get('draft_year') and player.draft_year != player_data.get('draft_year'):
                player.draft_year = player_data.get('draft_year')
                needs_update = True
            if player_data.get('birthdate') and player.birthdate != player_data.get('birthdate'):
                player.birthdate = player_data.get('birthdate')
                needs_update = True
            
            # Update rookie status
            if player.is_rookie != is_rookie:
                player.is_rookie = is_rookie
                needs_update = True
            
            if needs_update and not dry_run:
                player.save()
                team_str = f" ({team_name})" if team_name else ""
                self.stdout.write(
                    f'    * Updated player: {player.first_name} {player.last_name} #{player.number or "--"}{team_str}'
                )
            
            return player
            
        except Player.DoesNotExist:
            # Try to find by name match and update with external_id
            try:
                player = Player.objects.get(
                    first_name__iexact=first_name,
                    last_name__iexact=last_name
                )
                # Found by name - update with external_id
                if not player.external_id:
                    player.external_id = external_id
                    if not dry_run:
                        player.save()
                        self.stdout.write(
                            f'    * Updated player with NLL ID: {first_name} {last_name} (ID: {external_id})'
                        )
                return player
                
            except Player.DoesNotExist:
                # Try with just first and last name (ignoring middle)
                if len(name_parts) >= 3:
                    last_name = name_parts[-1]
                    try:
                        player = Player.objects.get(
                            first_name__iexact=first_name,
                            last_name__iexact=last_name
                        )
                        # Found by name - update with external_id
                        if not player.external_id:
                            player.external_id = external_id
                            if not dry_run:
                                player.save()
                                self.stdout.write(
                                    f'    * Updated player with NLL ID: {first_name} {last_name} (ID: {external_id})'
                                )
                        return player
                    except Player.DoesNotExist:
                        pass
                
                # Player not found - create new one
                last_name = ' '.join(name_parts[1:])  # Restore full last name
                
                # Determine position from player data
                if player_data.get('goalie', False):
                    position = 'G'
                elif player_data.get('defense', False):
                    position = 'D'
                elif player_data.get('transition', False):
                    position = 'T'
                else:
                    # Default to offense, or check if they have goalie stats in this game
                    if stat.get('sv', 0) > 0 or stat.get('ga', 0) > 0:
                        position = 'G'
                    else:
                        position = 'O'
                
                if dry_run:
                    num_str = f" #{jersey_number}" if jersey_number is not None else ""
                    team_str = f" ({team_name})" if team_name else ""
                    self.stdout.write(
                        f'    [DRY RUN] Would create new player: {first_name} {last_name}{num_str} ({position}){team_str} with NLL ID: {external_id}'
                    )
                    # Return a mock player object for dry run
                    class MockPlayer:
                        def __init__(self, fname, lname, pos, ext_id, num, team):
                            self.first_name = fname
                            self.last_name = lname
                            self.position = pos
                            self.external_id = ext_id
                            self.number = num
                            self.nll_team = team
                    return MockPlayer(first_name, last_name, position, external_id, jersey_number, team_name)
                
                # Create the new player with NLL stats ID, jersey number, team, and rookie status
                player = Player.objects.create(
                    first_name=first_name,
                    middle_name=middle_name,
                    last_name=last_name,
                    position=position,
                    external_id=external_id,
                    number=jersey_number,
                    nll_team=team_name,
                    shoots=player_data.get('shoots'),
                    height=player_data.get('height'),
                    weight=player_data.get('weight'),
                    hometown=player_data.get('hometown'),
                    draft_year=player_data.get('draft_year'),
                    birthdate=player_data.get('birthdate'),
                    is_rookie=is_rookie
                )
                
                num_str = f" #{jersey_number}" if jersey_number is not None else ""
                team_str = f" ({team_name})" if team_name else ""
                self.stdout.write(
                    f'    + Created new player: {first_name} {last_name}{num_str} ({position}){team_str} with NLL ID: {external_id}'
                )
                return player
                
            except Player.MultipleObjectsReturned:
                # If multiple players with same name, try to find one without external_id and update it
                player = Player.objects.filter(
                    first_name__iexact=first_name,
                    last_name__iexact=last_name,
                    external_id__isnull=True
                ).first()
                
                if player:
                    player.external_id = external_id
                    if not dry_run:
                        player.save()
                        self.stdout.write(
                            f'    * Updated player with NLL ID: {first_name} {last_name} (ID: {external_id})'
                        )
                    return player
                
                # Otherwise return the first match
                return Player.objects.filter(
                    first_name__iexact=first_name,
                    last_name__iexact=last_name
                ).first()

    def process_schedule(self, data, season_filter, week_filter, dry_run):
        """Process schedule.json to create week and game entries with proper dates"""
        games_created = 0
        games_updated = 0
        
        schedule_data = data.get('schedule', [])
        
        if not schedule_data:
            self.stdout.write(self.style.WARNING('No schedule data found'))
            return {'created': 0, 'updated': 0}
        
        # Build team ID to name mapping
        teams_by_id = {t.get('id'): t.get('team') for t in data.get('teams', [])}
        
        self.stdout.write(f'\nProcessing {len(schedule_data)} scheduled games from {season_filter} season...')
        
        # Group schedule by week and collect dates
        schedule_by_week = {}
        for game in schedule_data:
            if game.get('season') != season_filter:
                continue
            
            week_number = game.get('week', 1)
            is_playoff = game.get('playoffs', False)
            
            if week_number not in schedule_by_week:
                schedule_by_week[week_number] = {
                    'games': [],
                    'dates': [],
                    'is_playoff': is_playoff
                }
            
            schedule_by_week[week_number]['games'].append(game)
            
            # Parse date to find week boundaries
            date_str = game.get('date') or game.get('dt')
            if date_str:
                try:
                    # Handle format like "Dec 13, 2025 19:00:00"
                    if ' ' in date_str and ':' in date_str:
                        # Remove time component
                        date_str = date_str.split(' ')[0] + ' ' + date_str.split(' ')[1] + ' ' + date_str.split(' ')[2]
                    
                    for fmt in ('%b %d, %Y', '%Y-%m-%d', '%m/%d/%Y'):
                        try:
                            game_date = datetime.strptime(date_str.strip(), fmt).date()
                            schedule_by_week[week_number]['dates'].append(game_date)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
        
        # Create or update weeks from schedule
        if not dry_run:
            pt_tz = pytz.timezone('US/Pacific')
            now = datetime.now(pt_tz)
            
            for week_number in sorted(schedule_by_week.keys()):
                week_data = schedule_by_week[week_number]
                game_dates = week_data['dates']
                is_playoff = week_data['is_playoff']
                
                if game_dates:
                    start_date = min(game_dates)
                    end_date = max(game_dates)
                else:
                    # Fallback if no dates found
                    start_date = datetime(season_filter, 1, 1).date()
                    end_date = start_date + timedelta(days=6)
                
                # Calculate lock/unlock times
                # Lock time: first game of the week at 7 PM PT (or if game has time, use that)
                lock_time_pt = None
                if game_dates:
                    # Use 7 PM PT as lock time on the first game day
                    first_game_day = min(game_dates)
                    lock_time_pt = pt_tz.localize(datetime.combine(first_game_day, datetime.min.time())).replace(hour=19, minute=0)
                
                # Unlock time: Universal Tuesday at 9 AM PT (same for all weeks)
                # Rosters unlock on Tuesday at 9 AM PT when waivers/trades process
                # Calculate the next Tuesday from today
                today = now.date()
                days_until_tuesday = (1 - today.weekday()) % 7  # 0=Mon, 1=Tue, 6=Sun
                if days_until_tuesday == 0:  # Today is Tuesday
                    days_until_tuesday = 0 if now.hour >= 9 else 7  # If before 9 AM, today at 9 AM; otherwise next Tuesday
                next_tuesday = today + timedelta(days=days_until_tuesday)
                unlock_time_pt = pt_tz.localize(datetime.combine(next_tuesday, datetime.min.time())).replace(hour=9, minute=0)
                
                # Get or create week
                week, created = Week.objects.get_or_create(
                    season=season_filter,
                    week_number=week_number,
                    defaults={
                        'start_date': start_date,
                        'end_date': end_date,
                        'is_playoff': is_playoff,
                        'roster_lock_time': lock_time_pt,
                        'roster_unlock_time': unlock_time_pt
                    }
                )
                
                # Update lock/unlock times if they were None
                if not created and (week.roster_lock_time is None or week.roster_unlock_time is None):
                    week.roster_lock_time = lock_time_pt
                    week.roster_unlock_time = unlock_time_pt
                    week.save()
                    self.stdout.write(f'  * Updated Week {week_number} lock times')
                
                if created:
                    playoff_str = " (PLAYOFF)" if is_playoff else ""
                    self.stdout.write(f'  + Created Week {week_number}{playoff_str}: {start_date} to {end_date}')
        
        # Create or update games from schedule - deduplicate by home/away/date
        seen_games = set()
        for game in schedule_data:
            if game.get('season') != season_filter:
                continue
            
            week_number = game.get('week', 1)
            
            # Skip if filtering by week
            if week_filter and week_number != week_filter:
                continue
            
            game_id = game.get('id')
            if not game_id:
                continue
                
            date_str = game.get('date') or game.get('dt')
            # Get team IDs from API and convert to names
            home_team_id = game.get('home', 'TBA')
            away_team_id = game.get('away', 'TBA')
            
            # Convert IDs to team names if mapping is available
            home_team = teams_by_id.get(home_team_id, home_team_id) if str(home_team_id).isdigit() else home_team_id
            away_team = teams_by_id.get(away_team_id, away_team_id) if str(away_team_id).isdigit() else away_team_id
            
            # Create a unique key to avoid duplicates
            game_key = str(game_id)
            
            if game_key in seen_games:
                continue
            seen_games.add(game_key)
            
            # Parse game date
            game_date = None
            try:
                if date_str:
                    # Handle format like "Dec 13, 2025 19:00:00"
                    if ' ' in date_str and ':' in date_str:
                        date_str_clean = date_str.split(' ')[0] + ' ' + date_str.split(' ')[1] + ' ' + date_str.split(' ')[2]
                    else:
                        date_str_clean = date_str
                    
                    for fmt in ('%b %d, %Y', '%Y-%m-%d', '%m/%d/%Y'):
                        try:
                            game_date = datetime.strptime(date_str_clean.strip(), fmt).date()
                            break
                        except ValueError:
                            continue
            except (ValueError, TypeError, AttributeError):
                pass
            
            if not dry_run:
                # Get week
                try:
                    week = Week.objects.get(season=season_filter, week_number=week_number)
                except Week.DoesNotExist:
                    continue
                
                # Use game date or week start date as fallback
                if not game_date:
                    game_date = week.start_date
                
                # Create or update game using date/home/away as primary key (more reliable than nll_game_id)
                # This prevents duplicate games even if the API returns the same game with different IDs
                game_obj, created = Game.objects.update_or_create(
                    date=game_date,
                    home_team=home_team,
                    away_team=away_team,
                    defaults={
                        'week': week,
                        'nll_game_id': str(game_id) if game_id else None,
                    }
                )
                
                if created:
                    games_created += 1
                    self.stdout.write(f'  + Created game: {away_team} @ {home_team} on {game_date}')
                else:
                    games_updated += 1
                    # Update nll_game_id if it wasn't set
                    if not game_obj.nll_game_id and game_id:
                        game_obj.nll_game_id = str(game_id)
                        game_obj.save()
            else:
                games_created += 1
                self.stdout.write(f'  [DRY RUN] Would create game: {away_team} @ {home_team} on {game_date}')
        
        return {'created': games_created, 'updated': games_updated}

