from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.contrib.sessions.models import Session
from datetime import timedelta
import logging

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





@shared_task(name='unlock_rosters_and_process_transactions')
def unlock_rosters_and_process_transactions():
    """
    Unlock rosters (Monday 9am PT) and execute pending waivers/trades.
    Called automatically at Monday 9am PT via Celery Beat schedule.
    Uses the process_waivers management command to ensure consistency.
    """
    from django.core.management import call_command
    from web.models import Week, League
    
    now = timezone.now()
    
    try:
        # Find weeks where unlock_time has just passed
        weeks = Week.objects.filter(
            roster_unlock_time__lte=now,
            roster_unlock_time__gte=now - timedelta(hours=1)
        )
        
        for week in weeks:
            logger.info(f"Unlocking rosters for Week {week.week_number}, Season {week.season}")
            
            # Process waivers and trades for all active leagues using the management command
            try:
                call_command('process_waivers')
                logger.info(f"Successfully processed waivers and trades")
            except Exception as e:
                logger.error(f"Error calling process_waivers command: {str(e)}")
            
            # Update league current_week to next week
            update_current_week_for_season(week.season)
        
        return f"Successfully unlocked rosters and processed transactions for {weeks.count()} weeks"
    
    except Exception as e:
        logger.error(f"Error unlocking rosters and processing transactions: {str(e)}")
        raise


