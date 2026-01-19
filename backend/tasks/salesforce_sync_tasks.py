"""
Salesforce Integration Background Sync Tasks
Handles scheduled sync operations between CRM and Salesforce

Tasks:
- sync_emails_from_salesforce: Pull email history from Salesforce
- sync_calendar_from_salesforce: Pull calendar events from Salesforce
- sync_all_users: Run sync for all connected users
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
            f"Email sync for profile {integration_profile_id}: "
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
            f"Calendar sync for profile {integration_profile_id}: "
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
# Task: Sync All Connected Users
# ============================================================================

async def sync_all_users_salesforce(
    sync_emails: bool = True,
    sync_calendar: bool = True,
    push_to_salesforce: bool = True,
    email_days_back: int = 7,
    calendar_days_back: int = 7,
    calendar_days_forward: int = 30
) -> Dict[str, Any]:
    """
    Run bidirectional Salesforce sync for all connected users.

    Args:
        sync_emails: Whether to pull emails from Salesforce
        sync_calendar: Whether to pull calendar from Salesforce
        push_to_salesforce: Whether to push CRM changes to Salesforce
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
            'inbound': {
                'emails_synced': 0,
                'emails_skipped': 0,
                'events_synced': 0,
                'tasks_synced': 0,
                'errors': []
            },
            'outbound': {
                'loans_pushed': 0,
                'leads_pushed': 0,
                'emails_pushed': 0,
                'calendar_pushed': 0,
                'errors': []
            },
            'started_at': datetime.utcnow().isoformat(),
            'completed_at': None
        }

        # Get all connected Salesforce profiles
        profiles = db.query(IntegrationProfile).filter(
            IntegrationProfile.provider == 'salesforce',
            IntegrationProfile.status.in_(['connected', 'active']),
            IntegrationProfile.sync_enabled == True
        ).all()

        logger.info(f"Starting Salesforce sync for {len(profiles)} users")

        for profile in profiles:
            try:
                results['users_processed'] += 1

                # INBOUND: Pull emails from Salesforce
                if sync_emails:
                    email_result = await sync_emails_from_salesforce(
                        integration_profile_id=profile.id,
                        days_back=email_days_back,
                        limit=200
                    )
                    results['inbound']['emails_synced'] += email_result.get('emails_synced', 0)
                    results['inbound']['emails_skipped'] += email_result.get('emails_skipped', 0)
                    if email_result.get('errors'):
                        results['inbound']['errors'].extend(email_result['errors'][:3])

                # INBOUND: Pull calendar from Salesforce
                if sync_calendar:
                    calendar_result = await sync_calendar_from_salesforce(
                        integration_profile_id=profile.id,
                        days_back=calendar_days_back,
                        days_forward=calendar_days_forward,
                        limit=200
                    )
                    results['inbound']['events_synced'] += calendar_result.get('events_synced', 0)
                    results['inbound']['tasks_synced'] += calendar_result.get('tasks_synced', 0)
                    if calendar_result.get('errors'):
                        results['inbound']['errors'].extend(calendar_result['errors'][:3])

                # OUTBOUND: Push CRM data TO Salesforce
                if push_to_salesforce:
                    from services.salesforce.sync_service import salesforce_sync

                    outbound_result = await salesforce_sync.sync_outbound(
                        db=db,
                        integration_profile_id=profile.id,
                        sync_loans=True,
                        sync_leads=True,
                        sync_emails=True,
                        sync_calendar=True,
                        since_hours=24
                    )
                    results['outbound']['loans_pushed'] += outbound_result['loans']['pushed']
                    results['outbound']['leads_pushed'] += outbound_result['leads']['pushed']
                    results['outbound']['emails_pushed'] += outbound_result['emails']['pushed']
                    results['outbound']['calendar_pushed'] += outbound_result['calendar']['pushed']

                    # Collect errors
                    for key in ['loans', 'leads', 'emails', 'calendar']:
                        if outbound_result[key].get('errors'):
                            results['outbound']['errors'].extend(outbound_result[key]['errors'][:2])

                # Update last sync time
                profile.last_sync_at = datetime.utcnow()
                db.commit()

            except Exception as e:
                logger.error(f"Sync failed for user {profile.user_id}: {e}")

        results['completed_at'] = datetime.utcnow().isoformat()

        logger.info(
            f"Salesforce bidirectional sync complete: {results['users_processed']} users | "
            f"INBOUND: emails={results['inbound']['emails_synced']}, events={results['inbound']['events_synced']} | "
            f"OUTBOUND: loans={results['outbound']['loans_pushed']}, leads={results['outbound']['leads_pushed']}, "
            f"emails={results['outbound']['emails_pushed']}, calendar={results['outbound']['calendar_pushed']}"
        )

        return results

    finally:
        db.close()


