"""
Partner Portal Service

Business logic for the Realtor/Partner Portal:
- Partner authentication (magic-link sessions, separate from LO auth)
- Loan status sanitization (partners see milestones, not financials)
- Lead referral creation
- Pre-approval letter request management
- Co-marketing template retrieval
"""

import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_TOKEN_BYTES = 48  # 64-char hex token
SESSION_EXPIRY_HOURS = 24
MAGIC_LINK_EXPIRY_HOURS = 72

# Loan stage ordering for timeline display (milestone progression).
# Partners see friendly labels, not internal codes.
LOAN_STAGE_TIMELINE = [
    ("APPLICATION", "Application Received"),
    ("DISCLOSED", "Loan Disclosed"),
    ("PROCESSING", "In Processing"),
    ("SUBMITTED", "Submitted to Underwriting"),
    ("UNDERWRITING", "Under Review"),
    ("CONDITIONAL_APPROVAL", "Conditionally Approved"),
    ("APPROVED", "Approved"),
    ("CLEAR_TO_CLOSE", "Clear to Close"),
    ("CLOSING", "Closing Scheduled"),
    ("DOCS", "Docs Prepared"),
    ("DOCS_OUT", "Docs Sent"),
    ("FUNDED", "Funded"),
]

# Stages that are terminal / off the happy path
_TERMINAL_STAGES = frozenset({
    "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY", "NURTURE",
})

# Stage -> friendly label lookup
_STAGE_LABELS: Dict[str, str] = {code: label for code, label in LOAN_STAGE_TIMELINE}
_STAGE_LABELS.update({
    "CTC": "Clear to Close",
    "UW_RECEIVED": "Under Review",
    "SUSPENDED": "Suspended",
    "CANCELLED": "Cancelled",
    "DENIED": "Denied",
    "DEAD": "Inactive",
    "WITHDRAWN": "Withdrawn",
    "DOES_NOT_QUALIFY": "Does Not Qualify",
    "NURTURE": "Long-Term Nurture",
})


def _stage_label(stage: str) -> str:
    """Return a partner-friendly label for a loan stage."""
    return _STAGE_LABELS.get(stage, stage.replace("_", " ").title())


def _stage_index(stage: str) -> int:
    """Return the ordinal position of a stage in the timeline (-1 if not found)."""
    for i, (code, _) in enumerate(LOAN_STAGE_TIMELINE):
        if code == stage:
            return i
    return -1


# ============================================================================
# AUTHENTICATION
# ============================================================================

