"""Calendar service — POS-side wrapping of the existing Smart Calendar.

Resolves the assigned LO from the borrower's loan, filters availability for
that LO only, and sets Appointment.loan_id on bookings so the canonical
loan-file linkage is preserved.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.pos import (
    POSApplication,
    POSAuditEvent,
)
from database.models.lead_loan import Loan
from database.models.core import User
from database.models.scheduler import (
    Appointment,
    BookingLink,
)
from services.event_bus import Event, EventType, event_bus

from ._scheduler_bridge import (
    BridgeBooking,
    BridgeSlot,
    NoBookingLinkError,
    SchedulerBridge,
    get_scheduler_bridge,
)
from .application_service import ApplicationService, AuditContext


logger = logging.getLogger(__name__)


# Meeting type → (display label, default duration min, scheduler appointment_type_id key)
# The integer IDs come from your `appointment_types` table — they're tenant
# specific. The defaults below match the seed data shipped in this skill's
# `seed.sql`, but you can override per-tenant via the
# POS_MEETING_TYPE_IDS env var (JSON: {"checkin": 7, ...}).
MEETING_TYPES: dict[str, dict[str, Any]] = {
    "checkin": {"label": "Quick check-in", "duration": 15, "default_type_id": None},
    "application_review": {
        "label": "Application review",
        "duration": 30,
        "default_type_id": None,
    },
    "full_consultation": {
        "label": "Full consultation",
        "duration": 60,
        "default_type_id": None,
    },
}


class NoLoanOfficerAssignedError(LookupError):
    """Raised when we can't determine which LO this borrower should book with."""


