"""
Mobile Tasks Routes

GET   /api/v1/mobile/tasks              — List tasks from the `tasks` table for the current user
GET   /api/v1/mobile/tasks/summary      — Task count summaries for the mobile dashboard
PATCH /api/v1/mobile/tasks/{id}         — Update a task (status, priority, title, due_date)
PATCH /api/v1/mobile/tasks/{id}/snooze  — Snooze a task (push due_date forward)

These endpoints query the real `tasks` table (NOT `ai_tasks`) and support
status filtering, overdue detection, and optional workflow metadata via
LEFT JOIN on workflow_task_instances.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import require_auth, current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/mobile",
    tags=["Mobile Tasks"],
    dependencies=[Depends(require_auth)],
)


class SnoozeRequest(BaseModel):
    """Request body for task snooze endpoint.

    The frontend sends snooze_until as an ISO 8601 datetime string.
    If omitted, defaults to 1 hour from now.
    """
    snooze_until: Optional[str] = None
    duration_minutes: Optional[int] = None


@router.get("/tasks")
async def get_mobile_tasks(
    status: str = Query(default=None, description="Filter: pending, in_progress, completed, overdue"),
    limit: int = Query(default=50, ge=1, le=200),
    include_workflow: bool = Query(default=False, description="Include workflow_task_instances metadata"),
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Return tasks from the `tasks` table for the authenticated user.

    Supports filtering by status (including virtual 'overdue' status).
    Optionally LEFT JOINs workflow_task_instances for escalation_level
    and health_status when include_workflow=true.
    """
    user_id = current_user.id
    now = datetime.now(timezone.utc)
    params: dict = {"user_id": user_id, "limit": limit, "now": now}

    # Build WHERE clauses
    where_clauses = ["t.owner_id = :user_id"]

    if status == "overdue":
        # Overdue = still pending but past due_date
        where_clauses.append("t.status = 'pending'")
        where_clauses.append("t.due_date < :now")
    elif status in ("pending", "in_progress", "completed"):
        where_clauses.append("t.status = :status")
        params["status"] = status

    where_sql = " AND ".join(where_clauses)

    # Build SELECT and optional JOIN
    if include_workflow:
        select_cols = """
            t.id, t.title, t.description, t.status, t.priority,
            t.due_date, t.lead_id, t.loan_id, t.completed_at,
            t.related_contact_name, t.related_type,
            t.sla_milestone_type, t.task_group_key,
            t.created_at, t.updated_at,
            wti.escalation_level AS wf_escalation_level,
            wti.health_status AS wf_health_status,
            wti.task_name AS wf_task_name
        """
        join_sql = """
            LEFT JOIN workflow_task_instances wti
                ON wti.id = t.workflow_task_instance_id
        """
    else:
        select_cols = """
            t.id, t.title, t.description, t.status, t.priority,
            t.due_date, t.lead_id, t.loan_id, t.completed_at,
            t.related_contact_name, t.related_type,
            t.sla_milestone_type, t.task_group_key,
            t.created_at, t.updated_at
        """
        join_sql = ""

    query = f"""
        SELECT {select_cols}
        FROM tasks t
        {join_sql}
        WHERE {where_sql}
        ORDER BY
            CASE t.priority
                WHEN 'high' THEN 0
                WHEN 'medium' THEN 1
                WHEN 'low' THEN 2
                ELSE 3
            END,
            t.due_date ASC NULLS LAST
        LIMIT :limit
    """

    try:
        rows = db.execute(text(query), params).fetchall()
    except Exception:
        rows = []

    tasks = []
    for row in rows:
        row_dict = dict(row._mapping)

        # Compute is_overdue flag
        due = row_dict.get("due_date")
        is_overdue = (
            due is not None
            and row_dict.get("status") == "pending"
            and due < now
        )

        task = {
            "id": row_dict["id"],
            "title": row_dict["title"],
            "description": row_dict.get("description"),
            "status": row_dict["status"],
            "priority": row_dict.get("priority", "medium"),
            "due_date": row_dict["due_date"].isoformat() if row_dict.get("due_date") else None,
            "lead_id": row_dict.get("lead_id"),
            "loan_id": row_dict.get("loan_id"),
            "completed_at": row_dict["completed_at"].isoformat() if row_dict.get("completed_at") else None,
            "related_contact_name": row_dict.get("related_contact_name"),
            "related_type": row_dict.get("related_type"),
            "sla_milestone_type": row_dict.get("sla_milestone_type"),
            "task_group_key": row_dict.get("task_group_key"),
            "is_overdue": is_overdue,
            "created_at": row_dict["created_at"].isoformat() if row_dict.get("created_at") else None,
            "updated_at": row_dict["updated_at"].isoformat() if row_dict.get("updated_at") else None,
        }

        if include_workflow:
            task["workflow"] = {
                "escalation_level": row_dict.get("wf_escalation_level"),
                "health_status": str(row_dict["wf_health_status"]) if row_dict.get("wf_health_status") else None,
                "task_name": row_dict.get("wf_task_name"),
            }

        tasks.append(task)

    return {
        "tasks": tasks,
        "count": len(tasks),
        "filter": status or "all",
    }


