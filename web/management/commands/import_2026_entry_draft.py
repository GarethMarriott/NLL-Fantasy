"""Import the official 2026 NLL Entry Draft class for the 2027 NLL season."""

from django.core.management.base import BaseCommand
from django.db import transaction

from web.models import Player, PlayerNLLTeam


# Source: https://www.nll.com/news/draft-central-2026-nll-draft/
# (pick, first name, last name, fantasy position, drafting NLL team)
DRAFT_CLASS = [
    (1, 'Finn', 'Thomson', 'O', 'Rochester Knighthawks'), (2, 'Silas', 'Richmond', 'O', 'Toronto Rock'),
    (3, 'Matt', 'Collison', 'O', 'Vancouver Warriors'), (4, 'Michael', 'White', 'D', 'Las Vegas Desert Dogs'),
    (5, 'Joey', 'Spallina', 'O', 'Calgary Roughnecks'), (6, 'Dante', 'Bowen', 'T', 'Buffalo Bandits'),
    (7, 'Chad', 'Palumbo', 'O', 'Calgary Roughnecks'), (8, 'Aaron', 'Toguri', 'D', 'Saskatchewan Rush'),
    (9, 'David', 'Anderson', 'O', 'Georgia Swarm'), (10, 'Aidan', 'Maguire', 'D', 'San Diego Seals'),
    (11, 'Owen', 'Tasse', 'D', 'Las Vegas Desert Dogs'), (12, 'Nick', 'Crowley', 'D', 'Halifax Thunderbirds'),
    (13, 'Saka', 'Thompson', 'G', 'Rochester Knighthawks'), (14, 'Zach', 'Moen', 'D', 'Calgary Roughnecks'),
    (15, 'Jack', 'Cascadden', 'T', 'Georgia Swarm'), (16, 'Marcus', 'Khan', 'G', 'Vancouver Warriors'),
    (17, 'Alexis', 'Simard', 'D', 'Toronto Rock'), (18, 'Cole', 'Teeple', 'T', 'Colorado Mammoth'),
    (19, 'Justin', 'Lee', 'T', 'Oshawa FireWolves'), (20, 'Xavier', 'Delormier', 'G', 'Saskatchewan Rush'),
    (21, 'Owen', 'Rice', 'O', 'Buffalo Bandits'), (22, 'Lucas', 'Dudemaine', 'O', 'San Diego Seals'),
    (23, 'Will', 'Sheehan', 'O', 'Toronto Rock'), (24, 'Koleton', 'Marquis', 'O', 'Las Vegas Desert Dogs'),
    (25, 'Ryan', 'Stines', 'O', 'Colorado Mammoth'), (26, 'Alex', 'Lemieux', 'D', 'Saskatchewan Rush'),
    (27, 'Jeremy', 'Wudrick', 'O', 'Vancouver Warriors'), (28, 'Blake', 'Young', 'D', 'Vancouver Warriors'),
    (29, 'David', 'Peterkin', 'T', 'Halifax Thunderbirds'), (30, 'Andrew', 'McMeekin', 'T', 'Toronto Rock'),
    (31, 'Kaden', 'Kublinskas', 'D', 'Calgary Roughnecks'), (32, 'Joel', 'Mullen', 'D', 'Vancouver Warriors'),
    (33, 'Andrew', 'Bowman', 'O', 'Oshawa FireWolves'), (34, 'Nathan', 'Pouliot', 'T', 'Las Vegas Desert Dogs'),
    (35, 'Bowie', 'Horsman', 'O', 'San Diego Seals'), (36, 'Brinley', 'Wilson', 'O', 'Georgia Swarm'),
    (37, 'Brian', 'Jackman', 'O', 'Saskatchewan Rush'), (38, 'Max', 'Neeson', 'D', 'Georgia Swarm'),
    (39, 'Brooks', 'English', 'O', 'Toronto Rock'), (40, 'Connor', 'Gorman', 'O', 'Halifax Thunderbirds'),
    (41, 'Obrigh', 'Tallchief', 'D', 'Buffalo Bandits'), (42, 'Matt', 'Vilas', 'D', 'Rochester Knighthawks'),
    (43, 'Aiden', 'Long', 'T', 'Halifax Thunderbirds'), (44, 'Frank', 'Coyle', 'D', 'Rochester Knighthawks'),
    (45, 'Luke', 'Soenen', 'D', 'Calgary Roughnecks'), (46, 'Blake', 'Malamphy', 'T', 'Las Vegas Desert Dogs'),
    (47, 'Greyson', 'Beggs', 'G', 'San Diego Seals'), (48, 'Raymond', 'Cortes', 'D', 'Buffalo Bandits'),
    (49, 'Blake', 'Eiland', 'D', 'Georgia Swarm'), (50, 'Jayden', 'Richards', 'D', 'Saskatchewan Rush'),
    (51, 'Alex', 'Ross', 'D', 'Calgary Roughnecks'), (52, 'Brenden', 'Boyle', 'D', 'Georgia Swarm'),
    (53, 'Owen', 'Tovell', 'D', 'Rochester Knighthawks'), (54, 'Zach', 'Vanderwal', 'D', 'Calgary Roughnecks'),
    (55, 'John', 'Alie', 'O', 'Las Vegas Desert Dogs'), (56, 'Owen', 'Wills', 'D', 'San Diego Seals'),
    (57, 'Micah', 'Hanson', 'T', 'Buffalo Bandits'), (58, 'Kyle', 'Lewis', 'O', 'Georgia Swarm'),
    (59, 'Cal', 'Brennan', 'O', 'Saskatchewan Rush'), (60, 'Zach', 'Constantopoulos', 'G', 'Colorado Mammoth'),
    (61, 'Henry', 'Dodge', 'T', 'Vancouver Warriors'), (62, 'Rory', 'Graham', 'D', 'Halifax Thunderbirds'),
    (63, 'Troy', 'MacDonald', 'T', 'Toronto Rock'), (64, 'Kyle', 'Gonsiorek', 'D', 'Buffalo Bandits'),
    (65, 'Nate', 'Ruff', 'T', 'Buffalo Bandits'), (66, 'Joel', 'McCormick', 'O', 'Vancouver Warriors'),
    (67, 'Niky', 'Lowe', 'G', 'Buffalo Bandits'),
]


