"""Import reported 2026 NLL Dispersal Draft selections for the 2027 season."""

from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from web.models import NLLTransaction, Player, PlayerNLLTeam


SOURCE_URL = 'https://www.worldindoorlacrosse.com/blogs/nll-dispersal-draft-results-2026'
DISPERSAL_DRAFT_DATE = date(2026, 9, 15)

# (overall pick, player first name, player last name, destination NLL club)
# Source: secondary transcription of the NLL's reported results. The source does
# not identify the former Ottawa or Philadelphia club for each player.
DISPERSAL_RESULTS = [
    (1, 'Jeff', 'Teat', 'Oshawa FireWolves'),
    (2, 'Nick', 'Damude', 'Las Vegas Desert Dogs'),
    (3, 'Callum', 'Jones', 'Rochester Knighthawks'),
    (4, 'Lukas', 'Nielsen', 'Georgia Swarm'),
    (5, 'Brennan', "O'Neill", 'San Diego Seals'),
    (6, 'Matt', 'Marinier', 'Halifax Thunderbirds'),
    (7, 'Alex', 'Pace', 'Colorado Mammoth'),
    (8, 'Deacan', 'Knott', 'Georgia Swarm'),
    (9, 'Zach', 'Higgins', 'Buffalo Bandits'),
    (10, 'Jake', 'Stevens', 'Saskatchewan Rush'),
    (11, 'Dalton', 'Young', 'Buffalo Bandits'),
    (12, 'Mitchell', 'Armstrong', 'Las Vegas Desert Dogs'),
    (13, 'Connor', 'Kearnan', 'Oshawa FireWolves'),
    (14, 'Sam', 'Leclair', 'Las Vegas Desert Dogs'),
    (15, 'Brent', 'Noseworthy', 'Rochester Knighthawks'),
    (16, 'Ben', 'Kromer', 'Calgary Roughnecks'),
    (17, 'Jake', 'Saunders', 'San Diego Seals'),
    (18, 'Dustyn', 'Birkhof', 'Halifax Thunderbirds'),
    (19, 'Sam', 'Firth', 'Saskatchewan Rush'),
    (20, 'Bo', 'Columbus', 'Georgia Swarm'),
    (21, 'Larson', 'Sundown', 'Buffalo Bandits'),
    (22, 'Reed', 'Kurtz', 'Saskatchewan Rush'),
    (23, 'Scott', 'Dominey', 'Buffalo Bandits'),
    (24, 'Ryan', 'Wagner', 'Las Vegas Desert Dogs'),
    (25, 'Ron', 'John', 'Oshawa FireWolves'),
    (26, 'Liam', 'Aston', 'Las Vegas Desert Dogs'),
    (27, 'Travis', 'Longboat', 'Buffalo Bandits'),
    (28, 'Nicholas', 'Volkov', 'Calgary Roughnecks'),
    (29, 'Gregory', 'Elijah-Brown', 'San Diego Seals'),
    (30, 'Liam', 'Patten', 'Halifax Thunderbirds'),
    (31, 'Andrew', 'Borgatti', 'Colorado Mammoth'),
    (32, 'Isaiah', 'Davis-Allen', 'Georgia Swarm'),
    (33, 'Justin', 'Sykes', 'Buffalo Bandits'),
    (35, 'Michael', 'Sowers', 'Vancouver Warriors'),
    (37, 'Kevin', 'Brownell', 'Oshawa FireWolves'),
    (38, 'Chris', 'Corbeil', 'Las Vegas Desert Dogs'),
    (39, 'Luc', 'Magnan', 'Rochester Knighthawks'),
    (40, 'Cole', 'Begley', 'Calgary Roughnecks'),
    (41, 'Mason', 'Woodward', 'San Diego Seals'),
    (42, 'Landen', 'Sinfield', 'Halifax Thunderbirds'),
    (43, 'Evan', 'Messenger', 'Colorado Mammoth'),
]


class Command(BaseCommand):
    help = 'Import reported 2026 NLL Dispersal Draft results for the 2027 season.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing them.')

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        created = updated = skipped = 0

        for overall_pick, first_name, last_name, destination in DISPERSAL_RESULTS:
            matches = Player.objects.filter(
                first_name__iexact=first_name,
                last_name__iexact=last_name,
            )
            if matches.count() != 1:
                skipped += 1
                reason = 'not found' if not matches.exists() else 'ambiguous'
                self.stderr.write(f'Pick {overall_pick}: {first_name} {last_name} {reason}; skipped.')
                continue

            player = matches.get()
            transaction_url = f'{SOURCE_URL}#pick-{overall_pick}'
            details = (
                f'Reported selected by {destination} with pick {overall_pick} in the 2026 NLL Dispersal Draft. '
                'Source is a secondary transcription; former club was not specified per player.'
            )
            assignment_exists = PlayerNLLTeam.objects.filter(
                player=player,
                season=2027,
            ).exists()
            if dry_run:
                action = 'update' if assignment_exists else 'create'
                self.stdout.write(f'Pick {overall_pick}: would {action} 2027 assignment for {player}.')
                if assignment_exists:
                    updated += 1
                else:
                    created += 1
                continue

            transaction_record, _ = NLLTransaction.objects.get_or_create(
                nll_url=transaction_url,
                defaults={
                    'transaction_date': DISPERSAL_DRAFT_DATE,
                    'transaction_type': 'other',
                    'player_name': f'{player.first_name} {player.last_name}',
                    'to_team': destination,
                    'details': details,
                    'player': player,
                },
            )
            assignment, assignment_created = PlayerNLLTeam.objects.update_or_create(
                player=player,
                season=2027,
                defaults={
                    'nll_team': destination,
                    'source_transaction': transaction_record,
                },
            )
            if player.nll_team != destination:
                player.nll_team = destination
                player.save(update_fields=['nll_team'])

            if assignment_created:
                created += 1
            else:
                updated += 1

        if dry_run:
            transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(
            f'2026 Dispersal Draft: {created} created, {updated} updated, {skipped} skipped.'
        ))