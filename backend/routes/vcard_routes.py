"""
VCard routes — serves dynamically-generated .vcf contact cards.

The team-card endpoint is public (no JWT) because Telnyx fetches the
media URL server-side when delivering MMS.  Access is gated by a
short-lived HMAC token embedded in the URL.
"""

import hashlib
import hmac
import os
import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/vcard", tags=["VCard"])

_SECRET = (os.getenv("SECRET_KEY") or "dev-fallback-key").encode()
_TOKEN_MAX_AGE = 60 * 60 * 24  # 24 hours


def _sign_vcard_token(lead_id: int, ts: Optional[int] = None) -> str:
    ts = ts or int(time.time())
    msg = f"{lead_id}:{ts}".encode()
    sig = hmac.new(_SECRET, msg, hashlib.sha256).hexdigest()[:16]
    return f"{lead_id}.{ts}.{sig}"


def _verify_vcard_token(token: str) -> int:
    """Return lead_id if token is valid and not expired, else raise 403."""
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=403, detail="Invalid token")

    try:
        lead_id = int(parts[0])
        ts = int(parts[1])
        sig = parts[2]
    except (ValueError, IndexError):
        raise HTTPException(status_code=403, detail="Invalid token")

    expected = hmac.new(_SECRET, f"{lead_id}:{ts}".encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=403, detail="Invalid token")

    if time.time() - ts > _TOKEN_MAX_AGE:
        raise HTTPException(status_code=403, detail="Token expired")

    return lead_id


_get_db = None
_models = None


def set_dependencies(get_db, models=None):
    global _get_db, _models
    _get_db = get_db
    _models = models


@router.get("/team/{token}")
async def serve_team_vcard(token: str):
    """Serve a combined team vCard for a lead's assigned team.

    URL format: /api/v1/vcard/team/{lead_id}.{timestamp}.{hmac}
    Public (no JWT) — Telnyx fetches this URL to deliver MMS.
    """
    lead_id = _verify_vcard_token(token)

    if not _get_db:
        raise HTTPException(status_code=500, detail="Service not configured")

    db: Session = next(_get_db())
    try:
        from database.models.lead_loan import Lead, Loan
        from database.models.core import User, Organization
        from services.smart_docs.communication_orchestrator import generate_team_vcard

        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        org_name = "Your Mortgage Team"
        if lead.organization_id:
            org = db.query(Organization).filter(Organization.id == lead.organization_id).first()
            if org:
                org_name = org.name or org_name

        team = []

        # Priority 1: Use the configured contact card roster from Settings
        try:
            from database.models.contact_card import ContactCardMember
            configured = (
                db.query(ContactCardMember)
                .filter(
                    ContactCardMember.organization_id == lead.organization_id,
                    ContactCardMember.is_active.is_(True),
                )
                .order_by(ContactCardMember.sort_order, ContactCardMember.id)
                .all()
            )
            for m in configured:
                team.append({
                    "name": m.name,
                    "role": m.role_label,
                    "phone": m.phone,
                    "email": m.email,
                })
        except Exception:
            pass

        # Priority 2: Fall back to auto-discovery from Lead/Loan data
        if not team:
            if lead.owner_id:
                lo = db.query(User).filter(User.id == lead.owner_id).first()
                if lo:
                    team.append({
                        "name": lo.full_name or f"{lo.first_name or ''} {lo.last_name or ''}".strip(),
                        "role": "Loan Officer",
                        "phone": getattr(lo, "phone", None),
                        "email": lo.email,
                    })

            loan = None
            if lead.email and lead.organization_id:
                loan = db.query(Loan).filter(
                    Loan.borrower_email == lead.email,
                    Loan.organization_id == lead.organization_id,
                    Loan.deleted_at.is_(None),
                ).order_by(Loan.created_at.desc()).first()
            if not loan and lead.owner_id:
                loan = db.query(Loan).filter(
                    Loan.loan_officer_id == lead.owner_id,
                    Loan.organization_id == lead.organization_id,
                    Loan.deleted_at.is_(None),
                ).order_by(Loan.created_at.desc()).first()

            if loan:
                for field, role, email_field in [
                    ("processor", "Processor", "processor_email"),
                    ("underwriter", "Underwriter", "underwriter_email"),
                    ("closer", "Closer", "closer_email"),
                    ("production_assistant", "Production Assistant", None),
                ]:
                    name = getattr(loan, field, None)
                    if name:
                        team.append({
                            "name": name,
                            "role": role,
                            "phone": None,
                            "email": getattr(loan, email_field, None) if email_field else None,
                        })

        if not team:
            raise HTTPException(status_code=404, detail="No team members found")

        vcf_content = generate_team_vcard(team, company_name=org_name)

        return Response(
            content=vcf_content,
            media_type="text/vcard",
            headers={
                "Content-Disposition": "attachment; filename=team-contact.vcf",
                "Cache-Control": "public, max-age=3600",
            },
        )
    finally:
        db.close()
