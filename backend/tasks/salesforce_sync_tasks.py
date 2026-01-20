"""
Salesforce Integration Background Sync Tasks

Data flows BIDIRECTIONALLY: Salesforce ↔ CRM
- Inbound: Salesforce → CRM (pull emails, calendar, loans, leads)
- Outbound: CRM → Salesforce (push updated loans, leads, activities)

Tasks:
- sync_emails_from_salesforce: Pull email history from Salesforce
- sync_calendar_from_salesforce: Pull calendar events from Salesforce
- sync_all_users_salesforce: Run bidirectional sync for all connected users
- push_all_users_to_salesforce: Push CRM data to Salesforce for all users
- check_salesforce_sync_health: Health monitoring

Scheduler Integration:
- register_salesforce_sync_jobs: Register jobs with APScheduler (5-minute intervals)
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
    limit: int = 200,
    db: Session = None
) -> Dict[str, Any]:
    """
    Sync email history from Salesforce to CRM for a single user.

    Data flows ONE-WAY: Salesforce → CRM

    Args:
        integration_profile_id: Integration profile ID
        days_back: Number of days to sync back
        limit: Maximum emails to sync
        db: Optional database session (reuse parent session to avoid connection exhaustion)

    Returns:
        Sync result dictionary
    """
    # Reuse provided session or create new one (to avoid connection pool exhaustion)
    own_session = db is None
    if own_session:
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
        # Only close if we created the session
        if own_session:
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
    limit: int = 200,
    db: Session = None
) -> Dict[str, Any]:
    """
    Sync calendar events from Salesforce to CRM for a single user.

    Data flows ONE-WAY: Salesforce → CRM

    Args:
        integration_profile_id: Integration profile ID
        days_back: Number of days to sync back
        days_forward: Number of days to sync forward
        limit: Maximum events to sync
        db: Optional database session (reuse parent session to avoid connection exhaustion)

    Returns:
        Sync result dictionary
    """
    # Reuse provided session or create new one (to avoid connection pool exhaustion)
    own_session = db is None
    if own_session:
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
        # Only close if we created the session
        if own_session:
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
    push_to_salesforce: bool = True,
    email_days_back: int = 7,
    calendar_days_back: int = 7,
    calendar_days_forward: int = 30,
    push_since_hours: int = 1
) -> Dict[str, Any]:
    """
    Run BIDIRECTIONAL Salesforce sync for all connected users.

    Data flows BOTH WAYS:
    - Inbound: Salesforce → CRM (pull emails, calendar, loans, leads)
    - Outbound: CRM → Salesforce (push updated loans, leads, activities)

    Args:
        sync_emails: Whether to pull emails from Salesforce
        sync_calendar: Whether to pull calendar from Salesforce
        push_to_salesforce: Whether to push CRM data to Salesforce
        email_days_back: Days back to sync for emails
        calendar_days_back: Days back to sync for calendar
        calendar_days_forward: Days forward to sync for calendar
        push_since_hours: Only push records modified in last N hours

    Returns:
        Summary of all sync operations
    """
    db = SessionLocal()

    try:
        from salesforce_integration_models import IntegrationProfile

        results = {
            'users_processed': 0,
            'sync_direction': 'bidirectional',
            'inbound': {
                'emails_synced': 0,
                'emails_skipped': 0,
                'events_synced': 0,
                'tasks_synced': 0,
            },
            'outbound': {
                'loans_pushed': 0,
                'leads_pushed': 0,
                'emails_pushed': 0,
                'calendar_pushed': 0,
                'total_pushed': 0,
            },
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

        logger.info(f"Starting BIDIRECTIONAL Salesforce sync for {len(profiles)} users")

        for profile in profiles:
            try:
                results['users_processed'] += 1

                # ===== INBOUND: Pull from Salesforce → CRM =====
                # Pass db session to avoid creating nested connections (connection pool exhaustion fix)
                if sync_emails:
                    email_result = await sync_emails_from_salesforce(
                        integration_profile_id=profile.id,
                        days_back=email_days_back,
                        limit=200,
                        db=db  # Reuse parent session
                    )
                    results['inbound']['emails_synced'] += email_result.get('emails_synced', 0)
                    results['inbound']['emails_skipped'] += email_result.get('emails_skipped', 0)
                    if email_result.get('errors'):
                        results['errors'].extend(email_result['errors'][:3])

                if sync_calendar:
                    calendar_result = await sync_calendar_from_salesforce(
                        integration_profile_id=profile.id,
                        days_back=calendar_days_back,
                        days_forward=calendar_days_forward,
                        limit=200,
                        db=db  # Reuse parent session
                    )
                    results['inbound']['events_synced'] += calendar_result.get('events_synced', 0)
                    results['inbound']['tasks_synced'] += calendar_result.get('tasks_synced', 0)
                    if calendar_result.get('errors'):
                        results['errors'].extend(calendar_result['errors'][:3])

                # ===== OUTBOUND: Push CRM → Salesforce =====
                if push_to_salesforce:
                    try:
                        from services.salesforce.sync_service import salesforce_sync

                        push_result = await salesforce_sync.sync_outbound(
                            db=db,
                            integration_profile_id=profile.id,
                            sync_loans=True,
                            sync_leads=True,
                            sync_emails=True,
                            sync_calendar=True,
                            since_hours=push_since_hours
                        )

                        results['outbound']['loans_pushed'] += push_result['loans']['pushed']
                        results['outbound']['leads_pushed'] += push_result['leads']['pushed']
                        results['outbound']['emails_pushed'] += push_result['emails']['pushed']
                        results['outbound']['calendar_pushed'] += push_result['calendar']['pushed']
                        results['outbound']['total_pushed'] += (
                            push_result['loans']['pushed'] +
                            push_result['leads']['pushed'] +
                            push_result['emails']['pushed'] +
                            push_result['calendar']['pushed']
                        )

                        # Collect outbound errors
                        for category in ['loans', 'leads', 'emails', 'calendar']:
                            if push_result[category].get('errors'):
                                results['errors'].extend(push_result[category]['errors'][:2])

                    except Exception as e:
                        logger.error(f"Outbound sync failed for user {profile.user_id}: {e}")
                        results['errors'].append(f"Outbound sync user {profile.user_id}: {str(e)}")

                # Update last sync time
                profile.last_sync_at = datetime.utcnow()
                db.commit()

            except Exception as e:
                logger.error(f"Sync failed for user {profile.user_id}: {e}")
                results['errors'].append(f"User {profile.user_id}: {str(e)}")

        results['completed_at'] = datetime.utcnow().isoformat()

        logger.info(
            f"Salesforce BIDIRECTIONAL sync complete: {results['users_processed']} users | "
            f"inbound: emails={results['inbound']['emails_synced']}, events={results['inbound']['events_synced']} | "
            f"outbound: total={results['outbound']['total_pushed']}"
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
        Health status with metrics for bidirectional sync
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

        # Recent INBOUND sync activity (last 24 hours)
        recent_inbound_syncs = db.execute(text("""
            SELECT COUNT(*) FROM integration_events
            WHERE event_type IN ('email_sync_completed', 'calendar_sync_completed', 'sync_completed')
              AND (direction IS NULL OR direction = 'inbound')
              AND created_at >= NOW() - INTERVAL '24 hours'
        """)).scalar()

        recent_inbound_failures = db.execute(text("""
            SELECT COUNT(*) FROM integration_events
            WHERE event_type IN ('email_sync_failed', 'calendar_sync_failed', 'sync_failed')
              AND (direction IS NULL OR direction = 'inbound')
              AND created_at >= NOW() - INTERVAL '24 hours'
        """)).scalar()

        # Recent OUTBOUND sync activity (last 24 hours)
        recent_outbound_syncs = db.execute(text("""
            SELECT COUNT(*) FROM integration_events
            WHERE event_type IN ('sync_completed', 'record_synced')
              AND direction = 'outbound'
              AND created_at >= NOW() - INTERVAL '24 hours'
        """)).scalar()

        recent_outbound_failures = db.execute(text("""
            SELECT COUNT(*) FROM integration_events
            WHERE event_type IN ('sync_failed')
              AND direction = 'outbound'
              AND created_at >= NOW() - INTERVAL '24 hours'
        """)).scalar()

        # Stale connections (no sync in 15 minutes - since we sync every 5 minutes now)
        stale_connections = db.execute(text("""
            SELECT COUNT(*) FROM integration_profiles
            WHERE provider = 'salesforce'
              AND status IN ('connected', 'active')
              AND sync_enabled = TRUE
              AND (last_sync_at IS NULL OR last_sync_at < NOW() - INTERVAL '15 minutes')
        """)).scalar()

        # Calculate health
        total_inbound = (recent_inbound_syncs or 0) + (recent_inbound_failures or 0)
        total_outbound = (recent_outbound_syncs or 0) + (recent_outbound_failures or 0)

        inbound_failure_rate = (recent_inbound_failures or 0) / total_inbound if total_inbound > 0 else 0
        outbound_failure_rate = (recent_outbound_failures or 0) / total_outbound if total_outbound > 0 else 0
        overall_failure_rate = max(inbound_failure_rate, outbound_failure_rate)

        healthy = (
            overall_failure_rate < 0.1 and  # Less than 10% failure rate
            (stale_connections or 0) == 0 and  # No stale connections
            (error_profiles or 0) < (connected or 1) * 0.1  # Less than 10% in error state
        )

        return {
            'healthy': healthy,
            'sync_direction': 'bidirectional',
            'sync_interval_minutes': 15,
            'metrics': {
                'connected_profiles': connected or 0,
                'error_profiles': error_profiles or 0,
                'inbound': {
                    'recent_syncs_24h': recent_inbound_syncs or 0,
                    'recent_failures_24h': recent_inbound_failures or 0,
                    'failure_rate': round(inbound_failure_rate * 100, 2)
                },
                'outbound': {
                    'recent_syncs_24h': recent_outbound_syncs or 0,
                    'recent_failures_24h': recent_outbound_failures or 0,
                    'failure_rate': round(outbound_failure_rate * 100, 2)
                },
                'stale_connections': stale_connections or 0,
                'overall_failure_rate': round(overall_failure_rate * 100, 2)
            },
            'alerts': [
                alert for alert in [
                    f"High inbound failure rate: {inbound_failure_rate*100:.1f}%" if inbound_failure_rate >= 0.1 else None,
                    f"High outbound failure rate: {outbound_failure_rate*100:.1f}%" if outbound_failure_rate >= 0.1 else None,
                    f"{stale_connections} stale connections (no sync in 15+ minutes)" if stale_connections else None,
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

    Sync is BIDIRECTIONAL every 15 minutes (reduced from 5 to prevent connection exhaustion):
    - Inbound: Salesforce → CRM (pull emails, calendar, loans, leads)
    - Outbound: CRM → Salesforce (push updated loans, leads, activities)

    Args:
        scheduler: APScheduler instance
    """
    # BIDIRECTIONAL sync every 15 minutes (reduced from 5 to prevent connection exhaustion)
    scheduler.add_job(
        sync_all_users_salesforce_sync,
        'interval',
        minutes=15,
        id='salesforce_sync_all_users',
        name='Bidirectional Salesforce sync: pull from SF and push CRM changes every 15 minutes',
        replace_existing=True,
        kwargs={
            'sync_emails': True,
            'sync_calendar': True,
            'push_to_salesforce': True,  # Enable outbound sync
            'email_days_back': 1,
            'calendar_days_back': 1,
            'calendar_days_forward': 14,
            'push_since_hours': 1  # Push records modified in last hour
        }
    )

    # Health check every 15 minutes (aligned with sync interval)
    scheduler.add_job(
        check_salesforce_sync_health_sync,
        'interval',
        minutes=15,
        id='salesforce_sync_health',
        name='Salesforce sync health check',
        replace_existing=True
    )

    logger.info("Salesforce sync jobs registered (BIDIRECTIONAL): sync every 15 minutes, health check every 15 minutes")


