"""
Recruiting Workflow API Routes

Endpoints for:
- Workflow task management
- Dialer queue
- Task completion
- Email automation processing
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel

from workflows.recruiting_workflows import recruiting_workflow_service, RECRUITING_WORKFLOWS
from services.recruiting_email_service import get_recruiting_email_service
from sqlalchemy.exc import SQLAlchemyError
from auth.dependencies import get_current_user
from database.models import User
from routes.auth_deps import require_auth

router = APIRouter(prefix="/api/v1/recruiting/workflow", tags=["Recruiting Workflow"], dependencies=[Depends(require_auth)])


# =============================================================================
# Request/Response Models
# =============================================================================

class CreateTasksRequest(BaseModel):
    disposition: str
    assigned_to: int


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
    request: CreateTasksRequest,
    current_user: User = Depends(get_current_user)
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
        organization_id=current_user.organization_id
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
    current_user: User = Depends(get_current_user)
):
    """Get pending tasks, optionally filtered by candidate or assignee."""
    tasks = recruiting_workflow_service.get_pending_tasks(
        candidate_id=candidate_id,
        assigned_to=assigned_to,
        organization_id=current_user.organization_id
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
async def get_candidate_tasks(candidate_id: int, current_user: User = Depends(get_current_user)):
    """Get all tasks for a specific candidate."""
    tasks = recruiting_workflow_service.get_pending_tasks(
        candidate_id=candidate_id,
        organization_id=current_user.organization_id
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
    current_user: User = Depends(get_current_user)
):
    """
    Get tasks routed to the dialer queue.

    Returns candidates that need to be called, ordered by priority and due date.
    """
    queue = recruiting_workflow_service.get_dialer_queue(
        assigned_to=assigned_to,
        organization_id=current_user.organization_id
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
    from database import engine
    from sqlalchemy import text

    with engine.connect() as conn:
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
    current_user: User = Depends(get_current_user)
):
    """Get workflow dashboard data including task counts and dialer queue."""
    from database import engine
    from sqlalchemy import text

    params = {"org_id": current_user.organization_id}
    user_filter = ""
    if assigned_to:
        user_filter = "AND assigned_to = :assigned_to"
        params["assigned_to"] = assigned_to

    with engine.connect() as conn:
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

        # Get email queue count
        result = conn.execute(
            text(f"""
                SELECT COUNT(*) as count
                FROM recruiting_tasks
                WHERE organization_id = :org_id
                    AND status = 'pending'
                    AND route_to = 'email_automation'
                    {user_filter}
            """),
            params
        )
        email_count = result.fetchone().count

    return {
        "task_counts": {
            "pending": status_counts.get("pending", 0),
            "in_progress": status_counts.get("in_progress", 0),
            "completed": status_counts.get("completed", 0),
            "skipped": status_counts.get("skipped", 0)
        },
        "overdue_count": overdue_count,
        "today_count": today_count,
        "dialer_queue_count": dialer_count,
        "email_queue_count": email_count
    }


# =============================================================================
# Email Automation Endpoints
# =============================================================================

@router.get("/email-queue")
async def get_email_queue(
    assigned_to: Optional[int] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get tasks routed to email automation that are pending.

    Returns candidates that need automated emails sent.
    """
    from database import engine
    from sqlalchemy import text

    params = {"org_id": current_user.organization_id}
    filters = [
        "rt.organization_id = :org_id",
        "rt.status = 'pending'",
        "rt.route_to = 'email_automation'"
    ]

    if assigned_to:
        filters.append("rt.assigned_to = :assigned_to")
        params["assigned_to"] = assigned_to

    where_sql = " AND ".join(filters)

    with engine.connect() as conn:
        result = conn.execute(
            text(f"""
                SELECT rt.id, rt.candidate_id, rt.title, rt.description,
                       rt.due_date, rt.priority, rt.assigned_to,
                       rc.first_name, rc.last_name, rc.email
                FROM recruiting_tasks rt
                JOIN mm_candidates rc ON rc.id = rt.candidate_id
                WHERE {where_sql}
                ORDER BY rt.due_date ASC,
                         CASE rt.priority
                            WHEN 'high' THEN 1
                            WHEN 'medium' THEN 2
                            ELSE 3
                         END
            """),
            params
        )
        rows = result.fetchall()

    queue = [
        {
            "id": row.id,
            "candidate_id": row.candidate_id,
            "candidate_name": f"{row.first_name} {row.last_name}",
            "candidate_email": row.email,
            "title": row.title,
            "description": row.description,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "priority": row.priority
        }
        for row in rows
    ]

    return {
        "queue_length": len(queue),
        "queue": queue
    }


@router.post("/email-queue/{task_id}/send")
async def send_email_for_task(task_id: int, user_id: int = Query(...)):
    """
    Process and send an email for a specific email automation task.

    This marks the task as completed after successful send.
    """
    from database import engine
    from sqlalchemy import text

    with engine.connect() as conn:
        email_service = get_recruiting_email_service(conn)

        # Process the email task
        result = email_service.process_workflow_email_task(task_id, conn)

        if result.success:
            # Mark task as completed
            conn.execute(
                text("""
                    UPDATE recruiting_tasks
                    SET status = 'completed',
                        completed_at = NOW(),
                        completed_by = :user_id
                    WHERE id = :task_id
                """),
                {"task_id": task_id, "user_id": user_id}
            )
            conn.commit()

            return {
                "success": True,
                "message": result.message,
                "email_type": result.email_type,
                "recipient": result.recipient,
                "task_id": task_id
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send email: {result.error}"
            )


