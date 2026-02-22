"""
Perennia AI - Workflow System API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from datetime import date
import logging

from database import get_db
from routes.auth_deps import require_auth
from workflow_service import (
    WorkflowEngine,
    ThemeDayService,
    LastMileService,
    PostClosingService,
    AIWorkflowAnalyzer
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workflow", dependencies=[Depends(require_auth)])


# ============== Workflow Engine ==============

@router.post("/evaluate/{loan_id}")
async def evaluate_loan_workflows(
    loan_id: int,
    db: Session = Depends(get_db)
):
    """Evaluate all workflow rules for a specific loan"""
    result = WorkflowEngine.evaluate_loan_workflows(db, loan_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/tasks")
async def get_workflow_tasks(
    loan_id: Optional[int] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get workflow tasks with optional filters"""
    try:
        query = """
            SELECT wt.id, wt.loan_id, wt.task_title, wt.task_description,
                   wt.priority, wt.due_date, wt.status, wt.created_at,
                   l.borrower_name
            FROM workflow_tasks wt
            LEFT JOIN loans l ON wt.loan_id = l.id
            WHERE 1=1
        """
        params = {"limit": limit}

        if loan_id:
            query += " AND wt.loan_id = :loan_id"
            params["loan_id"] = loan_id

        if status:
            query += " AND wt.status = :status"
            params["status"] = status

        if priority:
            query += " AND wt.priority = :priority"
            params["priority"] = priority

        query += " ORDER BY wt.due_date ASC NULLS LAST LIMIT :limit"

        result = db.execute(text(query), params)
        tasks = [{
            "id": str(r[0]),
            "loan_id": r[1],
            "title": r[2],
            "description": r[3],
            "priority": r[4],
            "due_date": r[5].isoformat() if r[5] else None,
            "status": r[6],
            "created_at": r[7].isoformat() if r[7] else None,
            "borrower": r[8] or "Unknown"
        } for r in result]

        return {"tasks": tasks, "count": len(tasks)}

    except Exception as e:
        logger.error(f"Get tasks error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/tasks/{task_id}/complete")
