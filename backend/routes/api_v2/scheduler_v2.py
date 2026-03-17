"""
V2 Scheduler / Calendar Appointment Endpoints - Perennia AI

Mirrors the V1 scheduler appointment routes with V2 API conventions:
- Cursor-based pagination on list endpoints
- Sparse fieldsets (``?fields=id,title,start_time``)
- Related resource inclusion (``?include=attendees,meeting``)
- ISO 8601 datetimes with mandatory timezone offsets
- RFC 7807 Problem Details for all errors
- Consistent ``V2Envelope`` response wrapper

URL prefix: ``/api/v2/scheduler/`` (applied by parent ``api_v2/__init__.py``)

Version Negotiation
-------------------
These endpoints respond to:
- ``GET /api/v2/scheduler/appointments``
- ``Accept: application/vnd.perennia.v2+json`` on any scheduler URL
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from schemas.api_v2 import (
    APPOINTMENT_FIELDS,
    CursorInfo,
    CursorPage,
    ProblemDetail,
    V2AppointmentAttendee,
    V2AppointmentCreateRequest,
    V2AppointmentResponse,
    V2AppointmentUpdateRequest,
    V2Envelope,
    V2MeetingInfo,
    V2Meta,
    apply_sparse_fields,
    decode_cursor,
    encode_cursor,
    validate_sparse_fields,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["V2 Scheduler"])


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

_get_db = None
_get_current_user = None
_Appointment = None
_SchedulerConfig = None


def set_dependencies(get_db_func, get_current_user_func, models: dict):
    """Inject dependencies after import time to avoid circular imports.

    Called from main.py or the route registration code.  ``models`` dict
    should contain:
    - ``Appointment``: The SQLAlchemy Appointment model class
    - ``SchedulerConfig``: The SQLAlchemy SchedulerConfig model class
    """
    global _get_db, _get_current_user, _Appointment, _SchedulerConfig
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _Appointment = models.get("Appointment")
    _SchedulerConfig = models.get("SchedulerConfig")


def _db():
    """Get a database session or raise if dependencies not injected."""
    if _get_db is None:
        raise RuntimeError("V2 scheduler dependencies not initialized. Call set_dependencies() first.")
    return Depends(_get_db)


def _current_user():
    """Get current user or raise if dependencies not injected."""
    if _get_current_user is None:
        raise RuntimeError("V2 scheduler dependencies not initialized. Call set_dependencies() first.")
    return Depends(_get_current_user)


# =============================================================================
# HELPERS
# =============================================================================

def _problem_response(problem: ProblemDetail) -> JSONResponse:
    """Build a JSONResponse from a ProblemDetail."""
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(exclude_none=True),
        headers={"Content-Type": "application/problem+json"},
    )


def _format_datetime(dt) -> Optional[str]:
    """Format a datetime as ISO 8601 with timezone.

    Naive datetimes are assumed UTC.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _appointment_to_dict(appt) -> Dict[str, Any]:
    """Convert a SQLAlchemy Appointment to a plain dict with V2 formatting."""
    return {
        "id": appt.id,
        "uuid": getattr(appt, "uuid", None),
        "title": getattr(appt, "title", ""),
        "description": getattr(appt, "description", None),
        "status": getattr(appt, "status", None),
        "meeting_type": getattr(appt, "meeting_type", None),
        "meeting_mode": getattr(appt, "meeting_mode", None),
        "scheduled_start": _format_datetime(getattr(appt, "scheduled_start", None)),
        "scheduled_end": _format_datetime(getattr(appt, "scheduled_end", None)),
        "duration_minutes": getattr(appt, "duration_minutes", None),
        "timezone": getattr(appt, "timezone", None),
        "attendee_name": getattr(appt, "attendee_name", None),
        "attendee_email": getattr(appt, "attendee_email", None),
        "attendee_phone": getattr(appt, "attendee_phone", None),
        "attendee_notes": getattr(appt, "attendee_notes", None),
        "lead_id": getattr(appt, "lead_id", None),
        "loan_id": getattr(appt, "loan_id", None),
        "contact_id": getattr(appt, "contact_id", None),
        "assigned_user_id": getattr(appt, "assigned_user_id", None),
        "location": getattr(appt, "location", None),
        "video_link": getattr(appt, "video_link", None),
        "cancellation_reason": getattr(appt, "cancellation_reason", None),
        "internal_notes": getattr(appt, "internal_notes", None),
        "meeting_notes": getattr(appt, "meeting_notes", None),
        "booked_by_ai": getattr(appt, "booked_by_ai", False),
        "no_show_risk_score": getattr(appt, "no_show_risk_score", None),
        "created_at": _format_datetime(getattr(appt, "created_at", None)),
        "updated_at": _format_datetime(getattr(appt, "updated_at", None)),
    }