class CalendarService:
    """Smart Calendar operations scoped to a single borrower's loan file."""

    def __init__(
        self,
        bridge: SchedulerBridge | None = None,
        application_service: ApplicationService | None = None,
    ) -> None:
        self._bridge = bridge or get_scheduler_bridge()
        self._app_service = application_service or ApplicationService()

    # ----- LO resolution -----------------------------------------------------

    def resolve_loan_officer(
        self,
        session: Session,
        application: POSApplication,
    ) -> User:
        """Find the LO this borrower should book with.

        Resolution order:
          1. loan.loan_officer_id (the assigned LO)
          2. fall back to organization round-robin (not implemented here —
             raise so the frontend can show "no LO assigned" UI)
        """
        if application.loan_id is None:
            raise NoLoanOfficerAssignedError(
                "Application has no loan; an LO must be assigned before booking"
            )

        loan = session.get(Loan, application.loan_id)
        if loan is None:
            raise NoLoanOfficerAssignedError(
                f"Loan {application.loan_id} not found"
            )
        # Loan model field name from the dev spec: loan_officer_id.
        lo_id = getattr(loan, "loan_officer_id", None) or getattr(loan, "owner_id", None)
        if lo_id is None:
            raise NoLoanOfficerAssignedError(
                f"Loan {loan.id} has no assigned loan officer"
            )

        lo = session.get(User, lo_id)
        if lo is None:
            raise NoLoanOfficerAssignedError(f"Loan officer user {lo_id} not found")
        return lo

    def get_booking_link_for_lo(
        self,
        session: Session,
        lo_user_id: int,
    ) -> BookingLink | None:
        """Return the LO's primary public booking link if one exists."""
        stmt = (
            select(BookingLink)
            .where(BookingLink.owner_user_id == lo_user_id)
            .where(BookingLink.is_active.is_(True))
            .order_by(BookingLink.created_at.asc())
            .limit(1)
        )
        result = session.execute(stmt)
        return result.scalar_one_or_none()

    # ----- availability ------------------------------------------------------

    async def get_available_slots(
        self,
        session: Session,
        *,
        application: POSApplication,
        start_date: datetime,
        end_date: datetime,
        duration_minutes: int,
        timezone_str: str,
    ) -> dict[str, Any]:
        """Return open slots for the borrower's LO grouped by date."""
        lo = self.resolve_loan_officer(session, application)
        link = self.get_booking_link_for_lo(session, lo.id)
        slug = link.slug if link else None

        try:
            slots = await self._bridge.get_available_slots(
                loan_officer_user_id=lo.id,
                booking_link_slug=slug,
                start_date=start_date,
                end_date=end_date,
                duration_minutes=duration_minutes,
                timezone_str=timezone_str,
                db=session,
                organization_id=application.organization_id,
            )
        except NoBookingLinkError:
            # Surface to the route as an empty result with metadata — the
            # frontend will render an "ask Sarah for a link" message.
            logger.warning(
                "No booking link configured for LO %s; returning empty slots", lo.id
            )
            slots = []

        # Group by ISO date.
        grouped: dict[str, list[BridgeSlot]] = defaultdict(list)
        for s in slots:
            grouped[s.start.date().isoformat()].append(s)

        recommended = self._pick_recommended_slot(slots)

        return {
            "loan_officer_user_id": lo.id,
            "loan_officer_name": _full_name(lo),
            "loan_officer_nmls": getattr(lo, "nmls_id", None),
            "timezone": timezone_str,
            "duration_minutes": duration_minutes,
            "slots_by_date": {
                k: [_slot_to_dict(s) for s in v] for k, v in grouped.items()
            },
            "recommended_slot": _slot_to_dict(recommended) if recommended else None,
        }

    @staticmethod
    def _pick_recommended_slot(slots: list[BridgeSlot]) -> BridgeSlot | None:
        """Pick the smart-recommended slot.

        Heuristic: first available slot that's:
          - on a weekday (Mon-Fri)
          - between 9:30am and 11:30am local time (typical "best meeting" window)
          - at least 24h in the future (gives the LO prep time)

        Falls back to the earliest available slot if none match.
        """
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=24)

        ideal_start = time(9, 30)
        ideal_end = time(11, 30)

        for slot in slots:
            if not slot.is_available:
                continue
            if slot.start < cutoff:
                continue
            if slot.start.weekday() >= 5:  # Saturday or Sunday
                continue
            local_time = slot.start.time()
            if ideal_start <= local_time <= ideal_end:
                return slot

        # Fall back: first available future slot.
        for slot in slots:
            if slot.is_available and slot.start >= now:
                return slot
        return None

    # ----- booking -----------------------------------------------------------

    async def book(
        self,
        session: Session,
        *,
        application: POSApplication,
        meeting_type: str,
        slot_start: datetime,
        slot_end: datetime,
        timezone_str: str,
        attendee_name: str,
        attendee_email: str,
        attendee_phone: str | None,
        notes: str | None,
        ctx: AuditContext,
    ) -> BridgeBooking:
        """Book an appointment for the borrower."""
        if meeting_type not in MEETING_TYPES:
            raise ValueError(f"Unknown meeting_type: {meeting_type}")

        lo = self.resolve_loan_officer(session, application)
        link = self.get_booking_link_for_lo(session, lo.id)
        slug = link.slug if link else None

        appointment_type_id = MEETING_TYPES[meeting_type]["default_type_id"]
        if not appointment_type_id and link is not None:
            appointment_type_id = _resolve_appointment_type_id(meeting_type, link)

        booking = await self._bridge.book(
            loan_officer_user_id=lo.id,
            booking_link_slug=slug,
            appointment_type_id=appointment_type_id,
            attendee_name=attendee_name,
            attendee_email=attendee_email,
            attendee_phone=attendee_phone,
            slot_start=slot_start,
            slot_end=slot_end,
            timezone_str=timezone_str,
            loan_id=application.loan_id,
            notes=notes,
            intake_responses={"meeting_type": meeting_type, "notes": notes},
            db=session,
            organization_id=application.organization_id,
        )

        # Set Appointment.loan_id directly here as well — the public booking
        # endpoint may not honor the ai_booking_context payload depending on
        # version. This is defensive idempotent.
        if application.loan_id is not None:
            appointment = session.get(Appointment, booking.appointment_id)
            if appointment is not None and appointment.loan_id != application.loan_id:
                appointment.loan_id = application.loan_id
                session.flush()

        # Audit on the application side.
        self._app_service._write_audit(  # noqa: SLF001 — intentional
            session,
            application_id=application.id,
            ctx=ctx,
            event_type=POSAuditEvent.APPOINTMENT_BOOKED,
            delta={
                "appointment_id": booking.appointment_id,
                "loan_officer_user_id": lo.id,
                "meeting_type": meeting_type,
                "scheduled_start": booking.scheduled_start.isoformat(),
            },
        )

        # Subscribe-side check: the existing scheduler emits APPOINTMENT_CREATED.
        # We re-emit a POS-specific event so dashboards/analytics can filter to
        # POS-originated bookings without inspecting `ai_booking_context.source`.
        await event_bus.publish(
            Event(
                type=EventType.POS_APPOINTMENT_BOOKED,
                data={
                    "application_id": str(application.id),
                    "appointment_id": booking.appointment_id,
                    "loan_id": application.loan_id,
                    "loan_officer_user_id": lo.id,
                    "meeting_type": meeting_type,
                },
                org_id=str(application.organization_id),
            )
        )
        return booking


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _full_name(user: User) -> str:
    """Best-effort name string for a User."""
    parts = [
        getattr(user, "first_name", None) or "",
        getattr(user, "last_name", None) or "",
    ]
    name = " ".join(p for p in parts if p).strip()
    if name:
        return name
    return getattr(user, "name", None) or getattr(user, "email", "") or f"User #{user.id}"


def _slot_to_dict(slot: BridgeSlot) -> dict[str, Any]:
    return {
        "start": slot.start.isoformat(),
        "end": slot.end.isoformat(),
        "is_available": slot.is_available,
        "is_recommended": False,  # set by route layer based on recommended_slot
    }


def _resolve_appointment_type_id(meeting_type: str, link: BookingLink) -> int:
    """Look up the appointment_type_id for a given meeting_type label.

    The BookingLink has an associated set of appointment types. We pick the
    one whose duration matches the meeting type's expected duration.
    """
    expected = MEETING_TYPES[meeting_type]["duration"]
    types = getattr(link, "appointment_types", None) or []
    for t in types:
        if getattr(t, "duration_minutes", None) == expected:
            return int(t.id)
    # Fall back to the link's default appointment type.
    default_id = getattr(link, "default_appointment_type_id", None)
    if default_id:
        return int(default_id)
    raise ValueError(
        f"Could not resolve appointment_type_id for meeting_type={meeting_type} "
        f"on booking link {link.id}. Configure an appointment type with "
        f"duration_minutes={expected}."
    )