def sync_all_users_salesforce_sync(**kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for sync_all_users_salesforce"""
    return asyncio.run(sync_all_users_salesforce(**kwargs))


# ============================================================================
# Task: Push Emails to Salesforce (Bidirectional)
# ============================================================================

async def push_emails_to_salesforce(
    user_id: int,
    since_hours: int = 24
) -> Dict[str, Any]:
    """
    Push CRM email activities to Salesforce.
    Creates Task records in Salesforce for outbound emails.

    Args:
        user_id: CRM user ID
        since_hours: Hours back to look for unsent emails

    Returns:
        Push result dictionary
    """
    db = SessionLocal()

    try:
        from salesforce_integration_models import IntegrationProfile
        from services.salesforce.oauth_service import salesforce_oauth
        import httpx

        results = {
            'success': True,
            'emails_pushed': 0,
            'emails_failed': 0,
            'errors': []
        }

        # Get user's Salesforce profile
        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.user_id == user_id,
            IntegrationProfile.provider == 'salesforce',
            IntegrationProfile.status.in_(['connected', 'active'])
        ).first()

        if not profile:
            return {
                'success': False,
                'emails_pushed': 0,
                'emails_failed': 0,
                'errors': ['User not connected to Salesforce']
            }

        # Get access token
        access_token, instance_url = await salesforce_oauth.get_access_token(db, profile.id)

        # Get unsent emails from CRM
        since = datetime.utcnow() - timedelta(hours=since_hours)
        emails = db.execute(text("""
            SELECT em.id, em.to_email, em.from_email, em.subject, em.body,
                   em.direction, em.created_at, em.lead_id, em.loan_id,
                   l.salesforce_id as lead_sf_id,
                   lo.salesforce_id as loan_sf_id
            FROM email_messages em
            LEFT JOIN leads l ON l.id = em.lead_id
            LEFT JOIN loans lo ON lo.id = em.loan_id
            WHERE em.user_id = :user_id
              AND em.created_at >= :since
              AND em.direction = 'outbound'
              AND (em.meta_data IS NULL OR em.meta_data->>'salesforce_task_id' IS NULL)
            ORDER BY em.created_at DESC
            LIMIT 100
        """), {"user_id": user_id, "since": since}).fetchall()

        async with httpx.AsyncClient() as client:
            for email in emails:
                try:
                    # Determine WhoId and WhatId
                    who_id = email.lead_sf_id if email.lead_sf_id else None
                    what_id = email.loan_sf_id if email.loan_sf_id else None

                    # Create Task in Salesforce
                    task_data = {
                        "Subject": email.subject or "Email Activity",
                        "Description": email.body[:32000] if email.body else "",
                        "TaskSubtype": "Email",
                        "Status": "Completed",
                        "ActivityDate": email.created_at.strftime("%Y-%m-%d")
                    }

                    if who_id:
                        task_data["WhoId"] = who_id
                    if what_id:
                        task_data["WhatId"] = what_id

                    response = await client.post(
                        f"{instance_url}/services/data/v59.0/sobjects/Task",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json"
                        },
                        json=task_data,
                        timeout=30.0
                    )

                    if response.status_code == 201:
                        sf_task_id = response.json().get('id')

                        # Update email with Salesforce task ID
                        db.execute(text("""
                            UPDATE email_messages
                            SET meta_data = COALESCE(meta_data, '{}'::jsonb) ||
                                jsonb_build_object('salesforce_task_id', :sf_id, 'pushed_at', :pushed_at)
                            WHERE id = :email_id
                        """), {
                            "sf_id": sf_task_id,
                            "pushed_at": datetime.utcnow().isoformat(),
                            "email_id": email.id
                        })
                        db.commit()

                        results['emails_pushed'] += 1
                    else:
                        results['emails_failed'] += 1
                        results['errors'].append(f"Email {email.id}: {response.text[:100]}")

                except Exception as e:
                    results['emails_failed'] += 1
                    results['errors'].append(f"Email {email.id}: {str(e)[:100]}")

        logger.info(
            f"Pushed {results['emails_pushed']} emails to Salesforce for user {user_id}"
        )

        return results

    except Exception as e:
        logger.error(f"Email push failed for user {user_id}: {e}")
        return {
            'success': False,
            'emails_pushed': 0,
            'emails_failed': 0,
            'errors': [str(e)]
        }
    finally:
        db.close()


def push_emails_to_salesforce_sync(user_id: int, **kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for push_emails_to_salesforce"""
    return asyncio.run(push_emails_to_salesforce(user_id, **kwargs))


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

    Args:
        scheduler: APScheduler instance
    """
    # Sync all users every 15 minutes
    scheduler.add_job(
        sync_all_users_salesforce_sync,
        'interval',
        minutes=15,
        id='salesforce_sync_all_users',
        name='Sync emails and calendar from Salesforce for all users',
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

    logger.info("Salesforce sync jobs registered: sync every 15 minutes, health check every 10 minutes")


# ============================================================================
# Manual Trigger Functions (for API endpoints)
# ============================================================================

async def trigger_user_sync(
    user_id: int,
    sync_emails: bool = True,
    sync_calendar: bool = True,
    push_emails: bool = True
) -> Dict[str, Any]:
    """
    Manually trigger full sync for a specific user.

    Args:
        user_id: CRM user ID
        sync_emails: Pull emails from Salesforce
        sync_calendar: Pull calendar from Salesforce
        push_emails: Push emails to Salesforce

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
            'email_pull': None,
            'calendar_pull': None,
            'email_push': None
        }

        if sync_emails:
            results['email_pull'] = await sync_emails_from_salesforce(
                profile.id, days_back=30, limit=500
            )

        if sync_calendar:
            results['calendar_pull'] = await sync_calendar_from_salesforce(
                profile.id, days_back=30, days_forward=90, limit=500
            )

        if push_emails:
            results['email_push'] = await push_emails_to_salesforce(
                user_id, since_hours=168  # 7 days
            )

        return results

    finally:
        db.close()


def trigger_user_sync_sync(user_id: int, **kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for trigger_user_sync"""
    return asyncio.run(trigger_user_sync(user_id, **kwargs))
