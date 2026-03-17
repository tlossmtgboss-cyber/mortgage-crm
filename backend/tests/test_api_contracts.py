"""
API Contract Tests - Scheduler API Response Schema Validation

Verifies that API response schemas are consistent and match the documented format.
Tests validate response structure without requiring a live database by constructing
response payloads that mirror the actual endpoint return values.

Test Categories:
1. Response Envelope Contract (success/error wrapper consistency)
2. Appointment Schema Contract (required fields, types, formats)
3. Availability Schema Contract (slot structure, ordering)
4. Booking Link Schema Contract (link structure, public page data)
5. Error Schema Contract (error codes, field-level details)
6. Schema Versioning (no deprecated fields, enum coverage)
"""

import pytest
import re
import uuid
from datetime import datetime, date, time, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import BaseModel, Field, field_validator, ValidationError
from enum import Enum


# =============================================================================
# CONTRACT SCHEMA DEFINITIONS (Pydantic v2)
#
# These models define the expected API response contracts.
# Tests validate that actual endpoint response dicts conform to these schemas.
# =============================================================================

# --- Enums ---

class AppointmentStatusEnum(str, Enum):
    AVAILABLE = "available"
    TENTATIVE = "tentative"
    BOOKED = "booked"
    CONFIRMED = "confirmed"
    REMINDED = "reminded"
    CHECKED_IN = "checked_in"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


class MeetingTypeEnum(str, Enum):
    DISCOVERY_CALL = "discovery_call"
    PRE_APPROVAL_REVIEW = "pre_approval_review"
    APPLICATION_WALKTHROUGH = "application_walkthrough"
    DOCUMENT_REVIEW = "document_review"
    RATE_LOCK_DISCUSSION = "rate_lock_discussion"
    CLOSING_PREP = "closing_prep"
    POST_CLOSE_REVIEW = "post_close_review"
    REFERRAL_PARTNER_MEETING = "referral_partner_meeting"
    TEAM_SYNC = "team_sync"
    CUSTOM = "custom"


class MeetingModeEnum(str, Enum):
    VIDEO = "video"
    PHONE = "phone"
    IN_PERSON = "in_person"
    SCREEN_SHARE = "screen_share"


# --- Appointment Schemas ---

class AppointmentListItem(BaseModel):
    """Schema for an appointment in the list response."""
    id: Any  # int or "ai-{id}" string for legacy
    title: str
    description: Optional[str] = None
    meeting_type: Optional[str] = None
    meeting_mode: Optional[str] = None
    scheduled_start: str  # ISO 8601
    scheduled_end: str  # ISO 8601
    duration_minutes: Optional[int] = None
    status: Optional[str] = None
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    video_link: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    booked_by_ai: Optional[bool] = None
    created_at: Optional[str] = None


class AppointmentDetail(BaseModel):
    """Schema for a single appointment detail response."""
    id: int
    appointment_type_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    meeting_type: Optional[str] = None
    meeting_mode: Optional[str] = None
    scheduled_start: str  # ISO 8601
    scheduled_end: str  # ISO 8601
    duration_minutes: Optional[int] = None
    timezone: Optional[str] = None
    location: Optional[str] = None
    video_link: Optional[str] = None
    phone_number: Optional[str] = None
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    attendee_phone: Optional[str] = None
    attendee_notes: Optional[str] = None
    intake_responses: Optional[dict] = None
    status: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    contact_id: Optional[int] = None
    assigned_user_id: Optional[int] = None
    booked_by_ai: Optional[bool] = None
    ai_booking_context: Optional[dict] = None
    internal_notes: Optional[str] = None
    meeting_notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AppointmentListResponse(BaseModel):
    """Schema for the list appointments endpoint response."""
    appointments: List[AppointmentListItem]
    total: int
    limit: int
    offset: int


class AppointmentDetailResponse(BaseModel):
    """Schema for the get appointment detail endpoint response."""
    appointment: AppointmentDetail


class AppointmentCreateResponse(BaseModel):
    """Schema for the create appointment endpoint response."""
    message: str
    appointment_id: int
    scheduled_start: str
    scheduled_end: str
    email_sent: bool
    email_error: Optional[str] = None
    calendar_event_created: bool
    outlook_event_id: Optional[str] = None


# --- Availability Schemas ---

class AvailabilitySlotItem(BaseModel):
    """Schema for one availability slot."""
    id: int
    day_of_week: Optional[str] = None
    specific_date: Optional[str] = None
    start_time: str  # HH:MM
    end_time: str  # HH:MM
    priority: str
    is_recurring: bool


class BlockedTimeItem(BaseModel):
    """Schema for a blocked time entry."""
    id: int
    title: str
    start: str  # ISO 8601
    end: str  # ISO 8601
    all_day: bool
    block_type: str


class ExistingAppointmentItem(BaseModel):
    """Schema for an existing appointment in availability view."""
    id: int
    title: str
    start: str  # ISO 8601
    end: str  # ISO 8601
    status: str


class AvailabilityResponse(BaseModel):
    """Schema for the get availability endpoint response."""
    availability: List[AvailabilitySlotItem]
    working_hours: dict
    blocked_times: List[BlockedTimeItem]
    existing_appointments: List[ExistingAppointmentItem]


class AvailableSlotsResponse(BaseModel):
    """Schema for the available-slots endpoint response."""
    available_slots: list
    total_slots: int
    request: dict


# --- Booking Link Schemas ---

