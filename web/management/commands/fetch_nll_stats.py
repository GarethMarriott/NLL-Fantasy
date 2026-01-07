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
from django.core.management.base import BaseCommand
from django.db import transaction
from web.models import Player, Week, PlayerWeekStat, Team


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
            required_files = ['games.json', 'player_seasons.json', 'players.json', 'teams.json', 'game_scoring.json', 'jerseynumbers.json']
            
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
            
            self.stdout.write(self.style.SUCCESS(
                f'\nCompleted! Created: {stats_result["created"]}, Updated: {stats_result["updated"]}, Skipped: {stats_result["skipped"]}'
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

        # Group games by week to calculate week date ranges
        games_by_week = {}
        for game in games:
            week_number = game.get('week', 1)
            if week_number not in games_by_week:
                games_by_week[week_number] = []
            games_by_week[week_number].append(game)

        # Create Week objects with proper date ranges
        weeks_created = {}
        if not dry_run:
            for week_number, week_games in games_by_week.items():
                # Parse game dates to find start and end of week
                game_dates = []
                for game in week_games:
                    date_str = game.get('dt')
                    if date_str:
                        try:
                            game_date = datetime.strptime(date_str, '%b %d, %Y %H:%M:%S').date()
                            game_dates.append(game_date)
                        except ValueError:
                            pass
                
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
                        'end_date': end_date
                    }
                )
                weeks_created[week_number] = week
                if created:
                    self.stdout.write(f'Created Week {week_number}: {start_date} to {end_date}')

        # Group stats by player and week to accumulate multiple games
        stats_by_player_week = {}
        
        # Process each game
        for game in games:
            game_id = game.get('id')
            week_number = game.get('week', 1)
            game_date = game.get('dt')
            
            # Skip if filtering by week and this isn't it
            if week_filter and week_number != week_filter:
                continue

            # Get Week object
            if not dry_run:
                week = weeks_created.get(week_number)
                if not week:
                    continue
            else:
                week = None

            # Get stats for this game
            game_stats = stats_by_game.get(game_id, [])
            
            if not game_stats:
                continue

            # Determine winning team (for goalie wins)
            winner_team_id = game.get('winner')
            
            # Process each player's stats for this game
            for stat in game_stats:
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
                
                player = self.find_or_create_player(player_data, stat, jersey_number, team_name, dry_run)
                
                if not player:
                    stats_skipped += 1
                    continue

                # Create key for player-week combination
                key = (player.id if player else root_player_id, week_number)
                
                # Initialize accumulator if first time seeing this player-week
                if key not in stats_by_player_week:
                    stats_by_player_week[key] = {
                        'player': player,
                        'week': week,
                        'week_number': week_number,
                        'games_played': 0,
                        'goals': 0,
                        'assists': 0,
                        'loose_balls': 0,
                        'turnovers': 0,
                        'caused_turnovers': 0,
                        'blocked_shots': 0,
                        'wins': 0,
                        'saves': 0,
                        'goals_against': 0,
                    }
                
                # Accumulate stats
                acc = stats_by_player_week[key]
                acc['games_played'] += 1
                acc['goals'] += stat.get('goals', 0) or 0
                acc['assists'] += stat.get('assists', 0) or 0
                acc['loose_balls'] += stat.get('lb', 0) or 0
                acc['turnovers'] += stat.get('turnovers', 0) or 0
                acc['caused_turnovers'] += stat.get('cto', 0) or 0
                acc['blocked_shots'] += stat.get('blocked', 0) or 0
                acc['wins'] += stat.get('win', 0) or 0
                acc['saves'] += stat.get('sv', 0) or 0
                acc['goals_against'] += stat.get('ga', 0) or 0

        # Now save all accumulated stats
        for key, acc in stats_by_player_week.items():
            player = acc['player']
            week = acc['week']
            
            if not player or (not dry_run and not week):
                stats_skipped += 1
                continue
            
            # Determine if this is a goalie
            is_goalie = player.position == 'G'
            
            # Save stats based on position
            if is_goalie:
                result = self.save_goalie_stat_accumulated(player, week, acc, dry_run)
            else:
                result = self.save_field_player_stat_accumulated(player, week, acc, dry_run)
            
            if result == 'created':
                stats_created += 1
            elif result == 'updated':
                stats_updated += 1
            elif result == 'skipped':
                stats_skipped += 1

        return {
            'created': stats_created,
            'updated': stats_updated,
            'skipped': stats_skipped
        }

    def find_or_create_player(self, player_data, stat, jersey_number, team_name, dry_run):
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
                
                # Create the new player with NLL stats ID, jersey number, and team
                player = Player.objects.create(
                    first_name=first_name,
                    middle_name=middle_name,
                    last_name=last_name,
                    position=position,
                    external_id=external_id,
                    number=jersey_number,
                    nll_team=team_name
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

    def save_field_player_stat_accumulated(self, player, week, acc, dry_run):
        """Save or update accumulated field player stats"""
        goals = acc['goals']
        assists = acc['assists']
        loose_balls = acc['loose_balls']
        turnovers = acc['turnovers']
        caused_turnovers = acc['caused_turnovers']
        blocked_shots = acc['blocked_shots']
        games_played = acc['games_played']
        
        if dry_run:
            gp_str = f" ({games_played} games)" if games_played > 1 else ""
            self.stdout.write(
                f'    [DRY RUN] {player.first_name} {player.last_name}: '
                f'{goals}G, {assists}A, {loose_balls}LB{gp_str}'
            )
            return 'created'

        # Create or update stat
        stat_obj, created = PlayerWeekStat.objects.update_or_create(
            player=player,
            week=week,
            defaults={
                'goals': goals,
                'assists': assists,
                'points': goals + assists,
                'loose_balls': loose_balls,
                'turnovers': turnovers,
                'caused_turnovers': caused_turnovers,
                'blocked_shots': blocked_shots,
                'games_played': games_played,
            }
        )
        
        gp_str = f" ({games_played} games)" if games_played > 1 else ""
        if created:
            self.stdout.write(
                f'    + {player.first_name} {player.last_name}: '
                f'{goals}G, {assists}A, {loose_balls}LB{gp_str}'
            )
            return 'created'
        else:
            self.stdout.write(
                f'    * {player.first_name} {player.last_name}: '
                f'{goals}G, {assists}A, {loose_balls}LB{gp_str} (updated)'
            )
            return 'updated'

    def save_goalie_stat_accumulated(self, player, week, acc, dry_run):
        """Save or update accumulated goalie stats"""
        wins = acc['wins']
        saves = acc['saves']
        goals_against = acc['goals_against']
        games_played = acc['games_played']
        
        if dry_run:
            gp_str = f" ({games_played} games)" if games_played > 1 else ""
            self.stdout.write(
                f'    [DRY RUN] {player.first_name} {player.last_name} (G): '
                f'{wins}W, {saves}SV, {goals_against}GA{gp_str}'
            )
            return 'created'

        # Create or update stat
        stat_obj, created = PlayerWeekStat.objects.update_or_create(
            player=player,
            week=week,
            defaults={
                'wins': wins,
                'saves': saves,
                'goals_against': goals_against,
                'games_played': games_played,
            }
        )
        
        gp_str = f" ({games_played} games)" if games_played > 1 else ""
        if created:
            self.stdout.write(
                f'    + {player.first_name} {player.last_name} (G): '
                f'{wins}W, {saves}SV, {goals_against}GA{gp_str}'
            )
            return 'created'
        else:
            self.stdout.write(
                f'    * {player.first_name} {player.last_name} (G): '
                f'{wins}W, {saves}SV, {goals_against}GA{gp_str} (updated)'
            )
            return 'updated'
