"""
Salesforce Integration Background Sync Tasks

Data flows ONE-WAY: Salesforce → CRM
When data is updated in Salesforce, those changes are pulled into the CRM.
The CRM does NOT push data back to Salesforce.

Tasks:
- sync_emails_from_salesforce: Pull email history from Salesforce
- sync_calendar_from_salesforce: Pull calendar events from Salesforce
- sync_all_users_salesforce: Run inbound sync for all connected users
- check_salesforce_sync_health: Health monitoring

Scheduler Integration:
- register_salesforce_sync_jobs: Register jobs with APScheduler
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import text
from database import SessionLocal

logger = logging.getLogger(__name__)


# ============================================================================
# Task: Sync Emails from Salesforce for a Single User
# ============================================================================

async def sync_emails_from_salesforce(
    integration_profile_id: int,
    days_back: int = 7,
    limit: int = 200
) -> Dict[str, Any]:
    """
    Sync email history from Salesforce to CRM for a single user.

    Data flows ONE-WAY: Salesforce → CRM

    Args:
        integration_profile_id: Integration profile ID
        days_back: Number of days to sync back
        limit: Maximum emails to sync

    Returns:
        Sync result dictionary
    """
    db = SessionLocal()

    try:
        from services.salesforce.email_sync_service import salesforce_email_sync

        result = await salesforce_email_sync.sync_emails(
            db=db,
            integration_profile_id=integration_profile_id,
            days_back=days_back,
            limit=limit
        )

        logger.info(
            f"Email sync from Salesforce for profile {integration_profile_id}: "
            f"synced={result['emails_synced']}, skipped={result['emails_skipped']}"
        )

        return result

    except Exception as e:
        logger.error(f"Email sync failed for profile {integration_profile_id}: {e}")
        return {
            'success': False,
            'emails_synced': 0,
            'emails_skipped': 0,
            'errors': [str(e)]
        }
    finally:
        db.close()


def sync_emails_from_salesforce_sync(integration_profile_id: int, **kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for sync_emails_from_salesforce"""
    return asyncio.run(sync_emails_from_salesforce(integration_profile_id, **kwargs))


# ============================================================================
# Task: Sync Calendar from Salesforce for a Single User
# ============================================================================

async def sync_calendar_from_salesforce(
    integration_profile_id: int,
    days_back: int = 7,
    days_forward: int = 30,
    limit: int = 200
) -> Dict[str, Any]:
    """
    Sync calendar events from Salesforce to CRM for a single user.

    Data flows ONE-WAY: Salesforce → CRM

    Args:
        integration_profile_id: Integration profile ID
        days_back: Number of days to sync back
        days_forward: Number of days to sync forward
        limit: Maximum events to sync

    Returns:
        Sync result dictionary
    """
    db = SessionLocal()

    try:
        from services.salesforce.calendar_sync_service import salesforce_calendar_sync

        result = await salesforce_calendar_sync.sync_calendar(
            db=db,
            integration_profile_id=integration_profile_id,
            days_back=days_back,
            days_forward=days_forward,
            limit=limit
        )

        logger.info(
            f"Calendar sync from Salesforce for profile {integration_profile_id}: "
            f"events={result['events_synced']}, tasks={result['tasks_synced']}"
        )

        return result

    except Exception as e:
        logger.error(f"Calendar sync failed for profile {integration_profile_id}: {e}")
        return {
            'success': False,
            'events_synced': 0,
            'events_skipped': 0,
            'tasks_synced': 0,
            'tasks_skipped': 0,
            'errors': [str(e)]
        }
    finally:
        db.close()


