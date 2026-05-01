"""
Partner Portal Routes
=====================
Realtor/Partner Portal API — a dedicated interface where real estate agents
can track their referred borrowers' loan progress.

Partners authenticate via magic link (separate from LO auth).
All loan data is sanitized: partners see milestones, not financials.

Endpoints:
- POST /api/v1/partner/auth/login     — Partner login (email + magic-link token)
- POST /api/v1/partner/auth/logout    — Revoke session
- GET  /api/v1/partner/loans          — List loans for referred borrowers
- GET  /api/v1/partner/loans/{id}/status — Loan milestone timeline
- POST /api/v1/partner/leads/refer    — Refer a new buyer to the LO
- POST /api/v1/partner/prequal-letter/request — Request a pre-approval letter
- GET  /api/v1/partner/prequal-letters       — List pre-approval letter requests
- GET  /api/v1/partner/marketing/templates   — Get co-marketing templates
- GET  /api/v1/partner/profile        — Partner profile
- PUT  /api/v1/partner/profile        — Update partner profile
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from db import get_db
from schemas.partner_schemas import (
    PartnerLoginRequest,
    PartnerLoginResponse,
    MagicLinkSentResponse,
    PartnerProfileResponse,
    PartnerProfileUpdate,
    PartnerLoanSummary,
    LoanTimelineResponse,
    ReferLeadRequest,
    ReferLeadResponse,
    PreApprovalLetterRequestCreate,
    PreApprovalLetterResponse,
    MarketingTemplateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/partner", tags=["Partner Portal"])


# =============================================================================
# PARTNER AUTH DEPENDENCY
# =============================================================================

def get_current_partner(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Extract and validate the partner session from the Authorization header.
    Partners use Bearer tokens that map to PartnerSession rows.
    """
    from services.partner_portal_service import validate_partner_session

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header[7:]
    partner = validate_partner_session(db, token)
    if not partner:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return partner


# =============================================================================
# AUTH ENDPOINTS
# =============================================================================

@router.post("/auth/login", response_model=None)
async def partner_login(
    body: PartnerLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Partner login flow:
    1. If `token` is provided, validate the magic link and create a session.
    2. If only `email` is provided, send a magic link to the partner's email.
    """
    from services.partner_portal_service import (
        find_partner_by_email,
        create_partner_session,
    )

    partner = find_partner_by_email(db, body.email)
    if not partner:
        # Don't reveal whether the email exists
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if body.token:
        # Validate magic link token (placeholder — real implementation would
        # check a PartnerMagicLink table or signed JWT)
        # For now, create a session directly after partner is found
        ip = request.client.host if request.client else None
        ua = request.headers.get("User-Agent")
        session_data = create_partner_session(db, partner.id, ip_address=ip, user_agent=ua)
        return PartnerLoginResponse(**session_data)
    else:
        # TODO: Generate magic link and send via email
        logger.info("Magic link requested for partner %s (%s)", partner.name, body.email)
        return MagicLinkSentResponse(email=body.email)


@router.post("/auth/logout", status_code=204)
async def partner_logout(
    request: Request,
    db: Session = Depends(get_db),
):
    """Revoke the current partner session."""
    from services.partner_portal_service import revoke_partner_session

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        revoke_partner_session(db, token)
    return None


# =============================================================================
# LOAN STATUS
# =============================================================================

@router.get("/loans")
async def list_partner_loans(
    partner=Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """
    List all loans tied to borrowers referred by this partner.
    Financial details are stripped — only stage, dates, and property info.
    """
    from services.partner_portal_service import get_partner_loans

    loans = get_partner_loans(db, partner.id)
    return {"loans": loans, "count": len(loans)}


@router.get("/loans/{loan_id}/status")
async def get_loan_status(
    loan_id: int,
    partner=Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """
    Get the milestone timeline for a specific loan.
    Only accessible if the loan is linked to a lead referred by this partner.
    """
    from services.partner_portal_service import get_loan_timeline

    timeline = get_loan_timeline(db, loan_id, partner.id)
    if not timeline:
        raise HTTPException(status_code=404, detail="Loan not found or not accessible")
    return timeline


# =============================================================================
# LEAD REFERRAL
# =============================================================================

@router.post("/leads/refer", response_model=ReferLeadResponse, status_code=201)
async def refer_lead(
    body: ReferLeadRequest,
    partner=Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """
    Refer a new buyer/lead to the partner's associated loan officer.
    Creates a Lead record in the CRM linked to this referral partner.
    """
    from services.partner_portal_service import create_referred_lead

    try:
        result = create_referred_lead(
            db=db,
            partner_id=partner.id,
            first_name=body.first_name,
            last_name=body.last_name,
            email=body.email,
            phone=body.phone,
            notes=body.notes,
            property_address=body.property_address,
            loan_type=body.loan_type,
            estimated_purchase_price=body.estimated_purchase_price,
        )
        return ReferLeadResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# PRE-APPROVAL LETTERS
# =============================================================================

@router.post("/prequal-letter/request", response_model=PreApprovalLetterResponse, status_code=201)
async def request_prequal_letter(
    body: PreApprovalLetterRequestCreate,
    partner=Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """Request a pre-approval letter for a buyer."""
    from services.partner_portal_service import create_prequal_letter_request

    try:
        result = create_prequal_letter_request(
            db=db,
            partner_id=partner.id,
            buyer_name=body.buyer_name,
            buyer_email=body.buyer_email,
            property_address=body.property_address,
            requested_amount=body.requested_amount,
            loan_id=body.loan_id,
            lead_id=body.lead_id,
            notes=body.notes,
        )
        return PreApprovalLetterResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/prequal-letters")
async def list_prequal_letters(
    partner=Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """List all pre-approval letter requests submitted by this partner."""
    from services.partner_portal_service import get_prequal_letter_requests

    letters = get_prequal_letter_requests(db, partner.id)
    return {"letters": letters, "count": len(letters)}


# =============================================================================
# CO-MARKETING
# =============================================================================

@router.get("/marketing/templates")
async def list_marketing_templates(
    partner=Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """Get co-marketing templates available to this partner."""
    from services.partner_portal_service import get_marketing_templates

    templates = get_marketing_templates(db, partner.id)
    return {"templates": templates, "count": len(templates)}


# =============================================================================
# PARTNER PROFILE
# =============================================================================

@router.get("/profile", response_model=PartnerProfileResponse)
async def get_partner_profile(
    partner=Depends(get_current_partner),
):
    """Get the current partner's profile."""
    return PartnerProfileResponse.model_validate(partner)


@router.put("/profile", response_model=PartnerProfileResponse)
async def update_partner_profile(
    body: PartnerProfileUpdate,
    partner=Depends(get_current_partner),
    db: Session = Depends(get_db),
):
    """Update the current partner's profile fields."""
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    for field, value in update_data.items():
        if hasattr(partner, field):
            setattr(partner, field, value)

    db.commit()
    db.refresh(partner)
    return PartnerProfileResponse.model_validate(partner)
