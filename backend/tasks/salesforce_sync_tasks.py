"""
Salesforce Integration Background Sync Tasks

Data flows ONE WAY: Salesforce → CRM (INBOUND ONLY)
- Pull emails, calendar events, tasks from Salesforce
- NO data is pushed from CRM to Salesforce

Tasks:
- sync_emails_from_salesforce: Pull email history from Salesforce
- sync_calendar_from_salesforce: Pull calendar events from Salesforce
- sync_all_users_salesforce: Run inbound sync for all connected users
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
        # Rollback to recover from any transaction errors
        try:
            db.rollback()
        except Exception as e2:
            logger.error(f"Error in sync_emails_from_salesforce (rollback): {e2}")
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
# Task: Push Emails to Salesforce
# ============================================================================

async def push_emails_to_salesforce(
    integration_profile_id: int,
    limit: int = 100,
    db: Session = None
) -> Dict[str, Any]:
    """Push emails from CRM to Salesforce (placeholder for bidirectional sync)."""
    logger.info(f"push_emails_to_salesforce called for profile {integration_profile_id}")
    # This is a placeholder for future bidirectional email sync
    return {
        "status": "not_implemented",
        "message": "Email push to Salesforce not yet implemented",
        "pushed": 0,
        "errors": []
    }


def push_emails_to_salesforce_sync(integration_profile_id: int, **kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for push_emails_to_salesforce"""
    return asyncio.run(push_emails_to_salesforce(integration_profile_id, **kwargs))


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
        # Rollback to recover from any transaction errors
        try:
            db.rollback()
        except Exception as e2:
            logger.error(f"Error in sync_calendar_from_salesforce (rollback): {e2}")
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
# Task: Sync All Connected Users (INBOUND ONLY - Salesforce → CRM)
# ============================================================================

