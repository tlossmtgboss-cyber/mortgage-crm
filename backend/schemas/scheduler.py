"""
Scheduler Pydantic Schemas
==========================
All Pydantic schemas for the scheduler module:
  - Input / request models (originally in scheduler_models.py)
  - OpenAPI response models

Organized by functional area:
  A. INPUT / REQUEST SCHEMAS
     1. Intake Questions
     2. Scheduler Configuration (Create / Update)
     3. Landing Page Settings
     4. Appointment Types (Create / Update / Reorder)
     5. Availability Slots (Create / Update)
     6. Appointments (Create / Update / Cancel)
     7. Blocked Time
     8. Booking Links
     9. Available Slots Requests
     10. Public Booking Requests
     11. Recommendations / Misc

  B. RESPONSE / OPENAPI SCHEMAS
     1. Common / Shared models
     2. Scheduler Configuration
     3. Appointment Types
     4. Appointments
     5. Availability & Slots
     6. Booking Links
     7. Blocked Time
     8. Public Booking
     9. Intelligence / Analytics
     10. Email & Notifications
     11. Settings
"""

from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, EmailStr, Field, validator


# =============================================================================
# SHARED VALIDATORS
# =============================================================================

_RESERVED_SLUGS = {
    "api", "admin", "static", "reports", "public", "health", "metrics",
    "settings", "login", "logout", "register", "sitemap", "robots",
    "favicon", "calendar", "appointments", "book", "embed",
}


def _validate_timezone_string(v: str) -> str:
    """Validate that a timezone string is a recognized IANA timezone."""
    if v:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(v)
        except (KeyError, Exception):
            raise ValueError(f"Invalid timezone: '{v}'")
    return v


# #############################################################################
# A. INPUT / REQUEST SCHEMAS
#    (Consolidated from scheduler_models.py)
# #############################################################################

# =============================================================================
# A1. INTAKE QUESTIONS
# =============================================================================

class IntakeQuestion(BaseModel):
    """Schema for a single intake question on an appointment type."""
    key: str = Field(..., min_length=1, max_length=100)
    question: str = Field(..., min_length=1, max_length=500)
    type: str = Field(..., min_length=1, max_length=50)  # text, select, boolean, date
    options: Optional[List[str]] = None  # Required when type is 'select'
    required: bool = False

    @validator('options')
    def options_required_for_select(cls, v, values):
        if values.get('type') == 'select' and not v:
            raise ValueError("options must be provided when question type is 'select'")
        return v


# =============================================================================
# A2. SCHEDULER CONFIGURATION (Create / Update)
# =============================================================================

class WorkingHoursDay(BaseModel):
    start: str  # "09:00"
    end: str    # "17:00"
    enabled: bool = True


class SchedulerConfigCreate(BaseModel):
    config_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    timezone: str = "America/Chicago"
    default_duration_minutes: int = Field(30, ge=5, le=480)
    buffer_before_minutes: int = 5
    buffer_after_minutes: int = 5
    min_notice_hours: int = 2
    max_advance_days: int = 60
    max_meetings_per_day: int = 8
    working_hours: Optional[Dict[str, WorkingHoursDay]] = None
    routing_strategy: Optional[str] = "relationship"
    ai_scheduling_enabled: bool = True

    _validate_tz = validator('timezone', allow_reuse=True)(_validate_timezone_string)


class SchedulerConfigUpdate(BaseModel):
    config_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    timezone: Optional[str] = None
    default_duration_minutes: Optional[int] = Field(None, ge=5, le=480)
    buffer_before_minutes: Optional[int] = None
    buffer_after_minutes: Optional[int] = None
    min_notice_hours: Optional[int] = None
    max_advance_days: Optional[int] = None
    max_meetings_per_day: Optional[int] = None
    working_hours: Optional[Dict[str, WorkingHoursDay]] = None
    routing_strategy: Optional[str] = None
    ai_scheduling_enabled: Optional[bool] = None
    auto_reschedule_enabled: Optional[bool] = None
    smart_reminders_enabled: Optional[bool] = None
    is_active: Optional[bool] = None

    _validate_tz = validator('timezone', allow_reuse=True, pre=True)(_validate_timezone_string)


# =============================================================================
# A3. LANDING PAGE SETTINGS
# =============================================================================

class LandingPageSettings(BaseModel):
    logo_url: Optional[str] = ''
    profile_picture_url: Optional[str] = ''
    video_url: Optional[str] = ''
    video_type: Optional[str] = 'youtube'  # youtube, vimeo, loom, custom
    headline: Optional[str] = 'Schedule a Meeting'
    subheadline: Optional[str] = 'Choose a time that works for you'
    description: Optional[str] = ''
    show_profile: Optional[bool] = True
    profile_name: Optional[str] = ''
    profile_title: Optional[str] = ''
    profile_bio: Optional[str] = ''
    accent_color: Optional[str] = '#217F8D'
    background_style: Optional[str] = 'white'  # white, light, gradient
    show_company_logo: Optional[bool] = True
    show_social_proof: Optional[bool] = False
    testimonial_text: Optional[str] = ''
    testimonial_author: Optional[str] = ''


# =============================================================================
# A4. APPOINTMENT TYPES (Create / Update / Reorder)
# =============================================================================

class AppointmentTypeCreate(BaseModel):
    type_key: str = Field(..., min_length=1, max_length=100)
    type_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    meeting_type: Optional[str] = "custom"
    default_duration_minutes: int = Field(30, ge=15, le=480)
    allowed_durations: List[int] = [15, 30, 45, 60]
    allowed_modes: List[str] = ["video", "phone"]
    default_mode: Optional[str] = None  # Default meeting mode (phone, video, in_person, screen_share)
    buffer_before: int = Field(0, ge=0, le=60)
    buffer_after: int = Field(0, ge=0, le=60)
    max_per_day: Optional[int] = Field(None, ge=1, le=50)
    requires_loan_id: bool = False
    requires_lead_id: bool = False
    requires_intake: bool = False
    intake_questions: List[IntakeQuestion] = []
    color: str = "#3b82f6"
    icon: str = "calendar"
    is_public: bool = True
    public_slug: Optional[str] = None

    @validator('default_duration_minutes')
    def validate_duration(cls, v):
        if v < 15 or v > 480:
            raise ValueError('Duration must be between 15 and 480 minutes')
        return v

    @validator('buffer_before', 'buffer_after')
    def validate_buffer(cls, v):
        if v < 0 or v > 60:
            raise ValueError('Buffer must be between 0 and 60 minutes')
        return v

    @validator('color')
    def validate_color(cls, v):
        import re
        if v and not re.match(r'^#[0-9a-fA-F]{6}$', v):
            raise ValueError('Color must be a valid hex color (e.g., #3b82f6)')
        return v

    @validator('default_mode')
    def validate_default_mode(cls, v):
        valid_modes = {'video', 'phone', 'in_person', 'screen_share'}
        if v is not None and v not in valid_modes:
            raise ValueError(f'Meeting mode must be one of: {", ".join(valid_modes)}')
        return v

    @validator('intake_questions', each_item=False)
    def serialize_intake_questions(cls, v):
        """Convert IntakeQuestion models to dicts for JSON column compatibility."""
        return [q.model_dump(exclude_none=True) if isinstance(q, IntakeQuestion) else q for q in v]


