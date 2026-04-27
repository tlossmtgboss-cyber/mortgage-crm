"""
Ops Manager Background Tasks

Scheduled jobs for:
- Daily pipeline sweep across all active organizations (6:00 AM ET)
- Auto-resolve stale tasks (every 4 hours)

The sweep detects impediments (SLA breaches, lock expirations, doc issues,
staffing gaps, stalled files, etc.) and creates corrective ai_tasks for
loan officers — without requiring manual admin intervention.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database import SessionLocal
import database.models  # noqa: F401 — ensure all mappers register
from database.models.core import Organization

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB helpers (same pattern as sla_tasks.py)
# ---------------------------------------------------------------------------

def _get_db_session() -> Session:
    """Create a new database session for background tasks."""
    return SessionLocal()


def _get_all_active_org_ids(db: Session) -> list:
    """Get all active organization IDs."""
    try:
        org_ids = [
            row[0] for row in
            db.query(Organization.id).filter(Organization.is_active == True).all()
        ]
        if not org_ids:
            org_ids = [row[0] for row in db.query(Organization.id).all()]
        return org_ids
    except Exception as e:
        logger.warning("Error querying organizations, falling back to org_id=1: %s", e)
        return [1]


# ---------------------------------------------------------------------------
# Async sweep logic (agent.execute_tool is async)
# ---------------------------------------------------------------------------

async def _sweep_org(org_id: int, dry_run: bool = False) -> dict:
    """Run pipeline sweep for a single org using OpsManagerAgent.
    Uses tenant-scoped session to enforce RLS."""
    from agents.specialized.ops_manager_agent import OpsManagerAgent
    from database import get_db_with_tenant

    try:
        with get_db_with_tenant(org_id) as db:
            context = {
                "user_id": "system",
                "user_email": "ops-scheduler@system",
                "user_role": "system_admin",
                "_shared_db": db,
            }
            agent = OpsManagerAgent(context)
            result = await agent.execute_tool("run_pipeline_sweep", {
                "organization_id": org_id,
                "dry_run": dry_run,
            })
            return {
                "organization_id": org_id,
                "status": "success" if result.success else "error",
                "impediments_found": (result.data or {}).get("impediments_found", 0),
                "tasks_created": (result.data or {}).get("tasks_created", 0),
                "error": result.error,
            }
    except Exception as e:
        logger.error("Sweep failed for org %d: %s", org_id, e)
        return {
            "organization_id": org_id,
            "status": "error",
            "error": str(e),
        }


async def _sweep_all_orgs_async(dry_run: bool = False) -> dict:
    """Sweep all active organizations sequentially."""
    db = _get_db_session()
    try:
        org_ids = _get_all_active_org_ids(db)
    finally:
        db.close()

    logger.info("Ops Manager scheduled sweep starting for %d orgs", len(org_ids))
    results = []

    for org_id in org_ids:
        result = await _sweep_org(org_id, dry_run=dry_run)
        results.append(result)
        if result["status"] == "success":
            logger.info(
                "Org %d sweep: %d impediments, %d tasks created",
                org_id,
                result.get("impediments_found", 0),
                result.get("tasks_created", 0),
            )

    total_impediments = sum(r.get("impediments_found", 0) for r in results)
    total_tasks = sum(r.get("tasks_created", 0) for r in results)
    errors = [r for r in results if r["status"] == "error"]

    summary = {
        "organizations_swept": len(results),
        "total_impediments": total_impediments,
        "total_tasks_created": total_tasks,
        "errors": len(errors),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "Ops Manager sweep complete: %d orgs, %d impediments, %d tasks, %d errors",
        len(results), total_impediments, total_tasks, len(errors),
    )
    return summary


# ---------------------------------------------------------------------------
# Sync wrappers (APScheduler BackgroundScheduler calls sync functions)
# ---------------------------------------------------------------------------

def run_daily_ops_sweep():
    """
    Daily pipeline sweep across all active organizations.
    Scheduled via APScheduler CronTrigger (6:00 AM ET).
    """
    logger.info("=== Ops Manager daily sweep starting ===")
    try:
        result = asyncio.run(_sweep_all_orgs_async(dry_run=False))
        logger.info("=== Ops Manager daily sweep finished: %s ===", result)
        return result
    except Exception as e:
        logger.exception("Ops Manager daily sweep failed: %s", e)
        return {"error": str(e)}


def run_auto_resolve_stale_tasks():
    """
    Auto-resolve stale ops manager tasks that are past their expiry.
    Runs every 4 hours to keep the priority queue clean.
    """
    from sqlalchemy import text

    db = None
    try:
        db = _get_db_session()
        org_ids = _get_all_active_org_ids(db)
        db.close()
        db = None

        from database import get_db_with_tenant

        total_resolved = 0
        for org_id in org_ids:
            try:
                with get_db_with_tenant(org_id) as org_db:
                    # Auto-resolve ai_tasks created by ops_manager that are > 7 days old
                    # and still in a non-terminal state
                    result = org_db.execute(text("""
                        UPDATE ai_tasks
                        SET type = 'COMPLETED',
                            description = description || ' [Auto-resolved: stale after 7 days]',
                            updated_at = NOW()
                        WHERE organization_id = :org_id
                          AND source = 'ops_manager'
                          AND type != 'COMPLETED'
                          AND created_at < NOW() - INTERVAL '7 days'
                    """), {"org_id": org_id})
                    org_db.commit()
                    count = result.rowcount
                    if count > 0:
                        logger.info("Auto-resolved %d stale ops tasks for org %d", count, org_id)
                    total_resolved += count
            except Exception as e:
                logger.error("Auto-resolve failed for org %d: %s", org_id, e)

        if total_resolved > 0:
            logger.info("Auto-resolve complete: %d total tasks resolved", total_resolved)
        return {"total_resolved": total_resolved}

    except Exception as e:
        logger.exception("Auto-resolve stale tasks failed: %s", e)
        return {"error": str(e)}
    finally:
        if db:
            db.close()


# ---------------------------------------------------------------------------
# Scheduler registration
# ---------------------------------------------------------------------------

def setup_ops_manager_scheduler(scheduler):
    """
    Register ops manager background jobs with APScheduler.
    Called from inline_legacy_routes.py during app startup.
    """
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    # Daily pipeline sweep at 6:00 AM Eastern
    scheduler.add_job(
        run_daily_ops_sweep,
        trigger=CronTrigger(hour=6, minute=0, timezone="America/New_York"),
        id="ops_manager_daily_sweep",
        name="Ops Manager: Daily pipeline sweep across all orgs",
        replace_existing=True,
    )

    # Auto-resolve stale tasks every 4 hours
    scheduler.add_job(
        run_auto_resolve_stale_tasks,
        trigger=IntervalTrigger(hours=4),
        id="ops_manager_auto_resolve",
        name="Ops Manager: Auto-resolve stale tasks",
        replace_existing=True,
    )

    logger.info("Ops Manager scheduler jobs registered (daily sweep @ 6 AM ET, auto-resolve every 4h)")
