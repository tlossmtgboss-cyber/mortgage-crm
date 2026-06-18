"""
Recruit Calendar — Milestone endpoints.

Tracks post-hire milestones: start date, 30/90-day check-ins,
license renewals, onboarding completion, etc.

Prefix: /api/v1/recruit-calendar/milestones
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from database.models import User
from db import get_db
from routes.recruit_calendar._models import MilestoneCreate, MilestoneUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_org(user: User) -> int:
    oid = getattr(user, "organization_id", None)
    if not oid:
        raise HTTPException(status_code=400, detail="User has no organization")
    return oid


@router.get("")
async def list_milestones(
    candidate_id: Optional[int] = None,
    milestone_type: Optional[str] = None,
    completed: Optional[bool] = None,
    days_ahead: Optional[int] = Query(None, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List milestones with optional filters."""
    org_id = _get_org(current_user)
    where = ["organization_id = :org_id"]
    params: Dict[str, Any] = {"org_id": org_id, "limit": limit, "offset": offset}

    if candidate_id:
        where.append("candidate_id = :candidate_id")
        params["candidate_id"] = candidate_id
    if milestone_type:
        where.append("milestone_type = :milestone_type")
        params["milestone_type"] = milestone_type
    if completed is True:
        where.append("completed_at IS NOT NULL")
    elif completed is False:
        where.append("completed_at IS NULL")
    if days_ahead:
        cutoff = datetime.now(timezone.utc) + timedelta(days=days_ahead)
        where.append("scheduled_date <= :cutoff AND completed_at IS NULL")
        params["cutoff"] = cutoff

    where_sql = " AND ".join(where)
    rows = db.execute(text(f"""
        SELECT id, candidate_id, milestone_type, scheduled_date,
               completed_at, assigned_to_user_id, notes, created_at
        FROM recruit_milestones
        WHERE {where_sql}
        ORDER BY scheduled_date ASC NULLS LAST
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    total = db.execute(text(f"SELECT COUNT(*) FROM recruit_milestones WHERE {where_sql}"),
                       {k: v for k, v in params.items() if k not in ("limit", "offset")}).scalar()

    return {
        "milestones": [
            {
                "id": r.id,
                "candidate_id": r.candidate_id,
                "milestone_type": r.milestone_type,
                "scheduled_date": r.scheduled_date.isoformat() if r.scheduled_date else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "assigned_to_user_id": r.assigned_to_user_id,
                "notes": r.notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "is_overdue": (
                    r.completed_at is None
                    and r.scheduled_date is not None
                    and r.scheduled_date < datetime.now(timezone.utc)
                ),
            }
            for r in rows
        ],
        "total": total,
    }


@router.get("/upcoming")
async def upcoming_milestones(
    days: int = Query(14, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get milestones due in the next N days, grouped by urgency."""
    org_id = _get_org(current_user)
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)

    rows = db.execute(text("""
        SELECT m.id, m.candidate_id, m.milestone_type, m.scheduled_date,
               m.assigned_to_user_id, m.notes,
               c.first_name || ' ' || c.last_name AS candidate_name
        FROM recruit_milestones m
        LEFT JOIN mm_candidates c ON c.id = m.candidate_id
        WHERE m.organization_id = :org_id
          AND m.completed_at IS NULL
          AND (m.scheduled_date <= :cutoff OR m.scheduled_date IS NULL)
        ORDER BY m.scheduled_date ASC NULLS LAST
    """), {"org_id": org_id, "cutoff": cutoff}).fetchall()

    overdue, this_week, later = [], [], []
    week_cutoff = now + timedelta(days=7)

    for r in rows:
        item = {
            "id": r.id,
            "candidate_id": r.candidate_id,
            "candidate_name": r.candidate_name,
            "milestone_type": r.milestone_type,
            "scheduled_date": r.scheduled_date.isoformat() if r.scheduled_date else None,
            "assigned_to_user_id": r.assigned_to_user_id,
            "notes": r.notes,
        }
        if r.scheduled_date and r.scheduled_date < now:
            overdue.append(item)
        elif r.scheduled_date and r.scheduled_date <= week_cutoff:
            this_week.append(item)
        else:
            later.append(item)

    return {"overdue": overdue, "this_week": this_week, "later": later}


@router.post("")
async def create_milestone(
    data: MilestoneCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new milestone."""
    org_id = _get_org(current_user)
    result = db.execute(text("""
        INSERT INTO recruit_milestones (
            organization_id, candidate_id, milestone_type,
            scheduled_date, assigned_to_user_id, notes, created_at, updated_at
        ) VALUES (
            :org_id, :candidate_id, :mtype,
            :date, :assignee, :notes, NOW(), NOW()
        ) RETURNING id
    """), {
        "org_id": org_id,
        "candidate_id": data.candidate_id,
        "mtype": data.milestone_type.value,
        "date": data.scheduled_date,
        "assignee": data.assigned_to_user_id,
        "notes": data.notes,
    }).fetchone()
    db.commit()
    return {"id": result.id, "created": True}


@router.patch("/{milestone_id}")
async def update_milestone(
    milestone_id: int,
    data: MilestoneUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update milestone date, assignee, or notes."""
    org_id = _get_org(current_user)
    updates: Dict[str, Any] = {}
    if data.scheduled_date is not None:
        updates["scheduled_date"] = data.scheduled_date
    if data.assigned_to_user_id is not None:
        updates["assigned_to_user_id"] = data.assigned_to_user_id
    if data.notes is not None:
        updates["notes"] = data.notes

    if not updates:
        return {"id": milestone_id, "updated": False}

    set_sql = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = milestone_id
    updates["org_id"] = org_id
    result = db.execute(text(f"""
        UPDATE recruit_milestones SET {set_sql}, updated_at = NOW()
        WHERE id = :id AND organization_id = :org_id
        RETURNING id
    """), updates).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Milestone not found")

    db.commit()
    return {"id": milestone_id, "updated": True}


@router.post("/{milestone_id}/complete")
async def complete_milestone(
    milestone_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a milestone as complete."""
    org_id = _get_org(current_user)
    result = db.execute(text("""
        UPDATE recruit_milestones
        SET completed_at = NOW(), updated_at = NOW()
        WHERE id = :id AND organization_id = :org_id AND completed_at IS NULL
        RETURNING id
    """), {"id": milestone_id, "org_id": org_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Milestone not found or already completed")

    db.commit()
    return {"id": milestone_id, "completed": True}
