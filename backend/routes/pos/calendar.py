"""Borrower-facing Smart Calendar routes.

Wraps the existing /api/v1/scheduler endpoints with PURL token auth and
loan-scoped LO resolution. The borrower cannot fetch availability for any LO
other than their own.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from database import get_db
from middleware.purl_auth import (
    PURLAuthContext,
    check_purl_rate_limit,
    require_purl_token,
    require_purl_write_scope,
)

from database.models.pos import POSApplication
from schemas.pos.calendar import (
    AssignedLOResponse,
    AvailableSlotsResponse,
    BookingCancelRequest,
    BookingCancelResponse,
    BookingRequest,
    BookingResponse,
    SlotHoldRequest,
    SlotHoldResponse,
    TimeSlot,
)
from services.pos._scheduler_bridge import NoBookingLinkError
from services.pos.calendar_service import (
    CalendarService,
    NoLoanOfficerAssignedError,
)
from services.pos.application_service import AuditContext

from ._helpers import (
    build_audit_context,
    full_name as _full_name_parts,
    resolve_application_for_borrower,
    resolve_application_for_borrower_write,
)


router = APIRouter(
    prefix="/api/v1/pos/calendar",
    tags=["POS - Calendar"],
    dependencies=[Depends(check_purl_rate_limit)],
)


def get_calendar_service() -> CalendarService:
    return CalendarService()


# ---------------------------------------------------------------------------
# Assigned LO lookup
# ---------------------------------------------------------------------------


@router.get(
    "/applications/{application_id}/assigned-lo",
    response_model=AssignedLOResponse,
    summary="Get the loan officer assigned to this application",
)
def get_assigned_lo(
    application: POSApplication = Depends(resolve_application_for_borrower),
    db: Session = Depends(get_db),
    service: CalendarService = Depends(get_calendar_service),
) -> AssignedLOResponse:
    try:
        lo = service.resolve_loan_officer(db, application)
    except NoLoanOfficerAssignedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    link = service.get_booking_link_for_lo(db, lo.id)
    return AssignedLOResponse(
        user_id=lo.id,
        name=_full_name(lo),
        nmls=getattr(lo, "nmls_id", None),
        title=getattr(lo, "title", None),
        avatar_url=getattr(lo, "avatar_url", None),
        booking_link_slug=link.slug if link else None,
    )


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


@router.get(
    "/applications/{application_id}/available-slots",
    response_model=AvailableSlotsResponse,
    summary="List available slots for the borrower's assigned loan officer",
)
async def get_available_slots(
    start_date: datetime = Query(..., description="ISO date (YYYY-MM-DD)"),
    end_date: datetime = Query(..., description="ISO date (YYYY-MM-DD)"),
    duration_minutes: int = Query(30, ge=15, le=240),
    timezone_str: str = Query("America/New_York", alias="timezone"),
    application: POSApplication = Depends(resolve_application_for_borrower),
    db: Session = Depends(get_db),
    service: CalendarService = Depends(get_calendar_service),
) -> AvailableSlotsResponse:
    if (end_date - start_date) > timedelta(days=60):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Date range cannot exceed 60 days",
        )

    try:
        result = await service.get_available_slots(
            db,
            application=application,
            start_date=start_date,
            end_date=end_date,
            duration_minutes=duration_minutes,
            timezone_str=timezone_str,
        )
    except NoLoanOfficerAssignedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # Mark the recommended slot in slots_by_date by start time match.
    rec = result.get("recommended_slot")
    rec_iso = rec["start"] if rec else None

    slots_by_date: dict[str, list[TimeSlot]] = {}
    for date_key, raw_slots in (result.get("slots_by_date") or {}).items():
        slots_by_date[date_key] = [
            TimeSlot(
                start=datetime.fromisoformat(s["start"]),
                end=datetime.fromisoformat(s["end"]),
                is_available=s["is_available"],
                is_recommended=(rec_iso is not None and s["start"] == rec_iso),
            )
            for s in raw_slots
        ]

    return AvailableSlotsResponse(
        application_id=application.id,
        loan_officer_user_id=result["loan_officer_user_id"],
        loan_officer_name=result["loan_officer_name"],
        loan_officer_nmls=result.get("loan_officer_nmls"),
        timezone=result["timezone"],
        duration_minutes=result["duration_minutes"],
        slots_by_date=slots_by_date,
        recommended_slot=(
            TimeSlot(
                start=datetime.fromisoformat(rec["start"]),
                end=datetime.fromisoformat(rec["end"]),
                is_available=True,
                is_recommended=True,
            )
            if rec
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Holds (5-min TTL while the borrower confirms)
# ---------------------------------------------------------------------------
#
# Holds are managed by the existing scheduler via SlotHold. We don't persist
# our own — that would be duplicate state. The bridge calls the existing
# bulk hold endpoint and we round-trip the hold_id back to the borrower.


@router.post(
    "/holds",
    response_model=SlotHoldResponse,
    summary="Place a 5-minute hold on a slot while the borrower confirms",
)
async def create_hold(
    body: SlotHoldRequest,
    purl_ctx: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db),
    service: CalendarService = Depends(get_calendar_service),
) -> SlotHoldResponse:
    """Hold a slot via the existing scheduler's BatchHoldSlotsRequest endpoint.

    Per the dev spec, the underlying SlotHold is TTL-based with status
    transitions active → expired | released | converted. When the subsequent
    booking call succeeds, `converted_to_appointment_id` is set automatically
    by the scheduler. This route is just the borrower-scoped doorway.
    """
    from ._helpers import resolve_application_direct

    application = resolve_application_direct(
        body.application_id,
        purl_ctx=purl_ctx,
        db=db,
    )

    try:
        lo = service.resolve_loan_officer(db, application)
    except NoLoanOfficerAssignedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    link = service.get_booking_link_for_lo(db, lo.id)
    appointment_type_id: int | None = None
    if link is not None:
        try:
            from services.pos.calendar_service import (
                _resolve_appointment_type_id,
                MEETING_TYPES,
            )

            # Default to the application_review duration since this is the
            # primary POS Step 9 flow.
            for mt in ("application_review", "checkin", "full_consultation"):
                try:
                    appointment_type_id = _resolve_appointment_type_id(mt, link)
                    break
                except Exception:
                    continue
        except Exception:
            appointment_type_id = None

    held = await service._bridge.hold_slot(  # noqa: SLF001 — intentional cross-module
        loan_officer_user_id=lo.id,
        slot_start=body.slot_start,
        slot_end=body.slot_end,
        appointment_type_id=appointment_type_id,
        ttl_minutes=5,
        db=db,
        organization_id=application.organization_id,
    )

    return SlotHoldResponse(
        hold_id=held.hold_id,
        expires_at=held.expires_at,
        slot_start=held.slot_start,
        slot_end=held.slot_end,
    )


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------


@router.post(
    "/bookings",
    response_model=BookingResponse,
    summary="Confirm a booking (creates the appointment + calendar event)",
)
async def create_booking(
    body: BookingRequest,
    purl_ctx: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db),
    service: CalendarService = Depends(get_calendar_service),
    ctx: AuditContext = Depends(build_audit_context),
) -> BookingResponse:
    from ._helpers import resolve_application_direct

    application = resolve_application_direct(
        body.application_id,
        purl_ctx=purl_ctx,
        db=db,
    )

    # Prevent duplicate bookings on the same application.
    if application.submitted_appointment_id is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="An appointment has already been booked for this application.",
        )

    attendee_name, attendee_email, attendee_phone = _resolve_attendee_info(
        db, purl_ctx, application
    )

    # Resolve LO once — reuse for both the booking call and the response
    # instead of resolving again after book() returns.
    try:
        lo = service.resolve_loan_officer(db, application)
    except NoLoanOfficerAssignedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        booking = await service.book(
            db,
            application=application,
            meeting_type=body.meeting_type,
            slot_start=body.slot_start,
            slot_end=body.slot_end,
            timezone_str=body.timezone,
            attendee_name=attendee_name,
            attendee_email=attendee_email,
            attendee_phone=attendee_phone,
            notes=body.notes,
            ctx=ctx,
        )
    except NoLoanOfficerAssignedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except NoBookingLinkError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # Link the appointment to the application for duplicate prevention.
    application.submitted_appointment_id = booking.appointment_id
    db.commit()

    return BookingResponse(
        appointment_id=booking.appointment_id,
        application_id=application.id,
        loan_id=application.loan_id,
        loan_officer_user_id=lo.id,
        loan_officer_name=_full_name(lo),
        scheduled_start=booking.scheduled_start,
        scheduled_end=booking.scheduled_end,
        timezone=body.timezone,
        meeting_type=body.meeting_type,
        video_link=None,
        ics_link=booking.ics_link,
        confirmation_url=booking.confirmation_url or "",
        email_sent=booking.email_sent,
        calendar_event_created=booking.calendar_event_created,
    )


@router.delete(
    "/bookings/{appointment_id}",
    response_model=BookingCancelResponse,
    summary="Cancel a booking",
)
async def cancel_booking(
    appointment_id: int,
    body: BookingCancelRequest,
    purl_ctx: PURLAuthContext = Depends(require_purl_write_scope),
    db: Session = Depends(get_db),
    service: CalendarService = Depends(get_calendar_service),
) -> BookingCancelResponse:
    # We must verify the appointment belongs to the borrower's application
    # before allowing cancellation. Look it up via Appointment.loan_id.
    from database.models.scheduler import Appointment

    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    # Find a draft application for this borrower with this loan.
    from sqlalchemy import select

    stmt = select(POSApplication).where(
        POSApplication.contact_id == purl_ctx.contact_id,
        POSApplication.loan_id == appointment.loan_id,
    )
    result = db.execute(stmt)
    application = result.scalar_one_or_none()
    if application is None:
        # Don't reveal whether the appointment exists for someone else.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    cancellation = await service._bridge.cancel(  # noqa: SLF001
        appointment_id=appointment_id,
        reason=body.reason,
        loan_officer_user_id=appointment.assigned_user_id or 0,
        db=db,
        organization_id=application.organization_id,
    )

    # Clear the duplicate-prevention guard so the borrower can rebook.
    if application.submitted_appointment_id == appointment_id:
        application.submitted_appointment_id = None
    db.commit()

    return BookingCancelResponse(
        appointment_id=cancellation.appointment_id,
        cancelled_at=cancellation.cancelled_at,
        notification_sent=cancellation.notification_sent,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _full_name(user: Any) -> str:
    """Format a User object's name for display."""
    name = _full_name_parts(
        getattr(user, "first_name", None),
        getattr(user, "last_name", None),
    )
    if name != "Unknown":
        return name
    return getattr(user, "name", None) or getattr(user, "email", "") or f"User #{user.id}"


