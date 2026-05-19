"""
Calendar Export Routes - ICS download and PDF schedule generation.

Provides endpoints for exporting scheduler appointments as ICS files
(for import into any calendar application) and as printable PDF/HTML
schedules.

URL prefix: /api/v1/scheduler/export  (applied by this router)
Parent aggregator: smart_scheduler_routes.py includes this router.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from typing import Optional
from io import BytesIO
import logging

from db import get_db
from services.calendar_export import CalendarExportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export", tags=["calendar-export"])

# =============================================================================
# Dependency injection (same pattern as sibling scheduler modules)
# =============================================================================

_get_db = None
_get_current_user_func = None
_models = None


def set_dependencies(get_db_func, get_current_user_func, models_dict):
    """Called by smart_scheduler_routes to inject dependencies."""
    global _get_db, _get_current_user_func, _models
    _get_db = get_db_func
    _get_current_user_func = get_current_user_func
    _models = models_dict


from auth.dependencies import get_current_user  # dedup: was local wrapper
def _get_org_id(user) -> int:
    org_id = getattr(user, "organization_id", None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def _parse_date(date_str: str, param_name: str) -> date:
    """Parse a YYYY-MM-DD date string, raising 400 on failure."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {param_name} format. Expected YYYY-MM-DD, got: {date_str}",
        )


def _query_appointments(db: Session, org_id: int, start_date: date, end_date: date, user_id: Optional[int] = None):
    """Query appointments within a date range, scoped by org and optionally user."""
    Appointment = _models.get("Appointment")
    if Appointment is None:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    query = db.query(Appointment).filter(
        Appointment.organization_id == org_id,
        Appointment.scheduled_start >= start_dt,
        Appointment.scheduled_start <= end_dt,
        Appointment.status.notin_(["cancelled"]),
    )

    if user_id is not None:
        query = query.filter(Appointment.assigned_user_id == user_id)

    return query.order_by(Appointment.scheduled_start.asc()).all()


# =============================================================================
# ICS export endpoints
# =============================================================================

@router.get("/ics")
async def export_ics(
    request: Request,
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    user_id: Optional[int] = Query(None, description="Filter by assigned user ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Export appointments as an ICS file for calendar app import.

    Returns a downloadable .ics file containing all appointments in the
    specified date range.  If ``user_id`` is not provided, defaults to
    the current user's appointments.
    """
    org_id = _get_org_id(current_user)
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")

    if start > end:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")

    # Default to current user if no user_id specified
    target_user_id = user_id if user_id is not None else getattr(current_user, "id", None)

    appointments = _query_appointments(db, org_id, start, end, target_user_id)

    user_name = f"{getattr(current_user, 'first_name', '')} {getattr(current_user, 'last_name', '')}".strip()
    calendar_name = f"Perennia Schedule - {user_name}" if user_name else "Perennia Schedule"

    ics_content = CalendarExportService.generate_ics(appointments, calendar_name=calendar_name)

    filename = f"schedule_{start_date}_{end_date}.ics"

    try:
        from utils.export_audit import log_export_event, _get_client_ip
        log_export_event(
            db=db, user_id=getattr(current_user, "id", 0),
            organization_id=org_id, resource_type="schedule",
            export_format="ics", ip_address=_get_client_ip(request),
            details={"start_date": start_date, "end_date": end_date, "appointment_count": len(appointments)},
        )
    except Exception as _exc:  # noqa: BLE001
        pass

    return StreamingResponse(
        iter([ics_content.encode("utf-8")]),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ics/{appointment_id}")
async def export_single_ics(
    request: Request,
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Export a single appointment as an ICS file.

    Useful for attaching to emails or adding a single event to a calendar.
    """
    org_id = _get_org_id(current_user)
    Appointment = _models.get("Appointment")
    if Appointment is None:
        raise HTTPException(status_code=503, detail="Scheduler models not available")

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id,
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    ics_content = CalendarExportService.generate_ics_single(appointment)

    safe_title = (appointment.title or "appointment").replace(" ", "_")[:50]
    filename = f"{safe_title}_{appointment_id}.ics"

    try:
        from utils.export_audit import log_export_event, _get_client_ip
        log_export_event(
            db=db, user_id=getattr(current_user, "id", 0),
            organization_id=org_id, resource_type="appointment",
            export_format="ics", ip_address=_get_client_ip(request),
            details={"appointment_id": appointment_id},
        )
    except Exception as _exc:  # noqa: BLE001
        pass

    return StreamingResponse(
        iter([ics_content.encode("utf-8")]),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# =============================================================================
# PDF / HTML schedule export
# =============================================================================

@router.get("/pdf")
async def export_pdf(
    request: Request,
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    user_id: Optional[int] = Query(None, description="Filter by assigned user ID"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Export schedule as a printable PDF (or HTML fallback).

    Generates a professionally styled schedule document suitable for
    printing or sharing.  Returns PDF if weasyprint is installed,
    otherwise returns styled HTML that browsers can print natively.
    """
    org_id = _get_org_id(current_user)
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")

    if start > end:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")

    target_user_id = user_id if user_id is not None else getattr(current_user, "id", None)

    appointments = _query_appointments(db, org_id, start, end, target_user_id)

    user_name = f"{getattr(current_user, 'first_name', '')} {getattr(current_user, 'last_name', '')}".strip() or "User"

    # Get org name if available
    org_name = getattr(current_user, "organization_name", "") or ""

    pdf_bytes = CalendarExportService.generate_pdf_schedule(
        appointments=appointments,
        user_name=user_name,
        date_range=(start, end),
        org_name=org_name,
    )

    content_type = CalendarExportService.pdf_content_type()
    extension = CalendarExportService.pdf_file_extension()
    filename = f"schedule_{start_date}_{end_date}.{extension}"

    try:
        from utils.export_audit import log_export_event, _get_client_ip
        log_export_event(
            db=db, user_id=getattr(current_user, "id", 0),
            organization_id=org_id, resource_type="schedule",
            export_format="pdf", ip_address=_get_client_ip(request),
            details={"start_date": start_date, "end_date": end_date, "appointment_count": len(appointments)},
        )
    except Exception as _exc:  # noqa: BLE001
        pass

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
