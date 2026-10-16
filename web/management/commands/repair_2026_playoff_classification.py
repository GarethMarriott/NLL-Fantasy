"""Repair 2026 game week assignments using the NLLStats playoff metadata."""

import io
import json
import zipfile
from collections import defaultdict
from datetime import datetime

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from web.models import Game, Week


SEASON = 2026
SOURCE_URL = 'https://nllstats.com/json/jsonfiles.zip'


class Command(BaseCommand):
    help = 'Reassign 2026 NLL playoff games to their correct playoff weeks'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Validate the repair without saving changes')

    def handle(self, *args, **options):
        games = self.fetch_games()
        regular_games = [game for game in games if not game.get('playoffs')]
        playoff_games = [game for game in games if game.get('playoffs')]
        max_regular_week = max(game['week'] for game in regular_games)

        if len(regular_games) != 126 or len(playoff_games) != 12:
            raise CommandError(
                f'Expected 126 regular-season games and 12 playoff games; found '
                f'{len(regular_games)} and {len(playoff_games)}.'
            )

        source_ids = {str(game['id']) for game in games}
        local_games = Game.objects.filter(nll_game_id__in=source_ids).select_related('week')
        if local_games.count() != len(source_ids):
            raise CommandError(
                f'Expected {len(source_ids)} matching local games, found {local_games.count()}. '
                'No changes were made.'
            )

        games_by_week = defaultdict(list)
        for game in games:
            week_number = game['week'] + max_regular_week if game.get('playoffs') else game['week']
            games_by_week[week_number].append(game)

        self.stdout.write(
            f'Validated {len(regular_games)} regular-season and {len(playoff_games)} playoff games. '
            f'Playoffs map to Weeks {max_regular_week + 1}-{max(games_by_week)}.'
        )
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('DRY RUN: no database changes made.'))
            return

        game_by_id = {game.nll_game_id: game for game in local_games}
        with transaction.atomic():
            weeks = {}
            for week_number, week_games in games_by_week.items():
                dates = [self.game_date(game) for game in week_games]
                is_playoff = week_number > max_regular_week
                week, _ = Week.objects.update_or_create(
                    season=SEASON,
                    week_number=week_number,
                    defaults={
                        'start_date': min(dates),
                        'end_date': max(dates),
                        'is_playoff': is_playoff,
                    },
                )
                weeks[week_number] = week

            moved_games = 0
            for week_number, week_games in games_by_week.items():
                for source_game in week_games:
                    game = game_by_id[str(source_game['id'])]
                    if game.week_id != weeks[week_number].id:
                        game.week = weeks[week_number]
                        game.save(update_fields=['week'])
                        moved_games += 1

        self.stdout.write(self.style.SUCCESS(
            f'Repaired 2026 playoff classification: {moved_games} games reassigned; '
            f'Weeks {max_regular_week + 1}-{max(games_by_week)} are playoffs.'
        ))

    @staticmethod
    def fetch_games():
        response = requests.get(SOURCE_URL, timeout=60)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            payload = json.load(archive.open('games.json'))
        return [game for game in payload['games'] if game.get('season') == SEASON]

    @staticmethod
    def game_date(game):
        return datetime.strptime(game['dt'], '%b %d, %Y %H:%M:%S').date()