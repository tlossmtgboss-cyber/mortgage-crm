"""
POS Resolve Loan Officer Route
===============================
Lightweight endpoint for the URLA voice agent to look up a caller's assigned
loan officer by phone number.

    GET /api/v1/pos/resolve-lo?phone=+18435551212

The voice agent calls this before greeting the caller so the URLA application
gets attributed to the correct LO. Falls through gracefully — a 200 with
``found: false`` is returned when no match exists, so the caller can use env
defaults.

Auth: CRM_API_KEY or JWT Bearer (via get_current_user_or_api_key).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger("pos.resolve_lo")

router = APIRouter(prefix="/api/v1/pos", tags=["POS Resolve LO"])


# ---------------------------------------------------------------------------
# Lazy imports (avoid circular deps at module load)
# ---------------------------------------------------------------------------

def _get_db():
    from database import get_db
    return get_db


def _get_auth():
    from auth.dependencies import get_current_user_or_api_key
    return get_current_user_or_api_key


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class LoanOfficerInfo(BaseModel):
    user_id: int
    name: str
    nmlsr_id: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    organization_name: Optional[str] = None
    organization_nmlsr_id: Optional[str] = None


class ResolveLOResponse(BaseModel):
    found: bool
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    loan_officer: Optional[LoanOfficerInfo] = None


# ---------------------------------------------------------------------------
# Phone normalization
# ---------------------------------------------------------------------------

_DIGITS_RE = re.compile(r"\D")


def _normalize_phone(raw: str) -> str:
    """Strip to digits only, prepend +1 if 10 digits (US)."""
    digits = _DIGITS_RE.sub("", raw)
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits if digits else ""


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/resolve-lo", response_model=ResolveLOResponse)
async def resolve_loan_officer(
    phone: str = Query(..., min_length=5, description="Caller phone number (E.164 preferred)"),
    db: Session = Depends(_get_db()),
    _current_user=Depends(_get_auth()),
):
    """
    Look up a caller's assigned loan officer by phone number.

    Search order:
      1. Lead.phone match -> Lead.owner_id (the assigned LO)
      2. Loan.borrower_phone match -> Loan.loan_officer_id
      3. No match -> ``{"found": false}``

    Strategy 1 uses indexed Lead.phone (plain String) for fast SQL matching.
    Strategy 2 loads candidate Loans and compares borrower_phone in Python
    because borrower_phone is EncryptedString (Fernet with random IVs), so
    SQL equality comparison is not possible.
    """
    from database.models import Lead, Loan, User, Organization

    normalized = _normalize_phone(phone)
    if not normalized:
        return ResolveLOResponse(found=False)

    # --- C1 FIX: Tenant isolation ---
    # Filter queries by the caller's organization_id to prevent cross-tenant
    # data leakage.  _current_user is either a real User (JWT) or a _SystemUser
    # (API key auth) — both expose .organization_id.
    org_id = getattr(_current_user, "organization_id", None)
    if org_id is None and getattr(_current_user, "role", None) == "system":
        logger.warning(
            "resolve-lo called by _SystemUser with no organization_id — "
            "queries will be unscoped (backward compat)"
        )

    # Build phone variants for flexible matching
    # E.164: +18435551212, digits-only: 18435551212, local: 8435551212
    digits_only = normalized.lstrip("+")
    local_digits = digits_only[1:] if len(digits_only) == 11 and digits_only.startswith("1") else digits_only
    phone_variants = {normalized, digits_only, local_digits, phone.strip()}

    # --- Strategy 1: Find Lead by phone, get owner (LO) ---
    try:
        from sqlalchemy import or_

        lead_query = (
            db.query(Lead)
            .filter(
                Lead.owner_id.isnot(None),
                or_(*[Lead.phone == v for v in phone_variants if v]),
            )
        )
        if org_id is not None:
            lead_query = lead_query.filter(Lead.organization_id == org_id)
        lead = lead_query.order_by(Lead.updated_at.desc()).first()

        if lead and lead.owner_id:
            lo_user = db.query(User).filter(User.id == lead.owner_id).first()
            if lo_user:
                org = None
                if lo_user.organization_id:
                    org = db.query(Organization).filter(Organization.id == lo_user.organization_id).first()
                return ResolveLOResponse(
                    found=True,
                    lead_id=lead.id,
                    loan_officer=_user_to_lo_info(lo_user, org),
                )
    except Exception as e:
        logger.warning("Lead phone lookup failed", extra={"error": str(e)})

    # --- Strategy 2: Find Loan by borrower_phone, get loan_officer ---
    # Loan.borrower_phone is EncryptedString (Fernet with random IVs), so SQL
    # equality won't work — each encryption produces different ciphertext.
    # Load candidate loans and compare the decrypted phone in Python.
    #
    # M1 FIX: Cap at 100 rows to bound decryption cost.  Long-term this needs
    # a dedicated phone-hash lookup table (e.g. loans_phone_index with
    # SHA-256 of normalized phone) so we can do a single SQL hit.
    try:
        _LOAN_SCAN_LIMIT = 100

        loan_query = (
            db.query(Loan)
            .filter(
                Loan.loan_officer_id.isnot(None),
                Loan.borrower_phone.isnot(None),
            )
        )
        if org_id is not None:
            loan_query = loan_query.filter(Loan.organization_id == org_id)

        # Check if there are more rows than our scan limit (performance warning)
        candidate_count = loan_query.count()
        if candidate_count > _LOAN_SCAN_LIMIT:
            logger.warning(
                "Loan phone scan capped at %d rows (total matching: %d) — "
                "consider adding a phone-hash lookup table",
                _LOAN_SCAN_LIMIT,
                candidate_count,
            )

        candidate_loans = (
            loan_query
            .order_by(Loan.updated_at.desc())
            .limit(_LOAN_SCAN_LIMIT)
            .all()
        )

        digits_variants = {_DIGITS_RE.sub("", v) for v in phone_variants if v}
        matched_loan = None
        for loan in candidate_loans:
            loan_phone_digits = _DIGITS_RE.sub("", loan.borrower_phone or "")
            if loan_phone_digits in digits_variants:
                matched_loan = loan
                break

        if matched_loan and matched_loan.loan_officer_id:
            lo_user = db.query(User).filter(User.id == matched_loan.loan_officer_id).first()
            if lo_user:
                org = None
                if lo_user.organization_id:
                    org = db.query(Organization).filter(Organization.id == lo_user.organization_id).first()
                return ResolveLOResponse(
                    found=True,
                    loan_id=matched_loan.id,
                    loan_officer=_user_to_lo_info(lo_user, org),
                )
    except Exception as e:
        logger.warning("Loan phone lookup failed", extra={"error": str(e)})

    return ResolveLOResponse(found=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_to_lo_info(user, org=None) -> LoanOfficerInfo:
    """Convert a User model + optional Organization to LoanOfficerInfo."""
    name = ""
    if user.first_name and user.last_name:
        name = f"{user.first_name} {user.last_name}"
    elif user.first_name:
        name = user.first_name
    elif user.last_name:
        name = user.last_name

    # NMLS: User model has both nmls_number (indexed, public) and nmls_id
    nmlsr = user.nmls_number or user.nmls_id or ""

    return LoanOfficerInfo(
        user_id=user.id,
        name=name,
        nmlsr_id=nmlsr,
        email=user.email or "",
        phone=user.phone or "",
        organization_name=org.name if org else "",
        organization_nmlsr_id="",  # Organization model doesn't have NMLS; caller uses env fallback
    )