class AppointmentTypeUpdate(BaseModel):
    type_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    default_duration_minutes: Optional[int] = Field(None, ge=15, le=480)
    allowed_durations: Optional[List[int]] = None
    allowed_modes: Optional[List[str]] = None
    default_mode: Optional[str] = None
    buffer_before: Optional[int] = Field(None, ge=0, le=60)
    buffer_after: Optional[int] = Field(None, ge=0, le=60)
    max_per_day: Optional[int] = Field(None, ge=1, le=50)
    requires_intake: Optional[bool] = None
    intake_questions: Optional[List[IntakeQuestion]] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None
    display_order: Optional[int] = None

    @validator('color')
    def validate_color(cls, v):
        import re
        if v is not None and not re.match(r'^#[0-9a-fA-F]{6}$', v):
            raise ValueError('Color must be a valid hex color (e.g., #3b82f6)')
        return v

    @validator('default_mode')
    def validate_default_mode(cls, v):
        valid_modes = {'video', 'phone', 'in_person', 'screen_share'}
        if v is not None and v not in valid_modes:
            raise ValueError(f'Meeting mode must be one of: {", ".join(valid_modes)}')
        return v

    @validator('intake_questions', pre=False)
    def serialize_intake_questions(cls, v):
        """Convert IntakeQuestion models to dicts for JSON column compatibility."""
        if v is None:
            return v
        return [q.model_dump(exclude_none=True) if isinstance(q, IntakeQuestion) else q for q in v]


class AppointmentTypeReorder(BaseModel):
    """Request body for reordering appointment types."""
    ordered_ids: List[int] = Field(..., min_length=1)


# =============================================================================
# A5. AVAILABILITY SLOTS (Create / Update)
# =============================================================================

class AvailabilitySlotCreate(BaseModel):
    day_of_week: Optional[str] = None
    specific_date: Optional[date] = None
    start_time: str  # "09:00"
    end_time: str    # "17:00"
    priority: str = "standard"
    is_recurring: bool = True
    allowed_meeting_types: List[str] = []
    max_bookings: int = 1


class AvailabilitySlotUpdate(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    priority: Optional[str] = None
    is_active: Optional[bool] = None
    allowed_meeting_types: Optional[List[str]] = None


# =============================================================================
# A6. APPOINTMENTS (Create / Update / Cancel)
# =============================================================================

class AppointmentCreate(BaseModel):
    appointment_type_id: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    meeting_type: Optional[str] = "custom"
    meeting_mode: str = "video"
    scheduled_start: datetime
    duration_minutes: int = Field(30, ge=5, le=480)
    timezone: str = "America/Chicago"

    # Attendee info (for external bookings)
    attendee_name: Optional[str] = Field(None, min_length=1, max_length=200)
    attendee_email: Optional[EmailStr] = None
    attendee_phone: Optional[str] = Field(None, max_length=20)
    attendee_notes: Optional[str] = Field(None, max_length=2000)

    # Related entities
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    contact_id: Optional[int] = None
    assigned_user_id: Optional[int] = None

    # Intake responses
    intake_responses: Dict = {}

    # AI context
    booked_by_ai: bool = False
    ai_booking_context: Optional[Dict] = None

    _validate_tz = validator('timezone', allow_reuse=True)(_validate_timezone_string)


class AppointmentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(None, ge=5, le=480)
    meeting_mode: Optional[str] = None
    location: Optional[str] = Field(None, max_length=500)
    video_link: Optional[str] = Field(None, max_length=2000)
    status: Optional[str] = None
    cancellation_reason: Optional[str] = Field(None, max_length=2000)
    internal_notes: Optional[str] = Field(None, max_length=5000)
    meeting_notes: Optional[str] = Field(None, max_length=5000)
    attendee_name: Optional[str] = Field(None, min_length=1, max_length=200)
    attendee_email: Optional[EmailStr] = None
    attendee_phone: Optional[str] = Field(None, max_length=20)
    attendee_notes: Optional[str] = Field(None, max_length=2000)
    send_notification: Optional[bool] = True  # Send email/SMS on update


class CancelAppointmentRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=2000)


# =============================================================================
# A7. BLOCKED TIME
# =============================================================================

class BlockedTimeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    block_type: str = "custom"
    start_datetime: datetime
    end_datetime: datetime
    all_day: bool = False
    is_recurring: bool = False
    recurrence_pattern: Optional[Dict] = None
    applies_to_all_users: bool = False

    @validator('end_datetime')
    def end_after_start(cls, v, values):
        if 'start_datetime' in values and v <= values['start_datetime']:
            raise ValueError('end_datetime must be after start_datetime')
        return v


# =============================================================================
# A8. BOOKING LINKS
# =============================================================================

class BookingLinkCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=100, pattern=r'^[a-z0-9][a-z0-9\-_]*$')
    link_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    appointment_type_ids: List[int] = []
    single_appointment_type_id: Optional[int] = None
    is_public: bool = True
    custom_title: Optional[str] = Field(None, max_length=200)
    custom_description: Optional[str] = Field(None, max_length=2000)
    routing_strategy: str = "relationship"
    assigned_users: List[int] = []
    expires_at: Optional[datetime] = Field(None, description="When the booking link expires (ISO 8601). Defaults to 90 days from creation if not specified.")

    @validator('slug', pre=True)
    def lowercase_slug(cls, v):
        if isinstance(v, str):
            v = v.lower()
        return v

    @validator('slug')
    def validate_slug_not_reserved(cls, v):
        if v and v.strip() in _RESERVED_SLUGS:
            raise ValueError(f"Slug '{v}' is reserved and cannot be used")
        return v