def update_current_week_for_season(season):
    """
    Update all leagues' current_week to the next unlocked week.
    Called when Monday 9am PT rosters unlock.
    """
    from web.models import League, Week
    
    try:
        leagues = League.objects.filter(created_at__year=season, is_active=True)
        
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
                logger.info(f"Updated {league.name} current week to Week {next_week.week_number}")
    
    except Exception as e:
        logger.error(f"Error updating current week for season {season}: {str(e)}")


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
    
    Marks leagues as inactive (is_active=False) after the final game week
    (typically week 21) has completed. The Monday after the final week is
    when rosters unlock for the last time - at that point the league is archived.
    
    Called by: Celery Beat schedule (daily check)
    """
    from web.models import League, Week
    
    try:
        current_season = timezone.now().year
        
        # Get all active leagues
        active_leagues = League.objects.filter(is_active=True)
        
        for league in active_leagues:
            # Find the final week of the regular season (highest week number, or week 21)
            final_week = Week.objects.filter(
                season=current_season
            ).order_by('-week_number').first()
            
            # If current time is past the Monday after the final week ends
            # (allowing for playoff buffer), archive the league
            if final_week:
                # Calculate Monday after final week ends (add 2 days for games + 1 for Monday)
                archive_date = final_week.end_date + timedelta(days=3)
                
                if timezone.now().date() >= archive_date:
                    league.is_active = False
                    league.save()
                    logger.info(
                        f"Archived league: {league.name} (ID: {league.id}) "
                        f"after season {current_season} week {final_week.week_number}"
                    )
        
        logger.info(f"Archive task completed for season {current_season}")
        
    except Exception as e:
        logger.error(f"Error archiving old leagues: {str(e)}")
        raise


def renew_league(old_league_id, new_season=None):
    """
    Create a new league for the next season with same settings and members.
    
    This is called by commissioners to renew their league. Creates a new
    League with identical settings and optionally transfers team owners.
    
    For Dynasty leagues: Transfers all players from old league teams to new league teams.
    For Re-Draft leagues: Only transfers team owners; players are cleared and must be drafted fresh.
    
    Args:
        old_league_id: ID of the league to renew
        new_season: Year for new league (defaults to next year)
    
    Returns:
        New League object or None if error
    
    Usage:
        from web.tasks import renew_league
        new_league = renew_league(old_league.id)
    """
    from web.models import League, FantasyTeamOwner, Team, Roster
    
    try:
        old_league = League.objects.get(id=old_league_id)
        
        if new_season is None:
            new_season = timezone.now().year + 1
        
        # Create new league with same settings
        new_league = League(
            name=f"{old_league.name} - {new_season}",
            commissioner=old_league.commissioner,
            description=old_league.description,
            max_teams=old_league.max_teams,
            is_public=old_league.is_public,
            is_active=True,
            roster_size=old_league.roster_size,
            roster_forwards=old_league.roster_forwards,
            roster_defense=old_league.roster_defense,
            roster_goalies=old_league.roster_goalies,
            playoff_weeks=old_league.playoff_weeks,
            playoff_teams=old_league.playoff_teams,
            use_waivers=old_league.use_waivers,
            league_type=old_league.league_type,  # Preserve league type
            playoff_reseed=old_league.playoff_reseed,
            roster_format=old_league.roster_format,
            multigame_scoring=old_league.multigame_scoring,
            # Copy all scoring settings
            scoring_goals=old_league.scoring_goals,
            scoring_assists=old_league.scoring_assists,
            scoring_loose_balls=old_league.scoring_loose_balls,
            scoring_caused_turnovers=old_league.scoring_caused_turnovers,
            scoring_blocked_shots=old_league.scoring_blocked_shots,
            scoring_turnovers=old_league.scoring_turnovers,
            scoring_goalie_wins=old_league.scoring_goalie_wins,
            scoring_goalie_saves=old_league.scoring_goalie_saves,
            scoring_goalie_goals_against=old_league.scoring_goalie_goals_against,
            scoring_goalie_goals=old_league.scoring_goalie_goals,
            scoring_goalie_assists=old_league.scoring_goalie_assists,
        )
        new_league.save()
        
        # Get all previous team owners and their teams
        old_teams = Team.objects.filter(league=old_league)
        old_team_owners = FantasyTeamOwner.objects.filter(
            team__league=old_league
        ).distinct('user')
        
        # For Dynasty leagues, transfer rosters; for Re-Draft, just reset rosters
        if old_league.league_type == "dynasty":
            # Dynasty: Create new teams and transfer all rosters
            logger.info(f"Dynasty league renewal: transferring rosters to new league")
            for old_team in old_teams:
                # Create new team in new league with same name and owner
                new_team = Team.objects.create(
                    league=new_league,
                    name=old_team.name,
                    owner=old_team.owner,
                )
                
                # Transfer all roster entries from old team to new team
                old_rosters = Roster.objects.filter(team=old_team)
                for old_roster in old_rosters:
                    Roster.objects.create(
                        team=new_team,
                        player=old_roster.player,
                        season_year=new_season,
                    )
                logger.info(f"Transferred roster for team '{new_team.name}' ({old_rosters.count()} players)")
        else:
            # Re-Draft: Create new empty teams for each owner
            logger.info(f"Re-Draft league renewal: creating empty rosters for re-drafting")
            for old_team in old_teams:
                Team.objects.create(
                    league=new_league,
                    name=old_team.name,
                    owner=old_team.owner,
                )
        
        logger.info(f"Created renewed league '{new_league.name}' (ID: {new_league.id}) " +
                   f"with {old_team_owners.count()} members from {old_league.name} ({old_league.league_type})")
        
        # For dynasty leagues, create a rookie draft for the new season
        if old_league.league_type == "dynasty":
            try:
                create_rookie_draft(new_league.id, new_season)
            except Exception as e:
                logger.error(f"Failed to create rookie draft for league {new_league.id}: {str(e)}")
        
        return new_league
        
    except League.DoesNotExist:
        logger.error(f"League with ID {old_league_id} not found")
        return None
    except Exception as e:
        logger.error(f"Error renewing league {old_league_id}: {str(e)}")
        return None


def create_rookie_draft(league_id, season_year, draft_style="snake"):
    """
    Create a 2-round rookie draft for a dynasty league.
    
    Initializes all draft picks in snake draft order (teams 1,2,3,4 then 4,3,2,1 in round 2).
    
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
    from web.models import RookieDraft, RookieDraftPick, League, Team
    
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
        
        # Create the rookie draft
        rookie_draft = RookieDraft.objects.create(
            league=league,
            season_year=season_year,
            draft_style=draft_style,
            is_active=False,
            completed=False,
        )
        
        # Get teams for this league and sort by ID for consistent ordering
        teams = list(Team.objects.filter(league=league).order_by('id'))
        num_teams = len(teams)
        
        if num_teams == 0:
            logger.warning(f"No teams found for league {league.name}")
            return rookie_draft
        
        # Create draft picks for 2 rounds
        pick_number = 1
        for round_num in range(1, 3):  # 2 rounds for rookie draft
            if draft_style == "snake" and round_num == 2:
                # Snake draft: reverse order in round 2
                round_teams = list(reversed(teams))
            else:
                # Linear draft or round 1: normal order
                round_teams = teams
            
            for pick_in_round, team in enumerate(round_teams, 1):
                RookieDraftPick.objects.create(
                    draft=rookie_draft,
                    round=round_num,
                    pick_number=pick_in_round,
                    overall_pick=pick_number,
                    team=team,
                )
                pick_number += 1
        
        logger.info(f"Created rookie draft for {league.name} (season {season_year}) with {pick_number - 1} total picks")
        
        return rookie_draft
        
    except League.DoesNotExist:
        logger.error(f"League with ID {league_id} not found")
        return None
    except Exception as e:
        logger.error(f"Error creating rookie draft for league {league_id}: {str(e)}")
        return None