def _build_included(appt, include_set: set) -> Optional[Dict[str, List[Dict]]]:
    """Build the ``included`` sideloads from ?include= param."""
    if not include_set:
        return None

    included: Dict[str, List[Dict]] = {}

    if "attendees" in include_set:
        attendee = {
            "id": getattr(appt, "id", None),
            "name": getattr(appt, "attendee_name", None),
            "email": getattr(appt, "attendee_email", None),
            "phone": getattr(appt, "attendee_phone", None),
            "role": "attendee",
        }
        if attendee["name"] or attendee["email"]:
            included["attendees"] = [attendee]
        else:
            included["attendees"] = []

    if "meeting" in include_set:
        meeting_info = {
            "video_link": getattr(appt, "video_link", None),
            "location": getattr(appt, "location", None),
            "meeting_mode": getattr(appt, "meeting_mode", None),
            "duration_minutes": getattr(appt, "duration_minutes", None),
        }
        included["meeting"] = [meeting_info]

    return included if included else None


def _parse_include(include_param: Optional[str]) -> set:
    """Parse the ?include= query parameter into a set of resource names."""
    if not include_param:
        return set()
    valid_includes = {"attendees", "meeting"}
    requested = {s.strip() for s in include_param.split(",") if s.strip()}
    invalid = requested - valid_includes
    if invalid:
        raise ValueError(
            f"Unknown include resources: {', '.join(sorted(invalid))}. "
            f"Allowed: {', '.join(sorted(valid_includes))}"
        )
    return requested


# =============================================================================
# ROUTES
# =============================================================================

