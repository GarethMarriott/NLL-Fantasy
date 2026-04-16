from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone
from django.contrib.sessions.models import Session
from datetime import timedelta
import logging
import sys

logger = logging.getLogger(__name__)


@shared_task
def send_email_task(subject, message, recipient_list, html_message=None):
    """
    Async task to send emails without blocking the request
    
    Usage:
        from web.tasks import send_email_task
        send_email_task.delay('Subject', 'Message', ['user@example.com'])
    """
    try:
        send_mail(
            subject,
            message,
            'noreply@yourdomain.com',
            recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"Email sent to {recipient_list}")
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_list}: {str(e)}")
        raise


@shared_task
def send_password_reset_email(user_id, uid, token, protocol='https', domain='shamrockfantasy.com'):
    """Send password reset email with token"""
    from django.contrib.auth import get_user_model
    from django.template.loader import render_to_string
    from django.core.mail import send_mail
    from django.conf import settings
    User = get_user_model()
    
    try:
        user = User.objects.get(id=user_id)
        
        # Build reset URL with provided domain and protocol
        reset_url = f"{protocol}://{domain}/password-reset/{uid}/{token}/"
        
        # Render email template
        subject = 'Password Reset Request - NLL Fantasy'
        html_message = render_to_string('emails/password_reset_email.html', {
            'user': user,
            'protocol': protocol,
            'domain': domain,
            'uid': uid,
            'token': token,
            'token_expire_hours': 24,
            'reset_url': reset_url,
        })
        
        # Send email
        send_mail(
            subject,
            f"Click here to reset your password: {reset_url}",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Password reset email sent to {user.email}")
        return f"Password reset email sent to {user.email}"
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} not found for password reset")
        return f"User with id {user_id} not found"
    except Exception as e:
        logger.error(f"Error sending password reset email: {str(e)}")
        return f"Error sending password reset email: {str(e)}"


@shared_task
def cleanup_old_sessions():
    """
    Clean up expired sessions from database
    Called by Celery Beat daily at 2 AM
    """
    try:
        deleted_count, _ = Session.objects.filter(
            expire_date__lt=timezone.now()
        ).delete()
        logger.info(f"Cleaned up {deleted_count} expired sessions")
    except Exception as e:
        logger.error(f"Session cleanup task failed: {str(e)}")
        raise





@shared_task(name='web.tasks.unlock_rosters_and_process_transactions', bind=True, max_retries=3)
def unlock_rosters_and_process_transactions(self):
    """
    Unlock rosters (Tuesday 9am PT) and execute pending waivers/trades atomically.
    Called automatically at Tuesday 9am PT via Celery Beat schedule.
    
    Executes in sequence:
    1. Unlock rosters for weeks
    2. Process pending waiver claims
    3. Process pending accepted trades
    4. Update current_week to next week
    
    All steps execute together or task retries.
    Uses the process_waivers management command to ensure consistency.
    """
    from django.core.management import call_command
    from web.models import Week, League
    
    now = timezone.now()
    
    try:
        # Find weeks where we're currently in the unlocked window
        # (unlock_time has passed AND lock_time hasn't occurred yet)
        weeks = Week.objects.filter(
            roster_unlock_time__lte=now,
            roster_lock_time__gt=now
        )
        
        if not weeks.exists():
            logger.info("No weeks found in unlocked window")
            return "No weeks to unlock"
        
        weeks_updated = 0
        for week in weeks:
            logger.info(f"[UNLOCK SEQUENCE START] Week {week.week_number}, Season {week.season}")
            
            try:
                # Step 1: Process waivers and trades (critical - must succeed)
                logger.info(f"[STEP 1] Processing waiver claims and trades for Week {week.week_number}...")
                call_command('process_waivers')
                logger.info(f"[STEP 1 SUCCESS] Processed waivers and trades")
                
                # Step 2: Update league current_week to next week (critical - must succeed)
                logger.info(f"[STEP 2] Updating current week for Season {week.season}...")
                updated_count = update_current_week_for_season(week.season)
                logger.info(f"[STEP 2 SUCCESS] Updated current week for {updated_count} leagues")
                
                logger.info(f"[UNLOCK SEQUENCE COMPLETE] Week {week.week_number} rosters unlocked, waivers processed, current_week updated")
                weeks_updated += 1
                
            except Exception as e:
                logger.error(f"[UNLOCK SEQUENCE FAILED] Week {week.week_number}: {str(e)}")
                raise  # Re-raise to trigger task retry
        
        success_msg = f"Successfully completed unlock sequence for {weeks_updated} week(s): roster unlock + waivers + trades + current_week update"
        logger.info(f"[ALL SEQUENCES COMPLETE] {success_msg}")
        return success_msg
    
    except Exception as e:
        logger.error(f"[UNLOCK TASK ERROR] Error in unlock sequence: {str(e)}")
        # Retry with exponential backoff: 60s, 300s, 900s
        try:
            self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except Exception as retry_error:
            logger.critical(f"[UNLOCK TASK CRITICAL] Task failed after {self.request.retries} retries: {str(retry_error)}")
            raise