# =============================================================================
# A9. AVAILABLE SLOTS REQUESTS
# =============================================================================

class AvailableSlotsRequest(BaseModel):
    appointment_type_id: Optional[int] = None
    meeting_type: Optional[str] = None
    duration_minutes: int = Field(30, ge=5, le=480)
    start_date: date
    end_date: date
    timezone: str = "America/Chicago"
    user_ids: Optional[List[int]] = None  # Filter to specific users

    _validate_tz = validator('timezone', allow_reuse=True)(_validate_timezone_string)

    @validator('end_date')
    def end_date_after_start(cls, v, values):
        if 'start_date' in values and v < values['start_date']:
            raise ValueError('end_date must be on or after start_date')
        return v


class PublicAvailableSlotsRequest(BaseModel):
    """Request model for website demo scheduler"""
    start_date: date
    end_date: date
    duration_minutes: int = Field(30, ge=5, le=480)
    appointment_type: str = Field("platform-demo", max_length=100)
    organization_id: Optional[int] = Field(None, description="Organization ID for multi-tenant isolation")

    @validator('end_date')
    def end_date_after_start(cls, v, values):
        if 'start_date' in values and v < values['start_date']:
            raise ValueError('end_date must be on or after start_date')
        return v


# =============================================================================
# A10. PUBLIC BOOKING REQUESTS
# =============================================================================

class PublicBookingConfirmRequest(BaseModel):
    appointment_type_id: int
    start_time: datetime
    duration_minutes: int = Field(30, ge=5, le=480)
    attendee_name: str = Field(..., min_length=1, max_length=200)
    attendee_email: EmailStr
    attendee_phone: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=2000)
    user_ids: List[int] = []  # Empty = any available user
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    meeting_mode: Optional[str] = None  # video, phone, in_person
    team_member_id: Optional[int] = None
    team_member_name: Optional[str] = Field(None, max_length=200)
    cf_turnstile_token: Optional[str] = Field(None, max_length=4096)  # Cloudflare Turnstile bot protection


class WebsiteDemoBookingRequest(BaseModel):
    """Request model for website demo booking confirmation"""
    start_time: datetime  # ISO datetime
    duration_minutes: int = Field(30, ge=5, le=480)
    attendee_name: str = Field(..., min_length=1, max_length=200)
    attendee_email: EmailStr
    attendee_phone: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=500)
    meeting_mode: str = Field("video", max_length=20)
    organization_id: Optional[int] = Field(None, description="Organization ID for multi-tenant isolation")


# =============================================================================
# A11. RECOMMENDATIONS / MISC
# =============================================================================

class SlotRecommendation(BaseModel):
    slot_start: datetime
    slot_end: datetime
    user_id: int
    user_name: str
    score: float  # AI-calculated score
    reasons: List[str]  # Why this slot is recommended


class AIBookingContext(BaseModel):
    """Validated schema for AI booking decision context."""
    decision_source: Optional[str] = None
    confidence_score: Optional[float] = None
    decision_reason: Optional[str] = None
    matched_rules: Optional[List[str]] = None
    alternative_slots_considered: Optional[int] = None
    pipeline_trigger: Optional[str] = None

    class Config:
        extra = "allow"  # Allow forward-compatible extra fields


# #############################################################################
# B. RESPONSE / OPENAPI SCHEMAS
# #############################################################################


# =============================================================================
# 1. COMMON / SHARED MODELS
# =============================================================================

class ErrorDetail(BaseModel):
    """Standard error response body."""
    detail: str = Field(..., description="Human-readable error message")

    class Config:
        json_schema_extra = {
            "example": {"detail": "Resource not found"}
        }


class MessageResponse(BaseModel):
    """Simple success message response."""
    message: str = Field(..., description="Human-readable success message")

    class Config:
        json_schema_extra = {
            "example": {"message": "Operation completed successfully"}
        }


class MessageWithIdResponse(BaseModel):
    """Success message with a created resource ID."""
    message: str = Field(..., description="Human-readable success message")
    config_id: Optional[int] = Field(None, description="Created/updated config ID")
    type_id: Optional[int] = Field(None, description="Created appointment type ID")
    link_id: Optional[int] = Field(None, description="Created booking link ID")
    slot_id: Optional[int] = Field(None, description="Created availability slot ID")
    blocked_time_id: Optional[int] = Field(None, description="Created blocked time ID")
    url: Optional[str] = Field(None, description="URL of created resource (e.g., booking link)")


class PaginationMeta(BaseModel):
    """Pagination metadata for list endpoints."""
    total: int = Field(..., description="Total number of records matching the filter")
    page: int = Field(..., description="Current page number (1-based)")
    per_page: int = Field(..., description="Records per page")
    total_pages: int = Field(..., description="Total number of pages")

    class Config:
        json_schema_extra = {
            "example": {
                "total": 42,
                "page": 1,
                "per_page": 20,
                "total_pages": 3,
            }
        }


class SuccessEnvelope(BaseModel):
    """Standard envelope for settings/intelligence endpoints."""
    status: str = Field("success", description="Response status")
    data: Any = Field(..., description="Response payload")
    message: str = Field("", description="Human-readable message")


# =============================================================================
# 2. SCHEDULER CONFIGURATION
# =============================================================================

class WorkingHoursDaySchema(BaseModel):
    """Working hours for a single day."""
    start: str = Field(..., description="Start time in HH:MM format", example="09:00")
    end: str = Field(..., description="End time in HH:MM format", example="17:00")
    enabled: bool = Field(True, description="Whether this day is a working day")


class SchedulerConfigDefaults(BaseModel):
    """Default scheduler configuration values."""
    timezone: str = Field("America/Chicago", description="IANA timezone identifier")
    default_duration_minutes: int = Field(30, description="Default appointment duration in minutes")
    buffer_before_minutes: int = Field(5, description="Buffer time before appointments")
    buffer_after_minutes: int = Field(5, description="Buffer time after appointments")
    min_notice_hours: int = Field(2, description="Minimum hours notice for new bookings")
    max_advance_days: int = Field(60, description="Maximum days in advance for bookings")
    max_meetings_per_day: int = Field(8, description="Maximum appointments per day")
    working_hours: Dict[str, WorkingHoursDaySchema] = Field(
        ..., description="Working hours by day of week"
    )


