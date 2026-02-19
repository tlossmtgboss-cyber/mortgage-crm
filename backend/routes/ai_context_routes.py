"""
AI Context Routes

Comprehensive data endpoints for AI queries, providing context about leads, loans,
clients, tasks, emails, calendar events, and pipeline information.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from typing import Optional
import logging

from db import get_db

router = APIRouter(prefix="/api/v1/ai/context", tags=["AI Context"])
logger = logging.getLogger(__name__)


# =============================================================================
# Dependencies - Import from main at runtime to avoid circular imports
# =============================================================================

def get_current_user_flexible_dep():
    """Get current user flexible - imports from main at runtime"""
    import main
    return main.get_current_user_flexible


def get_models():
    """Get model classes from main at runtime to avoid circular imports"""
    import main
    return {
        "User": main.User,
        "Lead": main.Lead,
        "Loan": main.Loan,
        "Task": main.Task,
        "MUMClient": main.MUMClient,
        "ReferralPartner": main.ReferralPartner,
        "Email": main.Email,
        "ClientProfile": main.ClientProfile,
    }


def _get_org_id(current_user) -> Optional[int]:
    """Extract organization_id from the current user for tenant scoping."""
    return getattr(current_user, 'organization_id', None)


# ============================================================================
# AI CONTEXT ENDPOINTS - Comprehensive data for AI queries
# ============================================================================

@router.get("/lead/{lead_id}")
async def get_lead_context_for_ai(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return complete lead context for AI queries"""
    models = get_models()
    Lead = models["Lead"]

    org_id = _get_org_id(current_user)
    lead_query = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id)
    if org_id:
        lead_query = lead_query.filter(Lead.organization_id == org_id)
    lead = lead_query.first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Get activities/contact history (tenant-scoped)
    activity_params = {"lead_id": lead_id}
    activity_org_filter = ""
    if org_id:
        activity_org_filter = "AND organization_id = :org_id"
        activity_params["org_id"] = org_id
    activities = db.execute(
        text(f"""
            SELECT type, content, created_at
            FROM activities
            WHERE lead_id = :lead_id {activity_org_filter}
            ORDER BY created_at DESC
            LIMIT 20
        """),
        activity_params
    ).fetchall()

    # Get tasks for this lead (tenant-scoped via owner_id)
    tasks = db.execute(
        text("""
            SELECT title, status, due_date, priority, created_at
            FROM tasks
            WHERE lead_id = :lead_id
            ORDER BY created_at DESC
            LIMIT 10
        """),
        {"lead_id": lead_id}
    ).fetchall()

    return {
        "lead_id": lead.id,
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "current_status": lead.stage,
        "source": lead.source,
        "loan_type": lead.loan_type,
        "loan_amount": lead.preapproval_amount,
        "credit_score": lead.credit_score,
        "property_value": lead.property_value,
        "down_payment": lead.down_payment,
        "annual_income": lead.annual_income,
        "debt_to_income": lead.debt_to_income,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "last_contact": lead.last_contact.isoformat() if lead.last_contact else None,
        "contact_history": [
            {
                "type": a[0],
                "content": a[1],
                "date": a[2].isoformat() if a[2] else None
            }
            for a in activities
        ],
        "pending_tasks": [
            {
                "title": t[0],
                "status": t[1],
                "due_date": t[2].isoformat() if t[2] else None,
                "priority": t[3]
            }
            for t in tasks
        ],
        "timeline_summary": f"Lead created {lead.created_at.strftime('%Y-%m-%d') if lead.created_at else 'N/A'}, currently in {lead.stage} stage with {len(activities)} recorded activities"
    }


