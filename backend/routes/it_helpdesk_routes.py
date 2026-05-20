"""
IT Helpdesk Routes

Provides endpoints for IT helpdesk ticket management including:
- Ticket submission with AI diagnosis
- Ticket listing and detail views
- Approval and resolution workflows
- Admin management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from typing import Optional, List
from datetime import datetime, timezone
import logging
import json

from database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# Dependencies - Import from main at runtime to avoid circular imports
# =============================================================================

def get_current_user_dep():
    """Get current user - imports from main at runtime"""
    import main
    return main.get_current_user


def get_it_helpdesk_ticket_model():
    """Get ITHelpdeskTicket model at runtime"""
    import main
    return main.ITHelpdeskTicket


def get_user_model():
    """Get User model at runtime"""
    import main
    return main.User


def get_openai_client():
    """Get OpenAI client at runtime"""
    import main
    return main.openai_client


# =============================================================================
# Helper Functions
# =============================================================================

async def diagnose_it_issue(ticket, description, logs_attached):
    """Use AI to diagnose the IT issue and propose a fix"""
    try:
        openai_client = get_openai_client()

        # Build context for AI
        context = f"""You are an expert IT support AI helping diagnose and fix technical issues.

Issue Description:
{description}

Category: {ticket.category}
Affected System: {ticket.affected_system or 'Not specified'}
Affected Project: {ticket.affected_project or 'Not specified'}

"""

        if logs_attached:
            context += f"\nError Logs/Screenshots:\n"
            for log in logs_attached[:3]:  # Limit to 3 logs
                context += f"- {log}\n"

        context += """
Based on this issue, please:
1. Diagnose the root cause
2. Suggest a step-by-step fix
3. Provide any commands that should be run
4. Assess the risk level (low/medium/high)

Format your response as JSON:
{
  "root_cause": "Brief description of root cause",
  "diagnosis": "Detailed explanation of what's wrong",
  "proposed_fix": {
    "risk_level": "low|medium|high",
    "steps": ["Step 1", "Step 2", ...],
    "commands": [{"description": "What this does", "command": "actual command", "platform": "bash|powershell|api"}]
  }
}"""

        # Call OpenAI
        response = openai_client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are an expert IT support assistant. Always respond with valid JSON."},
                {"role": "user", "content": context}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )

        result = json.loads(response.choices[0].message.content)
        return result

    except Exception as e:
        logger.error(f"Error diagnosing IT issue: {e}")
        return {
            "root_cause": "Unable to diagnose automatically",
            "diagnosis": f"AI diagnosis failed: {str(e)}. Please review the issue manually.",
            "proposed_fix": None
        }


# =============================================================================
# IT HELPDESK ENDPOINTS
# =============================================================================

@router.post("/submit")
async def submit_it_ticket(
    ticket_data: dict,
    current_user=Depends(get_current_user_dep()),
    db: AsyncSession = Depends(get_async_db)
):
    """Submit a new IT helpdesk ticket for AI diagnosis"""
    try:
        ITHelpdeskTicket = get_it_helpdesk_ticket_model()

        title = ticket_data.get("title", "").strip()
        description = ticket_data.get("description", "").strip()
        category = ticket_data.get("category", "general")
        urgency = ticket_data.get("urgency", "normal")
        affected_system = ticket_data.get("affected_system", "")
        affected_project = ticket_data.get("affected_project", "")
        logs_attached = ticket_data.get("logs_attached", [])

        if not description:
            raise HTTPException(status_code=400, detail="Description is required")

        # Create ticket
        ticket = ITHelpdeskTicket(
            user_id=current_user.id,
            title=title or description[:100],
            description=description,
            category=category,
            urgency=urgency,
            affected_system=affected_system,
            affected_project=affected_project,
            logs_attached=logs_attached,
            status="analyzing"
        )
        db.add(ticket)
        await db.flush()

        # Use AI to diagnose the issue
        diagnosis_result = await diagnose_it_issue(ticket, description, logs_attached)

        # Update ticket with AI analysis
        ticket.ai_diagnosis = diagnosis_result.get("diagnosis", "")
        ticket.root_cause = diagnosis_result.get("root_cause", "")
        ticket.proposed_fix = diagnosis_result.get("proposed_fix", {})
        ticket.status = "awaiting_approval" if diagnosis_result.get("proposed_fix") else "analyzed"

        await db.commit()

        logger.info(f"IT ticket {ticket.id} created and analyzed for user {current_user.id}")

        return {
            "success": True,
            "ticket_id": ticket.id,
            "diagnosis": ticket.ai_diagnosis,
            "root_cause": ticket.root_cause,
            "proposed_fix": ticket.proposed_fix,
            "status": ticket.status
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting IT ticket: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tickets")
async def get_it_tickets(
    status: str = None,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get all IT helpdesk tickets for the current user"""
    try:
        ITHelpdeskTicket = get_it_helpdesk_ticket_model()

        query = db.query(ITHelpdeskTicket).filter(
            ITHelpdeskTicket.user_id == current_user.id
        )

        if status:
            query = query.filter(ITHelpdeskTicket.status == status)

        tickets = query.order_by(ITHelpdeskTicket.created_at.desc()).limit(50).all()

        ticket_list = []
        for ticket in tickets:
            ticket_list.append({
                "id": ticket.id,
                "title": ticket.title,
                "description": ticket.description,
                "category": ticket.category,
                "urgency": ticket.urgency,
                "status": ticket.status,
                "root_cause": ticket.root_cause,
                "ai_diagnosis": ticket.ai_diagnosis,
                "proposed_fix": ticket.proposed_fix,
                "affected_system": ticket.affected_system,
                "affected_project": ticket.affected_project,
                "auto_resolved": ticket.auto_resolved,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None
            })

        return {
            "success": True,
            "tickets": ticket_list,
            "total": len(ticket_list)
        }

    except Exception as e:
        logger.error(f"Error fetching IT tickets: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tickets/{ticket_id}")
