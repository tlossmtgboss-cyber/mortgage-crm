"""
Workflow Test Routes
====================
Routes extracted from main.py for workflow operations including:
- Workflow Automation Test Endpoints
- Stage History Endpoints
- Lead Conditions Endpoints
- Rate Lock Intelligence Endpoints
- Power Play Workflow Endpoints
- Document Intake Classification Endpoints
- Post-Closing Workflow Endpoints
"""

import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db

logger = logging.getLogger(__name__)

# ============================================================================
# ROUTER
# ============================================================================

def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1",
    tags=["Workflow Operations"],
    dependencies=[Depends(_get_current_user())],
)


# ============================================================================
# RUNTIME IMPORTS - To avoid circular imports
# ============================================================================

def get_current_user_dep():
    """Get current_user dependency from main at runtime"""
    import main
    return main.get_current_user

def get_current_user_flexible_dep():
    """Get current_user_flexible dependency from main at runtime"""
    import main
    return main.get_current_user_flexible

def get_models():
    """Get models from main at runtime"""
    import main
    return main

def get_filter_leads_by_permissions():
    """Get filter_leads_by_permissions from main at runtime"""
    import main
    return main.filter_leads_by_permissions


# ============================================================================
# ORG-SCOPED QUERY HELPERS (Multi-tenant IDOR prevention)
# ============================================================================

def _org_scoped_lead(db, lead_id, current_user):
    """Query Lead by ID scoped to the current user's organization."""
    import main
    Lead = main.Lead
    query = db.query(Lead).filter(Lead.id == lead_id)
    org_id = getattr(current_user, 'organization_id', None)
    if org_id:
        query = query.filter(Lead.organization_id == org_id)
    return query.first()


def _org_scoped_loan(db, loan_id, current_user):
    """Query Loan by ID scoped to the current user's organization."""
    import main
    Loan = main.Loan
    query = db.query(Loan).filter(Loan.id == loan_id)
    org_id = getattr(current_user, 'organization_id', None)
    if org_id:
        query = query.filter(Loan.organization_id == org_id)
    return query.first()


def _org_scoped_document_filter(current_user):
    """Return an org_id filter value for raw SQL document queries, or None if no scoping needed."""
    org_id = getattr(current_user, 'organization_id', None)
    return org_id if org_id else None


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

# Lead Conditions Models
class ConditionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: str = "other"
    priority: str = "required"
    due_date: Optional[str] = None
    status: str = "pending"
    notify_client: bool = True

class ConditionUpdate(BaseModel):
    status: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None


# Rate Lock Models
class RateLockAnalysisRequest(BaseModel):
    mbs_change_bps: Optional[float] = None
    treasury_10y_change_bps: Optional[float] = None
    days_to_close: Optional[int] = None
    borrower_risk_profile: Optional[str] = None

class RateLockAnalysisResponse(BaseModel):
    loan_id: int
    loan_number: str
    borrower_name: str
    is_eligible: bool
    eligibility_reason: Optional[str] = None
    lock_score: Optional[int] = None
    recommendation: Optional[str] = None
    recommendation_reason: Optional[str] = None
    days_to_close: Optional[int] = None
    risk_level: Optional[str] = None
    mbs_impact: Optional[str] = None
    treasury_impact: Optional[str] = None
    float_down_available: bool = False
    extension_analysis: Optional[dict] = None
    market_conditions: Optional[dict] = None


# Power Play Models
class PowerPlayTriggerRequest(BaseModel):
    trigger: str = "manual"  # new_lead, stage_change, timeline_update, scheduled_touch, etc.

class PowerPlayResponse(BaseModel):
    workflow_type: str
    entity_id: int
    entity_type: str
    status: str
    message: str
    actions_count: int
    next_touch_date: Optional[str] = None


# Document Intake Models
class EmailProcessRequest(BaseModel):
    from_email: str
    to_email: Optional[str] = None
    cc_emails: Optional[List[str]] = []
    subject: Optional[str] = ""
    body: Optional[str] = ""
    date: Optional[str] = None
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = []

class ClassifyAttachmentRequest(BaseModel):
    doc_type: str
    doc_category: str
    borrower_id: Optional[int] = None
    loan_id: Optional[int] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    notes: Optional[str] = None

class DiscardAttachmentRequest(BaseModel):
    reason: str

class UpdateMatchRequest(BaseModel):
    borrower_id: Optional[int] = None
    loan_id: Optional[int] = None


# ============================================================================
# WORKFLOW AUTOMATION TEST ENDPOINTS
# ============================================================================

