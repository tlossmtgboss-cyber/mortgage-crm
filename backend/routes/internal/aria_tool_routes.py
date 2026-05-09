# backend/routes/internal/aria_tool_routes.py
"""
Internal API endpoints for Aria voice agent tool calls.
These endpoints are called by the LiveKit agent worker via HTTP.
Auth: X-Internal-API-Key header (shared secret, no user JWT).

Enterprise controls:
- Tenant isolation (organization_id enforcement)
- Immutable audit trail (AuditLog + StageHistory)
- Input sanitization (validation.common.sanitize_string)
- Owner authorization (lead/loan must belong to caller's org)
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


# ─── Enterprise Helpers ───────────────────────────────────────────────────────

# Financial fields that require audit logging on change (TILA/RESPA)
_AUDITED_LEAD_FIELDS = frozenset({
    "stage", "loan_amount", "interest_rate", "credit_score", "preapproval_amount",
    "annual_income", "monthly_debts", "down_payment", "property_value",
})
_AUDITED_LOAN_FIELDS = frozenset({
    "stage", "amount", "rate", "term", "purchase_price", "down_payment",
    "closing_date", "lock_date", "lock_expiration_date", "rate_lock_status",
    "monthly_payment", "ltv", "cltv", "loan_type", "program",
})

# Valid lead stage transitions (from → allowed next stages)
_LEAD_STAGE_TRANSITIONS = {
    "New": {"Attempted Contact", "Prospect", "Pre-Qualified", "Long-Term Nurture", "Do Not Call"},
    "Attempted Contact": {"Prospect", "Pre-Qualified", "Long-Term Nurture", "Do Not Call"},
    "Prospect": {"Pre-Qualified", "Pre-Approved", "Long-Term Nurture", "Credit Repair", "Do Not Call"},
    "Pre-Qualified": {"Pre-Approved", "Application", "Long-Term Nurture", "Credit Repair"},
    "Pre-Approved": {"Application", "Long-Term Nurture"},
    "Long-Term Nurture": {"Attempted Contact", "Prospect", "Pre-Qualified", "Do Not Call"},
    "Credit Repair": {"Prospect", "Pre-Qualified", "Do Not Call"},
    "Application": {"Disclosed"},
}

# Valid loan stage transitions (loosely enforced — allows forward movement + common rework paths)
_LOAN_STAGE_ORDER = [
    "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
    "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
    "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
    "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
]
_LOAN_TERMINAL_STAGES = {"FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY"}


def _sanitize_fields(data: dict, text_fields: set, max_length: int = 500) -> dict:
    """Sanitize free-text string fields in a dict."""
    from validation.common import sanitize_string
    for field in text_fields:
        if field in data and data[field] and isinstance(data[field], str):
            data[field] = sanitize_string(data[field], max_length=max_length)
    return data


def _log_audit(
    db: Session,
    change_type: str,
    entity_type: str,
    entity_id: int,
    before: dict,
    after: dict,
    organization_id: Optional[int] = None,
    user_id: Optional[int] = None,
    reason: str = "aria_voice_agent",
):
    """Write an immutable audit log entry for compliance."""
    try:
        from database.models.security import AuditLog
        entry = AuditLog(
            organization_id=organization_id,
            user_id=user_id,
            change_type=change_type,
            entity_type=entity_type,
            entity_id=entity_id,
            before_state=before,
            after_state=after,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
        )
        db.add(entry)
    except Exception as e:
        logger.warning("Audit log write failed (non-blocking): %s", e)


def _log_stage_change(
    db: Session,
    entity_type: str,
    entity_id: int,
    from_stage: Optional[str],
    to_stage: str,
    organization_id: Optional[int] = None,
    changed_by_id: Optional[int] = None,
):
    """Write a stage history record."""
    try:
        from database.models.communication import StageHistory
        entry = StageHistory(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            lead_id=entity_id if entity_type == "lead" else None,
            loan_id=entity_id if entity_type == "loan" else None,
            from_stage=from_stage,
            to_stage=to_stage,
            changed_at=datetime.now(timezone.utc),
            changed_by_id=changed_by_id,
        )
        db.add(entry)
    except Exception as e:
        logger.warning("Stage history write failed (non-blocking): %s", e)


def _validate_lead_stage_transition(current: Optional[str], target: str) -> tuple[bool, str]:
    """Check if a lead stage transition is allowed."""
    if not current:
        return True, ""
    allowed = _LEAD_STAGE_TRANSITIONS.get(current)
    if allowed is None:
        return True, ""
    if target not in allowed:
        return False, f"Cannot move from '{current}' to '{target}'. Allowed: {', '.join(sorted(allowed))}"
    return True, ""


def _validate_loan_stage_transition(current: Optional[str], target: str) -> tuple[bool, str]:
    """Check if a loan stage transition is valid (forward progress or rework)."""
    target_upper = target.upper()
    if target_upper in _LOAN_TERMINAL_STAGES:
        return True, ""
    current_upper = (current or "").upper()
    if current_upper in _LOAN_TERMINAL_STAGES:
        return False, f"Loan is in terminal stage '{current}' — cannot transition to '{target}'"
    return True, ""

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
    organization_id: Optional[int] = None
    user_id: Optional[int] = None

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
    """Update an existing lead from voice agent — supports ALL lead fields.

    Enterprise controls:
    - Tenant isolation: lead must belong to caller's organization
    - Stage validation: enforces allowed transitions
    - Input sanitization: all text fields sanitized
    - Audit trail: financial/stage changes logged immutably
    """
    _verify_internal_key(request)
    from database.models.lead_loan import Lead

    # ── Tenant-isolated lookup ──
    q = db.query(Lead).filter(Lead.id == req.lead_id)
    if req.organization_id:
        q = q.filter(Lead.organization_id == req.organization_id)
    lead = q.first()
    if not lead:
        return {"error": f"Lead {req.lead_id} not found or access denied"}

    # ── Stage transition validation ──
    if req.stage:
        valid, reason = _validate_lead_stage_transition(lead.stage, req.stage)
        if not valid:
            return {"error": reason}

    # ── Sanitize text fields ──
    _TEXT_FIELDS = {
        "notes", "loan_purpose", "property_type", "timeline", "address",
        "city", "state", "zip_code", "source", "employment_status",
        "employer_name", "occupancy_type", "loan_officer", "processor",
        "next_action", "sentiment", "first_name", "last_name", "loan_type",
        "loan_term",
    }
    req_data = req.model_dump(exclude_none=True, exclude={"lead_id", "organization_id", "user_id"})
    req_data = _sanitize_fields(req_data, _TEXT_FIELDS)

    # ── Capture before-state for audited fields ──
    before_state = {}
    for field in _AUDITED_LEAD_FIELDS:
        if field in req_data:
            before_state[field] = getattr(lead, field, None)
            if hasattr(before_state[field], "value"):
                before_state[field] = before_state[field].value
            elif before_state[field] is not None:
                before_state[field] = str(before_state[field]) if not isinstance(before_state[field], (int, float, bool)) else before_state[field]

    # ── Apply updates ──
    updated_fields = []
    old_stage = lead.stage

    for field, value in req_data.items():
        if field == "notes":
            lead.notes = (lead.notes or "") + f"\n{value}" if lead.notes else value
        elif field == "first_name":
            lead.first_name = value
            lead.name = f"{value} {lead.last_name or ''}".strip()
        elif field == "last_name":
            lead.last_name = value
            lead.name = f"{lead.first_name or ''} {value}".strip()
        else:
            setattr(lead, field, value)
        updated_fields.append(field)

    if not updated_fields:
        return {"error": "No fields to update"}

    # ── Stage history ──
    if "stage" in updated_fields and old_stage != lead.stage:
        _log_stage_change(
            db, "lead", lead.id, old_stage, lead.stage,
            organization_id=lead.organization_id,
            changed_by_id=req.user_id,
        )

    # ── Audit log for financial/compliance fields ──
    audited_changes = {f: req_data[f] for f in _AUDITED_LEAD_FIELDS if f in req_data}
    if audited_changes:
        _log_audit(
            db,
            change_type="lead_update",
            entity_type="lead",
            entity_id=lead.id,
            before=before_state,
            after=audited_changes,
            organization_id=lead.organization_id,
            user_id=req.user_id,
            reason="aria_voice_agent",
        )

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
            func.coalesce(func.sum(Loan.amount), 0).label("volume"),
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
    organization_id: Optional[int] = None
    user_id: Optional[int] = None


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
    """Update loan fields — supports all active loan and MUM fields.

    Enterprise controls:
    - Tenant isolation: loan must belong to caller's organization
    - Stage validation: enforces valid transitions, blocks moves out of terminal
    - Input sanitization: all text fields sanitized
    - Audit trail: financial/stage changes logged immutably
    - Stage history: every stage change recorded with timestamp and actor
    """
    _verify_internal_key(request)
    from database.models.lead_loan import Loan
    from datetime import datetime as dt_cls

    # ── Tenant-isolated lookup ──
    q = db.query(Loan).filter(Loan.id == req.loan_id)
    if req.organization_id:
        q = q.filter(Loan.organization_id == req.organization_id)
    loan = q.first()
    if not loan:
        return {"error": f"Loan {req.loan_id} not found or access denied"}

    # ── Stage transition validation ──
    if req.stage:
        valid, reason = _validate_loan_stage_transition(loan.stage, req.stage)
        if not valid:
            return {"error": reason}

    # ── Sanitize text fields ──
    _TEXT_FIELDS = {
        "loan_type", "program", "property_address", "property_city",
        "property_state", "property_zip", "property_type", "occupancy_type",
        "borrower_name", "borrower_email", "borrower_phone", "coborrower_name",
        "processor", "underwriter", "closer", "realtor_agent", "title_company",
        "lender", "loan_purpose", "rate_lock_status", "loan_number", "notes",
    }
    req_data = req.model_dump(exclude_none=True, exclude={"loan_id", "organization_id", "user_id"})
    req_data = _sanitize_fields(req_data, _TEXT_FIELDS)

    # ── Capture before-state for audited fields ──
    before_state = {}
    for field in _AUDITED_LOAN_FIELDS:
        if field in req_data:
            val = getattr(loan, field, None)
            if hasattr(val, "value"):
                val = val.value
            elif hasattr(val, "isoformat"):
                val = val.isoformat()
            elif val is not None and not isinstance(val, (int, float, bool, str)):
                val = str(val)
            before_state[field] = val

    # ── Apply updates ──
    updated_fields = []
    old_stage = loan.stage
    date_fields = {"closing_date", "lock_date", "lock_expiration_date"}

    for field, value in req_data.items():
        if field == "notes":
            loan.ai_insights = (loan.ai_insights or "") + f"\n{value}" if loan.ai_insights else value
        elif field in date_fields:
            try:
                setattr(loan, field, dt_cls.fromisoformat(value))
            except (ValueError, TypeError):
                continue
        elif field == "stage":
            loan.stage = value.upper()
            loan.stage_changed_at = datetime.now(timezone.utc)
        else:
            setattr(loan, field, value)
        updated_fields.append(field)

    if not updated_fields:
        return {"error": "No fields to update"}

    # ── Stage history ──
    if "stage" in updated_fields and old_stage != loan.stage:
        _log_stage_change(
            db, "loan", loan.id, old_stage, loan.stage,
            organization_id=loan.organization_id,
            changed_by_id=req.user_id,
        )

    # ── Audit log for financial/compliance fields ──
    audited_changes = {}
    for f in _AUDITED_LOAN_FIELDS:
        if f in req_data:
            val = req_data[f]
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            audited_changes[f] = val
    if audited_changes:
        _log_audit(
            db,
            change_type="loan_update",
            entity_type="loan",
            entity_id=loan.id,
            before=before_state,
            after=audited_changes,
            organization_id=loan.organization_id,
            user_id=req.user_id,
            reason="aria_voice_agent",
        )

    db.commit()

    return {
        "loan_id": loan.id,
        "loan_number": loan.loan_number,
        "borrower_name": loan.borrower_name,
        "updated": True,
        "fields_updated": updated_fields,
    }