class SchedulerConfigData(BaseModel):
    """Full scheduler configuration record."""
    id: int = Field(..., description="Configuration ID")
    config_name: str = Field(..., description="Configuration display name")
    description: Optional[str] = Field(None, description="Configuration description")
    timezone: str = Field(..., description="IANA timezone identifier", example="America/Chicago")
    default_duration_minutes: int = Field(..., description="Default meeting duration")
    buffer_before_minutes: int = Field(..., description="Buffer before meetings (minutes)")
    buffer_after_minutes: int = Field(..., description="Buffer after meetings (minutes)")
    min_notice_hours: int = Field(..., description="Minimum notice for bookings (hours)")
    max_advance_days: int = Field(..., description="Maximum advance booking window (days)")
    max_meetings_per_day: int = Field(..., description="Daily meeting cap")
    working_hours: Dict[str, WorkingHoursDaySchema] = Field(
        ..., description="Working hours by day of week"
    )
    routing_strategy: str = Field(..., description="Appointment routing strategy", example="relationship")
    ai_scheduling_enabled: bool = Field(..., description="Whether AI scheduling is active")
    is_active: bool = Field(..., description="Whether this configuration is active")
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO 8601)")
    updated_at: Optional[str] = Field(None, description="Last update timestamp (ISO 8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "config_name": "Default Schedule",
                "description": "Primary scheduling configuration",
                "timezone": "America/Chicago",
                "default_duration_minutes": 30,
                "buffer_before_minutes": 5,
                "buffer_after_minutes": 5,
                "min_notice_hours": 2,
                "max_advance_days": 60,
                "max_meetings_per_day": 8,
                "working_hours": {
                    "monday": {"start": "09:00", "end": "17:00", "enabled": True},
                    "friday": {"start": "09:00", "end": "17:00", "enabled": True},
                },
                "routing_strategy": "round_robin",
                "ai_scheduling_enabled": True,
                "is_active": True,
                "created_at": "2026-03-01T10:00:00Z",
                "updated_at": "2026-03-10T15:30:00Z",
            }
        }


class SchedulerConfigResponse(BaseModel):
    """Response for GET /config."""
    config: Optional[SchedulerConfigData] = Field(
        None, description="User's scheduler configuration, or null if not yet created"
    )
    defaults: Optional[SchedulerConfigDefaults] = Field(
        None, description="Default values (returned when no config exists)"
    )


# =============================================================================
# 3. APPOINTMENT TYPES
# =============================================================================

class IntakeQuestionSchema(BaseModel):
    """Pre-appointment intake question definition."""
    key: str = Field(..., description="Unique question identifier", example="loan_type")
    question: str = Field(..., description="Question text displayed to attendee")
    type: str = Field(..., description="Input type: text, select, boolean, date")
    options: Optional[List[str]] = Field(None, description="Options for 'select' type")
    required: bool = Field(False, description="Whether the question is mandatory")


class AppointmentTypeSchema(BaseModel):
    """Appointment type definition."""
    id: int = Field(..., description="Appointment type ID")
    type_key: str = Field(..., description="Unique machine-readable key", example="discovery_call")
    type_name: str = Field(..., description="Human-readable name", example="Discovery Call")
    description: Optional[str] = Field(None, description="Detailed description for attendees")
    meeting_type: str = Field("custom", description="Category: consultation, discovery_call, etc.")
    default_duration_minutes: int = Field(30, description="Default duration in minutes")
    allowed_durations: List[int] = Field(
        default=[15, 30, 45, 60],
        description="Selectable duration options (minutes)"
    )
    allowed_modes: List[str] = Field(
        default=["video", "phone"],
        description="Allowed meeting modes"
    )
    requires_loan_id: bool = Field(False, description="Require a loan association")
    requires_lead_id: bool = Field(False, description="Require a lead association")
    intake_questions: List[IntakeQuestionSchema] = Field(
        default=[], description="Pre-appointment intake questions"
    )
    color: str = Field("#3b82f6", description="Calendar display color (hex)")
    icon: str = Field("calendar", description="Display icon name")
    is_public: bool = Field(True, description="Whether visible on public booking pages")
    public_slug: Optional[str] = Field(None, description="Public URL slug")
    is_active: bool = Field(True, description="Whether this type is active")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "type_key": "discovery_call",
                "type_name": "Discovery Call",
                "description": "Initial consultation to discuss mortgage options",
                "meeting_type": "discovery_call",
                "default_duration_minutes": 30,
                "allowed_durations": [15, 30, 45, 60],
                "allowed_modes": ["video", "phone"],
                "requires_loan_id": False,
                "requires_lead_id": False,
                "intake_questions": [],
                "color": "#3b82f6",
                "icon": "calendar",
                "is_public": True,
                "public_slug": "1-discovery_call",
                "is_active": True,
            }
        }


class AppointmentTypeListResponse(BaseModel):
    """Response for GET /appointment-types."""
    appointment_types: List[AppointmentTypeSchema] = Field(
        ..., description="List of appointment types"
    )
    source: str = Field(
        ..., description="Data source: 'database' or 'defaults'", example="database"
    )


# =============================================================================
# 4. APPOINTMENTS
# =============================================================================

class AppointmentTypeDetail(BaseModel):
    """Embedded appointment type info within an appointment."""
    id: int = Field(..., description="Appointment type ID")
    type_key: str = Field(..., description="Appointment type key")
    type_name: str = Field(..., description="Appointment type display name")
    color: Optional[str] = Field(None, description="Calendar color")