def update_current_week_for_season(season):
    """
    Update all leagues' current_week to the next unlocked week.
    Called when Tuesday 9am PT rosters unlock.
    Returns count of leagues updated.
    """
    from web.models import League, Week
    
    try:
        leagues = League.objects.filter(created_at__year=season, is_active=True)
        updated_count = 0
        
        for league in leagues:
            # Find the next unlocked week (most recent with unlock_time passed)
            now = timezone.now()
            next_week = Week.objects.filter(
                season=season,
                roster_unlock_time__lte=now
            ).order_by('-week_number').first()
            
            if next_week:
                league.current_week = next_week
                league.save()
                updated_count += 1
                logger.info(f"Updated {league.name} current week to Week {next_week.week_number}")
        
        return updated_count
    
    except Exception as e:
        logger.error(f"Error updating current week for season {season}: {str(e)}")
        raise  # Re-raise to fail the task so it retries


@shared_task
def fetch_nll_stats_task():
    """
    Fetch NLL player stats for the current season.
    
    Called by Celery Beat every Friday, Saturday, and Sunday at 11 PM PT
    to capture stats from recently completed games.
    """
    from django.core.management import call_command
    
    try:
        # Get current season (year)
        current_year = timezone.now().year
        
        logger.info(f"Starting NLL stats fetch for season {current_year}")
        
        # Call the fetch_nll_stats management command with --season as named argument
        call_command('fetch_nll_stats', season=current_year)
        
        logger.info(f"Successfully fetched NLL stats for season {current_year}")
        
    except Exception as e:
        logger.error(f"Error fetching NLL stats: {str(e)}")
        raise


@shared_task
def archive_old_leagues():
    """
    Archive completed leagues when the season ends.
    
    Marks league.status as 'season_complete' after the final game week
    (typically week 21) has completed. This prepares the league for renewal.
    
    Called by: Celery Beat schedule (daily check)
    """
    from web.models import League, Week
    
    try:
        current_season = timezone.now().year
        
        # Get all active leagues that are not yet completed
        active_leagues = League.objects.filter(
            is_active=True,
            status='active',
            season=current_season
        )
        
        for league in active_leagues:
            # Find the final week of the season
            final_week = Week.objects.filter(
                season=current_season
            ).order_by('-week_number').first()
            
            if final_week:
                # Calculate when to mark season complete (after playoffs end)
                archive_date = final_week.end_date + timedelta(days=3)
                
                if timezone.now().date() >= archive_date:
                    league.status = 'season_complete'
                    league.save(update_fields=['status'])
                    logger.info(
                        f"Marked league complete: {league.name} (ID: {league.id}) "
                        f"after season {current_season} week {final_week.week_number}. "
                        f"Ready for renewal."
                    )
        
        logger.info(f"Archive task completed for season {current_season}")
        
    except Exception as e:
        logger.error(f"Error archiving old leagues: {str(e)}")
        raise