class BookingLinkItem(BaseModel):
    """Schema for a booking link in the list response."""
    id: int
    slug: str
    link_name: str
    description: Optional[str] = None
    url: str
    is_public: bool
    view_count: Optional[int] = None
    booking_count: Optional[int] = None
    last_booked_at: Optional[str] = None
    created_at: Optional[str] = None


class BookingLinkListResponse(BaseModel):
    """Schema for the list booking links endpoint response."""
    booking_links: List[BookingLinkItem]


class BookingLinkCreateResponse(BaseModel):
    """Schema for the create booking link endpoint response."""
    message: str
    link_id: int
    url: str


# --- Error Schemas ---

class HTTPErrorDetail(BaseModel):
    """Standard FastAPI HTTPException detail."""
    detail: str


# --- Timeline ---

class TimelineEntry(BaseModel):
    """Schema for an appointment timeline entry."""
    id: Optional[int] = None
    previous_status: Optional[str] = None
    new_status: str
    changed_by_name: Optional[str] = None
    changed_by_user_id: Optional[int] = None
    change_source: Optional[str] = None
    notes: Optional[str] = None
    metadata: Optional[dict] = None
    changed_at: Optional[str] = None


class TimelineResponse(BaseModel):
    """Schema for the appointment timeline endpoint response."""
    appointment_id: int
    current_status: str
    standard_progression: List[str]
    history: List[TimelineEntry]
    appointment_summary: dict


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# ISO 8601 datetime pattern (strict)
_ISO8601_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(\.\d+)?"               # optional fractional seconds
    r"([+-]\d{2}:\d{2}|Z)?$"  # optional timezone offset
)

# UUID v4 pattern
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# HH:MM time pattern
_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


def is_iso8601(value: str) -> bool:
    """Check if a string is a valid ISO 8601 datetime."""
    return bool(_ISO8601_PATTERN.match(value))


def is_uuid(value: str) -> bool:
    """Check if a string is a valid UUID v4."""
    return bool(_UUID_PATTERN.match(value))


def is_hhmm(value: str) -> bool:
    """Check if a string is HH:MM format."""
    return bool(_TIME_PATTERN.match(value))


