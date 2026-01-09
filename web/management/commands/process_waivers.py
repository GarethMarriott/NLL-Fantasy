from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from web.models import WaiverClaim, League, Week, Roster, ChatMessage


class Command(BaseCommand):
    help = 'Process pending waiver claims for all leagues with waivers enabled'

    def add_arguments(self, parser):
        parser.add_argument(
            '--league-id',
            type=int,
            help='Process waivers for specific league only',
        )

    def handle(self, *args, **options):
        league_id = options.get('league_id')
        
        # Get leagues with waivers enabled
        leagues = League.objects.filter(use_waivers=True, is_active=True)
        if league_id:
            leagues = leagues.filter(id=league_id)
        
        total_processed = 0
        total_successful = 0
        
        for league in leagues:
            self.stdout.write(f"\nProcessing waivers for league: {league.name}")
            
            # Get current week
            current_week = Week.objects.filter(
                season=2025,
                start_date__lte=timezone.now().date()
            ).order_by('-week_number').first()
            
            if not current_week:
                self.stdout.write(self.style.WARNING(f"  No current week found for {league.name}"))
                continue
            
            # Initialize waiver priorities if not set (first time setup)
            teams_without_priority = league.teams.filter(waiver_priority=0)
            if teams_without_priority.exists():
                self.stdout.write(f"  Initializing waiver priorities for {teams_without_priority.count()} teams")
                for idx, team in enumerate(teams_without_priority.order_by('created_at'), start=1):
                    team.waiver_priority = idx
                    team.save()
            
            # Get pending claims for this league, ordered by team's waiver priority
            claims = WaiverClaim.objects.filter(
                league=league,
                status=WaiverClaim.Status.PENDING
            ).select_related(
                'team', 'player_to_add', 'player_to_drop', 'week'
            ).order_by('team__waiver_priority', 'created_at')
            
            if not claims.exists():
                self.stdout.write(f"  No pending claims for {league.name}")
                continue
            
            # Process claims in priority order
            for claim in claims:
                total_processed += 1
                success = self._process_claim(claim, current_week)
                if success:
                    total_successful += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\nProcessed {total_processed} claims, {total_successful} successful"
            )
        )

    def _process_claim(self, claim, current_week):
        """Process a single waiver claim"""
        try:
            with transaction.atomic():
                # Check if player is still available
                existing_roster = Roster.objects.filter(
                    player=claim.player_to_add,
                    league=claim.league,
                    week_dropped__isnull=True
                ).first()
                
                if existing_roster:
                    claim.status = WaiverClaim.Status.FAILED
                    claim.failure_reason = f"Player already on {existing_roster.team.name}"
                    claim.processed_at = timezone.now()
                    claim.save()
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ✗ {claim.team.name}: {claim.player_to_add} already taken"
                        )
                    )
                    return False
                
                # Check if team still has the player to drop (if applicable)
                if claim.player_to_drop:
                    drop_roster = Roster.objects.filter(
                        player=claim.player_to_drop,
                        team=claim.team,
                        league=claim.league,
                        week_dropped__isnull=True
                    ).first()
                    
                    if not drop_roster:
                        claim.status = WaiverClaim.Status.FAILED
                        claim.failure_reason = f"{claim.player_to_drop} no longer on roster"
                        claim.processed_at = timezone.now()
                        claim.save()
                        self.stdout.write(
                            self.style.WARNING(
                                f"  ✗ {claim.team.name}: Can't drop {claim.player_to_drop}"
                            )
                        )
                        return False
                    
                    # Drop the player
                    drop_roster.week_dropped = current_week
                    drop_roster.save()
                
                # Add the new player
                Roster.objects.create(
                    player=claim.player_to_add,
                    team=claim.team,
                    league=claim.league,
                    week_added=current_week,
                    added_date=timezone.now().date()
                )
                
                # Create chat notification
                if claim.player_to_drop:
                    message = f"{claim.team.name} claimed {claim.player_to_add.first_name} {claim.player_to_add.last_name}, dropped {claim.player_to_drop.first_name} {claim.player_to_drop.last_name}"
                else:
                    message = f"{claim.team.name} claimed {claim.player_to_add.first_name} {claim.player_to_add.last_name}"
                
                ChatMessage.objects.create(
                    league=claim.league,
                    message_type=ChatMessage.MessageType.ADD,
                    message=message,
                    player=claim.player_to_add,
                    team=claim.team
                )
                
                # Mark claim as successful
                claim.status = WaiverClaim.Status.SUCCESSFUL
                claim.processed_at = timezone.now()
                claim.save()
                
                # Move this team to the back of the waiver line
                # Get all teams in the league, ordered by current priority
                league_teams = claim.league.teams.all().order_by('waiver_priority')
                max_priority = league_teams.count()
                
                # Move all teams with higher priority (greater number) than this team up one spot
                teams_to_adjust = league_teams.filter(waiver_priority__gt=claim.team.waiver_priority)
                for team in teams_to_adjust:
                    team.waiver_priority -= 1
                    team.save()
                
                # Set this team to last priority
                claim.team.waiver_priority = max_priority
                claim.team.save()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ {claim.team.name}: Added {claim.player_to_add} (moved to waiver priority {max_priority})"
                    )
                )
                return True
                
        except Exception as e:
            claim.status = WaiverClaim.Status.FAILED
            claim.failure_reason = str(e)
            claim.processed_at = timezone.now()
            claim.save()
            self.stdout.write(
                self.style.ERROR(
                    f"  ✗ {claim.team.name}: Error - {str(e)}"
                )
            )
            return False
