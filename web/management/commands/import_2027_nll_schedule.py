"""Import the official 2026-27 NLL regular-season schedule as season 2027."""

import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError

from web.models import Game, Week


SOURCE_URL = 'https://www.nll.com/news/2026-27-nll-regular-season-schedule/'
SEASON = 2027
WEEK_DATES = {
    1: ('2026-11-27', '2026-11-28'),
    2: ('2026-12-04', '2026-12-05'),
    3: ('2026-12-11', '2026-12-13'),
    4: ('2026-12-18', '2026-12-19'),
    5: ('2026-12-26', '2026-12-27'),
    6: ('2027-01-01', '2027-01-03'),
    7: ('2027-01-08', '2027-01-10'),
    8: ('2027-01-15', '2027-01-16'),
    9: ('2027-01-22', '2027-01-23'),
    10: ('2027-01-29', '2027-01-30'),
    11: ('2027-02-05', '2027-02-07'),
    12: ('2027-02-12', '2027-02-13'),
    13: ('2027-02-20', '2027-02-21'),
    14: ('2027-02-26', '2027-02-27'),
    15: ('2027-03-05', '2027-03-06'),
    16: ('2027-03-13', '2027-03-13'),
    17: ('2027-03-18', '2027-03-20'),
    18: ('2027-03-26', '2027-03-27'),
    19: ('2027-04-02', '2027-04-03'),
    20: ('2027-04-09', '2027-04-10'),
    21: ('2027-04-17', '2027-04-17'),
    22: ('2027-04-24', '2027-04-25'),
}


class Command(BaseCommand):
    help = 'Import the official 2026-27 NLL regular-season schedule as season 2027'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Validate the source without saving changes')

    def handle(self, *args, **options):
        fixtures = self.fetch_fixtures()
        if len(fixtures) != 108:
            raise CommandError(f'Expected 108 official fixtures, found {len(fixtures)}. No changes were made.')

        counts_by_week = {week_number: 0 for week_number in WEEK_DATES}
        for fixture in fixtures:
            counts_by_week[fixture['week_number']] += 1
        if set(counts_by_week) != set(range(1, 23)) or counts_by_week[3] != 0:
            raise CommandError('The official source did not produce all 22 weeks with an empty Week 3.')

        self.stdout.write(f'Validated 22 official weeks and {len(fixtures)} fixtures from {SOURCE_URL}')
        self.stdout.write('Week 3 is retained as an explicit no-games week.')
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('DRY RUN: no database changes made.'))
            return

        weeks = {}
        weeks_created = weeks_updated = games_created = games_updated = 0
        for week_number, (start_date, end_date) in WEEK_DATES.items():
            week, created = Week.objects.update_or_create(
                season=SEASON,
                week_number=week_number,
                defaults={
                    'start_date': datetime.strptime(start_date, '%Y-%m-%d').date(),
                    'end_date': datetime.strptime(end_date, '%Y-%m-%d').date(),
                    'is_playoff': False,
                },
            )
            weeks[week_number] = week
            if created:
                weeks_created += 1
            else:
                weeks_updated += 1

        for fixture in fixtures:
            game, created = Game.objects.update_or_create(
                date=fixture['date'],
                home_team=fixture['home_team'],
                away_team=fixture['away_team'],
                defaults={'week': weeks[fixture['week_number']]},
            )
            if created:
                games_created += 1
            elif game.week_id != weeks[fixture['week_number']].id:
                games_updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'Weeks: {weeks_created} created, {weeks_updated} updated. '
            f'Games: {games_created} created, {games_updated} moved.'
        ))

    def fetch_fixtures(self):
        response = requests.get(
            SOURCE_URL,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; NLLFantasyScheduleImporter/1.0)'},
            timeout=30,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        fixtures = []
        current_week = None
        for element in soup.find_all(['h2', 'h3', 'tr']):
            if element.name in {'h2', 'h3'}:
                match = re.search(r'WEEK\s+(\d+)', element.get_text(' ', strip=True), re.IGNORECASE)
                if match:
                    current_week = int(match.group(1))
                continue

            if current_week not in WEEK_DATES:
                continue
            cells = [cell.get_text(' ', strip=True) for cell in element.find_all(['td', 'th'])]
            if len(cells) < 2 or ' at ' not in cells[1]:
                continue

            away_team, home_team = cells[1].split(' at ', 1)
            fixture_date = self.parse_fixture_date(cells[0])
            fixtures.append({
                'week_number': current_week,
                'date': fixture_date,
                'away_team': away_team,
                'home_team': home_team,
            })

        return fixtures

    @staticmethod
    def parse_fixture_date(value):
        clean_value = re.sub(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.\s*', '', value).replace('.', '')
        parsed = datetime.strptime(clean_value, '%b %d')
        year = 2026 if parsed.month in {11, 12} else 2027
        return parsed.replace(year=year).date()