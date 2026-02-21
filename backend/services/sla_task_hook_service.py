"""
SLA Task Hook Service

Event-driven SLA task creation that fires when loan dates or status change.
Designed for scale with non-blocking background processing.

Integration points:
- Called from loan update endpoint after commit
- Runs via asyncio.create_task() for non-blocking execution
- Also supports batch processing via scheduled job

Key design principles:
- Idempotent: Won't create duplicate tasks for same milestone
- Non-blocking: Uses async/await for database operations
- Scalable: Processes one loan at a time, can be parallelized
"""

import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# =============================================================================
# SLA MILESTONE TRIGGER MAPPING
# =============================================================================

# Maps loan date fields to the SLA milestones they should trigger
SLA_TRIGGER_MAP = {
    # When application_date is set, create these milestones
    "application_date": [
        "initial_disclosure",      # LE within 3 business days
        "appraisal_order",         # Order appraisal within 5 days
        "title_order",             # Order title within 3 days
        "submit_to_underwriting",  # Submit to UW within 7 days
    ],

    # When loan is submitted to underwriting
    "uw_received_date": [
        "initial_uw_decision",     # UW decision within 3 days
    ],

    # When conditions are received
    "conditions_for_review_date": [
        "conditions_review",       # Clear conditions within 2 days
    ],

    # When loan is approved
    "loan_approved_date": [
        "clear_to_close",          # Get CTC within 2 days
    ],

    # When clear to close
    "clear_to_close_date": [
        "closing_scheduled",       # Schedule closing within 1 day
    ],

    # When closing date is scheduled
    "scheduled_closing_date": [
        "closing_disclosure",      # CD 3 days before closing
        "docs_to_title",           # Docs 2 days before closing
    ],

    # When loan closes
    "funded_date": [
        "welcome_call",            # Welcome call within 1 day
    ],
}

# Stage-based triggers (when loan moves to a stage)
STAGE_TRIGGER_MAP = {
    "DISCLOSED": ["initial_disclosure"],
    "PROCESSING": ["submit_to_underwriting", "appraisal_order", "title_order"],
    "SUBMITTED": ["initial_uw_decision"],
    "CONDITIONAL": ["conditions_review"],
    "CTC": ["closing_scheduled", "closing_disclosure"],
    "FUNDED": ["welcome_call"],
}


# =============================================================================
# SLA TASK HOOK SERVICE
# =============================================================================

