"""
Recruit Calendar — Auto-provisioning.

Creates default recruiting appointment types for a new recruiter.
Called from JIT provisioning and SCIM user creation (same pattern as
services/scheduler_provisioning.py).
"""
from __future__ import annotations
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_INTERVIEW_TYPES = [
    {"name": "Phone Screen", "duration_minutes": 30, "interview_type": "phone_screen",
     "description": "Initial 30-minute phone screen"},
    {"name": "Video Interview", "duration_minutes": 60, "interview_type": "video_interview",
     "description": "60-minute video interview"},
    {"name": "Panel Interview", "duration_minutes": 90, "interview_type": "panel_interview",
     "description": "Panel interview with multiple team members"},
    {"name": "Culture Fit", "duration_minutes": 45, "interview_type": "culture_fit",
     "description": "Culture and values alignment conversation"},
    {"name": "Offer Call", "duration_minutes": 30, "interview_type": "offer_call",
     "description": "Offer presentation and discussion"},
]


def auto_provision_recruiter_calendar(
    user_id: int,
    organization_id: int,
    db: Session,
    user_email: Optional[str] = None,
) -> None:
    """
    Idempotently provision default recruiting appointment types for a user.
    Safe to call multiple times — skips if types already exist.
    Never raises; logs warnings on failure so user creation is never blocked.
    """
    try:
        for atype in DEFAULT_INTERVIEW_TYPES:
            existing = db.execute(text("""
                SELECT id FROM appointment_types
                WHERE organization_id = :org_id
                  AND user_id = :user_id
                  AND name = :name
            """), {
                "org_id": organization_id,
                "user_id": user_id,
                "name": atype["name"],
            }).fetchone()

            if existing:
                continue

            db.execute(text("""
                INSERT INTO appointment_types (
                    organization_id, user_id, name, description,
                    duration_minutes, meeting_mode, is_active,
                    external_source, created_at, updated_at
                ) VALUES (
                    :org_id, :user_id, :name, :desc,
                    :dur, 'video', true,
                    'recruiting', NOW(), NOW()
                )
            """), {
                "org_id": organization_id,
                "user_id": user_id,
                "name": atype["name"],
                "desc": atype["description"],
                "dur": atype["duration_minutes"],
            })

        db.commit()
        logger.info(
            "Provisioned recruiting calendar for user %s (org %s)",
            user_id, organization_id
        )
    except Exception as e:
        logger.warning(
            "Could not provision recruiting calendar for user %s: %s",
            user_id, e
        )
        try:
            db.rollback()
        except Exception:
            pass
