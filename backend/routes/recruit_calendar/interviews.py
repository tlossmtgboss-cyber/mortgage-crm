"""
Recruit Calendar — Interview endpoints.

Hybrid approach: scheduling mechanics live in scheduler_appointments;
recruiting metadata (candidate, type, outcome, scorecard) live in
recruit_interview_details (1:1 FK to scheduler_appointments).

Prefix: /api/v1/recruit-calendar/interviews
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from database.models import User
from db import get_db
from routes.recruit_calendar._models import (
    InterviewCreate, InterviewUpdate, InterviewCompleteRequest,
    InterviewType, InterviewOutcome,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_org(user: User) -> int:
    oid = getattr(user, "organization_id", None)
    if not oid:
        raise HTTPException(status_code=400, detail="User has no organization")
    return oid


def _require_admin(user: User) -> None:
    if user.role not in ("admin", "platform_admin", "site_admin", "management"):
        raise HTTPException(status_code=403, detail="Admin access required")


def _build_interview_response(row, detail_row) -> Dict[str, Any]:
    return {
        "id": row.id if row else None,
        "interview_detail_id": detail_row.id if detail_row else None,
        "candidate_id": detail_row.candidate_id if detail_row else None,
        "interview_type": detail_row.interview_type if detail_row else None,
        "outcome": detail_row.outcome if detail_row else "pending",
        "scorecard": detail_row.scorecard if detail_row else {},
        "panel_members": detail_row.panel_members if detail_row else [],
        "interviewer_notes": detail_row.interviewer_notes if detail_row else None,
        "title": row.title if row else None,
        "scheduled_start": row.scheduled_start.isoformat() if row and row.scheduled_start else None,
        "scheduled_end": row.scheduled_end.isoformat() if row and row.scheduled_end else None,
        "duration_minutes": row.duration_minutes if row else None,
        "location": row.location if row else None,
        "video_link": row.video_link if row else None,
        "status": row.status if row else None,
        "assigned_user_id": row.assigned_user_id if row else None,
        "attendee_name": row.attendee_name if row else None,
        "attendee_email": row.attendee_email if row else None,
        "created_at": row.created_at.isoformat() if row and row.created_at else None,
    }


@router.get("")
async def list_interviews(
    candidate_id: Optional[int] = None,
    interviewer_id: Optional[int] = None,
    interview_type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List interviews for the org with optional filters."""
    org_id = _get_org(current_user)

    where_clauses = [
        "sa.organization_id = :org_id",
        "sa.external_source = 'recruiting'",
        "sa.deleted_at IS NULL",
    ]
    params: Dict[str, Any] = {"org_id": org_id, "limit": limit, "offset": offset}

    if candidate_id:
        where_clauses.append("rid.candidate_id = :candidate_id")
        params["candidate_id"] = candidate_id
    if interviewer_id:
        where_clauses.append("sa.assigned_user_id = :interviewer_id")
        params["interviewer_id"] = interviewer_id
    if interview_type:
        where_clauses.append("rid.interview_type = :interview_type")
        params["interview_type"] = interview_type
    if status:
        where_clauses.append("sa.status = :status")
        params["status"] = status
    if date_from:
        where_clauses.append("sa.scheduled_start >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where_clauses.append("sa.scheduled_start <= :date_to")
        params["date_to"] = date_to

    where_sql = " AND ".join(where_clauses)
    rows = db.execute(text(f"""
        SELECT
            sa.id, sa.title, sa.scheduled_start, sa.scheduled_end,
            sa.duration_minutes, sa.location, sa.video_link, sa.status,
            sa.assigned_user_id, sa.attendee_name, sa.attendee_email,
            sa.created_at,
            rid.id AS detail_id, rid.candidate_id, rid.interview_type,
            rid.outcome, rid.scorecard, rid.panel_members, rid.interviewer_notes
        FROM scheduler_appointments sa
        LEFT JOIN recruit_interview_details rid ON rid.appointment_id = sa.id
        WHERE {where_sql}
        ORDER BY sa.scheduled_start ASC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    total = db.execute(text(f"""
        SELECT COUNT(*) FROM scheduler_appointments sa
        LEFT JOIN recruit_interview_details rid ON rid.appointment_id = sa.id
        WHERE {where_sql}
    """), {k: v for k, v in params.items() if k not in ("limit", "offset")}).scalar()

    return {
        "interviews": [
            {
                "id": r.id,
                "interview_detail_id": r.detail_id,
                "candidate_id": r.candidate_id,
                "interview_type": r.interview_type,
                "outcome": r.outcome or "pending",
                "title": r.title,
                "scheduled_start": r.scheduled_start.isoformat() if r.scheduled_start else None,
                "scheduled_end": r.scheduled_end.isoformat() if r.scheduled_end else None,
                "duration_minutes": r.duration_minutes,
                "location": r.location,
                "video_link": r.video_link,
                "status": r.status,
                "assigned_user_id": r.assigned_user_id,
                "attendee_name": r.attendee_name,
                "attendee_email": r.attendee_email,
                "scorecard": r.scorecard or {},
                "panel_members": r.panel_members or [],
                "interviewer_notes": r.interviewer_notes,
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/calendar")
async def interview_calendar_view(
    year: int = Query(...),
    month: int = Query(...),
    user_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return interviews for a month in calendar format."""
    org_id = _get_org(current_user)
    target_uid = user_id or current_user.id
    rows = db.execute(text("""
        SELECT
            sa.id, sa.title, sa.scheduled_start, sa.scheduled_end,
            sa.status, sa.attendee_name,
            rid.candidate_id, rid.interview_type, rid.outcome
        FROM scheduler_appointments sa
        LEFT JOIN recruit_interview_details rid ON rid.appointment_id = sa.id
        WHERE sa.organization_id = :org_id
          AND sa.external_source = 'recruiting'
          AND sa.deleted_at IS NULL
          AND EXTRACT(YEAR  FROM sa.scheduled_start) = :yr
          AND EXTRACT(MONTH FROM sa.scheduled_start) = :mo
          AND (:uid IS NULL OR sa.assigned_user_id = :uid)
        ORDER BY sa.scheduled_start
    """), {"org_id": org_id, "yr": year, "mo": month, "uid": target_uid}).fetchall()

    return {
        "year": year,
        "month": month,
        "events": [
            {
                "id": r.id,
                "title": r.title or f"{r.interview_type or 'Interview'} — {r.attendee_name or ''}",
                "start": r.scheduled_start.isoformat() if r.scheduled_start else None,
                "end": r.scheduled_end.isoformat() if r.scheduled_end else None,
                "status": r.status,
                "interview_type": r.interview_type,
                "outcome": r.outcome,
                "candidate_id": r.candidate_id,
            }
            for r in rows
        ],
    }


@router.get("/{interview_id}")
async def get_interview(
    interview_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get full interview details."""
    org_id = _get_org(current_user)
    row = db.execute(text("""
        SELECT
            sa.id, sa.title, sa.scheduled_start, sa.scheduled_end,
            sa.duration_minutes, sa.location, sa.video_link, sa.status,
            sa.assigned_user_id, sa.attendee_name, sa.attendee_email,
            sa.attendee_notes, sa.created_at,
            rid.id AS detail_id, rid.candidate_id, rid.interview_type,
            rid.outcome, rid.scorecard, rid.panel_members, rid.interviewer_notes
        FROM scheduler_appointments sa
        LEFT JOIN recruit_interview_details rid ON rid.appointment_id = sa.id
        WHERE sa.id = :id
          AND sa.organization_id = :org_id
          AND sa.external_source = 'recruiting'
          AND sa.deleted_at IS NULL
    """), {"id": interview_id, "org_id": org_id}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Interview not found")

    return {
        "id": row.id,
        "interview_detail_id": row.detail_id,
        "candidate_id": row.candidate_id,
        "interview_type": row.interview_type,
        "outcome": row.outcome or "pending",
        "scorecard": row.scorecard or {},
        "panel_members": row.panel_members or [],
        "interviewer_notes": row.interviewer_notes,
        "title": row.title,
        "scheduled_start": row.scheduled_start.isoformat() if row.scheduled_start else None,
        "scheduled_end": row.scheduled_end.isoformat() if row.scheduled_end else None,
        "duration_minutes": row.duration_minutes,
        "location": row.location,
        "video_link": row.video_link,
        "status": row.status,
        "assigned_user_id": row.assigned_user_id,
        "attendee_name": row.attendee_name,
        "attendee_email": row.attendee_email,
        "attendee_notes": row.attendee_notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.post("")
async def create_interview(
    data: InterviewCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new interview appointment."""
    org_id = _get_org(current_user)

    # Determine duration
    duration = int((data.scheduled_end - data.scheduled_start).total_seconds() / 60)
    if duration < 5:
        raise HTTPException(status_code=400, detail="Interview must be at least 5 minutes")

    title = data.title or f"{data.interview_type.replace('_', ' ').title()} — Candidate #{data.candidate_id}"

    appt = db.execute(text("""
        INSERT INTO scheduler_appointments (
            organization_id, title, meeting_type, meeting_mode,
            scheduled_start, scheduled_end, duration_minutes,
            status, assigned_user_id, created_by_user_id,
            location, video_link, external_source,
            created_at, updated_at
        ) VALUES (
            :org_id, :title, 'custom', 'video',
            :start, :end, :dur,
            'booked', :interviewer, :created_by,
            :location, :zoom_link, 'recruiting',
            NOW(), NOW()
        ) RETURNING id
    """), {
        "org_id": org_id,
        "title": title,
        "start": data.scheduled_start,
        "end": data.scheduled_end,
        "dur": duration,
        "interviewer": data.interviewer_user_id,
        "created_by": current_user.id,
        "location": data.location,
        "zoom_link": data.zoom_link,
    }).fetchone()
    appt_id = appt.id

    detail = db.execute(text("""
        INSERT INTO recruit_interview_details (
            organization_id, appointment_id, candidate_id,
            interview_type, panel_members, outcome, created_at, updated_at
        ) VALUES (
            :org_id, :appt_id, :candidate_id,
            :itype, :panel, 'pending', NOW(), NOW()
        ) RETURNING id
    """), {
        "org_id": org_id,
        "appt_id": appt_id,
        "candidate_id": data.candidate_id,
        "itype": data.interview_type.value,
        "panel": str(data.panel_members or []).replace("'", '"'),
    }).fetchone()

    db.commit()
    return {"id": appt_id, "interview_detail_id": detail.id, "status": "created"}


@router.patch("/{interview_id}")
async def update_interview(
    interview_id: int,
    data: InterviewUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update interview scheduling or metadata."""
    org_id = _get_org(current_user)

    # Verify ownership
    exists = db.execute(text("""
        SELECT id FROM scheduler_appointments
        WHERE id = :id AND organization_id = :org_id AND external_source = 'recruiting'
          AND deleted_at IS NULL
    """), {"id": interview_id, "org_id": org_id}).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Interview not found")

    # Update appointment row if scheduling changed
    appt_updates = {}
    if data.scheduled_start:
        appt_updates["scheduled_start"] = data.scheduled_start
    if data.scheduled_end:
        appt_updates["scheduled_end"] = data.scheduled_end
    if data.location is not None:
        appt_updates["location"] = data.location
    if data.zoom_link is not None:
        appt_updates["video_link"] = data.zoom_link

    if appt_updates:
        set_clauses = ", ".join(f"{k} = :{k}" for k in appt_updates)
        appt_updates["id"] = interview_id
        appt_updates["updated_at"] = datetime.now(timezone.utc)
        db.execute(text(f"UPDATE scheduler_appointments SET {set_clauses}, updated_at = :updated_at WHERE id = :id"), appt_updates)

    # Update detail row if metadata changed
    detail_updates: Dict[str, Any] = {}
    if data.outcome is not None:
        detail_updates["outcome"] = data.outcome.value
    if data.scorecard is not None:
        import json
        detail_updates["scorecard"] = json.dumps(data.scorecard)
    if data.interviewer_notes is not None:
        detail_updates["interviewer_notes"] = data.interviewer_notes

    if detail_updates:
        set_clauses = ", ".join(f"{k} = :{k}" for k in detail_updates)
        detail_updates["appt_id"] = interview_id
        detail_updates["updated_at"] = datetime.now(timezone.utc)
        db.execute(text(f"UPDATE recruit_interview_details SET {set_clauses}, updated_at = :updated_at WHERE appointment_id = :appt_id"), detail_updates)

    db.commit()
    return {"id": interview_id, "updated": True}


@router.delete("/{interview_id}")
async def delete_interview(
    interview_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-delete an interview."""
    org_id = _get_org(current_user)
    result = db.execute(text("""
        UPDATE scheduler_appointments
        SET deleted_at = NOW(), status = 'cancelled', updated_at = NOW()
        WHERE id = :id AND organization_id = :org_id AND external_source = 'recruiting'
          AND deleted_at IS NULL
        RETURNING id
    """), {"id": interview_id, "org_id": org_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Interview not found")

    db.commit()
    return {"id": interview_id, "deleted": True}


@router.post("/{interview_id}/complete")
async def complete_interview(
    interview_id: int,
    data: InterviewCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark interview complete with outcome and scorecard."""
    org_id = _get_org(current_user)

    appt = db.execute(text("""
        UPDATE scheduler_appointments
        SET status = 'completed', completed_at = NOW(), updated_at = NOW()
        WHERE id = :id AND organization_id = :org_id AND external_source = 'recruiting'
          AND deleted_at IS NULL
        RETURNING id
    """), {"id": interview_id, "org_id": org_id}).fetchone()

    if not appt:
        raise HTTPException(status_code=404, detail="Interview not found")

    import json
    db.execute(text("""
        UPDATE recruit_interview_details
        SET outcome = :outcome,
            interviewer_notes = COALESCE(:notes, interviewer_notes),
            scorecard = :scorecard::jsonb,
            updated_at = NOW()
        WHERE appointment_id = :appt_id
    """), {
        "outcome": data.outcome.value,
        "notes": data.interviewer_notes,
        "scorecard": json.dumps(data.scorecard or {}),
        "appt_id": interview_id,
    })

    db.commit()
    return {"id": interview_id, "outcome": data.outcome.value, "completed": True}
