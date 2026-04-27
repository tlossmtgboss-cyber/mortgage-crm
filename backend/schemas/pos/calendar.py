"""Pydantic schemas for borrower-facing Smart Calendar endpoints.

These wrap the existing internal scheduler API with PURL-token auth and
loan-scoped filtering. The borrower never sees other LOs' calendars or
other borrowers' bookings.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


class AvailableSlotsRequest(BaseModel):
    """Query params for GET /api/v1/pos/calendar/available-slots."""

    application_id: UUID
    start_date: date
    end_date: date
    duration_minutes: int = Field(default=30, ge=15, le=240)
    timezone: str = Field(default="America/New_York", max_length=64)

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v < start:
            raise ValueError("end_date must be on or after start_date")
        # Don't let borrowers fetch giant ranges that pin the DB.
        if start and (v - start).days > 60:
            raise ValueError("Date range cannot exceed 60 days")
        return v


class TimeSlot(BaseModel):
    """One bookable time slot."""

    start: datetime
    end: datetime
    is_available: bool = True
    is_recommended: bool = False  # smart-calendar suggested slot


class AvailableSlotsResponse(BaseModel):
    """Response for available-slots."""

    application_id: UUID
    loan_officer_user_id: int
    loan_officer_name: str
    loan_officer_nmls: str | None = None
    timezone: str
    duration_minutes: int

    # Slots grouped by date so the frontend can render the month grid efficiently.
    # Key = ISO date (YYYY-MM-DD), value = ordered list of slots.
    slots_by_date: dict[str, list[TimeSlot]]

    # The single best slot in the range (for the Aria-suggested gold dot).
    recommended_slot: TimeSlot | None = None


# ---------------------------------------------------------------------------
# Slot hold (5-minute TTL while the borrower confirms)
# ---------------------------------------------------------------------------


class SlotHoldRequest(BaseModel):
    """Body for POST /api/v1/pos/calendar/holds."""

    application_id: UUID
    slot_start: datetime
    slot_end: datetime
    duration_minutes: int


class SlotHoldResponse(BaseModel):
    """Response for slot hold creation."""

    hold_id: int
    expires_at: datetime  # 5 min from creation by default
    slot_start: datetime
    slot_end: datetime


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------


class BookingRequest(BaseModel):
    """Body for POST /api/v1/pos/calendar/bookings."""

    application_id: UUID
    hold_id: int | None = Field(
        default=None,
        description=(
            "Optional hold from the previous step. If provided and still "
            "active, it will be converted; otherwise a fresh booking is "
            "created against the slot."
        ),
    )
    meeting_type: str = Field(
        default="application_review",
        description="checkin (15m) | application_review (30m) | full_consultation (60m)",
    )
    slot_start: datetime
    slot_end: datetime
    timezone: str = Field(default="America/New_York")

    # Optional notes the borrower wants Sarah to see ahead of the meeting.
    notes: str | None = Field(default=None, max_length=2000)


class BookingResponse(BaseModel):
    """Response confirming a booking."""

    appointment_id: int
    application_id: UUID
    loan_id: int | None
    loan_officer_user_id: int
    loan_officer_name: str

    scheduled_start: datetime
    scheduled_end: datetime
    timezone: str
    meeting_type: str

    video_link: str | None = None  # populated if meeting type is video
    ics_link: str | None = None  # downloadable .ics file
    confirmation_url: str  # public confirmation page

    email_sent: bool
    calendar_event_created: bool


class BookingCancelRequest(BaseModel):
    """Body for DELETE /api/v1/pos/calendar/bookings/{appointment_id}."""

    reason: str | None = Field(default=None, max_length=500)


class BookingCancelResponse(BaseModel):
    """Response confirming cancellation."""

    appointment_id: int
    cancelled_at: datetime
    notification_sent: bool


# ---------------------------------------------------------------------------
# Assigned LO lookup
# ---------------------------------------------------------------------------


class AssignedLOResponse(BaseModel):
    """Response for GET /api/v1/pos/calendar/assigned-lo."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    name: str
    nmls: str | None = None
    title: str | None = None
    avatar_url: str | None = None
    booking_link_slug: str | None = Field(
        default=None,
        description=(
            "Public booking link slug if the LO has one — used by the "
            "frontend to render direct booking widgets in fallback modes."
        ),
    )