async def sync_all_users_salesforce(
    sync_emails: bool = True,
    sync_calendar: bool = True,
    sync_client_fields: bool = True,  # Match by email and pull ALL fields
    import_new_clients: bool = True,  # Import NEW clients from Salesforce
    push_to_salesforce: bool = False,  # DISABLED - inbound only
    email_days_back: int = 7,
    calendar_days_back: int = 7,
    calendar_days_forward: int = 30,
    import_days_back: int = 7,
    push_since_hours: int = 1  # Ignored - no outbound sync
) -> Dict[str, Any]:
    """
    Run INBOUND Salesforce sync for all connected users.

    Data flows ONE WAY: Salesforce → CRM
    - Imports NEW Salesforce Leads/Contacts/Opportunities as CRM records
    - Matches CRM clients to Salesforce by EMAIL
    - Pulls ALL fields (text, number, date) from matched Salesforce records
    - Pulls emails from Salesforce EmailMessage and Task objects
    - Pulls calendar events from Salesforce Event and Task objects
    - NO data is pushed from CRM to Salesforce

    Args:
        sync_emails: Whether to pull emails from Salesforce
        sync_calendar: Whether to pull calendar from Salesforce
        sync_client_fields: Whether to match by email and pull all fields
        push_to_salesforce: IGNORED - outbound sync is disabled
        email_days_back: Days back to sync for emails
        calendar_days_back: Days back to sync for calendar
        calendar_days_forward: Days forward to sync for calendar
        push_since_hours: IGNORED - outbound sync is disabled

    Returns:
        Summary of all sync operations
    """
    results = {
        'users_processed': 0,
        'sync_direction': 'inbound',  # ONE WAY: Salesforce → CRM
        'inbound': {
            'emails_synced': 0,
            'emails_skipped': 0,
            'events_synced': 0,
            'tasks_synced': 0,
            'leads_matched': 0,
            'leads_updated': 0,
            'loans_matched': 0,
            'loans_updated': 0,
            'new_leads_created': 0,
            'new_loans_created': 0,
            'duplicates_skipped': 0,
        },
        'errors': [],
        'started_at': datetime.utcnow().isoformat(),
        'completed_at': None
    }

    db = SessionLocal()

    try:
        from salesforce_integration_models import IntegrationProfile

        # Get all connected Salesforce profiles - wrapped in try/except for missing table
        try:
            profiles = db.query(IntegrationProfile).filter(
                IntegrationProfile.provider == 'salesforce',
                IntegrationProfile.status.in_(['connected', 'active']),
            ).all()

            # Auto-enable sync on connected profiles that have it disabled
            for profile in profiles:
                if not profile.sync_enabled:
                    logger.info(f"Auto-enabling sync for profile {profile.id} (user {profile.user_id})")
                    profile.sync_enabled = True
            db.commit()

        except Exception as e:
            # Table might not exist or other DB error
            logger.warning(f"Could not query integration profiles: {e}")
            results['errors'].append(f"Could not query profiles: {str(e)[:100]}")
            results['completed_at'] = datetime.utcnow().isoformat()
            return results

        logger.info(f"Starting INBOUND Salesforce sync for {len(profiles)} users (Salesforce → CRM only)")

        for profile in profiles:
            try:
                results['users_processed'] += 1

                # ===== EMAIL-BASED MATCHING: Match CRM clients to Salesforce =====
                # This is the primary sync - matches by email and pulls ALL fields
                if sync_client_fields:
                    try:
                        from services.salesforce.sync_service import salesforce_sync

                        client_result = await salesforce_sync.sync_crm_clients_from_salesforce(
                            db=db,
                            integration_profile_id=profile.id,
                            limit=100
                        )
                        results['inbound']['leads_matched'] += client_result.get('leads_matched', 0)
                        results['inbound']['leads_updated'] += client_result.get('leads_updated', 0)
                        results['inbound']['loans_matched'] += client_result.get('loans_matched', 0)
                        results['inbound']['loans_updated'] += client_result.get('loans_updated', 0)
                        if client_result.get('errors'):
                            results['errors'].extend(client_result['errors'][:3])
                    except Exception as e:
                        logger.error(f"Client field sync failed for profile {profile.id}: {e}")
                        results['errors'].append(f"Client sync: {str(e)[:100]}")
                        try:
                            db.rollback()
                        except Exception as e2:
                            logger.error(f"Error in sync_all_users_salesforce (client sync rollback): {e2}")

                # ===== IMPORT NEW CLIENTS: Create CRM records for new SF records =====
                if import_new_clients:
                    try:
                        from services.salesforce.sync_service import salesforce_sync

                        import_result = await salesforce_sync.import_new_clients_from_salesforce(
                            db=db,
                            integration_profile_id=profile.id,
                            days_back=import_days_back,
                            limit=200
                        )
                        results['inbound']['new_leads_created'] += import_result.get('new_leads_created', 0)
                        results['inbound']['new_loans_created'] += import_result.get('new_loans_created', 0)
                        results['inbound']['duplicates_skipped'] += import_result.get('duplicates_skipped', 0)
                        if import_result.get('errors'):
                            results['errors'].extend(import_result['errors'][:3])
                    except Exception as e:
                        logger.error(f"New client import failed for profile {profile.id}: {e}")
                        results['errors'].append(f"New client import: {str(e)[:100]}")
                        try:
                            db.rollback()
                        except Exception as e2:
                            logger.error(f"Error in sync_all_users_salesforce (import rollback): {e2}")

                # ===== INBOUND: Pull emails from Salesforce =====
                if sync_emails:
                    try:
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
                    except Exception as e:
                        logger.error(f"Email sync failed for profile {profile.id}: {e}")
                        results['errors'].append(f"Email sync: {str(e)[:100]}")
                        # Rollback to recover from any transaction errors
                        try:
                            db.rollback()
                        except Exception as e2:
                            logger.error(f"Error in sync_all_users_salesforce (email sync rollback): {e2}")

                # ===== INBOUND: Pull calendar from Salesforce =====
                if sync_calendar:
                    try:
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
                    except Exception as e:
                        logger.error(f"Calendar sync failed for profile {profile.id}: {e}")
                        results['errors'].append(f"Calendar sync: {str(e)[:100]}")
                        # Rollback to recover from any transaction errors
                        try:
                            db.rollback()
                        except Exception as e2:
                            logger.error(f"Error in sync_all_users_salesforce (calendar sync rollback): {e2}")

                # NO OUTBOUND SYNC - Data flows Salesforce → CRM only

                # Update last sync time - use fresh transaction after any rollbacks
                try:
                    # CRITICAL: Ensure clean transaction state before updating
                    try:
                        db.rollback()
                    except Exception as e2:
                        logger.error(f"Error in sync_all_users_salesforce (pre-update rollback): {e2}")

                    # Re-fetch profile to ensure we have a valid object in the current transaction
                    from salesforce_integration_models import IntegrationProfile as IP
                    fresh_profile = db.query(IP).filter(IP.id == profile.id).first()
                    if fresh_profile:
                        fresh_profile.last_sync_at = datetime.utcnow()
                        db.commit()
                        logger.info(f"Updated last_sync_at for profile {profile.id}")
                except Exception as commit_err:
                    logger.warning(f"Could not update last_sync_at for profile {profile.id}: {commit_err}")
                    try:
                        db.rollback()
                    except Exception as e2:
                        logger.error(f"Error in sync_all_users_salesforce (commit rollback): {e2}")

            except Exception as e:
                logger.error(f"Sync failed for user {profile.user_id}: {e}")
                results['errors'].append(f"User {profile.user_id}: {str(e)[:100]}")
                # Rollback to ensure clean state for next profile
                try:
                    db.rollback()
                except Exception as e2:
                    logger.error(f"Error in sync_all_users_salesforce (profile rollback): {e2}")

        results['completed_at'] = datetime.utcnow().isoformat()

        logger.info(
            f"Salesforce INBOUND sync complete: {results['users_processed']} users | "
            f"leads matched={results['inbound']['leads_matched']}, updated={results['inbound']['leads_updated']} | "
            f"loans matched={results['inbound']['loans_matched']}, updated={results['inbound']['loans_updated']} | "
            f"emails={results['inbound']['emails_synced']}, events={results['inbound']['events_synced']}"
        )

        return results

    finally:
        db.close()