def _resolve_attendee_info(
    db: Session,
    purl_ctx: PURLAuthContext,
    application: POSApplication,
) -> tuple[str, str, str | None]:
    """Build (name, email, phone) for the borrower attendee on the booking.

    Merges data from the personal section (name fields) and the PURLContact
    record (email/phone collected during the OTP start flow).
    """
    first: str | None = None
    last: str | None = None
    email: str | None = None
    phone: str | None = None

    # Personal section has first_name / last_name (but not email/phone).
    personal = next(
        (s for s in application.sections if s.section_key == "personal"),
        None,
    )
    if personal and personal.data:
        first = personal.data.get("first_name")
        last = personal.data.get("last_name")
        email = personal.data.get("email")
        phone = personal.data.get("phone")

    # PURLContact always has email/phone from the OTP start flow.
    if purl_ctx.contact_id:
        try:
            from models.purl import PURLContact

            contact = db.get(PURLContact, purl_ctx.contact_id)
            if contact:
                email = email or contact.email
                phone = phone or contact.phone
                first = first or contact.first_name
                last = last or contact.last_name
        except Exception as e:
            logger.warning("Failed to load PURLContact %s: %s", purl_ctx.contact_id, e)

    if first and last and email:
        return f"{first} {last}".strip(), email, phone

    raise HTTPException(
        status.HTTP_409_CONFLICT,
        detail=(
            "Borrower contact info incomplete — please complete the Personal "
            "Information section before booking your meeting."
        ),
    )