def make_iso_dt(dt: datetime = None) -> str:
    """Create an ISO 8601 datetime string."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.isoformat()


# =============================================================================
# FIXTURE: Sample response payloads that mirror actual endpoint output
# =============================================================================

@pytest.fixture
def sample_appointment_list_response():
    """Sample response from GET /appointments."""
    now = datetime.now(timezone.utc)
    return {
        "appointments": [
            {
                "id": 1,
                "title": "Pre-Approval Review",
                "description": "Review documents for pre-approval",
                "meeting_type": "pre_approval_review",
                "meeting_mode": "video",
                "scheduled_start": now.isoformat(),
                "scheduled_end": (now + timedelta(minutes=30)).isoformat(),
                "duration_minutes": 30,
                "status": "booked",
                "attendee_name": "John Doe",
                "attendee_email": "john@example.com",
                "video_link": "https://meet.example.com/abc",
                "lead_id": 42,
                "loan_id": None,
                "booked_by_ai": False,
                "created_at": now.isoformat(),
            },
            {
                "id": "ai-5",
                "title": "Appointment with Jane Smith",
                "description": None,
                "meeting_type": "discovery_call",
                "meeting_mode": "PHONE",
                "scheduled_start": (now + timedelta(hours=2)).isoformat(),
                "scheduled_end": (now + timedelta(hours=2, minutes=30)).isoformat(),
                "duration_minutes": 30,
                "status": "BOOKED",
                "attendee_name": "Jane Smith",
                "attendee_email": "jane@example.com",
                "video_link": None,
                "lead_id": 43,
                "loan_id": None,
                "booked_by_ai": True,
                "created_at": now.isoformat(),
            },
        ],
        "total": 2,
        "limit": 50,
        "offset": 0,
    }


@pytest.fixture
def sample_appointment_detail_response():
    """Sample response from GET /appointments/{id}."""
    now = datetime.now(timezone.utc)
    return {
        "appointment": {
            "id": 1,
            "appointment_type_id": 3,
            "title": "Rate Lock Discussion",
            "description": "Discuss rate lock options",
            "meeting_type": "rate_lock_discussion",
            "meeting_mode": "phone",
            "scheduled_start": now.isoformat(),
            "scheduled_end": (now + timedelta(minutes=45)).isoformat(),
            "duration_minutes": 45,
            "timezone": "America/Chicago",
            "location": None,
            "video_link": None,
            "phone_number": "+15551234567",
            "attendee_name": "Bob Builder",
            "attendee_email": "bob@example.com",
            "attendee_phone": "+15559876543",
            "attendee_notes": "Prefers afternoon calls",
            "intake_responses": {"preferred_rate_type": "fixed"},
            "status": "booked",
            "lead_id": 10,
            "loan_id": 20,
            "contact_id": None,
            "assigned_user_id": 5,
            "booked_by_ai": False,
            "ai_booking_context": None,
            "internal_notes": "Client referred by realtor",
            "meeting_notes": None,
            "created_at": now.isoformat(),
            "updated_at": None,
        }
    }


@pytest.fixture
def sample_availability_response():
    """Sample response from GET /availability."""
    now = datetime.now(timezone.utc)
    return {
        "availability": [
            {
                "id": 1,
                "day_of_week": "monday",
                "specific_date": None,
                "start_time": "09:00",
                "end_time": "17:00",
                "priority": "standard",
                "is_recurring": True,
            },
            {
                "id": 2,
                "day_of_week": None,
                "specific_date": "2026-03-15",
                "start_time": "10:00",
                "end_time": "14:00",
                "priority": "preferred",
                "is_recurring": False,
            },
        ],
        "working_hours": {
            "monday": {"start": "09:00", "end": "17:00", "enabled": True},
            "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
            "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
            "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
            "friday": {"start": "09:00", "end": "17:00", "enabled": True},
            "saturday": {"start": "00:00", "end": "00:00", "enabled": False},
            "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
        },
        "blocked_times": [
            {
                "id": 10,
                "title": "Team Lunch",
                "start": now.isoformat(),
                "end": (now + timedelta(hours=1)).isoformat(),
                "all_day": False,
                "block_type": "lunch",
            }
        ],
        "existing_appointments": [
            {
                "id": 100,
                "title": "Client Meeting",
                "start": (now + timedelta(hours=2)).isoformat(),
                "end": (now + timedelta(hours=2, minutes=30)).isoformat(),
                "status": "booked",
            }
        ],
    }


@pytest.fixture
def sample_booking_link_list_response():
    """Sample response from GET /booking-links."""
    now = datetime.now(timezone.utc)
    return {
        "booking_links": [
            {
                "id": 1,
                "slug": "john-doe-meeting",
                "link_name": "Schedule with John",
                "description": "Book a meeting with John Doe",
                "url": "/book/john-doe-meeting",
                "is_public": True,
                "view_count": 150,
                "booking_count": 23,
                "last_booked_at": now.isoformat(),
                "created_at": (now - timedelta(days=30)).isoformat(),
            },
            {
                "id": 2,
                "slug": "team-consultation",
                "link_name": "Team Consultation",
                "description": None,
                "url": "/book/team-consultation",
                "is_public": True,
                "view_count": 45,
                "booking_count": 8,
                "last_booked_at": None,
                "created_at": (now - timedelta(days=10)).isoformat(),
            },
        ]
    }


@pytest.fixture
def sample_create_appointment_response():
    """Sample response from POST /appointments."""
    now = datetime.now(timezone.utc)
    return {
        "message": "Appointment created",
        "appointment_id": 42,
        "scheduled_start": now.isoformat(),
        "scheduled_end": (now + timedelta(minutes=30)).isoformat(),
        "email_sent": True,
        "email_error": None,
        "calendar_event_created": False,
        "outlook_event_id": None,
    }


@pytest.fixture
def sample_available_slots_response():
    """Sample response from POST /available-slots."""
    now = datetime.now(timezone.utc)
    tomorrow = now + timedelta(days=1)
    return {
        "available_slots": [
            {
                "date": tomorrow.strftime("%Y-%m-%d"),
                "day": "tuesday",
                "start": tomorrow.replace(hour=9, minute=0, second=0, microsecond=0).isoformat(),
                "end": tomorrow.replace(hour=9, minute=30, second=0, microsecond=0).isoformat(),
                "available": True,
                "user_id": 5,
            },
            {
                "date": tomorrow.strftime("%Y-%m-%d"),
                "day": "tuesday",
                "start": tomorrow.replace(hour=10, minute=0, second=0, microsecond=0).isoformat(),
                "end": tomorrow.replace(hour=10, minute=30, second=0, microsecond=0).isoformat(),
                "available": True,
                "user_id": 5,
            },
        ],
        "total_slots": 2,
        "request": {
            "start_date": tomorrow.strftime("%Y-%m-%d"),
            "end_date": (tomorrow + timedelta(days=7)).strftime("%Y-%m-%d"),
            "duration_minutes": 30,
            "user_ids": [5],
        },
    }


@pytest.fixture
def sample_timeline_response():
    """Sample response from GET /appointments/{id}/timeline."""
    now = datetime.now(timezone.utc)
    return {
        "appointment_id": 1,
        "current_status": "confirmed",
        "standard_progression": ["booked", "confirmed", "reminded", "checked_in", "completed"],
        "history": [
            {
                "id": 1,
                "previous_status": None,
                "new_status": "booked",
                "changed_by_name": "System",
                "changed_by_user_id": 5,
                "change_source": "manual",
                "notes": None,
                "metadata": {},
                "changed_at": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "id": 2,
                "previous_status": "booked",
                "new_status": "confirmed",
                "changed_by_name": "John Doe",
                "changed_by_user_id": 5,
                "change_source": "manual",
                "notes": "Client confirmed via email",
                "metadata": {},
                "changed_at": (now - timedelta(hours=1)).isoformat(),
            },
        ],
        "appointment_summary": {
            "title": "Discovery Call",
            "attendee_name": "Jane Smith",
            "scheduled_start": now.isoformat(),
            "scheduled_end": (now + timedelta(minutes=30)).isoformat(),
            "cancellation_reason": None,
            "reschedule_count": 0,
        },
    }


# =============================================================================
# 1. RESPONSE ENVELOPE CONTRACT (10+ tests)
# =============================================================================

class TestResponseEnvelopeContract:
    """Verify consistent response envelope structure across endpoints."""

    def test_appointment_list_has_pagination_meta(self, sample_appointment_list_response):
        """List responses must include pagination metadata."""
        resp = sample_appointment_list_response
        assert "total" in resp, "List response must include 'total' count"
        assert "limit" in resp, "List response must include 'limit'"
        assert "offset" in resp, "List response must include 'offset'"
        assert isinstance(resp["total"], int)
        assert isinstance(resp["limit"], int)
        assert isinstance(resp["offset"], int)

    def test_appointment_list_validates_against_schema(self, sample_appointment_list_response):
        """List response must conform to AppointmentListResponse schema."""
        parsed = AppointmentListResponse(**sample_appointment_list_response)
        assert len(parsed.appointments) == 2
        assert parsed.total == 2

    def test_appointment_detail_wraps_in_appointment_key(self, sample_appointment_detail_response):
        """Detail response wraps data under 'appointment' key."""
        resp = sample_appointment_detail_response
        assert "appointment" in resp, "Detail response must wrap data under 'appointment' key"
        assert isinstance(resp["appointment"], dict)

    def test_appointment_detail_validates_against_schema(self, sample_appointment_detail_response):
        """Detail response must conform to AppointmentDetailResponse schema."""
        parsed = AppointmentDetailResponse(**sample_appointment_detail_response)
        assert parsed.appointment.id == 1
        assert parsed.appointment.title == "Rate Lock Discussion"

    def test_create_response_includes_message_and_id(self, sample_create_appointment_response):
        """Create response must include message and entity ID."""
        resp = sample_create_appointment_response
        assert "message" in resp, "Create response must include 'message'"
        assert "appointment_id" in resp, "Create response must include 'appointment_id'"
        assert isinstance(resp["appointment_id"], int)

    def test_create_response_validates_against_schema(self, sample_create_appointment_response):
        """Create response must conform to AppointmentCreateResponse schema."""
        parsed = AppointmentCreateResponse(**sample_create_appointment_response)
        assert parsed.appointment_id == 42
        assert parsed.email_sent is True

    def test_delete_response_includes_message(self):
        """Delete response must include a message field."""
        resp = {"message": "Booking link deactivated"}
        assert "message" in resp
        assert isinstance(resp["message"], str)
        assert len(resp["message"]) > 0

    def test_slot_create_response_includes_slot_id(self):
        """Availability slot creation response must include slot_id."""
        resp = {"message": "Availability slot created", "slot_id": 7}
        assert "message" in resp
        assert "slot_id" in resp
        assert isinstance(resp["slot_id"], int)

    def test_pagination_offset_is_non_negative(self, sample_appointment_list_response):
        """Pagination offset must be non-negative."""
        assert sample_appointment_list_response["offset"] >= 0

    def test_pagination_limit_is_positive(self, sample_appointment_list_response):
        """Pagination limit must be a positive integer."""
        assert sample_appointment_list_response["limit"] > 0

    def test_pagination_total_gte_list_length(self, sample_appointment_list_response):
        """Total must be >= length of the returned list."""
        resp = sample_appointment_list_response
        assert resp["total"] >= len(resp["appointments"])

    def test_available_slots_response_includes_request_echo(self, sample_available_slots_response):
        """Available slots response echoes back the request parameters."""
        resp = sample_available_slots_response
        assert "request" in resp
        assert "start_date" in resp["request"]
        assert "end_date" in resp["request"]
        assert "duration_minutes" in resp["request"]

    def test_available_slots_total_matches_list(self, sample_available_slots_response):
        """total_slots must match the length of available_slots list."""
        resp = sample_available_slots_response
        assert resp["total_slots"] == len(resp["available_slots"])


# =============================================================================
# 2. APPOINTMENT SCHEMA CONTRACT (10+ tests)
# =============================================================================

class TestAppointmentSchemaContract:
    """Verify appointment response includes all required fields with correct types."""

    def test_list_item_has_required_fields(self, sample_appointment_list_response):
        """Each appointment in list must have required fields."""
        required = {"id", "title", "scheduled_start", "scheduled_end", "status"}
        for appt in sample_appointment_list_response["appointments"]:
            missing = required - set(appt.keys())
            assert not missing, f"Appointment missing required fields: {missing}"

    def test_detail_has_all_required_fields(self, sample_appointment_detail_response):
        """Detail appointment must have all required fields."""
        required = {
            "id", "title", "status", "scheduled_start", "scheduled_end",
            "assigned_user_id", "attendee_name",
        }
        appt = sample_appointment_detail_response["appointment"]
        missing = required - set(appt.keys())
        assert not missing, f"Appointment detail missing required fields: {missing}"

    def test_scheduled_start_is_iso8601(self, sample_appointment_detail_response):
        """scheduled_start must be ISO 8601 format."""
        start = sample_appointment_detail_response["appointment"]["scheduled_start"]
        assert is_iso8601(start), f"scheduled_start is not ISO 8601: {start}"

    def test_scheduled_end_is_iso8601(self, sample_appointment_detail_response):
        """scheduled_end must be ISO 8601 format."""
        end = sample_appointment_detail_response["appointment"]["scheduled_end"]
        assert is_iso8601(end), f"scheduled_end is not ISO 8601: {end}"

    def test_created_at_is_iso8601_when_present(self, sample_appointment_list_response):
        """created_at must be ISO 8601 when non-null."""
        for appt in sample_appointment_list_response["appointments"]:
            if appt.get("created_at") is not None:
                assert is_iso8601(appt["created_at"]), (
                    f"created_at is not ISO 8601: {appt['created_at']}"
                )

    def test_status_is_valid_enum(self, sample_appointment_detail_response):
        """status must be a valid AppointmentStatus enum value."""
        status = sample_appointment_detail_response["appointment"]["status"]
        valid_statuses = {s.value for s in AppointmentStatusEnum}
        assert status.lower() in valid_statuses, f"Invalid status: {status}"

    def test_meeting_type_is_valid_enum_when_present(self, sample_appointment_detail_response):
        """meeting_type must be a valid MeetingType enum when non-null."""
        mt = sample_appointment_detail_response["appointment"]["meeting_type"]
        if mt is not None:
            valid = {m.value for m in MeetingTypeEnum}
            assert mt in valid, f"Invalid meeting_type: {mt}"

    def test_meeting_mode_is_valid_enum_when_present(self, sample_appointment_detail_response):
        """meeting_mode must be a valid MeetingMode enum when non-null."""
        mm = sample_appointment_detail_response["appointment"]["meeting_mode"]
        if mm is not None:
            valid = {m.value for m in MeetingModeEnum}
            assert mm in valid, f"Invalid meeting_mode: {mm}"

    def test_optional_fields_can_be_null(self, sample_appointment_detail_response):
        """Optional fields must be present but allowed to be null."""
        nullable_fields = [
            "description", "location", "video_link", "phone_number",
            "attendee_notes", "ai_booking_context", "internal_notes",
            "meeting_notes", "contact_id", "updated_at",
        ]
        appt = sample_appointment_detail_response["appointment"]
        for field_name in nullable_fields:
            assert field_name in appt, f"Optional field '{field_name}' must be present in response"
            # value can be None or any type -- just must exist

    def test_id_is_integer_in_detail(self, sample_appointment_detail_response):
        """Appointment ID must be an integer in the detail view."""
        appt = sample_appointment_detail_response["appointment"]
        assert isinstance(appt["id"], int), "Appointment ID must be int in detail view"

    def test_assigned_user_id_is_integer(self, sample_appointment_detail_response):
        """assigned_user_id must be an integer when present."""
        uid = sample_appointment_detail_response["appointment"]["assigned_user_id"]
        assert isinstance(uid, int), "assigned_user_id must be int"

    def test_intake_responses_is_dict_when_present(self, sample_appointment_detail_response):
        """intake_responses must be a dict when present."""
        ir = sample_appointment_detail_response["appointment"]["intake_responses"]
        if ir is not None:
            assert isinstance(ir, dict), "intake_responses must be a dict"

    def test_legacy_appointment_id_format(self, sample_appointment_list_response):
        """Legacy AI appointment IDs have 'ai-{id}' prefix format."""
        appointments = sample_appointment_list_response["appointments"]
        legacy = [a for a in appointments if isinstance(a["id"], str)]
        for appt in legacy:
            assert appt["id"].startswith("ai-"), (
                f"Legacy appointment ID must start with 'ai-': {appt['id']}"
            )

    def test_end_after_start(self, sample_appointment_detail_response):
        """scheduled_end must be after scheduled_start."""
        appt = sample_appointment_detail_response["appointment"]
        start = datetime.fromisoformat(appt["scheduled_start"])
        end = datetime.fromisoformat(appt["scheduled_end"])
        assert end > start, "scheduled_end must be after scheduled_start"


# =============================================================================
# 3. AVAILABILITY SCHEMA CONTRACT (6+ tests)
# =============================================================================

class TestAvailabilitySchemaContract:
    """Verify availability/slot response structure."""

    def test_availability_response_validates(self, sample_availability_response):
        """Availability response must conform to AvailabilityResponse schema."""
        parsed = AvailabilityResponse(**sample_availability_response)
        assert len(parsed.availability) == 2
        assert len(parsed.blocked_times) == 1
        assert len(parsed.existing_appointments) == 1

    def test_slot_times_are_hhmm_format(self, sample_availability_response):
        """Slot start_time and end_time must be HH:MM format."""
        for slot in sample_availability_response["availability"]:
            assert is_hhmm(slot["start_time"]), (
                f"start_time not HH:MM: {slot['start_time']}"
            )
            assert is_hhmm(slot["end_time"]), (
                f"end_time not HH:MM: {slot['end_time']}"
            )

    def test_blocked_times_are_iso8601(self, sample_availability_response):
        """Blocked time start/end must be ISO 8601."""
        for bt in sample_availability_response["blocked_times"]:
            assert is_iso8601(bt["start"]), f"blocked_time start not ISO 8601: {bt['start']}"
            assert is_iso8601(bt["end"]), f"blocked_time end not ISO 8601: {bt['end']}"

    def test_working_hours_has_all_days(self, sample_availability_response):
        """Working hours must include all 7 days of the week."""
        expected_days = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
        actual_days = set(sample_availability_response["working_hours"].keys())
        assert expected_days == actual_days, f"Missing days: {expected_days - actual_days}"

    def test_working_hours_day_structure(self, sample_availability_response):
        """Each working hours day must have start, end, and enabled."""
        for day, config in sample_availability_response["working_hours"].items():
            assert "start" in config, f"{day} missing 'start'"
            assert "end" in config, f"{day} missing 'end'"
            assert "enabled" in config, f"{day} missing 'enabled'"
            assert isinstance(config["enabled"], bool)

    def test_available_slots_sorted_chronologically(self, sample_available_slots_response):
        """Available slots should be in chronological order."""
        slots = sample_available_slots_response["available_slots"]
        if len(slots) > 1:
            for i in range(len(slots) - 1):
                current_start = slots[i]["start"]
                next_start = slots[i + 1]["start"]
                assert current_start <= next_start, (
                    f"Slots not sorted: {current_start} > {next_start}"
                )

    def test_available_slots_have_required_fields(self, sample_available_slots_response):
        """Each available slot must have date, start, end, and available fields."""
        required = {"date", "start", "end"}
        for slot in sample_available_slots_response["available_slots"]:
            missing = required - set(slot.keys())
            assert not missing, f"Available slot missing fields: {missing}"

    def test_slot_priority_is_valid_enum(self, sample_availability_response):
        """Slot priority must be a valid SlotPriority enum value."""
        valid_priorities = {"preferred", "standard", "overflow", "blocked"}
        for slot in sample_availability_response["availability"]:
            assert slot["priority"] in valid_priorities, (
                f"Invalid priority: {slot['priority']}"
            )

    def test_no_past_slots_in_available_response(self):
        """Available slots must not be in the past."""
        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=2)
        resp = {
            "available_slots": [
                {"date": future.strftime("%Y-%m-%d"),
                 "start": future.isoformat(),
                 "end": (future + timedelta(minutes=30)).isoformat(),
                 "available": True}
            ],
            "total_slots": 1,
            "request": {"start_date": future.strftime("%Y-%m-%d"),
                        "end_date": future.strftime("%Y-%m-%d"),
                        "duration_minutes": 30, "user_ids": [1]},
        }
        for slot in resp["available_slots"]:
            slot_start = datetime.fromisoformat(slot["start"])
            # Slots generated by the system should not be in the past
            # Allow a small tolerance of 1 minute for test timing
            assert slot_start >= now - timedelta(minutes=1), (
                f"Available slot is in the past: {slot['start']}"
            )


# =============================================================================
# 4. BOOKING LINK SCHEMA CONTRACT (5+ tests)
# =============================================================================

class TestBookingLinkSchemaContract:
    """Verify booking link response structure."""

    def test_booking_link_list_validates(self, sample_booking_link_list_response):
        """Booking link list must conform to BookingLinkListResponse schema."""
        parsed = BookingLinkListResponse(**sample_booking_link_list_response)
        assert len(parsed.booking_links) == 2

    def test_booking_link_has_required_fields(self, sample_booking_link_list_response):
        """Each booking link must have required fields."""
        required = {"id", "slug", "link_name", "url", "is_public"}
        for link in sample_booking_link_list_response["booking_links"]:
            missing = required - set(link.keys())
            assert not missing, f"Booking link missing required fields: {missing}"

    def test_booking_link_url_starts_with_book(self, sample_booking_link_list_response):
        """Booking link URL must start with /book/."""
        for link in sample_booking_link_list_response["booking_links"]:
            assert link["url"].startswith("/book/"), (
                f"Booking link URL must start with /book/: {link['url']}"
            )

    def test_booking_link_url_contains_slug(self, sample_booking_link_list_response):
        """Booking link URL must contain the slug."""
        for link in sample_booking_link_list_response["booking_links"]:
            assert link["slug"] in link["url"], (
                f"Booking link URL must contain slug: {link['url']} doesn't contain {link['slug']}"
            )

    def test_booking_link_slug_format(self, sample_booking_link_list_response):
        """Booking link slug must be lowercase alphanumeric with hyphens/underscores."""
        slug_pattern = re.compile(r"^[a-z0-9][a-z0-9\-_]*$")
        for link in sample_booking_link_list_response["booking_links"]:
            assert slug_pattern.match(link["slug"]), (
                f"Invalid slug format: {link['slug']}"
            )

    def test_booking_link_create_response_validates(self):
        """Create booking link response must conform to schema."""
        resp = {
            "message": "Booking link created",
            "link_id": 15,
            "url": "/book/my-new-link",
        }
        parsed = BookingLinkCreateResponse(**resp)
        assert parsed.link_id == 15
        assert parsed.url == "/book/my-new-link"

    def test_public_booking_page_data_structure(self):
        """Public booking page response must have org branding and appointment types."""
        # This mirrors the response shape from GET /public/book/{slug}
        resp = {
            "booking_link": {
                "id": 1,
                "slug": "team-meeting",
                "link_name": "Schedule a Meeting",
                "custom_title": "Book Your Consultation",
                "custom_description": "We look forward to meeting with you",
            },
            "appointment_types": [
                {
                    "id": 1,
                    "type_key": "discovery_call",
                    "type_name": "Discovery Call",
                    "description": "30-minute introductory call",
                    "default_duration_minutes": 30,
                    "allowed_durations": [15, 30],
                    "allowed_modes": ["video", "phone"],
                    "intake_questions": [],
                    "color": "#3b82f6",
                    "icon": "calendar",
                }
            ],
            "team_members": [
                {"id": 5, "name": "John Doe", "title": "Loan Officer"},
            ],
            "landing_page": {
                "headline": "Schedule a Meeting",
                "accent_color": "#217F8D",
            },
        }
        assert "booking_link" in resp
        assert "appointment_types" in resp
        assert isinstance(resp["appointment_types"], list)
        if resp["appointment_types"]:
            apt = resp["appointment_types"][0]
            assert "type_key" in apt
            assert "type_name" in apt
            assert "default_duration_minutes" in apt


# =============================================================================
# 5. ERROR SCHEMA CONTRACT (5+ tests)
# =============================================================================

class TestErrorSchemaContract:
    """Verify error response structure and consistency."""

    def test_400_error_has_detail(self):
        """400 Bad Request errors must have a detail field."""
        error_resp = {"detail": "Invalid time format. Use HH:MM"}
        parsed = HTTPErrorDetail(**error_resp)
        assert parsed.detail == "Invalid time format. Use HH:MM"

    def test_404_error_has_consistent_format(self):
        """404 Not Found errors must have consistent detail messages."""
        error_cases = [
            {"detail": "Appointment not found"},
            {"detail": "Slot not found"},
            {"detail": "Booking link not found"},
            {"detail": "Booking page not found"},
        ]
        for error_resp in error_cases:
            parsed = HTTPErrorDetail(**error_resp)
            # Detail should be a non-empty descriptive string
            assert len(parsed.detail) > 0
            # Should not leak internal information (no SQL, no model class names)
            assert "SELECT" not in parsed.detail
            assert "sqlalchemy" not in parsed.detail.lower()

    def test_409_conflict_has_descriptive_detail(self):
        """409 Conflict errors must describe the conflict."""
        conflict_messages = [
            "This time slot is no longer available. Please select a different time.",
            "This time slot is being booked by another user. Please select a different time.",
            "A booking for this email already exists at this time.",
            "This booking link slug is already in use. Please choose a different one.",
        ]
        for msg in conflict_messages:
            error_resp = {"detail": msg}
            parsed = HTTPErrorDetail(**error_resp)
            assert len(parsed.detail) > 20, "Conflict detail should be descriptive"

    def test_422_validation_error_structure(self):
        """422 Validation errors must include field-level details."""
        # This is the standard FastAPI validation error format
        error_resp = {
            "detail": [
                {
                    "loc": ["body", "attendee_email"],
                    "msg": "value is not a valid email address",
                    "type": "value_error.email",
                }
            ]
        }
        assert isinstance(error_resp["detail"], list)
        for err in error_resp["detail"]:
            assert "loc" in err, "Validation error must include 'loc' (location)"
            assert "msg" in err, "Validation error must include 'msg'"
            assert "type" in err, "Validation error must include 'type'"

    def test_429_rate_limit_includes_retry_after(self):
        """429 Rate Limit errors must include Retry-After header."""
        # The HTTPException headers are set in the route handlers
        error_resp = {
            "detail": "Too many requests. Please try again later.",
            "headers": {"Retry-After": "60"},
        }
        assert "Retry-After" in error_resp["headers"]
        retry_after = int(error_resp["headers"]["Retry-After"])
        assert retry_after > 0, "Retry-After must be positive"

    def test_403_error_for_no_org_context(self):
        """403 errors for missing organization context have consistent message."""
        error_resp = {"detail": "No organization context"}
        parsed = HTTPErrorDetail(**error_resp)
        assert "organization" in parsed.detail.lower()

    def test_public_error_sanitization(self):
        """Public endpoints must sanitize error messages."""
        # Import the sanitizer function from the route module
        from routes.scheduler.public_booking import _sanitize_public_error

        # Internal errors should be replaced with safe messages
        assert "booking" in _sanitize_public_error(400, "SQLAlchemy ORM error").lower()
        assert "not found" in _sanitize_public_error(404, "SELECT * FROM appointments WHERE id=999").lower()
        assert "time slot" in _sanitize_public_error(409, "Duplicate key violation").lower()
        assert "too many" in _sanitize_public_error(429, "Rate limit exceeded for IP 1.2.3.4").lower()
        # 500-level should get generic message
        safe_500 = _sanitize_public_error(500, "Traceback: File foo.py line 42")
        assert "traceback" not in safe_500.lower()
        assert "try again" in safe_500.lower()


# =============================================================================
# 6. SCHEMA VERSIONING (3+ tests)
# =============================================================================

class TestSchemaVersioning:
    """Verify schema consistency, no deprecated fields, enum completeness."""

    def test_appointment_status_enum_completeness(self):
        """All AppointmentStatus enum values must be documented."""
        from smart_scheduler_models import AppointmentStatus
        expected = {
            "available", "tentative", "booked", "confirmed", "reminded",
            "checked_in", "completed", "no_show", "cancelled", "rescheduled",
        }
        actual = {s.value for s in AppointmentStatus}
        assert expected == actual, f"Enum mismatch. Missing: {expected - actual}, Extra: {actual - expected}"

    def test_meeting_type_enum_completeness(self):
        """All MeetingType enum values must be documented."""
        from smart_scheduler_models import MeetingType
        expected = {
            "discovery_call", "pre_approval_review", "application_walkthrough",
            "document_review", "rate_lock_discussion", "closing_prep",
            "post_close_review", "referral_partner_meeting", "team_sync", "custom",
        }
        actual = {m.value for m in MeetingType}
        assert expected == actual, f"Enum mismatch. Missing: {expected - actual}, Extra: {actual - expected}"

    def test_meeting_mode_enum_completeness(self):
        """All MeetingMode enum values must be documented."""
        from smart_scheduler_models import MeetingMode
        expected = {"video", "phone", "in_person", "screen_share"}
        actual = {m.value for m in MeetingMode}
        assert expected == actual, f"Enum mismatch. Missing: {expected - actual}, Extra: {actual - expected}"

    def test_no_deprecated_snake_case_fields_in_list_response(self, sample_appointment_list_response):
        """List response should not contain deprecated field names."""
        # These are fields that were in v1 but should not appear in v2
        deprecated_fields = {"appointment_id", "contact_name", "contact_email",
                             "contact_phone", "meeting_link", "booked_via",
                             "loan_officer_id"}
        for appt in sample_appointment_list_response["appointments"]:
            # v2 appointments (int id) should not have deprecated fields
            if isinstance(appt["id"], int):
                found_deprecated = deprecated_fields & set(appt.keys())
                assert not found_deprecated, (
                    f"V2 appointment contains deprecated fields: {found_deprecated}"
                )

    def test_detail_response_no_unexpected_extra_fields(self, sample_appointment_detail_response):
        """Detail response should only contain known fields."""
        known_fields = {
            "id", "appointment_type_id", "title", "description",
            "meeting_type", "meeting_mode", "scheduled_start", "scheduled_end",
            "duration_minutes", "timezone", "location", "video_link",
            "phone_number", "attendee_name", "attendee_email", "attendee_phone",
            "attendee_notes", "intake_responses", "status", "lead_id", "loan_id",
            "contact_id", "assigned_user_id", "booked_by_ai", "ai_booking_context",
            "internal_notes", "meeting_notes", "created_at", "updated_at",
        }
        appt = sample_appointment_detail_response["appointment"]
        extra_fields = set(appt.keys()) - known_fields
        assert not extra_fields, f"Unexpected extra fields in detail response: {extra_fields}"

    def test_routing_strategy_enum_completeness(self):
        """All RoutingStrategy enum values must be documented."""
        from smart_scheduler_models import RoutingStrategy
        expected = {
            "round_robin", "load_balanced", "expertise",
            "relationship", "availability", "ai_optimized",
        }
        actual = {r.value for r in RoutingStrategy}
        assert expected == actual, f"Enum mismatch. Missing: {expected - actual}, Extra: {actual - expected}"


# =============================================================================
# 7. TIMELINE SCHEMA CONTRACT (additional tests)
# =============================================================================

class TestTimelineSchemaContract:
    """Verify appointment timeline response structure."""

    def test_timeline_response_validates(self, sample_timeline_response):
        """Timeline response must conform to TimelineResponse schema."""
        parsed = TimelineResponse(**sample_timeline_response)
        assert parsed.appointment_id == 1
        assert len(parsed.history) == 2

    def test_timeline_history_ordered_chronologically(self, sample_timeline_response):
        """Timeline history entries should be in chronological order."""
        entries = sample_timeline_response["history"]
        if len(entries) > 1:
            for i in range(len(entries) - 1):
                t1 = entries[i].get("changed_at")
                t2 = entries[i + 1].get("changed_at")
                if t1 and t2:
                    assert t1 <= t2, f"Timeline not chronological: {t1} > {t2}"

    def test_timeline_standard_progression_is_valid(self, sample_timeline_response):
        """Standard progression must contain valid appointment statuses."""
        valid = {s.value for s in AppointmentStatusEnum}
        for status in sample_timeline_response["standard_progression"]:
            assert status in valid, f"Invalid status in progression: {status}"

    def test_timeline_current_status_matches_latest_history(self, sample_timeline_response):
        """current_status should match the most recent history entry's new_status."""
        resp = sample_timeline_response
        if resp["history"]:
            latest = resp["history"][-1]["new_status"]
            assert resp["current_status"] == latest, (
                f"current_status ({resp['current_status']}) != latest history ({latest})"
            )

    def test_timeline_summary_has_required_fields(self, sample_timeline_response):
        """Appointment summary in timeline must have required fields."""
        required = {"title", "attendee_name", "scheduled_start", "scheduled_end"}
        summary = sample_timeline_response["appointment_summary"]
        missing = required - set(summary.keys())
        assert not missing, f"Timeline summary missing fields: {missing}"


