"""Scheduler bridge.

This module is the SINGLE wiring point between the POS feature and the
existing Smart Calendar / Scheduler module.

Each bridge method uses a two-tier strategy:
  1. **Direct service-layer call** (preferred) — when the caller provides
     ``db`` (SQLAlchemy Session) and ``organization_id`` kwargs, the method
     calls the real service code in-process with zero HTTP overhead:
       - get_available_slots -> RecurringAvailabilityService
       - book                -> appointment_creation_service.create_appointment
       - cancel              -> direct Appointment status update
       - hold_slot           -> slot_hold_service.create_hold
  2. **HTTP fallback** — if ``db``/``organization_id`` are not supplied, or if
     the direct import fails, the method falls back to the original public
     booking HTTP endpoints. This keeps dev/test environments working without
     a fully wired service layer.

The HTTP fallback uses an internal-only base URL set via env var
``PERENNIA_INTERNAL_API_URL`` (defaults to http://localhost:8000).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bridge data classes (transport-agnostic)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BridgeSlot:
    """One available slot returned from the scheduler."""

    start: datetime
    end: datetime
    is_available: bool
    capacity: int = 1


@dataclass(slots=True)
class BridgeBooking:
    """Result of a successful booking call."""

    appointment_id: int
    scheduled_start: datetime
    scheduled_end: datetime
    confirmation_url: str
    ics_link: str | None
    email_sent: bool
    calendar_event_created: bool


@dataclass(slots=True)
class BridgeCancellation:
    """Result of a cancellation."""

    appointment_id: int
    cancelled_at: datetime
    notification_sent: bool


@dataclass(slots=True)
class BridgeHold:
    """Result of placing a slot hold."""

    hold_id: int
    expires_at: datetime
    slot_start: datetime
    slot_end: datetime


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


class SchedulerBridge:
    """Wraps the existing scheduler API for borrower-context calls.

    All methods accept the loan officer user_id (resolved from the loan)
    rather than a booking-link slug, so the borrower never sees or supplies
    a slug directly.
    """

    def __init__(
        self,
        *,
        internal_api_url: str | None = None,
        internal_token: str | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self._base_url = (
            internal_api_url
            or os.environ.get("PERENNIA_INTERNAL_API_URL")
            or "http://localhost:8000"
        ).rstrip("/")
        self._internal_token = internal_token or os.environ.get(
            "PERENNIA_INTERNAL_SERVICE_TOKEN"
        )
        self._timeout = timeout_seconds

    # ----- availability ------------------------------------------------------

    async def get_available_slots(
        self,
        *,
        loan_officer_user_id: int,
        booking_link_slug: str | None,
        start_date: datetime,
        end_date: datetime,
        duration_minutes: int,
        timezone_str: str,
        appointment_type_id: int | None = None,
        db: Any | None = None,
        organization_id: int | None = None,
    ) -> list[BridgeSlot]:
        """Fetch open slots for the borrower's loan officer.

        WIRING POINT 1 — direct service-layer call with HTTP fallback.
        """
        # --- Direct service-layer path (preferred) ---
        if db is not None and organization_id is not None:
            try:
                return self._get_available_slots_direct(
                    db=db,
                    organization_id=organization_id,
                    loan_officer_user_id=loan_officer_user_id,
                    start_date=start_date,
                    end_date=end_date,
                    duration_minutes=duration_minutes,
                    timezone_str=timezone_str,
                    appointment_type_id=appointment_type_id,
                )
            except Exception as exc:
                logger.warning(
                    "Direct service call for get_available_slots failed, "
                    "falling back to HTTP: %s",
                    exc,
                )

        # --- HTTP fallback ---
        if not booking_link_slug:
            raise NoBookingLinkError(
                f"Loan officer {loan_officer_user_id} has no public booking "
                "link. Either configure one or wire the bridge to call the "
                "internal scheduler service directly."
            )

        url = f"{self._base_url}/api/v1/scheduler/public/book/{booking_link_slug}/slots"
        params: dict[str, Any] = {
            "start_date": start_date.date().isoformat(),
            "end_date": end_date.date().isoformat(),
            "duration_minutes": duration_minutes,
        }
        if appointment_type_id:
            params["appointment_type_id"] = appointment_type_id

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()

        # Public booking endpoint shape: {"slots": [{"start": ..., "end": ..., "available_capacity": int}]}
        # Tolerant of variations — some deployments return "available_slots".
        raw_slots = payload.get("slots") or payload.get("available_slots") or []
        out: list[BridgeSlot] = []
        for s in raw_slots:
            try:
                start = _parse_dt(s["start"])
                end = _parse_dt(s["end"])
                out.append(
                    BridgeSlot(
                        start=start,
                        end=end,
                        is_available=s.get("is_available", True),
                        capacity=int(s.get("available_capacity", 1)),
                    )
                )
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed slot from scheduler: %s (%s)", s, exc)
        return out

    @staticmethod
    def _get_available_slots_direct(
        *,
        db: Any,
        organization_id: int,
        loan_officer_user_id: int,
        start_date: datetime,
        end_date: datetime,
        duration_minutes: int,
        timezone_str: str,
        appointment_type_id: int | None,
    ) -> list[BridgeSlot]:
        """Direct call to RecurringAvailabilityService.get_available_slots()."""
        from services.recurring_availability_service import RecurringAvailabilityService

        svc = RecurringAvailabilityService(db)
        raw_slots = svc.get_available_slots(
            user_id=loan_officer_user_id,
            org_id=organization_id,
            start_date=start_date.date() if hasattr(start_date, "date") else start_date,
            end_date=end_date.date() if hasattr(end_date, "date") else end_date,
            duration_minutes=duration_minutes,
            timezone_str=timezone_str,
        )

        out: list[BridgeSlot] = []
        for s in raw_slots:
            try:
                # RecurringAvailabilityService returns dicts with
                # "start_datetime" (ISO UTC) and "end_datetime" (ISO UTC).
                start_dt = _parse_dt(s["start_datetime"])
                end_dt = _parse_dt(s["end_datetime"])
                out.append(
                    BridgeSlot(
                        start=start_dt,
                        end=end_dt,
                        is_available=True,
                        capacity=1,
                    )
                )
            except (KeyError, ValueError) as exc:
                logger.warning(
                    "Skipping malformed slot from availability service: %s (%s)",
                    s, exc,
                )
        return out

    # ----- booking -----------------------------------------------------------

    async def book(
        self,
        *,
        loan_officer_user_id: int,
        booking_link_slug: str | None,
        appointment_type_id: int,
        attendee_name: str,
        attendee_email: str,
        attendee_phone: str | None,
        slot_start: datetime,
        slot_end: datetime,
        timezone_str: str,
        loan_id: int | None,
        notes: str | None,
        intake_responses: dict[str, Any] | None = None,
        db: Any | None = None,
        organization_id: int | None = None,
    ) -> BridgeBooking:
        """Convert a slot into an appointment.

        WIRING POINT 2 — direct service-layer call with HTTP fallback.
        """
        # --- Direct service-layer path (preferred) ---
        if db is not None and organization_id is not None:
            try:
                return await self._book_direct(
                    db=db,
                    organization_id=organization_id,
                    loan_officer_user_id=loan_officer_user_id,
                    appointment_type_id=appointment_type_id,
                    attendee_name=attendee_name,
                    attendee_email=attendee_email,
                    attendee_phone=attendee_phone,
                    slot_start=slot_start,
                    slot_end=slot_end,
                    timezone_str=timezone_str,
                    loan_id=loan_id,
                    notes=notes,
                    intake_responses=intake_responses,
                )
            except Exception as exc:
                logger.warning(
                    "Direct service call for book failed, "
                    "falling back to HTTP: %s",
                    exc,
                )

        # --- HTTP fallback ---
        if not booking_link_slug:
            raise NoBookingLinkError(
                f"Loan officer {loan_officer_user_id} has no public booking link"
            )

        url = f"{self._base_url}/api/v1/scheduler/public/book/{booking_link_slug}/confirm"
        body: dict[str, Any] = {
            "attendee_name": attendee_name,
            "attendee_email": attendee_email,
            "attendee_phone": attendee_phone,
            "scheduled_start": slot_start.isoformat(),
            "scheduled_end": slot_end.isoformat(),
            "timezone": timezone_str,
            "appointment_type_id": appointment_type_id,
            "intake_responses": intake_responses or {},
            "ai_booking_context": {
                "source": "perennia_pos_1003",
                "loan_id": loan_id,
                "notes": notes,
            },
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=body, headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()

        return BridgeBooking(
            appointment_id=int(payload["appointment_id"]),
            scheduled_start=_parse_dt(payload.get("scheduled_start", slot_start.isoformat())),
            scheduled_end=_parse_dt(payload.get("scheduled_end", slot_end.isoformat())),
            confirmation_url=payload.get("confirmation_url", ""),
            ics_link=payload.get("ics_link"),
            email_sent=bool(payload.get("email_sent", False)),
            calendar_event_created=bool(payload.get("calendar_event_created", False)),
        )

    @staticmethod
    async def _book_direct(
        *,
        db: Any,
        organization_id: int,
        loan_officer_user_id: int,
        appointment_type_id: int,
        attendee_name: str,
        attendee_email: str,
        attendee_phone: str | None,
        slot_start: datetime,
        slot_end: datetime,
        timezone_str: str,
        loan_id: int | None,
        notes: str | None,
        intake_responses: dict[str, Any] | None,
    ) -> BridgeBooking:
        """Direct call to appointment_creation_service.create_appointment()."""
        from services.appointment_creation_service import (
            create_appointment as create_appointment_service,
        )

        duration_minutes = max(1, int((slot_end - slot_start).total_seconds() / 60))

        result = await create_appointment_service(
            db=db,
            organization_id=organization_id,
            assigned_user_id=loan_officer_user_id,
            created_by_user_id=None,  # POS/borrower-initiated — no authenticated user
            source="pos_booking",
            title=f"POS Booking — {attendee_name}",
            scheduled_start=slot_start,
            scheduled_end=slot_end,
            duration_minutes=duration_minutes,
            timezone=timezone_str,
            attendee_name=attendee_name,
            attendee_email=attendee_email,
            attendee_phone=attendee_phone,
            appointment_type_id=appointment_type_id,
            loan_id=loan_id,
            description=notes,
            intake_responses=intake_responses or {},
            ai_booking_context={
                "source": "perennia_pos_1003",
                "loan_id": loan_id,
                "notes": notes,
            },
            check_conflicts=True,
            check_cross_source=True,
            check_capacity=True,
            generate_meeting_link=True,
            create_lead_if_missing=True,
            auto_commit=True,
        )

        if not result.success:
            raise SchedulerBridgeError(
                f"Appointment creation failed: {result.error}"
            )

        appt = result.appointment
        return BridgeBooking(
            appointment_id=result.appointment_id,
            scheduled_start=appt.scheduled_start,
            scheduled_end=appt.scheduled_end,
            confirmation_url="",
            ics_link=None,
            email_sent=False,  # caller or background task handles notifications
            calendar_event_created=False,
        )

    # ----- holds -------------------------------------------------------------

    async def hold_slot(
        self,
        *,
        loan_officer_user_id: int,
        slot_start: datetime,
        slot_end: datetime,
        appointment_type_id: int | None,
        ttl_minutes: int = 5,
        db: Any | None = None,
        organization_id: int | None = None,
    ) -> BridgeHold:
        """Place a TTL hold on a slot.

        WIRING POINT 4 — direct service-layer call with HTTP fallback.

        If neither a DB session nor a service token is available, returns a
        synthetic hold for the frontend to track its own TTL countdown
        (correctness still holds because book operations are idempotent on
        (user_id, slot_start)).
        """
        # --- Direct service-layer path (preferred) ---
        if db is not None and organization_id is not None:
            try:
                return await self._hold_slot_direct(
                    db=db,
                    organization_id=organization_id,
                    loan_officer_user_id=loan_officer_user_id,
                    slot_start=slot_start,
                    slot_end=slot_end,
                    ttl_minutes=ttl_minutes,
                )
            except Exception as exc:
                logger.warning(
                    "Direct service call for hold_slot failed, "
                    "falling back to HTTP/synthetic: %s",
                    exc,
                )

        # --- HTTP fallback ---
        if not self._internal_token:
            # No service token configured — return a synthetic hold so the
            # frontend can run a TTL countdown. Book-time idempotency in the
            # scheduler itself prevents double-booking.
            return BridgeHold(
                hold_id=int(slot_start.timestamp()),
                expires_at=datetime.now(timezone.utc).replace(microsecond=0)
                + timedelta(minutes=ttl_minutes),
                slot_start=slot_start,
                slot_end=slot_end,
            )

        url = f"{self._base_url}/api/v1/scheduler/bulk/hold-slots"
        body = {
            "holds": [
                {
                    "user_id": loan_officer_user_id,
                    "slot_start": slot_start.isoformat(),
                    "slot_end": slot_end.isoformat(),
                    "appointment_type_id": appointment_type_id,
                    "ttl_minutes": ttl_minutes,
                }
            ]
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=body, headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()

        # The dev spec describes the response as {held_count, failed_count}
        # with the hold rows themselves under a `holds` key. Tolerant parsing:
        holds = payload.get("holds") or []
        if not holds or payload.get("held_count", 0) < 1:
            raise SchedulerBridgeError(
                f"Failed to hold slot: {payload.get('errors') or payload}"
            )

        first = holds[0]
        return BridgeHold(
            hold_id=int(first["id"]),
            expires_at=_parse_dt(first["expires_at"]),
            slot_start=slot_start,
            slot_end=slot_end,
        )

    @staticmethod
    async def _hold_slot_direct(
        *,
        db: Any,
        organization_id: int,
        loan_officer_user_id: int,
        slot_start: datetime,
        slot_end: datetime,
        ttl_minutes: int,
    ) -> BridgeHold:
        """Direct call to slot_hold_service.create_hold()."""
        from services.slot_hold_service import create_hold
        from routes.scheduler._core import get_models

        models = get_models()
        result = await create_hold(
            lo_id=loan_officer_user_id,
            start_time=slot_start,
            end_time=slot_end,
            held_by="public_booking",
            organization_id=organization_id,
            db=db,
            models=models,
            ttl_seconds=ttl_minutes * 60,
        )

        return BridgeHold(
            hold_id=int(result["id"]),
            expires_at=_parse_dt(result["expires_at"]),
            slot_start=slot_start,
            slot_end=slot_end,
        )

    # ----- cancellation ------------------------------------------------------

    async def cancel(
        self,
        *,
        appointment_id: int,
        reason: str | None,
        loan_officer_user_id: int,
        db: Any | None = None,
        organization_id: int | None = None,
    ) -> BridgeCancellation:
        """Cancel an appointment.

        WIRING POINT 3 — direct service-layer call with HTTP fallback.
        """
        # --- Direct service-layer path (preferred) ---
        if db is not None and organization_id is not None:
            try:
                return self._cancel_direct(
                    db=db,
                    organization_id=organization_id,
                    appointment_id=appointment_id,
                    reason=reason,
                )
            except Exception as exc:
                logger.warning(
                    "Direct service call for cancel failed, "
                    "falling back to HTTP: %s",
                    exc,
                )

        # --- HTTP fallback ---
        url = f"{self._base_url}/api/v1/scheduler/appointments/{appointment_id}/cancel"
        body = {
            "reason": reason or "Cancelled by borrower",
            "notify_attendee": True,
            "offer_alternative": False,
        }

        if not self._internal_token:
            raise SchedulerBridgeError(
                "Cancellation requires an internal service token. Either set "
                "PERENNIA_INTERNAL_SERVICE_TOKEN or replace this method with a "
                "direct service-layer call (see WIRING POINT above)."
            )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=body, headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()

        return BridgeCancellation(
            appointment_id=appointment_id,
            cancelled_at=datetime.now(timezone.utc),
            notification_sent=bool(payload.get("emails_sent", False)),
        )

    @staticmethod
    def _cancel_direct(
        *,
        db: Any,
        organization_id: int,
        appointment_id: int,
        reason: str | None,
    ) -> BridgeCancellation:
        """Direct DB cancellation mirroring routes/scheduler/appointments.py logic."""
        from routes.scheduler._core import get_models
        from smart_scheduler_models import AppointmentStatus

        models = get_models()
        Appointment = models["Appointment"]

        appointment = db.query(Appointment).filter(
            Appointment.id == appointment_id,
            Appointment.organization_id == organization_id,
        ).first()

        if not appointment:
            raise SchedulerBridgeError(
                f"Appointment {appointment_id} not found in org {organization_id}"
            )

        # Only cancel from cancellable statuses
        current_status = (
            appointment.status.value
            if hasattr(appointment.status, "value")
            else str(appointment.status or "booked")
        )
        cancellable = {"booked", "confirmed", "reminded", "checked_in", "tentative"}
        if current_status not in cancellable:
            raise SchedulerBridgeError(
                f"Cannot cancel appointment with status: {current_status}"
            )

        now = datetime.now(timezone.utc)
        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancelled_at = now
        appointment.cancellation_reason = reason or "Cancelled by borrower"
        appointment.status_changed_at = now

        db.flush()

        return BridgeCancellation(
            appointment_id=appointment_id,
            cancelled_at=now,
            notification_sent=False,
        )

    # ----- internals ---------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._internal_token:
            h["Authorization"] = f"Bearer {self._internal_token}"
        return h


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SchedulerBridgeError(RuntimeError):
    """Base error raised by the bridge."""


class NoBookingLinkError(SchedulerBridgeError):
    """Raised when an LO has no public booking link configured."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: str) -> datetime:
    """Parse an ISO-8601 datetime, tolerating trailing Z."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


# Module-level singleton (cheap; httpx clients are created per-call).
_bridge_singleton: SchedulerBridge | None = None


def get_scheduler_bridge() -> SchedulerBridge:
    global _bridge_singleton
    if _bridge_singleton is None:
        _bridge_singleton = SchedulerBridge()
    return _bridge_singleton
