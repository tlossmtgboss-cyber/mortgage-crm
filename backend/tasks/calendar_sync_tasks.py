"""
Calendar Sync Background Tasks
Handles async sync operations between CRM and Salesforce calendars

Tasks:
- push_event_to_salesforce: Push a single event to Salesforce
- process_pending_sync_events: Process all pending events in queue
- reconcile_calendar: Nightly reconciliation job
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
                    "error": str(e)
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
# Scheduler Integration
# ============================================================================

def register_calendar_sync_jobs(scheduler):
    """
    Register calendar sync jobs with APScheduler or similar.

    Args:
        scheduler: APScheduler instance
    """
    # Process pending events every 30 seconds
    scheduler.add_job(
        process_pending_sync_events_sync,
        'interval',
        seconds=30,
        id='calendar_sync_pending',
        name='Process pending calendar sync events',
        replace_existing=True
    )

    # Health check every 5 minutes
    scheduler.add_job(
        check_sync_health_sync,
        'interval',
        minutes=5,
        id='calendar_sync_health',
        name='Calendar sync health check',
        replace_existing=True
    )

    logger.info("Calendar sync background jobs registered")
