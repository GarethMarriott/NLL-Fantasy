from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from web.models import WaiverClaim, League, Week, Roster, ChatMessage, Trade, TradePlayer, Player
import logging

logger = logging.getLogger(__name__)


def check_roster_capacity(team, position, exclude_player=None):
    """
    Check if a team has room to add a player to a specific position.
    
    Args:
        team: Team object
        position: Position to check ('O', 'D', 'G')
        exclude_player: Optional player to exclude from count (for swaps)
    
    Returns:
        Tuple of (can_add: bool, current_count: int, max_allowed: int)
    """
    # Count active players in this position
    query = Roster.objects.filter(
        team=team,
        league=team.league,
        week_dropped__isnull=True
    ).select_related('player')
    
    if exclude_player:
        query = query.exclude(player=exclude_player)
    
    # Filter by position - need to check assigned_side if set, otherwise check player position
    players = list(query)
    
    # Count players by their assigned position or natural position
    position_count = 0
    for roster in players:
        # Use assigned_side if set (for transition players), otherwise use natural position
        player_assigned = roster.player.assigned_side if roster.player.assigned_side else roster.player.position
        
        # Count if this player is assigned to the target position
        if player_assigned == position:
            position_count += 1
    
    # Get max slots for this position
    max_slots = {
        'O': team.league.roster_forwards,
        'D': team.league.roster_defense,
        'G': team.league.roster_goalies
    }
    max_allowed = max_slots.get(position, 0)
    
    return position_count < max_allowed, position_count, max_allowed


