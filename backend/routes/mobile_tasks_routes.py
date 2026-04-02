"""
Mobile Tasks Routes

GET /api/v1/mobile/tasks         — List tasks from the `tasks` table for the current user
GET /api/v1/mobile/tasks/summary — Task count summaries for the mobile dashboard

These endpoints query the real `tasks` table (NOT `ai_tasks`) and support
status filtering, overdue detection, and optional workflow metadata via
LEFT JOIN on workflow_task_instances.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import require_auth, current_user_dep

router = APIRouter(
    prefix="/api/v1/mobile",
    tags=["Mobile Tasks"],
    dependencies=[Depends(require_auth)],
)


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
