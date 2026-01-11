"""
Calendar Sync Background Jobs

Implements 1-minute bi-directional sync between CRM Calendar and Salesforce Events.

Jobs:
- calendar_push_job: Push pending CRM events to Salesforce (every 60 seconds)
- calendar_pull_job: Pull Salesforce events to CRM (every 60 seconds, staggered by 30s)
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database import SessionLocal
from services.calendar_sync_service import calendar_sync_service

logger = logging.getLogger(__name__)


def get_db_session() -> Session:
    """Get a new database session"""
    return SessionLocal()


async def _run_push_cycle():
    """Internal async function to run the push cycle"""
    db = get_db_session()
    try:
        logger.info("Starting calendar push cycle...")
        start_time = datetime.now(timezone.utc)

        result = await calendar_sync_service.push_pending_events(db)

        logger.info(
            f"Calendar push cycle complete: "
            f"{result.records_succeeded}/{result.records_processed} succeeded, "
            f"{result.records_failed} failed, "
            f"{result.duration_ms}ms"
        )

        if result.errors:
            for error in result.errors[:5]:  # Log first 5 errors
                logger.warning(f"Push error: {error}")

        return result

    except Exception as e:
        logger.exception(f"Calendar push cycle failed: {e}")
        raise
    finally:
        db.close()


async def _run_pull_cycle():
    """Internal async function to run the pull cycle"""
    db = get_db_session()
    try:
        logger.info("Starting calendar pull cycle...")
        start_time = datetime.now(timezone.utc)

        result = await calendar_sync_service.pull_salesforce_changes(db)

        logger.info(
            f"Calendar pull cycle complete: "
            f"{result.records_succeeded}/{result.records_processed} succeeded, "
            f"{result.records_skipped} skipped, "
            f"{result.echo_prevented} echoes prevented, "
            f"{result.records_failed} failed, "
            f"{result.duration_ms}ms"
        )

        if result.errors:
            for error in result.errors[:5]:  # Log first 5 errors
                logger.warning(f"Pull error: {error}")

        return result

    except Exception as e:
        logger.exception(f"Calendar pull cycle failed: {e}")
        raise
    finally:
        db.close()


def calendar_push_job():
    """
    Push pending CRM events to Salesforce.

    Runs every 60 seconds. This is the main push loop that ensures
    CRM calendar changes are synced to Salesforce (and subsequently Outlook)
    within 1 minute.

    This function is called by APScheduler and wraps the async implementation.
    """
    try:
        # Run the async function in the event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running (e.g., in FastAPI), create task
            asyncio.create_task(_run_push_cycle())
        else:
            # Run synchronously
            loop.run_until_complete(_run_push_cycle())
    except RuntimeError:
        # No event loop, create a new one
        asyncio.run(_run_push_cycle())
    except Exception as e:
        logger.exception(f"Calendar push job failed: {e}")


def calendar_pull_job():
    """
    Pull Salesforce events to CRM.

    Runs every 60 seconds (staggered by 30s from push loop). This is the main
    pull loop that ensures Outlook/Salesforce calendar changes are synced to
    CRM within 1 minute.

    This function is called by APScheduler and wraps the async implementation.
    """
    try:
        # Run the async function in the event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running (e.g., in FastAPI), create task
            asyncio.create_task(_run_pull_cycle())
        else:
            # Run synchronously
            loop.run_until_complete(_run_pull_cycle())
    except RuntimeError:
        # No event loop, create a new one
        asyncio.run(_run_pull_cycle())
    except Exception as e:
        logger.exception(f"Calendar pull job failed: {e}")


def register_calendar_sync_jobs(scheduler):
    """
    Register calendar sync jobs with APScheduler.

    Call this function during application startup to enable
    automatic bi-directional calendar synchronization.

    Args:
        scheduler: APScheduler instance (AsyncIOScheduler)
    """
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger

    # Push job: Every 60 seconds
    scheduler.add_job(
        calendar_push_job,
        trigger=IntervalTrigger(seconds=60),
        id='calendar_push_job',
        name='Calendar Push to Salesforce',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )

    # Pull job: Every 60 seconds, starting 30 seconds after push
    # This staggers the jobs to reduce load spikes
    scheduler.add_job(
        calendar_pull_job,
        trigger=IntervalTrigger(seconds=60, start_date=datetime.now(timezone.utc).replace(second=30)),
        id='calendar_pull_job',
        name='Calendar Pull from Salesforce',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )

    logger.info("Calendar sync jobs registered: push every 60s, pull every 60s (staggered by 30s)")


async def run_manual_sync(direction: str = 'both'):
    """
    Run a manual sync cycle.

    Useful for testing or admin-triggered syncs.

    Args:
        direction: 'push', 'pull', or 'both'
    """
    db = get_db_session()
    try:
        if direction in ['push', 'both']:
            push_result = await calendar_sync_service.push_pending_events(db)
            logger.info(f"Manual push complete: {push_result.to_dict()}")

        if direction in ['pull', 'both']:
            pull_result = await calendar_sync_service.pull_salesforce_changes(db)
            logger.info(f"Manual pull complete: {pull_result.to_dict()}")

    finally:
        db.close()
