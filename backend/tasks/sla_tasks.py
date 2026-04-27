"""
SLA Background Tasks

Scheduled jobs for:
- Updating milestone statuses (every 15 minutes)
- Creating performance snapshots (8 AM and 12 PM)
- Generating efficiency reports (weekly)
- Reactivating snoozed alerts
- Creating risk alerts
- Run rate calculations with inventory forecasting
"""

import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from database import SessionLocal, get_db_with_tenant
import database.models  # noqa: F401 — ensure all mappers register
from database.models.core import Organization
from crud.sla_tracking import (
    update_milestone_statuses_batch,
    create_performance_snapshot,
    create_efficiency_report,
    reactivate_snoozed_alerts,
    get_all_sla_measures,
    get_active_milestones
)
from services.sla_tracking_service import get_sla_service
from models.sla_tracking import (
    LoanMilestoneHistory,
    SLAMeasure,
    SLAStatus,
    MilestoneType,
    TimeUnit
)

logger = logging.getLogger(__name__)


def get_db_session():
    """Create a new database session for background tasks.

    Note: Background tasks run outside the FastAPI request lifecycle,
    so RLS context is not available from middleware. For tenant-scoped
    background work, use get_db_with_tenant(org_id) instead.
    """
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        logger.error(f"Error creating DB session: {e}")
        db.close()
        raise