@router.get("/workflows/test")
async def test_workflow_system(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Test the workflow automation system"""

    try:
        from workflows.workflow_engine import LeadWorkflowEngine, TimeBasedWorkflowEngine, WorkflowActionExecutor

        # Test workflow engine initialization
        workflow_engine = LeadWorkflowEngine(db)
        time_engine = TimeBasedWorkflowEngine(db)
        action_executor = WorkflowActionExecutor(db)

        return {
            "status": "operational",
            "components": {
                "lead_workflow_engine": "Ready",
                "time_based_engine": "Ready",
                "action_executor": "Ready",
                "sms_service": "Available" if action_executor.sms_client and action_executor.sms_client.enabled else "Not configured",
                "email_service": "Available" if action_executor.email_service else "Not configured"
            },
            "message": "Workflow automation system is operational"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": "Internal server error"
        }


@router.post("/workflows/test-status-change")
async def test_status_change_workflow(
    lead_id: int,
    new_status: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Test workflow by simulating a status change (dry run - does not update lead)"""
    import main
    LeadStatusChange = main.LeadStatusChange

    # Get the lead (org-scoped)
    lead = _org_scoped_lead(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Create status change event
    from workflows.workflow_engine import LeadWorkflowEngine

    status_change = LeadStatusChange(
        lead_id=lead.id,
        lead_name=lead.name,
        lead_email=lead.email,
        lead_phone=lead.phone,
        old_status=lead.stage.value if lead.stage else "None",
        new_status=new_status,
        loan_officer_id=1,  # Default to 1 for test
        loan_officer_name="Test User",
        loan_officer_email="test@example.com",
        loan_type=getattr(lead, 'loan_type', None),
        loan_amount=getattr(lead, 'loan_amount', None),
        changed_at=datetime.now(timezone.utc)
    )

    # Process workflow (dry run)
    workflow_engine = LeadWorkflowEngine(db)
    workflow_result = await workflow_engine.process_status_change(status_change)

    return {
        "lead_id": lead.id,
        "lead_name": lead.name,
        "simulated_transition": f"{status_change.old_status} -> {new_status}",
        "actions_generated": workflow_result.get("action_count", 0),
        "actions": workflow_result.get("actions", []),
        "note": "This is a dry run - no actions were executed and lead status was not changed"
    }


@router.post("/workflows/run-time-based")
async def run_time_based_workflows_manual(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Manually trigger time-based workflow checks"""
    from workflows.workflow_engine import TimeBasedWorkflowEngine, WorkflowActionExecutor

    time_engine = TimeBasedWorkflowEngine(db)
    actions = await time_engine.check_stale_leads()

    if actions:
        executor = WorkflowActionExecutor(db)
        result = await executor.execute_actions(actions)
        return {
            "status": "executed",
            "total_actions": result["total"],
            "successful": result["successful"],
            "failed": result["failed"],
            "skipped": result["skipped"],
            "details": result["details"]
        }
    else:
        return {
            "status": "no_actions",
            "message": "No stale leads found requiring action"
        }


@router.get("/workflows/status")
async def get_workflow_status(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Get workflow automation status and recent executions"""
    import main
    LeadStage = main.LeadStage
    scheduler = getattr(main, 'scheduler', None)

    try:
        # Get recent workflow executions
        result = db.execute(text("""
            SELECT workflow_name, trigger_event, execution_status, lead_id
            FROM workflow_executions
            ORDER BY id DESC
            LIMIT 10
        """))
        executions = [dict(row._mapping) for row in result.fetchall()]

        return {
            "scheduler_running": scheduler.running if scheduler and hasattr(scheduler, 'running') else False,
            "recent_executions": executions,
            "available_statuses": [s.value for s in LeadStage]
        }
    except Exception as e:
        return {
            "scheduler_running": scheduler.running if scheduler and hasattr(scheduler, 'running') else False,
            "recent_executions": [],
            "error": "Internal server error",
            "available_statuses": [s.value for s in LeadStage] if 'LeadStage' in dir() else []
        }


# ============================================================================
# STAGE HISTORY ENDPOINTS
# ============================================================================

@router.get("/leads/{lead_id}/stage-history")
async def get_lead_stage_history(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Get the complete stage history for a lead"""
    import main
    StageHistory = main.StageHistory

    # Verify lead exists and user has access (org-scoped)
    lead = _org_scoped_lead(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Get stage history ordered by date (newest first)
    history = db.query(StageHistory).filter(
        StageHistory.lead_id == lead_id
    ).order_by(StageHistory.changed_at.desc()).all()

    return {
        "lead_id": lead_id,
        "lead_name": lead.name,
        "current_stage": lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage) if lead.stage else None,
        "stage_history": [
            {
                "id": h.id,
                "from_stage": h.from_stage,
                "to_stage": h.to_stage,
                "changed_at": h.changed_at.isoformat() if h.changed_at else None,
                "changed_by_id": h.changed_by_id,
                "duration_in_previous_stage": h.duration_in_previous_stage,
                "notes": h.notes
            }
            for h in history
        ]
    }


@router.get("/leads/{lead_id}/chat-messages")
async def get_lead_chat_messages(
    lead_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Get Sarah AI chat messages associated with a lead"""

    # Verify lead exists and user has access (org-scoped)
    lead = _org_scoped_lead(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    messages = []

    # Get chat sessions linked to this lead from chat_sessions table
    try:
        # First check if tables exist
        table_check = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'chat_sessions'
            )
        """)).scalar()

        if table_check:
            # Get all chat sessions for this lead with their messages
            sessions_result = db.execute(text("""
                SELECT cs.id, cs.visitor_id, cs.contact_name, cs.contact_email,
                       cs.current_phase, cs.intent_score, cs.created_at as session_started
                FROM chat_sessions cs
                WHERE cs.lead_id = :lead_id
                ORDER BY cs.created_at DESC
            """), {"lead_id": lead_id})

            session_ids = []
            sessions_info = {}
            for row in sessions_result:
                session_id = row[0]
                session_ids.append(session_id)
                sessions_info[str(session_id)] = {
                    "visitor_id": row[1],
                    "contact_name": row[2],
                    "contact_email": row[3],
                    "phase": row[4],
                    "intent_score": row[5],
                    "session_started": row[6].isoformat() if row[6] else None
                }

            # Get messages from those sessions
            if session_ids:
                messages_result = db.execute(text("""
                    SELECT cm.id, cm.session_id, cm.role, cm.content, cm.turn_number,
                           cm.phase_at_message, cm.created_at
                    FROM chat_messages cm
                    WHERE cm.session_id = ANY(:session_ids)
                    ORDER BY cm.created_at DESC
                    LIMIT :limit
                """), {"session_ids": session_ids, "limit": limit})

                for row in messages_result:
                    session_id_str = str(row[1])
                    session_info = sessions_info.get(session_id_str, {})
                    messages.append({
                        "id": str(row[0]),
                        "session_id": session_id_str,
                        "role": row[2],
                        "content": row[3],
                        "turn_number": row[4],
                        "phase": row[5],
                        "created_at": row[6].isoformat() if row[6] else None,
                        "contact_name": session_info.get("contact_name"),
                        "type": "sarah_ai_chat"
                    })
    except Exception as e:
        logger.warning(f"Error fetching chat messages for lead {lead_id}: {e}")

    # Also try to get messages from ai_chat_sessions table (alternative table name)
    try:
        alt_table_check = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'ai_chat_sessions'
            )
        """)).scalar()

        if alt_table_check:
            alt_messages = db.execute(text("""
                SELECT acs.id, acs.session_id, acm.role, acm.content, acm.created_at
                FROM ai_chat_sessions acs
                JOIN ai_chat_messages acm ON acm.session_id = acs.id
                WHERE acs.lead_id = :lead_id
                ORDER BY acm.created_at DESC
                LIMIT :limit
            """), {"lead_id": lead_id, "limit": limit})

            for row in alt_messages:
                messages.append({
                    "id": str(row[0]),
                    "session_id": str(row[1]),
                    "role": row[2],
                    "content": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                    "type": "sarah_ai_chat"
                })
    except Exception as e:
        logger.debug(f"ai_chat_sessions table not found or error: {e}")

    # Sort all messages by created_at descending
    messages.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    return {
        "lead_id": lead_id,
        "lead_name": lead.name,
        "messages": messages[:limit],
        "total": len(messages)
    }


@router.get("/leads/{lead_id}/circle-contacts")
async def get_lead_circle_contacts(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Get the circle of cash flow contacts for a lead (trusted professionals from questionnaire)"""

    # Verify lead exists and user has access (org-scoped)
    lead = _org_scoped_lead(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Get circle contacts from database
    result = db.execute(text("""
        SELECT id, name, email, phone, type, notes, rating, source, created_at, updated_at
        FROM circle_contacts
        WHERE lead_id = :lead_id
        ORDER BY type, created_at
    """), {"lead_id": lead_id})

    contacts = []
    for row in result:
        contacts.append({
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "phone": row[3],
            "type": row[4],
            "notes": row[5],
            "rating": row[6],
            "source": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "updated_at": row[9].isoformat() if row[9] else None
        })

    return {
        "lead_id": lead_id,
        "lead_name": lead.name,
        "contacts": contacts,
        "total": len(contacts)
    }


# ============================================================================
# LEAD CONDITIONS ENDPOINTS (for Needs List / Client Portal integration)
# ============================================================================

@router.get("/leads/{lead_id}/conditions")
async def get_lead_conditions(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Get all conditions/needs list items for a lead"""

    # Verify lead exists and user has access (org-scoped)
    lead = _org_scoped_lead(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    conditions = []

    # Get conditions from lead_conditions table using raw SQL (table may not exist yet)
    try:
        result = db.execute(text("""
            SELECT id, name, description, category, priority, due_date, status, is_new, created_at, updated_at
            FROM lead_conditions
            WHERE lead_id = :lead_id
            ORDER BY
                CASE priority WHEN 'required' THEN 1 WHEN 'recommended' THEN 2 ELSE 3 END,
                created_at DESC
        """), {"lead_id": lead_id})

        for row in result:
            conditions.append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "category": row[3],
                "priority": row[4],
                "due_date": row[5].isoformat() if row[5] else None,
                "status": row[6],
                "is_new": row[7],
                "created_at": row[8].isoformat() if row[8] else None,
                "updated_at": row[9].isoformat() if row[9] else None,
                "source": "lead_conditions"
            })
    except Exception as e:
        # Table might not exist yet
        logger.warning(f"Error fetching lead_conditions: {e}")

    # Also fetch Smart Docs document requests if there's a linked loan
    try:
        # First try by loan_number pattern
        loan_number_pattern = f"APP-{lead_id:06d}"
        loan_result = db.execute(text("""
            SELECT id FROM loans WHERE loan_number LIKE :pattern LIMIT 1
        """), {"pattern": f"{loan_number_pattern}%"}).first()

        # If not found, try by email match
        if not loan_result and lead.email:
            loan_result = db.execute(text("""
                SELECT id FROM loans WHERE borrower_email = :email ORDER BY created_at DESC LIMIT 1
            """), {"email": lead.email}).first()

        if loan_result:
            loan_id = loan_result[0]
            # Fetch document requests from Smart Docs (smart_document_requests table)
            doc_requests = db.execute(text("""
                SELECT id, title, description, priority, due_date, status, created_at
                FROM smart_document_requests
                WHERE loan_id = :loan_id AND is_active = true
                ORDER BY
                    CASE priority WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'NORMAL' THEN 3 ELSE 4 END,
                    created_at DESC
            """), {"loan_id": loan_id})

            for row in doc_requests:
                # Map Smart Docs status to condition status
                status = row[5]
                if status in ['ACCEPTED', 'WAIVED']:
                    mapped_status = 'approved'
                elif status == 'PENDING_REVIEW':
                    mapped_status = 'received'
                else:
                    mapped_status = 'pending'

                # Map priority
                priority = row[3]
                if priority in ['CRITICAL', 'HIGH']:
                    mapped_priority = 'required'
                else:
                    mapped_priority = 'recommended'

                conditions.append({
                    "id": f"doc_{row[0]}",  # Prefix to avoid ID conflicts
                    "name": row[1],
                    "description": row[2],
                    "category": "document",
                    "priority": mapped_priority,
                    "due_date": row[4].isoformat() if row[4] else None,
                    "status": mapped_status,
                    "is_new": False,
                    "created_at": row[6].isoformat() if row[6] else None,
                    "updated_at": None,
                    "source": "smart_docs",
                    "loan_id": loan_id
                })
    except Exception as e:
        logger.warning(f"Error fetching Smart Docs conditions from smart_document_requests: {e}")

    return {"conditions": conditions, "total": len(conditions)}


@router.post("/leads/{lead_id}/conditions")
async def create_lead_condition(
    lead_id: int,
    condition: ConditionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Create a new condition/needs list item for a lead"""

    # Verify lead exists and user has access (org-scoped)
    lead = _org_scoped_lead(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        # Insert condition
        result = db.execute(text("""
            INSERT INTO lead_conditions (lead_id, name, description, category, priority, due_date, status, is_new, created_by_id, created_at, updated_at)
            VALUES (:lead_id, :name, :description, :category, :priority, :due_date, :status, true, :created_by, NOW(), NOW())
            RETURNING id, name, description, category, priority, due_date, status, is_new, created_at, updated_at
        """), {
            "lead_id": lead_id,
            "name": condition.name,
            "description": condition.description,
            "category": condition.category,
            "priority": condition.priority,
            "due_date": condition.due_date if condition.due_date else None,
            "status": condition.status,
            "created_by": getattr(current_user, 'id', 1)
        })
        db.commit()

        row = result.fetchone()
        new_condition = {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "category": row[3],
            "priority": row[4],
            "due_date": row[5].isoformat() if row[5] else None,
            "status": row[6],
            "is_new": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "updated_at": row[9].isoformat() if row[9] else None
        }

        # If notify_client is true, create notification for client portal
        if condition.notify_client and lead.email:
            try:
                # Create notification record
                db.execute(text("""
                    INSERT INTO notifications (user_id, lead_id, type, title, message, is_read, created_at)
                    VALUES (
                        (SELECT id FROM users WHERE email = :lead_email LIMIT 1),
                        :lead_id, 'condition_requested', 'New Document Requested',
                        :message, false, NOW()
                    )
                """), {
                    "lead_email": lead.email,
                    "lead_id": lead_id,
                    "message": f"A new document has been requested: {condition.name}"
                })
                db.commit()
            except Exception as notify_error:
                logger.warning(f"Failed to create notification: {notify_error}")

        return {"condition": new_condition, "message": "Condition created successfully"}
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating condition: {e}")
        raise HTTPException(status_code=500, detail="Failed to create condition")


@router.patch("/leads/{lead_id}/conditions/{condition_id}")
async def update_lead_condition(
    lead_id: int,
    condition_id: int,
    condition_update: ConditionUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Update a condition status"""

    # Verify lead exists and user has access (org-scoped)
    lead = _org_scoped_lead(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        # Build update query dynamically
        updates = ["updated_at = NOW()", "is_new = false"]
        params = {"condition_id": condition_id, "lead_id": lead_id}

        if condition_update.status:
            updates.append("status = :status")
            params["status"] = condition_update.status
        if condition_update.description:
            updates.append("description = :description")
            params["description"] = condition_update.description
        if condition_update.due_date:
            updates.append("due_date = :due_date")
            params["due_date"] = condition_update.due_date

        result = db.execute(text(f"""
            UPDATE lead_conditions
            SET {', '.join(updates)}
            WHERE id = :condition_id AND lead_id = :lead_id
            RETURNING id, name, description, category, priority, due_date, status, is_new, created_at, updated_at
        """), params)
        db.commit()

        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Condition not found")

        updated_condition = {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "category": row[3],
            "priority": row[4],
            "due_date": row[5].isoformat() if row[5] else None,
            "status": row[6],
            "is_new": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "updated_at": row[9].isoformat() if row[9] else None
        }

        return {"condition": updated_condition, "message": "Condition updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating condition: {e}")
        raise HTTPException(status_code=500, detail="Failed to update condition")


@router.delete("/leads/{lead_id}/conditions/{condition_id}")
async def delete_lead_condition(
    lead_id: int,
    condition_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Delete a condition"""

    # Verify lead exists and user has access (org-scoped)
    lead = _org_scoped_lead(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        result = db.execute(text("""
            DELETE FROM lead_conditions WHERE id = :condition_id AND lead_id = :lead_id RETURNING id
        """), {"condition_id": condition_id, "lead_id": lead_id})
        db.commit()

        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Condition not found")

        return {"message": "Condition deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting condition: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete condition")


@router.get("/leads/{lead_id}/team-assignments")
async def get_lead_team_assignments(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Get team assignments for a lead including owner, processor, and other assigned team members"""
    import main
    User = main.User

    # Verify lead exists and user has access (org-scoped)
    lead = _org_scoped_lead(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        # Get owner details
        owner = None
        if lead.owner_id:
            owner_user = db.query(User).filter(User.id == lead.owner_id).first()
            if owner_user:
                owner = {
                    "user_id": owner_user.id,
                    "name": owner_user.name,
                    "email": owner_user.email,
                    "role": "Loan Officer"
                }

        # Build team assignments list
        team_assignments = []

        # Add owner as primary team member
        if owner:
            team_assignments.append({
                "role": "Loan Officer",
                "user_id": owner["user_id"],
                "name": owner["name"],
                "email": owner["email"],
                "is_primary": True
            })

        # Add processor if specified
        if lead.processor:
            team_assignments.append({
                "role": "Processor",
                "user_id": None,
                "name": lead.processor,
                "email": None,
                "is_primary": False
            })

        # Add underwriter if specified
        if lead.underwriter:
            team_assignments.append({
                "role": "Underwriter",
                "user_id": None,
                "name": lead.underwriter,
                "email": None,
                "is_primary": False
            })

        return {
            "lead_id": lead_id,
            "lead_name": lead.name,
            "team_assignments": team_assignments,
            "total_assignments": len(team_assignments)
        }
    except Exception as e:
        logger.error(f"Error getting lead team assignments: {e}")
        raise HTTPException(status_code=500, detail="Failed to get team assignments")


@router.get("/loans/{loan_id}/stage-history")
async def get_loan_stage_history(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """Get the complete stage history for a loan"""
    import main
    StageHistory = main.StageHistory

    # Verify loan exists and user has access (org-scoped)
    loan = _org_scoped_loan(db, loan_id, current_user)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Get stage history ordered by date (newest first)
    history = db.query(StageHistory).filter(
        StageHistory.loan_id == loan_id
    ).order_by(StageHistory.changed_at.desc()).all()

    return {
        "loan_id": loan_id,
        "loan_number": loan.loan_number,
        "borrower_name": loan.borrower_name,
        "current_stage": loan.stage.value if hasattr(loan.stage, 'value') else str(loan.stage) if loan.stage else None,
        "stage_history": [
            {
                "id": h.id,
                "from_stage": h.from_stage,
                "to_stage": h.to_stage,
                "changed_at": h.changed_at.isoformat() if h.changed_at else None,
                "changed_by_id": h.changed_by_id,
                "duration_in_previous_stage": h.duration_in_previous_stage,
                "notes": h.notes
            }
            for h in history
        ]
    }


# ============================================================================
# RATE LOCK INTELLIGENCE ENDPOINTS
# ============================================================================

@router.get("/loans/{loan_id}/rate-lock-analysis", response_model=RateLockAnalysisResponse)
async def get_rate_lock_analysis(
    loan_id: int,
    mbs_change_bps: Optional[float] = Query(None, description="MBS price change in basis points"),
    treasury_10y_change_bps: Optional[float] = Query(None, description="10Y Treasury change in basis points"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Get comprehensive rate lock analysis for a loan.

    The Rate Lock Intelligence Engine analyzes:
    - Lock eligibility based on loan stage
    - Lock score (0-100) based on market conditions and days to close
    - Recommendation (Lock Now, Float and Monitor, etc.)
    - Float-down opportunities
    - Extension strategy if lock is expiring
    """
    from workflows.rate_lock_engine import RateLockIntelligenceEngine

    # Verify loan exists and user has access (org-scoped)
    loan = _org_scoped_loan(db, loan_id, current_user)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Initialize the Rate Lock Intelligence Engine
    engine = RateLockIntelligenceEngine(loan, db)

    # Run full analysis
    analysis = engine.run_full_analysis(
        mbs_change_bps=mbs_change_bps,
        treasury_10y_change_bps=treasury_10y_change_bps
    )

    # Build response
    return RateLockAnalysisResponse(
        loan_id=loan.id,
        loan_number=loan.loan_number,
        borrower_name=loan.borrower_name,
        is_eligible=analysis.is_eligible,
        eligibility_reason=analysis.eligibility_reason,
        lock_score=analysis.lock_score,
        recommendation=analysis.recommendation.value if analysis.recommendation else None,
        recommendation_reason=analysis.recommendation_reason,
        days_to_close=analysis.days_to_close,
        risk_level=analysis.risk_level,
        mbs_impact=analysis.mbs_impact,
        treasury_impact=analysis.treasury_impact,
        float_down_available=analysis.float_down_available,
        extension_analysis=analysis.extension_analysis,
        market_conditions=analysis.market_conditions
    )


@router.post("/loans/{loan_id}/rate-lock-action")
async def execute_rate_lock_action(
    loan_id: int,
    action: str = Query(..., description="Action: lock, float, extend, relock"),
    lock_term_days: Optional[int] = Query(None, description="Lock term in days (for lock action)"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Execute a rate lock action on a loan.

    Actions:
    - lock: Lock the rate (requires lock_term_days)
    - float: Enter float monitoring mode
    - extend: Extend an existing lock
    - relock: Relock after expiration
    """
    import main
    RateLockStatus = main.RateLockStatus
    RateLockRecommendation = main.RateLockRecommendation

    from workflows.rate_lock_engine import RateLockIntelligenceEngine

    # Verify loan exists and user has access (org-scoped)
    loan = _org_scoped_loan(db, loan_id, current_user)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    engine = RateLockIntelligenceEngine(loan, db)

    # Initialize history if needed
    if not loan.rate_lock_history:
        loan.rate_lock_history = []

    history_entry = {
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": 1,  # Default user
        "previous_status": loan.rate_lock_status.value if loan.rate_lock_status else None
    }

    if action == "lock":
        if not lock_term_days:
            raise HTTPException(status_code=400, detail="lock_term_days required for lock action")

        # Check eligibility first
        is_eligible, reason = engine.check_eligibility()
        if not is_eligible:
            raise HTTPException(status_code=400, detail=f"Loan not eligible for rate lock: {reason}")

        loan.rate_lock_status = RateLockStatus.LOCKED
        loan.lock_term_days = lock_term_days
        loan.rate_lock_date = datetime.now(timezone.utc).date()
        loan.rate_lock_expiration = (datetime.now(timezone.utc) + timedelta(days=lock_term_days)).date()
        history_entry["lock_term_days"] = lock_term_days
        history_entry["expiration"] = loan.rate_lock_expiration.isoformat()

        message = f"Rate locked for {lock_term_days} days. Expires {loan.rate_lock_expiration}"

    elif action == "float":
        loan.rate_lock_status = RateLockStatus.FLOAT_MONITORING
        loan.rate_lock_recommendation = RateLockRecommendation.FLOAT_AND_MONITOR
        message = "Entered float monitoring mode. Will alert on favorable market movements."

    elif action == "extend":
        if loan.rate_lock_status != RateLockStatus.LOCKED:
            raise HTTPException(status_code=400, detail="Can only extend an active lock")

        # Calculate extension
        extension_analysis = engine.analyze_extension_strategy()
        extension_days = extension_analysis.get("recommended_extension_days", 15)

        loan.rate_lock_status = RateLockStatus.LOCK_EXTENDED
        old_expiration = loan.rate_lock_expiration
        loan.rate_lock_expiration = (datetime.now(timezone.utc) + timedelta(days=extension_days)).date()
        loan.lock_term_days = (loan.lock_term_days or 0) + extension_days

        history_entry["extension_days"] = extension_days
        history_entry["old_expiration"] = old_expiration.isoformat() if old_expiration else None
        history_entry["new_expiration"] = loan.rate_lock_expiration.isoformat()

        message = f"Lock extended by {extension_days} days. New expiration: {loan.rate_lock_expiration}"

    elif action == "relock":
        if loan.rate_lock_status not in [RateLockStatus.LOCK_EXPIRED, RateLockStatus.LOCK_EXPIRING]:
            raise HTTPException(status_code=400, detail="Relock only available for expired or expiring locks")

        loan.rate_lock_status = RateLockStatus.LOCKED
        loan.rate_lock_date = datetime.now(timezone.utc).date()
        loan.rate_lock_expiration = (datetime.now(timezone.utc) + timedelta(days=lock_term_days or 30)).date()
        loan.lock_term_days = lock_term_days or 30

        message = f"Rate relocked for {loan.lock_term_days} days"

    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}. Use: lock, float, extend, relock")

    # Update history
    loan.rate_lock_history = loan.rate_lock_history + [history_entry]

    db.commit()
    logger.info(f"Rate lock action '{action}' executed for loan {loan_id}")

    return {
        "success": True,
        "loan_id": loan_id,
        "action": action,
        "message": message,
        "new_status": loan.rate_lock_status.value,
        "rate_lock_expiration": loan.rate_lock_expiration.isoformat() if loan.rate_lock_expiration else None
    }


@router.get("/rate-lock/dashboard")
async def get_rate_lock_dashboard(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep()),
):
    """
    Get rate lock dashboard showing all loans and their lock status.

    Returns:
    - Summary counts by status
    - Loans requiring attention (expiring soon, high volatility)
    - Market conditions summary
    """
    import main
    Loan = main.Loan
    LoanStage = main.LoanStage
    RateLockStatus = main.RateLockStatus

    from workflows.rate_lock_engine import RateLockIntelligenceEngine

    # Get loans in lockable stages scoped to user's organization
    lockable_stages = [LoanStage.PROCESSING, LoanStage.SUBMITTED, LoanStage.UNDERWRITING, LoanStage.CONDITIONAL_APPROVAL, LoanStage.CTC]
    query = db.query(Loan).filter(Loan.stage.in_(lockable_stages))
    if hasattr(current_user, 'organization_id') and current_user.organization_id:
        query = query.filter(Loan.organization_id == current_user.organization_id)
    loans = query.all()

    # Categorize by status
    status_counts = {
        "not_eligible": 0,
        "eligible_no_lock": 0,
        "locked": 0,
        "float_monitoring": 0,
        "lock_expiring": 0,
        "lock_expired": 0
    }

    attention_needed = []

    for loan in loans:
        status = loan.rate_lock_status or RateLockStatus.NOT_ELIGIBLE

        # Count by status
        if status == RateLockStatus.NOT_ELIGIBLE:
            status_counts["not_eligible"] += 1
        elif status == RateLockStatus.ELIGIBLE_NO_LOCK:
            status_counts["eligible_no_lock"] += 1
        elif status == RateLockStatus.LOCKED:
            status_counts["locked"] += 1
            # Check if expiring soon
            if loan.rate_lock_expiration:
                days_until_expiration = (loan.rate_lock_expiration - datetime.now(timezone.utc).date()).days
                if days_until_expiration <= 5:
                    attention_needed.append({
                        "loan_id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower_name": loan.borrower_name,
                        "issue": "Lock expiring soon",
                        "days_until_expiration": days_until_expiration,
                        "priority": "high" if days_until_expiration <= 2 else "medium"
                    })
        elif status == RateLockStatus.FLOAT_MONITORING:
            status_counts["float_monitoring"] += 1
        elif status == RateLockStatus.LOCK_EXPIRING:
            status_counts["lock_expiring"] += 1
            attention_needed.append({
                "loan_id": loan.id,
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "issue": "Lock expiring",
                "priority": "high"
            })
        elif status == RateLockStatus.LOCK_EXPIRED:
            status_counts["lock_expired"] += 1
            attention_needed.append({
                "loan_id": loan.id,
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "issue": "Lock expired - needs relock",
                "priority": "critical"
            })

    # Get loans with high volatility scores (org-scoped)
    high_vol_query = db.query(Loan).filter(Loan.volatility_score >= 70)
    if hasattr(current_user, 'organization_id') and current_user.organization_id:
        high_vol_query = high_vol_query.filter(Loan.organization_id == current_user.organization_id)
    high_volatility_loans = high_vol_query.all()

    for loan in high_volatility_loans:
        if not any(a["loan_id"] == loan.id for a in attention_needed):
            attention_needed.append({
                "loan_id": loan.id,
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "issue": f"High market volatility (score: {loan.volatility_score})",
                "priority": "medium"
            })

    return {
        "total_loans": len(loans),
        "status_summary": status_counts,
        "attention_needed": sorted(attention_needed, key=lambda x: {"critical": 0, "high": 1, "medium": 2}.get(x["priority"], 3)),
        "market_snapshot": {
            "note": "Connect to real-time market data for live MBS/Treasury feeds",
            "recommendation": "Review loans in float monitoring mode for lock opportunities"
        }
    }


@router.post("/rate-lock/bulk-analysis")
async def bulk_rate_lock_analysis(
    mbs_change_bps: Optional[float] = Query(None, description="MBS price change in basis points"),
    treasury_10y_change_bps: Optional[float] = Query(None, description="10Y Treasury change in basis points"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Run rate lock analysis on all eligible loans.

    Useful for daily morning analysis when market data is available.
    Returns recommendations for all loans that should be locked or monitored.
    """
    import main
    Loan = main.Loan
    LoanStage = main.LoanStage
    RateLockRecommendation = main.RateLockRecommendation

    from workflows.rate_lock_engine import RateLockIntelligenceEngine

    # Get all loans in lockable stages (org-scoped)
    lockable_stages = [LoanStage.PROCESSING, LoanStage.SUBMITTED, LoanStage.UNDERWRITING, LoanStage.CONDITIONAL_APPROVAL, LoanStage.CTC]
    query = db.query(Loan).filter(Loan.stage.in_(lockable_stages))
    if hasattr(current_user, 'organization_id') and current_user.organization_id:
        query = query.filter(Loan.organization_id == current_user.organization_id)
    loans = query.all()

    results = {
        "lock_now": [],
        "float_and_monitor": [],
        "extend_lock": [],
        "relock": [],
        "not_eligible": []
    }

    for loan in loans:
        engine = RateLockIntelligenceEngine(loan, db)
        analysis = engine.run_full_analysis(
            mbs_change_bps=mbs_change_bps,
            treasury_10y_change_bps=treasury_10y_change_bps
        )

        loan_summary = {
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "borrower_name": loan.borrower_name,
            "lock_score": analysis.lock_score,
            "days_to_close": analysis.days_to_close,
            "risk_level": analysis.risk_level,
            "reason": analysis.recommendation_reason
        }

        if not analysis.is_eligible:
            results["not_eligible"].append(loan_summary)
        elif analysis.recommendation == RateLockRecommendation.LOCK_NOW:
            results["lock_now"].append(loan_summary)
        elif analysis.recommendation == RateLockRecommendation.FLOAT_AND_MONITOR:
            results["float_and_monitor"].append(loan_summary)
        elif analysis.recommendation == RateLockRecommendation.EXTEND_LOCK:
            results["extend_lock"].append(loan_summary)
        elif analysis.recommendation == RateLockRecommendation.RELOCK:
            results["relock"].append(loan_summary)

    # Sort lock_now by score (highest first - most urgent)
    results["lock_now"] = sorted(results["lock_now"], key=lambda x: x["lock_score"] or 0, reverse=True)

    return {
        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
        "market_inputs": {
            "mbs_change_bps": mbs_change_bps,
            "treasury_10y_change_bps": treasury_10y_change_bps
        },
        "total_analyzed": len(loans),
        "recommendations": results,
        "summary": {
            "lock_now_count": len(results["lock_now"]),
            "float_count": len(results["float_and_monitor"]),
            "extend_count": len(results["extend_lock"]),
            "relock_count": len(results["relock"]),
            "not_eligible_count": len(results["not_eligible"])
        }
    }


# ============================================================================
# POWER PLAY WORKFLOW ENDPOINTS
# ============================================================================

@router.post("/leads/{lead_id}/power-play", response_model=PowerPlayResponse)
async def trigger_lead_power_play(
    lead_id: int,
    request: PowerPlayTriggerRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Trigger the appropriate Power Play workflow for a lead.

    The engine automatically determines which Power Play applies:
    - Prospect Power Play: Active buyers with timeline-based touches
    - PreQual Power Play: Soft-pulled, document collection focus
    - Pre-Approved Power Play: House hunting, rate lock ready
    - Long-Term Nurture Power Play: 10+ month buyers, monthly touches

    Triggers:
    - new_lead: New lead created
    - stage_change: Lead stage changed
    - timeline_update: Buying timeline updated
    - scheduled_touch: Time-based touch due
    - manual: Manual trigger
    """
    import main
    Task = main.Task

    from workflows.power_play_engine import PowerPlayEngine

    # Verify lead exists and user has access (org-scoped)
    lead = _org_scoped_lead(db, lead_id, current_user)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    engine = PowerPlayEngine(db)
    result = engine.process_lead_workflow(lead, trigger=request.trigger)

    # Execute actions (create tasks, etc.)
    actions_executed = await _execute_power_play_actions(result.actions, lead, db, Task)

    # Update next touch date on lead
    if result.next_touch_date:
        lead.next_touch_date = result.next_touch_date
        db.commit()

    logger.info(f"Power Play triggered for lead {lead_id}: {result.workflow_type.value}")

    return PowerPlayResponse(
        workflow_type=result.workflow_type.value,
        entity_id=result.entity_id,
        entity_type=result.entity_type,
        status=result.status,
        message=result.message,
        actions_count=len(result.actions),
        next_touch_date=result.next_touch_date.isoformat() if result.next_touch_date else None
    )


@router.post("/loans/{loan_id}/power-play", response_model=PowerPlayResponse)
async def trigger_loan_power_play(
    loan_id: int,
    request: PowerPlayTriggerRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Trigger Under Contract Power Play for an active loan.

    Integrates with Rate Lock Intelligence for lock decisions.

    Triggers:
    - new_contract: Just went under contract
    - milestone_reached: Loan reached new milestone
    - rate_lock_expiring: Rate lock expiration warning
    - closing_approaching: Closing date approaching
    - manual: Manual trigger
    """
    import main
    Task = main.Task

    from workflows.power_play_engine import PowerPlayEngine

    # Verify loan exists and user has access (org-scoped)
    loan = _org_scoped_loan(db, loan_id, current_user)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    engine = PowerPlayEngine(db)
    result = engine.process_loan_workflow(loan, trigger=request.trigger)

    # Execute actions
    actions_executed = await _execute_power_play_actions(result.actions, loan, db, main.Task)

    logger.info(f"Under Contract Power Play triggered for loan {loan_id}")

    return PowerPlayResponse(
        workflow_type=result.workflow_type.value,
        entity_id=result.entity_id,
        entity_type=result.entity_type,
        status=result.status,
        message=result.message,
        actions_count=len(result.actions),
        next_touch_date=result.next_touch_date.isoformat() if result.next_touch_date else None
    )


@router.get("/power-play/dashboard")
async def get_power_play_dashboard(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep()),
):
    """
    Get Power Play workflow dashboard showing leads/loans by workflow type.

    Returns counts and lists for each Power Play category.
    """
    import main
    Lead = main.Lead
    Loan = main.Loan
    LoanStage = main.LoanStage

    from workflows.power_play_engine import PowerPlayEngine

    engine = PowerPlayEngine(db)

    # Get leads scoped to user's organization
    lead_query = db.query(Lead)
    if hasattr(current_user, 'organization_id') and current_user.organization_id:
        lead_query = lead_query.filter(Lead.organization_id == current_user.organization_id)
    leads = lead_query.all()

    workflow_counts = {
        "prospect": [],
        "prequal": [],
        "pre_approved": [],
        "long_term_nurture": [],
        "under_contract": []
    }

    touches_due_today = []
    touches_due_this_week = []

    now = datetime.now(timezone.utc)
    week_from_now = now + timedelta(days=7)

    for lead in leads:
        workflow_type = engine._determine_lead_workflow(lead)

        lead_summary = {
            "id": lead.id,
            "name": lead.name,
            "stage": lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage),
            "timeline": getattr(lead, 'buying_timeline_category', None),
            "next_touch": getattr(lead, 'next_touch_date', None)
        }

        if workflow_type:
            type_key = workflow_type.value.replace("_power_play", "")
            if type_key in workflow_counts:
                workflow_counts[type_key].append(lead_summary)

        # Check for due touches
        next_touch = getattr(lead, 'next_touch_date', None)
        if next_touch:
            if isinstance(next_touch, datetime):
                if next_touch <= now:
                    touches_due_today.append(lead_summary)
                elif next_touch <= week_from_now:
                    touches_due_this_week.append(lead_summary)

    # Get active loans for Under Contract (scoped to organization)
    loan_query = db.query(Loan).filter(
        Loan.stage.in_([LoanStage.PROCESSING, LoanStage.SUBMITTED, LoanStage.UNDERWRITING,
                        LoanStage.CONDITIONAL_APPROVAL, LoanStage.CTC, LoanStage.DOCS_OUT])
    )
    if hasattr(current_user, 'organization_id') and current_user.organization_id:
        loan_query = loan_query.filter(Loan.organization_id == current_user.organization_id)
    active_loans = loan_query.all()

    for loan in active_loans:
        workflow_counts["under_contract"].append({
            "id": loan.id,
            "loan_number": loan.loan_number,
            "borrower_name": loan.borrower_name,
            "stage": loan.stage.value if hasattr(loan.stage, 'value') else str(loan.stage),
            "rate_lock_status": loan.rate_lock_status.value if loan.rate_lock_status else "Not Set"
        })

    return {
        "workflow_summary": {
            "prospect_count": len(workflow_counts["prospect"]),
            "prequal_count": len(workflow_counts["prequal"]),
            "pre_approved_count": len(workflow_counts["pre_approved"]),
            "long_term_nurture_count": len(workflow_counts["long_term_nurture"]),
            "under_contract_count": len(workflow_counts["under_contract"])
        },
        "touches_due": {
            "today": touches_due_today,
            "this_week": touches_due_this_week
        },
        "workflows": workflow_counts
    }


@router.post("/power-play/run-scheduled-touches")
async def run_scheduled_touches(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Run all scheduled touches that are due.

    This should be called periodically (e.g., daily) to process time-based workflows.
    """
    from workflows.power_play_engine import PowerPlayScheduler

    scheduler = PowerPlayScheduler(db)
    results = await scheduler.run_scheduled_touches()

    return {
        "success": True,
        "touches_processed": len(results),
        "results": [
            {
                "entity_id": r.entity_id,
                "workflow": r.workflow_type.value,
                "actions": len(r.actions),
                "next_touch": r.next_touch_date.isoformat() if r.next_touch_date else None
            }
            for r in results
        ]
    }


async def _execute_power_play_actions(actions: list, entity: Any, db: Session, Task) -> int:
    """Execute Power Play actions (create tasks, send alerts, etc.)"""
    from workflows.power_play_engine import WorkflowActionType

    executed = 0

    for action in actions:
        try:
            if action.action_type == WorkflowActionType.TASK:
                # Create task
                task_data = action.data
                due_date = datetime.now(timezone.utc) + timedelta(hours=task_data.get("due_hours", 24))

                task = Task(
                    title=task_data.get("title", "Power Play Task"),
                    description=task_data.get("description", ""),
                    due_date=due_date,
                    priority=task_data.get("priority", "medium"),
                    status="pending",
                    owner_id=1,  # Default owner
                    loan_id=task_data.get("loan_id"),
                    lead_id=task_data.get("lead_id")
                )
                db.add(task)
                executed += 1

            elif action.action_type == WorkflowActionType.TAG:
                # Add tags (would require tag model implementation)
                pass

            elif action.action_type == WorkflowActionType.ALERT:
                # Log alert (could integrate with notification system)
                logger.info(f"ALERT: {action.data.get('message', 'Power Play Alert')}")
                executed += 1

            elif action.action_type == WorkflowActionType.DRIP_CAMPAIGN:
                # Start drip campaign (would require drip system)
                logger.info(f"Drip campaign started: {action.data.get('campaign', 'unknown')}")
                executed += 1

        except Exception as e:
            logger.error(f"Error executing Power Play action: {e}")

    db.commit()
    return executed


# ============================================================================
# DOCUMENT INTAKE CLASSIFICATION ENDPOINTS
# ============================================================================

@router.post("/document-intake/process")
async def process_inbound_email(
    email_data: EmailProcessRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Process an inbound email with attachments.

    This endpoint receives email data (from an email provider webhook or manual trigger),
    parses attachments, attempts to match to a borrower/loan, and creates a classification task.
    """
    from workflows.document_intake_engine import DocumentIntakeEngine

    engine = DocumentIntakeEngine(db)

    raw_email = {
        "from_email": email_data.from_email,
        "to_email": email_data.to_email,
        "cc": email_data.cc_emails or [],
        "subject": email_data.subject or "",
        "body": email_data.body or "",
        "date": email_data.date or datetime.now(timezone.utc).isoformat(),
        "message_id": email_data.message_id or f"manual-{datetime.now().timestamp()}",
        "in_reply_to": email_data.in_reply_to,
        "attachments": email_data.attachments or []
    }

    try:
        result = await engine.process_inbound_email(raw_email)
        return result
    except Exception as e:
        logger.error(f"Error processing document intake: {e}")
        raise HTTPException(status_code=500, detail="Failed to process email")


@router.get("/document-intake/pending")
async def get_pending_intakes(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Get all email intakes with pending classifications.

    Returns list of email intakes that have attachments awaiting classification.
    """
    import main
    EmailIntake = main.EmailIntake
    Lead = main.Lead
    Loan = main.Loan
    AttachmentClassificationStatus = main.AttachmentClassificationStatus

    # Org-scope: EmailIntake doesn't have organization_id, so filter via matched borrower/loan
    query = db.query(EmailIntake).filter(
        EmailIntake.processing_status == "processed"
    )
    org_id = getattr(current_user, 'organization_id', None)
    if org_id:
        query = query.outerjoin(Lead, EmailIntake.matched_borrower_id == Lead.id).outerjoin(
            Loan, EmailIntake.matched_loan_id == Loan.id
        ).filter(
            (Lead.organization_id == org_id) | (Loan.organization_id == org_id) |
            ((EmailIntake.matched_borrower_id.is_(None)) & (EmailIntake.matched_loan_id.is_(None)))
        )
    pending_intakes = query.options(
        selectinload(EmailIntake.attachments),
        selectinload(EmailIntake.matched_borrower),
        selectinload(EmailIntake.matched_loan)
    ).order_by(EmailIntake.received_at.desc()).limit(50).all()

    result = []
    for intake in pending_intakes:
        pending_attachments = [
            att for att in intake.attachments
            if att.classification_status == AttachmentClassificationStatus.PENDING
        ]

        if pending_attachments:
            result.append({
                "id": intake.id,
                "from_email": intake.from_email,
                "subject": intake.subject,
                "received_at": intake.received_at.isoformat() if intake.received_at else None,
                "match_status": intake.match_status.value if intake.match_status else "unmatched",
                "matched_borrower": {
                    "id": intake.matched_borrower.id,
                    "name": intake.matched_borrower.name
                } if intake.matched_borrower else None,
                "matched_loan": {
                    "id": intake.matched_loan.id,
                    "loan_number": intake.matched_loan.loan_number,
                    "borrower_name": intake.matched_loan.borrower_name
                } if intake.matched_loan else None,
                "pending_attachments": len(pending_attachments),
                "total_attachments": len(intake.attachments)
            })

    return result


@router.get("/document-intake/{intake_id}")
async def get_email_intake(
    intake_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Get detailed information about an email intake and its attachments.
    """
    import main
    EmailIntake = main.EmailIntake
    Lead = main.Lead
    Loan = main.Loan

    intake = db.query(EmailIntake).filter(EmailIntake.id == intake_id).options(
        selectinload(EmailIntake.attachments),
        selectinload(EmailIntake.matched_borrower),
        selectinload(EmailIntake.matched_loan),
        selectinload(EmailIntake.classification_task)
    ).first()

    if not intake:
        raise HTTPException(status_code=404, detail="Email intake not found")

    # Org-scope: verify matched borrower/loan belongs to user's organization
    org_id = getattr(current_user, 'organization_id', None)
    if org_id:
        if intake.matched_borrower_id:
            borrower = db.query(Lead).filter(Lead.id == intake.matched_borrower_id, Lead.organization_id == org_id).first()
            if not borrower:
                raise HTTPException(status_code=404, detail="Email intake not found")
        if intake.matched_loan_id:
            loan = db.query(Loan).filter(Loan.id == intake.matched_loan_id, Loan.organization_id == org_id).first()
            if not loan:
                raise HTTPException(status_code=404, detail="Email intake not found")

    return {
        "id": intake.id,
        "from_email": intake.from_email,
        "to_email": intake.to_email,
        "cc_emails": intake.cc_emails.split(",") if intake.cc_emails else [],
        "subject": intake.subject,
        "body_snippet": intake.body_snippet,
        "received_at": intake.received_at.isoformat() if intake.received_at else None,
        "match_status": intake.match_status.value if intake.match_status else "unmatched",
        "match_candidates": intake.match_candidates,
        "matched_borrower": {
            "id": intake.matched_borrower.id,
            "name": intake.matched_borrower.name,
            "email": intake.matched_borrower.email
        } if intake.matched_borrower else None,
        "matched_loan": {
            "id": intake.matched_loan.id,
            "loan_number": intake.matched_loan.loan_number,
            "borrower_name": intake.matched_loan.borrower_name
        } if intake.matched_loan else None,
        "attachments": [
            {
                "id": att.id,
                "filename": att.filename,
                "original_filename": att.original_filename,
                "file_size": att.file_size,
                "mime_type": att.mime_type,
                "classification_status": att.classification_status.value if att.classification_status else "pending",
                "ai_suggested_doc_type": att.ai_suggested_doc_type,
                "ai_suggested_doc_category": att.ai_suggested_doc_category,
                "ai_confidence": att.ai_confidence,
                "classified_doc_type": att.classified_doc_type.value if att.classified_doc_type else None,
                "classified_doc_category": att.classified_doc_category.value if att.classified_doc_category else None,
                "period_start_date": att.period_start_date.isoformat() if att.period_start_date else None,
                "period_end_date": att.period_end_date.isoformat() if att.period_end_date else None,
                "document_id": att.document_id,
                "discarded_reason": att.discarded_reason
            }
            for att in intake.attachments
        ],
        "classification_task": {
            "id": intake.classification_task.id,
            "status": intake.classification_task.status,
            "title": intake.classification_task.title
        } if intake.classification_task else None,
        "processing_status": intake.processing_status
    }


@router.put("/document-intake/{intake_id}/match")
async def update_intake_match(
    intake_id: int,
    match_data: UpdateMatchRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Update the matched borrower/loan for an email intake.

    Use this when the automatic matching was wrong or when match_status is MULTIPLE/UNMATCHED.
    """
    import main
    EmailIntake = main.EmailIntake
    Lead = main.Lead
    Loan = main.Loan
    EmailIntakeMatchStatus = main.EmailIntakeMatchStatus

    intake = db.query(EmailIntake).filter(EmailIntake.id == intake_id).first()

    if not intake:
        raise HTTPException(status_code=404, detail="Email intake not found")

    # Org-scope: verify existing matched entities belong to user's organization
    org_id = getattr(current_user, 'organization_id', None)
    if org_id:
        if intake.matched_borrower_id:
            existing_borrower = db.query(Lead).filter(Lead.id == intake.matched_borrower_id, Lead.organization_id == org_id).first()
            if not existing_borrower:
                raise HTTPException(status_code=404, detail="Email intake not found")
        if intake.matched_loan_id:
            existing_loan = db.query(Loan).filter(Loan.id == intake.matched_loan_id, Loan.organization_id == org_id).first()
            if not existing_loan:
                raise HTTPException(status_code=404, detail="Email intake not found")

    if match_data.borrower_id is not None:
        # Verify borrower exists (org-scoped)
        borrower = _org_scoped_lead(db, match_data.borrower_id, current_user)
        if not borrower:
            raise HTTPException(status_code=400, detail="Borrower not found")
        intake.matched_borrower_id = match_data.borrower_id

    if match_data.loan_id is not None:
        # Verify loan exists (org-scoped)
        loan = _org_scoped_loan(db, match_data.loan_id, current_user)
        if not loan:
            raise HTTPException(status_code=400, detail="Loan not found")
        intake.matched_loan_id = match_data.loan_id

    if match_data.borrower_id or match_data.loan_id:
        intake.match_status = EmailIntakeMatchStatus.MATCHED

    db.commit()

    return {
        "success": True,
        "intake_id": intake_id,
        "matched_borrower_id": intake.matched_borrower_id,
        "matched_loan_id": intake.matched_loan_id,
        "match_status": intake.match_status.value
    }


@router.post("/document-intake/attachments/{attachment_id}/classify")
async def classify_attachment(
    attachment_id: int,
    classification: ClassifyAttachmentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Classify an attachment and create a Document record.

    This is called when the user reviews an attachment and confirms its document type.
    """
    # Org-scope: if borrower_id or loan_id provided, verify they belong to the user's org
    if classification.borrower_id is not None:
        borrower = _org_scoped_lead(db, classification.borrower_id, current_user)
        if not borrower:
            raise HTTPException(status_code=400, detail="Borrower not found")
    if classification.loan_id is not None:
        loan = _org_scoped_loan(db, classification.loan_id, current_user)
        if not loan:
            raise HTTPException(status_code=400, detail="Loan not found")

    from workflows.document_intake_engine import DocumentClassificationHandler

    handler = DocumentClassificationHandler(db)

    try:
        result = await handler.classify_attachment(
            attachment_id=attachment_id,
            user_id=getattr(current_user, 'id', 1),
            doc_type=classification.doc_type,
            doc_category=classification.doc_category,
            borrower_id=classification.borrower_id,
            loan_id=classification.loan_id,
            period_start=classification.period_start,
            period_end=classification.period_end,
            notes=classification.notes
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception as e:
        logger.error(f"Error classifying attachment: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Classification failed")


@router.post("/document-intake/attachments/{attachment_id}/discard")
async def discard_attachment(
    attachment_id: int,
    discard_data: DiscardAttachmentRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Discard an attachment as irrelevant/junk.

    Use this for signature images, email footers, or other non-document attachments.
    """
    from workflows.document_intake_engine import DocumentClassificationHandler

    handler = DocumentClassificationHandler(db)

    try:
        result = await handler.discard_attachment(
            attachment_id=attachment_id,
            user_id=getattr(current_user, 'id', 1),
            reason=discard_data.reason
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception as e:
        logger.error(f"Error discarding attachment: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Discard failed")


@router.post("/document-intake/tasks/{task_id}/complete")
async def complete_classification_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Complete a document classification task.

    This should be called after all attachments have been classified or discarded.
    """
    from workflows.document_intake_engine import DocumentClassificationHandler

    handler = DocumentClassificationHandler(db)

    try:
        result = await handler.complete_classification_task(
            task_id=task_id,
            user_id=getattr(current_user, 'id', 1)
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception as e:
        logger.error(f"Error completing task: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to complete task")


@router.get("/document-intake/doc-types")
async def get_document_types():
    """
    Get available document types and categories for classification UI.
    """
    import main
    DocumentType = main.DocumentType
    DocumentCategory = main.DocumentCategory

    return {
        "doc_types": [dt.value for dt in DocumentType],
        "doc_categories": [dc.value for dc in DocumentCategory],
        "type_to_category": {
            "W2": "INCOME",
            "PAYSTUB": "INCOME",
            "TAX_RETURN_1040": "INCOME",
            "TAX_RETURN_1099": "INCOME",
            "BANK_STATEMENT": "ASSETS",
            "INVESTMENT_STATEMENT": "ASSETS",
            "RETIREMENT_STATEMENT": "ASSETS",
            "GIFT_LETTER": "ASSETS",
            "DRIVERS_LICENSE": "IDENTITY",
            "PASSPORT": "IDENTITY",
            "SSN_CARD": "IDENTITY",
            "GREEN_CARD": "IDENTITY",
            "PURCHASE_CONTRACT": "PROPERTY",
            "APPRAISAL": "PROPERTY",
            "TITLE_COMMITMENT": "PROPERTY",
            "HOMEOWNERS_INSURANCE": "PROPERTY",
            "SURVEY": "PROPERTY",
            "CREDIT_REPORT": "CREDIT",
            "CREDIT_EXPLANATION": "CREDIT",
            "VOE": "EMPLOYMENT",
            "EMPLOYMENT_CONTRACT": "EMPLOYMENT",
            "BUSINESS_LICENSE": "EMPLOYMENT",
            "OTHER": "MISC"
        }
    }


@router.get("/documents")
async def get_documents(
    borrower_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    doc_type: Optional[str] = None,
    doc_category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Get documents with optional filtering.
    Uses raw SQL to avoid enum validation issues with legacy data.
    """
    # Build query with raw SQL to bypass ORM enum validation
    conditions = ["status = 'active'"]
    params = {"limit_val": limit, "offset_val": offset}

    # Org-scope: Document has organization_id
    org_id = _org_scoped_document_filter(current_user)
    if org_id:
        conditions.append("organization_id = :org_id")
        params["org_id"] = org_id

    if borrower_id:
        conditions.append("borrower_id = :borrower_id")
        params["borrower_id"] = borrower_id
    if loan_id:
        conditions.append("loan_id = :loan_id")
        params["loan_id"] = loan_id
    if doc_type:
        conditions.append("doc_type = :doc_type")
        params["doc_type"] = doc_type
    if doc_category:
        conditions.append("doc_category = :doc_category")
        params["doc_category"] = doc_category

    where_clause = " AND ".join(conditions)

    # Get total count
    count_query = text(f"SELECT COUNT(*) FROM documents WHERE {where_clause}")
    total = db.execute(count_query, params).scalar() or 0

    # Get documents
    select_query = text(f"""
        SELECT id, borrower_id, loan_id, doc_type, doc_category, filename,
               file_size, mime_type, period_start_date, period_end_date,
               source, uploaded_at, notes
        FROM documents
        WHERE {where_clause}
        ORDER BY uploaded_at DESC NULLS LAST
        LIMIT :limit_val OFFSET :offset_val
    """)

    result = db.execute(select_query, params)
    documents = []
    for row in result:
        documents.append({
            "id": row.id,
            "borrower_id": row.borrower_id,
            "loan_id": row.loan_id,
            "doc_type": row.doc_type,
            "doc_category": row.doc_category,
            "filename": row.filename,
            "file_size": row.file_size,
            "mime_type": row.mime_type,
            "period_start_date": row.period_start_date.isoformat() if row.period_start_date else None,
            "period_end_date": row.period_end_date.isoformat() if row.period_end_date else None,
            "source": row.source,
            "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
            "notes": row.notes
        })

    return {
        "total": total,
        "documents": documents
    }


@router.get("/documents/{document_id}")
async def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Get a single document by ID.
    Uses raw SQL to avoid enum validation issues with legacy data.
    """
    # Org-scope: Document has organization_id
    conditions = ["id = :doc_id"]
    params = {"doc_id": document_id}

    org_id = _org_scoped_document_filter(current_user)
    if org_id:
        conditions.append("organization_id = :org_id")
        params["org_id"] = org_id

    where_clause = " AND ".join(conditions)
    query = text(f"""
        SELECT id, borrower_id, loan_id, doc_type, doc_category, filename,
               original_filename, file_size, mime_type, file_location,
               period_start_date, period_end_date, source, source_email_intake_id,
               status, notes, uploaded_at, updated_at
        FROM documents
        WHERE {where_clause}
    """)

    result = db.execute(query, params).first()

    if not result:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": result.id,
        "borrower_id": result.borrower_id,
        "loan_id": result.loan_id,
        "doc_type": result.doc_type,
        "doc_category": result.doc_category,
        "filename": result.filename,
        "original_filename": result.original_filename,
        "file_size": result.file_size,
        "mime_type": result.mime_type,
        "file_location": result.file_location,
        "period_start_date": result.period_start_date.isoformat() if result.period_start_date else None,
        "period_end_date": result.period_end_date.isoformat() if result.period_end_date else None,
        "source": result.source,
        "source_email_intake_id": result.source_email_intake_id,
        "status": result.status,
        "notes": result.notes,
        "uploaded_at": result.uploaded_at.isoformat() if result.uploaded_at else None,
        "updated_at": result.updated_at.isoformat() if result.updated_at else None
    }


# ============================================================================
# POST-CLOSING WORKFLOW ENDPOINTS
# ============================================================================

@router.post("/loans/{loan_id}/trigger-workflow")
async def trigger_post_closing_workflow(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_flexible_dep()),
):
    """
    Manually trigger the post-closing referral workflow for a loan.
    This analyzes the borrower's referral potential and creates appropriate tasks/tags.
    """
    import main
    Lead = main.Lead

    from workflows.post_closing_workflow import (
        PostClosingWorkflowEngine,
        WorkflowTrigger,
        LeadWorkflowData,
        calculate_referral_score
    )

    # Get the loan (org-scoped)
    loan = _org_scoped_loan(db, loan_id, current_user)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Find matching lead by borrower name (org-scoped)
    org_id = getattr(current_user, 'organization_id', None)
    lead_query = db.query(Lead).filter(Lead.name == loan.borrower_name)
    if org_id:
        lead_query = lead_query.filter(Lead.organization_id == org_id)
    lead = lead_query.first()
    if not lead:
        # Try partial match (org-scoped)
        lead_query = db.query(Lead).filter(Lead.name.ilike(f"%{loan.borrower_name.split()[0]}%"))
        if org_id:
            lead_query = lead_query.filter(Lead.organization_id == org_id)
        lead = lead_query.first()

    if not lead:
        return {
            "success": False,
            "message": f"No matching lead found for borrower: {loan.borrower_name}",
            "suggestion": "Create a lead record for this borrower first"
        }

    # Calculate referral score if not set
    if not lead.referral_source_score:
        lead.referral_source_score = calculate_referral_score(lead)
        db.commit()

    # Create trigger
    trigger = WorkflowTrigger(
        loan_id=loan.id,
        lead_id=lead.id,
        loan_status=str(loan.stage) if loan.stage else "Unknown",
        closed_date=loan.funded_date or datetime.now(timezone.utc),
        loan_officer_id=loan.loan_officer_id or 1
    )

    # Create lead data
    lead_data = LeadWorkflowData(
        id=lead.id,
        name=lead.name,
        referral_source_score=lead.referral_source_score or 0,
        leadership_level=getattr(lead, 'leadership_level', None),
        employees_managed=getattr(lead, 'employees_managed', 0) or 0,
        referral_industry_flag=getattr(lead, 'referral_industry_flag', None),
        company_size=getattr(lead, 'company_size', None),
        employer_name=getattr(lead, 'employer_name', None),
        industry=getattr(lead, 'industry', None)
    )

    # Run workflow
    engine = PostClosingWorkflowEngine(db)
    result = await engine.process_loan_closing(trigger, lead_data)

    logger.info(f"Workflow triggered for loan {loan_id}: {result['action_count']} actions")

    return {
        "success": True,
        "loan_id": loan_id,
        "lead_id": lead.id,
        "lead_name": lead.name,
        "referral_score": lead.referral_source_score,
        "actions_triggered": result['action_count'],
        "actions": result['actions']
    }
