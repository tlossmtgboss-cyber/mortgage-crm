"""
Recruit Calendar — Candidate Booking endpoints.

Candidates book interviews via a time-limited token link.
Reuses scheduler_booking_links table with context_type='recruiting'.

Prefix: /api/v1/recruit-calendar/booking
"""
from __future__ import annotations
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from database.models import User
from db import get_db
from routes.recruit_calendar._models import BookingLinkCreate, BookingConfirm

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_org(user: User) -> int:
    oid = getattr(user, "organization_id", None)
    if not oid:
        raise HTTPException(status_code=400, detail="User has no organization")
    return oid


@router.post("/links")
async def create_booking_link(
    data: BookingLinkCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a time-limited booking link for a candidate to self-schedule
    an interview with a specific interviewer.
    """
    org_id = _get_org(current_user)
    token = secrets.token_urlsafe(24)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=data.expires_hours)
    title = data.title or f"{data.interview_type.replace('_', ' ').title()} Scheduling"

    result = db.execute(text("""
        INSERT INTO scheduler_booking_links (
            organization_id, slug, title, is_active,
            duration_minutes, context_type, context_id,
            assigned_user_id, expires_at, created_at, updated_at,
            link_metadata
        ) VALUES (
            :org_id, :slug, :title, true,
            30, 'recruiting', :candidate_id,
            :interviewer, :expires_at, NOW(), NOW(),
            :meta::jsonb
        ) RETURNING id, slug
    """), {
        "org_id": org_id,
        "slug": token,
        "title": title,
        "candidate_id": data.candidate_id,
        "interviewer": data.interviewer_user_id or current_user.id,
        "expires_at": expires_at,
        "meta": f'{{"interview_type": "{data.interview_type.value}", "candidate_id": {data.candidate_id}}}',
    }).fetchone()
    db.commit()

    return {
        "id": result.id,
        "token": result.slug,
        "booking_url": f"/recruit-portal/{result.slug}",
        "expires_at": expires_at.isoformat(),
        "interview_type": data.interview_type.value,
    }


@router.get("/links")
async def list_booking_links(
    candidate_id: Optional[int] = None,
    active_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List recruiting booking links for this org."""
    org_id = _get_org(current_user)
    where = ["organization_id = :org_id", "context_type = 'recruiting'"]
    params: Dict[str, Any] = {"org_id": org_id}

    if candidate_id:
        where.append("context_id = :candidate_id")
        params["candidate_id"] = candidate_id
    if active_only:
        where.append("is_active = true AND (expires_at IS NULL OR expires_at > NOW())")

    rows = db.execute(text(f"""
        SELECT id, slug, title, context_id AS candidate_id,
               assigned_user_id, expires_at, is_active, created_at, link_metadata
        FROM scheduler_booking_links
        WHERE {" AND ".join(where)}
        ORDER BY created_at DESC
        LIMIT 100
    """), params).fetchall()

    return {
        "links": [
            {
                "id": r.id,
                "token": r.slug,
                "booking_url": f"/recruit-portal/{r.slug}",
                "title": r.title,
                "candidate_id": r.candidate_id,
                "assigned_user_id": r.assigned_user_id,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "metadata": r.link_metadata,
            }
            for r in rows
        ]
    }


@router.get("/links/{token}")
async def get_booking_page(
    token: str,
    db: Session = Depends(get_db),
):
    """
    Public endpoint — no auth required.
    Returns booking page data for a candidate to self-schedule.
    """
    link = db.execute(text("""
        SELECT
            bl.id, bl.slug, bl.title, bl.context_id AS candidate_id,
            bl.assigned_user_id, bl.expires_at, bl.is_active,
            bl.duration_minutes, bl.link_metadata,
            u.first_name || ' ' || u.last_name AS interviewer_name,
            u.email AS interviewer_email,
            o.name AS org_name
        FROM scheduler_booking_links bl
        LEFT JOIN users u ON u.id = bl.assigned_user_id
        LEFT JOIN organizations o ON o.id = bl.organization_id
        WHERE bl.slug = :token
          AND bl.context_type = 'recruiting'
          AND bl.is_active = true
    """), {"token": token}).fetchone()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This booking link has expired")

    import json
    meta = {}
    if link.link_metadata:
        try:
            meta = json.loads(link.link_metadata) if isinstance(link.link_metadata, str) else link.link_metadata
        except Exception:
            pass

    return {
        "token": token,
        "title": link.title,
        "interview_type": meta.get("interview_type", "interview"),
        "duration_minutes": link.duration_minutes or 30,
        "interviewer_name": link.interviewer_name,
        "org_name": link.org_name or "Recruiting Team",
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        "candidate_id": link.candidate_id,
    }


@router.post("/links/{token}/book")
async def confirm_booking(
    token: str,
    data: BookingConfirm,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public endpoint — no auth required.
    Candidate confirms a booking slot via the token link.
    Creates a scheduler_appointment + recruit_interview_details row.
    """
    # SELECT FOR UPDATE serializes concurrent booking requests on the same link row.
    # If two requests race, the second sees is_active=false (set by the first) and
    # returns 404 rather than double-booking the same slot.
    link = db.execute(text("""
        SELECT bl.id, bl.organization_id, bl.context_id AS candidate_id,
               bl.assigned_user_id, bl.duration_minutes, bl.is_active,
               bl.expires_at, bl.link_metadata
        FROM scheduler_booking_links bl
        WHERE bl.slug = :token AND bl.context_type = 'recruiting' AND bl.is_active = true
        FOR UPDATE
    """), {"token": token}).fetchone()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found or inactive")

    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This booking link has expired")

    import json
    meta = {}
    if link.link_metadata:
        try:
            meta = json.loads(link.link_metadata) if isinstance(link.link_metadata, str) else link.link_metadata
        except Exception:
            pass

    interview_type = meta.get("interview_type", "interview")
    duration = int((data.slot_end - data.slot_start).total_seconds() / 60)

    # Conflict check: raises HTTPException 409 if the interviewer already has an
    # overlapping appointment.  The FOR UPDATE lock above serializes concurrent
    # requests on the same booking link, but we still need this check for the
    # case where the interviewer was booked through a different link/channel.
    from routes.scheduler._conflicts import _check_appointment_conflict
    await _check_appointment_conflict(
        db,
        link.assigned_user_id,
        data.slot_start,
        data.slot_end,
        org_id=link.organization_id,
    )

    appt = db.execute(text("""
        INSERT INTO scheduler_appointments (
            organization_id, title, meeting_type, meeting_mode,
            scheduled_start, scheduled_end, duration_minutes,
            status, assigned_user_id,
            attendee_name, attendee_email, attendee_notes,
            external_source, created_at, updated_at
        ) VALUES (
            :org_id, :title, 'custom', 'video',
            :start, :end, :dur,
            'booked', :interviewer,
            :aname, :aemail, :anotes,
            'recruiting', NOW(), NOW()
        ) RETURNING id
    """), {
        "org_id": link.organization_id,
        "title": f"{interview_type.replace('_', ' ').title()} — {data.candidate_name}",
        "start": data.slot_start,
        "end": data.slot_end,
        "dur": duration,
        "interviewer": link.assigned_user_id,
        "aname": data.candidate_name,
        "aemail": data.candidate_email,
        "anotes": data.notes,
    }).fetchone()

    db.execute(text("""
        INSERT INTO recruit_interview_details (
            organization_id, appointment_id, candidate_id,
            interview_type, outcome, created_at, updated_at
        ) VALUES (
            :org_id, :appt_id, :candidate_id,
            :itype, 'pending', NOW(), NOW()
        )
    """), {
        "org_id": link.organization_id,
        "appt_id": appt.id,
        "candidate_id": link.candidate_id,
        "itype": interview_type,
    })

    # Deactivate the single-use link
    db.execute(text("""
        UPDATE scheduler_booking_links SET is_active = false, updated_at = NOW()
        WHERE id = :id
    """), {"id": link.id})

    db.commit()
    return {
        "appointment_id": appt.id,
        "confirmed": True,
        "scheduled_start": data.slot_start.isoformat(),
        "scheduled_end": data.slot_end.isoformat(),
        "message": "Your interview has been scheduled. You will receive a confirmation email.",
    }