@router.get("/tasks/summary")
async def get_mobile_tasks_summary(
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Return task count summaries for the mobile dashboard.

    Counts: pending, overdue, in_progress, completed_today, total_active.
    """
    user_id = current_user.id
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    params = {"user_id": user_id, "now": now, "today_start": today_start}

    summary_sql = """
        SELECT
            COUNT(*) FILTER (WHERE t.status = 'pending' AND (t.due_date IS NULL OR t.due_date >= :now))
                AS pending,
            COUNT(*) FILTER (WHERE t.status = 'pending' AND t.due_date < :now)
                AS overdue,
            COUNT(*) FILTER (WHERE t.status = 'in_progress')
                AS in_progress,
            COUNT(*) FILTER (WHERE t.status = 'completed' AND t.completed_at >= :today_start)
                AS completed_today,
            COUNT(*) FILTER (WHERE t.status IN ('pending', 'in_progress'))
                AS total_active
        FROM tasks t
        WHERE t.owner_id = :user_id
    """

    try:
        row = db.execute(text(summary_sql), params).fetchone()
    except Exception:
        row = None

    if row:
        row_dict = dict(row._mapping)
        return {
            "pending": row_dict.get("pending", 0) or 0,
            "overdue": row_dict.get("overdue", 0) or 0,
            "in_progress": row_dict.get("in_progress", 0) or 0,
            "completed_today": row_dict.get("completed_today", 0) or 0,
            "total_active": row_dict.get("total_active", 0) or 0,
        }

    return {
        "pending": 0,
        "overdue": 0,
        "in_progress": 0,
        "completed_today": 0,
        "total_active": 0,
    }


# ============================================================================
# TASK UPDATE ENDPOINT
# ============================================================================

ALLOWED_STATUSES = {"pending", "in_progress", "completed"}
ALLOWED_PRIORITIES = {"low", "medium", "high"}


class TaskUpdateRequest(BaseModel):
    """Partial update for a task. All fields optional."""
    status: Optional[str] = None
    priority: Optional[str] = None
    title: Optional[str] = None
    due_date: Optional[str] = None


@router.patch("/tasks/{task_id}")
async def update_mobile_task(
    task_id: int,
    body: TaskUpdateRequest,
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Update a task — PATCH /api/v1/mobile/tasks/{task_id}

    Supports partial updates to status, priority, title, and due_date.
    Used by CarPlayAPIService.completeTask() and notification quick actions.
    """
    from database.models.task import Task

    task = (
        db.query(Task)
        .filter(
            Task.id == task_id,
            Task.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    now = datetime.now(timezone.utc)
    changes = []

    if body.status is not None:
        normalized = body.status.lower()
        if normalized not in ALLOWED_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{body.status}'. Allowed: {', '.join(sorted(ALLOWED_STATUSES))}",
            )
        task.status = normalized
        changes.append(f"status={normalized}")
        if normalized == "completed" and not task.completed_at:
            task.completed_at = now

    if body.priority is not None:
        normalized = body.priority.lower()
        if normalized not in ALLOWED_PRIORITIES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid priority '{body.priority}'. Allowed: {', '.join(sorted(ALLOWED_PRIORITIES))}",
            )
        task.priority = normalized
        changes.append(f"priority={normalized}")

    if body.title is not None:
        task.title = body.title.strip()
        changes.append("title updated")

    if body.due_date is not None:
        try:
            new_due = datetime.fromisoformat(body.due_date.replace("Z", "+00:00"))
            if new_due.tzinfo is None:
                new_due = new_due.replace(tzinfo=timezone.utc)
            task.due_date = new_due
            changes.append(f"due_date={new_due.isoformat()}")
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid due_date: {exc}")

    if not changes:
        raise HTTPException(status_code=422, detail="No valid fields to update")

    task.updated_at = now

    try:
        db.commit()
        db.refresh(task)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to update task %s: %s", task_id, exc)
        raise HTTPException(status_code=500, detail="Failed to update task")

    logger.info(
        "Task %s updated by user %s: %s",
        task_id, current_user.id, ", ".join(changes),
    )

    return {
        "success": True,
        "task_id": task.id,
        "status": task.status,
        "priority": task.priority,
        "title": task.title,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


# ============================================================================
# SNOOZE ENDPOINT
# ============================================================================

async def _snooze_task(
    task_id: int,
    body: SnoozeRequest,
    current_user,
    db: Session,
):
    """Core snooze logic shared by both route paths.

    Accepts either ``snooze_until`` (ISO datetime) or ``duration_minutes``.
    Falls back to +60 minutes from now when neither is provided.

    Updates the task's ``due_date`` to the resolved snooze time and returns
    a success payload with the new due date.
    """
    from database.models.task import Task

    task = (
        db.query(Task)
        .filter(
            Task.id == task_id,
            Task.organization_id == current_user.organization_id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Resolve the new due_date
    now = datetime.now(timezone.utc)

    if body.snooze_until:
        try:
            # Parse ISO 8601 string — handle both 'Z' suffix and +00:00
            snooze_dt = datetime.fromisoformat(body.snooze_until.replace("Z", "+00:00"))
            if snooze_dt.tzinfo is None:
                snooze_dt = snooze_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid snooze_until datetime: {exc}",
            )
        if snooze_dt <= now:
            raise HTTPException(
                status_code=422,
                detail="snooze_until must be in the future",
            )
        new_due = snooze_dt
    elif body.duration_minutes and body.duration_minutes > 0:
        new_due = now + timedelta(minutes=body.duration_minutes)
    else:
        # Default: snooze for 1 hour
        new_due = now + timedelta(hours=1)

    task.due_date = new_due
    task.updated_at = now
    # Reset status back to pending if it was something else
    if task.status == "completed":
        # Don't un-complete a completed task
        pass
    elif task.status != "pending":
        task.status = "pending"

    try:
        db.commit()
        db.refresh(task)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to snooze task %s: %s", task_id, exc)
        raise HTTPException(status_code=500, detail="Failed to snooze task")

    logger.info(
        "Task %s snoozed until %s by user %s",
        task_id, new_due.isoformat(), current_user.id,
    )

    return {
        "success": True,
        "task_id": task.id,
        "new_due_date": new_due.isoformat(),
    }


@router.patch("/tasks/{task_id}/snooze")
async def snooze_mobile_task(
    task_id: int,
    body: SnoozeRequest = Body(default=SnoozeRequest()),
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Snooze a task — PATCH /api/v1/mobile/tasks/{task_id}/snooze

    Pushes the task's due_date forward. Accepts an explicit ``snooze_until``
    ISO datetime or a ``duration_minutes`` offset. Defaults to +60 min.
    """
    return await _snooze_task(task_id, body, current_user, db)
