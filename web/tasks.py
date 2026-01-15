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
