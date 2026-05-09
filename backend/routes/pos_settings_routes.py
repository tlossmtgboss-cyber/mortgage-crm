"""
POS Settings endpoint for the Marketing Lab.

Returns org slug (for the application link) and the calendar user
(whose calendar appointments are booked on) plus team role assignments.
Auth: JWT (internal CRM user).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pos", tags=["POS Settings"])


def _get_current_user():
    from auth.dependencies import get_current_user
    return get_current_user


class CalendarUserInfo(BaseModel):
    user_id: int
    name: str
    email: Optional[str] = None


class POSSettingsResponse(BaseModel):
    org_slug: Optional[str] = None
    calendar_user: Optional[CalendarUserInfo] = None


@router.get("/settings", response_model=POSSettingsResponse)
def get_pos_settings(
    user=Depends(_get_current_user()),
    db: Session = Depends(get_db),
) -> POSSettingsResponse:
    org_id = user.organization_id
    org_slug: str | None = None
    calendar_user: CalendarUserInfo | None = None

    # 1. Org slug for the application link
    try:
        from database.models.core import Organization
        org = db.get(Organization, org_id)
        if org:
            org_slug = org.slug
    except Exception as e:
        logger.warning("Failed to load org slug: %s", e)

    # 2. Calendar user — the LO whose calendar appointments are booked on.
    #    Determined by: first user with the "Loan Officer" workflow role,
    #    or falling back to the booking link owner.
    try:
        from database.models.core import User

        lo_row = db.execute(text("""
            SELECT dra.user_id
            FROM default_role_assignments dra
            JOIN roles r ON r.id = dra.role_id
            WHERE dra.organization_id = :org_id
              AND r.name ILIKE '%%loan officer%%'
            ORDER BY dra.id ASC
            LIMIT 1
        """), {"org_id": org_id}).fetchone()

        lo_user_id = lo_row[0] if lo_row else None

        if lo_user_id is None:
            lo_user_id = user.id

        lo_user = db.get(User, lo_user_id)
        if lo_user:
            first = getattr(lo_user, "first_name", "") or ""
            last = getattr(lo_user, "last_name", "") or ""
            name = f"{first} {last}".strip() or lo_user.email or f"User #{lo_user.id}"
            calendar_user = CalendarUserInfo(
                user_id=lo_user.id,
                name=name,
                email=lo_user.email,
            )
    except Exception as e:
        logger.warning("Failed to resolve calendar user: %s", e)

    return POSSettingsResponse(
        org_slug=org_slug,
        calendar_user=calendar_user,
    )