def sync_calendar_from_salesforce_sync(integration_profile_id: int, **kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for sync_calendar_from_salesforce"""
    return asyncio.run(sync_calendar_from_salesforce(integration_profile_id, **kwargs))


# ============================================================================
# Task: Sync All Connected Users (Inbound Only)
# ============================================================================

async def sync_all_users_salesforce(
    sync_emails: bool = True,
    sync_calendar: bool = True,
    email_days_back: int = 7,
    calendar_days_back: int = 7,
    calendar_days_forward: int = 30
) -> Dict[str, Any]:
    """
    Run Salesforce sync for all connected users.

    Data flows ONE-WAY: Salesforce → CRM
    Pulls emails and calendar events from Salesforce into the CRM.

    Args:
        sync_emails: Whether to pull emails from Salesforce
        sync_calendar: Whether to pull calendar from Salesforce
        email_days_back: Days back to sync for emails
        calendar_days_back: Days back to sync for calendar
        calendar_days_forward: Days forward to sync for calendar

    Returns:
        Summary of all sync operations
    """
    db = SessionLocal()

    try:
        from salesforce_integration_models import IntegrationProfile

        results = {
            'users_processed': 0,
            'sync_direction': 'inbound_only',
            'emails_synced': 0,
            'emails_skipped': 0,
            'events_synced': 0,
            'tasks_synced': 0,
            'errors': [],
            'started_at': datetime.utcnow().isoformat(),
            'completed_at': None
        }

        # Get all connected Salesforce profiles
        profiles = db.query(IntegrationProfile).filter(
            IntegrationProfile.provider == 'salesforce',
            IntegrationProfile.status.in_(['connected', 'active']),
            IntegrationProfile.sync_enabled == True
        ).all()

        logger.info(f"Starting Salesforce inbound sync for {len(profiles)} users")

        for profile in profiles:
            try:
                results['users_processed'] += 1

                # Pull emails from Salesforce → CRM
                if sync_emails:
                    email_result = await sync_emails_from_salesforce(
                        integration_profile_id=profile.id,
                        days_back=email_days_back,
                        limit=200
                    )
                    results['emails_synced'] += email_result.get('emails_synced', 0)
                    results['emails_skipped'] += email_result.get('emails_skipped', 0)
                    if email_result.get('errors'):
                        results['errors'].extend(email_result['errors'][:3])

                # Pull calendar from Salesforce → CRM
                if sync_calendar:
                    calendar_result = await sync_calendar_from_salesforce(
                        integration_profile_id=profile.id,
                        days_back=calendar_days_back,
                        days_forward=calendar_days_forward,
                        limit=200
                    )
                    results['events_synced'] += calendar_result.get('events_synced', 0)
                    results['tasks_synced'] += calendar_result.get('tasks_synced', 0)
                    if calendar_result.get('errors'):
                        results['errors'].extend(calendar_result['errors'][:3])

                # Update last sync time
                profile.last_sync_at = datetime.utcnow()
                db.commit()

            except Exception as e:
                logger.error(f"Sync failed for user {profile.user_id}: {e}")
                results['errors'].append(f"User {profile.user_id}: {str(e)}")

        results['completed_at'] = datetime.utcnow().isoformat()

        logger.info(
            f"Salesforce inbound sync complete: {results['users_processed']} users | "
            f"emails={results['emails_synced']}, events={results['events_synced']}, "
            f"tasks={results['tasks_synced']}"
        )

        return results

    finally:
        db.close()


def sync_all_users_salesforce_sync(**kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for sync_all_users_salesforce"""
    return asyncio.run(sync_all_users_salesforce(**kwargs))


# ============================================================================
# Task: Salesforce Sync Health Check
# ============================================================================

async def check_salesforce_sync_health() -> Dict[str, Any]:
    """
    Check overall Salesforce sync health across all users.

    Returns:
        Health status with metrics
    """
    db = SessionLocal()

    try:
        from salesforce_integration_models import IntegrationProfile, IntegrationEvent

        # Count profiles by status
        connected = db.execute(text("""
            SELECT COUNT(*) FROM integration_profiles
            WHERE provider = 'salesforce' AND status IN ('connected', 'active')
        """)).scalar()

        error_profiles = db.execute(text("""
            SELECT COUNT(*) FROM integration_profiles
            WHERE provider = 'salesforce' AND status = 'error'
        """)).scalar()

        # Recent sync activity (last 24 hours)
        recent_syncs = db.execute(text("""
            SELECT COUNT(*) FROM integration_events
            WHERE event_type IN ('email_sync_completed', 'calendar_sync_completed')
              AND created_at >= NOW() - INTERVAL '24 hours'
        """)).scalar()

        recent_failures = db.execute(text("""
            SELECT COUNT(*) FROM integration_events
            WHERE event_type IN ('email_sync_failed', 'calendar_sync_failed')
              AND created_at >= NOW() - INTERVAL '24 hours'
        """)).scalar()

        # Stale connections (no sync in 48 hours)
        stale_connections = db.execute(text("""
            SELECT COUNT(*) FROM integration_profiles
            WHERE provider = 'salesforce'
              AND status IN ('connected', 'active')
              AND sync_enabled = TRUE
              AND (last_sync_at IS NULL OR last_sync_at < NOW() - INTERVAL '48 hours')
        """)).scalar()

        # Calculate health
        total_syncs = (recent_syncs or 0) + (recent_failures or 0)
        failure_rate = (recent_failures or 0) / total_syncs if total_syncs > 0 else 0

        healthy = (
            failure_rate < 0.1 and  # Less than 10% failure rate
            (stale_connections or 0) == 0 and  # No stale connections
            (error_profiles or 0) < (connected or 1) * 0.1  # Less than 10% in error state
        )

        return {
            'healthy': healthy,
            'sync_direction': 'inbound_only',
            'metrics': {
                'connected_profiles': connected or 0,
                'error_profiles': error_profiles or 0,
                'recent_syncs_24h': recent_syncs or 0,
                'recent_failures_24h': recent_failures or 0,
                'stale_connections': stale_connections or 0,
                'failure_rate': round(failure_rate * 100, 2)
            },
            'alerts': [
                alert for alert in [
                    f"High failure rate: {failure_rate*100:.1f}%" if failure_rate >= 0.1 else None,
                    f"{stale_connections} stale connections" if stale_connections else None,
                    f"{error_profiles} profiles in error state" if error_profiles else None,
                ] if alert
            ],
            'checked_at': datetime.utcnow().isoformat()
        }

    finally:
        db.close()


def check_salesforce_sync_health_sync() -> Dict[str, Any]:
    """Synchronous wrapper for check_salesforce_sync_health"""
    return asyncio.run(check_salesforce_sync_health())


# ============================================================================
# Scheduler Integration
# ============================================================================

def register_salesforce_sync_jobs(scheduler):
    """
    Register Salesforce sync jobs with APScheduler.

    Note: Sync is ONE-WAY only (Salesforce → CRM).
    No data is pushed from CRM to Salesforce.

    Args:
        scheduler: APScheduler instance
    """
    # Sync all users every 15 minutes (inbound only)
    scheduler.add_job(
        sync_all_users_salesforce_sync,
        'interval',
        minutes=15,
        id='salesforce_sync_all_users',
        name='Sync emails and calendar from Salesforce for all users (inbound only)',
        replace_existing=True,
        kwargs={
            'sync_emails': True,
            'sync_calendar': True,
            'email_days_back': 1,  # Daily sync looks back 1 day
            'calendar_days_back': 1,
            'calendar_days_forward': 14
        }
    )

    # Health check every 10 minutes
    scheduler.add_job(
        check_salesforce_sync_health_sync,
        'interval',
        minutes=10,
        id='salesforce_sync_health',
        name='Salesforce sync health check',
        replace_existing=True
    )

    logger.info("Salesforce sync jobs registered (inbound only): sync every 15 minutes, health check every 10 minutes")


# ============================================================================
# Manual Trigger Functions (for API endpoints)
# ============================================================================

async def trigger_user_sync(
    user_id: int,
    sync_emails: bool = True,
    sync_calendar: bool = True
) -> Dict[str, Any]:
    """
    Manually trigger sync for a specific user.

    Data flows ONE-WAY: Salesforce → CRM
    Pulls latest data from Salesforce into the CRM.

    Args:
        user_id: CRM user ID
        sync_emails: Pull emails from Salesforce
        sync_calendar: Pull calendar from Salesforce

    Returns:
        Combined sync results
    """
    db = SessionLocal()

    try:
        from salesforce_integration_models import IntegrationProfile

        # Get profile
        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.user_id == user_id,
            IntegrationProfile.provider == 'salesforce'
        ).first()

        if not profile:
            return {
                'success': False,
                'error': 'Salesforce not connected'
            }

        results = {
            'success': True,
            'user_id': user_id,
            'sync_direction': 'inbound_only',
            'email_sync': None,
            'calendar_sync': None
        }

        if sync_emails:
            results['email_sync'] = await sync_emails_from_salesforce(
                profile.id, days_back=30, limit=500
            )

        if sync_calendar:
            results['calendar_sync'] = await sync_calendar_from_salesforce(
                profile.id, days_back=30, days_forward=90, limit=500
            )

        return results

    finally:
        db.close()


def trigger_user_sync_sync(user_id: int, **kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for trigger_user_sync"""
    return asyncio.run(trigger_user_sync(user_id, **kwargs))