class AppointmentResponse(BaseModel):
    """Full appointment record."""
    id: int = Field(..., description="Unique appointment ID")
    title: str = Field(..., description="Appointment title/subject")
    description: Optional[str] = Field(None, description="Detailed description or notes")
    status: str = Field(..., description="Current status: booked, tentative, completed, cancelled, no_show")
    meeting_type: Optional[str] = Field(None, description="Meeting category")
    meeting_mode: Optional[str] = Field(None, description="Meeting mode: video, phone, in_person")
    scheduled_start: str = Field(..., description="Start time (ISO 8601)")
    scheduled_end: str = Field(..., description="End time (ISO 8601)")
    duration_minutes: Optional[int] = Field(None, description="Duration in minutes")
    timezone: Optional[str] = Field(None, description="Timezone for this appointment")
    attendee_name: Optional[str] = Field(None, description="Attendee full name")
    attendee_email: Optional[str] = Field(None, description="Attendee email address")
    attendee_phone: Optional[str] = Field(None, description="Attendee phone number")
    attendee_notes: Optional[str] = Field(None, description="Notes from the attendee")
    location: Optional[str] = Field(None, description="Physical location or address")
    video_link: Optional[str] = Field(None, description="Video conference URL")
    assigned_user_id: Optional[int] = Field(None, description="Assigned loan officer user ID")
    assigned_user_name: Optional[str] = Field(None, description="Assigned LO display name")
    lead_id: Optional[int] = Field(None, description="Linked CRM lead ID")
    loan_id: Optional[int] = Field(None, description="Linked loan ID")
    appointment_type: Optional[AppointmentTypeDetail] = Field(
        None, description="Appointment type details"
    )
    booked_by_ai: bool = Field(False, description="Whether booked by AI agent")
    internal_notes: Optional[str] = Field(None, description="Internal team notes")
    cancellation_reason: Optional[str] = Field(None, description="Reason for cancellation")
    version: Optional[int] = Field(None, description="Optimistic concurrency version")
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO 8601)")
    updated_at: Optional[str] = Field(None, description="Last update timestamp (ISO 8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 42,
                "title": "Mortgage Consultation",
                "description": "Initial consultation to discuss refinancing options",
                "status": "booked",
                "meeting_type": "consultation",
                "meeting_mode": "video",
                "scheduled_start": "2026-03-15T10:00:00-05:00",
                "scheduled_end": "2026-03-15T10:30:00-05:00",
                "duration_minutes": 30,
                "timezone": "America/Chicago",
                "attendee_name": "John Doe",
                "attendee_email": "john.doe@example.com",
                "assigned_user_id": 5,
                "assigned_user_name": "Sarah Johnson",
                "lead_id": 123,
                "booked_by_ai": False,
                "version": 1,
                "created_at": "2026-03-10T08:30:00Z",
            }
        }


class AppointmentListResponse(BaseModel):
    """Response for GET /appointments."""
    appointments: List[AppointmentResponse] = Field(
        ..., description="List of appointments"
    )
    total: int = Field(..., description="Total matching appointments")
    page: int = Field(1, description="Current page")
    per_page: int = Field(20, description="Items per page")


class AppointmentCreateResponse(BaseModel):
    """Response for POST /appointments."""
    message: str = Field(..., description="Success message")
    appointment_id: int = Field(..., description="Created appointment ID")
    video_link: Optional[str] = Field(None, description="Auto-generated video conference link")
    licensing_warning: Optional[str] = Field(None, description="LO licensing advisory warning")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Appointment created and confirmation sent",
                "appointment_id": 42,
                "video_link": "https://meet.example.com/abc123",
            }
        }


class AppointmentCancelResponse(BaseModel):
    """Response for POST /appointments/{id}/cancel."""
    message: str = Field(..., description="Cancellation confirmation message")
    appointment_id: int = Field(..., description="Cancelled appointment ID")


# =============================================================================
# 5. AVAILABILITY & SLOTS
# =============================================================================

class AvailabilitySlotSchema(BaseModel):
    """A configured availability slot."""
    id: int = Field(..., description="Slot ID")
    day_of_week: Optional[str] = Field(None, description="Day of week for recurring slots")
    specific_date: Optional[str] = Field(None, description="Specific date (YYYY-MM-DD)")
    start_time: str = Field(..., description="Start time (HH:MM)", example="09:00")
    end_time: str = Field(..., description="End time (HH:MM)", example="17:00")
    priority: str = Field("standard", description="Slot priority: preferred, standard, overflow")
    is_recurring: bool = Field(True, description="Whether this slot recurs weekly")


class BlockedTimeSchema(BaseModel):
    """A blocked time period."""
    id: int = Field(..., description="Blocked time ID")
    title: str = Field(..., description="Block title (e.g., 'Lunch Break')")
    start: str = Field(..., description="Block start (ISO 8601)")
    end: str = Field(..., description="Block end (ISO 8601)")
    all_day: bool = Field(False, description="Whether this is an all-day block")
    block_type: Optional[str] = Field(None, description="Block type: lunch, ooo, custom, etc.")


class ExistingAppointmentSlim(BaseModel):
    """Slim appointment representation for availability overlays."""
    id: int = Field(..., description="Appointment ID")
    title: str = Field(..., description="Appointment title")
    start: str = Field(..., description="Start time (ISO 8601)")
    end: str = Field(..., description="End time (ISO 8601)")
    status: str = Field("booked", description="Appointment status")


class AvailabilityResponse(BaseModel):
    """Response for GET /availability."""
    availability: List[AvailabilitySlotSchema] = Field(
        ..., description="Custom availability slots"
    )
    working_hours: Dict[str, Any] = Field(
        ..., description="Working hours configuration"
    )
    blocked_times: List[BlockedTimeSchema] = Field(
        ..., description="Blocked time periods"
    )
    existing_appointments: List[ExistingAppointmentSlim] = Field(
        ..., description="Existing appointments in the date range"
    )


class AvailableSlotResponse(BaseModel):
    """A single bookable time slot."""
    date: str = Field(..., description="Date (YYYY-MM-DD)", example="2026-03-15")
    start_time: str = Field(..., description="Slot start (ISO 8601)")
    end_time: str = Field(..., description="Slot end (ISO 8601)")
    user_id: int = Field(..., description="Available user/LO ID")
    user_name: Optional[str] = Field(None, description="User display name")
    available: bool = Field(True, description="Whether slot is bookable")


class AvailableSlotsListResponse(BaseModel):
    """Response for POST /available-slots."""
    slots: List[AvailableSlotResponse] = Field(..., description="Available time slots")
    total_slots: int = Field(..., description="Total number of available slots")


class AIRecommendedSlot(BaseModel):
    """An AI-recommended time slot with scoring."""
    slot_start: str = Field(..., description="Recommended start time (ISO 8601)")
    slot_end: str = Field(..., description="Recommended end time (ISO 8601)")
    user_id: int = Field(..., description="Recommended loan officer ID")
    user_name: str = Field(..., description="Loan officer name")
    score: float = Field(
        ..., description="AI-calculated recommendation score (0.0-1.0)", ge=0.0, le=1.0
    )
    reasons: List[str] = Field(..., description="Explanation of why this slot is recommended")

    class Config:
        json_schema_extra = {
            "example": {
                "slot_start": "2026-03-15T10:00:00-05:00",
                "slot_end": "2026-03-15T10:30:00-05:00",
                "user_id": 5,
                "user_name": "Sarah Johnson",
                "score": 0.92,
                "reasons": [
                    "High show rate for Tuesday morning slots",
                    "LO has expertise in refinancing",
                    "Lead source matches LO's conversion strengths",
                ],
            }
        }