def create_partner_session(
    db: Session,
    partner_id: int,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new session token for an authenticated partner.
    Returns dict with token, partner info, and expiry.
    """
    from database.models.partner import PartnerSession
    from database.models.referral import ReferralPartner

    partner = db.query(ReferralPartner).filter(ReferralPartner.id == partner_id).first()
    if not partner:
        raise ValueError(f"Partner {partner_id} not found")

    token = secrets.token_hex(SESSION_TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_EXPIRY_HOURS)

    session = PartnerSession(
        partner_id=partner_id,
        token=token,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "session_token": token,
        "partner_id": partner.id,
        "name": partner.name,
        "email": partner.email or "",
        "expires_at": expires_at,
    }


def validate_partner_session(db: Session, token: str):
    """
    Validate a partner session token.
    Returns the ReferralPartner row or None.
    """
    from database.models.partner import PartnerSession
    from database.models.referral import ReferralPartner

    session = (
        db.query(PartnerSession)
        .filter(
            PartnerSession.token == token,
            PartnerSession.revoked.is_(False),
            PartnerSession.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )
    if not session:
        return None

    partner = db.query(ReferralPartner).filter(ReferralPartner.id == session.partner_id).first()
    return partner


def revoke_partner_session(db: Session, token: str) -> bool:
    """Revoke a session token (logout)."""
    from database.models.partner import PartnerSession

    session = db.query(PartnerSession).filter(PartnerSession.token == token).first()
    if session:
        session.revoked = True
        db.commit()
        return True
    return False


def find_partner_by_email(db: Session, email: str):
    """Look up a ReferralPartner by email."""
    from database.models.referral import ReferralPartner

    return (
        db.query(ReferralPartner)
        .filter(
            func.lower(ReferralPartner.email) == email.lower(),
            ReferralPartner.status == "active",
        )
        .first()
    )


# ============================================================================
# LOAN STATUS (sanitized for partners)
# ============================================================================

def get_partner_loans(db: Session, partner_id: int) -> List[Dict[str, Any]]:
    """
    Return all loans tied to leads referred by this partner.
    Financial details are stripped — only stage, dates, and property info.
    """
    from database.models.lead_loan import Lead, Loan

    # Leads referred by this partner that have a loan_number linking to a loan
    leads = (
        db.query(Lead)
        .filter(Lead.referral_partner_id == partner_id)
        .all()
    )

    results = []
    for lead in leads:
        # Find associated loans by loan_number or via organization + borrower match
        loans = []
        if lead.loan_number:
            loan = db.query(Loan).filter(Loan.loan_number == lead.loan_number).first()
            if loan:
                loans.append(loan)

        # Also check for loans matched by borrower email within same org
        if lead.email:
            email_loans = (
                db.query(Loan)
                .filter(
                    Loan.organization_id == lead.organization_id,
                    Loan.borrower_email == lead.email,
                )
                .all()
            )
            existing_ids = {l.id for l in loans}
            for el in email_loans:
                if el.id not in existing_ids:
                    loans.append(el)

        for loan in loans:
            results.append(_sanitize_loan(loan))

    return results


def get_loan_timeline(db: Session, loan_id: int, partner_id: int) -> Optional[Dict[str, Any]]:
    """
    Build a milestone timeline for a specific loan.
    Only returns data if the loan is linked to the requesting partner.
    """
    from database.models.lead_loan import Lead, Loan

    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        return None

    # Verify partner access: the loan must be tied to a lead referred by this partner
    linked = (
        db.query(Lead)
        .filter(
            Lead.referral_partner_id == partner_id,
            Lead.organization_id == loan.organization_id,
        )
        .first()
    )
    if not linked:
        return None

    current_idx = _stage_index(loan.stage or "")
    milestones = []
    for i, (code, label) in enumerate(LOAN_STAGE_TIMELINE):
        reached = i <= current_idx if current_idx >= 0 else False
        milestones.append({
            "stage": code,
            "label": label,
            "reached": reached,
            "reached_at": None,  # Could be enriched from StageHistory
        })

    return {
        "loan_id": loan.id,
        "borrower_name": loan.borrower_name,
        "current_stage": loan.stage or "",
        "current_stage_label": _stage_label(loan.stage or ""),
        "milestones": milestones,
    }


def _sanitize_loan(loan) -> Dict[str, Any]:
    """
    Strip financial details from a loan, returning only partner-safe fields.
    Partners see: stage, dates, property location, borrower name, SLA status.
    They do NOT see: rates, fees, credit scores, DTI, income, LTV.
    """
    return {
        "loan_id": loan.id,
        "borrower_name": loan.borrower_name,
        "property_address": None,  # Encrypted column — omit for safety
        "stage": loan.stage or "",
        "stage_label": _stage_label(loan.stage or ""),
        "loan_type": loan.loan_type,
        "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
        "created_at": loan.created_at.isoformat() if loan.created_at else None,
        "days_in_stage": loan.days_in_stage or 0,
        "sla_status": loan.sla_status,
    }


# ============================================================================
# LEAD REFERRAL
# ============================================================================

def create_referred_lead(
    db: Session,
    partner_id: int,
    first_name: str,
    last_name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    notes: Optional[str] = None,
    property_address: Optional[str] = None,
    loan_type: Optional[str] = None,
    estimated_purchase_price: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new Lead record from a partner referral.
    Links the lead to the referring partner and their associated LO.
    """
    from database.models.lead_loan import Lead
    from database.models.referral import ReferralPartner

    partner = db.query(ReferralPartner).filter(ReferralPartner.id == partner_id).first()
    if not partner:
        raise ValueError(f"Partner {partner_id} not found")

    if not email and not phone:
        raise ValueError("At least one of email or phone is required")

    name = f"{first_name} {last_name}".strip()

    lead = Lead(
        name=name,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        source="Partner Referral",
        referral_partner_id=partner_id,
        owner_id=partner.owner_id,  # Assign to the LO who owns this partner relationship
        organization_id=partner.organization_id,
        stage="New",
        notes=f"Referred by {partner.name}" + (f"\n{notes}" if notes else ""),
        loan_type=loan_type,
        property_address=property_address,
    )
    db.add(lead)

    # Increment partner referral count
    partner.referrals_in = (partner.referrals_in or 0) + 1
    partner.last_interaction = datetime.now(timezone.utc)

    db.commit()
    db.refresh(lead)

    logger.info(
        "Partner %s referred lead %s (id=%d) to org %s",
        partner.name, name, lead.id, partner.organization_id,
    )

    return {
        "lead_id": lead.id,
        "message": "Lead referred successfully",
        "borrower_name": name,
    }


# ============================================================================
# PRE-APPROVAL LETTER REQUESTS
# ============================================================================

def create_prequal_letter_request(
    db: Session,
    partner_id: int,
    buyer_name: str,
    buyer_email: Optional[str] = None,
    property_address: Optional[str] = None,
    requested_amount: Optional[str] = None,
    loan_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a pre-approval letter request on behalf of the partner."""
    from database.models.partner import PreApprovalLetterRequest
    from database.models.referral import ReferralPartner

    partner = db.query(ReferralPartner).filter(ReferralPartner.id == partner_id).first()
    if not partner:
        raise ValueError(f"Partner {partner_id} not found")

    req = PreApprovalLetterRequest(
        partner_id=partner_id,
        organization_id=partner.organization_id,
        buyer_name=buyer_name,
        buyer_email=buyer_email,
        property_address=property_address,
        requested_amount=requested_amount,
        loan_id=loan_id,
        lead_id=lead_id,
        notes=notes,
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    logger.info("Pre-approval letter request %d created by partner %d", req.id, partner_id)

    return {
        "id": req.id,
        "buyer_name": req.buyer_name,
        "status": req.status,
        "letter_url": req.letter_url,
        "property_address": req.property_address,
        "created_at": req.created_at,
        "updated_at": req.updated_at,
    }


def get_prequal_letter_requests(db: Session, partner_id: int) -> List[Dict[str, Any]]:
    """List all pre-approval letter requests for this partner."""
    from database.models.partner import PreApprovalLetterRequest

    requests = (
        db.query(PreApprovalLetterRequest)
        .filter(PreApprovalLetterRequest.partner_id == partner_id)
        .order_by(PreApprovalLetterRequest.created_at.desc())
        .all()
    )

    return [
        {
            "id": r.id,
            "buyer_name": r.buyer_name,
            "status": r.status,
            "letter_url": r.letter_url,
            "property_address": r.property_address,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in requests
    ]


# ============================================================================
# CO-MARKETING TEMPLATES
# ============================================================================

def get_marketing_templates(db: Session, partner_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve co-marketing templates available to the partner.
    Uses the ContentLibraryItem model if available; falls back to empty list.
    """
    try:
        from database.models.content_library import ContentLibraryItem
        from database.models.referral import ReferralPartner

        partner = db.query(ReferralPartner).filter(ReferralPartner.id == partner_id).first()
        if not partner:
            return []

        items = (
            db.query(ContentLibraryItem)
            .filter(
                ContentLibraryItem.organization_id == partner.organization_id,
                ContentLibraryItem.is_active.is_(True),
            )
            .order_by(ContentLibraryItem.created_at.desc())
            .limit(50)
            .all()
        )

        return [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "category": item.category.value if item.category else None,
                "thumbnail_url": item.thumbnail_url if hasattr(item, "thumbnail_url") else None,
                "template_type": item.content_type.value if item.content_type else None,
            }
            for item in items
        ]
    except Exception as e:
        logger.warning("Could not fetch marketing templates: %s", e)
        return []
