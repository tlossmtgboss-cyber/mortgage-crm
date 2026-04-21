# backend/routes/internal/aria_tool_routes.py
"""
Internal API endpoints for Aria voice agent tool calls.
These endpoints are called by the LiveKit agent worker via HTTP.
Auth: X-Internal-API-Key header (shared secret, no user JWT).
"""
import os
import json
import logging
from typing import Any, Dict, Optional

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
    _verify_internal_key(request)
    from database.models.lead_loan import Lead
    q = db.query(Lead).filter(Lead.id == req.lead_id)
    if req.organization_id:
        q = q.filter(Lead.organization_id == req.organization_id)
    lead = q.first()
    if not lead:
        return {"error": f"Lead {req.lead_id} not found"}
    return {
        "first_name": getattr(lead, "first_name", None) or lead.name,
        "last_name": getattr(lead, "last_name", ""),
        "phone": lead.phone,
        "email": lead.email,
        "stage": lead.stage,
        "owner_id": lead.owner_id,
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
    """Update an existing lead from voice agent."""
    _verify_internal_key(request)
    from database.models.lead_loan import Lead

    lead = db.query(Lead).filter(Lead.id == req.lead_id).first()
    if not lead:
        return {"error": f"Lead {req.lead_id} not found"}

    if req.phone:
        lead.phone = req.phone
    if req.email:
        lead.email = req.email
    if req.loan_purpose:
        lead.loan_purpose = req.loan_purpose
    if req.property_type:
        lead.property_type = req.property_type
    if req.timeline:
        lead.timeline = req.timeline
    if req.notes:
        lead.notes = (lead.notes or "") + f"\n{req.notes}" if lead.notes else req.notes
    db.commit()

    return {
        "lead_id": lead.id,
        "name": lead.name,
        "updated": True,
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