async def get_it_ticket(
    ticket_id: int,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific IT ticket"""
    try:
        ITHelpdeskTicket = get_it_helpdesk_ticket_model()

        ticket = db.query(ITHelpdeskTicket).filter(
            ITHelpdeskTicket.id == ticket_id,
            ITHelpdeskTicket.user_id == current_user.id
        ).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        return {
            "success": True,
            "ticket": {
                "id": ticket.id,
                "title": ticket.title,
                "description": ticket.description,
                "category": ticket.category,
                "urgency": ticket.urgency,
                "status": ticket.status,
                "ai_diagnosis": ticket.ai_diagnosis,
                "root_cause": ticket.root_cause,
                "proposed_fix": ticket.proposed_fix,
                "affected_system": ticket.affected_system,
                "affected_project": ticket.affected_project,
                "logs_attached": ticket.logs_attached,
                "execution_log": ticket.execution_log,
                "resolution_notes": ticket.resolution_notes,
                "auto_resolved": ticket.auto_resolved,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "approved_at": ticket.approved_at.isoformat() if ticket.approved_at else None,
                "executed_at": ticket.executed_at.isoformat() if ticket.executed_at else None,
                "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching IT ticket {ticket_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tickets/{ticket_id}/approve")
async def approve_it_fix(
    ticket_id: int,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Approve and mark a fix as ready for manual execution"""
    try:
        ITHelpdeskTicket = get_it_helpdesk_ticket_model()

        ticket = db.query(ITHelpdeskTicket).filter(
            ITHelpdeskTicket.id == ticket_id,
            ITHelpdeskTicket.user_id == current_user.id
        ).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        ticket.approved_at = datetime.now(timezone.utc)
        ticket.status = "approved"

        db.commit()

        logger.info(f"IT ticket {ticket_id} approved by user {current_user.id}")

        return {
            "success": True,
            "message": "Fix approved. Execute the commands manually and update the ticket when complete.",
            "ticket_id": ticket.id,
            "proposed_fix": ticket.proposed_fix
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving IT ticket {ticket_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tickets/{ticket_id}/resolve")
async def resolve_it_ticket(
    ticket_id: int,
    resolution_data: dict,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Mark a ticket as resolved with notes"""
    try:
        ITHelpdeskTicket = get_it_helpdesk_ticket_model()

        ticket = db.query(ITHelpdeskTicket).filter(
            ITHelpdeskTicket.id == ticket_id,
            ITHelpdeskTicket.user_id == current_user.id
        ).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        ticket.status = "resolved"
        ticket.resolved_at = datetime.now(timezone.utc)
        ticket.resolution_notes = resolution_data.get("notes", "")
        ticket.execution_log = resolution_data.get("execution_log", {})

        db.commit()

        logger.info(f"IT ticket {ticket_id} resolved by user {current_user.id}")

        return {
            "success": True,
            "message": "Ticket marked as resolved",
            "ticket_id": ticket.id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving IT ticket {ticket_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# IT HELPDESK ADMIN ENDPOINTS
# =============================================================================

@router.get("/admin/tickets")
async def get_all_it_tickets_admin(
    status: Optional[str] = None,
    urgency: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get all IT helpdesk tickets for admin view (all users)"""
    try:
        ITHelpdeskTicket = get_it_helpdesk_ticket_model()
        User = get_user_model()

        # Build query - no user filter for admin view
        query = db.query(ITHelpdeskTicket)

        # Apply filters
        if status:
            query = query.filter(ITHelpdeskTicket.status == status)
        if urgency:
            query = query.filter(ITHelpdeskTicket.urgency == urgency)
        if category:
            query = query.filter(ITHelpdeskTicket.category == category)
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    ITHelpdeskTicket.title.ilike(search_pattern),
                    ITHelpdeskTicket.description.ilike(search_pattern),
                    ITHelpdeskTicket.root_cause.ilike(search_pattern)
                )
            )

        # Get tickets ordered by creation date
        tickets = query.order_by(ITHelpdeskTicket.created_at.desc()).limit(100).all()

        # Calculate stats
        all_tickets = db.query(ITHelpdeskTicket).all()
        stats = {
            "total": len(all_tickets),
            "open": len([t for t in all_tickets if t.status not in ['resolved', 'failed']]),
            "awaiting_approval": len([t for t in all_tickets if t.status == 'awaiting_approval']),
            "resolved": len([t for t in all_tickets if t.status == 'resolved']),
            "critical": len([t for t in all_tickets if t.urgency == 'critical'])
        }

        # Get user names for display
        user_ids = list(set([t.user_id for t in tickets]))
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        user_map = {u.id: u.full_name or u.email for u in users}

        return {
            "tickets": [
                {
                    "id": t.id,
                    "user_id": t.user_id,
                    "user_name": user_map.get(t.user_id, f"User #{t.user_id}"),
                    "title": t.title,
                    "description": t.description,
                    "category": t.category,
                    "urgency": t.urgency,
                    "status": t.status,
                    "ai_diagnosis": t.ai_diagnosis,
                    "root_cause": t.root_cause,
                    "proposed_fix": t.proposed_fix,
                    "affected_system": t.affected_system,
                    "affected_project": t.affected_project,
                    "resolution_notes": t.resolution_notes,
                    "admin_notes": t.execution_log.get("admin_notes", []) if t.execution_log else [],
                    "assigned_to": t.execution_log.get("assigned_to") if t.execution_log else None,
                    "assigned_to_name": t.execution_log.get("assigned_to_name") if t.execution_log else None,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                    "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
                    "approved_at": t.approved_at.isoformat() if t.approved_at else None
                }
                for t in tickets
            ],
            "stats": stats
        }

    except Exception as e:
        logger.error(f"Error fetching admin IT tickets: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/admin/tickets/{ticket_id}/status")
async def update_ticket_status_admin(
    ticket_id: int,
    status_data: dict,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Update ticket status (admin only)"""
    try:
        ITHelpdeskTicket = get_it_helpdesk_ticket_model()

        ticket = db.query(ITHelpdeskTicket).filter(ITHelpdeskTicket.id == ticket_id).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        new_status = status_data.get("status")
        if new_status:
            ticket.status = new_status
            if new_status == "resolved":
                ticket.resolved_at = datetime.now(timezone.utc)

        db.commit()

        logger.info(f"IT ticket {ticket_id} status updated to {new_status} by admin {current_user.id}")

        return {
            "success": True,
            "message": f"Ticket status updated to {new_status}",
            "ticket_id": ticket.id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating IT ticket status {ticket_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/admin/tickets/{ticket_id}/assign")
async def assign_ticket_admin(
    ticket_id: int,
    assign_data: dict,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Assign a ticket to a team member (admin only)"""
    try:
        ITHelpdeskTicket = get_it_helpdesk_ticket_model()
        User = get_user_model()

        ticket = db.query(ITHelpdeskTicket).filter(ITHelpdeskTicket.id == ticket_id).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        assigned_to_id = assign_data.get("assigned_to")

        # Get assignee name
        assignee = db.query(User).filter(User.id == assigned_to_id).first()
        assignee_name = assignee.full_name or assignee.email if assignee else f"User #{assigned_to_id}"

        # Update execution_log with assignment info
        execution_log = ticket.execution_log or {}
        execution_log["assigned_to"] = assigned_to_id
        execution_log["assigned_to_name"] = assignee_name
        execution_log["assigned_at"] = datetime.now(timezone.utc).isoformat()
        execution_log["assigned_by"] = current_user.id
        ticket.execution_log = execution_log

        db.commit()

        logger.info(f"IT ticket {ticket_id} assigned to {assignee_name} by admin {current_user.id}")

        return {
            "success": True,
            "message": f"Ticket assigned to {assignee_name}",
            "ticket_id": ticket.id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning IT ticket {ticket_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/tickets/{ticket_id}/notes")
async def add_admin_note(
    ticket_id: int,
    note_data: dict,
    current_user=Depends(get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Add an admin note to a ticket"""
    try:
        ITHelpdeskTicket = get_it_helpdesk_ticket_model()

        ticket = db.query(ITHelpdeskTicket).filter(ITHelpdeskTicket.id == ticket_id).first()

        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        note_text = note_data.get("note", "").strip()
        if not note_text:
            raise HTTPException(status_code=400, detail="Note cannot be empty")

        # Update execution_log with admin notes
        execution_log = ticket.execution_log or {}
        admin_notes = execution_log.get("admin_notes", [])
        admin_notes.append({
            "note": note_text,
            "added_by": current_user.id,
            "added_by_name": current_user.full_name or current_user.email,
            "added_at": datetime.now(timezone.utc).isoformat()
        })
        execution_log["admin_notes"] = admin_notes
        ticket.execution_log = execution_log

        db.commit()

        logger.info(f"Admin note added to IT ticket {ticket_id} by {current_user.id}")

        return {
            "success": True,
            "message": "Note added successfully",
            "ticket_id": ticket.id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding note to IT ticket {ticket_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
