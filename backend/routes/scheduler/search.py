"""
Scheduler Search - Advanced appointment search with full-text, filters, pagination.

Endpoints:
  - GET /search                  Advanced appointment search
  - GET /search/suggestions      Typeahead suggestions for search input
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func, cast, String, desc, asc
from datetime import datetime, date, time, timezone
from typing import List, Optional
from math import ceil
import logging

from smart_scheduler_models import AppointmentStatus
from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id, _is_scheduler_admin,
)
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# SEARCH HELPERS
# ============================================================================

def _serialize_appointment(a) -> dict:
    """Serialize an Appointment model instance to a dict for API response."""
    return {
        "id": a.id,
        "title": a.title,
        "description": a.description,
        "meeting_type": a.meeting_type.value if a.meeting_type else None,
        "meeting_mode": a.meeting_mode.value if a.meeting_mode else None,
        "scheduled_start": a.scheduled_start.isoformat() if a.scheduled_start else None,
        "scheduled_end": a.scheduled_end.isoformat() if a.scheduled_end else None,
        "duration_minutes": a.duration_minutes,
        "timezone": a.timezone,
        "status": a.status.value if a.status else None,
        "attendee_name": a.attendee_name,
        "attendee_email": a.attendee_email,
        "attendee_phone": a.attendee_phone,
        "attendee_notes": a.attendee_notes,
        "location": a.location,
        "video_link": a.video_link,
        "lead_id": a.lead_id,
        "loan_id": a.loan_id,
        "contact_id": a.contact_id,
        "assigned_user_id": a.assigned_user_id,
        "appointment_type_id": a.appointment_type_id,
        "booked_by_ai": a.booked_by_ai,
        "internal_notes": a.internal_notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def _apply_text_search(query, Appointment, search_text: str):
    """Apply ILIKE free-text search across multiple columns."""
    pattern = f"%{search_text}%"
    return query.filter(
        or_(
            Appointment.title.ilike(pattern),
            Appointment.attendee_name.ilike(pattern),
            Appointment.attendee_email.ilike(pattern),
            Appointment.description.ilike(pattern),
            Appointment.internal_notes.ilike(pattern),
            Appointment.meeting_notes.ilike(pattern),
            Appointment.attendee_notes.ilike(pattern),
            Appointment.location.ilike(pattern),
        )
    )


def _apply_status_filter(query, Appointment, statuses: List[str]):
    """Apply status filter, validating each status value."""
    valid_statuses = []
    for s in statuses:
        try:
            valid_statuses.append(AppointmentStatus(s.lower()))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status filter: '{s}'. Valid values: {[e.value for e in AppointmentStatus]}"
            )
    if len(valid_statuses) == 1:
        return query.filter(Appointment.status == valid_statuses[0])
    return query.filter(Appointment.status.in_(valid_statuses))


def _apply_date_range(query, Appointment, date_from: Optional[str], date_to: Optional[str]):
    """Apply date range filter on scheduled_start."""
    if date_from:
        try:
            from_date = date.fromisoformat(date_from)
            query = query.filter(
                Appointment.scheduled_start >= datetime.combine(from_date, time.min)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date_from format: '{date_from}'. Use YYYY-MM-DD.")
    if date_to:
        try:
            to_date = date.fromisoformat(date_to)
            query = query.filter(
                Appointment.scheduled_start <= datetime.combine(to_date, time(23, 59, 59))
            )
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date_to format: '{date_to}'. Use YYYY-MM-DD.")
    return query


ALLOWED_SORT_FIELDS = {
    "scheduled_start",
    "created_at",
    "status",
    "attendee_name",
    "updated_at",
    "title",
}


def _apply_sorting(query, Appointment, sort_by: str, sort_order: str):
    """Apply sorting to the query."""
    if sort_by not in ALLOWED_SORT_FIELDS:
        sort_by = "scheduled_start"
    sort_order = sort_order.lower()
    if sort_order not in ("asc", "desc"):
        sort_order = "asc"

    column = getattr(Appointment, sort_by, Appointment.scheduled_start)

    # Use the column's .desc()/.asc() methods if available (SQLAlchemy columns),
    # otherwise fall back to module-level desc()/asc() wrappers.
    try:
        if sort_order == "desc":
            query = query.order_by(column.desc())
        else:
            query = query.order_by(column.asc())
    except (AttributeError, TypeError):
        if sort_order == "desc":
            query = query.order_by(desc(column))
        else:
            query = query.order_by(asc(column))
    return query


# ============================================================================
# SEARCH ENDPOINT
# ============================================================================

@router.get("/search")
async def search_appointments(
    request: Request,
    q: Optional[str] = Query(None, description="Free text search (name, email, title, notes)"),
    status: Optional[List[str]] = Query(None, description="Filter by status(es)"),
    appointment_type_id: Optional[int] = Query(None, description="Filter by appointment type ID"),
    assigned_user_id: Optional[int] = Query(None, description="Filter by assigned user ID"),
    date_from: Optional[str] = Query(None, description="Start date filter (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date filter (YYYY-MM-DD)"),
    attendee_email: Optional[str] = Query(None, description="Filter by attendee email (exact match)"),
    meeting_type: Optional[str] = Query(None, description="Filter by meeting type"),
    lead_id: Optional[int] = Query(None, description="Filter by lead ID"),
    loan_id: Optional[int] = Query(None, description="Filter by loan ID"),
    booked_by_ai: Optional[bool] = Query(None, description="Filter by AI-booked flag"),
    sort_by: str = Query("scheduled_start", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Results per page"),
    db: Session = Depends(get_db),
):
    """Advanced appointment search with full-text, filters, and pagination.

    Supports free-text search across title, attendee name/email, description,
    notes, and location. Combine with status, date range, type, and user filters.
    Results are paginated with total count and page metadata.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    Appointment = _models['Appointment']

    # Base query: org-scoped
    query = db.query(Appointment).filter(
        Appointment.organization_id == org_id,
    )

    # RBAC visibility: admins see all org appointments, non-admins see own
    is_admin = _is_scheduler_admin(user)
    if not is_admin:
        query = query.filter(
            or_(
                Appointment.assigned_user_id == user.id,
                Appointment.created_by_user_id == user.id,
            )
        )

    # Apply free-text search
    if q and q.strip():
        query = _apply_text_search(query, Appointment, q.strip())

    # Apply status filter
    if status:
        query = _apply_status_filter(query, Appointment, status)

    # Apply appointment type filter
    if appointment_type_id is not None:
        query = query.filter(Appointment.appointment_type_id == appointment_type_id)

    # Apply assigned user filter
    if assigned_user_id is not None:
        query = query.filter(Appointment.assigned_user_id == assigned_user_id)

    # Apply date range filter
    query = _apply_date_range(query, Appointment, date_from, date_to)

    # Apply attendee email filter (exact, case-insensitive)
    if attendee_email:
        query = query.filter(
            func.lower(Appointment.attendee_email) == attendee_email.lower()
        )

    # Apply meeting type filter
    if meeting_type:
        query = query.filter(
            cast(Appointment.meeting_type, String) == meeting_type
        )

    # Apply lead_id / loan_id filters
    if lead_id is not None:
        query = query.filter(Appointment.lead_id == lead_id)
    if loan_id is not None:
        query = query.filter(Appointment.loan_id == loan_id)

    # Apply AI-booked filter
    if booked_by_ai is not None:
        query = query.filter(Appointment.booked_by_ai == booked_by_ai)

    # Get total count before pagination
    total = query.count()
    total_pages = ceil(total / page_size) if total > 0 else 1

    # Clamp page to valid range
    if page > total_pages:
        page = total_pages

    # Apply sorting
    query = _apply_sorting(query, Appointment, sort_by, sort_order)

    # Apply pagination
    offset = (page - 1) * page_size
    appointments = query.offset(offset).limit(page_size).all()

    return {
        "success": True,
        "data": [_serialize_appointment(a) for a in appointments],
        "meta": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
        "filters_applied": {
            "q": q,
            "status": status,
            "appointment_type_id": appointment_type_id,
            "assigned_user_id": assigned_user_id,
            "date_from": date_from,
            "date_to": date_to,
            "attendee_email": attendee_email,
            "meeting_type": meeting_type,
            "lead_id": lead_id,
            "loan_id": loan_id,
            "booked_by_ai": booked_by_ai,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    }


# ============================================================================
# SEARCH SUGGESTIONS (TYPEAHEAD)
# ============================================================================

@router.get("/search/suggestions")
async def search_suggestions(
    request: Request,
    q: str = Query(..., min_length=2, description="Search query for typeahead suggestions"),
    limit: int = Query(8, ge=1, le=20, description="Max number of suggestions"),
    db: Session = Depends(get_db),
):
    """Return typeahead suggestions for the search input.

    Searches attendee names and emails, returning distinct matches
    grouped by type (name, email, title). Results are limited and
    designed for fast typeahead display.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    Appointment = _models['Appointment']

    pattern = f"%{q.strip()}%"
    suggestions = []

    # Base filter: org-scoped + RBAC
    is_admin = _is_scheduler_admin(user)

    def _base_filter():
        filters = [Appointment.organization_id == org_id]
        if not is_admin:
            filters.append(
                or_(
                    Appointment.assigned_user_id == user.id,
                    Appointment.created_by_user_id == user.id,
                )
            )
        return filters

    # Search attendee names
    try:
        name_results = (
            db.query(Appointment.attendee_name)
            .filter(
                and_(
                    *_base_filter(),
                    Appointment.attendee_name.ilike(pattern),
                    Appointment.attendee_name.isnot(None),
                )
            )
            .distinct()
            .limit(limit)
            .all()
        )
        for row in name_results:
            if row[0]:
                suggestions.append({
                    "type": "attendee",
                    "value": row[0],
                    "label": row[0],
                })
    except Exception as e:
        logger.warning(f"Name suggestion query failed: {e}")

    # Search attendee emails
    remaining = limit - len(suggestions)
    if remaining > 0:
        try:
            email_results = (
                db.query(Appointment.attendee_email)
                .filter(
                    and_(
                        *_base_filter(),
                        Appointment.attendee_email.ilike(pattern),
                        Appointment.attendee_email.isnot(None),
                    )
                )
                .distinct()
                .limit(remaining)
                .all()
            )
            for row in email_results:
                if row[0]:
                    suggestions.append({
                        "type": "email",
                        "value": row[0],
                        "label": row[0],
                    })
        except Exception as e:
            logger.warning(f"Email suggestion query failed: {e}")

    # Search appointment titles
    remaining = limit - len(suggestions)
    if remaining > 0:
        try:
            title_results = (
                db.query(Appointment.title)
                .filter(
                    and_(
                        *_base_filter(),
                        Appointment.title.ilike(pattern),
                    )
                )
                .distinct()
                .limit(remaining)
                .all()
            )
            for row in title_results:
                if row[0]:
                    suggestions.append({
                        "type": "title",
                        "value": row[0],
                        "label": row[0],
                    })
        except Exception as e:
            logger.warning(f"Title suggestion query failed: {e}")

    return {
        "success": True,
        "suggestions": suggestions,
        "query": q,
    }