@router.post("/email-queue/process-all")
async def process_all_pending_emails(
    user_id: int = Query(...),
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """
    Process all pending email automation tasks.

    Sends emails for all tasks in the queue and marks them complete.
    Returns summary of processed tasks.
    """
    from database import engine
    from sqlalchemy import text

    results = {
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "details": []
    }

    with engine.connect() as conn:
        # Get pending email tasks
        tasks = conn.execute(
            text("""
                SELECT id, title FROM recruiting_tasks
                WHERE organization_id = :org_id
                    AND status = 'pending'
                    AND route_to = 'email_automation'
                ORDER BY due_date ASC
                LIMIT :limit
            """),
            {"org_id": current_user.organization_id, "limit": limit}
        ).fetchall()

        email_service = get_recruiting_email_service(conn)

        for task in tasks:
            results["processed"] += 1

            try:
                result = email_service.process_workflow_email_task(task.id, conn)

                if result.success:
                    # Mark as completed
                    conn.execute(
                        text("""
                            UPDATE recruiting_tasks
                            SET status = 'completed',
                                completed_at = NOW(),
                                completed_by = :user_id
                            WHERE id = :task_id
                        """),
                        {"task_id": task.id, "user_id": user_id}
                    )
                    results["succeeded"] += 1
                    results["details"].append({
                        "task_id": task.id,
                        "title": task.title,
                        "status": "sent",
                        "email_type": result.email_type
                    })
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "task_id": task.id,
                        "title": task.title,
                        "status": "failed",
                        "error": result.error
                    })

            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "task_id": task.id,
                    "title": task.title,
                    "status": "error",
                    "error": "Internal server error"
                })

        conn.commit()

    return results


@router.post("/email-queue/{task_id}/preview")
async def preview_email_for_task(task_id: int):
    """
    Preview the email that would be sent for a task without actually sending it.

    Useful for reviewing email content before sending.
    """
    from database import engine
    from sqlalchemy import text
    from services.recruiting_email_service import RecruitingEmailTemplates
    import os

    FRONTEND_URL = os.getenv("FRONTEND_URL", "https://perenniaai.com")

    with engine.connect() as conn:
        # Get task and candidate info
        task = conn.execute(
            text("""
                SELECT rt.id, rt.candidate_id, rt.title, rt.description,
                       rt.assigned_to,
                       rc.first_name, rc.last_name, rc.email as candidate_email
                FROM recruiting_tasks rt
                JOIN mm_candidates rc ON rc.id = rt.candidate_id
                WHERE rt.id = :task_id
            """),
            {"task_id": task_id}
        ).fetchone()

        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Get recruiter info
        recruiter = conn.execute(
            text("SELECT full_name, email, phone FROM users WHERE id = :user_id"),
            {"user_id": task.assigned_to}
        ).fetchone()

        # Get portal URL if exists
        portal = conn.execute(
            text("""
                SELECT slug FROM recruit_portal_workspaces
                WHERE candidate_id = :candidate_id AND is_active = true
                LIMIT 1
            """),
            {"candidate_id": task.candidate_id}
        ).fetchone()

        candidate_name = f"{task.first_name} {task.last_name}"
        recruiter_name = recruiter.full_name if recruiter else "Recruiting Team"
        recruiter_email = recruiter.email if recruiter else "recruiting@perenniaai.com"
        recruiter_phone = recruiter.phone if recruiter else None
        portal_url = f"{FRONTEND_URL}/recruit/{portal.slug}" if portal else f"{FRONTEND_URL}/recruit"

        templates = RecruitingEmailTemplates()
        title_lower = task.title.lower()

        # Determine template and generate preview
        if "follow-up email" in title_lower or "followup" in title_lower:
            template = templates.phone_screen_followup(
                candidate_name=candidate_name,
                recruiter_name=recruiter_name,
                recruiter_email=recruiter_email,
                recruiter_phone=recruiter_phone,
            )
            email_type = "phone_screen_followup"

        elif "portal invitation" in title_lower or ("portal" in title_lower and "send" in title_lower):
            template = templates.portal_invitation(
                candidate_name=candidate_name,
                recruiter_name=recruiter_name,
                portal_url=portal_url,
            )
            email_type = "portal_invitation"

        elif "assessment" in title_lower or "technical" in title_lower:
            assessment_url = f"{FRONTEND_URL}/recruit/{portal.slug}/assessment" if portal else f"{FRONTEND_URL}/recruit"
            template = templates.assessment_invitation(
                candidate_name=candidate_name,
                recruiter_name=recruiter_name,
                assessment_url=assessment_url,
            )
            email_type = "assessment_invitation"

        elif "welcome" in title_lower or "offer acceptance" in title_lower or "confirmation" in title_lower:
            onboarding_url = f"{FRONTEND_URL}/recruit/{portal.slug}/onboarding" if portal else None
            template = templates.offer_acceptance_welcome(
                candidate_name=candidate_name,
                recruiter_name=recruiter_name,
                onboarding_url=onboarding_url,
            )
            email_type = "welcome_email"

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown email type for task: {task.title}"
            )

        return {
            "task_id": task_id,
            "email_type": email_type,
            "recipient": task.candidate_email,
            "candidate_name": candidate_name,
            "subject": template["subject"],
            "html_content": template["html_content"],
            "plain_content": template["plain_content"]
        }
