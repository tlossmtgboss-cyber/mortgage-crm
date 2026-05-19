"""
Command Center Routes - Unified Action Items Dashboard

This module provides the Command Center API which aggregates all actionable items
across the CRM including leads, loans, portfolio, emails, SMS, calls, and reconciliation.

Routes:
- GET /api/v1/command-center - Get all action items for the current user
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["command-center"])

# Dependency injection placeholders
User = None
Task = None
Lead = None
Loan = None
AIAction = None
_get_current_user_flexible = None
_get_db = None
_get_all_workflow_tasks_logic = None


def set_dependencies(
    user_model,
    task_model,
    lead_model,
    loan_model,
    ai_action_model,
    current_user_func,
    db_func,
    workflow_tasks_func=None
):
    """Set dependencies for this router."""
    global User, Task, Lead, Loan, AIAction, _get_current_user_flexible, _get_db, _get_all_workflow_tasks_logic
    User = user_model
    Task = task_model
    Lead = lead_model
    Loan = loan_model
    AIAction = ai_action_model
    _get_current_user_flexible = current_user_func
    _get_db = db_func
    _get_all_workflow_tasks_logic = workflow_tasks_func


def get_db():
    """Get database session - wrapper that works at request time."""
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    yield from _get_db()


from auth.dependencies import get_current_user  # dedup: was local wrapper
@router.get("/command-center")
async def get_command_center(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Command Center - Aggregates all actionable items across the CRM.
    Returns categorized action items for leads, loans, portfolio, emails, SMS, calls, and reconciliation.
    """
    user_id = current_user.id
    now = datetime.now(timezone.utc)

    action_items = {
        "urgent": [],          # Critical/overdue items
        "leads": [],           # Lead follow-ups and tasks
        "loans": [],           # Active loan milestones and tasks
        "portfolio": [],       # Portfolio touchpoints and opportunities
        "emails": [],          # Unanswered emails
        "sms": [],             # Unanswered SMS
        "calls": [],           # Pending calls/voicemails
        "reconciliation": [],  # Data reconciliation items
        "approvals": [],       # AI actions pending approval
        "summary": {}          # Counts and metrics
    }

    # 1. URGENT - SLA Alerts (at-risk and overdue milestones)
    try:
        sla_alerts = db.execute(text("""
            SELECT sa.id, sa.alert_type, sa.milestone_type, sa.status, sa.created_at,
                   sa.target_deadline, sa.loan_id, l.borrower_name, l.loan_number
            FROM sla_alerts sa
            LEFT JOIN loans l ON sa.loan_id = l.id
            WHERE sa.status = 'active'
              AND l.loan_officer_id = :user_id
            ORDER BY sa.alert_type DESC, sa.created_at ASC
            LIMIT 20
        """), {"user_id": user_id}).fetchall()

        for alert in sla_alerts:
            action_items["urgent"].append({
                "id": f"sla_{alert.id}",
                "type": "sla_alert",
                "priority": "critical" if alert.alert_type == "critical" else "high",
                "title": f"{alert.milestone_type} - {alert.alert_type.upper()}",
                "description": f"Loan: {alert.borrower_name or 'Unknown'} ({alert.loan_number or 'N/A'})",
                "entity_type": "loan",
                "entity_id": alert.loan_id,
                "entity_name": alert.borrower_name,
                "due_date": alert.target_deadline.isoformat() if alert.target_deadline else None,
                "url": f"/loans/{alert.loan_id}",
                "created_at": alert.created_at.isoformat() if alert.created_at else None
            })
    except Exception as e:
        logger.warning(f"Command center - SLA alerts error: {e}")
        db.rollback()  # Reset transaction state

    # 2. LEADS - Pending tasks and follow-ups
    try:
        lead_tasks = db.query(Task).filter(
            Task.owner_id == user_id,
            Task.status.in_(["pending", "in_progress"]),
            Task.lead_id.isnot(None)
        ).order_by(Task.due_date.asc().nullslast()).limit(30).all()

        # Batch-fetch all referenced leads to avoid N+1 queries
        lead_ids_needed = {t.lead_id for t in lead_tasks if t.lead_id}
        leads_map = {}
        if lead_ids_needed:
            leads_batch = db.query(Lead).filter(Lead.id.in_(lead_ids_needed)).all()
            leads_map = {l.id: l for l in leads_batch}

        for task in lead_tasks:
            lead = leads_map.get(task.lead_id)
            is_overdue = task.due_date and task.due_date < now if task.due_date else False
            priority = "critical" if is_overdue else (task.priority or "medium")

            item = {
                "id": f"task_{task.id}",
                "type": "task",
                "priority": priority,
                "title": task.title,
                "description": task.description,
                "entity_type": "lead",
                "entity_id": task.lead_id,
                "entity_name": lead.name if lead else None,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "url": f"/leads/{task.lead_id}",
                "status": task.status
            }

            if is_overdue:
                action_items["urgent"].append(item)
            else:
                action_items["leads"].append(item)
    except Exception as e:
        logger.warning(f"Command center - lead tasks error: {e}")
        db.rollback()  # Reset transaction state

    # Also get leads needing follow-up (no contact in X days based on stage)
    try:
        # Get leads assigned to this user that need follow-up
        stale_leads = db.execute(text("""
            SELECT l.id, l.name, l.stage::text as stage, l.last_contact, l.email, l.phone,
                   EXTRACT(EPOCH FROM (NOW() - COALESCE(l.last_contact, l.created_at)))/86400 as days_since_contact
            FROM leads l
            WHERE l.owner_id = :user_id
            AND l.stage::text NOT IN ('Closed', 'Withdrawn', 'Does Not Qualify')
            ORDER BY l.last_contact ASC NULLS FIRST, l.created_at DESC
            LIMIT 15
        """), {"user_id": user_id}).fetchall()

        for lead in stale_leads:
            days = int(lead.days_since_contact) if lead.days_since_contact else 999
            priority = "critical" if days > 7 else "high" if days > 5 else "medium"
            action_items["leads"].append({
                "id": f"followup_lead_{lead.id}",
                "type": "follow_up",
                "priority": priority,
                "title": f"Follow up with {lead.name}",
                "description": f"No contact in {days} days" if days < 999 else "Never contacted",
                "entity_type": "lead",
                "entity_id": lead.id,
                "entity_name": lead.name,
                "stage": str(lead.stage) if lead.stage else None,
                "url": f"/leads/{lead.id}",
                "days_stale": days
            })
    except Exception as e:
        logger.warning(f"Command center - stale leads error: {e}")
        db.rollback()  # Reset transaction state

    # 3. LOANS - Active milestones and tasks
    try:
        loan_tasks = db.query(Task).filter(
            Task.owner_id == user_id,
            Task.status.in_(["pending", "in_progress"]),
            Task.loan_id.isnot(None)
        ).order_by(Task.due_date.asc().nullslast()).limit(30).all()

        # Batch-fetch all referenced loans to avoid N+1 queries
        loan_ids_needed = {t.loan_id for t in loan_tasks if t.loan_id}
        loans_map = {}
        if loan_ids_needed:
            loans_batch = db.query(Loan).filter(Loan.id.in_(loan_ids_needed)).all()
            loans_map = {l.id: l for l in loans_batch}

        for task in loan_tasks:
            loan = loans_map.get(task.loan_id)
            is_overdue = task.due_date and task.due_date < now if task.due_date else False
            priority = "critical" if is_overdue else (task.priority or "medium")

            item = {
                "id": f"task_{task.id}",
                "type": "task",
                "priority": priority,
                "title": task.title,
                "description": task.description,
                "entity_type": "loan",
                "entity_id": task.loan_id,
                "entity_name": loan.borrower_name if loan else None,
                "loan_number": loan.loan_number if loan else None,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "url": f"/loans/{task.loan_id}",
                "status": task.status
            }

            if is_overdue:
                action_items["urgent"].append(item)
            else:
                action_items["loans"].append(item)
    except Exception as e:
        logger.warning(f"Command center - loan tasks error: {e}")
        db.rollback()  # Reset transaction state

    # Get loans with upcoming deadlines (closing, lock expiration)
    # Exclude funded loans (case insensitive) - they should only appear in Portfolio
    try:
        upcoming_deadlines = db.execute(text("""
            SELECT l.id, l.borrower_name, l.loan_number, l.stage::text as status,
                   l.closing_date, l.lock_expiration_date as lock_expiration,
                   CASE
                       WHEN l.lock_expiration_date IS NOT NULL AND l.lock_expiration_date < NOW() + INTERVAL '3 days'
                       THEN 'lock_expiring'
                       WHEN l.closing_date IS NOT NULL AND l.closing_date < NOW() + INTERVAL '7 days'
                       THEN 'closing_soon'
                       ELSE 'deadline'
                   END as deadline_type
            FROM loans l
            WHERE l.loan_officer_id = :user_id
              AND UPPER(l.stage::text) NOT IN ('FUNDED', 'WITHDRAWN', 'CLOSED')
              AND (
                  (l.lock_expiration_date IS NOT NULL AND l.lock_expiration_date < NOW() + INTERVAL '5 days')
                  OR (l.closing_date IS NOT NULL AND l.closing_date < NOW() + INTERVAL '7 days')
              )
            ORDER BY COALESCE(l.lock_expiration_date, l.closing_date) ASC
            LIMIT 15
        """), {"user_id": user_id}).fetchall()

        # If no deadline loans, show active loans that need attention
        if not upcoming_deadlines:
            upcoming_deadlines = db.execute(text("""
                SELECT l.id, l.borrower_name, l.loan_number, l.stage::text as status,
                       l.closing_date, l.lock_expiration_date as lock_expiration,
                       'active_loan' as deadline_type
                FROM loans l
                WHERE l.loan_officer_id = :user_id
                  AND UPPER(l.stage::text) NOT IN ('FUNDED', 'WITHDRAWN', 'CLOSED')
                ORDER BY l.created_at DESC
                LIMIT 10
            """), {"user_id": user_id}).fetchall()

        for loan in upcoming_deadlines:
            deadline_date = loan.lock_expiration if loan.deadline_type == 'lock_expiring' else loan.closing_date
            days_until = (deadline_date - now).days if deadline_date else 999

            if loan.deadline_type == 'active_loan':
                priority = "medium"
                title = f"Active Loan: {loan.borrower_name}"
                description = f"Status: {loan.status} - {loan.loan_number or 'N/A'}"
            else:
                priority = "critical" if days_until <= 1 else "high" if days_until <= 3 else "medium"
                title = "Rate Lock Expiring" if loan.deadline_type == 'lock_expiring' else "Closing Coming Up"
                description = f"In {days_until} days - {loan.loan_number or 'N/A'}"
            action_items["loans"].append({
                "id": f"deadline_{loan.id}_{loan.deadline_type}",
                "type": loan.deadline_type,
                "priority": priority,
                "title": title if loan.deadline_type == 'active_loan' else f"{title}: {loan.borrower_name}",
                "description": description,
                "entity_type": "loan",
                "entity_id": loan.id,
                "entity_name": loan.borrower_name,
                "loan_number": loan.loan_number,
                "due_date": deadline_date.isoformat() if deadline_date else None,
                "url": f"/loans/{loan.id}",
                "days_until": days_until if loan.deadline_type != 'active_loan' else None
            })
    except Exception as e:
        logger.warning(f"Command center - loan deadlines error: {e}")
        db.rollback()

    # 4. PORTFOLIO - Funded loans and MUM clients (Mortgages Under Management)
    # First, add funded loans from the loans table
    try:
        funded_loans = db.execute(text("""
            SELECT l.id, l.borrower_name, l.loan_number, l.stage::text as status,
                   l.funded_date, l.amount, l.closing_date
            FROM loans l
            WHERE l.loan_officer_id = :user_id
              AND UPPER(l.stage::text) = 'FUNDED'
            ORDER BY COALESCE(l.funded_date, l.closing_date, l.updated_at) DESC
            LIMIT 20
        """), {"user_id": user_id}).fetchall()

        for loan in funded_loans:
            action_items["portfolio"].append({
                "id": f"funded_loan_{loan.id}",
                "type": "funded_loan",
                "priority": "low",
                "title": f"Funded: {loan.borrower_name}",
                "description": f"Loan #{loan.loan_number or 'N/A'} - ${loan.amount:,.0f}" if loan.amount else f"Loan #{loan.loan_number or 'N/A'}",
                "entity_type": "loan",
                "entity_id": loan.id,
                "entity_name": loan.borrower_name,
                "loan_number": loan.loan_number,
                "funded_date": loan.funded_date.isoformat() if loan.funded_date else None,
                "url": f"/portfolio?loan={loan.id}"
            })
    except Exception as e:
        logger.warning(f"Command center - funded loans error: {e}")
        db.rollback()

    # Then add MUM clients with touchpoints due
    try:
        portfolio_items = db.execute(text("""
            SELECT m.id, m.client_name, m.email, m.phone, m.loan_number,
                   m.next_touchpoint, m.refinance_opportunity, m.estimated_savings,
                   m.last_contact, m.interest_rate, m.current_loan_amount
            FROM mum_clients m
            WHERE m.loan_officer_id = :user_id
              AND m.next_touchpoint IS NOT NULL
              AND m.next_touchpoint <= NOW() + INTERVAL '14 days'
            ORDER BY m.next_touchpoint ASC
            LIMIT 15
        """), {"user_id": user_id}).fetchall()

        # If no touchpoints due, show recent portfolio clients for this user
        if not portfolio_items:
            portfolio_items = db.execute(text("""
                SELECT m.id, m.client_name, m.email, m.phone, m.loan_number,
                       m.next_touchpoint, m.refinance_opportunity, m.estimated_savings,
                       m.last_contact, m.interest_rate, m.current_loan_amount
                FROM mum_clients m
                WHERE m.loan_officer_id = :user_id
                ORDER BY m.id DESC
                LIMIT 10
            """), {"user_id": user_id}).fetchall()

        for client in portfolio_items:
            is_overdue = client.next_touchpoint < now if client.next_touchpoint else False
            priority = "high" if is_overdue else "medium"

            if client.refinance_opportunity and client.estimated_savings:
                description = f"Refi opportunity - save ${client.estimated_savings:,.0f}/mo"
            elif client.next_touchpoint:
                description = "Touchpoint due"
            else:
                description = f"Portfolio client - {client.loan_number or 'review needed'}"

            action_items["portfolio"].append({
                "id": f"portfolio_{client.id}",
                "type": "touchpoint",
                "priority": priority,
                "title": f"Contact {client.client_name}",
                "description": description,
                "entity_type": "portfolio",
                "entity_id": client.id,
                "entity_name": client.client_name,
                "loan_number": client.loan_number,
                "due_date": client.next_touchpoint.isoformat() if client.next_touchpoint else None,
                "url": f"/portfolio/{client.id}",
                "refinance_opportunity": client.refinance_opportunity,
                "estimated_savings": client.estimated_savings
            })
    except Exception as e:
        logger.warning(f"Command center - portfolio error: {e}")
        db.rollback()

    # 5. EMAILS - Unanswered/unprocessed emails
    try:
        pending_emails = db.execute(text("""
            SELECT ei.id, ei.from_email, ei.subject, ei.received_at,
                   ei.match_status, ei.loan_id, ei.lead_id,
                   COALESCE(l.borrower_name, ld.name) as entity_name
            FROM email_intakes ei
            LEFT JOIN loans l ON ei.loan_id = l.id
            LEFT JOIN leads ld ON ei.lead_id = ld.id
            WHERE ei.processing_status = 'pending'
               OR (ei.match_status = 'UNMATCHED' AND ei.received_at > NOW() - INTERVAL '7 days')
            ORDER BY ei.received_at DESC
            LIMIT 20
        """)).fetchall()

        for email in pending_emails:
            hours_old = (now - email.received_at).total_seconds() / 3600 if email.received_at else 0
            priority = "critical" if hours_old > 24 else "high" if hours_old > 4 else "medium"

            action_items["emails"].append({
                "id": f"email_{email.id}",
                "type": "email_pending",
                "priority": priority,
                "title": email.subject or "(No subject)",
                "description": f"From: {email.from_email}",
                "entity_type": "loan" if email.loan_id else "lead" if email.lead_id else "email",
                "entity_id": email.loan_id or email.lead_id or email.id,
                "entity_name": email.entity_name,
                "from_email": email.from_email,
                "received_at": email.received_at.isoformat() if email.received_at else None,
                "url": "/reconciliation",
                "match_status": email.match_status,
                "hours_old": round(hours_old, 1)
            })
    except Exception as e:
        logger.warning(f"Command center - emails error: {e}")
        db.rollback()

    # 6. SMS - Unanswered inbound messages
    try:
        unanswered_sms = db.execute(text("""
            SELECT sc.id, sc.lead_id, sc.loan_id, sc.phone_number,
                   sc.last_message_at, sc.unread_count,
                   sm.content as last_message,
                   COALESCE(l.borrower_name, ld.name) as entity_name
            FROM sms_conversations sc
            LEFT JOIN sms_messages sm ON sm.conversation_id = sc.id
                AND sm.id = (SELECT MAX(id) FROM sms_messages WHERE conversation_id = sc.id AND sender = 'inbound')
            LEFT JOIN loans l ON sc.loan_id = l.id
            LEFT JOIN leads ld ON sc.lead_id = ld.id
            WHERE sc.user_id = :user_id
              AND sc.unread_count > 0
            ORDER BY sc.last_message_at DESC
            LIMIT 15
        """), {"user_id": user_id}).fetchall()

        for sms in unanswered_sms:
            hours_old = (now - sms.last_message_at).total_seconds() / 3600 if sms.last_message_at else 0
            priority = "critical" if hours_old > 4 else "high" if hours_old > 1 else "medium"

            action_items["sms"].append({
                "id": f"sms_{sms.id}",
                "type": "sms_unanswered",
                "priority": priority,
                "title": f"SMS from {sms.entity_name or sms.phone_number}",
                "description": (sms.last_message[:80] + "...") if sms.last_message and len(sms.last_message) > 80 else sms.last_message,
                "entity_type": "loan" if sms.loan_id else "lead",
                "entity_id": sms.loan_id or sms.lead_id,
                "entity_name": sms.entity_name,
                "phone_number": sms.phone_number,
                "received_at": sms.last_message_at.isoformat() if sms.last_message_at else None,
                "url": f"/{'loans' if sms.loan_id else 'leads'}/{sms.loan_id or sms.lead_id}",
                "unread_count": sms.unread_count,
                "hours_old": round(hours_old, 1)
            })
    except Exception as e:
        logger.warning(f"Command center - SMS error: {e}")
        db.rollback()

    # 7. CALLS - Pending voicemail drops and missed calls
    try:
        pending_calls = db.execute(text("""
            SELECT vd.id, vd.lead_id, vd.loan_id, vd.phone_number,
                   vd.status, vd.created_at, vd.message_text,
                   COALESCE(l.borrower_name, ld.name) as entity_name
            FROM voicemail_drops vd
            LEFT JOIN loans l ON vd.loan_id = l.id
            LEFT JOIN leads ld ON vd.lead_id = ld.id
            WHERE vd.status IN ('pending', 'queued', 'human_answered')
            ORDER BY vd.created_at DESC
            LIMIT 15
        """)).fetchall()

        for call in pending_calls:
            priority = "high" if call.status == 'human_answered' else "medium"
            status_text = "Human answered - follow up!" if call.status == 'human_answered' else f"Status: {call.status}"

            action_items["calls"].append({
                "id": f"call_{call.id}",
                "type": "voicemail",
                "priority": priority,
                "title": f"Call {call.entity_name or call.phone_number}",
                "description": status_text,
                "entity_type": "loan" if call.loan_id else "lead",
                "entity_id": call.loan_id or call.lead_id,
                "entity_name": call.entity_name,
                "phone_number": call.phone_number,
                "created_at": call.created_at.isoformat() if call.created_at else None,
                "url": f"/{'loans' if call.loan_id else 'leads'}/{call.loan_id or call.lead_id}",
                "call_status": call.status
            })
    except Exception as e:
        logger.warning(f"Command center - calls error: {e}")
        db.rollback()

    # 8. RECONCILIATION - Pending data matches
    try:
        reconciliation_items = db.execute(text("""
            SELECT ed.id, ed.event_id, ed.source_type, ed.extracted_email,
                   ed.extracted_name, ed.created_at, ed.is_processed,
                   ide.raw_data
            FROM extracted_data ed
            LEFT JOIN incoming_data_events ide ON ed.event_id = ide.id
            WHERE ed.is_processed = false
              AND ed.created_at > NOW() - INTERVAL '14 days'
            ORDER BY ed.created_at DESC
            LIMIT 20
        """)).fetchall()

        for item in reconciliation_items:
            hours_old = (now - item.created_at).total_seconds() / 3600 if item.created_at else 0
            priority = "high" if hours_old > 24 else "medium"

            action_items["reconciliation"].append({
                "id": f"recon_{item.id}",
                "type": "reconciliation",
                "priority": priority,
                "title": f"Match: {item.extracted_name or item.extracted_email or 'Unknown'}",
                "description": f"Source: {item.source_type}",
                "source_type": item.source_type,
                "extracted_email": item.extracted_email,
                "extracted_name": item.extracted_name,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "url": "/reconciliation",
                "hours_old": round(hours_old, 1)
            })
    except Exception as e:
        logger.warning(f"Command center - reconciliation error: {e}")
        db.rollback()

    # 9. APPROVALS - AI actions pending approval
    try:
        pending_approvals = db.query(AIAction).filter(
            AIAction.status == "pending"
        ).order_by(AIAction.created_at.desc()).limit(15).all()

        for action in pending_approvals:
            action_items["approvals"].append({
                "id": f"approval_{action.id}",
                "type": "ai_approval",
                "priority": "medium",
                "title": f"AI Action: {action.action_type}",
                "description": action.reasoning[:100] if action.reasoning else None,
                "entity_type": action.entity_type,
                "entity_id": action.entity_id,
                "action_type": action.action_type,
                "confidence": action.confidence,
                "created_at": action.created_at.isoformat() if action.created_at else None,
                "url": "/ai-actions"
            })
    except Exception as e:
        logger.warning(f"Command center - approvals error: {e}")
        db.rollback()

    # 10. WORKFLOW TASKS - Dynamic tasks from workflow configurations
    try:
        # Use the workflow tasks logic function if available
        if _get_all_workflow_tasks_logic:
            try:
                workflow_tasks = _get_all_workflow_tasks_logic(db, current_user, days_ahead=14)
            except Exception as e:
                logger.error(f"Error fetching workflow tasks: {e}")
                workflow_tasks = []
        else:
            workflow_tasks = []

        for task in workflow_tasks:
            # Skip phone-only tasks (those go to Power Dialer)
            comm_methods = task.get("communication_methods", [])
            if comm_methods == ["phone"]:
                continue

            priority = task.get("urgency", "medium")
            is_overdue = task.get("days_until_due", 0) < 0

            workflow_item = {
                "id": task.get("id", f"workflow_{task.get('client_id')}"),
                "type": "workflow_task",
                "priority": "critical" if is_overdue else priority,
                "title": task.get("title", "Workflow Task"),
                "description": task.get("description", ""),
                "entity_type": task.get("client_type", "lead"),
                "entity_id": task.get("client_id"),
                "entity_name": task.get("client_name"),
                "workflow_name": task.get("workflow_name"),
                "workflow_color": task.get("workflow_color"),
                "due_date": task.get("due_date"),
                "url": f"/{'leads' if task.get('client_type') == 'lead' else 'loans'}/{task.get('client_id')}",
                "days_until_due": task.get("days_until_due"),
                "communication_methods": comm_methods,
                "source": "Workflow"
            }

            # Add to appropriate category based on client type and urgency
            if is_overdue:
                action_items["urgent"].append(workflow_item)
            elif task.get("client_type") == "lead":
                action_items["leads"].append(workflow_item)
            else:
                action_items["loans"].append(workflow_item)
    except Exception as e:
        logger.warning(f"Command center - workflow tasks error: {e}")
        db.rollback()

    # Calculate summary counts
    action_items["summary"] = {
        "urgent_count": len(action_items["urgent"]),
        "leads_count": len(action_items["leads"]),
        "loans_count": len(action_items["loans"]),
        "portfolio_count": len(action_items["portfolio"]),
        "emails_count": len(action_items["emails"]),
        "sms_count": len(action_items["sms"]),
        "calls_count": len(action_items["calls"]),
        "reconciliation_count": len(action_items["reconciliation"]),
        "approvals_count": len(action_items["approvals"]),
        "total_action_items": sum([
            len(action_items["urgent"]),
            len(action_items["leads"]),
            len(action_items["loans"]),
            len(action_items["portfolio"]),
            len(action_items["emails"]),
            len(action_items["sms"]),
            len(action_items["calls"]),
            len(action_items["reconciliation"]),
            len(action_items["approvals"])
        ]),
        "generated_at": now.isoformat()
    }

    return action_items
