"""
Scheduler Pydantic Models / Schemas
Extracted from smart_scheduler_routes.py
"""

from datetime import datetime, date
from typing import Any, List, Optional, Dict
from pydantic import BaseModel, EmailStr, Field, validator


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

    @validator('slug', pre=True)
    def lowercase_slug(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v


class AvailableSlotsRequest(BaseModel):
    appointment_type_id: Optional[int] = None
    meeting_type: Optional[str] = None
    duration_minutes: int = Field(30, ge=5, le=480)
    start_date: date
    end_date: date
    timezone: str = "America/Chicago"
    user_ids: Optional[List[int]] = None  # Filter to specific users

    @validator('end_date')
    def end_date_after_start(cls, v, values):
        if 'start_date' in values and v < values['start_date']:
            raise ValueError('end_date must be on or after start_date')
        return v


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


class PublicAvailableSlotsRequest(BaseModel):
    """Request model for website demo scheduler"""
    start_date: date
    end_date: date
    duration_minutes: int = Field(30, ge=5, le=480)
    appointment_type: str = Field("platform-demo", max_length=100)

    @validator('end_date')
    def end_date_after_start(cls, v, values):
        if 'start_date' in values and v < values['start_date']:
            raise ValueError('end_date must be on or after start_date')
        return v


class SlotRecommendation(BaseModel):
    slot_start: datetime
    slot_end: datetime
    user_id: int
    user_name: str
    score: float  # AI-calculated score
    reasons: List[str]  # Why this slot is recommended


class CancelAppointmentRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=2000)


class WebsiteDemoBookingRequest(BaseModel):
    """Request model for website demo booking confirmation"""
    start_time: datetime  # ISO datetime
    duration_minutes: int = Field(30, ge=5, le=480)
    attendee_name: str = Field(..., min_length=1, max_length=200)
    attendee_email: EmailStr
    attendee_phone: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = Field(None, max_length=500)
    meeting_mode: str = Field("video", max_length=20)
