"""
SLA Background Tasks

Scheduled jobs for:
- Updating milestone statuses (every 15 minutes)
- Creating performance snapshots (daily)
- Generating efficiency reports (weekly)
- Reactivating snoozed alerts
- Creating risk alerts
"""

import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from database import SessionLocal
from crud.sla_tracking import (
    update_milestone_statuses_batch,
    create_performance_snapshot,
    create_efficiency_report,
    reactivate_snoozed_alerts,
    get_all_sla_measures
)
from services.sla_tracking_service import get_sla_service

logger = logging.getLogger(__name__)


def get_db_session():
    """Create a new database session for background tasks."""
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        logger.error(f"Error creating DB session: {e}")
        db.close()
        raise


# ============================================================================
# Status Update Task
# ============================================================================

def update_milestone_statuses_task():
    """
    Background task to update all active milestone statuses.
    Should run every 15 minutes.
    Checks milestones against their deadlines and updates status to at_risk or overdue.
    """
    db = None
    try:
        db = get_db_session()
        logger.info("Starting milestone status update task...")

        results = update_milestone_statuses_batch(db, organization_id=1)

        logger.info(f"Milestone status update complete: {results}")
        return results

    except Exception as e:
        logger.error(f"Error in milestone status update task: {e}")
        return {"error": str(e)}
    finally:
        if db:
            db.close()


# ============================================================================
# Risk Alert Task
# ============================================================================

def create_risk_alerts_task():
    """
    Background task to create alerts for at-risk and overdue milestones.
    Should run every hour or after status updates.
    """
    db = None
    try:
        db = get_db_session()
        logger.info("Starting risk alert creation task...")

        service = get_sla_service(db)
        service.check_and_create_risk_alerts()

        logger.info("Risk alert creation task complete")
        return {"status": "success"}

    except Exception as e:
        logger.error(f"Error in risk alert creation task: {e}")
        return {"error": str(e)}
    finally:
        if db:
            db.close()


# ============================================================================
# Snoozed Alert Reactivation Task
# ============================================================================

def reactivate_snoozed_alerts_task():
    """
    Background task to reactivate snoozed alerts that have passed their snooze time.
    Should run every 15 minutes.
    """
    db = None
    try:
        db = get_db_session()
        logger.info("Starting snoozed alert reactivation task...")

        count = reactivate_snoozed_alerts(db, organization_id=1)

        logger.info(f"Reactivated {count} snoozed alerts")
        return {"reactivated": count}

    except Exception as e:
        logger.error(f"Error in snoozed alert reactivation task: {e}")
        return {"error": str(e)}
    finally:
        if db:
            db.close()


# ============================================================================
# Daily Snapshot Task
# ============================================================================

def create_daily_snapshot_task(snapshot_date: Optional[date] = None):
    """
    Background task to create daily performance snapshots.
    Should run once daily, after midnight.

    Creates snapshots at:
    - Organization level (overall)
    - Per milestone type
    """
    db = None
    try:
        db = get_db_session()

        if not snapshot_date:
            snapshot_date = date.today() - timedelta(days=1)  # Yesterday's snapshot

        logger.info(f"Starting daily snapshot creation for {snapshot_date}...")

        # Create org-level snapshot
        org_snapshot = create_performance_snapshot(
            db,
            snapshot_date=snapshot_date,
            scope_type="organization",
            scope_id=None,
            milestone_type=None,
            period_type="daily",
            organization_id=1
        )
        logger.info(f"Created org snapshot: on_time_rate={org_snapshot.on_time_rate}%")

        # Get all active milestone types
        measures = get_all_sla_measures(db, organization_id=1, active_only=True)
        milestone_types = list(set(m.milestone_type for m in measures))

        # Create per-milestone-type snapshots
        for mt in milestone_types:
            try:
                create_performance_snapshot(
                    db,
                    snapshot_date=snapshot_date,
                    scope_type="organization",
                    scope_id=None,
                    milestone_type=mt,
                    period_type="daily",
                    organization_id=1
                )
            except Exception as e:
                logger.warning(f"Error creating snapshot for {mt}: {e}")

        logger.info(f"Daily snapshot creation complete for {snapshot_date}")
        return {"status": "success", "date": str(snapshot_date)}

    except Exception as e:
        logger.error(f"Error in daily snapshot task: {e}")
        return {"error": str(e)}
    finally:
        if db:
            db.close()