# =============================================================================
# 6. BOOKING LINKS
# =============================================================================

class BookingLinkSchema(BaseModel):
    """A booking link record."""
    id: int = Field(..., description="Booking link ID")
    slug: str = Field(..., description="URL-friendly identifier", example="sarah-johnson")
    link_name: str = Field(..., description="Display name for the link")
    description: Optional[str] = Field(None, description="Link description")
    url: str = Field(..., description="Relative booking URL", example="/book/sarah-johnson")
    is_public: bool = Field(True, description="Whether publicly accessible")
    user_id: Optional[int] = Field(None, description="Owner user ID")
    owner_name: Optional[str] = Field(None, description="Owner display name")
    view_count: Optional[int] = Field(None, description="Number of page views")
    booking_count: Optional[int] = Field(None, description="Number of completed bookings")
    last_booked_at: Optional[str] = Field(None, description="Last booking timestamp (ISO 8601)")
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO 8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "slug": "sarah-johnson",
                "link_name": "Schedule with Sarah",
                "description": "Book a mortgage consultation",
                "url": "/book/sarah-johnson",
                "is_public": True,
                "user_id": 5,
                "owner_name": "Sarah Johnson",
                "view_count": 150,
                "booking_count": 23,
                "created_at": "2026-02-15T10:00:00Z",
            }
        }


class BookingLinkListResponse(BaseModel):
    """Response for GET /booking-links."""
    booking_links: List[BookingLinkSchema] = Field(
        ..., description="List of booking links"
    )


class BookingLinkCreateResponse(BaseModel):
    """Response for POST /booking-links."""
    message: str = Field(..., description="Success message")
    link_id: int = Field(..., description="Created booking link ID")
    url: str = Field(..., description="Booking URL path", example="/book/sarah-johnson")


# =============================================================================
# 7. BLOCKED TIME
# =============================================================================

class BlockedTimeDetailSchema(BaseModel):
    """Detailed blocked time record."""
    id: int = Field(..., description="Blocked time ID")
    title: str = Field(..., description="Block title")
    description: Optional[str] = Field(None, description="Block description")
    block_type: str = Field("custom", description="Type: lunch, ooo, meeting, custom")
    start_datetime: str = Field(..., description="Block start (ISO 8601)")
    end_datetime: str = Field(..., description="Block end (ISO 8601)")
    all_day: bool = Field(False, description="Whether this is an all-day block")
    is_recurring: bool = Field(False, description="Whether this block recurs")
    recurrence_pattern: Optional[Dict] = Field(None, description="Recurrence rules (JSON)")
    applies_to_all_users: bool = Field(
        False, description="Whether this block applies org-wide (admin only)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": 10,
                "title": "Lunch Break",
                "description": "Daily lunch",
                "block_type": "lunch",
                "start_datetime": "2026-03-15T12:00:00-05:00",
                "end_datetime": "2026-03-15T13:00:00-05:00",
                "all_day": False,
                "is_recurring": True,
                "recurrence_pattern": {"frequency": "daily"},
                "applies_to_all_users": False,
            }
        }


class BlockedTimeListResponse(BaseModel):
    """Response for GET /blocked-times."""
    blocked_times: List[BlockedTimeDetailSchema] = Field(
        ..., description="List of blocked time periods"
    )


# =============================================================================
# 8. PUBLIC BOOKING
# =============================================================================

class PublicBookingPageTeamMember(BaseModel):
    """Team member available on a public booking page."""
    id: int = Field(..., description="User ID")
    name: str = Field(..., description="Display name")
    title: Optional[str] = Field(None, description="Job title")
    profile_picture_url: Optional[str] = Field(None, description="Avatar URL")


class PublicBookingPageResponse(BaseModel):
    """Response for GET /public/book/{slug}."""
    booking_link: Dict[str, Any] = Field(
        ..., description="Booking link configuration"
    )
    appointment_types: List[Dict[str, Any]] = Field(
        ..., description="Available appointment types"
    )
    team_members: List[PublicBookingPageTeamMember] = Field(
        default=[], description="Available team members"
    )
    landing_page_settings: Optional[Dict[str, Any]] = Field(
        None, description="Landing page customization"
    )


class PublicBookingSlot(BaseModel):
    """A time slot on a public booking page."""
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    start_time: str = Field(..., description="Start time (ISO 8601)")
    end_time: str = Field(..., description="End time (ISO 8601)")
    user_id: int = Field(..., description="Assigned user ID")
    user_name: Optional[str] = Field(None, description="Assigned user name")


class PublicBookingSlotsResponse(BaseModel):
    """Response for GET /public/book/{slug}/slots."""
    slots: List[PublicBookingSlot] = Field(..., description="Available booking slots")
    total_slots: int = Field(..., description="Total number of available slots")


class PublicBookingConfirmResponse(BaseModel):
    """Response for POST /public/book/{slug}/confirm."""
    message: str = Field("Appointment booked successfully", description="Success message")
    appointment_id: int = Field(..., description="Created appointment ID")
    confirmation_number: Optional[str] = Field(None, description="Booking confirmation number")
    video_link: Optional[str] = Field(None, description="Video conference link")
    reschedule_url: Optional[str] = Field(None, description="URL to reschedule")
    assigned_to: Optional[str] = Field(None, description="Assigned team member name")


# =============================================================================
# 9. INTELLIGENCE / ANALYTICS
# =============================================================================

class NoShowRiskResponse(BaseModel):
    """No-show risk prediction for an appointment."""
    appointment_id: int = Field(..., description="Appointment ID")
    risk_score: float = Field(
        ..., description="No-show probability (0.0 = certain show, 1.0 = certain no-show)",
        ge=0.0, le=1.0,
    )
    risk_level: str = Field(
        ..., description="Risk category: low, medium, high", example="medium"
    )
    factors: List[str] = Field(
        ..., description="Contributing risk factors",
        example=["Friday afternoon slot", "No prior appointments", "Booked >7 days ago"],
    )
    mitigation_suggestions: List[str] = Field(
        default=[], description="Suggested actions to reduce no-show risk"
    )


