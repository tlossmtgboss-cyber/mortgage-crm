"""Phone → loan/contact/lead resolver for CIE webhooks."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class CallContext:
    organization_id: int
    contact_id: Optional[int] = None
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    user_id: Optional[int] = None


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"[^0-9]", "", raw)
    return digits[-10:] if len(digits) >= 10 else digits


def resolve_call_context(
    phone: str,
    organization_id: int,
    db: Session,
) -> CallContext:
    """Resolve a phone number to CRM entities within a tenant.

    Queries leads table (phone column) with 10-digit normalization,
    then walks lead → loan linkage.
    """
    ctx = CallContext(organization_id=organization_id)
    if not phone:
        return ctx

    cleaned = _normalize_phone(phone)
    if not cleaned:
        return ctx

    try:
        from database.models import Lead

        phone_digits = func.right(
            func.regexp_replace(Lead.phone, "[^0-9]", "", "g"), 10,
        )
        lead = (
            db.query(Lead)
            .filter(Lead.organization_id == organization_id)
            .filter(phone_digits == cleaned)
            .first()
        )

        if lead:
            ctx.lead_id = lead.id
            ctx.loan_id = getattr(lead, "loan_id", None)
            ctx.user_id = getattr(lead, "owner_id", None) or getattr(lead, "assigned_to", None)
            ctx.contact_id = getattr(lead, "contact_id", None)
            logger.info("CIE: phone %s → lead %s loan %s", cleaned, lead.id, ctx.loan_id)
        else:
            logger.info("CIE: no lead found for phone %s in org %s", cleaned, organization_id)

    except Exception as e:
        logger.warning("CIE: phone resolution failed: %s", e)

    return ctx
