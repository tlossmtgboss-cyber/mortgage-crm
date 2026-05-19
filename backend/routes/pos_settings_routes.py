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
    user_slug: Optional[str] = None
    calendar_user: Optional[CalendarUserInfo] = None


def _ensure_user_slug(db: Session, user) -> str | None:
    """Return user.slug, auto-generating one if missing."""
    if user.slug:
        return user.slug

    import re
    from database.models.core import User

    first = (getattr(user, "first_name", None) or "user").lower()
    last = (getattr(user, "last_name", None) or str(user.id)).lower()
    base = re.sub(r"[^a-z0-9-]", "", f"{first}-{last}")
    if not base or base == "-":
        base = f"lo-{user.id}"

    slug = base
    existing = db.query(User).filter(User.slug == slug, User.id != user.id).first()
    if existing:
        slug = f"{base}-{user.id}"

    try:
        user.slug = slug
        db.commit()
        logger.info("Auto-generated POS slug '%s' for user %s", slug, user.id)
        return slug
    except Exception as e:
        db.rollback()
        logger.warning("Failed to auto-generate slug for user %s: %s", user.id, e)
        return None


@router.get("/settings", response_model=POSSettingsResponse)
def get_pos_settings(
    user=Depends(_get_current_user()),
    db: Session = Depends(get_db),
) -> POSSettingsResponse:
    org_id = user.organization_id
    org_slug: str | None = None
    user_slug: str | None = None
    calendar_user: CalendarUserInfo | None = None

    # 1. Org slug (fallback) and user slug (per-user POS link)
    try:
        from database.models.core import Organization
        org = db.get(Organization, org_id)
        if org:
            org_slug = org.slug
    except Exception as e:
        logger.warning("Failed to load org slug: %s", e)

    user_slug = _ensure_user_slug(db, user)

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

    # 3. Check for explicit calendar user override
    try:
        override_row = db.execute(text("""
            SELECT calendar_user_id FROM pos_calendar_settings
            WHERE organization_id = :org_id
            LIMIT 1
        """), {"org_id": org_id}).fetchone()
        if override_row and override_row.calendar_user_id:
            from database.models.core import User
            override_user = db.get(User, override_row.calendar_user_id)
            if override_user:
                first = getattr(override_user, "first_name", "") or ""
                last = getattr(override_user, "last_name", "") or ""
                name = f"{first} {last}".strip() or override_user.email
                calendar_user = CalendarUserInfo(
                    user_id=override_user.id,
                    name=name,
                    email=override_user.email,
                )
    except Exception as _exc:  # noqa: BLE001
        pass

    return POSSettingsResponse(
        org_slug=org_slug,
        user_slug=user_slug,
        calendar_user=calendar_user,
    )


class CalendarUserUpdateRequest(BaseModel):
    calendar_user_id: Optional[int] = None


@router.put("/settings/calendar-user")
def update_pos_calendar_user(
    body: CalendarUserUpdateRequest,
    user=Depends(_get_current_user()),
    db: Session = Depends(get_db),
):
    org_id = user.organization_id

    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_calendar_settings (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL UNIQUE,
                calendar_user_id INTEGER,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        db.execute(text("""
            INSERT INTO pos_calendar_settings (organization_id, calendar_user_id, updated_at)
            VALUES (:org_id, :uid, NOW())
            ON CONFLICT (organization_id) DO UPDATE
            SET calendar_user_id = :uid, updated_at = NOW()
        """), {"org_id": org_id, "uid": body.calendar_user_id})
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        logger.exception("Failed to update POS calendar user: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save")
