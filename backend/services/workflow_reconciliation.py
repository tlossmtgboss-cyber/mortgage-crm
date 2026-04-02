"""
Workflow Reconciliation Service

After external actions (Aria autonomous tasks, Call Intelligence artifact execution),
reconcile with active workflow_task_instances to prevent duplicate outreach and
keep SLA tracking accurate.

The problem: When Aria executes an autonomous action (send SMS, create task, send email),
it creates standalone records without checking or completing matching workflow_task_instances.
This means SLA timers, sibling cancellation, and escalation chains are all bypassed.

This service bridges that gap by searching for matching active workflow_task_instances
and marking them completed after any external action completes.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Map external action types to workflow task communication methods.
# WorkflowTaskInstance uses both `task_type` (SLA mixin enum) and
# `communication_method` (legacy CommunicationMethod enum). We match on
# `task_type` first (the SLA system's column), then fall back to
# `communication_method` as text comparison for legacy rows.
ACTION_TYPE_TO_TASK_TYPES: Dict[str, List[str]] = {
    "sms": ["text", "text_am", "text_pm"],
    "email": ["email"],
    "call": ["phone", "phone_am", "phone_pm"],
    "task": ["manual"],
}

# Legacy communication_method enum values (from workflow_config_models.CommunicationMethod)
ACTION_TYPE_TO_COMM_METHODS: Dict[str, List[str]] = {
    "sms": ["TEXT", "text"],
    "email": ["EMAIL", "email"],
    "call": ["PHONE", "phone"],
    "task": [],
}


async def reconcile_after_action(
    db: Session,
    action_type: str,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    completed_by: Optional[str] = None,
    completion_source: str = "aria_autonomous",
) -> Dict[str, Any]:
    """
    Reconcile workflow task instances after an external action completes.

    Searches for active workflow_task_instances that match the action just
    performed, marks them completed, cancels sibling tasks in the same group,
    and updates linked tasks in the tasks table.

    Args:
        db: SQLAlchemy session (already open from the calling endpoint)
        action_type: Type of action performed ('sms', 'email', 'call', 'task')
        lead_id: Lead ID the action was performed for (optional)
        loan_id: Loan ID the action was performed for (optional)
        completed_by: User ID string of who completed the action (optional)
        completion_source: Source label for audit trail (default: 'aria_autonomous')

    Returns:
        Dict with reconciliation results:
        {
            "reconciled_count": int,
            "siblings_cancelled": int,
            "linked_tasks_completed": int,
            "task_ids": List[int],
        }
    """
    if not lead_id and not loan_id:
        logger.debug("Workflow reconciliation skipped: no lead_id or loan_id provided")
        return {
            "reconciled_count": 0,
            "siblings_cancelled": 0,
            "linked_tasks_completed": 0,
            "task_ids": [],
        }

    task_types = ACTION_TYPE_TO_TASK_TYPES.get(action_type, [])
    comm_methods = ACTION_TYPE_TO_COMM_METHODS.get(action_type, [])

    if not task_types and not comm_methods:
        logger.debug(f"Workflow reconciliation skipped: unknown action_type '{action_type}'")
        return {
            "reconciled_count": 0,
            "siblings_cancelled": 0,
            "linked_tasks_completed": 0,
            "task_ids": [],
        }

    # --- Step 1: Find matching active workflow_task_instances ---
    matching_instances = _find_matching_task_instances(
        db=db,
        task_types=task_types,
        comm_methods=comm_methods,
        lead_id=lead_id,
        loan_id=loan_id,
    )

    if not matching_instances:
        logger.debug(
            f"Workflow reconciliation: no matching task instances for "
            f"action_type={action_type}, lead_id={lead_id}, loan_id={loan_id}"
        )
        return {
            "reconciled_count": 0,
            "siblings_cancelled": 0,
            "linked_tasks_completed": 0,
            "task_ids": [],
        }

    # --- Step 2: Complete each matching instance ---
    reconciled_ids = []
    total_siblings_cancelled = 0
    total_linked_completed = 0

    completed_by_int = None
    if completed_by:
        try:
            completed_by_int = int(completed_by)
        except (ValueError, TypeError):
            pass

    for instance in matching_instances:
        instance_id = instance["id"]
        task_group_key = instance.get("task_group_key")
        linked_task_id = instance.get("linked_task_id")

        # Mark the workflow task instance as completed
        _complete_task_instance(
            db=db,
            instance_id=instance_id,
            completion_source=completion_source,
            completed_by_id=completed_by_int,
        )
        reconciled_ids.append(instance_id)

        # Update linked task in the tasks table if one exists
        if linked_task_id:
            linked_count = _complete_linked_task(db=db, linked_task_id=linked_task_id)
            total_linked_completed += linked_count

        # Cancel sibling tasks in the same task_group_key
        if task_group_key:
            siblings = _cancel_sibling_tasks(
                db=db,
                task_group_key=task_group_key,
                exclude_task_id=instance_id,
                reason=f"Contact made via {completion_source} ({action_type})",
            )
            total_siblings_cancelled += siblings

    # Commit all changes in one transaction
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Workflow reconciliation commit failed: {e}")
        raise

    logger.info(
        f"Workflow reconciliation complete: "
        f"reconciled={len(reconciled_ids)}, "
        f"siblings_cancelled={total_siblings_cancelled}, "
        f"linked_tasks_completed={total_linked_completed}, "
        f"source={completion_source}, action={action_type}"
    )

    return {
        "reconciled_count": len(reconciled_ids),
        "siblings_cancelled": total_siblings_cancelled,
        "linked_tasks_completed": total_linked_completed,
        "task_ids": reconciled_ids,
    }


def _find_matching_task_instances(
    db: Session,
    task_types: List[str],
    comm_methods: List[str],
    lead_id: Optional[int],
    loan_id: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Find active workflow_task_instances matching the action type and entity.

    Matches on:
    - task_type (SLA system column) OR communication_method (legacy column)
    - lead_id (direct on instance) or via joined workflow_instances
    - loan_id (direct on instance) or via joined workflow_instances
    - Status must be in ('scheduled', 'pending', 'in_progress')

    Returns list of dicts with id, task_group_key, linked_task_id.
    """
    # Build entity filter: match lead_id or loan_id on the task instance directly,
    # or on the parent workflow_instance (some task instances only have the reference
    # on the workflow_instance, not duplicated on the task).
    entity_conditions = []
    params: Dict[str, Any] = {}

    if lead_id:
        entity_conditions.append(
            "(wti.lead_id = :lead_id OR wi.lead_id = :lead_id)"
        )
        params["lead_id"] = lead_id

    if loan_id:
        entity_conditions.append(
            "(wti.loan_id = :loan_id OR wi.loan_id = :loan_id)"
        )
        params["loan_id"] = loan_id

    if not entity_conditions:
        return []

    entity_filter = " OR ".join(entity_conditions)

    # Build type filter: match task_type (VARCHAR or enum) or communication_method
    type_conditions = []

    if task_types:
        # task_type column may be an enum or text; cast to text for safe comparison
        type_placeholders = ", ".join(f":tt_{i}" for i in range(len(task_types)))
        type_conditions.append(f"CAST(wti.task_type AS TEXT) IN ({type_placeholders})")
        for i, tt in enumerate(task_types):
            params[f"tt_{i}"] = tt

    if comm_methods:
        cm_placeholders = ", ".join(f":cm_{i}" for i in range(len(comm_methods)))
        type_conditions.append(f"CAST(wti.communication_method AS TEXT) IN ({cm_placeholders})")
        for i, cm in enumerate(comm_methods):
            params[f"cm_{i}"] = cm

    type_filter = " OR ".join(type_conditions) if type_conditions else "FALSE"

    query = f"""
        SELECT
            wti.id,
            wti.task_group_key,
            wti.linked_task_id
        FROM workflow_task_instances wti
        LEFT JOIN workflow_instances wi ON wi.id = wti.workflow_instance_id
        WHERE wti.status IN ('scheduled', 'pending', 'in_progress')
        AND ({entity_filter})
        AND ({type_filter})
        ORDER BY wti.scheduled_date ASC NULLS LAST
    """

    try:
        rows = db.execute(text(query), params).fetchall()
        return [
            {
                "id": row[0],
                "task_group_key": row[1],
                "linked_task_id": row[2],
            }
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Workflow reconciliation query failed: {e}")
        return []


def _complete_task_instance(
    db: Session,
    instance_id: int,
    completion_source: str,
    completed_by_id: Optional[int],
) -> None:
    """Mark a single workflow_task_instance as completed."""
    params: Dict[str, Any] = {
        "id": instance_id,
        "source": completion_source,
    }

    completed_by_clause = ""
    if completed_by_id is not None:
        completed_by_clause = ", completed_by_id = :completed_by_id"
        params["completed_by_id"] = completed_by_id

    complete_query = (
        "UPDATE workflow_task_instances"
        " SET status = 'completed',"
        "     completion_source = :source,"
        "     completed_at = NOW(),"
        "     updated_at = NOW()"
        + completed_by_clause
        + " WHERE id = :id"
        " AND status IN ('scheduled', 'pending', 'in_progress')"
    )
    db.execute(text(complete_query), params)


def _complete_linked_task(db: Session, linked_task_id: int) -> int:
    """Complete the linked task in the tasks table. Returns count of rows updated."""
    result = db.execute(text("""
        UPDATE tasks
        SET status = 'completed',
            completed_at = NOW(),
            updated_at = NOW()
        WHERE id = :task_id
        AND status NOT IN ('completed', 'cancelled')
    """), {"task_id": linked_task_id})
    return result.rowcount


def _cancel_sibling_tasks(
    db: Session,
    task_group_key: str,
    exclude_task_id: int,
    reason: str,
) -> int:
    """
    Cancel sibling tasks in the same task_group_key.

    This prevents duplicate outreach: if Aria already sent an SMS to a lead,
    the scheduled phone call and email in the same day-group should be cancelled.

    Returns count of siblings cancelled.
    """
    # Cancel workflow_task_instances siblings
    result = db.execute(text("""
        UPDATE workflow_task_instances
        SET status = 'cancelled',
            error_message = :reason,
            updated_at = NOW()
        WHERE task_group_key = :group_key
        AND id != :exclude_id
        AND status IN ('scheduled', 'pending', 'in_progress')
    """), {
        "group_key": task_group_key,
        "exclude_id": exclude_task_id,
        "reason": reason,
    })
    siblings_cancelled = result.rowcount

    # Also cancel linked tasks in the tasks table for those siblings
    if siblings_cancelled > 0:
        db.execute(text("""
            UPDATE tasks
            SET status = 'cancelled',
                description = COALESCE(description, '') || E'\n[Cancelled: ' || :reason || ']',
                updated_at = NOW()
            WHERE workflow_task_instance_id IN (
                SELECT id FROM workflow_task_instances
                WHERE task_group_key = :group_key
                AND id != :exclude_id
                AND status = 'cancelled'
            )
            AND status NOT IN ('completed', 'cancelled')
        """), {
            "group_key": task_group_key,
            "exclude_id": exclude_task_id,
            "reason": reason,
        })

    return siblings_cancelled
