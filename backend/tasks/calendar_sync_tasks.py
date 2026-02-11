"""
Calendar Sync Background Tasks
Handles async sync operations between CRM and Salesforce calendars

Phase 1 Tasks (Push - CRM → Salesforce):
- push_event_to_salesforce: Push a single event to Salesforce
- process_pending_sync_events: Process all pending events in queue

Phase 2 Tasks (Pull - Salesforce → CRM):
- poll_salesforce_events: Poll Salesforce for event changes
- process_inbound_sync: Process pulled events

Maintenance Tasks:
- reconcile_calendar: Nightly reconciliation job
- check_sync_health: Health monitoring
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from database import SessionLocal

from models.calendar_sync_models import (
    CRMCalendarEvent,
    CalendarEventSyncMap,
    CalendarSyncLog,
    SyncStatus
)
from services.calendar_sync_service import CalendarSyncService, CalendarSyncResult

logger = logging.getLogger(__name__)


# ============================================================================
# Task: Push Single Event to Salesforce
# ============================================================================

async def push_event_to_salesforce(
    crm_event_id: str,
    max_retries: int = 5,
    retry_delay_base: float = 1.0
) -> dict:
    """
    Push a single CRM event to Salesforce.

    Implements exponential backoff retry logic.

    Args:
        crm_event_id: CRM event ID to push
        max_retries: Maximum retry attempts
        retry_delay_base: Base delay in seconds for exponential backoff

    Returns:
        Result dictionary with success status and details
    """
    db = SessionLocal()
    attempt = 0
    last_error = None

    try:
        while attempt < max_retries:
            attempt += 1

            try:
                service = CalendarSyncService(db)
                result = await service.push_event_to_salesforce(crm_event_id)

                if result.success:
                    logger.info(
                        f"Successfully pushed event {crm_event_id} to Salesforce "
                        f"(attempt {attempt}/{max_retries})"
                    )
                    return result.to_dict()
                else:
                    last_error = result.error
                    logger.warning(
                        f"Failed to push event {crm_event_id}: {result.error} "
                        f"(attempt {attempt}/{max_retries})"
                    )

            except Exception as e:
                last_error = str(e)
                logger.exception(
                    f"Error pushing event {crm_event_id}: {e} "
                    f"(attempt {attempt}/{max_retries})"
                )

            # Exponential backoff
            if attempt < max_retries:
                delay = retry_delay_base * (2 ** (attempt - 1))
                logger.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)

        # Max retries exceeded - mark as failed
        event = db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.id == crm_event_id
        ).first()

        if event:
            event.sync_status = SyncStatus.FAILED.value
            event.sync_error = f"Max retries exceeded: {last_error}"
            db.commit()

        return {
            "success": False,
            "crm_event_id": crm_event_id,
            "error": f"Max retries ({max_retries}) exceeded. Last error: {last_error}",
            "attempts": attempt
        }

    finally:
        db.close()


def push_event_to_salesforce_sync(crm_event_id: str, **kwargs) -> dict:
    """Synchronous wrapper for push_event_to_salesforce"""
    return asyncio.run(push_event_to_salesforce(crm_event_id, **kwargs))


# ============================================================================
# Task: Process All Pending Events
# ============================================================================

async def process_pending_sync_events(
    batch_size: int = 50,
    max_concurrent: int = 5
) -> dict:
    """
    Process all pending calendar sync events.

    Args:
        batch_size: Maximum events to process in one run
        max_concurrent: Maximum concurrent sync operations

    Returns:
        Summary of processed events
    """
    db = SessionLocal()

    try:
        service = CalendarSyncService(db)
        pending_events = service.get_pending_sync_events(limit=batch_size)

        if not pending_events:
            logger.info("No pending calendar sync events")
            return {
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "events": []
            }

        logger.info(f"Processing {len(pending_events)} pending calendar sync events")

        results = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "events": []
        }

        # Process in batches with concurrency limit
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(event_id: str):
            async with semaphore:
                return await push_event_to_salesforce(event_id, max_retries=3)

        tasks = [
            process_with_semaphore(event.id)
            for event in pending_events
        ]

        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(task_results):
            results["processed"] += 1

            if isinstance(result, Exception):
                results["failed"] += 1
                results["events"].append({
                    "crm_event_id": pending_events[i].id,
                    "success": False,
                    "error": str(result)
                })
            elif isinstance(result, dict):
                if result.get("success"):
                    results["succeeded"] += 1
                else:
                    results["failed"] += 1
                results["events"].append(result)

        logger.info(
            f"Processed {results['processed']} events: "
            f"{results['succeeded']} succeeded, {results['failed']} failed"
        )

        return results

    finally:
        db.close()


def process_pending_sync_events_sync(**kwargs) -> dict:
    """Synchronous wrapper for process_pending_sync_events"""
    return asyncio.run(process_pending_sync_events(**kwargs))


# ============================================================================
# Task: Nightly Reconciliation
# ============================================================================

async def reconcile_calendar(
    user_id: int,
    lookback_hours: int = 24
) -> dict:
    """
    Reconcile calendar events between CRM and Salesforce.

    Checks for:
    - CRM events missing in Salesforce
    - Fingerprint mismatches
    - Orphaned mappings

    Args:
        user_id: User ID to reconcile
        lookback_hours: Hours to look back for modified events

    Returns:
        Reconciliation results
    """
    db = SessionLocal()

    try:
        service = CalendarSyncService(db)
        cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)

        results = {
            "user_id": user_id,
            "checked": 0,
            "missing_in_salesforce": 0,
            "fingerprint_mismatch": 0,
            "orphaned_mappings": 0,
            "fixed": 0,
            "errors": []
        }

        # Get recently modified CRM events
        events = db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.owner_user_id == user_id,
            CRMCalendarEvent.updated_at >= cutoff
        ).all()

        results["checked"] = len(events)

        for event in events:
            try:
                if not event.sync_mapping:
                    # Event not synced to Salesforce
                    results["missing_in_salesforce"] += 1

                    # Queue for sync
                    event.sync_status = SyncStatus.PENDING.value
                    results["fixed"] += 1

                elif event.sync_mapping.fingerprint_hash != event.fingerprint_hash:
                    # Fingerprint mismatch - needs resync
                    results["fingerprint_mismatch"] += 1

                    # Queue for sync
                    event.sync_status = SyncStatus.PENDING.value
                    results["fixed"] += 1

            except Exception as e:
                results["errors"].append({
                    "event_id": event.id,
                    "error": "Internal server error"
                })

        db.commit()

        # Check for orphaned mappings (mappings without CRM events)
        orphaned = db.query(CalendarEventSyncMap).filter(
            ~CalendarEventSyncMap.crm_event_id.in_(
                db.query(CRMCalendarEvent.id)
            )
        ).all()

        results["orphaned_mappings"] = len(orphaned)

        # Clean up orphaned mappings
        for mapping in orphaned:
            db.delete(mapping)
            results["fixed"] += 1

        db.commit()

        logger.info(
            f"Calendar reconciliation for user {user_id}: "
            f"checked={results['checked']}, fixed={results['fixed']}"
        )

        return results

    finally:
        db.close()


def reconcile_calendar_sync(user_id: int, **kwargs) -> dict:
    """Synchronous wrapper for reconcile_calendar"""
    return asyncio.run(reconcile_calendar(user_id, **kwargs))


# ============================================================================
# Task: Sync Health Check
# ============================================================================

async def check_sync_health() -> dict:
    """
    Check overall calendar sync health.

    Returns:
        Health status with metrics
    """
    db = SessionLocal()

    try:
        # Count events by sync status
        pending = db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.sync_status == SyncStatus.PENDING.value
        ).count()

        failed = db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.sync_status == SyncStatus.FAILED.value
        ).count()

        synced = db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.sync_status == SyncStatus.SYNCED.value
        ).count()

        # Check for stale pending events (pending > 1 hour)
        stale_cutoff = datetime.utcnow() - timedelta(hours=1)
        stale = db.query(CRMCalendarEvent).filter(
            CRMCalendarEvent.sync_status == SyncStatus.PENDING.value,
            CRMCalendarEvent.updated_at < stale_cutoff
        ).count()

        # Recent sync errors (last 24 hours)
        error_cutoff = datetime.utcnow() - timedelta(hours=24)
        recent_errors = db.query(CalendarSyncLog).filter(
            CalendarSyncLog.result == "failed",
            CalendarSyncLog.created_at >= error_cutoff
        ).count()

        # Calculate health score
        total = pending + failed + synced
        if total > 0:
            failure_rate = failed / total
            pending_rate = pending / total
        else:
            failure_rate = 0
            pending_rate = 0

        healthy = (
            failure_rate < 0.05 and  # Less than 5% failures
            stale == 0 and  # No stale pending events
            pending < 100  # Queue not backed up
        )

        return {
            "healthy": healthy,
            "metrics": {
                "pending": pending,
                "failed": failed,
                "synced": synced,
                "stale_pending": stale,
                "recent_errors_24h": recent_errors,
                "failure_rate": round(failure_rate * 100, 2),
                "pending_rate": round(pending_rate * 100, 2)
            },
            "alerts": [
                alert for alert in [
                    "High failure rate" if failure_rate >= 0.05 else None,
                    f"{stale} stale pending events" if stale > 0 else None,
                    f"Queue backed up: {pending} pending" if pending >= 100 else None,
                ] if alert
            ],
            "checked_at": datetime.utcnow().isoformat()
        }

    finally:
        db.close()


def check_sync_health_sync() -> dict:
    """Synchronous wrapper for check_sync_health"""
    return asyncio.run(check_sync_health())


# ============================================================================
# Task: Poll Salesforce for Event Changes (Phase 2)
# ============================================================================

async def poll_salesforce_events() -> dict:
    """
    Poll Salesforce for event changes for all active users.

    Queries Salesforce for events modified since last poll watermark.
    Creates/updates CRM events accordingly.

    Returns:
        Summary of polling results
    """
    db = SessionLocal()

    try:
        from salesforce_integration_models import IntegrationProfile
        from models.calendar_sync_models import CalendarSyncSettings

        results = {
            "users_polled": 0,
            "total_pulled": 0,
            "total_created": 0,
            "total_updated": 0,
            "total_skipped": 0,
            "errors": []
        }

        # Get all users with active Salesforce integration and polling enabled
        active_profiles = db.query(IntegrationProfile).filter(
            IntegrationProfile.provider == "salesforce",
            IntegrationProfile.status == "active"
        ).all()

        for profile in active_profiles:
            try:
                # Check if polling is enabled for this user
                settings = db.query(CalendarSyncSettings).filter(
                    CalendarSyncSettings.user_id == profile.user_id
                ).first()

                if not settings or not settings.polling_enabled:
                    continue

                service = CalendarSyncService(db)

                # Use last poll watermark or default to 24 hours
                since = settings.last_poll_watermark
                if not since:
                    since = datetime.utcnow() - timedelta(hours=24)

                pull_result = await service.pull_events_from_salesforce(
                    user_id=profile.user_id,
                    since=since,
                    limit=settings.batch_size or 200
                )

                results["users_polled"] += 1
                results["total_pulled"] += pull_result["pulled"]
                results["total_created"] += pull_result["created"]
                results["total_updated"] += pull_result["updated"]
                results["total_skipped"] += pull_result["skipped_echo"] + pull_result["skipped_conflict"]

                if pull_result["errors"]:
                    results["errors"].extend(pull_result["errors"][:3])

                logger.info(
                    f"Polled Salesforce for user {profile.user_id}: "
                    f"pulled={pull_result['pulled']}, created={pull_result['created']}"
                )

            except Exception as e:
                logger.error(f"Error polling for user {profile.user_id}: {e}")
                results["errors"].append({
                    "user_id": profile.user_id,
                    "error": "Internal server error"
                })

        logger.info(
            f"Salesforce polling complete: {results['users_polled']} users, "
            f"{results['total_pulled']} events processed"
        )

        return results

    finally:
        db.close()


def poll_salesforce_events_sync() -> dict:
    """Synchronous wrapper for poll_salesforce_events"""
    return asyncio.run(poll_salesforce_events())


# ============================================================================
# Task: Bidirectional Sync for Single User
# ============================================================================

async def sync_user_calendar(user_id: int) -> dict:
    """
    Perform bidirectional sync for a single user.

    1. Push pending CRM events to Salesforce
    2. Pull changed events from Salesforce

    Args:
        user_id: CRM user ID

    Returns:
        Sync summary
    """
    db = SessionLocal()

    try:
        service = CalendarSyncService(db)

        results = {
            "user_id": user_id,
            "push": {"processed": 0, "succeeded": 0, "failed": 0},
            "pull": {"pulled": 0, "created": 0, "updated": 0}
        }

        # Phase 1: Push pending events
        pending = service.get_pending_sync_events(limit=50)
        pending_for_user = [e for e in pending if e.owner_user_id == user_id]

        for event in pending_for_user:
            try:
                result = await service.push_event_to_salesforce(event.id)
                results["push"]["processed"] += 1
                if result.success:
                    results["push"]["succeeded"] += 1
                else:
                    results["push"]["failed"] += 1
            except Exception as e:
                logger.error(f"Push error for event {event.id}: {e}")
                results["push"]["failed"] += 1

        # Phase 2: Pull from Salesforce
        settings = service.get_settings(user_id)
        since = settings.last_poll_watermark or (datetime.utcnow() - timedelta(hours=24))

        pull_result = await service.pull_events_from_salesforce(
            user_id=user_id,
            since=since,
            limit=200
        )

        results["pull"] = {
            "pulled": pull_result["pulled"],
            "created": pull_result["created"],
            "updated": pull_result["updated"]
        }

        logger.info(f"User {user_id} sync complete: push={results['push']}, pull={results['pull']}")

        return results

    finally:
        db.close()


def sync_user_calendar_sync(user_id: int) -> dict:
    """Synchronous wrapper for sync_user_calendar"""
    return asyncio.run(sync_user_calendar(user_id))


# ============================================================================
# Scheduler Integration
# ============================================================================

def register_calendar_sync_jobs(scheduler):
    """
    Register calendar sync jobs with APScheduler or similar.

    Args:
        scheduler: APScheduler instance
    """
    # Process pending push events every 2 minutes
    scheduler.add_job(
        process_pending_sync_events_sync,
        'interval',
        minutes=2,
        id='calendar_sync_pending',
        name='Process pending calendar sync events (push)',
        replace_existing=True
    )

    # Poll Salesforce for changes every 2 minutes
    scheduler.add_job(
        poll_salesforce_events_sync,
        'interval',
        minutes=2,
        id='calendar_sync_poll',
        name='Poll Salesforce for event changes (pull)',
        replace_existing=True
    )

    # Health check every 15 minutes (reduced from 5 to prevent connection exhaustion)
    scheduler.add_job(
        check_sync_health_sync,
        'interval',
        minutes=15,
        id='calendar_sync_health',
        name='Calendar sync health check',
        replace_existing=True
    )

    logger.info("Calendar sync jobs registered: push/pull every 2 minutes")
