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
        from agents.tools.base import ToolRegistry
        registry = ToolRegistry()
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
