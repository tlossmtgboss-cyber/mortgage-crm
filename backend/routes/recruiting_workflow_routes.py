"""
Recruiting Workflow API Routes

Endpoints for:
- Workflow task management
- Dialer queue
- Task completion
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel

from workflows.recruiting_workflows import recruiting_workflow_service, RECRUITING_WORKFLOWS

router = APIRouter(prefix="/api/v1/recruiting/workflow", tags=["Recruiting Workflow"])


# =============================================================================
# Request/Response Models
# =============================================================================

class CreateTasksRequest(BaseModel):
    disposition: str
    assigned_to: int
    organization_id: int = 1


class CompleteTaskRequest(BaseModel):
    completed_by: int


class SkipTaskRequest(BaseModel):
    reason: str
    skipped_by: int


# =============================================================================
# Workflow Definition Endpoints
# =============================================================================

@router.get("/definitions")
async def get_workflow_definitions():
    """Get all recruiting workflow definitions."""
    definitions = []
    for disposition, workflow in RECRUITING_WORKFLOWS.items():
        definitions.append({
            "disposition": disposition,
            "name": workflow["name"],
            "trigger": workflow["trigger"],
            "task_count": len(workflow["tasks"]),
            "tasks": [
                {
                    "day": t["day"],
                    "title": t["title"],
                    "priority": t["priority"],
                    "route_to": t["route_to"]
                }
                for t in workflow["tasks"]
            ]
        })
    return {"workflows": definitions}


@router.get("/definitions/{disposition}")
async def get_workflow_definition(disposition: str):
    """Get workflow definition for a specific disposition."""
    workflow = recruiting_workflow_service.get_workflow_for_disposition(disposition)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"No workflow found for disposition: {disposition}")
    return {
        "disposition": disposition,
        "name": workflow["name"],
        "trigger": workflow["trigger"],
        "tasks": workflow["tasks"]
    }


# =============================================================================
# Task Management Endpoints
# =============================================================================

@router.post("/candidates/{candidate_id}/create-tasks")
async def create_tasks_for_candidate(
    candidate_id: int,
    request: CreateTasksRequest
):
    """
    Create workflow tasks for a candidate when their disposition changes.

    This is typically called automatically when a candidate status is updated.
    """
    workflow = recruiting_workflow_service.get_workflow_for_disposition(request.disposition)
    if not workflow:
        return {
            "message": f"No workflow defined for disposition: {request.disposition}",
            "tasks_created": 0,
            "tasks": []
        }

    tasks = recruiting_workflow_service.create_tasks_for_disposition(
        candidate_id=candidate_id,
        disposition=request.disposition,
        assigned_to=request.assigned_to,
        organization_id=request.organization_id
    )

    return {
        "message": f"Created {len(tasks)} tasks for {request.disposition} workflow",
        "tasks_created": len(tasks),
        "tasks": tasks
    }


@router.get("/tasks")
async def get_pending_tasks(
    candidate_id: Optional[int] = None,
    assigned_to: Optional[int] = None,
    organization_id: int = 1
):
    """Get pending tasks, optionally filtered by candidate or assignee."""
    tasks = recruiting_workflow_service.get_pending_tasks(
        candidate_id=candidate_id,
        assigned_to=assigned_to,
        organization_id=organization_id
    )

    # Group by priority for dashboard view
    high_priority = [t for t in tasks if t["priority"] == "high"]
    medium_priority = [t for t in tasks if t["priority"] == "medium"]
    low_priority = [t for t in tasks if t["priority"] == "low"]
    overdue = [t for t in tasks if t.get("is_overdue")]

    return {
        "total": len(tasks),
        "overdue_count": len(overdue),
        "by_priority": {
            "high": len(high_priority),
            "medium": len(medium_priority),
            "low": len(low_priority)
        },
        "tasks": tasks
    }


@router.get("/candidates/{candidate_id}/tasks")
async def get_candidate_tasks(candidate_id: int, organization_id: int = 1):
    """Get all tasks for a specific candidate."""
    tasks = recruiting_workflow_service.get_pending_tasks(
        candidate_id=candidate_id,
        organization_id=organization_id
    )
    return {"candidate_id": candidate_id, "tasks": tasks, "total": len(tasks)}


@router.post("/tasks/{task_id}/complete")
async def complete_task(task_id: int, request: CompleteTaskRequest):
    """Mark a task as completed."""
    success = recruiting_workflow_service.complete_task(
        task_id=task_id,
        completed_by=request.completed_by
    )
    if success:
        return {"message": "Task completed", "task_id": task_id}
    raise HTTPException(status_code=500, detail="Failed to complete task")


@router.post("/tasks/{task_id}/skip")
async def skip_task(task_id: int, request: SkipTaskRequest):
    """Skip a task with a reason."""
    success = recruiting_workflow_service.skip_task(
        task_id=task_id,
        reason=request.reason,
        skipped_by=request.skipped_by
    )
    if success:
        return {"message": "Task skipped", "task_id": task_id}
    raise HTTPException(status_code=500, detail="Failed to skip task")


# =============================================================================
# Dialer Queue Endpoints
# =============================================================================

@router.get("/dialer-queue")
async def get_dialer_queue(
    assigned_to: Optional[int] = None,
    organization_id: int = 1
):
    """
    Get tasks routed to the dialer queue.

    Returns candidates that need to be called, ordered by priority and due date.
    """
    queue = recruiting_workflow_service.get_dialer_queue(
        assigned_to=assigned_to,
        organization_id=organization_id
    )
    return {
        "queue_length": len(queue),
        "queue": queue
    }


@router.post("/dialer-queue/{task_id}/start-call")
async def start_call_for_task(task_id: int, user_id: int = Query(...)):
    """
    Mark a dialer task as being worked on.

    This can be called when initiating a call to prevent duplicate calls.
    """
    from database import get_db_connection
    from sqlalchemy import text

    with get_db_connection() as conn:
        # Update task status to in_progress
        conn.execute(
            text("""
                UPDATE recruiting_tasks
                SET status = 'in_progress'
                WHERE id = :task_id AND status = 'pending'
            """),
            {"task_id": task_id}
        )
        conn.commit()

    return {"message": "Call started", "task_id": task_id}


# =============================================================================
# Dashboard Endpoints
# =============================================================================

@router.get("/dashboard")
async def get_workflow_dashboard(
    assigned_to: Optional[int] = None,
    organization_id: int = 1
):
    """Get workflow dashboard data including task counts and dialer queue."""
    from database import get_db_connection
    from sqlalchemy import text

    params = {"org_id": organization_id}
    user_filter = ""
    if assigned_to:
        user_filter = "AND assigned_to = :assigned_to"
        params["assigned_to"] = assigned_to

    with get_db_connection() as conn:
        # Get task counts by status
        result = conn.execute(
            text(f"""
                SELECT status, COUNT(*) as count
                FROM recruiting_tasks
                WHERE organization_id = :org_id {user_filter}
                GROUP BY status
            """),
            params
        )
        status_counts = {row.status: row.count for row in result.fetchall()}

        # Get overdue count
        result = conn.execute(
            text(f"""
                SELECT COUNT(*) as count
                FROM recruiting_tasks
                WHERE organization_id = :org_id
                    AND status = 'pending'
                    AND due_date < NOW()
                    {user_filter}
            """),
            params
        )
        overdue_count = result.fetchone().count

        # Get today's tasks
        result = conn.execute(
            text(f"""
                SELECT COUNT(*) as count
                FROM recruiting_tasks
                WHERE organization_id = :org_id
                    AND status = 'pending'
                    AND DATE(due_date) = CURRENT_DATE
                    {user_filter}
            """),
            params
        )
        today_count = result.fetchone().count

        # Get dialer queue count
        result = conn.execute(
            text(f"""
                SELECT COUNT(*) as count
                FROM recruiting_tasks
                WHERE organization_id = :org_id
                    AND status = 'pending'
                    AND route_to = 'dialer_queue'
                    {user_filter}
            """),
            params
        )
        dialer_count = result.fetchone().count

    return {
        "task_counts": {
            "pending": status_counts.get("pending", 0),
            "in_progress": status_counts.get("in_progress", 0),
            "completed": status_counts.get("completed", 0),
            "skipped": status_counts.get("skipped", 0)
        },
        "overdue_count": overdue_count,
        "today_count": today_count,
        "dialer_queue_count": dialer_count
    }