@router.get("/loan/{loan_id}")
async def get_loan_context_for_ai(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return complete loan context for AI queries"""
    models = get_models()
    Loan = models["Loan"]

    org_id = _get_org_id(current_user)
    loan_query = db.query(Loan).filter(
        Loan.id == loan_id,
        Loan.loan_officer_id == current_user.id
    )
    if org_id:
        loan_query = loan_query.filter(Loan.organization_id == org_id)
    loan = loan_query.first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Get loan activities (tenant-scoped)
    activity_params = {"loan_id": loan_id}
    activity_org_filter = ""
    if org_id:
        activity_org_filter = "AND organization_id = :org_id"
        activity_params["org_id"] = org_id
    activities = db.execute(
        text(f"""
            SELECT type, content, created_at
            FROM activities
            WHERE loan_id = :loan_id {activity_org_filter}
            ORDER BY created_at DESC
            LIMIT 20
        """),
        activity_params
    ).fetchall()

    # Get loan tasks
    tasks = db.execute(
        text("""
            SELECT title, status, due_date, priority
            FROM tasks
            WHERE loan_id = :loan_id
            ORDER BY created_at DESC
            LIMIT 10
        """),
        {"loan_id": loan_id}
    ).fetchall()

    # Get workflow alerts (table may not exist)
    try:
        alerts = db.execute(
            text("""
                SELECT alert_type, alert_message, severity, created_at
                FROM workflow_alerts
                WHERE loan_id = :loan_id AND is_resolved = false
                ORDER BY created_at DESC
                LIMIT 5
            """),
            {"loan_id": loan_id}
        ).fetchall()
    except Exception:
        alerts = []

    return {
        "loan_id": loan.id,
        "loan_number": loan.loan_number,
        "borrower_name": loan.borrower_name,
        "property_address": loan.property_address,
        "current_stage": str(loan.stage) if loan.stage else None,
        "loan_type": loan.loan_type,
        "loan_amount": loan.amount,
        "interest_rate": loan.rate,
        "lock_date": loan.lock_date.isoformat() if loan.lock_date else None,
        "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
        "processor": loan.processor,
        "underwriter": loan.underwriter,
        "created_at": loan.created_at.isoformat() if loan.created_at else None,
        "activity_history": [
            {
                "type": a[0],
                "description": a[1],
                "date": a[2].isoformat() if a[2] else None
            }
            for a in activities
        ],
        "pending_tasks": [
            {
                "title": t[0],
                "status": t[1],
                "due_date": t[2].isoformat() if t[2] else None,
                "priority": t[3]
            }
            for t in tasks
        ],
        "active_alerts": [
            {
                "type": a[0],
                "message": a[1],
                "severity": a[2],
                "date": a[3].isoformat() if a[3] else None
            }
            for a in alerts
        ],
        "days_in_stage": loan.days_in_stage or 0,
        "timeline_summary": f"Loan {loan.loan_number} for {loan.borrower_name} at {loan.property_address}, currently in {str(loan.stage) if loan.stage else 'Unknown'} stage"
    }


@router.get("/client/{client_id}")
async def get_client_context_for_ai(
    client_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return complete MUM client context for AI queries"""
    models = get_models()
    MUMClient = models["MUMClient"]

    org_id = _get_org_id(current_user)
    client_query = db.query(MUMClient).filter(
        MUMClient.id == client_id,
        MUMClient.user_id == current_user.id
    )
    if org_id:
        client_query = client_query.filter(MUMClient.organization_id == org_id)
    client = client_query.first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Get client activities (tenant-scoped)
    activity_params = {"client_id": client_id}
    activity_org_filter = ""
    if org_id:
        activity_org_filter = "AND organization_id = :org_id"
        activity_params["org_id"] = org_id
    activities = db.execute(
        text(f"""
            SELECT type, content, created_at
            FROM activities
            WHERE mum_client_id = :client_id {activity_org_filter}
            ORDER BY created_at DESC
            LIMIT 20
        """),
        activity_params
    ).fetchall()

    # Get tasks for this client
    tasks = db.execute(
        text("""
            SELECT title, status, due_date, priority
            FROM ai_tasks
            WHERE mum_client_id = :client_id
            ORDER BY created_at DESC
            LIMIT 10
        """),
        {"client_id": client_id}
    ).fetchall()

    # Get loan balance
    loan_balance = client.loan_balance or 0

    return {
        "client_id": client.id,
        "name": client.name,
        "email": client.email,
        "phone": client.phone,
        "loan_number": client.loan_number,
        "original_close_date": client.original_close_date.isoformat() if client.original_close_date else None,
        "original_rate": client.original_rate,
        "current_rate": client.current_rate,
        "loan_balance": loan_balance,
        "days_since_funding": client.days_since_funding,
        "refinance_opportunity": client.refinance_opportunity,
        "estimated_savings": client.estimated_savings,
        "engagement_score": client.engagement_score,
        "status": client.status,
        "last_contact": client.last_contact.isoformat() if client.last_contact else None,
        "next_touchpoint": client.next_touchpoint.isoformat() if client.next_touchpoint else None,
        "referrals_sent": client.referrals_sent,
        "notes": client.notes,
        "loan_officer": client.loan_officer,
        "processor": client.processor,
        "contact_history": [
            {
                "type": a[0],
                "description": a[1],
                "date": a[2].isoformat() if a[2] else None
            }
            for a in activities
        ],
        "pending_tasks": [
            {
                "title": t[0],
                "status": t[1],
                "due_date": t[2].isoformat() if t[2] else None,
                "priority": t[3]
            }
            for t in tasks
        ],
        "refinance_analysis": {
            "has_opportunity": client.refinance_opportunity,
            "estimated_savings": client.estimated_savings,
            "rate_reduction_potential": (client.original_rate - client.current_rate) if client.original_rate and client.current_rate else 0,
            "years_since_closing": (client.days_since_funding // 365) if client.days_since_funding else None
        },
        "timeline_summary": f"Client since {client.original_close_date.strftime('%Y') if client.original_close_date else 'N/A'}, {client.days_since_funding or 0} days since funding, rate {client.current_rate}%"
    }


@router.get("/summary")
async def get_ai_context_summary(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return overall CRM summary for AI context"""
    org_id = _get_org_id(current_user)
    base_params = {"user_id": current_user.id}
    org_filter = ""
    if org_id:
        org_filter = "AND organization_id = :org_id"
        base_params["org_id"] = org_id

    # Count leads by stage
    lead_counts = db.execute(
        text(f"""
            SELECT stage, COUNT(*) as count
            FROM leads
            WHERE owner_id = :user_id {org_filter}
            GROUP BY stage
        """),
        base_params
    ).fetchall()

    # Count active loans by stage
    loan_counts = db.execute(
        text(f"""
            SELECT stage, COUNT(*) as count
            FROM loans
            WHERE loan_officer_id = :user_id {org_filter}
            GROUP BY stage
        """),
        base_params
    ).fetchall()

    # Get pending tasks count (ai_tasks table may not exist)
    try:
        pending_tasks = db.execute(
            text(f"""
                SELECT COUNT(*) FROM ai_tasks
                WHERE user_id = :user_id {org_filter} AND status != 'completed'
            """),
            base_params
        ).scalar()
    except Exception:
        pending_tasks = 0

    # Get MUM client count and total equity
    try:
        mum_stats = db.execute(
            text(f"""
                SELECT
                    COUNT(*) as total_clients,
                    SUM(COALESCE(loan_balance, 0)) as total_balance
                FROM mum_clients
                WHERE user_id = :user_id {org_filter}
            """),
            base_params
        ).fetchone()
    except Exception:
        mum_stats = (0, 0)

    return {
        "leads_by_stage": {row[0]: row[1] for row in lead_counts},
        "total_leads": sum(row[1] for row in lead_counts),
        "loans_by_stage": {row[0]: row[1] for row in loan_counts},
        "total_active_loans": sum(row[1] for row in loan_counts),
        "pending_tasks": pending_tasks or 0,
        "mum_clients": mum_stats[0] if mum_stats else 0,
        "total_portfolio_balance": float(mum_stats[1]) if mum_stats and mum_stats[1] else 0,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/task/{task_id}")
async def get_task_context_for_ai(
    task_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return complete task context for AI queries"""
    models = get_models()
    Task = models["Task"]
    Lead = models["Lead"]
    Loan = models["Loan"]

    org_id = _get_org_id(current_user)
    task_query = db.query(Task).filter(
        Task.id == task_id,
        Task.owner_id == current_user.id
    )
    if org_id:
        task_query = task_query.filter(Task.organization_id == org_id)
    task = task_query.first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get related lead info if exists
    lead_info = None
    if task.lead_id:
        lead_query = db.query(Lead).filter(Lead.id == task.lead_id)
        if org_id:
            lead_query = lead_query.filter(Lead.organization_id == org_id)
        lead = lead_query.first()
        if lead:
            lead_info = {
                "id": lead.id,
                "name": lead.name,
                "stage": str(lead.stage.value) if lead.stage else None,
                "email": lead.email,
                "phone": lead.phone
            }

    # Get related loan info if exists
    loan_info = None
    if task.loan_id:
        loan_query = db.query(Loan).filter(Loan.id == task.loan_id)
        if org_id:
            loan_query = loan_query.filter(Loan.organization_id == org_id)
        loan = loan_query.first()
        if loan:
            loan_info = {
                "id": loan.id,
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "stage": str(loan.stage) if loan.stage else None,
                "amount": loan.amount
            }

    return {
        "task_id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "related_lead": lead_info,
        "related_loan": loan_info,
        "related_contact_name": task.related_contact_name,
        "context_summary": f"Task '{task.title}' ({task.status}) - Priority: {task.priority}, Due: {task.due_date.strftime('%Y-%m-%d') if task.due_date else 'No due date'}"
    }


@router.get("/user/profile")
async def get_user_profile_context_for_ai(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return current user's profile and performance context for AI"""
    org_id = _get_org_id(current_user)
    base_params = {"user_id": current_user.id}
    org_filter = ""
    if org_id:
        org_filter = "AND organization_id = :org_id"
        base_params["org_id"] = org_id

    # Get task stats
    try:
        task_stats = db.execute(
            text(f"""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') as pending,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed,
                    COUNT(*) FILTER (WHERE status = 'in_progress') as in_progress,
                    COUNT(*) FILTER (WHERE due_date < CURRENT_DATE AND status != 'completed') as overdue
                FROM tasks
                WHERE owner_id = :user_id {org_filter}
            """),
            base_params
        ).fetchone()
    except Exception:
        db.rollback()
        task_stats = (0, 0, 0, 0)

    # Get lead stats
    try:
        lead_stats = db.execute(
            text(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE created_at > CURRENT_DATE - INTERVAL '30 days') as new_this_month
                FROM leads
                WHERE owner_id = :user_id {org_filter}
            """),
            base_params
        ).fetchone()
    except Exception:
        db.rollback()
        lead_stats = (0, 0)

    # Get loan stats
    try:
        loan_stats = db.execute(
            text(f"""
                SELECT
                    COUNT(*) as total,
                    COALESCE(SUM(amount), 0) as total_volume,
                    COUNT(*) FILTER (WHERE stage::text LIKE '%FUNDED%' OR stage::text LIKE '%Funded%') as funded_count
                FROM loans
                WHERE loan_officer_id = :user_id {org_filter}
            """),
            base_params
        ).fetchone()
    except Exception:
        db.rollback()
        loan_stats = (0, 0, 0)

    # Get recent activities count
    try:
        recent_activities = db.execute(
            text(f"""
                SELECT COUNT(*) FROM activities
                WHERE user_id = :user_id {org_filter} AND created_at > CURRENT_DATE - INTERVAL '7 days'
            """),
            base_params
        ).scalar()
    except Exception:
        db.rollback()
        recent_activities = 0

    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "task_stats": {
            "pending": task_stats[0] if task_stats else 0,
            "completed": task_stats[1] if task_stats else 0,
            "in_progress": task_stats[2] if task_stats else 0,
            "overdue": task_stats[3] if task_stats else 0
        },
        "lead_stats": {
            "total": lead_stats[0] if lead_stats else 0,
            "new_this_month": lead_stats[1] if lead_stats else 0
        },
        "loan_stats": {
            "total": loan_stats[0] if loan_stats else 0,
            "total_volume": float(loan_stats[1]) if loan_stats else 0,
            "funded_count": loan_stats[2] if loan_stats else 0
        },
        "recent_activities_7d": recent_activities or 0,
        "profile_summary": f"{current_user.full_name} ({current_user.role}) - {lead_stats[0] if lead_stats else 0} leads, {loan_stats[0] if loan_stats else 0} loans, {task_stats[0] if task_stats else 0} pending tasks"
    }


@router.get("/referral-partner/{partner_id}")
async def get_referral_partner_context_for_ai(
    partner_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return referral partner context for AI queries"""
    models = get_models()
    ReferralPartner = models["ReferralPartner"]

    org_id = _get_org_id(current_user)
    partner_query = db.query(ReferralPartner).filter(ReferralPartner.id == partner_id)
    if org_id:
        partner_query = partner_query.filter(ReferralPartner.organization_id == org_id)
    partner = partner_query.first()
    if not partner:
        raise HTTPException(status_code=404, detail="Referral partner not found")

    # Get leads from this partner (tenant-scoped)
    lead_params = {"partner_id": partner_id, "user_id": current_user.id}
    lead_org_filter = ""
    if org_id:
        lead_org_filter = "AND organization_id = :org_id"
        lead_params["org_id"] = org_id
    lead_stats = db.execute(
        text(f"""
            SELECT
                COUNT(*) as total_leads,
                COUNT(*) FILTER (WHERE stage IN ('Application', 'PRE_APPROVED', 'CLOSED')) as converted
            FROM leads
            WHERE referral_partner_id = :partner_id AND owner_id = :user_id {lead_org_filter}
        """),
        lead_params
    ).fetchone()

    # Get recent leads from this partner
    recent_leads = db.execute(
        text(f"""
            SELECT id, name, stage, created_at
            FROM leads
            WHERE referral_partner_id = :partner_id AND owner_id = :user_id {lead_org_filter}
            ORDER BY created_at DESC
            LIMIT 5
        """),
        lead_params
    ).fetchall()

    return {
        "partner_id": partner.id,
        "name": partner.name,
        "company": partner.company,
        "type": partner.type,
        "phone": partner.phone,
        "email": partner.email,
        "notes": partner.notes,
        "total_referrals": lead_stats[0] if lead_stats else 0,
        "converted_referrals": lead_stats[1] if lead_stats else 0,
        "conversion_rate": round((lead_stats[1] / lead_stats[0] * 100) if lead_stats and lead_stats[0] > 0 else 0, 1),
        "recent_leads": [
            {
                "id": l[0],
                "name": l[1],
                "stage": str(l[2]) if l[2] else None,
                "created_at": l[3].isoformat() if l[3] else None
            }
            for l in recent_leads
        ],
        "partner_summary": f"{partner.name} ({partner.type or 'Unknown type'}) from {partner.company or 'N/A'} - {lead_stats[0] if lead_stats else 0} referrals, {round((lead_stats[1] / lead_stats[0] * 100) if lead_stats and lead_stats[0] > 0 else 0, 1)}% conversion"
    }


@router.get("/email/{email_id}")
async def get_email_context_for_ai(
    email_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return email context for AI queries"""
    models = get_models()
    Email = models["Email"]
    Lead = models["Lead"]

    org_id = _get_org_id(current_user)
    email = db.query(Email).filter(
        Email.id == email_id,
        Email.user_id == current_user.id
    ).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    # Get related lead info if exists (tenant-scoped)
    lead_info = None
    if email.lead_id:
        lead_query = db.query(Lead).filter(Lead.id == email.lead_id)
        if org_id:
            lead_query = lead_query.filter(Lead.organization_id == org_id)
        lead = lead_query.first()
        if lead:
            lead_info = {
                "id": lead.id,
                "name": lead.name,
                "stage": str(lead.stage.value) if lead.stage else None
            }

    # Get other emails from same sender for context
    related_emails = db.execute(
        text("""
            SELECT id, subject, sender_email, received_date
            FROM emails
            WHERE sender_email = :sender_email AND user_id = :user_id AND id != :email_id
            ORDER BY received_date DESC
            LIMIT 5
        """),
        {"sender_email": email.sender_email, "user_id": current_user.id, "email_id": email_id}
    ).fetchall()

    return {
        "email_id": email.id,
        "message_id": email.message_id,
        "subject": email.subject,
        "sender_email": email.sender_email,
        "sender_name": email.sender_name,
        "recipients": email.recipient_emails,
        "body": email.body_text,
        "received_date": email.received_date.isoformat() if email.received_date else None,
        "is_read": email.is_read,
        "has_attachments": email.has_attachments,
        "folder": email.folder_name,
        "processed": email.processed,
        "ai_extracted_data": email.ai_extracted_data,
        "ai_confidence": email.ai_confidence,
        "related_lead": lead_info,
        "related_emails_from_sender": [
            {
                "id": e[0],
                "subject": e[1],
                "sender": e[2],
                "date": e[3].isoformat() if e[3] else None
            }
            for e in related_emails
        ],
        "email_summary": f"Email from {email.sender_name or email.sender_email}: '{email.subject}' - {'Processed' if email.processed else 'Unprocessed'}"
    }


@router.get("/calendar")
async def get_calendar_context_for_ai(
    days_ahead: int = 7,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return upcoming calendar events context for AI"""
    models = get_models()
    Lead = models["Lead"]
    Loan = models["Loan"]
    org_id = _get_org_id(current_user)

    events = db.execute(
        text("""
            SELECT id, title, description, start_time, end_time, location, event_type,
                   lead_id, loan_id, attendees
            FROM calendar_events
            WHERE user_id = :user_id
            AND start_time >= CURRENT_TIMESTAMP
            AND start_time <= CURRENT_TIMESTAMP + :days_interval * INTERVAL '1 day'
            ORDER BY start_time ASC
        """),
        {"user_id": current_user.id, "days_interval": days_ahead}
    ).fetchall()

    formatted_events = []
    for e in events:
        # Get related lead/loan names (tenant-scoped)
        lead_name = None
        loan_info = None
        if e[7]:  # lead_id
            lead_query = db.query(Lead).filter(Lead.id == e[7])
            if org_id:
                lead_query = lead_query.filter(Lead.organization_id == org_id)
            lead = lead_query.first()
            if lead:
                lead_name = lead.name
        if e[8]:  # loan_id
            loan_query = db.query(Loan).filter(Loan.id == e[8])
            if org_id:
                loan_query = loan_query.filter(Loan.organization_id == org_id)
            loan = loan_query.first()
            if loan:
                loan_info = f"{loan.loan_number} - {loan.borrower_name}"

        formatted_events.append({
            "id": e[0],
            "title": e[1],
            "description": e[2],
            "start_time": e[3].isoformat() if e[3] else None,
            "end_time": e[4].isoformat() if e[4] else None,
            "location": e[5],
            "event_type": e[6],
            "related_lead": lead_name,
            "related_loan": loan_info,
            "attendees": e[9]
        })

    return {
        "upcoming_events": formatted_events,
        "total_events": len(formatted_events),
        "days_covered": days_ahead,
        "calendar_summary": f"{len(formatted_events)} events in the next {days_ahead} days"
    }


@router.get("/account-profile/{profile_id}")
async def get_account_profile_context_for_ai(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return account/subscriber profile context for AI"""
    models = get_models()
    ClientProfile = models["ClientProfile"]

    org_id = _get_org_id(current_user)
    profile_query = db.query(ClientProfile).filter(
        ClientProfile.id == profile_id,
        ClientProfile.primary_user_id == current_user.id
    )
    if org_id:
        profile_query = profile_query.filter(ClientProfile.organization_id == org_id)
    profile = profile_query.first()
    if not profile:
        raise HTTPException(status_code=404, detail="Account profile not found")

    # Extract user profile from JSON
    user_profile = profile.user_profile or {}

    return {
        "profile_id": profile.id,
        "account_id": profile.account_id,
        "account_type": profile.account_type,
        "company_name": profile.company_name,
        "nmls_number": profile.nmls_number,
        "team_size": profile.team_size,
        "subscription_plan": profile.subscription_plan,
        "billing_status": profile.billing_status,
        "user_profile": user_profile,
        "kpi_targets": profile.kpi_targets,
        "automation_settings": profile.automation_settings,
        "integration_settings": profile.integration_settings,
        "profile_summary": f"{profile.company_name or 'Account'} ({profile.account_type or 'N/A'}) - {profile.team_size or 1} team members, {profile.subscription_plan or 'Unknown'} plan"
    }


@router.get("/pipeline")
async def get_pipeline_context_for_ai(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return detailed pipeline health context for AI"""
    org_id = _get_org_id(current_user)
    base_params = {"user_id": current_user.id}
    org_filter = ""
    if org_id:
        org_filter = "AND organization_id = :org_id"
        base_params["org_id"] = org_id

    # Lead pipeline by stage with values
    lead_pipeline = db.execute(
        text(f"""
            SELECT
                stage,
                COUNT(*) as count,
                COALESCE(SUM(preapproval_amount), 0) as total_value,
                AVG(ai_score) as avg_score
            FROM leads
            WHERE owner_id = :user_id {org_filter}
            GROUP BY stage
            ORDER BY count DESC
        """),
        base_params
    ).fetchall()

    # Loan pipeline by stage
    loan_pipeline = db.execute(
        text(f"""
            SELECT
                stage,
                COUNT(*) as count,
                COALESCE(SUM(amount), 0) as total_value,
                AVG(days_in_stage) as avg_days
            FROM loans
            WHERE loan_officer_id = :user_id {org_filter}
            GROUP BY stage
            ORDER BY count DESC
        """),
        base_params
    ).fetchall()

    # At-risk loans (high days in stage)
    at_risk_loans = db.execute(
        text(f"""
            SELECT id, loan_number, borrower_name, stage, days_in_stage, amount
            FROM loans
            WHERE loan_officer_id = :user_id {org_filter} AND days_in_stage > 7
            ORDER BY days_in_stage DESC
            LIMIT 5
        """),
        base_params
    ).fetchall()

    # Hot leads (high AI score)
    hot_leads = db.execute(
        text(f"""
            SELECT id, name, stage, ai_score, preapproval_amount, last_contact
            FROM leads
            WHERE owner_id = :user_id {org_filter} AND ai_score >= 70
            ORDER BY ai_score DESC
            LIMIT 5
        """),
        base_params
    ).fetchall()

    # Closing this week
    closing_soon = db.execute(
        text(f"""
            SELECT id, loan_number, borrower_name, amount, closing_date, stage
            FROM loans
            WHERE loan_officer_id = :user_id {org_filter}
            AND closing_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'
            ORDER BY closing_date ASC
        """),
        base_params
    ).fetchall()

    return {
        "lead_pipeline": [
            {
                "stage": str(l[0]) if l[0] else "Unknown",
                "count": l[1],
                "total_value": float(l[2]),
                "avg_ai_score": round(float(l[3]), 1) if l[3] else 0
            }
            for l in lead_pipeline
        ],
        "loan_pipeline": [
            {
                "stage": str(l[0]) if l[0] else "Unknown",
                "count": l[1],
                "total_value": float(l[2]),
                "avg_days_in_stage": round(float(l[3]), 1) if l[3] else 0
            }
            for l in loan_pipeline
        ],
        "at_risk_loans": [
            {
                "id": l[0],
                "loan_number": l[1],
                "borrower_name": l[2],
                "stage": str(l[3]) if l[3] else None,
                "days_in_stage": l[4],
                "amount": l[5]
            }
            for l in at_risk_loans
        ],
        "hot_leads": [
            {
                "id": l[0],
                "name": l[1],
                "stage": str(l[2]) if l[2] else None,
                "ai_score": l[3],
                "loan_amount": l[4],
                "last_contact": l[5].isoformat() if l[5] else None
            }
            for l in hot_leads
        ],
        "closing_this_week": [
            {
                "id": l[0],
                "loan_number": l[1],
                "borrower_name": l[2],
                "amount": l[3],
                "closing_date": l[4].isoformat() if l[4] else None,
                "stage": str(l[5]) if l[5] else None
            }
            for l in closing_soon
        ],
        "pipeline_summary": f"Pipeline: {sum(l[1] for l in lead_pipeline)} leads (${sum(l[2] for l in lead_pipeline):,.0f}), {sum(l[1] for l in loan_pipeline)} loans (${sum(l[2] for l in loan_pipeline):,.0f}), {len(at_risk_loans)} at-risk, {len(closing_soon)} closing this week"
    }


@router.get("/activity-feed")
async def get_activity_feed_context_for_ai(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return recent activity feed for AI context"""
    org_id = _get_org_id(current_user)
    activity_params = {"user_id": current_user.id, "limit": limit}
    org_filter = ""
    if org_id:
        org_filter = "AND a.organization_id = :org_id"
        activity_params["org_id"] = org_id

    activities = db.execute(
        text(f"""
            SELECT a.id, a.type, a.content, a.created_at, a.lead_id, a.loan_id,
                   l.name as lead_name, lo.loan_number, lo.borrower_name
            FROM activities a
            LEFT JOIN leads l ON a.lead_id = l.id
            LEFT JOIN loans lo ON a.loan_id = lo.id
            WHERE a.user_id = :user_id {org_filter}
            ORDER BY a.created_at DESC
            LIMIT :limit
        """),
        activity_params
    ).fetchall()

    return {
        "activities": [
            {
                "id": a[0],
                "type": str(a[1]) if a[1] else None,
                "content": a[2],
                "timestamp": a[3].isoformat() if a[3] else None,
                "related_lead": {"id": a[4], "name": a[6]} if a[4] else None,
                "related_loan": {"id": a[5], "loan_number": a[7], "borrower": a[8]} if a[5] else None
            }
            for a in activities
        ],
        "total_count": len(activities),
        "feed_summary": f"Last {len(activities)} activities for user"
    }


@router.get("/mum-client/{client_id}")
async def get_mum_client_context_for_ai(
    client_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return MUM (Monitor & Upsell Mortgage) client context for AI"""
    models = get_models()
    MUMClient = models["MUMClient"]

    org_id = _get_org_id(current_user)
    client_query = db.query(MUMClient).filter(
        MUMClient.id == client_id,
        MUMClient.user_id == current_user.id
    )
    if org_id:
        client_query = client_query.filter(MUMClient.organization_id == org_id)
    client = client_query.first()
    if not client:
        raise HTTPException(status_code=404, detail="MUM client not found")

    # Get related activities (tenant-scoped)
    activity_params = {"client_id": client_id}
    activity_org_filter = ""
    if org_id:
        activity_org_filter = "AND organization_id = :org_id"
        activity_params["org_id"] = org_id
    activities = db.execute(
        text(f"""
            SELECT type, content, created_at
            FROM activities
            WHERE mum_client_id = :client_id {activity_org_filter}
            ORDER BY created_at DESC
            LIMIT 10
        """),
        activity_params
    ).fetchall()

    return {
        "client_id": client.id,
        "name": client.name,
        "email": client.email,
        "phone": client.phone,
        "loan_number": client.loan_number,
        "original_close_date": client.original_close_date.isoformat() if client.original_close_date else None,
        "days_since_funding": client.days_since_funding,
        "original_rate": client.original_rate,
        "current_rate": client.current_rate,
        "loan_balance": client.loan_balance,
        "refinance_opportunity": client.refinance_opportunity,
        "estimated_savings": client.estimated_savings,
        "engagement_score": client.engagement_score,
        "status": client.status,
        "last_contact": client.last_contact.isoformat() if client.last_contact else None,
        "next_touchpoint": client.next_touchpoint.isoformat() if client.next_touchpoint else None,
        "referrals_sent": client.referrals_sent,
        "notes": client.notes,
        "opportunity_notes": client.opportunity_notes,
        "team": {
            "loan_officer": client.loan_officer,
            "processor": client.processor,
            "underwriter": client.underwriter,
            "closer": client.closer
        },
        "recent_activities": [
            {
                "type": str(a[0]) if a[0] else None,
                "content": a[1],
                "date": a[2].isoformat() if a[2] else None
            }
            for a in activities
        ],
        "client_summary": f"{client.name} - Loan #{client.loan_number or 'N/A'}, ${client.loan_balance or 0:,.0f} balance at {client.current_rate or 0}%, {'Refi opportunity' if client.refinance_opportunity else 'No refi opportunity'}"
    }


@router.get("/tasks")
async def get_all_tasks_context_for_ai(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Return all tasks context for AI queries"""
    org_id = _get_org_id(current_user)

    query = """
        SELECT t.id, t.title, t.description, t.status, t.priority, t.due_date,
               t.created_at, t.lead_id, t.loan_id, l.name as lead_name,
               lo.loan_number, lo.borrower_name
        FROM tasks t
        LEFT JOIN leads l ON t.lead_id = l.id
        LEFT JOIN loans lo ON t.loan_id = lo.id
        WHERE t.owner_id = :user_id
    """
    params = {"user_id": current_user.id}

    if org_id:
        query += " AND t.organization_id = :org_id"
        params["org_id"] = org_id

    if status:
        query += " AND t.status = :status"
        params["status"] = status

    query += " ORDER BY t.due_date ASC NULLS LAST, t.priority DESC LIMIT 50"

    tasks = db.execute(text(query), params).fetchall()

    # Get task stats
    stats_params = {"user_id": current_user.id}
    stats_org_filter = ""
    if org_id:
        stats_org_filter = "AND organization_id = :org_id"
        stats_params["org_id"] = org_id
    task_stats = db.execute(
        text(f"""
            SELECT
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COUNT(*) FILTER (WHERE status = 'in_progress') as in_progress,
                COUNT(*) FILTER (WHERE due_date < CURRENT_DATE AND status != 'completed') as overdue
            FROM tasks
            WHERE owner_id = :user_id {stats_org_filter}
        """),
        stats_params
    ).fetchone()

    return {
        "tasks": [
            {
                "id": t[0],
                "title": t[1],
                "description": t[2],
                "status": t[3],
                "priority": t[4],
                "due_date": t[5].isoformat() if t[5] else None,
                "created_at": t[6].isoformat() if t[6] else None,
                "related_lead": {"id": t[7], "name": t[9]} if t[7] else None,
                "related_loan": {"id": t[8], "loan_number": t[10], "borrower": t[11]} if t[8] else None
            }
            for t in tasks
        ],
        "stats": {
            "pending": task_stats[0] if task_stats else 0,
            "completed": task_stats[1] if task_stats else 0,
            "in_progress": task_stats[2] if task_stats else 0,
            "overdue": task_stats[3] if task_stats else 0
        },
        "tasks_summary": f"{task_stats[0] if task_stats else 0} pending, {task_stats[3] if task_stats else 0} overdue tasks"
    }