def renew_league(league_id):
    """
    Renew a completed league for the next season.
    
    Takes a league that is marked as 'season_complete' and:
    1. Creates a LeagueHistory snapshot of the current season
    2. Advances the league.season by 1
    3. Resets league status to 'active' with draft_locked=True
    4. Handles rosters based on league_type:
       - Redraft: Clears all rosters for the new season
       - Dynasty: Copies all rosters to the new season
    5. For dynasty leagues: Creates rookie draft and future picks
    
    Args:
        league_id: ID of the league to renew
    
    Returns:
        The renewed League object or None if error
    
    Usage:
        from web.tasks import renew_league
        renewed_league = renew_league(league_id=5)
    """
    from web.models import League, LeagueHistory, Team, Roster, TaxiSquad, Draft
    
    try:
        league = League.objects.get(id=league_id)
        
        if league.status != 'season_complete':
            logger.warning(f"Cannot renew league {league.name}: status is '{league.status}', not 'season_complete'")
            return None
        
        current_season = league.season
        new_season = current_season + 1
        
        logger.info(f"[RENEWAL] Starting renewal for league {league.name} (ID: {league.id})")
        logger.info(f"[RENEWAL] League type: {league.league_type} | Current season: {current_season} → New season: {new_season}")
        
        # ============================================================================
        # 1. CREATE LEAGUEHISTORY SNAPSHOT OF COMPLETED SEASON
        # ============================================================================
        try:
            # Get the final champion and standings
            champion = league.season_winner
            
            # Calculate final standings JSON snapshot
            standings_data = []
            current_teams = Team.objects.filter(league=league, season_year=current_season).order_by('-id')
            
            for team in current_teams:
                team_data = {
                    'team_id': team.id,
                    'team_name': team.name,
                    'owner': team.owner.user.username if team.owner else 'Unknown'
                }
                standings_data.append(team_data)
            
            # Create history record
            league_history = LeagueHistory.objects.create(
                league=league,
                season_year=current_season,
                champion=champion,
                final_standings={'teams': standings_data}
            )
            
            logger.info(f"[RENEWAL] Created LeagueHistory for season {current_season}")
            
        except Exception as e:
            logger.error(f"[RENEWAL] Failed to create LeagueHistory: {str(e)}")
            raise
        
        # ============================================================================
        # 2. CREATE NEW TEAMS FOR NEXT SEASON (same owners, same names)
        # ============================================================================
        try:
            from web.models import FantasyTeamOwner
            old_teams = Team.objects.filter(league=league, season_year=current_season)
            logger.info(f"[RENEWAL] Found {old_teams.count()} teams in season {current_season}")
            
            for old_team in old_teams:
                # Create new team for next season with same owner and name
                new_team = Team.objects.create(
                    league=league,
                    name=old_team.name,
                    season_year=new_season,
                    waiver_priority=12 if league.use_waivers else 0  # Reset waiver priority
                )
                
                # Link the new team to the same owner as the old team
                if hasattr(old_team, 'owner') and old_team.owner:
                    FantasyTeamOwner.objects.create(
                        user=old_team.owner.user,
                        team=new_team
                    )
                    logger.info(f"[RENEWAL] Created new team '{new_team.name}' for {old_team.owner.user.username}")
                else:
                    logger.info(f"[RENEWAL] Created new team '{new_team.name}' (no owner)")
            
        except Exception as e:
            logger.error(f"[RENEWAL] Failed to create new teams: {str(e)}")
            raise
        
        # ============================================================================
        # 3. HANDLE ROSTERS BASED ON LEAGUE TYPE
        # ============================================================================
        if league.league_type == 'redraft':
            logger.info(f"[RENEWAL] Re-Draft league: Clearing all old rosters for new season")
            # Re-draft: DELETE all old rosters so teams start empty for draft
            try:
                old_rosters = Roster.objects.filter(
                    team__in=old_teams,
                    season_year=current_season
                )
                deleted_count, _ = old_rosters.delete()
                logger.info(f"[RENEWAL] Deleted {deleted_count} old roster entries")
                
                # Also clear taxi squad for redraft
                old_taxi = TaxiSquad.objects.filter(
                    team__in=old_teams,
                    player__isnull=False
                )
                taxi_deleted, _ = old_taxi.delete()
                logger.info(f"[RENEWAL] Deleted {taxi_deleted} old taxi squad entries")
                
            except Exception as e:
                logger.error(f"[RENEWAL] Failed to clear old rosters: {str(e)}")
                raise
            
        elif league.league_type == 'dynasty':
            logger.info(f"[RENEWAL] Dynasty league: Transferring rosters to new season")
            try:
                # Copy all rosters from current season teams to new season teams
                for old_team in old_teams:
                    new_team = Team.objects.get(league=league, season_year=new_season, name=old_team.name)
                    
                    # Transfer all roster entries
                    old_rosters = Roster.objects.filter(team=old_team, season_year=current_season)
                    transferred_count = 0
                    
                    for old_roster in old_rosters:
                        Roster.objects.create(
                            team=new_team,
                            player=old_roster.player,
                            season_year=new_season,
                            slot_assignment=old_roster.slot_assignment if old_roster.slot_assignment else None
                        )
                        transferred_count += 1
                    
                    logger.info(f"[RENEWAL] Transferred {transferred_count} players to {new_team.name}")
                    
                    # Move taxi squad players to main roster
                    old_taxi = TaxiSquad.objects.filter(team=old_team, player__isnull=False)
                    taxi_moved = 0
                    for taxi_entry in old_taxi:
                        if taxi_entry.player:
                            Roster.objects.create(
                                team=new_team,
                                player=taxi_entry.player,
                                season_year=new_season
                            )
                            taxi_moved += 1
                    
                    # Create empty taxi squad slots for new season
                    if league.use_taxi_squad:
                        for slot_num in range(1, league.taxi_squad_size + 1):
                            TaxiSquad.objects.get_or_create(
                                team=new_team,
                                slot_number=slot_num,
                                defaults={'player': None}
                            )
                        logger.info(f"[RENEWAL] Created {league.taxi_squad_size} taxi squad slots for {new_team.name}")
                
                logger.info(f"[RENEWAL] Roster transfer complete for all teams")
                
            except Exception as e:
                logger.error(f"[RENEWAL] Failed to transfer rosters: {str(e)}")
                raise
        
        # ============================================================================
        # 4. UPDATE LEAGUE METADATA FOR NEW SEASON
        # ============================================================================
        try:
            league.season = new_season
            league.status = 'active'
            league.season_winner = None  # Clear previous winner
            league.draft_locked = True  # Lock during draft
            league.save()
            
            logger.info(f"[RENEWAL] League updated: season={new_season}, status=active, draft_locked=True")
            
            # For redraft leagues: lock all NEW rosters during draft period
            if league.league_type == 'redraft':
                new_teams = Team.objects.filter(league=league, season_year=new_season)
                rosters = Roster.objects.filter(team__in=new_teams, season_year=new_season)
                rosters.update(is_locked=True, locked_reason='draft_in_progress')
                logger.info(f"[RENEWAL] Locked {rosters.count()} new rosters for draft period")
            
        except Exception as e:
            logger.error(f"[RENEWAL] Failed to update league: {str(e)}")
            raise
        
        # ============================================================================
        # 5. FOR DYNASTY LEAGUES: CREATE ROOKIE DRAFT & FUTURE PICKS
        # ============================================================================
        if league.league_type == 'dynasty':
            try:
                rookie_draft = create_rookie_draft(league.id, new_season)
                logger.info(f"[RENEWAL] Created rookie draft for dynasty league")
            except Exception as e:
                logger.error(f"[RENEWAL] Failed to create rookie draft: {str(e)}")
            
            try:
                if league.use_future_rookie_picks:
                    create_future_rookie_picks(league.id, years_ahead=5, num_rounds=None)
                    logger.info(f"[RENEWAL] Created future rookie picks for dynasty league")
            except Exception as e:
                logger.error(f"[RENEWAL] Failed to create future picks: {str(e)}")
        
        logger.info(f"[RENEWAL] ✓ League renewal complete: {league.name} renewed for season {new_season}")
        return league
        
    except League.DoesNotExist:
        logger.error(f"League with ID {league_id} not found")
        return None
    
    except Exception as e:
        logger.error(f"[RENEWAL] ✗ Error renewing league {league_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def create_rookie_draft(league_id, season_year, draft_style="snake"):
    """
    Create a 2-round rookie draft for a dynasty league using reverse standings.
    
    Reverse standings means: worst team picks first, best team picks last.
    This provides competitive balance for dynasty leagues.
    
    Initializes all draft picks in snake draft order:
    - Round 1: Worst to best (ascending standings)
    - Round 2: Best to worst (descending standings - snake)
    
    Args:
        league_id: ID of the league to create draft for
        season_year: Season year for which rookies are being drafted
        draft_style: "snake" or "linear" draft style
    
    Returns:
        RookieDraft object or None if error
    
    Usage:
        from web.tasks import create_rookie_draft
        draft = create_rookie_draft(league_id=5, season_year=2026)
    """
    from web.models import RookieDraft, RookieDraftPick, League, Team, Week, Roster
    from django.utils import timezone
    
    try:
        league = League.objects.get(id=league_id)
        
        # Check if rookie draft already exists for this league/season
        existing_draft = RookieDraft.objects.filter(
            league=league,
            season_year=season_year
        ).first()
        
        if existing_draft:
            logger.info(f"Rookie draft already exists for {league.name} season {season_year}")
            return existing_draft
        
        # Get teams for this league
        teams = list(Team.objects.filter(league=league).order_by('id'))
        num_teams = len(teams)
        
        if num_teams == 0:
            logger.warning(f"No teams found for league {league.name}")
            return None
        
        # Build standings map with points from previous season
        standings_map = {
            t.id: {
                "team": t,
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "total_points": 0,
                "points_against": 0,
                "games": 0,
            }
            for t in teams
        }
        
        # Get all completed weeks from previous season to calculate standings
        prev_season = season_year - 1
        today = timezone.now().date()
        completed_weeks = Week.objects.filter(
            season=prev_season,
            end_date__lt=today
        ).order_by('week_number')
        
        if completed_weeks.exists():
            # Calculate standings from completed weeks
            all_rosters = list(
                Roster.objects.filter(team__in=teams, league=league, player__active=True)
                .select_related("player", "team")
                .prefetch_related("player__game_stats__game__week")
            )
            
            # OPTIMIZATION: Group rosters by team_id for O(1) lookup instead of looping all rosters
            from collections import defaultdict
            rosters_by_team = defaultdict(list)
            for roster_entry in all_rosters:
                rosters_by_team[roster_entry.team_id].append(roster_entry)
            
            def fantasy_points(stat_obj, player):
                """Calculate fantasy points for a player stat"""
                if stat_obj is None:
                    return 0
                # Goalie scoring
                if player.position == "G":
                    return (
                        stat_obj.wins * float(league.scoring_goalie_wins) +
                        stat_obj.saves * float(league.scoring_goalie_saves) +
                        stat_obj.goals_against * float(league.scoring_goalie_goals_against) +
                        stat_obj.goals * float(league.scoring_goalie_goals) +
                        stat_obj.assists * float(league.scoring_goalie_assists)
                    )
                # Field player scoring
                return (
                    stat_obj.goals * float(league.scoring_goals) +
                    stat_obj.assists * float(league.scoring_assists) +
                    stat_obj.loose_balls * float(league.scoring_loose_balls) +
                    stat_obj.caused_turnovers * float(league.scoring_caused_turnovers) +
                    stat_obj.blocked_shots * float(league.scoring_blocked_shots) +
                    stat_obj.turnovers * float(league.scoring_turnovers)
                )
            
            def team_week_total(team_id, week_obj):
                """Calculate total points for a team in a specific week"""
                total = 0
                # OPTIMIZATION: Access only this team's rosters (12-14 items) instead of all rosters (140+ items)
                team_rosters = rosters_by_team.get(team_id, [])
                for roster_entry in team_rosters:
                    week_added = roster_entry.week_added or 0
                    week_dropped = roster_entry.week_dropped or 999
                    if week_added <= week_obj.week_number < week_dropped:
                        player = roster_entry.player
                        stat = next(
                            (s for s in player.game_stats.all() if s.game.week_id == week_obj.id),
                            None
                        )
                        pts = fantasy_points(stat, player)
                        total += pts
                return total
            
            # Process each completed week
            for week in completed_weeks:
                # Create simple matchups - pair teams sequentially
                for i in range(0, num_teams, 2):
                    if i + 1 < num_teams:
                        team_a_id = teams[i].id
                        team_b_id = teams[i + 1].id
                        
                        home_total = team_week_total(team_a_id, week)
                        away_total = team_week_total(team_b_id, week)
                        
                        standings_map[team_a_id]["total_points"] += home_total
                        standings_map[team_b_id]["total_points"] += away_total
                        standings_map[team_a_id]["points_against"] += away_total
                        standings_map[team_b_id]["points_against"] += home_total
                        standings_map[team_a_id]["games"] += 1
                        standings_map[team_b_id]["games"] += 1
                        
                        if home_total > away_total:
                            standings_map[team_a_id]["wins"] += 1
                            standings_map[team_b_id]["losses"] += 1
                        elif home_total < away_total:
                            standings_map[team_b_id]["wins"] += 1
                            standings_map[team_a_id]["losses"] += 1
                        else:
                            standings_map[team_a_id]["ties"] += 1
                            standings_map[team_b_id]["ties"] += 1
            
            # Sort standings: worst team first (lower wins, lower points)
            standings_list = list(standings_map.values())
            standings_list.sort(key=lambda r: (r["wins"], r["total_points"], r["team"].name))
            # Extract teams in reverse standings order (worst to best)
            draft_order_teams = [s["team"] for s in standings_list]
            logger.info(f"Draft order determined from previous season standings")
        else:
            # No previous season data - use team creation order
            logger.info(f"No completed weeks from season {prev_season}, using team creation order for draft")
            draft_order_teams = teams
        
        # Create the rookie draft
        rookie_draft = RookieDraft.objects.create(
            league=league,
            season_year=season_year,
            draft_style=draft_style,
            is_active=False,
            completed=False,
        )
        
        # Create draft picks for 2 rounds using draft_order_teams
        pick_number = 1
        for round_num in range(1, 3):  # 2 rounds for rookie draft
            if draft_style == "snake" and round_num == 2:
                # Snake draft: reverse order in round 2
                round_teams = list(reversed(draft_order_teams))
            else:
                # Linear draft or round 1: normal order (worst to best)
                round_teams = draft_order_teams
            
            for pick_in_round, team in enumerate(round_teams, 1):
                RookieDraftPick.objects.create(
                    draft=rookie_draft,
                    round=round_num,
                    pick_number=pick_in_round,
                    overall_pick=pick_number,
                    team=team,
                )
                pick_number += 1
        
        logger.info(f"Created rookie draft for {league.name} (season {season_year}) with {pick_number - 1} total picks (reverse standings)")
        
        return rookie_draft
        
    except League.DoesNotExist:
        logger.error(f"League with ID {league_id} not found")
        return None
    except Exception as e:
        logger.error(f"Error creating rookie draft for league {league_id}: {str(e)}")
        return None


def reorder_rookie_draft_picks(draft_id, new_order):
    """
    Reorder rookie draft picks by swapping pick order and positions.
    
    Allows commissioner to customize draft order after it's been generated.
    Can only be called before draft starts (order_locked=False).
    
    Args:
        draft_id: ID of the RookieDraft to reorder
        new_order: List of team IDs in desired draft order
        Example: [team_5, team_2, team_8, team_1] for 4-team draft
    
    Returns:
        (success: bool, message: str)
    
    Usage:
        from web.tasks import reorder_rookie_draft_picks
        success, msg = reorder_rookie_draft_picks(draft_id=5, new_order=[2, 1, 3, 4])
    """
    from web.models import RookieDraft, RookieDraftPick
    
    try:
        draft = RookieDraft.objects.get(id=draft_id)
        
        # Prevent reordering if draft has started or is locked
        if draft.order_locked or draft.is_active:
            return False, "Cannot reorder picks - draft is locked or in progress"
        
        # Validate new order
        existing_picks = RookieDraftPick.objects.filter(draft=draft).values_list('team_id', flat=True).distinct()
        if set(new_order) != set(existing_picks):
            return False, f"New order teams don't match existing draft picks. Expected: {list(existing_picks)}"
        
        # Get all picks for both rounds
        all_picks = list(RookieDraftPick.objects.filter(draft=draft).order_by('overall_pick'))
        
        if not all_picks:
            return False, "No picks found in draft"
        
        num_teams = len(new_order)
        picks_per_round = num_teams
        
        # Rebuild picks with new team order
        pick_number = 1
        for round_num in range(1, 3):  # 2 rounds
            if draft.draft_style == "snake" and round_num == 2:
                # Snake draft: reverse order in round 2
                round_order = list(reversed(new_order))
            else:
                # Linear or round 1: normal order
                round_order = new_order
            
            for pick_in_round, team_id in enumerate(round_order, 1):
                # Find the pick object for this team
                pick = all_picks[pick_number - 1]
                
                # Update pick position
                pick.round = round_num
                pick.pick_number = pick_in_round
                pick.overall_pick = pick_number
                pick.team_id = team_id
                pick.save()
                
                pick_number += 1
        
        logger.info(f"Reordered draft {draft.id} for {draft.league.name} season {draft.season_year}")
        logger.info(f"New order: {new_order}")
        
        return True, f"Successfully reordered draft for {draft.league.name}"
        
    except RookieDraft.DoesNotExist:
        return False, f"Draft with ID {draft_id} not found"
    except Exception as e:
        logger.error(f"Error reordering draft {draft_id}: {str(e)}")
        return False, f"Error reordering draft: {str(e)}"


def lock_rookie_draft_order(draft_id):
    """
    Lock the draft order to prevent further changes.
    Called when commissioner is satisfied with the draft order and wants to start draft.
    
    Args:
        draft_id: ID of the RookieDraft to lock
    
    Returns:
        (success: bool, message: str)
    
    Usage:
        from web.tasks import lock_rookie_draft_order
        success, msg = lock_rookie_draft_order(draft_id=5)
    """
    from web.models import RookieDraft
    
    try:
        draft = RookieDraft.objects.get(id=draft_id)
        
        if draft.order_locked:
            return False, "Draft order already locked"
        
        draft.order_locked = True
        draft.save()
        
        logger.info(f"Locked draft order for {draft.league.name} season {draft.season_year}")
        
        return True, f"Draft order locked for {draft.league.name}"
        
    except RookieDraft.DoesNotExist:
        return False, f"Draft with ID {draft_id} not found"
    except Exception as e:
        logger.error(f"Error locking draft order {draft_id}: {str(e)}")
        return False, f"Error locking draft: {str(e)}"

@shared_task
def lock_taxi_squad_at_season_start(season_year):
    """
    Lock all taxi squad slots when the first game of the season starts.
    This should be called automatically when the first game is scheduled or starts.
    """
    from web.models import TaxiSquad, League, Week
    
    try:
        # Get all dynasty leagues
        dynasty_leagues = League.objects.filter(league_type='dynasty')
        
        locked_count = 0
        
        for league in dynasty_leagues:
            # Get all taxi squad entries for this league's teams
            taxi_squad_entries = TaxiSquad.objects.filter(
                team__league=league,
                is_locked=False
            )
            
            # Lock them
            updated = taxi_squad_entries.update(is_locked=True)
            locked_count += updated
            
            if updated > 0:
                logger.info(f"Locked {updated} taxi squad slots in league {league.name} for season {season_year}")
        
        logger.info(f"Total taxi squad slots locked: {locked_count} for season {season_year}")
        return True, f"Locked {locked_count} taxi squad slots"
        
    except Exception as e:
        logger.error(f"Error locking taxi squad at season start: {str(e)}")
        return False, f"Error locking taxi squad: {str(e)}"


def create_future_rookie_picks(league_id, team=None, years_ahead=5, num_rounds=None):
    """
    Create future rookie picks for a dynasty league team or all teams.
    
    Creates picks for multiple years in the future based on reverse standings order
    (worst team picks first). Pick order rotates each year based on previous season standings.
    
    Args:
        league_id: ID of the dynasty league
        team: Optional Team object; if provided, creates picks only for that team.
              If None, creates picks for all teams in the league.
        years_ahead: Number of years into the future to create picks (default: 5)
        num_rounds: Number of rounds per draft (default: uses league draft.total_rounds or roster_size)
    
    Returns:
        Tuple of (success: bool, message: str, picks_created: int)
    """
    from web.models import League, FutureRookiePick, Team, Draft, Week, Roster
    
    try:
        league = League.objects.get(id=league_id)
        
        # Only for dynasty leagues
        if league.league_type != "dynasty":
            return False, "Future picks only available for dynasty leagues", 0
        
        # Check if feature is enabled
        if not getattr(league, 'use_future_rookie_picks', True):
            return False, "Future rookie picks feature is disabled for this league", 0
        
        # Get all teams in the league
        all_teams = list(league.teams.all())
        if not all_teams:
            return False, "No teams in league", 0
        
        # Determine number of rounds
        if num_rounds is None:
            draft = getattr(league, 'draft', None)
            if draft and hasattr(draft, 'total_rounds'):
                num_rounds = draft.total_rounds
            else:
                num_rounds = league.roster_size if hasattr(league, 'roster_size') else 12
        
        # Get current year
        current_year = timezone.now().year
        picks_created = 0
        
        # For each year in advance
        for year_offset in range(1, years_ahead + 1):
            future_year = current_year + year_offset
            
            # Calculate draft order based on standings from previous year
            standings_order = _calculate_draft_order_from_standings(league, future_year - 1)
            
            # If no standings data (first year of league), use team ID order
            if not standings_order:
                standings_order = list(league.teams.all().order_by('id'))
            
            # Create picks for each round using standings order
            for round_num in range(1, num_rounds + 1):
                for pick_in_round, team_obj in enumerate(standings_order, 1):
                    # Create the future pick with standings-based order
                    frp, created = FutureRookiePick.objects.get_or_create(
                        league=league,
                        year=future_year,
                        round_number=round_num,
                        pick_number=pick_in_round,
                        defaults={
                            'team': team_obj,
                            'original_owner': team_obj,
                        }
                    )
                    
                    if created:
                        picks_created += 1
            
            logger.info(f"Created {num_rounds} rounds of future picks for {league.name} season {future_year} (based on {future_year-1} standings)")
        
        logger.info(f"Created {picks_created} future rookie picks for league {league.name}")
        return True, f"Created {picks_created} future picks ({years_ahead} years × {num_rounds} rounds)", picks_created
        
    except League.DoesNotExist:
        return False, f"League {league_id} not found", 0
    except Exception as e:
        logger.error(f"Error creating future rookie picks: {str(e)}")
        return False, f"Error creating picks: {str(e)}", 0


def _calculate_draft_order_from_standings(league, season_year):
    """
    Calculate draft order (worst to best) from previous season standings.
    
    Args:
        league: League object
        season_year: Year to calculate standings for
    
    Returns:
        List of Team objects ordered by reverse standings (worst team first)
        Returns None if no standings data available
    """
    from web.models import Week, Roster, Team
    
    try:
        # Get all teams
        teams = list(Team.objects.filter(league=league).order_by('id'))
        if not teams:
            return None
        
        # Build standings map
        standings_map = {
            t.id: {
                "team": t,
                "wins": 0,
                "losses": 0,
                "ties": 0,
                "total_points": 0.0,
            }
            for t in teams
        }
        
        # Get all completed weeks from the specified season
        today = timezone.now().date()
        completed_weeks = Week.objects.filter(
            season=season_year,
            end_date__lt=today
        ).order_by('week_number')
        
        if not completed_weeks.exists():
            logger.info(f"No completed weeks for season {season_year}, using default order")
            return None
        
        # Calculate points for each team in each completed week
        def fantasy_points(stat_obj, player):
            """Calculate fantasy points for a player stat"""
            if stat_obj is None:
                return 0.0
            # Goalie scoring
            if player.position == "G":
                return float(
                    stat_obj.wins * league.scoring_goalie_wins +
                    stat_obj.saves * league.scoring_goalie_saves +
                    stat_obj.goals_against * league.scoring_goalie_goals_against +
                    stat_obj.goals * league.scoring_goalie_goals +
                    stat_obj.assists * league.scoring_goalie_assists
                )
            # Field player scoring
            return float(
                stat_obj.goals * league.scoring_goals +
                stat_obj.assists * league.scoring_assists +
                stat_obj.loose_balls * league.scoring_loose_balls +
                stat_obj.caused_turnovers * league.scoring_caused_turnovers +
                stat_obj.blocked_shots * league.scoring_blocked_shots +
                stat_obj.turnovers * league.scoring_turnovers
            )
        
        # Get all rosters with related stats
        all_rosters = list(
            Roster.objects.filter(team__in=teams, season_year=season_year, player__active=True)
            .select_related("player", "team")
            .prefetch_related("player__game_stats__game__week")
        )
        
        # OPTIMIZATION: Group rosters by team_id for O(1) lookup instead of looping all rosters
        from collections import defaultdict
        rosters_by_team = defaultdict(list)
        for roster_entry in all_rosters:
            rosters_by_team[roster_entry.team_id].append(roster_entry)
        
        # Calculate points for each team in each completed week
        for week in completed_weeks:
            # Simple matchup: pair teams sequentially
            for i in range(0, len(teams), 2):
                if i + 1 < len(teams):
                    team1 = teams[i]
                    team2 = teams[i + 1]
                    
                    # Calculate team 1 points
                    # OPTIMIZATION: Access only team1's rosters (12-14 items) instead of all rosters (140+ items)
                    team1_total = 0.0
                    team1_rosters = rosters_by_team.get(team1.id, [])
                    for roster_entry in team1_rosters:
                        week_added = roster_entry.week_added or 0
                        week_dropped = roster_entry.week_dropped or 999
                        if week_added <= week.week_number < week_dropped:
                            player = roster_entry.player
                            # Look for stat for this week
                            stat = next(
                                (s for s in player.game_stats.all() if s.game.week_id == week.id),
                                None
                            )
                            if stat:
                                team1_total += fantasy_points(stat, player)
                    
                    # Calculate team 2 points
                    # OPTIMIZATION: Access only team2's rosters (12-14 items) instead of all rosters (140+ items)
                    team2_total = 0.0
                    team2_rosters = rosters_by_team.get(team2.id, [])
                    for roster_entry in team2_rosters:
                        week_added = roster_entry.week_added or 0
                        week_dropped = roster_entry.week_dropped or 999
                        if week_added <= week.week_number < week_dropped:
                            player = roster_entry.player
                            stat = next(
                                (s for s in player.game_stats.all() if s.game.week_id == week.id),
                                None
                            )
                            if stat:
                                team2_total += fantasy_points(stat, player)
                    
                    # Update standings
                    standings_map[team1.id]["total_points"] += team1_total
                    standings_map[team2.id]["total_points"] += team2_total
                    
                    if team1_total > team2_total:
                        standings_map[team1.id]["wins"] += 1
                        standings_map[team2.id]["losses"] += 1
                    elif team1_total < team2_total:
                        standings_map[team2.id]["wins"] += 1
                        standings_map[team1.id]["losses"] += 1
                    else:
                        standings_map[team1.id]["ties"] += 1
                        standings_map[team2.id]["ties"] += 1
        
        # Sort standings: worst team first (lower wins, lower points)
        standings_list = list(standings_map.values())
        standings_list.sort(key=lambda r: (r["wins"], r["total_points"], r["team"].name))
        
        # Return teams in order (worst to best)
        draft_order = [s["team"] for s in standings_list]
        
        logger.info(f"Calculated draft order for {league.name} from season {season_year} standings")
        logger.info(f"Draft order: {' → '.join([t.name for t in draft_order])}")
        
        return draft_order
        
    except Exception as e:
        logger.error(f"Error calculating draft order from standings: {str(e)}")
        return None

@shared_task(name='web.tasks.auto_complete_seasons')
def auto_complete_seasons():
    """
    Automatically mark leagues as season_complete on the Tuesday after their championship week ends.
    
    IMPORTANT: This task runs EVERY TUESDAY (per Celery Beat schedule), but each league is only 
    marked complete ONCE - on the specific Tuesday after its championship week ends. After that,
    the league status changes from 'active' to 'season_complete', so it won't be reprocessed on 
    subsequent Tuesday runs.
    
    Works with any championship structure:
    - Year 1: Week 20 championship -> marked complete the Tuesday after week 20 ends
    - Year 2: Week 21 championship -> marked complete the Tuesday after week 21 ends
    - All leagues in a season share the same week calendar
    
    Finds the most recent week that has ended for the season, and if it's Tuesday,
    marks all still-'active' leagues as season_complete (once per league).
    
    Called via Celery Beat schedule: Every Tuesday at 8 AM PT
    """
    from web.models import League, Week
    from datetime import datetime
    import pytz
    
    today_utc = timezone.now()
    logger.info(f"[AUTO COMPLETE] Running season auto-complete check at {today_utc}")
    
    try:
        # Convert to Pacific time for business logic check
        pacific = pytz.timezone('US/Pacific')
        today_pacific = today_utc.astimezone(pacific)
        today_date_pacific = today_pacific.date()
        
        # Find the most recent completed week for this season
        # (could be week 20, 21, or later depending on playoff structure)
        # We look for the most recent week that has actually ENDED, not just the latest week in the system
        latest_ended_week = Week.objects.filter(
            season=today_utc.year,
            end_date__lt=today_date_pacific  # Only weeks that have ended
        ).order_by('-week_number').first()
        
        if not latest_ended_week:
            logger.info(f"[AUTO COMPLETE] No completed weeks found for season {today_utc.year}")
            return "No completed weeks found"
        
        # Check if we're on Tuesday (Pacific) and the latest ended week is championship-like
        # Championship could be week 20, 21, 22, etc - we just found the most recent week that ended
        if today_pacific.weekday() == 1:  # Tuesday = 1
            logger.info(f"[AUTO COMPLETE] Today is TUESDAY (Pacific). Latest ended week: {latest_ended_week.week_number} (ended: {latest_ended_week.end_date})")
            
            # Mark all active leagues for this season as season_complete
            # Once marked complete, they won't match status='active' on future Tuesday runs
            active_leagues = League.objects.filter(
                season=today_utc.year,
                status='active'  # Only auto-complete active leagues (already-complete ones won't match)
            )
            
            updated_count = 0
            for league in active_leagues:
                try:
                    league.status = 'season_complete'
                    league.save()
                    logger.info(f"[AUTO COMPLETE] ✓ Marked {league.name} as season_complete (will not be reprocessed on future Tuesdays)")
                    updated_count += 1
                except Exception as e:
                    logger.error(f"[AUTO COMPLETE] Error marking {league.name} as complete: {str(e)}")
            
            if updated_count > 0:
                logger.info(f"[AUTO COMPLETE] Successfully completed {updated_count} league(s) for season {today_utc.year}")
            else:
                logger.info(f"[AUTO COMPLETE] No active leagues to process (all already marked season_complete or none exist)")
        else:
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            current_day = day_names[today_pacific.weekday()]
            logger.info(f"[AUTO COMPLETE] Today is {current_day} (not Tuesday) - skipping season completion (latest ended week is {latest_ended_week.week_number})")
        
    except Exception as e:
        logger.error(f"[AUTO COMPLETE] Error in auto_complete_season_task: {str(e)}")
        raise


@shared_task(name='web.tasks.scrape_nll_transactions_task', bind=True, max_retries=3)
def scrape_nll_transactions_celery_task(self):
    """
    Scrape NLL transactions from nll.com
    Called daily at 4 AM UTC via Celery Beat schedule
    """
    from web.management.commands.scrape_nll_transactions import scrape_nll_transactions_task
    
    try:
        logger.info("Starting nightly NLL transactions scrape...")
        count, html = scrape_nll_transactions_task()
        logger.info(f"NLL transactions scrape completed. Found {count} transaction articles")
        return f"Scraped {count} transactions"
    
    except Exception as e:
        logger.error(f"Error scraping NLL transactions: {str(e)}")
        # Retry with exponential backoff: 60s, 300s, 900s
        try:
            self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
        except Exception as retry_error:
            logger.critical(f"NLL scrape task failed after {self.request.retries} retries: {str(retry_error)}")
            raise