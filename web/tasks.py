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
def send_password_reset_email(user_id, reset_url):
    """Send password reset email"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    try:
        user = User.objects.get(id=user_id)
        subject = 'Reset Your NLL Fantasy Password'
        html_message = render_to_string('emails/password_reset.html', {
            'user': user,
            'reset_url': reset_url,
        })
        
        send_email_task.delay(
            subject,
            f"Reset your password at: {reset_url}",
            [user.email],
            html_message=html_message
        )
        logger.info(f"Password reset email queued for {user.email}")
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} not found")


@shared_task
def process_waivers():
    """
    Process pending waivers at scheduled time
    Called by Celery Beat at configured schedule (default: 11 PM daily)
    """
    from web.models import WaiverClaim, Roster
    
    try:
        # Get all pending waivers that should be processed
        pending_waivers = WaiverClaim.objects.filter(
            status='pending',
            process_at__lte=timezone.now()
        ).order_by('priority', 'created_at')
        
        processed_count = 0
        for waiver in pending_waivers:
            try:
                # Process waiver logic here
                waiver.process()
                processed_count += 1
            except Exception as e:
                logger.error(f"Error processing waiver {waiver.id}: {str(e)}")
                continue
        
        logger.info(f"Processed {processed_count} waivers")
    except Exception as e:
        logger.error(f"Waiver processing task failed: {str(e)}")
        raise


@shared_task
def check_league_status():
    """
    Check and update league statuses
    Called by Celery Beat every 6 hours
    """
    from web.models import League, Week
    
    try:
        for league in League.objects.filter(is_active=True):
            try:
                # Update league status based on current week
                current_week = Week.objects.filter(
                    league=league,
                    start_date__lte=timezone.now().date(),
                    end_date__gte=timezone.now().date()
                ).first()
                
                # Add your league status update logic here
                logger.info(f"Updated status for league {league.name}")
            except Exception as e:
                logger.error(f"Error checking league {league.name}: {str(e)}")
                continue
                
    except Exception as e:
        logger.error(f"League status check task failed: {str(e)}")
        raise


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


@shared_task
def send_league_notification(league_id, subject, message):
    """
    Send notification to all league members
    """
    from web.models import League, ChatMessage
    
    try:
        league = League.objects.get(id=league_id)
        
        # Post to league chat
        ChatMessage.objects.create(
            league=league,
            sender=None,  # System message
            message=message,
            message_type=ChatMessage.MessageType.SYSTEM
        )
        
        logger.info(f"Notification sent to league {league.name}")
    except Exception as e:
        logger.error(f"Failed to send league notification: {str(e)}")
        raise


@shared_task
def generate_performance_stats():
    """
    Generate performance statistics for leagues and teams
    This can be called periodically or on-demand
    """
    from web.models import League, Roster, PlayerGameStat
    from django.db.models import Sum, Avg, Count
    
    try:
        stats_generated = 0
        for league in League.objects.filter(is_active=True):
            try:
                # Calculate league-wide stats
                league_stats = {
                    'total_trades': league.trade_set.count(),
                    'total_waivers': league.waivers.count(),
                    'avg_score': Roster.objects.filter(
                        league=league
                    ).aggregate(Avg('week_score'))['week_score__avg'],
                }
                
                # Could save to cache or database here
                logger.info(f"Generated stats for league {league.name}")
                stats_generated += 1
            except Exception as e:
                logger.error(f"Error generating stats for league {league.id}: {str(e)}")
                continue
        
        return f"Generated stats for {stats_generated} leagues"
    except Exception as e:
        logger.error(f"Performance stats generation task failed: {str(e)}")
        raise


@shared_task
def archive_old_leagues():
    """
    Archive leagues that are no longer active (season ended)
    """
    from web.models import League
    from datetime import timedelta
    
    try:
        # Archive leagues whose last week ended more than 30 days ago
        cutoff_date = timezone.now() - timedelta(days=30)
        
        archived = League.objects.filter(
            is_active=True,
            week__end_date__lt=cutoff_date
        ).distinct().update(is_active=False)
        
        logger.info(f"Archived {archived} old leagues")
        return archived
    except Exception as e:
        logger.error(f"League archival task failed: {str(e)}")
        raise


@shared_task(name='lock_rosters_for_current_week')
def lock_rosters_for_current_week():
    """
    Lock rosters for the current week (at first game time).
    Called automatically when rosters lock time arrives via Celery Beat schedule.
    Rosters remain locked until Monday 9am PT.
    """
    from web.models import Week
    
    now = timezone.now()
    
    try:
        # Find weeks where lock_time has just passed (within last hour)
        weeks = Week.objects.filter(
            roster_lock_time__lte=now,
            roster_lock_time__gte=now - timedelta(hours=1)
        )
        
        for week in weeks:
            logger.info(f"Locking rosters for Week {week.week_number}, Season {week.season}")
            # The is_locked() method now handles the logic based on roster_lock_time
        
        return f"Successfully locked rosters for {weeks.count()} weeks"
    
    except Exception as e:
        logger.error(f"Error locking rosters: {str(e)}")
        raise


@shared_task(name='unlock_rosters_and_process_transactions')
def unlock_rosters_and_process_transactions():
    """
    Unlock rosters (Monday 9am PT) and execute pending waivers/trades.
    Called automatically at Monday 9am PT via Celery Beat schedule.
    """
    from web.models import Week, WaiverClaim, Trade, League
    
    now = timezone.now()
    
    try:
        # Find weeks where unlock_time has just passed
        weeks = Week.objects.filter(
            roster_unlock_time__lte=now,
            roster_unlock_time__gte=now - timedelta(hours=1)
        )
        
        for week in weeks:
            logger.info(f"Unlocking rosters for Week {week.week_number}, Season {week.season}")
            
            # Process pending waivers for this week
            process_waivers_for_week(week)
            
            # Process pending trades for this week
            process_trades_for_week(week)
            
            # Update league current_week to next week
            update_current_week_for_season(week.season)
        
        return f"Successfully unlocked rosters and processed transactions for {weeks.count()} weeks"
    
    except Exception as e:
        logger.error(f"Error unlocking rosters and processing transactions: {str(e)}")
        raise


def process_waivers_for_week(week):
    """
    Execute all pending waiver claims for a given week.
    Process in priority order (highest priority first).
    """
    from web.models import WaiverClaim, Roster
    
    try:
        pending_waivers = WaiverClaim.objects.filter(
            week=week,
            status='pending'
        ).order_by('priority')
        
        for waiver in pending_waivers:
            try:
                # Execute the waiver claim
                waiver.status = 'executed'
                waiver.executed_at = timezone.now()
                waiver.save()
                
                # Update the roster
                Roster.objects.filter(
                    team=waiver.team,
                    week=week
                ).update(player=waiver.player)
                
                logger.info(f"Executed waiver: {waiver.team} claims {waiver.player}")
                
            except Exception as e:
                logger.error(f"Error executing waiver {waiver.id}: {str(e)}")
                waiver.status = 'failed'
                waiver.save()
    
    except Exception as e:
        logger.error(f"Error processing waivers for week {week.week_number}: {str(e)}")


def process_trades_for_week(week):
    """
    Execute all pending trades for a given week.
    """
    from web.models import Trade
    
    try:
        pending_trades = Trade.objects.filter(
            week=week,
            status='pending'
        )
        
        for trade in pending_trades:
            try:
                # Execute the trade
                trade.execute()
                logger.info(f"Executed trade between {trade.team_a} and {trade.team_b}")
                
            except Exception as e:
                logger.error(f"Error executing trade {trade.id}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error processing trades for week {week.week_number}: {str(e)}")


def update_current_week_for_season(season):
    """
    Update all leagues' current_week to the next unlocked week.
    Called when Monday 9am PT rosters unlock.
    """
    from web.models import League
    from datetime import timedelta
    
    try:
        leagues = League.objects.filter(created_at__year=season)
        
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
        
        # Call the fetch_nll_stats management command
        call_command('fetch_nll_stats', current_year)
        
        logger.info(f"Successfully fetched NLL stats for season {current_year}")
        
    except Exception as e:
        logger.error(f"Error fetching NLL stats: {str(e)}")
        raise