class SLATaskHookService:
    """
    Service for event-driven SLA task creation.

    Usage:
        # In loan update endpoint, after db.commit():
        asyncio.create_task(
            SLATaskHookService.on_loan_updated(
                loan_id=loan.id,
                changed_fields=changed_fields,
                user_id=current_user.id
            )
        )
    """

    @staticmethod
    async def on_loan_updated(
        loan_id: int,
        changed_fields: Set[str],
        user_id: int,
        old_stage: str = None,
        new_stage: str = None,
    ) -> Dict[str, Any]:
        """
        Handle loan update event - create SLA tasks for changed date fields.

        Args:
            loan_id: ID of the updated loan
            changed_fields: Set of field names that were changed
            user_id: ID of user who made the change (for task assignment)
            old_stage: Previous loan stage (if stage changed)
            new_stage: New loan stage (if stage changed)

        Returns:
            Dict with results of task creation
        """
        from database import SessionLocal

        db = None
        try:
            db = SessionLocal()
            results = {
                "loan_id": loan_id,
                "tasks_created": [],
                "tasks_skipped": [],
                "errors": [],
            }

            # Collect all milestones to create based on changed fields
            milestones_to_create = set()

            # Check date field triggers
            for field in changed_fields:
                if field in SLA_TRIGGER_MAP:
                    milestones_to_create.update(SLA_TRIGGER_MAP[field])
                    logger.info(f"Field {field} changed - triggering milestones: {SLA_TRIGGER_MAP[field]}")

            # Check stage change triggers
            if new_stage and old_stage != new_stage:
                stage_milestones = STAGE_TRIGGER_MAP.get(new_stage, [])
                milestones_to_create.update(stage_milestones)
                logger.info(f"Stage changed to {new_stage} - triggering milestones: {stage_milestones}")

            if not milestones_to_create:
                logger.debug(f"No SLA milestones to create for loan {loan_id}")
                return results

            # Get loan owner for task assignment
            loan = db.execute(text("""
                SELECT loan_officer_id FROM loans WHERE id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            owner_id = loan[0] if loan and loan[0] else user_id

            # Create tasks for each milestone (if not already exists)
            from services.task_sla_bridge_service import get_task_sla_bridge_service
            sla_service = get_task_sla_bridge_service(db)

            for milestone_type in milestones_to_create:
                # Check if task already exists for this milestone
                existing = db.execute(text("""
                    SELECT id FROM tasks
                    WHERE loan_id = :loan_id
                    AND sla_milestone_type = :milestone_type
                    AND status NOT IN ('completed', 'cancelled')
                """), {"loan_id": loan_id, "milestone_type": milestone_type}).fetchone()

                if existing:
                    results["tasks_skipped"].append({
                        "milestone_type": milestone_type,
                        "reason": "Task already exists",
                        "existing_task_id": existing[0],
                    })
                    continue

                # Skip if active workflow tasks exist for this loan
                active_wf = db.execute(text("""
                    SELECT COUNT(*) FROM workflow_task_instances wti
                    JOIN workflow_instances wi ON wi.id = wti.workflow_instance_id
                    WHERE wti.loan_id = :loan_id
                    AND wti.status IN ('scheduled', 'pending', 'in_progress')
                    AND wi.status = 'active'
                """), {"loan_id": loan_id}).scalar()

                if active_wf and active_wf > 0:
                    results["tasks_skipped"].append({
                        "milestone_type": milestone_type,
                        "reason": f"Active workflow has {active_wf} pending tasks",
                    })
                    continue

                # Create the SLA task
                try:
                    result = sla_service.create_sla_task(
                        loan_id=loan_id,
                        milestone_type=milestone_type,
                        owner_id=owner_id,
                    )

                    if result.get("success"):
                        results["tasks_created"].append({
                            "milestone_type": milestone_type,
                            "task_id": result.get("task_id"),
                            "sla_status": result.get("sla_status"),
                        })
                        logger.info(f"Created SLA task {result.get('task_id')} for {milestone_type}")
                    else:
                        results["tasks_skipped"].append({
                            "milestone_type": milestone_type,
                            "reason": result.get("error", "Unknown error"),
                        })

                except Exception as e:
                    results["errors"].append({
                        "milestone_type": milestone_type,
                        "error": "Internal server error",
                    })
                    logger.error(f"Error creating SLA task for {milestone_type}: {e}")

            logger.info(f"SLA hook completed for loan {loan_id}: "
                       f"{len(results['tasks_created'])} created, "
                       f"{len(results['tasks_skipped'])} skipped")

            return results

        except Exception as e:
            logger.error(f"Error in SLA task hook for loan {loan_id}: {e}")
            return {"error": "Internal server error", "loan_id": loan_id}
        finally:
            if db:
                db.close()

    @staticmethod
    async def create_initial_sla_tasks(
        loan_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """
        Create all applicable SLA tasks for a new loan.
        Called when a loan is first created.
        """
        from database import SessionLocal

        db = None
        try:
            db = SessionLocal()

            from services.task_sla_bridge_service import get_task_sla_bridge_service
            sla_service = get_task_sla_bridge_service(db)

            # Get loan owner
            loan = db.execute(text("""
                SELECT loan_officer_id FROM loans WHERE id = :loan_id
            """), {"loan_id": loan_id}).fetchone()

            owner_id = loan[0] if loan and loan[0] else user_id

            # Create all applicable SLA tasks
            result = sla_service.create_loan_sla_tasks(
                loan_id=loan_id,
                owner_id=owner_id,
            )

            logger.info(f"Initial SLA tasks created for loan {loan_id}: {result}")
            return result

        except SQLAlchemyError as e:
            logger.error(f"Error creating initial SLA tasks for loan {loan_id}: {e}")
            return {"error": "Internal server error", "loan_id": loan_id}
        finally:
            if db:
                db.close()


# =============================================================================
# BATCH PROCESSING FOR EXISTING LOANS
# =============================================================================

async def backfill_sla_tasks_batch(
    limit: int = 100,
    organization_id: int = 1,
) -> Dict[str, Any]:
    """
    Batch job to create SLA tasks for existing loans that don't have them.
    Run this as a one-time migration or scheduled cleanup job.

    Args:
        limit: Maximum loans to process per batch
        organization_id: Organization to process

    Returns:
        Dict with batch processing results
    """
    from database import SessionLocal

    db = None
    try:
        db = SessionLocal()

        # Find loans that have application_date but no SLA tasks
        loans_needing_tasks = db.execute(text("""
            SELECT DISTINCT l.id, l.loan_officer_id
            FROM loans l
            LEFT JOIN tasks t ON t.loan_id = l.id AND t.sla_milestone_type IS NOT NULL
            WHERE l.application_date IS NOT NULL
            AND l.stage NOT IN ('Funded')
            AND t.id IS NULL
            LIMIT :limit
        """), {"limit": limit}).fetchall()

        results = {
            "loans_processed": 0,
            "tasks_created": 0,
            "errors": [],
        }

        for loan_id, loan_officer_id in loans_needing_tasks:
            try:
                owner_id = loan_officer_id or 1

                from services.task_sla_bridge_service import get_task_sla_bridge_service
                sla_service = get_task_sla_bridge_service(db)

                result = sla_service.create_loan_sla_tasks(
                    loan_id=loan_id,
                    owner_id=owner_id,
                )

                results["loans_processed"] += 1
                results["tasks_created"] += result.get("total_created", 0)

            except Exception as e:
                results["errors"].append({
                    "loan_id": loan_id,
                    "error": "Internal server error",
                })

        logger.info(f"SLA backfill batch complete: {results}")
        return results

    except Exception as e:
        logger.error(f"Error in SLA backfill batch: {e}")
        return {"error": "Internal server error"}
    finally:
        if db:
            db.close()


def sync_backfill_sla_tasks_batch(limit: int = 100) -> Dict[str, Any]:
    """Synchronous wrapper for use with APScheduler."""
    return asyncio.run(backfill_sla_tasks_batch(limit=limit))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_changed_sla_fields(old_values: Dict, new_values: Dict) -> Set[str]:
    """
    Compare old and new values to determine which SLA-triggering fields changed.

    Args:
        old_values: Dict of field names to old values
        new_values: Dict of field names to new values

    Returns:
        Set of field names that changed and are SLA triggers
    """
    changed = set()

    sla_fields = set(SLA_TRIGGER_MAP.keys())

    for field in sla_fields:
        old_val = old_values.get(field)
        new_val = new_values.get(field)

        # Field changed from None to a value (newly set)
        if old_val is None and new_val is not None:
            changed.add(field)
        # Field changed from one value to another
        elif old_val != new_val and new_val is not None:
            changed.add(field)

    return changed


# =============================================================================
# SCHEDULER INTEGRATION
# =============================================================================

def setup_sla_task_hook_scheduler(scheduler):
    """
    Add SLA task backfill job to the scheduler.
    Runs daily to catch any loans that might have been missed.

    Args:
        scheduler: APScheduler instance
    """
    from apscheduler.triggers.cron import CronTrigger

    # Daily backfill at 2 AM (low traffic time)
    scheduler.add_job(
        sync_backfill_sla_tasks_batch,
        trigger=CronTrigger(hour=2, minute=0),
        id="sla_task_backfill",
        name="Backfill SLA Tasks for Loans",
        replace_existing=True,
        kwargs={"limit": 100},
    )

    logger.info("SLA task hook scheduler configured: backfill job at 2 AM daily")
