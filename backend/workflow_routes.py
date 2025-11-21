"""
Pipeline 360 - Workflow System API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from datetime import date
import logging

from database import get_db
from workflow_service import (
    WorkflowEngine,
    ThemeDayService,
    LastMileService,
    PostClosingService,
    AIWorkflowAnalyzer
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workflow")


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
            SELECT wt.id, wt.loan_id, wt.lead_id, wt.task_type, wt.title,
                   wt.description, wt.priority, wt.due_date, wt.status,
                   wt.created_at, le.first_name, le.last_name
            FROM workflow_tasks wt
            JOIN leads le ON wt.lead_id = le.id
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

        query += " ORDER BY wt.due_date ASC LIMIT :limit"

        result = db.execute(text(query), params)
        tasks = [{
            "id": str(r[0]),
            "loan_id": r[1],
            "lead_id": r[2],
            "task_type": r[3],
            "title": r[4],
            "description": r[5],
            "priority": r[6],
            "due_date": r[7].isoformat() if r[7] else None,
            "status": r[8],
            "created_at": r[9].isoformat() if r[9] else None,
            "borrower": f"{r[10]} {r[11]}"
        } for r in result]

        return {"tasks": tasks, "count": len(tasks)}

    except Exception as e:
        logger.error(f"Get tasks error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
            SELECT wa.id, wa.loan_id, wa.lead_id, wa.alert_type, wa.message,
                   wa.severity, wa.acknowledged, wa.created_at,
                   le.first_name, le.last_name
            FROM workflow_alerts wa
            JOIN leads le ON wa.lead_id = le.id
            WHERE wa.acknowledged = :ack
        """
        params = {"ack": acknowledged, "limit": limit}

        if loan_id:
            query += " AND wa.loan_id = :loan_id"
            params["loan_id"] = loan_id

        if severity:
            query += " AND wa.severity = :severity"
            params["severity"] = severity

        query += " ORDER BY wa.created_at DESC LIMIT :limit"

        result = db.execute(text(query), params)
        alerts = [{
            "id": str(r[0]),
            "loan_id": r[1],
            "lead_id": r[2],
            "alert_type": r[3],
            "message": r[4],
            "severity": r[5],
            "acknowledged": r[6],
            "created_at": r[7].isoformat() if r[7] else None,
            "borrower": f"{r[8]} {r[9]}"
        } for r in result]

        return {"alerts": alerts, "count": len(alerts)}

    except Exception as e:
        logger.error(f"Get alerts error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
        query = """
            SELECT tds.id, tds.loan_id, tds.lead_id, tds.theme_name,
                   tds.scheduled_date, tds.message_content, tds.channel,
                   tds.status, le.first_name, le.last_name
            FROM theme_day_schedule tds
            JOIN leads le ON tds.lead_id = le.id
            WHERE 1=1
        """
        params = {"limit": limit}

        if date_filter:
            query += " AND tds.scheduled_date = :date"
            params["date"] = date_filter
        else:
            query += " AND tds.scheduled_date >= :today"
            params["today"] = date.today()

        if status:
            query += " AND tds.status = :status"
            params["status"] = status

        query += " ORDER BY tds.scheduled_date DESC LIMIT :limit"

        result = db.execute(text(query), params)
        messages = [{
            "id": str(r[0]),
            "loan_id": r[1],
            "lead_id": r[2],
            "theme_name": r[3],
            "scheduled_date": r[4].isoformat() if r[4] else None,
            "message": r[5],
            "channel": r[6],
            "status": r[7],
            "borrower": f"{r[8]} {r[9]}"
        } for r in result]

        return {"messages": messages, "count": len(messages)}

    except Exception as e:
        logger.error(f"Get scheduled messages error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
    status: Optional[str] = "scheduled",
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get scheduled post-closing calls"""
    try:
        result = db.execute(text("""
            SELECT pc.id, pc.loan_id, pc.lead_id, pc.call_purpose,
                   pc.scheduled_date, pc.status, le.first_name, le.last_name,
                   le.phone
            FROM post_closing_calls pc
            JOIN leads le ON pc.lead_id = le.id
            WHERE pc.status = :status
            ORDER BY pc.scheduled_date ASC
            LIMIT :limit
        """), {"status": status, "limit": limit}).fetchall()

        calls = [{
            "id": str(r[0]),
            "loan_id": r[1],
            "lead_id": r[2],
            "purpose": r[3],
            "scheduled_date": r[4].isoformat() if r[4] else None,
            "status": r[5],
            "borrower": f"{r[6]} {r[7]}",
            "phone": r[8]
        } for r in result]

        return {"calls": calls, "count": len(calls)}

    except Exception as e:
        logger.error(f"Get post-closing calls error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


# ============== Dashboard ==============

@router.get("/dashboard/summary")
async def get_workflow_dashboard(
    organization_id: int = 1,
    db: Session = Depends(get_db)
):
    """Get workflow dashboard summary"""
    try:
        # Pending tasks count
        pending_tasks = db.execute(text("""
            SELECT COUNT(*) FROM workflow_tasks wt
            JOIN leads le ON wt.lead_id = le.id
            WHERE le.organization_id = :org_id AND wt.status = 'pending'
        """), {"org_id": organization_id}).scalar() or 0

        # Overdue tasks
        overdue_tasks = db.execute(text("""
            SELECT COUNT(*) FROM workflow_tasks wt
            JOIN leads le ON wt.lead_id = le.id
            WHERE le.organization_id = :org_id
            AND wt.status = 'pending' AND wt.due_date < NOW()
        """), {"org_id": organization_id}).scalar() or 0

        # Unacknowledged alerts
        alerts = db.execute(text("""
            SELECT COUNT(*) FROM workflow_alerts wa
            JOIN leads le ON wa.lead_id = le.id
            WHERE le.organization_id = :org_id AND wa.acknowledged = FALSE
        """), {"org_id": organization_id}).scalar() or 0

        # Last Mile tasks today
        last_mile_today = db.execute(text("""
            SELECT COUNT(*) FROM last_mile_tasks lmt
            JOIN leads le ON lmt.lead_id = le.id
            WHERE le.organization_id = :org_id
            AND lmt.task_date = CURRENT_DATE AND lmt.status = 'pending'
        """), {"org_id": organization_id}).scalar() or 0

        # High risk loans
        high_risk = db.execute(text("""
            SELECT COUNT(DISTINCT loan_id) FROM ai_analysis
            WHERE risk_score >= 15
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
        raise HTTPException(status_code=500, detail=str(e))