# ============================================================================
# Weekly Report Task
# ============================================================================

def generate_weekly_report_task():
    """
    Background task to generate weekly efficiency reports.
    Should run once weekly (e.g., Monday morning).
    """
    db = None
    try:
        db = get_db_session()

        # Calculate last week's date range
        today = date.today()
        period_end = today - timedelta(days=today.weekday())  # Last Monday
        period_start = period_end - timedelta(days=7)  # Week before that

        logger.info(f"Starting weekly report generation for {period_start} to {period_end}...")

        report = create_efficiency_report(
            db,
            period_start=period_start,
            period_end=period_end,
            organization_id=1
        )

        logger.info(f"Weekly report generated: compliance_rate={report.overall_sla_compliance_rate}%")
        return {
            "status": "success",
            "report_id": report.id,
            "period_start": str(period_start),
            "period_end": str(period_end),
            "compliance_rate": report.overall_sla_compliance_rate
        }

    except Exception as e:
        logger.error(f"Error in weekly report task: {e}")
        return {"error": str(e)}
    finally:
        if db:
            db.close()


# ============================================================================
# Combined Task Runner
# ============================================================================

def run_all_sla_tasks():
    """
    Run all SLA background tasks in sequence.
    Useful for manual triggering or testing.
    """
    results = {}

    logger.info("Running all SLA tasks...")

    # 1. Update statuses
    results["status_update"] = update_milestone_statuses_task()

    # 2. Create risk alerts
    results["risk_alerts"] = create_risk_alerts_task()

    # 3. Reactivate snoozed alerts
    results["snoozed_reactivation"] = reactivate_snoozed_alerts_task()

    logger.info(f"All SLA tasks complete: {results}")
    return results


def run_daily_sla_tasks():
    """
    Run daily SLA tasks (called once per day).
    """
    results = {}

    logger.info("Running daily SLA tasks...")

    # Run regular tasks first
    results["regular"] = run_all_sla_tasks()

    # Create daily snapshot
    results["snapshot"] = create_daily_snapshot_task()

    logger.info(f"Daily SLA tasks complete: {results}")
    return results


def run_weekly_sla_tasks():
    """
    Run weekly SLA tasks (called once per week).
    """
    results = {}

    logger.info("Running weekly SLA tasks...")

    # Run daily tasks first
    results["daily"] = run_daily_sla_tasks()

    # Generate weekly report
    results["report"] = generate_weekly_report_task()

    logger.info(f"Weekly SLA tasks complete: {results}")
    return results


# ============================================================================
# APScheduler Integration
# ============================================================================

def setup_sla_scheduler(scheduler):
    """
    Configure APScheduler jobs for SLA tracking.
    Call this from main.py to register scheduled tasks.

    Args:
        scheduler: AsyncIOScheduler instance from APScheduler
    """
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger

    # Update milestone statuses every 15 minutes
    scheduler.add_job(
        update_milestone_statuses_task,
        trigger=IntervalTrigger(minutes=15),
        id="sla_status_update",
        name="Update SLA Milestone Statuses",
        replace_existing=True
    )

    # Create risk alerts every hour
    scheduler.add_job(
        create_risk_alerts_task,
        trigger=IntervalTrigger(hours=1),
        id="sla_risk_alerts",
        name="Create SLA Risk Alerts",
        replace_existing=True
    )

    # Reactivate snoozed alerts every 15 minutes
    scheduler.add_job(
        reactivate_snoozed_alerts_task,
        trigger=IntervalTrigger(minutes=15),
        id="sla_snooze_reactivation",
        name="Reactivate Snoozed Alerts",
        replace_existing=True
    )

    # Daily snapshot at 1 AM
    scheduler.add_job(
        create_daily_snapshot_task,
        trigger=CronTrigger(hour=1, minute=0),
        id="sla_daily_snapshot",
        name="Create Daily SLA Snapshot",
        replace_existing=True
    )

    # Weekly report on Monday at 6 AM
    scheduler.add_job(
        generate_weekly_report_task,
        trigger=CronTrigger(day_of_week="mon", hour=6, minute=0),
        id="sla_weekly_report",
        name="Generate Weekly SLA Report",
        replace_existing=True
    )

    logger.info("SLA scheduler jobs configured")
