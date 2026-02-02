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
    Archive completed leagues at end of season.
    
    Marks leagues as inactive (is_active=False) if their playoff weeks
    have completed. Called by Celery Beat at end of season.
    
    Called by: Celery Beat schedule (configurable)
    """
    from web.models import League, Week
    
    try:
        current_season = timezone.now().year
        
        # Get all active leagues
        active_leagues = League.objects.filter(is_active=True)
        
        for league in active_leagues:
            # Find the last playoff week for this season
            playoff_end = Week.objects.filter(
                season=current_season,
                is_playoff=True
            ).order_by('-week_number').first()
            
            # If there's no playoff week or current time has passed the end of playoffs
            if playoff_end and timezone.now() > playoff_end.end_date + timedelta(days=1):
                league.is_active = False
                league.save()
                logger.info(f"Archived league: {league.name} (ID: {league.id})")
        
        logger.info(f"Archive task completed for season {current_season}")
        
    except Exception as e:
        logger.error(f"Error archiving old leagues: {str(e)}")
        raise


def renew_league(old_league_id, new_season=None):
    """
    Create a new league for the next season with same settings and members.
    
    This is called by commissioners to renew their league. Creates a new
    League with identical settings and optionally transfers team owners.
    
    Args:
        old_league_id: ID of the league to renew
        new_season: Year for new league (defaults to next year)
    
    Returns:
        New League object or None if error
    
    Usage:
        from web.tasks import renew_league
        new_league = renew_league(old_league.id)
    """
    from web.models import League, FantasyTeamOwner, Team
    
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
        
        # Invite all previous team owners to join the new league
        old_team_owners = FantasyTeamOwner.objects.filter(
            team__league=old_league
        ).distinct('user')
        
        logger.info(f"Created renewed league '{new_league.name}' (ID: {new_league.id}) " +
                   f"with {old_team_owners.count()} invited members from {old_league.name}")
        
        return new_league
        
    except League.DoesNotExist:
        logger.error(f"League with ID {old_league_id} not found")
        return None
    except Exception as e:
        logger.error(f"Error renewing league {old_league_id}: {str(e)}")
        return None