class NoShowRiskBatchResponse(BaseModel):
    """Batch no-show risk for a date range."""
    date: str = Field(..., description="Analysis date")
    risks: List[NoShowRiskResponse] = Field(
        ..., description="Per-appointment risk assessments"
    )


class OptimalTimeSlot(BaseModel):
    """An AI-recommended optimal time for a lead."""
    start: str = Field(..., description="Slot start (ISO 8601)")
    end: str = Field(..., description="Slot end (ISO 8601)")
    score: float = Field(..., description="Predicted conversion score")
    lo_id: int = Field(..., description="Loan officer ID")
    lo_name: Optional[str] = Field(None, description="Loan officer name")
    reasons: List[str] = Field(default=[], description="Why this time is optimal")


class LOMatchResult(BaseModel):
    """Best LO match for a lead."""
    lo_id: int = Field(..., description="Recommended loan officer ID")
    lo_name: str = Field(..., description="Loan officer name")
    match_score: float = Field(..., description="Match score (0.0-1.0)")
    historical_show_rate: Optional[float] = Field(
        None, description="Historical show rate with similar leads"
    )
    reasons: List[str] = Field(default=[], description="Match reasoning")


class ConversionTrendPeriod(BaseModel):
    """One period in a conversion trend series."""
    period: str = Field(..., description="Period label (e.g., 'Week of Mar 3')")
    show_rate: float = Field(..., description="Show rate for this period")
    no_show_rate: float = Field(..., description="No-show rate")
    total_appointments: int = Field(..., description="Total appointments in period")
    trend: str = Field(..., description="Trend direction: up, down, flat")


class SchedulingInsight(BaseModel):
    """A human-readable scheduling insight."""
    category: str = Field(
        ..., description="Insight category: timing, routing, communication, etc."
    )
    insight: str = Field(
        ..., description="Human-readable insight text"
    )
    confidence: float = Field(
        ..., description="Statistical confidence (0.0-1.0)"
    )
    data: Optional[Dict[str, Any]] = Field(
        None, description="Supporting data points"
    )


class DurationPrediction(BaseModel):
    """Predicted appointment duration."""
    predicted_minutes: int = Field(
        ..., description="Predicted actual duration in minutes"
    )
    confidence_interval: Optional[List[int]] = Field(
        None, description="95% confidence interval [low, high]"
    )
    sample_size: int = Field(..., description="Historical data points used")
    factors: Dict[str, Any] = Field(
        default={}, description="Factors influencing the prediction"
    )


class FollowupTimingResult(BaseModel):
    """Optimal follow-up timing recommendation."""
    recommended_days: int = Field(
        ..., description="Recommended days to wait before follow-up"
    )
    optimal_day_of_week: Optional[str] = Field(
        None, description="Best day of week for follow-up"
    )
    optimal_time_of_day: Optional[str] = Field(
        None, description="Best time of day (HH:MM)"
    )
    historical_conversion_rate: Optional[float] = Field(
        None, description="Historical conversion rate at this timing"
    )


# =============================================================================
# 10. EMAIL & NOTIFICATIONS
# =============================================================================

class EmailServiceStatusResponse(BaseModel):
    """Email service health check response."""
    sendgrid_configured: bool = Field(
        ..., description="Whether SendGrid API key is present"
    )
    from_email: str = Field(
        ..., description="Configured sender email address"
    )
    status: str = Field(
        ..., description="Service status: ready, not_configured"
    )
    message: str = Field(
        ..., description="Human-readable status message"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "sendgrid_configured": True,
                "from_email": "sarah@reply.perenniaai.com",
                "status": "ready",
                "message": "Email service is ready to send",
            }
        }


class TestEmailResponse(BaseModel):
    """Response from test email send."""
    test_result: Dict[str, Any] = Field(
        ..., description="Email delivery result"
    )
    to_email: str = Field(..., description="Recipient email")
    from_email: Optional[str] = Field(None, description="Sender email")
    sendgrid_key_present: bool = Field(
        ..., description="Whether API key was available"
    )


# =============================================================================
# 11. SETTINGS (Advanced scheduler settings)
# =============================================================================

class BookingSettingsSchema(BaseModel):
    """Booking window and limit settings."""
    min_notice_hours: int = Field(2, description="Minimum advance notice (hours)")
    max_advance_days: int = Field(60, description="Maximum booking window (days)")
    default_duration_minutes: int = Field(30, description="Default meeting duration")
    buffer_between_appointments: int = Field(5, description="Buffer between meetings (minutes)")
    max_meetings_per_day: int = Field(8, description="Maximum meetings per day")


class AISettingsSchema(BaseModel):
    """AI scheduling behavior settings."""
    ai_scheduling_enabled: bool = Field(True, description="Enable AI scheduling")
    ai_can_reschedule: bool = Field(True, description="Allow AI to reschedule")
    ai_can_cancel: bool = Field(False, description="Allow AI to cancel appointments")
    smart_reminders_enabled: bool = Field(True, description="Enable smart reminders")
    auto_reschedule_enabled: bool = Field(True, description="Enable auto-reschedule for no-shows")


class SchedulerSettingsData(BaseModel):
    """Complete scheduler settings payload."""
    id: Optional[int] = Field(None, description="Configuration ID (null if using defaults)")
    timezone: str = Field("America/Chicago", description="IANA timezone identifier")
    business_hours: Dict[str, WorkingHoursDaySchema] = Field(
        ..., description="Business hours by day of week"
    )
    booking_settings: BookingSettingsSchema = Field(
        ..., description="Booking window and limits"
    )
    ai_settings: AISettingsSchema = Field(
        ..., description="AI scheduling preferences"
    )
    scheduling_method: str = Field(
        "round_robin", description="Routing method: direct, round_robin, priority, etc."
    )
    default_meeting_mode: str = Field(
        "video", description="Default meeting mode: video, phone, in_person"
    )
    zoom_enabled: bool = Field(True, description="Zoom integration enabled")
    google_meet_enabled: bool = Field(True, description="Google Meet integration enabled")
    auto_create_meeting_link: bool = Field(True, description="Auto-create video links")
    is_active: Optional[bool] = Field(None, description="Whether config is active")
    is_default: Optional[bool] = Field(
        None, description="True if no custom configuration exists"
    )
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class SchedulerSettingsResponse(SuccessEnvelope):
    """Response for GET /settings."""
    data: SchedulerSettingsData = Field(
        ..., description="Scheduler settings data"
    )