def sync_all_users_salesforce_sync(**kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for sync_all_users_salesforce"""
    logger.warning("🔄 Salesforce sync task TRIGGERED by scheduler")
    try:
        result = asyncio.run(sync_all_users_salesforce(**kwargs))
        logger.warning(f"✅ Salesforce sync task COMPLETED: {result.get('users_processed', 0)} users, errors={len(result.get('errors', []))}")
        return result
    except Exception as e:
        logger.error(f"❌ Salesforce sync task FAILED: {e}", exc_info=True)
        return {"error": "Internal server error"}


# ============================================================================
# Task: Salesforce Sync Health Check
# ============================================================================

async def check_salesforce_sync_health() -> Dict[str, Any]:
    """
    Check overall Salesforce sync health across all users.

    Returns:
        Health status with metrics for inbound sync
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
              AND created_at >= NOW() - INTERVAL '24 hours'
        """)).scalar()

        recent_inbound_failures = db.execute(text("""
            SELECT COUNT(*) FROM integration_events
            WHERE event_type IN ('email_sync_failed', 'calendar_sync_failed', 'sync_failed')
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
        inbound_failure_rate = (recent_inbound_failures or 0) / total_inbound if total_inbound > 0 else 0

        healthy = (
            inbound_failure_rate < 0.1 and  # Less than 10% failure rate
            (stale_connections or 0) == 0 and  # No stale connections
            (error_profiles or 0) < (connected or 1) * 0.1  # Less than 10% in error state
        )

        return {
            'healthy': healthy,
            'sync_direction': 'inbound',  # ONE WAY: Salesforce → CRM
            'sync_interval_minutes': 5,
            'metrics': {
                'connected_profiles': connected or 0,
                'error_profiles': error_profiles or 0,
                'inbound': {
                    'recent_syncs_24h': recent_inbound_syncs or 0,
                    'recent_failures_24h': recent_inbound_failures or 0,
                    'failure_rate': round(inbound_failure_rate * 100, 2)
                },
                'stale_connections': stale_connections or 0,
            },
            'alerts': [
                alert for alert in [
                    f"High inbound failure rate: {inbound_failure_rate*100:.1f}%" if inbound_failure_rate >= 0.1 else None,
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

    Sync is INBOUND ONLY every 10 minutes:
    - Salesforce → CRM (pull emails, calendar, tasks)
    - NO outbound sync (CRM does NOT push to Salesforce)

    Jobs are STAGGERED to prevent database connection spikes:
    - Sync runs at :08, :18, :28, :38, :48, :58
    - Health check runs at :02, :12, :22, :32, :42, :52

    Args:
        scheduler: APScheduler instance
    """
    from apscheduler.triggers.cron import CronTrigger

    # INBOUND sync every 3 minutes
    scheduler.add_job(
        sync_all_users_salesforce_sync,
        CronTrigger(minute="*/3"),
        id='salesforce_sync_all_users',
        name='Inbound Salesforce sync: pull from Salesforce to CRM every 3 minutes',
        replace_existing=True,
        kwargs={
            'sync_emails': True,
            'sync_calendar': True,
            'sync_client_fields': True,  # Match CRM records to Salesforce by email and pull all fields
            'import_new_clients': True,  # Import NEW Salesforce Leads/Contacts/Opportunities
            'push_to_salesforce': False,  # DISABLED - inbound only
            'email_days_back': 1,
            'calendar_days_back': 1,
            'calendar_days_forward': 14,
            'import_days_back': 7,  # Import clients created/modified in last 7 days
        }
    )

    # Health check every 10 minutes at :02, :12, :22, :32, :42, :52
    # Reduced frequency from 5 min to 10 min, staggered timing
    scheduler.add_job(
        check_salesforce_sync_health_sync,
        CronTrigger(minute="2,12,22,32,42,52"),
        id='salesforce_sync_health',
        name='Salesforce sync health check',
        replace_existing=True
    )

    logger.warning("🔄 Salesforce sync jobs registered: Salesforce → CRM every 3 minutes")


# ============================================================================
# Manual Trigger Functions (for API endpoints)
# ============================================================================

async def trigger_user_sync(
    user_id: int,
    sync_emails: bool = True,
    sync_calendar: bool = True,
    push_emails: bool = False,  # DISABLED - inbound only
    push_to_salesforce: bool = False  # DISABLED - inbound only
) -> Dict[str, Any]:
    """
    Manually trigger INBOUND sync for a specific user.

    Data flows ONE WAY: Salesforce → CRM
    - Pulls emails from Salesforce
    - Pulls calendar events from Salesforce
    - NO data is pushed to Salesforce

    Args:
        user_id: CRM user ID
        sync_emails: Pull emails from Salesforce
        sync_calendar: Pull calendar from Salesforce
        push_emails: IGNORED - outbound sync disabled
        push_to_salesforce: IGNORED - outbound sync disabled

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
            'sync_direction': 'inbound',  # ONE WAY: Salesforce → CRM
            'inbound': {
                'email_sync': None,
                'calendar_sync': None,
            }
        }

        # ===== INBOUND ONLY: Pull from Salesforce =====
        # Pass db session to avoid creating nested connections (connection pool exhaustion fix)
        if sync_emails:
            try:
                results['inbound']['email_sync'] = await sync_emails_from_salesforce(
                    profile.id, days_back=30, limit=500, db=db
                )
            except Exception as e:
                logger.error(f"Email sync failed for user {user_id}: {e}")
                results['inbound']['email_sync'] = {'success': False, 'error': str(e)}
                try:
                    db.rollback()
                except Exception as e2:
                    logger.error(f"Error in trigger_user_sync (email rollback): {e2}")

        if sync_calendar:
            try:
                results['inbound']['calendar_sync'] = await sync_calendar_from_salesforce(
                    profile.id, days_back=30, days_forward=90, limit=500, db=db
                )
            except Exception as e:
                logger.error(f"Calendar sync failed for user {user_id}: {e}")
                results['inbound']['calendar_sync'] = {'success': False, 'error': str(e)}
                try:
                    db.rollback()
                except Exception as e2:
                    logger.error(f"Error in trigger_user_sync (calendar rollback): {e2}")

        # NO OUTBOUND SYNC - Data flows Salesforce → CRM only

        # Update last sync time - use fresh transaction after any rollbacks
        try:
            # CRITICAL: Ensure clean transaction state before updating
            try:
                db.rollback()
            except Exception as e2:
                logger.error(f"Error in trigger_user_sync (pre-update rollback): {e2}")

            from salesforce_integration_models import IntegrationProfile as IP
            fresh_profile = db.query(IP).filter(IP.id == profile.id).first()
            if fresh_profile:
                fresh_profile.last_sync_at = datetime.utcnow()
                db.commit()
                logger.info(f"Updated last_sync_at for profile {profile.id}")
        except Exception as commit_err:
            logger.warning(f"Could not update last_sync_at for profile {profile.id}: {commit_err}")
            try:
                db.rollback()
            except Exception as e2:
                logger.error(f"Error in trigger_user_sync (commit rollback): {e2}")

        return results

    finally:
        db.close()


def trigger_user_sync_sync(user_id: int, **kwargs) -> Dict[str, Any]:
    """Synchronous wrapper for trigger_user_sync"""
    return asyncio.run(trigger_user_sync(user_id, **kwargs))