@router.get(
    "/appointments",
    summary="List appointments (V2 - cursor pagination)",
    response_description="Paginated list of appointments in V2 envelope",
)
async def list_appointments_v2(
    request: Request,
    cursor: Optional[str] = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    status: Optional[str] = Query(None, description="Filter by status"),
    fields: Optional[str] = Query(None, description="Sparse fieldset (e.g. id,title,start_time)"),
    include: Optional[str] = Query(None, description="Include related resources (attendees,meeting)"),
):
    """List appointments with cursor-based pagination.

    Version Negotiation
    -------------------
    This is a V2-only endpoint.  V1 clients should use
    ``GET /api/v1/scheduler/appointments`` with offset pagination.

    Cursor Pagination
    -----------------
    - First request: omit ``cursor``
    - Next page: pass ``cursor=<value from response.cursor.next>``
    - Previous page: pass ``cursor=<value from response.cursor.prev>``

    Sparse Fieldsets
    ----------------
    Use ``?fields=id,title,scheduled_start`` to receive only the
    requested fields (``id`` is always included).

    Related Resources
    -----------------
    Use ``?include=attendees,meeting`` to sideload related data in
    the ``included`` key.
    """
    if _Appointment is None:
        return _problem_response(ProblemDetail.internal_error(
            "Scheduler dependencies not initialized"
        ))

    # Validate sparse fields
    try:
        field_set = validate_sparse_fields(fields)
    except ValueError as exc:
        return _problem_response(ProblemDetail.bad_request(str(exc)))

    # Validate include param
    try:
        include_set = _parse_include(include)
    except ValueError as exc:
        return _problem_response(ProblemDetail.bad_request(str(exc)))

    # Resolve cursor
    cursor_id = None
    if cursor:
        try:
            cursor_data = decode_cursor(cursor)
            cursor_id = cursor_data.get("id")
        except ValueError as exc:
            return _problem_response(ProblemDetail.bad_request(f"Invalid cursor: {exc}"))

    # Build query
    db: Session = next(_get_db())
    try:
        query = db.query(_Appointment)

        # Tenant isolation: filter by user's organization if available
        user = None
        if _get_current_user is not None:
            try:
                user = await _get_current_user(request)
                if hasattr(user, "organization_id") and user.organization_id:
                    query = query.filter(
                        _Appointment.organization_id == user.organization_id
                    )
            except Exception:
                pass  # Public or unauthenticated context

        if status:
            query = query.filter(_Appointment.status == status)

        # Cursor-based pagination: fetch items after the cursor ID
        if cursor_id is not None:
            query = query.filter(_Appointment.id > cursor_id)

        query = query.order_by(_Appointment.id.asc())

        # Fetch limit+1 to detect has_more
        appointments = query.limit(limit + 1).all()
        has_more = len(appointments) > limit
        if has_more:
            appointments = appointments[:limit]

        # Build response
        items = []
        for appt in appointments:
            item_dict = _appointment_to_dict(appt)
            item_dict = apply_sparse_fields(item_dict, field_set)
            items.append(item_dict)

        # Build cursor info
        next_cursor = None
        prev_cursor = None
        if has_more and appointments:
            next_cursor = encode_cursor({"id": appointments[-1].id})
        if cursor_id is not None and appointments:
            prev_cursor = encode_cursor({"id": appointments[0].id, "direction": "prev"})

        # Build included resources (from first item as representative)
        page_included = None
        if include_set and appointments:
            page_included = {}
            for appt in appointments:
                inc = _build_included(appt, include_set)
                if inc:
                    for key, val in inc.items():
                        page_included.setdefault(key, []).extend(val)

        page = CursorPage(
            data=items,
            cursor=CursorInfo(next=next_cursor, prev=prev_cursor),
            has_more=has_more,
        )

        return V2Envelope(
            data=page.model_dump(),
            meta=V2Meta(api_version="2.0"),
            included=page_included,
        ).model_dump(exclude_none=True)

    except Exception as exc:
        logger.exception("V2 list_appointments failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()


@router.get(
    "/appointments/{appointment_id}",
    summary="Get appointment by ID (V2)",
    response_description="Single appointment in V2 envelope",
)
async def get_appointment_v2(
    request: Request,
    appointment_id: int,
    fields: Optional[str] = Query(None, description="Sparse fieldset"),
    include: Optional[str] = Query(None, description="Include related resources"),
):
    """Get a single appointment by ID.

    Version Negotiation
    -------------------
    V2 endpoint.  Returns ISO 8601 datetimes with timezone and
    consistent error format.

    Sparse Fieldsets
    ----------------
    Use ``?fields=id,title`` to limit returned fields.

    Related Resources
    -----------------
    Use ``?include=attendees,meeting`` to sideload related data.
    """
    if _Appointment is None:
        return _problem_response(ProblemDetail.internal_error(
            "Scheduler dependencies not initialized"
        ))

    try:
        field_set = validate_sparse_fields(fields)
    except ValueError as exc:
        return _problem_response(ProblemDetail.bad_request(str(exc)))

    try:
        include_set = _parse_include(include)
    except ValueError as exc:
        return _problem_response(ProblemDetail.bad_request(str(exc)))

    db: Session = next(_get_db())
    try:
        appt = db.query(_Appointment).filter(_Appointment.id == appointment_id).first()
        if not appt:
            return _problem_response(ProblemDetail.not_found(
                f"Appointment with id '{appointment_id}' not found",
                instance=f"/api/v2/scheduler/appointments/{appointment_id}",
            ))

        item_dict = _appointment_to_dict(appt)
        item_dict = apply_sparse_fields(item_dict, field_set)

        included = _build_included(appt, include_set)

        return V2Envelope(
            data=item_dict,
            meta=V2Meta(api_version="2.0"),
            included=included,
        ).model_dump(exclude_none=True)

    except Exception as exc:
        logger.exception("V2 get_appointment failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()


@router.post(
    "/appointments",
    summary="Create appointment (V2)",
    status_code=201,
    response_description="Created appointment in V2 envelope",
)
async def create_appointment_v2(
    request: Request,
    body: V2AppointmentCreateRequest,
):
    """Create a new appointment.

    Version Negotiation
    -------------------
    V2 endpoint.  Requires ISO 8601 datetime with timezone offset
    for ``scheduled_start``.  Returns RFC 7807 errors on validation
    failure.
    """
    if _Appointment is None:
        return _problem_response(ProblemDetail.internal_error(
            "Scheduler dependencies not initialized"
        ))

    db: Session = next(_get_db())
    try:
        # Parse the scheduled start
        start_dt = datetime.fromisoformat(body.scheduled_start)
        from datetime import timedelta
        end_dt = start_dt + timedelta(minutes=body.duration_minutes)

        appt = _Appointment(
            title=body.title,
            description=body.description,
            meeting_type=body.meeting_type,
            meeting_mode=body.meeting_mode,
            scheduled_start=start_dt,
            scheduled_end=end_dt,
            duration_minutes=body.duration_minutes,
            timezone=body.timezone,
            attendee_name=body.attendee_name,
            attendee_email=body.attendee_email,
            attendee_phone=body.attendee_phone,
            attendee_notes=body.attendee_notes,
            lead_id=body.lead_id,
            loan_id=body.loan_id,
            contact_id=body.contact_id,
            assigned_user_id=body.assigned_user_id,
            booked_by_ai=body.booked_by_ai,
            status="booked",
        )

        # Set appointment_type_id if provided
        if body.appointment_type_id is not None:
            appt.appointment_type_id = body.appointment_type_id

        # Set organization from current user if available
        try:
            user = await _get_current_user(request)
            if hasattr(user, "organization_id"):
                appt.organization_id = user.organization_id
            if hasattr(user, "id"):
                appt.user_id = user.id
        except Exception:
            pass

        db.add(appt)
        db.commit()
        db.refresh(appt)

        item_dict = _appointment_to_dict(appt)

        return JSONResponse(
            status_code=201,
            content=V2Envelope(
                data=item_dict,
                meta=V2Meta(api_version="2.0"),
            ).model_dump(exclude_none=True),
        )

    except Exception as exc:
        db.rollback()
        logger.exception("V2 create_appointment failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()


@router.patch(
    "/appointments/{appointment_id}",
    summary="Update appointment (V2)",
    response_description="Updated appointment in V2 envelope",
)
async def update_appointment_v2(
    request: Request,
    appointment_id: int,
    body: V2AppointmentUpdateRequest,
):
    """Partially update an appointment.

    Version Negotiation
    -------------------
    V2 endpoint.  Uses PATCH semantics: only provided fields are
    updated.  Returns RFC 7807 errors.
    """
    if _Appointment is None:
        return _problem_response(ProblemDetail.internal_error(
            "Scheduler dependencies not initialized"
        ))

    db: Session = next(_get_db())
    try:
        appt = db.query(_Appointment).filter(_Appointment.id == appointment_id).first()
        if not appt:
            return _problem_response(ProblemDetail.not_found(
                f"Appointment with id '{appointment_id}' not found",
                instance=f"/api/v2/scheduler/appointments/{appointment_id}",
            ))

        update_data = body.model_dump(exclude_unset=True)

        # Handle scheduled_start -> scheduled_end recalculation
        if "scheduled_start" in update_data and update_data["scheduled_start"]:
            start_dt = datetime.fromisoformat(update_data["scheduled_start"])
            update_data["scheduled_start"] = start_dt
            duration = update_data.get("duration_minutes") or appt.duration_minutes or 30
            from datetime import timedelta
            update_data["scheduled_end"] = start_dt + timedelta(minutes=duration)

        for key, value in update_data.items():
            if hasattr(appt, key):
                setattr(appt, key, value)

        db.commit()
        db.refresh(appt)

        item_dict = _appointment_to_dict(appt)

        return V2Envelope(
            data=item_dict,
            meta=V2Meta(api_version="2.0"),
        ).model_dump(exclude_none=True)

    except Exception as exc:
        db.rollback()
        logger.exception("V2 update_appointment failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()


@router.delete(
    "/appointments/{appointment_id}",
    summary="Cancel appointment (V2)",
    response_description="Cancellation confirmation in V2 envelope",
)
async def cancel_appointment_v2(
    request: Request,
    appointment_id: int,
    reason: Optional[str] = Query(None, description="Cancellation reason"),
):
    """Cancel an appointment by setting status to 'cancelled'.

    Version Negotiation
    -------------------
    V2 endpoint.  Does not hard-delete; sets status to ``cancelled``
    and records the cancellation reason.
    """
    if _Appointment is None:
        return _problem_response(ProblemDetail.internal_error(
            "Scheduler dependencies not initialized"
        ))

    db: Session = next(_get_db())
    try:
        appt = db.query(_Appointment).filter(_Appointment.id == appointment_id).first()
        if not appt:
            return _problem_response(ProblemDetail.not_found(
                f"Appointment with id '{appointment_id}' not found",
                instance=f"/api/v2/scheduler/appointments/{appointment_id}",
            ))

        appt.status = "cancelled"
        if reason:
            appt.cancellation_reason = reason

        db.commit()

        return V2Envelope(
            data={
                "id": appointment_id,
                "status": "cancelled",
                "cancellation_reason": reason,
            },
            meta=V2Meta(api_version="2.0"),
        ).model_dump(exclude_none=True)

    except Exception as exc:
        db.rollback()
        logger.exception("V2 cancel_appointment failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()


@router.get(
    "/appointments/search",
    summary="Search appointments (V2 - cursor pagination)",
    response_description="Search results with cursor pagination",
)
async def search_appointments_v2(
    request: Request,
    q: Optional[str] = Query(None, description="Search query (title, attendee name)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    meeting_type: Optional[str] = Query(None, description="Filter by meeting type"),
    start_after: Optional[str] = Query(None, description="ISO 8601 datetime lower bound"),
    start_before: Optional[str] = Query(None, description="ISO 8601 datetime upper bound"),
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(20, ge=1, le=100),
    fields: Optional[str] = Query(None, description="Sparse fieldset"),
    include: Optional[str] = Query(None, description="Include related resources"),
):
    """Search appointments with flexible filters and cursor pagination.

    Version Negotiation
    -------------------
    V2-only search endpoint with consistent filter parameters and
    cursor pagination.
    """
    if _Appointment is None:
        return _problem_response(ProblemDetail.internal_error(
            "Scheduler dependencies not initialized"
        ))

    try:
        field_set = validate_sparse_fields(fields)
    except ValueError as exc:
        return _problem_response(ProblemDetail.bad_request(str(exc)))

    try:
        include_set = _parse_include(include)
    except ValueError as exc:
        return _problem_response(ProblemDetail.bad_request(str(exc)))

    cursor_id = None
    if cursor:
        try:
            cursor_data = decode_cursor(cursor)
            cursor_id = cursor_data.get("id")
        except ValueError as exc:
            return _problem_response(ProblemDetail.bad_request(f"Invalid cursor: {exc}"))

    db: Session = next(_get_db())
    try:
        query = db.query(_Appointment)

        if q:
            search_term = f"%{q}%"
            query = query.filter(
                (_Appointment.title.ilike(search_term))
                | (_Appointment.attendee_name.ilike(search_term))
            )

        if status:
            query = query.filter(_Appointment.status == status)

        if meeting_type:
            query = query.filter(_Appointment.meeting_type == meeting_type)

        if start_after:
            try:
                after_dt = datetime.fromisoformat(start_after)
                query = query.filter(_Appointment.scheduled_start >= after_dt)
            except ValueError:
                return _problem_response(ProblemDetail.bad_request(
                    f"Invalid start_after datetime: {start_after}"
                ))

        if start_before:
            try:
                before_dt = datetime.fromisoformat(start_before)
                query = query.filter(_Appointment.scheduled_start <= before_dt)
            except ValueError:
                return _problem_response(ProblemDetail.bad_request(
                    f"Invalid start_before datetime: {start_before}"
                ))

        if cursor_id is not None:
            query = query.filter(_Appointment.id > cursor_id)

        query = query.order_by(_Appointment.id.asc())
        appointments = query.limit(limit + 1).all()

        has_more = len(appointments) > limit
        if has_more:
            appointments = appointments[:limit]

        items = []
        for appt in appointments:
            item_dict = _appointment_to_dict(appt)
            item_dict = apply_sparse_fields(item_dict, field_set)
            items.append(item_dict)

        next_cursor = None
        prev_cursor = None
        if has_more and appointments:
            next_cursor = encode_cursor({"id": appointments[-1].id})
        if cursor_id is not None and appointments:
            prev_cursor = encode_cursor({"id": appointments[0].id, "direction": "prev"})

        page = CursorPage(
            data=items,
            cursor=CursorInfo(next=next_cursor, prev=prev_cursor),
            has_more=has_more,
        )

        return V2Envelope(
            data=page.model_dump(),
            meta=V2Meta(api_version="2.0"),
        ).model_dump(exclude_none=True)

    except Exception as exc:
        logger.exception("V2 search_appointments failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()