async def complete_workflow_task(
    task_id: str,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Mark a workflow task as completed"""
    try:
        db.execute(text("""
            UPDATE workflow_tasks
            SET status = 'completed', completed_at = NOW(), notes = :notes
            WHERE id = :task_id
        """), {"task_id": task_id, "notes": notes})
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/alerts")
async def get_workflow_alerts(
    loan_id: Optional[int] = None,
    severity: Optional[str] = None,
    acknowledged: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get workflow alerts with optional filters"""
    try:
        query = """
            SELECT wa.id, wa.loan_id, wa.alert_type, wa.alert_message,
                   wa.alert_level, wa.acknowledged, wa.created_at,
                   l.borrower_name
            FROM workflow_alerts wa
            LEFT JOIN loans l ON wa.loan_id = l.id
            WHERE wa.acknowledged = :ack
        """
        params = {"ack": acknowledged, "limit": limit}

        if loan_id:
            query += " AND wa.loan_id = :loan_id"
            params["loan_id"] = loan_id

        if severity:
            query += " AND wa.alert_level = :severity"
            params["severity"] = severity

        query += " ORDER BY wa.created_at DESC LIMIT :limit"

        result = db.execute(text(query), params)
        alerts = [{
            "id": str(r[0]),
            "loan_id": r[1],
            "alert_type": r[2],
            "message": r[3],
            "severity": r[4],
            "acknowledged": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
            "borrower": r[7] or "Unknown"
        } for r in result]

        return {"alerts": alerts, "count": len(alerts)}

    except Exception as e:
        logger.error(f"Get alerts error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    db: Session = Depends(get_db)
):
    """Acknowledge a workflow alert"""
    try:
        db.execute(text("""
            UPDATE workflow_alerts
            SET acknowledged = TRUE, acknowledged_at = NOW()
            WHERE id = :alert_id
        """), {"alert_id": alert_id})
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ============== Theme Days ==============

@router.get("/theme-days/today")
async def get_today_theme():
    """Get today's theme day configuration"""
    return ThemeDayService.get_today_theme()


@router.post("/theme-days/schedule")
async def schedule_theme_messages(
    organization_id: int = 1,
    db: Session = Depends(get_db)
):
    """Schedule theme day messages for all active loans"""
    result = ThemeDayService.schedule_theme_messages(db, organization_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/theme-days/scheduled")
async def get_scheduled_messages(
    date_filter: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get scheduled theme day messages"""
    try:
        # Query theme_day_messages table which has scheduled content
        query = """
            SELECT tdm.id, tdm.loan_id, tdm.week_number, tdm.theme_name,
                   tdm.scheduled_send_date, tdm.ai_generated_content,
                   tdm.status, l.borrower_name
            FROM theme_day_messages tdm
            LEFT JOIN loans l ON tdm.loan_id = l.id
            WHERE 1=1
        """
        params = {"limit": limit}

        if date_filter:
            query += " AND tdm.scheduled_send_date = :date"
            params["date"] = date_filter
        else:
            query += " AND tdm.scheduled_send_date >= :today"
            params["today"] = date.today()

        if status:
            query += " AND tdm.status = :status"
            params["status"] = status

        query += " ORDER BY tdm.scheduled_send_date DESC LIMIT :limit"

        result = db.execute(text(query), params)
        messages = [{
            "id": str(r[0]),
            "loan_id": r[1],
            "week_number": r[2],
            "theme_name": r[3],
            "scheduled_date": r[4].isoformat() if r[4] else None,
            "message": r[5],
            "status": r[6],
            "borrower": r[7] or "Unknown"
        } for r in result]

        return {"messages": messages, "count": len(messages)}

    except Exception as e:
        logger.error(f"Get scheduled messages error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============== Last Mile ==============

@router.post("/last-mile/initialize/{loan_id}")
async def initialize_last_mile(
    loan_id: int,
    db: Session = Depends(get_db)
):
    """Initialize Last Mile 7-day process for a loan"""
    result = LastMileService.initialize_last_mile(db, loan_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/last-mile/today")
async def get_last_mile_today(
    db: Session = Depends(get_db)
):
    """Get all Last Mile tasks due today"""
    tasks = LastMileService.get_today_tasks(db)
    return {"tasks": tasks, "count": len(tasks)}


@router.put("/last-mile/tasks/{task_id}/complete")
async def complete_last_mile_task(
    task_id: str,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Mark a Last Mile task as completed"""
    result = LastMileService.complete_task(db, task_id, notes)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/last-mile/loan/{loan_id}")
async def get_last_mile_status(
    loan_id: int,
    db: Session = Depends(get_db)
):
    """Get Last Mile status for a specific loan"""
    try:
        tasks = db.execute(text("""
            SELECT id, task_name, task_date, parties_involved, status,
                   completed_at, notes
            FROM last_mile_tasks
            WHERE loan_id = :loan_id
            ORDER BY task_date ASC
        """), {"loan_id": loan_id}).fetchall()

        return {
            "loan_id": loan_id,
            "tasks": [{
                "id": str(t[0]),
                "task_name": t[1],
                "task_date": t[2].isoformat() if t[2] else None,
                "parties": t[3],
                "status": t[4],
                "completed_at": t[5].isoformat() if t[5] else None,
                "notes": t[6]
            } for t in tasks],
            "total": len(tasks),
            "completed": sum(1 for t in tasks if t[4] == 'completed')
        }

    except Exception as e:
        logger.error(f"Get Last Mile status error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============== Post-Closing ==============

@router.post("/post-closing/schedule/{loan_id}")
async def schedule_post_closing(
    loan_id: int,
    db: Session = Depends(get_db)
):
    """Schedule post-closing follow-up calls for a funded loan"""
    result = PostClosingService.schedule_post_closing_calls(db, loan_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/post-closing/calls")
async def get_post_closing_calls(
    completed: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get post-closing calls"""
    try:
        if completed:
            where_clause = "pc.completed_date IS NOT NULL"
        else:
            where_clause = "pc.completed_date IS NULL AND pc.scheduled_date >= NOW()"

        result = db.execute(text(f"""
            SELECT pc.id, pc.loan_id, pc.scheduled_date, pc.completed_date,
                   pc.experience_rating, l.borrower_name
            FROM post_closing_calls pc
            LEFT JOIN loans l ON pc.loan_id = l.id
            WHERE {where_clause}
            ORDER BY pc.scheduled_date ASC
            LIMIT :limit
        """), {"limit": limit}).fetchall()

        calls = [{
            "id": str(r[0]),
            "loan_id": r[1],
            "scheduled_date": r[2].isoformat() if r[2] else None,
            "completed_date": r[3].isoformat() if r[3] else None,
            "rating": r[4],
            "borrower": r[5] or "Unknown"
        } for r in result]

        return {"calls": calls, "count": len(calls)}

    except Exception as e:
        logger.error(f"Get post-closing calls error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============== AI Analysis ==============

@router.post("/ai/analyze/{loan_id}")
async def analyze_loan_risk(
    loan_id: int,
    db: Session = Depends(get_db)
):
    """Run AI risk analysis on a loan"""
    result = AIWorkflowAnalyzer.analyze_loan_risk(db, loan_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/ai/priority-loans")
async def get_priority_loans(
    organization_id: int = 1,
    db: Session = Depends(get_db)
):
    """Get loans requiring immediate attention"""
    loans = AIWorkflowAnalyzer.get_priority_loans(db, organization_id)
    return {"priority_loans": loans, "count": len(loans)}


@router.get("/ai/analysis/{loan_id}")
async def get_loan_analysis(
    loan_id: int,
    db: Session = Depends(get_db)
):
    """Get latest AI analysis for a loan"""
    try:
        result = db.execute(text("""
            SELECT id, analysis_type, risk_score, findings, recommendations,
                   created_at
            FROM ai_analysis
            WHERE loan_id = :loan_id
            ORDER BY created_at DESC
            LIMIT 5
        """), {"loan_id": loan_id}).fetchall()

        analyses = [{
            "id": str(r[0]),
            "type": r[1],
            "risk_score": r[2],
            "findings": r[3],
            "recommendations": r[4],
            "created_at": r[5].isoformat() if r[5] else None
        } for r in result]

        return {"loan_id": loan_id, "analyses": analyses}

    except Exception as e:
        logger.error(f"Get analysis error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============== Dashboard ==============

@router.get("/dashboard/summary")
async def get_workflow_dashboard(
    organization_id: int = 1,
    db: Session = Depends(get_db)
):
    """Get workflow dashboard summary"""
    try:
        # Pending tasks count (simplified - no org filter for now)
        pending_tasks = db.execute(text("""
            SELECT COUNT(*) FROM workflow_tasks
            WHERE status = 'pending'
        """)).scalar() or 0

        # Overdue tasks
        overdue_tasks = db.execute(text("""
            SELECT COUNT(*) FROM workflow_tasks
            WHERE status = 'pending' AND due_date < NOW()
        """)).scalar() or 0

        # Unacknowledged alerts
        alerts = db.execute(text("""
            SELECT COUNT(*) FROM workflow_alerts
            WHERE acknowledged = FALSE
        """)).scalar() or 0

        # Last Mile tasks today
        last_mile_today = db.execute(text("""
            SELECT COUNT(*) FROM last_mile_tasks
            WHERE due_date::date = CURRENT_DATE AND status = 'pending'
        """)).scalar() or 0

        # High risk loans (using confidence_score < 0.5 as risk indicator)
        high_risk = db.execute(text("""
            SELECT COUNT(DISTINCT loan_id) FROM ai_analysis
            WHERE confidence_score < 0.5
            AND created_at > NOW() - INTERVAL '24 hours'
        """)).scalar() or 0

        return {
            "pending_tasks": pending_tasks,
            "overdue_tasks": overdue_tasks,
            "unacknowledged_alerts": alerts,
            "last_mile_today": last_mile_today,
            "high_risk_loans": high_risk,
            "theme_day": ThemeDayService.get_today_theme()
        }

    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============== Workflow Definitions ==============

# The 10 pre-configured workflows with their task templates
WORKFLOW_DEFINITIONS = {
    "prospect": {
        "id": "workflow_prospect",
        "name": "prospect",
        "display_name": "Prospect",
        "description": "Statuses impacted: New, Attempted Contact, Prospect",
        "objective": "Get the lead to complete the application for pre-approval",
        "color": "#3b82f6",
        "task_count": 18
    },
    "prequal": {
        "id": "workflow_prequal",
        "name": "prequal",
        "display_name": "PreQual",
        "description": "Statuses impacted: Application and PreQual",
        "objective": "Have clients return supporting documents",
        "color": "#8b5cf6",
        "task_count": 18
    },
    "pre_approved": {
        "id": "workflow_pre_approved",
        "name": "pre_approved",
        "display_name": "Pre-Approval",
        "description": "Statuses impacted: Pre-Approved",
        "objective": "Stay in contact with Pre-Approved Borrower until they find the house",
        "color": "#10b981",
        "task_count": 13
    },
    "under_contract": {
        "id": "workflow_under_contract",
        "name": "under_contract",
        "display_name": "Under Contract",
        "description": "Statuses impacted: Disclosed, In Processing, In Underwriting, Approved, Clear to Close",
        "objective": "Create a 5-star processing experience",
        "color": "#f59e0b",
        "task_count": 9
    },
    "lead_purchase": {
        "id": "workflow_lead_purchase",
        "name": "lead_purchase",
        "display_name": "Lead Purchase",
        "description": "High-touch nurturing for purchased leads",
        "objective": "Get the lead to complete the application for pre-approval",
        "color": "#ec4899",
        "task_count": 36
    },
    "theme_day": {
        "id": "workflow_theme_day",
        "name": "theme_day",
        "display_name": "Theme Day",
        "description": "Weekly themed communications for active loans",
        "objective": "Create a 5-star experience with themed touchpoints",
        "color": "#06b6d4",
        "task_count": 3
    },
    "last_mile": {
        "id": "workflow_last_mile",
        "name": "last_mile",
        "display_name": "Last Mile",
        "description": "7-day pre-closing preparation",
        "objective": "Prepare the buyer for closing and life after closing",
        "color": "#14b8a6",
        "task_count": 1
    },
    "post_close": {
        "id": "workflow_post_close",
        "name": "post_close",
        "display_name": "Post Close",
        "description": "Statuses impacted: Funded",
        "objective": "Guide homebuyers over the next 12 months",
        "color": "#22c55e",
        "task_count": 5
    },
    "credit_repair": {
        "id": "workflow_credit_repair",
        "name": "credit_repair",
        "display_name": "Credit Repair",
        "description": "Long-term credit improvement nurturing",
        "objective": "Stay in contact with lead until they're ready",
        "color": "#f97316",
        "task_count": 12
    },
    "nurture": {
        "id": "workflow_nurture",
        "name": "nurture",
        "display_name": "Nurture",
        "description": "Lead conversion over time",
        "objective": "Stay in contact with lead until they're ready",
        "color": "#6366f1",
        "task_count": 12
    }
}


@router.get("/definitions")
async def get_workflow_definitions(
    db: Session = Depends(get_db)
):
    """Get all workflow definitions with task counts"""
    try:
        # Try to get actual task counts from database if tables exist
        workflows = []
        for key, workflow in WORKFLOW_DEFINITIONS.items():
            workflow_data = workflow.copy()

            # Try to get actual task count from DB
            try:
                result = db.execute(text("""
                    SELECT COUNT(*) FROM workflow_task_templates
                    WHERE workflow_id = :workflow_id
                """), {"workflow_id": workflow["id"]})
                count = result.scalar()
                if count and count > 0:
                    workflow_data["task_count"] = count
            except Exception as e:
                logger.exception(f"Failed to query task count for workflow: {e}")

            workflows.append(workflow_data)

        return {
            "workflows": workflows,
            "total_workflows": len(workflows),
            "total_tasks": sum(w["task_count"] for w in workflows)
        }
    except Exception as e:
        logger.error(f"Get workflow definitions error: {e}")
        # Return default definitions even on error
        return {
            "workflows": list(WORKFLOW_DEFINITIONS.values()),
            "total_workflows": len(WORKFLOW_DEFINITIONS),
            "total_tasks": 127
        }


@router.get("/definitions/{workflow_name}")
async def get_workflow_definition(
    workflow_name: str,
    db: Session = Depends(get_db)
):
    """Get a specific workflow definition with its tasks"""
    if workflow_name not in WORKFLOW_DEFINITIONS:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = WORKFLOW_DEFINITIONS[workflow_name].copy()

    # Try to get tasks from database
    try:
        result = db.execute(text("""
            SELECT id, sequence_order, name, timing_type, timing_value, timing_label,
                   requires_phone_call, requires_text_message, requires_email,
                   requires_referral_partner_contact, assigned_to, is_automated
            FROM workflow_task_templates
            WHERE workflow_id = :workflow_id
            ORDER BY sequence_order ASC
        """), {"workflow_id": workflow["id"]})

        tasks = [{
            "id": str(r[0]),
            "sequence": r[1],
            "name": r[2],
            "timing_type": r[3],
            "timing_value": r[4],
            "timing_label": r[5],
            "requires_phone": r[6],
            "requires_text": r[7],
            "requires_email": r[8],
            "requires_partner_contact": r[9],
            "assigned_to": r[10],
            "is_automated": r[11]
        } for r in result]

        workflow["tasks"] = tasks
        workflow["task_count"] = len(tasks) if tasks else workflow["task_count"]
    except Exception as e:
        logger.warning(f"Could not fetch tasks from DB: {e}")
        workflow["tasks"] = []

    return workflow


@router.get("/definitions/{workflow_name}/tasks")
async def get_workflow_tasks_for_user(
    workflow_name: str,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    status: Optional[str] = "pending",
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get workflow task instances for a specific workflow"""
    if workflow_name not in WORKFLOW_DEFINITIONS:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow_id = WORKFLOW_DEFINITIONS[workflow_name]["id"]

    try:
        # Get task instances from workflow_task_instances table
        query = """
            SELECT wti.id, wti.task_name, wti.scheduled_date, wti.status,
                   wti.lead_id, wti.loan_id, wti.assigned_to, wti.completed_at,
                   COALESCE(l.borrower_name, CONCAT(ld.first_name, ' ', ld.last_name)) as borrower_name
            FROM workflow_task_instances wti
            LEFT JOIN loans l ON wti.loan_id = l.id
            LEFT JOIN leads ld ON wti.lead_id = ld.id
            WHERE wti.workflow_id = :workflow_id
        """
        params = {"workflow_id": workflow_id, "limit": limit}

        if status:
            query += " AND wti.status = :status"
            params["status"] = status

        if lead_id:
            query += " AND wti.lead_id = :lead_id"
            params["lead_id"] = lead_id

        if loan_id:
            query += " AND wti.loan_id = :loan_id"
            params["loan_id"] = loan_id

        query += " ORDER BY wti.scheduled_date ASC NULLS LAST LIMIT :limit"

        result = db.execute(text(query), params)
        tasks = [{
            "id": str(r[0]),
            "task_name": r[1],
            "scheduled_date": r[2].isoformat() if r[2] else None,
            "status": r[3],
            "lead_id": r[4],
            "loan_id": r[5],
            "assigned_to": r[6],
            "completed_at": r[7].isoformat() if r[7] else None,
            "borrower_name": r[8] or "Unknown"
        } for r in result]

        return {
            "workflow": WORKFLOW_DEFINITIONS[workflow_name],
            "tasks": tasks,
            "count": len(tasks)
        }
    except Exception as e:
        logger.error(f"Get workflow tasks error: {e}")
        return {
            "workflow": WORKFLOW_DEFINITIONS[workflow_name],
            "tasks": [],
            "count": 0,
            "note": "Workflow task instances table may not exist yet"
        }


# ============== Upcoming Tasks by Workflow Stage ==============

@router.get("/upcoming-tasks-all")
async def get_all_upcoming_tasks(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get ALL upcoming tasks for the next N business days (no stage filtering)"""
    try:
        from datetime import datetime, timedelta

        # Calculate business days range
        today = datetime.now().date()
        end_date = today + timedelta(days=days + 4)  # Add buffer for weekends

        # Query ALL tasks without stage filtering
        # Include tasks without due dates (treat as today's tasks)
        # Query from ai_tasks table (main task table used by the UI)
        query = """
            SELECT
                t.id,
                t.title,
                t.description,
                t.priority,
                COALESCE(t.due_date, CURRENT_DATE) as due_date,
                t.type::text,
                t.assigned_to_id,
                u.full_name as owner_name,
                COALESCE(t.borrower_name, l.borrower_name, le.name, 'Unknown') as client_name,
                COALESCE(l.loan_number, '') as loan_number
            FROM ai_tasks t
            LEFT JOIN users u ON t.assigned_to_id = u.id
            LEFT JOIN loans l ON t.loan_id = l.id
            LEFT JOIN leads le ON t.lead_id = le.id
            WHERE t.type::text != 'Completed'
            AND (t.due_date IS NULL OR t.due_date <= :end_date)
            ORDER BY COALESCE(t.due_date, CURRENT_DATE) ASC, t.priority DESC
            LIMIT 200
        """
        params = {"today": today, "end_date": end_date}

        result = db.execute(text(query), params)
        tasks = result.fetchall()

        logger.info(f"Upcoming tasks all: found {len(tasks)} raw tasks, today={today}, end={end_date}")
        for t in tasks[:3]:
            logger.info(f"  Task sample: id={t[0]}, title={t[1][:30] if t[1] else 'N/A'}, due={t[4]}, type={t[5]}")

        # Group tasks by day
        tasks_by_day = {}
        user_stats = {}

        for task in tasks:
            due_date = task[4]
            if due_date:
                # Skip weekends
                if due_date.weekday() >= 5:
                    continue

                date_key = due_date.strftime('%Y-%m-%d')
                if date_key not in tasks_by_day:
                    tasks_by_day[date_key] = []

                owner_id = task[6]
                owner_name = task[7] or "Unassigned"

                task_data = {
                    "id": str(task[0]),
                    "title": task[1],
                    "description": task[2] or "",
                    "priority": task[3] or "medium",
                    "dueTime": due_date.strftime('%H:%M') if due_date else "09:00",
                    "estimatedMinutes": 30,
                    "status": task[5] or "pending",
                    "clientName": task[8] or "Unknown",
                    "loanNumber": task[9] or "",
                    "assignedTo": {
                        "id": owner_id,
                        "name": owner_name,
                        "role": "Team Member"
                    }
                }
                tasks_by_day[date_key].append(task_data)

                # Track user stats
                if owner_id not in user_stats:
                    user_stats[owner_id] = {
                        "id": owner_id,
                        "name": owner_name,
                        "role": "Team Member",
                        "avgDailyCapacity": 15,
                        "totalAssigned": 0,
                        "dailyTasks": {}
                    }
                user_stats[owner_id]["totalAssigned"] += 1
                if date_key not in user_stats[owner_id]["dailyTasks"]:
                    user_stats[owner_id]["dailyTasks"][date_key] = 0
                user_stats[owner_id]["dailyTasks"][date_key] += 1

        # Calculate user capacity
        user_capacity = []
        for user_id, stats in user_stats.items():
            daily_tasks = [
                {"date": d, "assigned": c, "estimatedHours": c * 0.5}
                for d, c in sorted(stats["dailyTasks"].items())
            ]
            avg_daily = stats["totalAssigned"] / max(len(stats["dailyTasks"]), 1)
            user_capacity.append({
                "id": stats["id"],
                "name": stats["name"],
                "role": stats["role"],
                "avgDailyCapacity": stats["avgDailyCapacity"],
                "totalAssigned": stats["totalAssigned"],
                "avgDailyAssigned": round(avg_daily, 1),
                "dailyTasks": daily_tasks,
                "capacityUtilization": min(100, round((avg_daily / stats["avgDailyCapacity"]) * 100)),
                "overCapacity": avg_daily > stats["avgDailyCapacity"],
                "completedToday": 0,
                "completedThisWeek": 0
            })

        total_tasks = sum(len(t) for t in tasks_by_day.values())

        return {
            "workflow_key": "all",
            "tasks_by_day": tasks_by_day,
            "user_capacity": user_capacity,
            "total_tasks": total_tasks
        }

    except Exception as e:
        logger.error(f"Get all upcoming tasks error: {e}")
        return {
            "workflow_key": "all",
            "tasks_by_day": {},
            "user_capacity": [],
            "total_tasks": 0,
            "error": "Internal server error"
        }


@router.post("/generate-tasks")
async def generate_tasks_for_pipeline(
    db: Session = Depends(get_db)
):
    """Generate follow-up tasks for all leads and loans based on their stage"""
    try:
        from datetime import datetime, timedelta
        import random

        today = datetime.now()
        tasks_created = 0

        # Task templates by lead stage
        lead_task_templates = {
            'NEW': [
                ("Initial contact call", "Call to introduce yourself and understand their needs", "high"),
                ("Send welcome email", "Send personalized welcome email with next steps", "medium"),
            ],
            'CONTACTED': [
                ("Follow up call", "Follow up on previous conversation", "high"),
                ("Send rate information", "Provide current rate options", "medium"),
            ],
            'QUALIFIED': [
                ("Schedule pre-qualification call", "Discuss financial situation and loan options", "high"),
                ("Request income documentation", "Request W2s, pay stubs, tax returns", "high"),
            ],
            'PRE_QUALIFIED': [
                ("Send pre-qualification letter", "Generate and send pre-qual letter", "high"),
                ("Property search check-in", "Check on property search progress", "medium"),
            ],
            'PRE_APPROVED': [
                ("Pre-approval follow-up", "Check if borrower found a property", "high"),
                ("Rate lock discussion", "Discuss rate lock options", "medium"),
            ],
        }

        # Task templates by loan stage
        loan_task_templates = {
            'DISCLOSED': [
                ("Review disclosure documents", "Ensure borrower reviewed and signed disclosures", "high"),
                ("Collect remaining conditions", "Follow up on outstanding conditions", "high"),
            ],
            'PROCESSING': [
                ("Processing status update", "Check with processor on file status", "medium"),
                ("Borrower update call", "Update borrower on processing progress", "medium"),
            ],
            'SUBMITTED': [
                ("Underwriting follow-up", "Check on underwriting timeline", "high"),
                ("Prepare for conditions", "Anticipate potential conditions", "medium"),
            ],
            'APPROVED': [
                ("Clear conditions", "Work on clearing remaining conditions", "high"),
                ("Schedule closing", "Coordinate closing date with all parties", "high"),
            ],
            'CTC': [
                ("Final walkthrough reminder", "Remind borrower about final walkthrough", "high"),
                ("Closing preparation", "Confirm closing details and funds needed", "high"),
            ],
            'DOCS_OUT': [
                ("Closing document review", "Review closing docs for accuracy", "high"),
                ("Wire instructions", "Verify wire instructions with title", "urgent"),
            ],
        }

        # Get all leads
        leads_result = db.execute(text("""
            SELECT l.id, l.name, l.stage::text, l.owner_id
            FROM leads l
            WHERE l.stage IS NOT NULL
            LIMIT 100
        """))
        leads = leads_result.fetchall()

        for lead in leads:
            lead_id, lead_name, stage, owner_id = lead
            stage_upper = stage.upper().replace(' ', '_').replace('-', '_') if stage else 'NEW'

            templates = lead_task_templates.get(stage_upper, lead_task_templates.get('NEW', []))

            for title, description, priority in templates:
                # Random due date in next 7 days
                due_date = today + timedelta(days=random.randint(1, 7))

                db.execute(text("""
                    INSERT INTO ai_tasks (title, description, priority, type, lead_id, assigned_to_id, due_date, created_at, updated_at)
                    VALUES (:title, :description, :priority, 'IN_PROGRESS'::tasktype, :lead_id, :owner_id, :due_date, NOW(), NOW())
                    ON CONFLICT DO NOTHING
                """), {
                    "title": f"{title} - {lead_name}",
                    "description": description,
                    "priority": priority,
                    "lead_id": lead_id,
                    "owner_id": owner_id or 1,
                    "due_date": due_date
                })
                tasks_created += 1

        # Get all loans
        loans_result = db.execute(text("""
            SELECT l.id, l.borrower_name, l.stage::text, l.loan_officer_id, l.loan_number
            FROM loans l
            WHERE l.stage IS NOT NULL
            LIMIT 100
        """))
        loans = loans_result.fetchall()

        for loan in loans:
            loan_id, borrower_name, stage, loan_officer_id, loan_number = loan
            stage_upper = stage.upper().replace(' ', '_').replace('-', '_') if stage else 'DISCLOSED'

            templates = loan_task_templates.get(stage_upper, loan_task_templates.get('DISCLOSED', []))

            for title, description, priority in templates:
                # Random due date in next 7 days
                due_date = today + timedelta(days=random.randint(1, 7))

                db.execute(text("""
                    INSERT INTO ai_tasks (title, description, priority, type, loan_id, assigned_to_id, borrower_name, due_date, created_at, updated_at)
                    VALUES (:title, :description, :priority, 'IN_PROGRESS'::tasktype, :loan_id, :owner_id, :borrower_name, :due_date, NOW(), NOW())
                    ON CONFLICT DO NOTHING
                """), {
                    "title": f"{title} - {borrower_name or loan_number}",
                    "description": description,
                    "priority": priority,
                    "loan_id": loan_id,
                    "owner_id": loan_officer_id or 1,
                    "borrower_name": borrower_name,
                    "due_date": due_date
                })
                tasks_created += 1

        db.commit()

        return {
            "success": True,
            "tasks_created": tasks_created,
            "leads_processed": len(leads),
            "loans_processed": len(loans)
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Generate tasks error: {e}")
        return {
            "success": False,
            "error": "Internal server error"
        }


# Map workflow keys to stage filters
WORKFLOW_STAGE_MAPPING = {
    'prospect': {'lead_stages': ['new', 'contacted', 'qualified'], 'loan_stages': []},
    'prequal': {'lead_stages': ['pre_qualified'], 'loan_stages': []},
    'pre_approved': {'lead_stages': ['pre_approved'], 'loan_stages': ['Disclosed']},
    'under_contract': {'lead_stages': [], 'loan_stages': ['Processing', 'Submitted', 'UW Received', 'Approved', 'Suspended']},
    'lead_purchase': {'lead_stages': ['purchased'], 'loan_stages': []},
    'theme_day': {'is_theme_day': True},
    'last_mile': {'lead_stages': [], 'loan_stages': ['CTC', 'Docs Out']},
    'post_close': {'lead_stages': [], 'loan_stages': ['Funded']},
    'credit_repair': {'lead_stages': ['credit_repair'], 'loan_stages': []},
    'nurture': {'lead_stages': ['nurture', 'not_ready'], 'loan_stages': []}
}


@router.get("/upcoming-tasks/{workflow_key}")
async def get_upcoming_tasks_by_workflow(
    workflow_key: str,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get upcoming tasks filtered by workflow stage for the next N business days"""
    try:
        from datetime import datetime, timedelta
        import json

        # Get the stage mapping for this workflow
        stage_filter = WORKFLOW_STAGE_MAPPING.get(workflow_key, {})
        lead_stages = stage_filter.get('lead_stages', [])
        loan_stages = stage_filter.get('loan_stages', [])

        # Calculate business days range
        today = datetime.now().date()
        end_date = today + timedelta(days=days + 4)  # Add buffer for weekends

        # Build query for tasks
        query = """
            SELECT
                t.id,
                t.title,
                t.description,
                t.priority,
                t.due_date,
                t.status,
                t.owner_id,
                u.full_name as owner_name,
                COALESCE(l.borrower_name, le.name, t.related_contact_name, 'Unknown') as client_name,
                COALESCE(l.loan_number, '') as loan_number,
                l.stage as loan_stage,
                le.stage as lead_stage
            FROM tasks t
            LEFT JOIN users u ON t.owner_id = u.id
            LEFT JOIN loans l ON t.loan_id = l.id
            LEFT JOIN leads le ON t.lead_id = le.id
            WHERE t.status != 'completed'
            AND t.due_date IS NOT NULL
            AND t.due_date >= :today
            AND t.due_date <= :end_date
        """
        params = {"today": today, "end_date": end_date}

        # Add stage filters based on workflow
        if lead_stages and loan_stages:
            query += " AND (le.stage IN :lead_stages OR l.stage IN :loan_stages)"
            params["lead_stages"] = tuple(lead_stages) if len(lead_stages) > 1 else (lead_stages[0],)
            params["loan_stages"] = tuple(loan_stages) if len(loan_stages) > 1 else (loan_stages[0],)
        elif lead_stages:
            query += " AND le.stage IN :lead_stages"
            params["lead_stages"] = tuple(lead_stages) if len(lead_stages) > 1 else (lead_stages[0],)
        elif loan_stages:
            query += " AND l.stage IN :loan_stages"
            params["loan_stages"] = tuple(loan_stages) if len(loan_stages) > 1 else (loan_stages[0],)

        query += " ORDER BY t.due_date ASC, t.priority DESC LIMIT 200"

        result = db.execute(text(query), params)
        tasks = result.fetchall()

        # Group tasks by day
        tasks_by_day = {}
        user_stats = {}

        for task in tasks:
            due_date = task[4]
            if due_date:
                # Skip weekends
                if due_date.weekday() >= 5:
                    continue

                date_key = due_date.strftime('%Y-%m-%d')
                if date_key not in tasks_by_day:
                    tasks_by_day[date_key] = []

                owner_id = task[6]
                owner_name = task[7] or "Unassigned"

                task_data = {
                    "id": str(task[0]),
                    "title": task[1],
                    "description": task[2] or "",
                    "priority": task[3] or "medium",
                    "dueTime": due_date.strftime('%H:%M') if due_date else "09:00",
                    "estimatedMinutes": 30,
                    "status": task[5] or "pending",
                    "clientName": task[8] or "Unknown",
                    "loanNumber": task[9] or "",
                    "assignedTo": {
                        "id": owner_id,
                        "name": owner_name,
                        "role": "Team Member"
                    }
                }
                tasks_by_day[date_key].append(task_data)

                # Track user stats
                if owner_id not in user_stats:
                    user_stats[owner_id] = {
                        "id": owner_id,
                        "name": owner_name,
                        "role": "Team Member",
                        "avgDailyCapacity": 15,
                        "totalAssigned": 0,
                        "dailyTasks": {}
                    }
                user_stats[owner_id]["totalAssigned"] += 1
                if date_key not in user_stats[owner_id]["dailyTasks"]:
                    user_stats[owner_id]["dailyTasks"][date_key] = 0
                user_stats[owner_id]["dailyTasks"][date_key] += 1

        # Calculate user capacity
        user_capacity = []
        for user_id, stats in user_stats.items():
            daily_tasks = [
                {"date": d, "assigned": c, "estimatedHours": c * 0.5}
                for d, c in sorted(stats["dailyTasks"].items())
            ]
            avg_daily = stats["totalAssigned"] / max(len(stats["dailyTasks"]), 1)
            user_capacity.append({
                "id": stats["id"],
                "name": stats["name"],
                "role": stats["role"],
                "avgDailyCapacity": stats["avgDailyCapacity"],
                "totalAssigned": stats["totalAssigned"],
                "avgDailyAssigned": round(avg_daily, 1),
                "dailyTasks": daily_tasks,
                "capacityUtilization": min(100, round((avg_daily / stats["avgDailyCapacity"]) * 100)),
                "overCapacity": avg_daily > stats["avgDailyCapacity"],
                "completedToday": 0,
                "completedThisWeek": 0
            })

        total_tasks = sum(len(tasks) for tasks in tasks_by_day.values())

        return {
            "workflow_key": workflow_key,
            "tasks_by_day": tasks_by_day,
            "user_capacity": user_capacity,
            "total_tasks": total_tasks
        }

    except Exception as e:
        logger.error(f"Get upcoming tasks error: {e}")
        # Return empty structure on error
        return {
            "workflow_key": workflow_key,
            "tasks_by_day": {},
            "user_capacity": [],
            "total_tasks": 0,
            "error": "Internal server error"
        }