# ============================================================================
# Manual Trigger Functions (for API endpoints)
# ============================================================================

async def trigger_user_sync(
    user_id: int,
    sync_emails: bool = True,
    sync_calendar: bool = True,
    push_emails: bool = True,
    push_to_salesforce: bool = True
) -> Dict[str, Any]:
    """
    Manually trigger BIDIRECTIONAL sync for a specific user.

    Data flows BOTH WAYS:
    - Inbound: Salesforce → CRM (pull emails, calendar)
    - Outbound: CRM → Salesforce (push updated data)

    Args:
        user_id: CRM user ID
        sync_emails: Pull emails from Salesforce
        sync_calendar: Pull calendar from Salesforce
        push_emails: Push CRM emails to Salesforce
        push_to_salesforce: Push all CRM changes to Salesforce

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
            'sync_direction': 'bidirectional',
            'inbound': {
                'email_sync': None,
                'calendar_sync': None,
            },
            'outbound': {
                'push_result': None,
            }
        }

        # ===== INBOUND: Pull from Salesforce =====
        # Pass db session to avoid creating nested connections (connection pool exhaustion fix)
        if sync_emails:
            results['inbound']['email_sync'] = await sync_emails_from_salesforce(
                profile.id, days_back=30, limit=500, db=db
            )

        if sync_calendar:
            results['inbound']['calendar_sync'] = await sync_calendar_from_salesforce(
                profile.id, days_back=30, days_forward=90, limit=500, db=db
            )

        # ===== OUTBOUND: Push to Salesforce =====
        if push_to_salesforce or push_emails:
            try:
                from services.salesforce.sync_service import salesforce_sync

                push_result = await salesforce_sync.sync_outbound(
                    db=db,
                    integration_profile_id=profile.id,
                    sync_loans=push_to_salesforce,
                    sync_leads=push_to_salesforce,
                    sync_emails=push_emails,
                    sync_calendar=push_to_salesforce,
                    since_hours=24
                )
                results['outbound']['push_result'] = push_result

            except Exception as e:
                logger.error(f"Outbound sync failed for user {user_id}: {e}")
                results['outbound']['error'] = str(e)
                results['success'] = False

        # Update last sync time
        profile.last_sync_at = datetime.utcnow()
        db.commit()

        return results

    finally:
        db.close()


def trigger_user_sync_sync(user_id: int, **kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for trigger_user_sync"""
    return asyncio.run(trigger_user_sync(user_id, **kwargs))