def get_all_org_ids(db: Session) -> List[int]:
    """Get all active organization IDs. Falls back to all orgs if none are active."""
    try:
        org_ids = [row[0] for row in db.query(Organization.id).filter(Organization.is_active == True).all()]
        if not org_ids:
            org_ids = [row[0] for row in db.query(Organization.id).all()]
        return org_ids
    except Exception as e:
        logger.warning(f"Error querying organizations, falling back to org_id=1: {e}")
        return [1]


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

        org_ids = get_all_org_ids(db)
        db.close()
        db = None

        all_results = {}
        for org_id in org_ids:
            try:
                with get_db_with_tenant(org_id) as tenant_db:
                    results = update_milestone_statuses_batch(tenant_db, organization_id=org_id)
                    all_results[org_id] = results
                    logger.info(f"Milestone status update for org {org_id}: {results}")
            except Exception as e:
                logger.error(f"Error updating milestones for org {org_id}: {e}")
                all_results[org_id] = {"error": str(e)}

        logger.info(f"Milestone status update complete for {len(org_ids)} orgs")
        return all_results

    except Exception as e:
        logger.error(f"Error in milestone status update task: {e}")
        return {"error": "Internal server error"}
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
    Iterates over all active organizations for multi-tenant support.
    """
    db = None
    try:
        db = get_db_session()
        org_ids = get_all_org_ids(db)
        db.close()
        db = None

        logger.info(f"Starting risk alert creation task for {len(org_ids)} orgs...")

        for org_id in org_ids:
            try:
                with get_db_with_tenant(org_id) as tenant_db:
                    service = get_sla_service(tenant_db, organization_id=org_id)
                    service.check_and_create_risk_alerts()
            except Exception as e:
                logger.error(f"Error creating risk alerts for org {org_id}: {e}")

        logger.info("Risk alert creation task complete")
        return {"status": "success"}

    except Exception as e:
        logger.error(f"Error in risk alert creation task: {e}")
        return {"error": "Internal server error"}
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

        org_ids = get_all_org_ids(db)
        db.close()
        db = None

        total_count = 0
        per_org = {}
        for org_id in org_ids:
            try:
                with get_db_with_tenant(org_id) as tenant_db:
                    count = reactivate_snoozed_alerts(tenant_db, organization_id=org_id)
                    total_count += count
                    per_org[org_id] = count
                    if count > 0:
                        logger.info(f"Reactivated {count} snoozed alerts for org {org_id}")
            except Exception as e:
                logger.error(f"Error reactivating snoozed alerts for org {org_id}: {e}")
                per_org[org_id] = {"error": str(e)}

        logger.info(f"Reactivated {total_count} total snoozed alerts across {len(org_ids)} orgs")
        return {"reactivated": total_count, "per_org": per_org}

    except Exception as e:
        logger.error(f"Error in snoozed alert reactivation task: {e}")
        return {"error": "Internal server error"}
    finally:
        if db:
            db.close()


# ============================================================================
# Run Rate & Forecasting Calculations
# ============================================================================

def calculate_run_rate(
    db: Session,
    milestone_type: MilestoneType,
    organization_id: int,
    lookback_days: int = 30,
) -> Dict[str, Any]:
    """
    Calculate run rate for a specific milestone type.

    Run rate = average completions per day over the lookback period

    Returns:
        Dict with run rate metrics including:
        - daily_run_rate: Average completions per day
        - weekly_run_rate: Average completions per week
        - avg_completion_time_hours: Average time to complete
        - on_time_rate: Percentage completed on time
        - trend: "improving", "declining", or "stable"
    """
    now = datetime.now(timezone.utc)
    lookback_start = now - timedelta(days=lookback_days)
    half_period_start = now - timedelta(days=lookback_days // 2)

    # Get completions in the lookback period
    completions = db.query(LoanMilestoneHistory).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            LoanMilestoneHistory.milestone_type == milestone_type,
            LoanMilestoneHistory.status == SLAStatus.COMPLETED,
            LoanMilestoneHistory.completed_at >= lookback_start,
            LoanMilestoneHistory.completed_at <= now
        )
    ).all()

    total_completions = len(completions)

    if total_completions == 0:
        return {
            "milestone_type": milestone_type.value,
            "daily_run_rate": 0,
            "weekly_run_rate": 0,
            "avg_completion_time_hours": 0,
            "on_time_rate": 0,
            "trend": "stable",
            "lookback_days": lookback_days,
            "total_completions": 0
        }

    # Calculate basic run rates
    daily_run_rate = total_completions / lookback_days
    weekly_run_rate = daily_run_rate * 7

    # Calculate average completion time
    completion_times = [
        c.actual_hours for c in completions
        if c.actual_hours is not None
    ]
    avg_completion_time = sum(completion_times) / len(completion_times) if completion_times else 0

    # Calculate on-time rate
    on_time_count = sum(1 for c in completions if c.variance_hours is None or c.variance_hours <= 0)
    on_time_rate = (on_time_count / total_completions) * 100

    # Calculate trend (compare first half vs second half)
    first_half = [c for c in completions if c.completed_at < half_period_start]
    second_half = [c for c in completions if c.completed_at >= half_period_start]

    first_half_rate = len(first_half) / (lookback_days / 2) if lookback_days > 0 else 0
    second_half_rate = len(second_half) / (lookback_days / 2) if lookback_days > 0 else 0

    if second_half_rate > first_half_rate * 1.1:
        trend = "improving"
    elif second_half_rate < first_half_rate * 0.9:
        trend = "declining"
    else:
        trend = "stable"

    return {
        "milestone_type": milestone_type.value,
        "daily_run_rate": round(daily_run_rate, 2),
        "weekly_run_rate": round(weekly_run_rate, 2),
        "avg_completion_time_hours": round(avg_completion_time, 1),
        "on_time_rate": round(on_time_rate, 1),
        "trend": trend,
        "lookback_days": lookback_days,
        "total_completions": total_completions
    }


def calculate_inventory_forecast(
    db: Session,
    milestone_type: MilestoneType,
    organization_id: int,
) -> Dict[str, Any]:
    """
    Calculate inventory forecast for a milestone type.

    Uses current inventory (active milestones) and run rate to forecast:
    - Days to clear current inventory
    - Expected completions this week
    - Projected bottlenecks
    """
    # Get current inventory (active milestones)
    active_milestones = db.query(LoanMilestoneHistory).filter(
        and_(
            LoanMilestoneHistory.organization_id == organization_id,
            LoanMilestoneHistory.milestone_type == milestone_type,
            LoanMilestoneHistory.status.in_([
                SLAStatus.IN_PROGRESS,
                SLAStatus.ON_TRACK,
                SLAStatus.AT_RISK,
                SLAStatus.OVERDUE
            ])
        )
    ).all()

    current_inventory = len(active_milestones)

    # Get run rate
    run_rate = calculate_run_rate(db, milestone_type, organization_id=organization_id, lookback_days=30)
    daily_rate = run_rate["daily_run_rate"]

    # Calculate forecasts
    if daily_rate > 0:
        days_to_clear = current_inventory / daily_rate
        expected_completions_week = min(daily_rate * 7, current_inventory)
    else:
        days_to_clear = float('inf') if current_inventory > 0 else 0
        expected_completions_week = 0

    # Count at-risk and overdue
    at_risk_count = sum(1 for m in active_milestones if m.status == SLAStatus.AT_RISK)
    overdue_count = sum(1 for m in active_milestones if m.status == SLAStatus.OVERDUE)

    # Calculate average time remaining to deadline
    now = datetime.now(timezone.utc)
    time_to_deadline = []
    for m in active_milestones:
        if m.target_deadline:
            hours_remaining = (m.target_deadline - now).total_seconds() / 3600
            time_to_deadline.append(hours_remaining)

    avg_hours_to_deadline = sum(time_to_deadline) / len(time_to_deadline) if time_to_deadline else 0

    # Determine if this is a bottleneck
    is_bottleneck = (
        current_inventory > 0 and
        (days_to_clear > 7 or overdue_count > current_inventory * 0.2 or at_risk_count > current_inventory * 0.3)
    )

    return {
        "milestone_type": milestone_type.value,
        "current_inventory": current_inventory,
        "at_risk_count": at_risk_count,
        "overdue_count": overdue_count,
        "daily_run_rate": daily_rate,
        "days_to_clear_inventory": round(days_to_clear, 1) if days_to_clear != float('inf') else None,
        "expected_completions_this_week": round(expected_completions_week, 1),
        "avg_hours_to_deadline": round(avg_hours_to_deadline, 1),
        "is_potential_bottleneck": is_bottleneck,
        "run_rate_trend": run_rate["trend"],
        "on_time_rate": run_rate["on_time_rate"]
    }


def generate_run_rate_report(organization_id: int) -> Dict[str, Any]:
    """
    Generate comprehensive run rate report for all milestone types.
    Includes forecasting based on current inventory.
    """
    try:
        logger.info("Generating run rate report...")

        with get_db_with_tenant(organization_id) as db:
            # Get all active SLA measures
            measures = get_all_sla_measures(db, organization_id=organization_id, active_only=True)
            milestone_types = list(set(m.milestone_type for m in measures))

            report = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "organization_id": organization_id,
                "milestone_run_rates": [],
                "inventory_forecasts": [],
                "bottlenecks": [],
                "summary": {}
            }

            total_inventory = 0
            total_at_risk = 0
            total_overdue = 0

            for mt in milestone_types:
                # Calculate run rate
                run_rate = calculate_run_rate(db, mt, organization_id=organization_id, lookback_days=30)
                report["milestone_run_rates"].append(run_rate)

                # Calculate inventory forecast
                forecast = calculate_inventory_forecast(db, mt, organization_id=organization_id)
                report["inventory_forecasts"].append(forecast)

                # Track bottlenecks
                if forecast["is_potential_bottleneck"]:
                    report["bottlenecks"].append({
                        "milestone_type": mt.value,
                        "inventory": forecast["current_inventory"],
                        "days_to_clear": forecast["days_to_clear_inventory"],
                        "overdue_count": forecast["overdue_count"],
                        "at_risk_count": forecast["at_risk_count"]
                    })

                # Aggregate totals
                total_inventory += forecast["current_inventory"]
                total_at_risk += forecast["at_risk_count"]
                total_overdue += forecast["overdue_count"]

            # Sort bottlenecks by severity (days to clear)
            report["bottlenecks"].sort(
                key=lambda x: x["days_to_clear"] if x["days_to_clear"] else float('inf'),
                reverse=True
            )

            # Summary
            report["summary"] = {
                "total_active_milestones": total_inventory,
                "total_at_risk": total_at_risk,
                "total_overdue": total_overdue,
                "bottleneck_count": len(report["bottlenecks"]),
                "health_score": calculate_health_score(total_inventory, total_at_risk, total_overdue)
            }

        logger.info(f"Run rate report generated: {report['summary']}")
        return report

    except Exception as e:
        logger.error(f"Error generating run rate report: {e}")
        return {"error": "Internal server error"}


def calculate_health_score(total: int, at_risk: int, overdue: int) -> int:
    """
    Calculate overall health score (0-100).
    100 = all on track, 0 = all overdue
    """
    if total == 0:
        return 100

    on_track = total - at_risk - overdue
    # Weight: on_track = 100%, at_risk = 50%, overdue = 0%
    score = ((on_track * 100) + (at_risk * 50) + (overdue * 0)) / total
    return round(score)


# ============================================================================
# Snapshot Task (8 AM and 12 PM)
# ============================================================================

def create_snapshot_with_run_rates(snapshot_time: str = "morning"):
    """
    Create performance snapshot including run rates and forecasts.

    Args:
        snapshot_time: "morning" (8 AM) or "midday" (12 PM)
    """
    db = None
    try:
        db = get_db_session()
        snapshot_date = date.today()

        logger.info(f"Creating {snapshot_time} snapshot for {snapshot_date}...")

        org_ids = get_all_org_ids(db)
        db.close()
        db = None

        all_org_results = {}

        for org_id in org_ids:
            try:
                with get_db_with_tenant(org_id) as tenant_db:
                    # Create org-level snapshot
                    org_snapshot = create_performance_snapshot(
                        tenant_db,
                        snapshot_date=snapshot_date,
                        scope_type="organization",
                        scope_id=None,
                        milestone_type=None,
                        period_type=f"intraday_{snapshot_time}",
                        organization_id=org_id
                    )
                    logger.info(f"Created org {org_id} snapshot: on_time_rate={org_snapshot.on_time_rate}%")

                    # Get all active milestone types
                    measures = get_all_sla_measures(tenant_db, organization_id=org_id, active_only=True)
                    milestone_types = list(set(m.milestone_type for m in measures))

                    # Create per-milestone-type snapshots with run rate data
                    snapshot_results = []
                    for mt in milestone_types:
                        try:
                            # Create performance snapshot
                            snapshot = create_performance_snapshot(
                                tenant_db,
                                snapshot_date=snapshot_date,
                                scope_type="organization",
                                scope_id=None,
                                milestone_type=mt,
                                period_type=f"intraday_{snapshot_time}",
                                organization_id=org_id
                            )

                            # Calculate run rate and forecast
                            run_rate = calculate_run_rate(tenant_db, mt, organization_id=org_id, lookback_days=30)
                            forecast = calculate_inventory_forecast(tenant_db, mt, organization_id=org_id)

                            snapshot_results.append({
                                "milestone_type": mt.value,
                                "snapshot_id": snapshot.id,
                                "on_time_rate": snapshot.on_time_rate,
                                "daily_run_rate": run_rate["daily_run_rate"],
                                "trend": run_rate["trend"],
                                "current_inventory": forecast["current_inventory"],
                                "days_to_clear": forecast["days_to_clear_inventory"],
                                "is_bottleneck": forecast["is_potential_bottleneck"]
                            })

                        except Exception as e:
                            logger.warning(f"Error creating snapshot for {mt} in org {org_id}: {e}")

                # generate_run_rate_report creates its own tenant-scoped session
                run_rate_report = generate_run_rate_report(organization_id=org_id)

                all_org_results[org_id] = {
                    "milestone_snapshots": snapshot_results,
                    "summary": run_rate_report.get("summary", {}),
                    "bottlenecks": run_rate_report.get("bottlenecks", [])
                }

            except Exception as e:
                logger.error(f"Error creating snapshots for org {org_id}: {e}")
                all_org_results[org_id] = {"error": str(e)}

        logger.info(f"{snapshot_time.capitalize()} snapshot creation complete for {len(org_ids)} orgs")
        return {
            "status": "success",
            "snapshot_time": snapshot_time,
            "date": str(snapshot_date),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "organizations": all_org_results
        }

    except Exception as e:
        logger.error(f"Error in {snapshot_time} snapshot task: {e}")
        return {"error": "Internal server error"}
    finally:
        if db:
            db.close()


def create_morning_snapshot_task():
    """8 AM snapshot with run rates and forecasting."""
    return create_snapshot_with_run_rates(snapshot_time="morning")


def create_midday_snapshot_task():
    """12 PM snapshot with run rates and forecasting."""
    return create_snapshot_with_run_rates(snapshot_time="midday")


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

        org_ids = get_all_org_ids(db)
        db.close()
        db = None

        all_reports = {}
        for org_id in org_ids:
            try:
                with get_db_with_tenant(org_id) as tenant_db:
                    report = create_efficiency_report(
                        tenant_db,
                        period_start=period_start,
                        period_end=period_end,
                        organization_id=org_id
                    )

                    logger.info(f"Weekly report generated for org {org_id}: compliance_rate={report.overall_sla_compliance_rate}%")
                    all_reports[org_id] = {
                        "report_id": report.id,
                        "compliance_rate": report.overall_sla_compliance_rate
                    }
            except Exception as e:
                logger.error(f"Error generating weekly report for org {org_id}: {e}")
                all_reports[org_id] = {"error": str(e)}

        return {
            "status": "success",
            "period_start": str(period_start),
            "period_end": str(period_end),
            "organizations": all_reports
        }

    except Exception as e:
        logger.error(f"Error in weekly report task: {e}")
        return {"error": "Internal server error"}
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

    # Create morning snapshot (for manual runs)
    results["snapshot"] = create_morning_snapshot_task()

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

    # Morning snapshot at 8 AM (with run rates and forecasting)
    scheduler.add_job(
        create_morning_snapshot_task,
        trigger=CronTrigger(hour=8, minute=0),
        id="sla_morning_snapshot",
        name="Create Morning SLA Snapshot (8 AM)",
        replace_existing=True
    )

    # Midday snapshot at 12 PM (with run rates and forecasting)
    scheduler.add_job(
        create_midday_snapshot_task,
        trigger=CronTrigger(hour=12, minute=0),
        id="sla_midday_snapshot",
        name="Create Midday SLA Snapshot (12 PM)",
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

    logger.info("SLA scheduler jobs configured: status updates (15min), alerts (hourly), snapshots (8am/12pm), weekly report (Mon 6am)")


# ============================================================================
# Data Retention & Backup Tasks (Domain 8: Disaster Recovery)
# ============================================================================

def run_retention_cleanup_task(dry_run: bool = False):
    """
    Celery task: Run automated data retention cleanup.

    Processes all organizations, deleting/redacting records past their
    retention period. Default schedule: Sunday 3:30 AM.

    Note: This is a cross-tenant admin operation. RLS context is not set
    because the service internally iterates over all organizations.
    """
    db = get_db_session()
    try:
        from services.data_retention import DataRetentionService

        service = DataRetentionService(db)
        result = service.run_retention_cleanup(dry_run=dry_run)
        logger.info(
            f"Retention cleanup: {result.get('total_records_affected', 0)} "
            f"records affected (dry_run={dry_run})"
        )
        return result
    except Exception as e:
        logger.error(f"Retention cleanup task failed: {e}")
        return {"error": str(e)}
    finally:
        db.close()


def verify_backup_task():
    """
    Celery task: Verify backup integrity and RPO compliance.

    Runs daily backup verification and records results for audit.
    Default schedule: daily 5 AM.

    Note: This is a cross-tenant infrastructure operation. RLS context
    is not set because backup verification is not tenant-scoped.
    """
    db = get_db_session()
    try:
        from services.backup_service import BackupVerificationService

        service = BackupVerificationService(db)
        backup_status = service.verify_latest_backup()
        integrity = service.verify_backup_integrity()
        service.record_verification(backup_status, integrity)

        is_compliant = backup_status.get("rpo_compliant", False)
        logger.info(
            f"Backup verification: status={backup_status.get('status')}, "
            f"RPO compliant={is_compliant}"
        )
        return {"status": backup_status.get("status"), "rpo_compliant": is_compliant}
    except Exception as e:
        logger.error(f"Backup verification task failed: {e}")
        return {"error": str(e)}
    finally:
        db.close()