class Command(BaseCommand):
    help = 'Import the official 2026 NLL Entry Draft class as 2027 rookies.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing them.')

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        created = updated = 0

        for pick, first_name, last_name, position, nll_team in DRAFT_CLASS:
            players = Player.objects.filter(first_name__iexact=first_name, last_name__iexact=last_name)
            if players.count() > 1:
                self.stderr.write(f'Pick {pick}: ambiguous player match for {first_name} {last_name}; skipped.')
                continue

            player = players.first()
            if player is None:
                created += 1
                if dry_run:
                    self.stdout.write(f'Pick {pick}: would create {first_name} {last_name} ({position}) - {nll_team}')
                    continue
                player = Player.objects.create(first_name=first_name, last_name=last_name, position=position)
            else:
                updated += 1
                if dry_run:
                    self.stdout.write(f'Pick {pick}: would update {player} ({position}) - {nll_team}')
                    continue

            player.position = position
            player.nll_team = nll_team
            player.draft_year = 2026
            player.draft_team = nll_team
            player.entry_draft_pick = pick
            player.is_rookie = True
            player.rookie_season = 2027
            player.seasons_played = 0
            player.active = True
            player.save()
            PlayerNLLTeam.objects.update_or_create(
                player=player,
                season=2027,
                defaults={'nll_team': nll_team},
            )

        if dry_run:
            transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(f'2026 Entry Draft: {created} created, {updated} updated, {len(DRAFT_CLASS)} official picks processed.'))