# ============================================================================
# Outbound Push Functions (CRM → Salesforce)
# ============================================================================

async def push_emails_to_salesforce(
    user_id: int,
    since_hours: int = 24
) -> Dict[str, Any]:
    """
    Push CRM email activities to Salesforce for a specific user.

    Creates Task records in Salesforce for outbound emails sent from the CRM.

    Args:
        user_id: CRM user ID
        since_hours: Hours back to look for unsent emails

    Returns:
        Result with counts of pushed/failed emails
    """
    db = SessionLocal()

    try:
        from salesforce_integration_models import IntegrationProfile
        from services.salesforce.sync_service import salesforce_sync
        from sqlalchemy import text

        # Get profile
        profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.user_id == user_id,
            IntegrationProfile.provider == 'salesforce'
        ).first()

        if not profile or profile.status not in ['connected', 'active']:
            return {
                'success': False,
                'error': 'Salesforce not connected',
                'emails_pushed': 0,
                'emails_failed': 0,
                'errors': ['Salesforce integration not connected']
            }

        results = {
            'success': True,
            'emails_pushed': 0,
            'emails_failed': 0,
            'errors': []
        }

        # Get emails to push (not yet pushed to Salesforce)
        since = datetime.utcnow() - timedelta(hours=since_hours)
        emails = db.execute(text("""
            SELECT id FROM email_messages
            WHERE user_id = :user_id
              AND created_at >= :since
              AND direction = 'outbound'
              AND (meta_data IS NULL OR meta_data->>'salesforce_task_id' IS NULL)
            ORDER BY created_at DESC
            LIMIT 100
        """), {"user_id": user_id, "since": since}).fetchall()

        logger.info(f"Found {len(emails)} emails to push to Salesforce for user {user_id}")

        for email in emails:
            try:
                result = await salesforce_sync.push_email_to_salesforce(
                    db=db,
                    integration_profile_id=profile.id,
                    email_id=email.id
                )
                if result['success']:
                    results['emails_pushed'] += 1
                else:
                    results['emails_failed'] += 1
                    results['errors'].append(result.get('error', 'Unknown error')[:100])
            except Exception as e:
                results['emails_failed'] += 1
                results['errors'].append(str(e)[:100])

        results['success'] = results['emails_failed'] == 0

        logger.info(
            f"Push emails to Salesforce complete for user {user_id}: "
            f"pushed={results['emails_pushed']}, failed={results['emails_failed']}"
        )

        return results

    except Exception as e:
        logger.error(f"Push emails failed for user {user_id}: {e}")
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


