"""
Scheduler Pydantic Models / Schemas
Extracted from smart_scheduler_routes.py
"""

from datetime import datetime, date
from typing import List, Optional, Dict
from pydantic import BaseModel, EmailStr


class WorkingHoursDay(BaseModel):
    start: str  # "09:00"
    end: str    # "17:00"
    enabled: bool = True


class SchedulerConfigCreate(BaseModel):
    config_name: str
    description: Optional[str] = None
    timezone: str = "America/Chicago"
    default_duration_minutes: int = 30
    buffer_before_minutes: int = 5
    buffer_after_minutes: int = 5
    min_notice_hours: int = 2
    max_advance_days: int = 60
    max_meetings_per_day: int = 8
    working_hours: Optional[Dict[str, WorkingHoursDay]] = None
    routing_strategy: Optional[str] = "relationship"
    ai_scheduling_enabled: bool = True


class SchedulerConfigUpdate(BaseModel):
    config_name: Optional[str] = None
    description: Optional[str] = None
    timezone: Optional[str] = None
    default_duration_minutes: Optional[int] = None
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
    type_key: str
    type_name: str
    description: Optional[str] = None
    meeting_type: Optional[str] = "custom"
    default_duration_minutes: int = 30
    allowed_durations: List[int] = [15, 30, 45, 60]
    allowed_modes: List[str] = ["video", "phone"]
    requires_loan_id: bool = False
    requires_lead_id: bool = False
    intake_questions: List[Dict] = []
    color: str = "#3b82f6"
    icon: str = "calendar"
    is_public: bool = True
    public_slug: Optional[str] = None


class AppointmentTypeUpdate(BaseModel):
    type_name: Optional[str] = None
    description: Optional[str] = None
    default_duration_minutes: Optional[int] = None
    allowed_durations: Optional[List[int]] = None
    allowed_modes: Optional[List[str]] = None
    intake_questions: Optional[List[Dict]] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None


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
    title: str
    description: Optional[str] = None
    meeting_type: Optional[str] = "custom"
    meeting_mode: str = "video"
    scheduled_start: datetime
    duration_minutes: int = 30
    timezone: str = "America/Chicago"

    # Attendee info (for external bookings)
    attendee_name: Optional[str] = None
    attendee_email: Optional[EmailStr] = None
    attendee_phone: Optional[str] = None
    attendee_notes: Optional[str] = None

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
    title: Optional[str] = None
    description: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    meeting_mode: Optional[str] = None
    location: Optional[str] = None
    video_link: Optional[str] = None
    status: Optional[str] = None
    cancellation_reason: Optional[str] = None
    internal_notes: Optional[str] = None
    meeting_notes: Optional[str] = None
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    attendee_phone: Optional[str] = None
    attendee_notes: Optional[str] = None
    send_notification: Optional[bool] = True  # Send email/SMS on update


class BlockedTimeCreate(BaseModel):
    title: str
    description: Optional[str] = None
    block_type: str = "custom"
    start_datetime: datetime
    end_datetime: datetime
    all_day: bool = False
    is_recurring: bool = False
    recurrence_pattern: Optional[Dict] = None
    applies_to_all_users: bool = False


class BookingLinkCreate(BaseModel):
    slug: str
    link_name: str
    description: Optional[str] = None
    appointment_type_ids: List[int] = []
    single_appointment_type_id: Optional[int] = None
    is_public: bool = True
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None
    routing_strategy: str = "relationship"
    assigned_users: List[int] = []


class AvailableSlotsRequest(BaseModel):
    appointment_type_id: Optional[int] = None
    meeting_type: Optional[str] = None
    duration_minutes: int = 30
    start_date: date
    end_date: date
    timezone: str = "America/Chicago"


class PublicBookingConfirmRequest(BaseModel):
    appointment_type_id: int
    start_time: datetime
    duration_minutes: int = 30
    attendee_name: str
    attendee_email: EmailStr
    attendee_phone: Optional[str] = None
    notes: Optional[str] = None
    user_ids: List[int] = []  # Empty = any available user
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    meeting_mode: Optional[str] = None  # video, phone, in_person
    team_member_id: Optional[int] = None
    team_member_name: Optional[str] = None


class PublicAvailableSlotsRequest(BaseModel):
    """Request model for website demo scheduler"""
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    duration_minutes: int = 30
    appointment_type: str = "platform-demo"


class SlotRecommendation(BaseModel):
    slot_start: datetime
    slot_end: datetime
    user_id: int
    user_name: str
    score: float  # AI-calculated score
    reasons: List[str]  # Why this slot is recommended


class CancelAppointmentRequest(BaseModel):
    reason: Optional[str] = None


class WebsiteDemoBookingRequest(BaseModel):
    """Request model for website demo booking confirmation"""
    start_time: str  # ISO datetime
    duration_minutes: int = 30
    attendee_name: str
    attendee_email: EmailStr
    attendee_phone: Optional[str] = None
    notes: Optional[str] = None
    meeting_mode: str = "video"
