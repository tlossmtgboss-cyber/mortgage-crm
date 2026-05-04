# backend/routes/internal/aria_tool_routes.py
"""
Internal API endpoints for Aria voice agent tool calls.
These endpoints are called by the LiveKit agent worker via HTTP.
Auth: X-Internal-API-Key header (shared secret, no user JWT).
"""
import os
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db

logger = logging.getLogger("aria.internal")

router = APIRouter(prefix="/internal/aria", tags=["Aria Internal"])

def _verify_internal_key(request: Request):
    """Verify X-Internal-API-Key header matches the INTERNAL_API_KEY env var.
    Reads env at request time so tests can set it after module import.
    Uses constant-time comparison to prevent timing side-channel attacks."""
    import hmac
    expected = os.environ.get("INTERNAL_API_KEY", "")
    key = request.headers.get("X-Internal-API-Key", "")
    if not expected or not hmac.compare_digest(key, expected):
        raise HTTPException(status_code=403, detail="Invalid internal API key")


# ─── Request/Response Schemas ───────────────────────────────────────────────

class LeadLookupRequest(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    lead_id: Optional[int] = None
    organization_id: Optional[int] = None

class ToolExecuteRequest(BaseModel):
    tool_name: str
    params: Dict[str, Any] = {}
    organization_id: Optional[int] = None

class LeadCreateRequest(BaseModel):
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    source: str = "voice_assistant"
    loan_purpose: Optional[str] = None
    property_type: Optional[str] = None
    timeline: Optional[str] = None
    notes: Optional[str] = None
    organization_id: Optional[int] = None
    user_id: Optional[int] = None

class LeadUpdateRequest(BaseModel):
    lead_id: int
    phone: Optional[str] = None
    email: Optional[str] = None
    loan_purpose: Optional[str] = None
    property_type: Optional[str] = None
    timeline: Optional[str] = None
    notes: Optional[str] = None
    stage: Optional[str] = None
    credit_score: Optional[int] = None
    loan_amount: Optional[float] = None
    loan_type: Optional[str] = None
    interest_rate: Optional[float] = None
    loan_term: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    source: Optional[str] = None
    annual_income: Optional[float] = None
    employment_status: Optional[str] = None
    employer_name: Optional[str] = None
    property_value: Optional[float] = None
    down_payment: Optional[float] = None
    first_time_buyer: Optional[bool] = None
    occupancy_type: Optional[str] = None
    monthly_debts: Optional[float] = None
    preapproval_amount: Optional[float] = None
    loan_officer: Optional[str] = None
    processor: Optional[str] = None
    next_action: Optional[str] = None
    sentiment: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class LeadInfoRequest(BaseModel):
    lead_id: int
    organization_id: Optional[int] = None

class LoanStatusRequest(BaseModel):
    borrower_id: Optional[int] = None
    loan_id: Optional[int] = None
    organization_id: Optional[int] = None

class LOInfoRequest(BaseModel):
    lead_id: Optional[int] = None
    user_id: Optional[int] = None
    organization_id: Optional[int] = None


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/lead-lookup")
async def lead_lookup(
    req: LeadLookupRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _verify_internal_key(request)
    from database.models.lead_loan import Lead

    lead = None
    base_q = db.query(Lead)
    if req.organization_id:
        base_q = base_q.filter(Lead.organization_id == req.organization_id)

    if req.lead_id:
        lead = base_q.filter(Lead.id == req.lead_id).first()
    elif req.phone:
        from integrations.sms_service import _to_e164
        normalized = _to_e164(req.phone) or req.phone
        lead = base_q.filter(Lead.phone == normalized).first()
        if not lead:
            lead = base_q.filter(Lead.phone == req.phone).first()
    elif req.email:
        lead = base_q.filter(Lead.email == req.email).first()

    if not lead:
        return {"lead": None}

    return {
        "lead": {
            "id": lead.id,
            "first_name": getattr(lead, "first_name", None) or lead.name,
            "last_name": getattr(lead, "last_name", ""),
            "phone": lead.phone,
            "email": lead.email,
            "stage": lead.stage,
            "owner_id": lead.owner_id,
            "organization_id": lead.organization_id,
            "preferred_communication": getattr(lead, "preferred_communication", None),
            "loan_type": getattr(lead, "loan_type", None),
            "loan_amount": str(getattr(lead, "loan_amount", "")) if getattr(lead, "loan_amount", None) else None,
            "credit_score": getattr(lead, "credit_score", None),
        }
    }


@router.post("/lead-info")
async def lead_info(
    req: LeadInfoRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Return comprehensive lead data for the voice agent."""
    _verify_internal_key(request)
    from database.models.lead_loan import Lead
    q = db.query(Lead).filter(Lead.id == req.lead_id)
    if req.organization_id:
        q = q.filter(Lead.organization_id == req.organization_id)
    lead = q.first()
    if not lead:
        return {"error": f"Lead {req.lead_id} not found"}

    def _num(val):
        return float(val) if val is not None else None

    return {
        "id": lead.id,
        "first_name": getattr(lead, "first_name", None) or lead.name,
        "last_name": getattr(lead, "last_name", ""),
        "name": lead.name,
        "phone": lead.phone,
        "email": lead.email,
        "stage": lead.stage,
        "source": lead.source,
        "owner_id": lead.owner_id,
        "organization_id": lead.organization_id,
        "credit_score": getattr(lead, "credit_score", None),
        "loan_amount": _num(getattr(lead, "loan_amount", None)),
        "loan_type": getattr(lead, "loan_type", None),
        "loan_purpose": getattr(lead, "loan_purpose", None),
        "interest_rate": _num(getattr(lead, "interest_rate", None)),
        "loan_term": getattr(lead, "loan_term", None),
        "property_type": getattr(lead, "property_type", None),
        "property_value": _num(getattr(lead, "property_value", None)),
        "address": getattr(lead, "address", None),
        "city": getattr(lead, "city", None),
        "state": getattr(lead, "state", None),
        "zip_code": getattr(lead, "zip_code", None),
        "occupancy_type": getattr(lead, "occupancy_type", None),
        "down_payment": _num(getattr(lead, "down_payment", None)),
        "preapproval_amount": _num(getattr(lead, "preapproval_amount", None)),
        "annual_income": _num(getattr(lead, "annual_income", None)),
        "monthly_debts": _num(getattr(lead, "monthly_debts", None)),
        "employment_status": getattr(lead, "employment_status", None),
        "employer_name": getattr(lead, "employer_name", None),
        "first_time_buyer": getattr(lead, "first_time_buyer", None),
        "ai_score": getattr(lead, "ai_score", None),
        "sentiment": getattr(lead, "sentiment", None),
        "next_action": getattr(lead, "next_action", None),
        "notes": getattr(lead, "notes", None),
        "timeline": getattr(lead, "timeline", None),
        "loan_officer": getattr(lead, "loan_officer", None),
        "processor": getattr(lead, "processor", None),
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
    }


@router.post("/loan-status")
async def loan_status(
    req: LoanStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _verify_internal_key(request)
    from database.models.lead_loan import Loan, Lead

    loan = None
    if req.loan_id:
        q = db.query(Loan).filter(Loan.id == req.loan_id)
        if req.organization_id:
            q = q.filter(Loan.organization_id == req.organization_id)
        loan = q.first()
    elif req.borrower_id:
        q = db.query(Lead).filter(Lead.id == req.borrower_id)
        if req.organization_id:
            q = q.filter(Lead.organization_id == req.organization_id)
        lead = q.first()
        if lead:
            loan = db.query(Loan).filter(Loan.lead_id == lead.id).order_by(Loan.created_at.desc()).first()

    if not loan:
        return {"spoken_summary": "I couldn't find an active loan on file for that borrower."}

    stage = getattr(loan, "stage", "unknown")
    loan_type = getattr(loan, "loan_type", "")
    amount = getattr(loan, "loan_amount", "")
    amount_str = f"${amount:,.0f}" if amount else "unknown amount"

    return {
        "spoken_summary": f"The {loan_type or 'loan'} for {amount_str} is currently in {stage.replace('_', ' ').lower()}.",
        "stage": stage,
        "loan_type": loan_type,
        "loan_amount": str(amount) if amount else None,
        "loan_id": loan.id,
    }


@router.post("/tool/execute")
async def execute_tool(
    req: ToolExecuteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Generic tool execution — runs any @mortgage_tool by name."""
    _verify_internal_key(request)

    try:
        from agents.tools import tool_registry
        registry = tool_registry
        tool_def = registry.get(req.tool_name)
    except Exception as e:
        return {"error": f"Tool registry unavailable: {e}"}

    if tool_def is None:
        return {"error": f"Tool '{req.tool_name}' not found"}

    try:
        import asyncio
        import inspect

        # Validate params against tool function signature to prevent injection
        sig = inspect.signature(tool_def.func)
        allowed_params = set(sig.parameters.keys())
        unknown = set(req.params.keys()) - allowed_params
        if unknown:
            return {"error": f"Unknown parameters for '{req.tool_name}': {', '.join(sorted(unknown))}"}

        safe_params = {k: v for k, v in req.params.items() if k in allowed_params}
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: tool_def.func(**safe_params))
        if hasattr(result, "to_dict"):
            return {"result": result.to_dict()}
        return {"result": result}
    except Exception as e:
        logger.error(f"Tool {req.tool_name} failed: {e}")
        return {"error": str(e)}


@router.post("/lo-info")
async def lo_info(
    req: LOInfoRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get the assigned LO for a lead, or info about a specific user."""
    _verify_internal_key(request)
    from database.models.core import User
    from database.models.lead_loan import Lead

    lead_id = req.lead_id
    user_id = req.user_id

    if lead_id:
        q = db.query(Lead).filter(Lead.id == lead_id)
        if req.organization_id:
            q = q.filter(Lead.organization_id == req.organization_id)
        lead = q.first()
        if not lead or not lead.owner_id:
            return {"error": "No LO assigned to this lead"}
        user_id = lead.owner_id

    if not user_id:
        return {"error": "No user_id or lead_id provided"}

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": f"User {user_id} not found"}

    return {
        "id": user.id,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "full_name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
        "phone": user.phone or "",
        "email": user.email,
        "timezone": getattr(user, "timezone", "America/Chicago"),
    }


@router.post("/create-lead")
async def create_lead_endpoint(
    req: LeadCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Create a new lead from voice agent."""
    _verify_internal_key(request)
    from database.models.lead_loan import Lead

    lead = Lead(
        first_name=req.first_name,
        last_name=req.last_name,
        name=f"{req.first_name} {req.last_name}".strip(),
        phone=req.phone or "",
        email=req.email or "",
        source=req.source,
        loan_purpose=req.loan_purpose or "",
        property_type=req.property_type or "",
        timeline=req.timeline or "",
        notes=req.notes or "",
        stage="New",
    )
    if req.organization_id:
        lead.organization_id = req.organization_id
    if req.user_id:
        lead.owner_id = req.user_id
    db.add(lead)
    db.flush()

    from services.client_file_service import ensure_client_file
    ensure_client_file(db, lead)

    db.commit()
    db.refresh(lead)

    return {
        "lead_id": lead.id,
        "name": lead.name,
        "phone": lead.phone,
        "email": lead.email,
        "stage": lead.stage,
    }


@router.post("/update-lead")
async def update_lead_endpoint(
    req: LeadUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update an existing lead from voice agent — supports ALL lead fields."""
    _verify_internal_key(request)
    from database.models.lead_loan import Lead

    lead = db.query(Lead).filter(Lead.id == req.lead_id).first()
    if not lead:
        return {"error": f"Lead {req.lead_id} not found"}

    updated_fields = []

    if req.phone:
        lead.phone = req.phone
        updated_fields.append("phone")
    if req.email:
        lead.email = req.email
        updated_fields.append("email")
    if req.loan_purpose:
        lead.loan_purpose = req.loan_purpose
        updated_fields.append("loan_purpose")
    if req.property_type:
        lead.property_type = req.property_type
        updated_fields.append("property_type")
    if req.timeline:
        lead.timeline = req.timeline
        updated_fields.append("timeline")
    if req.notes:
        lead.notes = (lead.notes or "") + f"\n{req.notes}" if lead.notes else req.notes
        updated_fields.append("notes")
    if req.stage:
        lead.stage = req.stage
        updated_fields.append("stage")
    if req.credit_score is not None:
        lead.credit_score = req.credit_score
        updated_fields.append("credit_score")
    if req.loan_amount is not None:
        lead.loan_amount = req.loan_amount
        updated_fields.append("loan_amount")
    if req.loan_type:
        lead.loan_type = req.loan_type
        updated_fields.append("loan_type")
    if req.interest_rate is not None:
        lead.interest_rate = req.interest_rate
        updated_fields.append("interest_rate")
    if req.loan_term:
        lead.loan_term = req.loan_term
        updated_fields.append("loan_term")
    if req.address:
        lead.address = req.address
        updated_fields.append("address")
    if req.city:
        lead.city = req.city
        updated_fields.append("city")
    if req.state:
        lead.state = req.state
        updated_fields.append("state")
    if req.zip_code:
        lead.zip_code = req.zip_code
        updated_fields.append("zip_code")
    if req.source:
        lead.source = req.source
        updated_fields.append("source")
    if req.annual_income is not None:
        lead.annual_income = req.annual_income
        updated_fields.append("annual_income")
    if req.employment_status:
        lead.employment_status = req.employment_status
        updated_fields.append("employment_status")
    if req.employer_name:
        lead.employer_name = req.employer_name
        updated_fields.append("employer_name")
    if req.property_value is not None:
        lead.property_value = req.property_value
        updated_fields.append("property_value")
    if req.down_payment is not None:
        lead.down_payment = req.down_payment
        updated_fields.append("down_payment")
    if req.first_time_buyer is not None:
        lead.first_time_buyer = req.first_time_buyer
        updated_fields.append("first_time_buyer")
    if req.occupancy_type:
        lead.occupancy_type = req.occupancy_type
        updated_fields.append("occupancy_type")
    if req.monthly_debts is not None:
        lead.monthly_debts = req.monthly_debts
        updated_fields.append("monthly_debts")
    if req.preapproval_amount is not None:
        lead.preapproval_amount = req.preapproval_amount
        updated_fields.append("preapproval_amount")
    if req.loan_officer:
        lead.loan_officer = req.loan_officer
        updated_fields.append("loan_officer")
    if req.processor:
        lead.processor = req.processor
        updated_fields.append("processor")
    if req.next_action:
        lead.next_action = req.next_action
        updated_fields.append("next_action")
    if req.sentiment:
        lead.sentiment = req.sentiment
        updated_fields.append("sentiment")
    if req.first_name:
        lead.first_name = req.first_name
        lead.name = f"{req.first_name} {lead.last_name or ''}".strip()
        updated_fields.append("first_name")
    if req.last_name:
        lead.last_name = req.last_name
        lead.name = f"{lead.first_name or ''} {req.last_name}".strip()
        updated_fields.append("last_name")

    db.commit()

    return {
        "lead_id": lead.id,
        "name": lead.name,
        "updated": True,
        "fields_updated": updated_fields,
    }


@router.post("/find-referral-partners")
async def find_referral_partners_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """Find referral partners by category."""
    _verify_internal_key(request)
    body = await request.json()
    category = body.get("category", "realtor")
    org_id = body.get("organization_id")

    from database.models.referral import ReferralPartner
    q = db.query(ReferralPartner).filter(ReferralPartner.status == "active")
    if category and category.lower() != "all":
        q = q.filter(ReferralPartner.category == category.lower())
    if org_id:
        q = q.filter(ReferralPartner.organization_id == int(org_id))
    q = q.order_by(ReferralPartner.name).limit(200)
    partners = q.all()

    return {
        "partners": [
            {
                "id": p.id,
                "name": p.name,
                "contact_name": p.contact_name,
                "phone": p.phone or "",
                "email": p.email or "",
                "category": p.category or "",
                "company": p.company or "",
            }
            for p in partners
        ],
        "count": len(partners),
    }


class EmailReportRequest(BaseModel):
    user_id: int
    email: str
    organization_id: Optional[int] = None
    report_type: str = "daily"  # daily, pipeline, tasks


@router.post("/email-report")
async def email_daily_report(
    req: EmailReportRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Compile a pipeline + leads + tasks report and email it to the LO."""
    _verify_internal_key(request)

    from database.models.lead_loan import Lead, Loan
    from database.models.core import User
    from database.models.task import Task
    from sqlalchemy import func

    org_filter = []
    if req.organization_id:
        org_filter_lead = [Lead.organization_id == req.organization_id]
        org_filter_loan = [Loan.organization_id == req.organization_id]
    else:
        org_filter_lead = []
        org_filter_loan = []

    # ── Pipeline summary ──
    active_stages = [
        "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
        "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
        "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
        "CLOSING", "DOCS", "DOCS_OUT",
    ]
    pipeline_rows = (
        db.query(
            func.upper(Loan.stage).label("stage"),
            func.count(Loan.id).label("cnt"),
            func.coalesce(func.sum(Loan.loan_amount), 0).label("volume"),
        )
        .filter(
            func.upper(Loan.stage).in_(active_stages),
            Loan.loan_officer_id == req.user_id,
            *org_filter_loan,
        )
        .group_by(func.upper(Loan.stage))
        .all()
    )
    total_loans = sum(r.cnt for r in pipeline_rows)
    total_volume = sum(float(r.volume or 0) for r in pipeline_rows)

    # ── Leads by stage ──
    lead_rows = (
        db.query(
            func.coalesce(Lead.stage, "New").label("stage"),
            func.count(Lead.id).label("cnt"),
        )
        .filter(Lead.owner_id == req.user_id, *org_filter_lead)
        .group_by(func.coalesce(Lead.stage, "New"))
        .all()
    )
    total_leads = sum(r.cnt for r in lead_rows)

    # ── Tasks due today or overdue ──
    today = datetime.now(timezone.utc).date()
    tasks = (
        db.query(Task)
        .filter(
            Task.owner_id == req.user_id,
            Task.status.in_(["pending", "in_progress"]),
        )
        .order_by(Task.due_date.asc().nullslast(), Task.priority.desc())
        .limit(30)
        .all()
    )

    overdue = [t for t in tasks if t.due_date and t.due_date.date() < today]
    due_today = [t for t in tasks if t.due_date and t.due_date.date() == today]
    upcoming = [t for t in tasks if not t.due_date or t.due_date.date() > today]

    # ── Compose HTML email ──
    def fmt_currency(val):
        try:
            return f"${float(val):,.0f}"
        except (TypeError, ValueError):
            return "$0"

    def task_row(t, label=""):
        title = t.title or "Untitled"
        due = t.due_date.strftime("%b %d") if t.due_date else "No date"
        pri = (t.priority or "normal").capitalize()
        badge = f' <span style="color:#dc2626;font-weight:bold;">({label})</span>' if label else ""
        return f'<tr><td style="padding:6px 12px;">{title}{badge}</td><td style="padding:6px 12px;">{due}</td><td style="padding:6px 12px;">{pri}</td></tr>'

    pipeline_html = ""
    for r in sorted(pipeline_rows, key=lambda x: active_stages.index(x.stage) if x.stage in active_stages else 99):
        stage_display = r.stage.replace("_", " ").title()
        pipeline_html += f'<tr><td style="padding:6px 12px;">{stage_display}</td><td style="padding:6px 12px;text-align:center;">{r.cnt}</td><td style="padding:6px 12px;text-align:right;">{fmt_currency(r.volume)}</td></tr>'

    leads_html = ""
    for r in sorted(lead_rows, key=lambda x: x.cnt, reverse=True):
        leads_html += f'<tr><td style="padding:6px 12px;">{r.stage}</td><td style="padding:6px 12px;text-align:center;">{r.cnt}</td></tr>'

    tasks_html = ""
    for t in overdue:
        tasks_html += task_row(t, "OVERDUE")
    for t in due_today:
        tasks_html += task_row(t, "TODAY")
    for t in upcoming[:10]:
        tasks_html += task_row(t)

    user = db.query(User).filter(User.id == req.user_id).first()
    first_name = user.first_name if user else "there"

    subject = f"Your Daily Briefing — {datetime.now(timezone.utc).strftime('%b %d, %Y')}"
    body = f"""\
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:680px;margin:0 auto;color:#1a1a2e;">
<h2 style="color:#6366f1;">Good morning, {first_name}!</h2>
<p>Here's your daily pipeline, leads, and task briefing from Aria.</p>

<h3 style="border-bottom:2px solid #6366f1;padding-bottom:6px;">Active Pipeline — {total_loans} Loans ({fmt_currency(total_volume)})</h3>
<table style="width:100%;border-collapse:collapse;font-size:14px;">
<tr style="background:#f1f5f9;"><th style="padding:8px 12px;text-align:left;">Stage</th><th style="padding:8px 12px;text-align:center;">Count</th><th style="padding:8px 12px;text-align:right;">Volume</th></tr>
{pipeline_html}
</table>

<h3 style="border-bottom:2px solid #6366f1;padding-bottom:6px;margin-top:24px;">Leads — {total_leads} Total</h3>
<table style="width:100%;border-collapse:collapse;font-size:14px;">
<tr style="background:#f1f5f9;"><th style="padding:8px 12px;text-align:left;">Stage</th><th style="padding:8px 12px;text-align:center;">Count</th></tr>
{leads_html}
</table>

<h3 style="border-bottom:2px solid #6366f1;padding-bottom:6px;margin-top:24px;">Tasks — {len(overdue)} Overdue, {len(due_today)} Due Today</h3>
<table style="width:100%;border-collapse:collapse;font-size:14px;">
<tr style="background:#f1f5f9;"><th style="padding:8px 12px;text-align:left;">Task</th><th style="padding:8px 12px;">Due</th><th style="padding:8px 12px;">Priority</th></tr>
{tasks_html if tasks_html else '<tr><td colspan="3" style="padding:12px;text-align:center;color:#64748b;">No pending tasks — nice work!</td></tr>'}
</table>

<p style="margin-top:24px;font-size:13px;color:#64748b;">— Aria, your AI assistant at Perennia</p>
</div>"""

    # ── Send via tool registry (Microsoft Graph) ──
    try:
        from agents.tools import tool_registry
        send_tool = tool_registry.get("send_email")
        if send_tool:
            import inspect
            result = send_tool.func(
                to_email=req.email,
                subject=subject,
                body=body,
                user_id=req.user_id,
            )
            return {
                "sent": True,
                "to": req.email,
                "subject": subject,
                "summary": {
                    "total_loans": total_loans,
                    "total_volume": fmt_currency(total_volume),
                    "total_leads": total_leads,
                    "overdue_tasks": len(overdue),
                    "due_today_tasks": len(due_today),
                },
            }
        else:
            return {"error": "send_email tool not found in registry"}
    except Exception as e:
        logger.error("Email report send failed: %s", e)
        return {"error": f"Failed to send email: {e}"}


# ─── Loan Endpoints ────────────────────────────────────────────────────────

class LoanInfoRequest(BaseModel):
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    loan_number: Optional[str] = None
    organization_id: Optional[int] = None


class LoanUpdateRequest(BaseModel):
    loan_id: int
    stage: Optional[str] = None
    loan_type: Optional[str] = None
    program: Optional[str] = None
    amount: Optional[float] = None
    purchase_price: Optional[float] = None
    down_payment: Optional[float] = None
    rate: Optional[float] = None
    term: Optional[int] = None
    property_address: Optional[str] = None
    property_city: Optional[str] = None
    property_state: Optional[str] = None
    property_zip: Optional[str] = None
    property_type: Optional[str] = None
    occupancy_type: Optional[str] = None
    borrower_name: Optional[str] = None
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    coborrower_name: Optional[str] = None
    processor: Optional[str] = None
    underwriter: Optional[str] = None
    closer: Optional[str] = None
    realtor_agent: Optional[str] = None
    title_company: Optional[str] = None
    lender: Optional[str] = None
    loan_purpose: Optional[str] = None
    closing_date: Optional[str] = None
    lock_date: Optional[str] = None
    lock_expiration_date: Optional[str] = None
    rate_lock_status: Optional[str] = None
    notes: Optional[str] = None
    monthly_payment: Optional[float] = None
    property_tax: Optional[float] = None
    hazard_insurance: Optional[float] = None
    mortgage_insurance: Optional[float] = None
    hoa_amount: Optional[float] = None
    ltv: Optional[float] = None
    cltv: Optional[float] = None
    loan_number: Optional[str] = None


@router.post("/loan-info")
async def loan_info(
    req: LoanInfoRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Return comprehensive loan data — ALL fields for active loans and MUM."""
    _verify_internal_key(request)
    from database.models.lead_loan import Loan, Lead

    loan = None
    if req.loan_id:
        q = db.query(Loan).filter(Loan.id == req.loan_id)
        if req.organization_id:
            q = q.filter(Loan.organization_id == req.organization_id)
        loan = q.first()
    elif req.loan_number:
        q = db.query(Loan).filter(Loan.loan_number == req.loan_number)
        if req.organization_id:
            q = q.filter(Loan.organization_id == req.organization_id)
        loan = q.first()
    elif req.lead_id:
        q = db.query(Lead).filter(Lead.id == req.lead_id)
        if req.organization_id:
            q = q.filter(Lead.organization_id == req.organization_id)
        lead = q.first()
        if lead:
            loan = db.query(Loan).filter(Loan.lead_id == lead.id).order_by(Loan.created_at.desc()).first()

    if not loan:
        return {"error": "Loan not found"}

    def _num(val):
        return float(val) if val is not None else None

    def _dt(val):
        return val.isoformat() if val else None

    return {
        "id": loan.id,
        "loan_number": loan.loan_number,
        "organization_id": loan.organization_id,
        "stage": loan.stage,
        "program": loan.program,
        "loan_type": loan.loan_type,
        "loan_purpose": getattr(loan, "loan_purpose", None),
        # Borrower
        "borrower_name": loan.borrower_name,
        "borrower_email": loan.borrower_email,
        "borrower_phone": loan.borrower_phone,
        "preferred_communication": loan.preferred_communication,
        "coborrower_name": loan.coborrower_name,
        "co_borrower_email": loan.co_borrower_email,
        "co_borrower_phone": loan.co_borrower_phone,
        # Financials
        "amount": _num(loan.amount),
        "purchase_price": _num(loan.purchase_price),
        "down_payment": _num(loan.down_payment),
        "rate": _num(loan.rate),
        "term": loan.term,
        "monthly_payment": _num(getattr(loan, "monthly_payment", None)),
        "property_tax": _num(getattr(loan, "property_tax", None)),
        "hazard_insurance": _num(getattr(loan, "hazard_insurance", None)),
        "mortgage_insurance": _num(getattr(loan, "mortgage_insurance", None)),
        "hoa_amount": _num(getattr(loan, "hoa_amount", None)),
        "origination_fee": _num(getattr(loan, "origination_fee", None)),
        "points": _num(getattr(loan, "points", None)),
        "ltv": _num(getattr(loan, "ltv", None)),
        "cltv": _num(getattr(loan, "cltv", None)),
        "rate_type": getattr(loan, "rate_type", None),
        # Property
        "property_address": loan.property_address,
        "property_city": loan.property_city,
        "property_state": loan.property_state,
        "property_zip": loan.property_zip,
        "property_type": getattr(loan, "property_type", None),
        "occupancy_type": getattr(loan, "occupancy_type", None),
        "property_county": getattr(loan, "property_county", None),
        "property_units": getattr(loan, "property_units", None),
        # Team
        "loan_officer_id": loan.loan_officer_id,
        "loan_officer_name": loan.loan_officer_name,
        "loan_officer_email": loan.loan_officer_email,
        "processor": loan.processor,
        "processor_email": loan.processor_email,
        "underwriter": loan.underwriter,
        "underwriter_email": loan.underwriter_email,
        "closer": loan.closer,
        "closer_email": loan.closer_email,
        "production_assistant": loan.production_assistant,
        "realtor_agent": loan.realtor_agent,
        "title_company": loan.title_company,
        "lender": loan.lender,
        # Key dates
        "lock_date": _dt(loan.lock_date),
        "closing_date": _dt(loan.closing_date),
        "funded_date": _dt(loan.funded_date),
        "application_date": _dt(getattr(loan, "application_date", None)),
        "contract_received_date": _dt(getattr(loan, "contract_received_date", None)),
        "conditional_approval_date": _dt(getattr(loan, "conditional_approval_date", None)),
        "clear_to_close_date": _dt(getattr(loan, "clear_to_close_date", None)),
        "docs_ordered_date": _dt(getattr(loan, "docs_ordered_date", None)),
        "docs_out_date": _dt(getattr(loan, "docs_out_date", None)),
        "scheduled_closing_date": _dt(getattr(loan, "scheduled_closing_date", None)),
        "scheduled_funding_date": _dt(getattr(loan, "scheduled_funding_date", None)),
        # Rate Lock
        "lock_expiration_date": _dt(loan.lock_expiration_date),
        "rate_lock_status": loan.rate_lock_status.value if hasattr(loan.rate_lock_status, "value") else str(loan.rate_lock_status) if loan.rate_lock_status else None,
        "lock_term_days": loan.lock_term_days,
        "float_down_available": loan.float_down_available,
        "volatility_score": loan.volatility_score,
        # Appraisal
        "appraisal_ordered_date": _dt(loan.appraisal_ordered_date),
        "appraisal_scheduled_date": _dt(loan.appraisal_scheduled_date),
        "appraisal_completed_date": _dt(loan.appraisal_completed_date),
        "appraisal_value": _num(loan.appraisal_value),
        "appraisal_received_date": _dt(loan.appraisal_received_date),
        # Title & Insurance
        "title_ordered_date": _dt(loan.title_ordered_date),
        "title_received_date": _dt(loan.title_received_date),
        "insurance_ordered_date": _dt(loan.insurance_ordered_date),
        "insurance_received_date": _dt(loan.insurance_received_date),
        # SLA
        "days_in_stage": loan.days_in_stage,
        "sla_status": loan.sla_status,
        "predicted_close_date": _dt(loan.predicted_close_date),
        "risk_score": loan.risk_score,
        "stage_changed_at": _dt(loan.stage_changed_at),
        # AMR / MUM
        "mum_date": _dt(getattr(loan, "mum_date", None)),
        "last_amr_date": _dt(loan.last_amr_date),
        "next_amr_date": _dt(loan.next_amr_date),
        "refi_opportunity_score": loan.refi_opportunity_score,
        # Timestamps
        "created_at": _dt(loan.created_at),
        "updated_at": _dt(loan.updated_at),
    }


@router.post("/update-loan")
async def update_loan_endpoint(
    req: LoanUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update loan fields — supports all active loan and MUM fields."""
    _verify_internal_key(request)
    from database.models.lead_loan import Loan
    from datetime import datetime as dt_cls

    loan = db.query(Loan).filter(Loan.id == req.loan_id).first()
    if not loan:
        return {"error": f"Loan {req.loan_id} not found"}

    updated_fields = []

    if req.stage:
        loan.stage = req.stage
        updated_fields.append("stage")
    if req.loan_type:
        loan.loan_type = req.loan_type
        updated_fields.append("loan_type")
    if req.program:
        loan.program = req.program
        updated_fields.append("program")
    if req.amount is not None:
        loan.amount = req.amount
        updated_fields.append("amount")
    if req.purchase_price is not None:
        loan.purchase_price = req.purchase_price
        updated_fields.append("purchase_price")
    if req.down_payment is not None:
        loan.down_payment = req.down_payment
        updated_fields.append("down_payment")
    if req.rate is not None:
        loan.rate = req.rate
        updated_fields.append("rate")
    if req.term is not None:
        loan.term = req.term
        updated_fields.append("term")
    if req.property_address:
        loan.property_address = req.property_address
        updated_fields.append("property_address")
    if req.property_city:
        loan.property_city = req.property_city
        updated_fields.append("property_city")
    if req.property_state:
        loan.property_state = req.property_state
        updated_fields.append("property_state")
    if req.property_zip:
        loan.property_zip = req.property_zip
        updated_fields.append("property_zip")
    if req.property_type:
        loan.property_type = req.property_type
        updated_fields.append("property_type")
    if req.occupancy_type:
        loan.occupancy_type = req.occupancy_type
        updated_fields.append("occupancy_type")
    if req.borrower_name:
        loan.borrower_name = req.borrower_name
        updated_fields.append("borrower_name")
    if req.borrower_email:
        loan.borrower_email = req.borrower_email
        updated_fields.append("borrower_email")
    if req.borrower_phone:
        loan.borrower_phone = req.borrower_phone
        updated_fields.append("borrower_phone")
    if req.coborrower_name:
        loan.coborrower_name = req.coborrower_name
        updated_fields.append("coborrower_name")
    if req.processor:
        loan.processor = req.processor
        updated_fields.append("processor")
    if req.underwriter:
        loan.underwriter = req.underwriter
        updated_fields.append("underwriter")
    if req.closer:
        loan.closer = req.closer
        updated_fields.append("closer")
    if req.realtor_agent:
        loan.realtor_agent = req.realtor_agent
        updated_fields.append("realtor_agent")
    if req.title_company:
        loan.title_company = req.title_company
        updated_fields.append("title_company")
    if req.lender:
        loan.lender = req.lender
        updated_fields.append("lender")
    if req.loan_purpose:
        loan.loan_purpose = req.loan_purpose
        updated_fields.append("loan_purpose")
    if req.closing_date:
        try:
            loan.closing_date = dt_cls.fromisoformat(req.closing_date)
            updated_fields.append("closing_date")
        except ValueError:
            pass
    if req.lock_date:
        try:
            loan.lock_date = dt_cls.fromisoformat(req.lock_date)
            updated_fields.append("lock_date")
        except ValueError:
            pass
    if req.lock_expiration_date:
        try:
            loan.lock_expiration_date = dt_cls.fromisoformat(req.lock_expiration_date)
            updated_fields.append("lock_expiration_date")
        except ValueError:
            pass
    if req.rate_lock_status:
        loan.rate_lock_status = req.rate_lock_status
        updated_fields.append("rate_lock_status")
    if req.monthly_payment is not None:
        loan.monthly_payment = req.monthly_payment
        updated_fields.append("monthly_payment")
    if req.property_tax is not None:
        loan.property_tax = req.property_tax
        updated_fields.append("property_tax")
    if req.hazard_insurance is not None:
        loan.hazard_insurance = req.hazard_insurance
        updated_fields.append("hazard_insurance")
    if req.mortgage_insurance is not None:
        loan.mortgage_insurance = req.mortgage_insurance
        updated_fields.append("mortgage_insurance")
    if req.hoa_amount is not None:
        loan.hoa_amount = req.hoa_amount
        updated_fields.append("hoa_amount")
    if req.ltv is not None:
        loan.ltv = req.ltv
        updated_fields.append("ltv")
    if req.cltv is not None:
        loan.cltv = req.cltv
        updated_fields.append("cltv")
    if req.loan_number:
        loan.loan_number = req.loan_number
        updated_fields.append("loan_number")
    if req.notes:
        loan.ai_insights = (loan.ai_insights or "") + f"\n{req.notes}" if loan.ai_insights else req.notes
        updated_fields.append("notes")

    if not updated_fields:
        return {"error": "No fields to update"}

    db.commit()

    return {
        "loan_id": loan.id,
        "loan_number": loan.loan_number,
        "borrower_name": loan.borrower_name,
        "updated": True,
        "fields_updated": updated_fields,
    }