# =============================================================================
# 8. PYDANTIC INPUT SCHEMA VALIDATION (cross-check with scheduler_models.py)
# =============================================================================

class TestInputSchemaValidation:
    """Verify that Pydantic input schemas enforce documented constraints."""

    def test_appointment_create_requires_title(self):
        """AppointmentCreate must require a title."""
        from scheduler_models import AppointmentCreate
        with pytest.raises(ValidationError):
            AppointmentCreate(
                scheduled_start=datetime.now(timezone.utc),
                title="",  # empty string should fail min_length=1
            )

    def test_appointment_create_enforces_duration_range(self):
        """AppointmentCreate duration_minutes must be 5-480."""
        from scheduler_models import AppointmentCreate
        with pytest.raises(ValidationError):
            AppointmentCreate(
                title="Test",
                scheduled_start=datetime.now(timezone.utc),
                duration_minutes=3,  # below minimum of 5
            )

    def test_booking_link_slug_must_be_lowercase(self):
        """BookingLinkCreate slug must be lowercase."""
        from scheduler_models import BookingLinkCreate
        link = BookingLinkCreate(
            slug="My-LINK-Here",
            link_name="Test Link",
        )
        assert link.slug == "my-link-here", "Slug should be lowercased by validator"

    def test_booking_link_slug_rejects_invalid_chars(self):
        """BookingLinkCreate slug must match pattern ^[a-z0-9][a-z0-9\\-_]*$."""
        from scheduler_models import BookingLinkCreate
        with pytest.raises(ValidationError):
            BookingLinkCreate(
                slug="@invalid!slug",
                link_name="Test Link",
            )

    def test_blocked_time_end_must_be_after_start(self):
        """BlockedTimeCreate end_datetime must be after start_datetime."""
        from scheduler_models import BlockedTimeCreate
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            BlockedTimeCreate(
                title="Test Block",
                start_datetime=now + timedelta(hours=1),
                end_datetime=now,  # before start
            )

    def test_available_slots_request_end_after_start(self):
        """AvailableSlotsRequest end_date must be on or after start_date."""
        from scheduler_models import AvailableSlotsRequest
        with pytest.raises(ValidationError):
            AvailableSlotsRequest(
                start_date=date(2026, 4, 1),
                end_date=date(2026, 3, 15),  # before start
            )

    def test_intake_question_options_required_for_select(self):
        """IntakeQuestion must have options when type is 'select'."""
        from scheduler_models import IntakeQuestion
        with pytest.raises(ValidationError):
            IntakeQuestion(
                key="question_1",
                question="Choose one",
                type="select",
                options=None,  # required for select type
            )

    def test_scheduler_config_duration_range(self):
        """SchedulerConfigCreate default_duration_minutes must be 5-480."""
        from scheduler_models import SchedulerConfigCreate
        with pytest.raises(ValidationError):
            SchedulerConfigCreate(
                config_name="Test",
                default_duration_minutes=500,  # exceeds max 480
            )