async def push_all_users_to_salesforce(
    sync_loans: bool = True,
    sync_leads: bool = True,
    sync_emails: bool = True,
    sync_calendar: bool = True,
    since_hours: int = 1
) -> Dict[str, Any]:
    """
    Push CRM data to Salesforce for ALL connected users.

    This is the scheduled outbound sync that runs every 5 minutes.

    Args:
        sync_loans: Push loan changes
        sync_leads: Push lead changes
        sync_emails: Push email activities
        sync_calendar: Push calendar events
        since_hours: Only push records modified in last N hours

    Returns:
        Summary of all push operations
    """
    db = SessionLocal()

    try:
        from salesforce_integration_models import IntegrationProfile
        from services.salesforce.sync_service import salesforce_sync

        results = {
            'users_processed': 0,
            'total_pushed': 0,
            'loans_pushed': 0,
            'leads_pushed': 0,
            'emails_pushed': 0,
            'calendar_pushed': 0,
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

        logger.info(f"Starting outbound Salesforce push for {len(profiles)} users")

        for profile in profiles:
            try:
                results['users_processed'] += 1

                push_result = await salesforce_sync.sync_outbound(
                    db=db,
                    integration_profile_id=profile.id,
                    sync_loans=sync_loans,
                    sync_leads=sync_leads,
                    sync_emails=sync_emails,
                    sync_calendar=sync_calendar,
                    since_hours=since_hours
                )

                results['loans_pushed'] += push_result['loans']['pushed']
                results['leads_pushed'] += push_result['leads']['pushed']
                results['emails_pushed'] += push_result['emails']['pushed']
                results['calendar_pushed'] += push_result['calendar']['pushed']
                results['total_pushed'] += (
                    push_result['loans']['pushed'] +
                    push_result['leads']['pushed'] +
                    push_result['emails']['pushed'] +
                    push_result['calendar']['pushed']
                )

            except Exception as e:
                logger.error(f"Outbound push failed for user {profile.user_id}: {e}")
                results['errors'].append(f"User {profile.user_id}: {str(e)}")

        results['completed_at'] = datetime.utcnow().isoformat()

        logger.info(
            f"Outbound Salesforce push complete: {results['users_processed']} users | "
            f"total={results['total_pushed']} (loans={results['loans_pushed']}, "
            f"leads={results['leads_pushed']}, emails={results['emails_pushed']}, "
            f"calendar={results['calendar_pushed']})"
        )

        return results

    finally:
        db.close()


def push_all_users_to_salesforce_sync(**kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for push_all_users_to_salesforce"""
    return asyncio.run(push_all_users_to_salesforce(**kwargs))