class Command(BaseCommand):
    help = 'Process pending waiver claims and trades for all leagues with waivers enabled'

    def add_arguments(self, parser):
        parser.add_argument(
            '--league-id',
            type=int,
            help='Process waivers/trades for specific league only',
        )

    def handle(self, *args, **options):
        league_id = options.get('league_id')
        
        # Get leagues with waivers enabled
        leagues = League.objects.filter(use_waivers=True, is_active=True)
        if league_id:
            leagues = leagues.filter(id=league_id)
        
        total_waivers_processed = 0
        total_waivers_successful = 0
        total_trades_processed = 0
        total_trades_successful = 0
        
        for league in leagues:
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"Processing league: {league.name}")
            self.stdout.write(f"{'='*60}")
            
            # Get current week - use the current year as season
            # IMPORTANT: Use end_date__gte (week hasn't ended yet) instead of start_date__lte
            # to avoid picking the wrong week. On Monday 9am, we're transitioning from the 
            # previous week (which ended Sunday) to the new week.
            current_year = timezone.now().year
            current_week = Week.objects.filter(
                season=current_year,
                end_date__gte=timezone.now().date()
            ).order_by('week_number').first()
            
            if not current_week:
                self.stdout.write(self.style.WARNING(f"  No current week found for {league.name}"))
                continue
            
            # IMPORTANT: Waivers are processed when the current week's rosters UNLOCK (Monday 9am)
            # At that time, players from waiver claims should have week_added set to the NEXT week
            # (not the current locked week), since they only become active after the current week ends
            try:
                next_week = Week.objects.filter(
                    season=current_year,
                    week_number__gt=current_week.week_number
                ).order_by('week_number').first()
                
                if not next_week:
                    # Fallback: if no next week exists, use next week number
                    next_week_number = current_week.week_number + 1
                else:
                    next_week_number = next_week.week_number
            except:
                next_week_number = current_week.week_number + 1
            
            # Initialize waiver priorities if not set (first time setup)
            teams_without_priority = league.teams.filter(waiver_priority=0)
            if teams_without_priority.exists():
                self.stdout.write(f"  Initializing waiver priorities for {teams_without_priority.count()} teams")
                for idx, team in enumerate(teams_without_priority.order_by('created_at'), start=1):
                    team.waiver_priority = idx
                    team.save()
            
            # Process waivers
            self.stdout.write(f"\n--- PROCESSING WAIVERS ---")
            waiver_stats = self._process_waivers(league, current_week, next_week_number)
            total_waivers_processed += waiver_stats['processed']
            total_waivers_successful += waiver_stats['successful']
            
            # Process trades
            self.stdout.write(f"\n--- PROCESSING TRADES ---")
            trade_stats = self._process_trades(league, current_week, next_week_number)
            total_trades_processed += trade_stats['processed']
            total_trades_successful += trade_stats['successful']
        
        # Summary
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS(
            f"SUMMARY:\n"
            f"  Waivers: {total_waivers_successful}/{total_waivers_processed} successful\n"
            f"  Trades:  {total_trades_successful}/{total_trades_processed} successful"
        ))
        self.stdout.write(f"{'='*60}\n")

    def _process_waivers(self, league, current_week, next_week_number):
        """Process all pending waiver claims for a league"""
        stats = {'processed': 0, 'successful': 0}
        
        claims = WaiverClaim.objects.filter(
            league=league,
            status=WaiverClaim.Status.PENDING
        ).select_related('team', 'player_to_add', 'player_to_drop').order_by('team__waiver_priority', 'created_at')
        
        if not claims.exists():
            self.stdout.write(f"  No pending waiver claims")
            return stats
        
        for claim in claims:
            stats['processed'] += 1
            success = self._process_claim(claim, current_week, next_week_number)
            if success:
                stats['successful'] += 1
        
        return stats
    
    def _process_trades(self, league, current_week, next_week_number):
        """Process all accepted trades for a league"""
        stats = {'processed': 0, 'successful': 0}
        
        # Get ACCEPTED trades that haven't been executed yet
        trades = Trade.objects.filter(
            league=league,
            status=Trade.Status.ACCEPTED,
            executed_at__isnull=True
        ).select_related('proposing_team', 'receiving_team').prefetch_related('players').order_by('created_at')
        
        if not trades.exists():
            self.stdout.write(f"  No pending trades to execute")
            return stats
        
        for trade in trades:
            stats['processed'] += 1
            success = self._process_trade(trade, current_week, next_week_number)
            if success:
                stats['successful'] += 1
        
        return stats

    def _process_claim(self, claim, current_week, next_week_number):
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
                    self.stdout.write(self.style.WARNING(f"  ✗ {claim.team.name}: {claim.player_to_add.last_name} already taken"))
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
                        claim.failure_reason = f"{claim.player_to_drop.last_name} no longer on roster"
                        claim.processed_at = timezone.now()
                        claim.save()
                        self.stdout.write(self.style.WARNING(f"  ✗ {claim.team.name}: Can't drop {claim.player_to_drop.last_name}"))
                        return False
                    
                    # Drop the player
                    drop_roster.week_dropped = current_week.week_number
                    drop_roster.save()
                else:
                    # No drop player - check if team has room
                    current_roster_count = Roster.objects.filter(
                        team=claim.team,
                        league=claim.league,
                        week_dropped__isnull=True
                    ).count()
                    
                    if current_roster_count >= claim.league.roster_size:
                        claim.status = WaiverClaim.Status.FAILED
                        claim.failure_reason = f"Roster full ({current_roster_count}/{claim.league.roster_size})"
                        claim.processed_at = timezone.now()
                        claim.save()
                        self.stdout.write(self.style.WARNING(f"  ✗ {claim.team.name}: Roster full"))
                        return False
                
                # Check position-specific capacity for the player being added
                player_position = claim.player_to_add.assigned_side if claim.player_to_add.assigned_side else claim.player_to_add.position
                can_add, current_pos_count, max_pos_slots = check_roster_capacity(claim.team, player_position, exclude_player=claim.player_to_drop)
                
                if not can_add:
                    claim.status = WaiverClaim.Status.FAILED
                    pos_name = {'O': 'Offence', 'D': 'Defence', 'G': 'Goalie'}.get(player_position, 'Unknown')
                    claim.failure_reason = f"{pos_name} roster full ({current_pos_count}/{max_pos_slots})"
                    claim.processed_at = timezone.now()
                    claim.save()
                    self.stdout.write(self.style.WARNING(f"  ✗ {claim.team.name}: {pos_name} roster full"))
                    return False
                
                # Add the new player with week_added set to NEXT week
                # (not current locked week, since player only becomes active next week)
                Roster.objects.create(
                    player=claim.player_to_add,
                    team=claim.team,
                    league=claim.league,
                    week_added=next_week_number,
                    added_date=timezone.now().date()
                )
                
                # Create chat notification
                if claim.player_to_drop:
                    message = f"⚡ WAIVER: {claim.team.name} claimed {claim.player_to_add.last_name}, dropped {claim.player_to_drop.last_name}"
                else:
                    message = f"⚡ WAIVER: {claim.team.name} claimed {claim.player_to_add.last_name}"
                
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
                league_teams = claim.league.teams.all().order_by('waiver_priority')
                max_priority = league_teams.count()
                teams_to_adjust = league_teams.filter(waiver_priority__gt=claim.team.waiver_priority)
                for team in teams_to_adjust:
                    team.waiver_priority -= 1
                    team.save()
                
                claim.team.waiver_priority = max_priority
                claim.team.save()
                
                self.stdout.write(self.style.SUCCESS(f"  ✓ {claim.team.name}: Added {claim.player_to_add.last_name} (waiver priority {max_priority})"))
                return True
                
        except Exception as e:
            claim.status = WaiverClaim.Status.FAILED
            claim.failure_reason = str(e)
            claim.processed_at = timezone.now()
            claim.save()
            logger.exception(f"Error processing waiver claim {claim.id}: {str(e)}")
            self.stdout.write(self.style.ERROR(f"  ✗ {claim.team.name}: Error - {str(e)}"))
            return False
    
    def _process_trade(self, trade, current_week, next_week_number):
        """Process a single accepted trade"""
        try:
            with transaction.atomic():
                # Get all players involved in trade
                trade_players = trade.players.all().select_related('player', 'from_team')
                
                if not trade_players.exists():
                    self.stdout.write(self.style.WARNING(f"  ✗ Trade {trade.id}: No players"))
                    return False
                
                # Determine teams - players should come from 2 different teams
                from_team_to_players = {}
                for tp in trade_players:
                    if tp.from_team not in from_team_to_players:
                        from_team_to_players[tp.from_team] = []
                    from_team_to_players[tp.from_team].append(tp)
                
                # Should be 2 teams involved
                if len(from_team_to_players) != 2:
                    self.stdout.write(self.style.WARNING(f"  ✗ Trade {trade.id}: Invalid team structure"))
                    return False
                
                teams_in_trade = list(from_team_to_players.keys())
                team1, team2 = teams_in_trade[0], teams_in_trade[1]
                
                # Validate all players are still on their teams
                for tp in trade_players:
                    roster = Roster.objects.filter(
                        player=tp.player,
                        team=tp.from_team,
                        league=trade.league,
                        week_dropped__isnull=True
                    ).first()
                    
                    if not roster:
                        self.stdout.write(self.style.WARNING(
                            f"  ✗ Trade {trade.id}: {tp.player.last_name} no longer on {tp.from_team.name}"
                        ))
                        return False
                
                # Validate roster capacity for receiving teams
                # Team 1 players → Team 2, Team 2 players → Team 1
                for tp in from_team_to_players[team1]:
                    player_position = tp.player.assigned_side if tp.player.assigned_side else tp.player.position
                    can_add, current_pos_count, max_pos_slots = check_roster_capacity(team2, player_position)
                    if not can_add:
                        pos_name = {'O': 'Offence', 'D': 'Defence', 'G': 'Goalie'}.get(player_position, 'Unknown')
                        self.stdout.write(self.style.WARNING(
                            f"  ✗ Trade {trade.id}: {team2.name} {pos_name} roster full ({current_pos_count}/{max_pos_slots})"
                        ))
                        return False
                
                for tp in from_team_to_players[team2]:
                    player_position = tp.player.assigned_side if tp.player.assigned_side else tp.player.position
                    can_add, current_pos_count, max_pos_slots = check_roster_capacity(team1, player_position)
                    if not can_add:
                        pos_name = {'O': 'Offence', 'D': 'Defence', 'G': 'Goalie'}.get(player_position, 'Unknown')
                        self.stdout.write(self.style.WARNING(
                            f"  ✗ Trade {trade.id}: {team1.name} {pos_name} roster full ({current_pos_count}/{max_pos_slots})"
                        ))
                        return False
                
                # Execute the trade - swap players between teams
                player_moves = []
                
                # Team 1 players go to Team 2
                for tp in from_team_to_players[team1]:
                    roster = Roster.objects.filter(
                        player=tp.player,
                        team=tp.from_team,
                        league=trade.league,
                        week_dropped__isnull=True
                    ).first()
                    
                    roster.week_dropped = current_week.week_number
                    roster.save()
                    
                    Roster.objects.create(
                        player=tp.player,
                        team=team2,
                        league=trade.league,
                        week_added=next_week_number,
                        added_date=timezone.now().date()
                    )
                    
                    player_moves.append(f"{tp.player.last_name} ({team1.name}→{team2.name})")
                
                # Team 2 players go to Team 1
                for tp in from_team_to_players[team2]:
                    roster = Roster.objects.filter(
                        player=tp.player,
                        team=tp.from_team,
                        league=trade.league,
                        week_dropped__isnull=True
                    ).first()
                    
                    roster.week_dropped = current_week.week_number
                    roster.save()
                    
                    Roster.objects.create(
                        player=tp.player,
                        team=team1,
                        league=trade.league,
                        week_added=next_week_number,
                        added_date=timezone.now().date()
                    )
                    
                    player_moves.append(f"{tp.player.last_name} ({team2.name}→{team1.name})")
                
                # Create chat notification
                players_str = ", ".join(player_moves)
                message = f"🤝 TRADE: {players_str}"
                
                ChatMessage.objects.create(
                    league=trade.league,
                    message_type=ChatMessage.MessageType.TRADE,
                    message=message,
                    team=trade.proposing_team
                )
                
                # Mark trade as executed
                trade.executed_at = timezone.now()
                trade.save()
                
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ Trade executed: {players_str}")
                )
                return True
                
        except Exception as e:
            trade.status = Trade.Status.FAILED
            trade.failure_reason = str(e)
            trade.processed_at = timezone.now()
            trade.save()
            logger.exception(f"Error processing trade {trade.id}: {str(e)}")
            self.stdout.write(self.style.ERROR(f"  ✗ Trade {trade.id}: Error - {str(e)}"))
            return False