class WeeklyCapacity(BaseModel):
    """Calculated weekly meeting capacity."""
    total_working_hours: float = Field(..., description="Total working hours per week")
    working_days: int = Field(..., description="Number of working days")
    max_meetings_per_week: int = Field(..., description="Calculated maximum meetings per week")
    avg_hours_per_day: float = Field(..., description="Average working hours per day")


class SettingsUpdateResult(BaseModel):
    """Settings update result."""
    updated: bool = Field(True, description="Whether the update succeeded")
    warnings: List[str] = Field(
        default=[], description="Configuration warnings"
    )
    capacity: Optional[WeeklyCapacity] = Field(
        None, description="Calculated capacity (if business hours and booking settings provided)"
    )


class SettingsUpdateResponse(SuccessEnvelope):
    """Response for PUT /settings."""
    data: SettingsUpdateResult = Field(
        ..., description="Update result with warnings and capacity"
    )


class SettingsTestResult(BaseModel):
    """Result of scheduler configuration test."""
    success: bool = Field(..., description="Whether all checks passed")
    issues: List[str] = Field(
        default=[], description="Configuration issues found"
    )
    loan_officers_available: int = Field(
        ..., description="Number of active LOs in the scheduling pool"
    )
    test_date: Optional[str] = Field(None, description="Date tested against")
    test_duration: int = Field(30, description="Duration tested")


class SettingsTestResponse(SuccessEnvelope):
    """Response for POST /settings/test."""
    data: SettingsTestResult = Field(
        ..., description="Configuration test results"
    )


# =============================================================================
# 12. TIMEZONES & SCHEDULING METHODS
# =============================================================================

class TimezoneOption(BaseModel):
    """A timezone option."""
    value: str = Field(..., description="IANA timezone ID", example="America/Chicago")
    label: str = Field(..., description="Human-readable label", example="Central Time (CT)")
    offset: str = Field("", description="UTC offset", example="UTC-6")


class TimezoneListResponse(BaseModel):
    """Response for GET /timezones."""
    common: List[TimezoneOption] = Field(
        ..., description="Common US timezones"
    )
    all_timezones: Optional[List[TimezoneOption]] = Field(
        None, description="Additional matching timezones (when search is provided)"
    )


class SchedulingMethodOption(BaseModel):
    """A scheduling method option."""
    value: str = Field(..., description="Method identifier", example="round_robin")
    label: str = Field(..., description="Display label", example="Round Robin")
    description: str = Field(..., description="Method description")


class SchedulingMethodListResponse(BaseModel):
    """Response for GET /scheduling-methods."""
    methods: List[SchedulingMethodOption] = Field(
        ..., description="Available scheduling methods"
    )


# =============================================================================
# 13. MIGRATION & SEED
# =============================================================================

class MigrationResponse(BaseModel):
    """Response for POST /migrate."""
    message: str = Field("Scheduler migration complete", description="Status message")
    created_tables: List[str] = Field(
        default=[], description="Tables that were created"
    )
    existing_tables: List[str] = Field(
        default=[], description="Tables that already existed"
    )
    demo_link_exists: bool = Field(True, description="Whether the demo booking link exists")


class SeedDefaultsResponse(BaseModel):
    """Response for POST /seed-defaults."""
    message: str = Field(..., description="Status message with count of seeded types")
    config_id: int = Field(..., description="Scheduler configuration ID")


# =============================================================================
# OPENAPI TAG METADATA
# =============================================================================

SCHEDULER_TAGS_METADATA = [
    {
        "name": "Scheduler Configuration",
        "description": (
            "Scheduler configuration management. Each user has one configuration "
            "per organization controlling timezone, working hours, buffer times, "
            "routing strategy, and AI scheduling preferences."
        ),
    },
    {
        "name": "Appointment Types",
        "description": (
            "CRUD operations for appointment types. Appointment types define the "
            "kinds of meetings available (e.g., Discovery Call, Rate Review) "
            "including duration options, intake questions, and public visibility."
        ),
    },
    {
        "name": "Appointments",
        "description": (
            "Appointment lifecycle management: create, read, update, cancel. "
            "Includes conflict detection with SELECT FOR UPDATE, duplicate booking "
            "prevention, CRM lead/loan linking, and Microsoft Graph calendar sync."
        ),
    },
    {
        "name": "Availability",
        "description": (
            "Availability slot management and bookable time slot generation. "
            "Supports recurring weekly slots, date-specific overrides, priority "
            "levels, and cross-source conflict detection (scheduler, CRM calendar, "
            "Microsoft/Google calendar)."
        ),
    },
    {
        "name": "Booking Links",
        "description": (
            "Public booking link management. Booking links provide shareable URLs "
            "for clients to self-schedule appointments. Supports multiple routing "
            "strategies (round-robin, relationship, priority) and team assignment."
        ),
    },
    {
        "name": "Public Booking",
        "description": (
            "Unauthenticated public-facing booking endpoints. These power the "
            "client-facing booking pages accessed via booking link slugs. "
            "Rate-limited and protected by Cloudflare Turnstile bot detection."
        ),
    },
    {
        "name": "Blocked Time",
        "description": (
            "Blocked time period management for lunch breaks, out-of-office, "
            "personal blocks, and org-wide capacity limits. Supports recurring "
            "patterns and admin-only org-wide blocks."
        ),
    },
    {
        "name": "Scheduling Intelligence",
        "description": (
            "AI-powered scheduling analytics and optimization. Includes no-show "
            "risk prediction, optimal time recommendations, LO matching, "
            "conversion trend analysis, and follow-up timing optimization."
        ),
    },
    {
        "name": "Scheduler Settings",
        "description": (
            "Advanced scheduler settings including business hours, booking limits, "
            "AI preferences, video conferencing integration, and capacity estimation."
        ),
    },
    {
        "name": "Email Service",
        "description": (
            "Email service status and testing endpoints for appointment "
            "confirmations, reminders, and cancellation notifications."
        ),
    },
    {
        "name": "Scheduler Admin",
        "description": (
            "Administrative operations: schema migration, default data seeding, "
            "and configuration testing. Requires admin role."
        ),
    },
]
