"""
Smart Docs Appointment Intelligence Service

Manages scheduling intelligence for document-related appointments:
- Document review sessions (LO reviews uploaded docs with borrower)
- Signing appointments (e-sign or wet-sign sessions)
- Condition clearance (review outstanding conditions with borrower)
- Initial consultation (first document needs discussion)
- Closing prep (pre-closing document review)

Features:
- Predicts optimal appointment times from borrower response patterns
- Checks LO calendar availability across all calendar sources
- Avoids conflicts with loan milestones (lock expiration, closing dates)
- Manages reminders (24-hour and 1-hour)
- Pre-appointment document readiness briefs
- Post-appointment task creation and follow-up
- No-show handling with automatic reschedule
- Appointment analytics (completion rates, duration, outcomes)
- Video meeting link hooks
- iCal event generation

Usage:
    from services.smart_docs.appointment_intelligence_service import (
        AppointmentIntelligenceService,
        DocAppointmentType,
    )

    service = AppointmentIntelligenceService(db=db, org_id=42, user_id=7)

    # Suggest optimal times
    slots = await service.suggest_appointment(loan_id=100, appointment_type="DOCUMENT_REVIEW")

    # Create appointment
    appt = await service.create_appointment(loan_id=100, appointment_data={...})

    # Pre-appointment brief
    brief = await service.get_pre_appointment_brief(appointment_id=55)

    # Handle no-show
    result = await service.handle_no_show(appointment_id=55)

    # Analytics
    analytics = await service.get_appointment_analytics(start_date=..., end_date=...)
"""

import enum
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from database.models.document_followup import (
    AppointmentStatus,
    AppointmentType,
    DocumentAppointment,
    LocationType,
)
from exceptions import (
    EntityNotFoundError,
    LoanNotFoundError,
    TenantIsolationError,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class DocAppointmentType(str, enum.Enum):
    """Extended appointment types for Smart Docs V2."""
    DOCUMENT_REVIEW = "document_review"
    SIGNING_APPOINTMENT = "signing_appointment"
    CONDITION_CLEARANCE = "condition_clearance"
    INITIAL_CONSULTATION = "initial_consultation"
    CLOSING_PREP = "closing_prep"


# Map our extended types to the DB model AppointmentType enum
_TYPE_TO_DB_MAP: Dict[DocAppointmentType, AppointmentType] = {
    DocAppointmentType.DOCUMENT_REVIEW: AppointmentType.DOCUMENT_REVIEW,
    DocAppointmentType.SIGNING_APPOINTMENT: AppointmentType.NOTARY_SIGNING,
    DocAppointmentType.CONDITION_CLEARANCE: AppointmentType.DOCUMENT_REVIEW,
    DocAppointmentType.INITIAL_CONSULTATION: AppointmentType.GENERAL_CONSULTATION,
    DocAppointmentType.CLOSING_PREP: AppointmentType.DOCUMENT_REVIEW,
}

# Default durations per appointment type (minutes)
_DEFAULT_DURATIONS: Dict[DocAppointmentType, int] = {
    DocAppointmentType.DOCUMENT_REVIEW: 30,
    DocAppointmentType.SIGNING_APPOINTMENT: 45,
    DocAppointmentType.CONDITION_CLEARANCE: 20,
    DocAppointmentType.INITIAL_CONSULTATION: 45,
    DocAppointmentType.CLOSING_PREP: 60,
}

# Human-readable titles per type
_DEFAULT_TITLES: Dict[DocAppointmentType, str] = {
    DocAppointmentType.DOCUMENT_REVIEW: "Document Review Session",
    DocAppointmentType.SIGNING_APPOINTMENT: "Document Signing Appointment",
    DocAppointmentType.CONDITION_CLEARANCE: "Condition Clearance Review",
    DocAppointmentType.INITIAL_CONSULTATION: "Initial Document Consultation",
    DocAppointmentType.CLOSING_PREP: "Pre-Closing Document Review",
}

# Buffer minutes between appointments
APPOINTMENT_BUFFER_MINUTES = 15

# How far ahead (days) to search for available slots
SLOT_SEARCH_DAYS = 14

# Maximum slots to return per suggestion request
MAX_SUGGESTED_SLOTS = 10

# Default business hours (used when no org-specific config is found)
_DEFAULT_BUSINESS_HOURS: Dict[str, Dict[str, Any]] = {
    "monday": {"start": "09:00", "end": "17:00", "enabled": True},
    "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
    "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
    "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
    "friday": {"start": "09:00", "end": "17:00", "enabled": True},
    "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
    "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
}

# Weekday name lookup (Monday=0)
_WEEKDAY_NAMES = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]

# Reminder lead times
REMINDER_24H = timedelta(hours=24)
REMINDER_1H = timedelta(hours=1)

# No-show: how many times before flagging for manual follow-up
MAX_NO_SHOW_RESCHEDULES = 2


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TimeSlot:
    """A proposed time slot for an appointment."""
    start: datetime
    end: datetime
    duration_minutes: int
    score: float = 0.0  # 0-100, higher is better
    reason: str = ""
    lo_user_id: Optional[int] = None
    lo_name: Optional[str] = None
    conflicts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "duration_minutes": self.duration_minutes,
            "score": round(self.score, 1),
            "reason": self.reason,
            "lo_user_id": self.lo_user_id,
            "lo_name": self.lo_name,
            "conflicts": self.conflicts,
        }


@dataclass
class AppointmentBrief:
    """Pre-appointment briefing data."""
    appointment_id: int
    loan_id: int
    borrower_name: str
    appointment_type: str
    scheduled_at: datetime
    duration_minutes: int
    documents_to_review: List[Dict[str, Any]]
    issues_to_discuss: List[Dict[str, Any]]
    agenda_items: List[str]
    loan_stage: Optional[str] = None
    days_in_stage: Optional[int] = None
    outstanding_conditions: int = 0
    meeting_link: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "appointment_id": self.appointment_id,
            "loan_id": self.loan_id,
            "borrower_name": self.borrower_name,
            "appointment_type": self.appointment_type,
            "scheduled_at": self.scheduled_at.isoformat(),
            "duration_minutes": self.duration_minutes,
            "loan_stage": self.loan_stage,
            "days_in_stage": self.days_in_stage,
            "outstanding_conditions": self.outstanding_conditions,
            "documents_to_review": self.documents_to_review,
            "issues_to_discuss": self.issues_to_discuss,
            "agenda_items": self.agenda_items,
            "meeting_link": self.meeting_link,
        }


@dataclass
class RescheduleResult:
    """Result of a no-show handling attempt."""
    original_appointment_id: int
    action_taken: str  # "rescheduled", "flagged_for_followup", "max_attempts_reached"
    new_appointment_id: Optional[int] = None
    new_time: Optional[datetime] = None
    no_show_count: int = 0
    follow_up_required: bool = False
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_appointment_id": self.original_appointment_id,
            "action_taken": self.action_taken,
            "new_appointment_id": self.new_appointment_id,
            "new_time": self.new_time.isoformat() if self.new_time else None,
            "no_show_count": self.no_show_count,
            "follow_up_required": self.follow_up_required,
            "message": self.message,
        }


@dataclass
class AppointmentAnalytics:
    """Aggregate appointment analytics."""
    total_scheduled: int = 0
    total_completed: int = 0
    total_cancelled: int = 0
    total_no_shows: int = 0
    total_rescheduled: int = 0
    completion_rate: float = 0.0
    no_show_rate: float = 0.0
    avg_duration_minutes: float = 0.0
    by_type: Dict[str, Dict[str, int]] = field(default_factory=dict)
    by_outcome: Dict[str, int] = field(default_factory=dict)
    busiest_day: Optional[str] = None
    busiest_hour: Optional[int] = None
    avg_lead_time_days: float = 0.0  # avg days between booking and appointment

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_scheduled": self.total_scheduled,
            "total_completed": self.total_completed,
            "total_cancelled": self.total_cancelled,
            "total_no_shows": self.total_no_shows,
            "total_rescheduled": self.total_rescheduled,
            "completion_rate": round(self.completion_rate, 1),
            "no_show_rate": round(self.no_show_rate, 1),
            "avg_duration_minutes": round(self.avg_duration_minutes, 1),
            "by_type": self.by_type,
            "by_outcome": self.by_outcome,
            "busiest_day": self.busiest_day,
            "busiest_hour": self.busiest_hour,
            "avg_lead_time_days": round(self.avg_lead_time_days, 1),
        }


# =============================================================================
# APPOINTMENT INTELLIGENCE SERVICE
# =============================================================================

class AppointmentIntelligenceService:
    """
    Manages scheduling intelligence for document-related appointments.

    All methods enforce org_id isolation. The service uses the existing
    DocumentAppointment model and cross-references ScheduledAppointment,
    CalendarEvent, and CRMCalendarEvent for conflict detection.

    Args:
        db: SQLAlchemy session for the current request.
        org_id: Organization ID for tenant isolation.
        user_id: Authenticated user performing the action (optional for system contexts).
    """

    def __init__(self, db: Session, org_id: int, user_id: Optional[int] = None):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    async def suggest_appointment(
        self,
        loan_id: int,
        appointment_type: str,
        lo_user_id: Optional[int] = None,
        preferred_dates: Optional[List[date]] = None,
        duration_minutes: Optional[int] = None,
    ) -> List[TimeSlot]:
        """
        Suggest optimal appointment times for a document-related meeting.

        Considers:
        - LO calendar availability (all 3 calendar sources)
        - Borrower response patterns (time-of-day and day-of-week)
        - Loan milestone conflicts (lock expiration, closing date)
        - Existing document appointments for the loan
        - Buffer time between appointments

        Args:
            loan_id: Loan to schedule the appointment for.
            appointment_type: One of DocAppointmentType values.
            lo_user_id: Specific LO to check. If None, uses the loan's assigned LO.
            preferred_dates: Optional list of preferred dates to prioritize.
            duration_minutes: Override default duration for the appointment type.

        Returns:
            List of TimeSlot objects, sorted by score (best first), up to MAX_SUGGESTED_SLOTS.

        Raises:
            LoanNotFoundError: If the loan does not exist or is in another org.
        """
        loan = self._get_loan_or_raise(loan_id)
        appt_type = self._resolve_appointment_type(appointment_type)
        duration = duration_minutes or _DEFAULT_DURATIONS.get(appt_type, 30)

        # Determine which LO to check availability for
        target_lo_id = lo_user_id or loan.get("loan_officer_id")
        if not target_lo_id:
            logger.warning(f"No LO assigned to loan {loan_id}, cannot suggest appointments")
            return []

        lo_name = loan.get("lo_name", "")

        # Get business hours for this org
        business_hours = self._get_business_hours()

        # Get LO busy times for the search window
        now = datetime.now(timezone.utc)
        search_start = now + timedelta(hours=2)  # Minimum 2 hours notice
        search_end = now + timedelta(days=SLOT_SEARCH_DAYS)

        busy_times = self._get_all_busy_times(target_lo_id, search_start, search_end)

        # Get loan milestone dates to avoid
        milestone_blackouts = self._get_milestone_blackout_windows(loan)

        # Get borrower response pattern scores
        borrower_pattern = self._analyze_borrower_patterns(loan_id)

        # Generate candidate slots
        candidates = self._generate_candidate_slots(
            search_start=search_start,
            search_end=search_end,
            duration_minutes=duration,
            business_hours=business_hours,
            busy_times=busy_times,
            milestone_blackouts=milestone_blackouts,
        )

        # Score and rank slots
        scored_slots = self._score_slots(
            candidates=candidates,
            borrower_pattern=borrower_pattern,
            preferred_dates=preferred_dates,
            lo_user_id=target_lo_id,
            lo_name=lo_name,
        )

        # Sort by score descending and limit
        scored_slots.sort(key=lambda s: s.score, reverse=True)
        return scored_slots[:MAX_SUGGESTED_SLOTS]

    async def create_appointment(
        self,
        loan_id: int,
        appointment_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Create a document-related appointment.

        Args:
            loan_id: Loan to attach the appointment to.
            appointment_data: Dict with keys:
                - appointment_type (str): One of DocAppointmentType values.
                - start_time (datetime): Appointment start.
                - duration_minutes (int, optional): Defaults based on type.
                - lo_user_id (int, optional): Assigned LO. Defaults to loan's LO.
                - location_type (str, optional): "video_call", "phone_call", "in_person".
                - location_details (str, optional): Address or meeting description.
                - description (str, optional): Additional notes.
                - documents_to_discuss (list[int], optional): Document request IDs.
                - attendee_name (str, optional): Borrower name override.
                - attendee_email (str, optional): Borrower email override.
                - attendee_phone (str, optional): Borrower phone override.
                - campaign_id (int, optional): Link to follow-up campaign.

        Returns:
            Dict with created appointment details.

        Raises:
            LoanNotFoundError: If the loan does not exist or is in another org.
            ValueError: If required fields are missing.
        """
        loan = self._get_loan_or_raise(loan_id)

        appt_type_str = appointment_data.get("appointment_type", "document_review")
        appt_type = self._resolve_appointment_type(appt_type_str)
        db_appt_type = _TYPE_TO_DB_MAP.get(appt_type, AppointmentType.DOCUMENT_REVIEW)

        start_time = appointment_data.get("start_time")
        if not start_time:
            raise ValueError("start_time is required")
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time)

        duration = appointment_data.get(
            "duration_minutes",
            _DEFAULT_DURATIONS.get(appt_type, 30),
        )
        end_time = start_time + timedelta(minutes=duration)

        lo_user_id = appointment_data.get("lo_user_id") or loan.get("loan_officer_id")

        # Resolve location type
        loc_type_str = appointment_data.get("location_type", "video_call")
        try:
            loc_type = LocationType(loc_type_str)
        except ValueError:
            loc_type = LocationType.VIDEO_CALL

        # Generate meeting link placeholder (hook for video integration)
        meeting_link = appointment_data.get("meeting_link")
        if not meeting_link and loc_type == LocationType.VIDEO_CALL:
            meeting_link = self._generate_meeting_link_placeholder(loan_id)

        title = appointment_data.get(
            "title",
            _DEFAULT_TITLES.get(appt_type, "Document Appointment"),
        )

        # Resolve borrower info from loan if not provided
        attendee_name = (
            appointment_data.get("attendee_name")
            or loan.get("borrower_name", "")
        )
        attendee_email = (
            appointment_data.get("attendee_email")
            or loan.get("borrower_email", "")
        )
        attendee_phone = (
            appointment_data.get("attendee_phone")
            or loan.get("borrower_phone", "")
        )

        appointment = DocumentAppointment(
            organization_id=self.org_id,
            loan_id=loan_id,
            borrower_id=appointment_data.get("borrower_id"),
            campaign_id=appointment_data.get("campaign_id"),
            appointment_type=db_appt_type,
            title=title,
            description=appointment_data.get("description", ""),
            status=AppointmentStatus.SCHEDULED,
            scheduled_date=start_time.date(),
            scheduled_time_start=start_time,
            scheduled_time_end=end_time,
            duration_minutes=duration,
            location_type=loc_type,
            location_details=appointment_data.get("location_details", ""),
            meeting_link=meeting_link,
            assigned_to_user_id=lo_user_id,
            attendee_name=attendee_name,
            attendee_email=attendee_email,
            attendee_phone=attendee_phone,
            documents_to_discuss=appointment_data.get("documents_to_discuss", []),
        )

        self.db.add(appointment)
        self.db.flush()

        logger.info(
            f"Created doc appointment {appointment.id} for loan {loan_id}, "
            f"type={appt_type_str}, at {start_time.isoformat()}"
        )

        return {
            "id": appointment.id,
            "loan_id": loan_id,
            "appointment_type": appt_type_str,
            "title": title,
            "status": AppointmentStatus.SCHEDULED.value,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_minutes": duration,
            "location_type": loc_type.value,
            "meeting_link": meeting_link,
            "assigned_to_user_id": lo_user_id,
            "attendee_name": attendee_name,
            "attendee_email": attendee_email,
            "documents_to_discuss": appointment_data.get("documents_to_discuss", []),
        }

    async def get_pre_appointment_brief(
        self,
        appointment_id: int,
    ) -> AppointmentBrief:
        """
        Generate a pre-appointment briefing with document readiness status.

        Includes:
        - Documents to review in this session
        - Issues and flags to discuss
        - Generated agenda items
        - Loan stage context

        Args:
            appointment_id: ID of the DocumentAppointment.

        Returns:
            AppointmentBrief dataclass.

        Raises:
            EntityNotFoundError: If appointment does not exist in this org.
        """
        appt = self._get_appointment_or_raise(appointment_id)

        loan_id = appt.loan_id
        loan = self._get_loan_or_raise(loan_id)

        # Gather documents linked to this appointment
        documents_to_review = self._get_documents_for_appointment(appt)

        # Gather issues (missing docs, expired docs, compliance flags)
        issues_to_discuss = self._get_issues_for_loan(loan_id)

        # Count outstanding conditions/compliance alerts
        outstanding_conditions = self._count_outstanding_conditions(loan_id)

        # Calculate days in current stage
        days_in_stage = None
        stage_changed_at = loan.get("stage_changed_at")
        if stage_changed_at:
            if isinstance(stage_changed_at, datetime):
                days_in_stage = (datetime.now(timezone.utc) - stage_changed_at.replace(tzinfo=timezone.utc)).days
            elif isinstance(stage_changed_at, date):
                days_in_stage = (date.today() - stage_changed_at).days

        # Build agenda
        agenda_items = self._build_agenda(
            appointment_type=appt.appointment_type,
            documents_to_review=documents_to_review,
            issues=issues_to_discuss,
            outstanding_conditions=outstanding_conditions,
            loan_stage=loan.get("stage"),
        )

        borrower_name = appt.attendee_name or loan.get("borrower_name", "Borrower")

        return AppointmentBrief(
            appointment_id=appointment_id,
            loan_id=loan_id,
            borrower_name=borrower_name,
            appointment_type=(
                appt.appointment_type.value
                if hasattr(appt.appointment_type, "value")
                else str(appt.appointment_type)
            ),
            scheduled_at=appt.scheduled_time_start,
            duration_minutes=appt.duration_minutes or 30,
            documents_to_review=documents_to_review,
            issues_to_discuss=issues_to_discuss,
            agenda_items=agenda_items,
            loan_stage=loan.get("stage"),
            days_in_stage=days_in_stage,
            outstanding_conditions=outstanding_conditions,
            meeting_link=appt.meeting_link,
        )

    async def handle_no_show(
        self,
        appointment_id: int,
    ) -> RescheduleResult:
        """
        Handle a no-show for a document appointment.

        Logic:
        - Mark the appointment as NO_SHOW.
        - Count prior no-shows for this loan+borrower.
        - If under MAX_NO_SHOW_RESCHEDULES, auto-reschedule 2 business days out.
        - If at/over the limit, flag for manual LO follow-up.

        Args:
            appointment_id: ID of the missed appointment.

        Returns:
            RescheduleResult with details of the action taken.

        Raises:
            EntityNotFoundError: If appointment not found in this org.
        """
        appt = self._get_appointment_or_raise(appointment_id)

        # Mark as no-show
        appt.status = AppointmentStatus.NO_SHOW
        appt.completed_at = datetime.now(timezone.utc)
        self.db.flush()

        # Count total no-shows for this borrower on this loan
        no_show_count = (
            self.db.query(func.count(DocumentAppointment.id))
            .filter(
                DocumentAppointment.organization_id == self.org_id,
                DocumentAppointment.loan_id == appt.loan_id,
                DocumentAppointment.borrower_id == appt.borrower_id,
                DocumentAppointment.status == AppointmentStatus.NO_SHOW,
            )
            .scalar()
        ) or 0

        if no_show_count >= MAX_NO_SHOW_RESCHEDULES:
            # Too many no-shows - flag for manual follow-up
            logger.warning(
                f"Appointment {appointment_id}: {no_show_count} no-shows for "
                f"loan {appt.loan_id} borrower {appt.borrower_id}. Flagging for follow-up."
            )
            self._create_no_show_followup_task(appt, no_show_count)
            return RescheduleResult(
                original_appointment_id=appointment_id,
                action_taken="max_attempts_reached",
                no_show_count=no_show_count,
                follow_up_required=True,
                message=(
                    f"Borrower has missed {no_show_count} appointments. "
                    f"Manual follow-up task created for the loan officer."
                ),
            )

        # Auto-reschedule: 2 business days from now
        new_start = self._next_business_day(
            datetime.now(timezone.utc),
            skip_days=2,
        )
        # Try to keep the same time of day
        original_time = appt.scheduled_time_start
        if original_time:
            new_start = new_start.replace(
                hour=original_time.hour,
                minute=original_time.minute,
                second=0,
                microsecond=0,
            )

        duration = appt.duration_minutes or 30
        new_end = new_start + timedelta(minutes=duration)

        new_appt = DocumentAppointment(
            organization_id=self.org_id,
            loan_id=appt.loan_id,
            borrower_id=appt.borrower_id,
            campaign_id=appt.campaign_id,
            appointment_type=appt.appointment_type,
            title=appt.title,
            description=f"Rescheduled after no-show (attempt {no_show_count + 1})",
            status=AppointmentStatus.SCHEDULED,
            scheduled_date=new_start.date(),
            scheduled_time_start=new_start,
            scheduled_time_end=new_end,
            duration_minutes=duration,
            location_type=appt.location_type,
            location_details=appt.location_details,
            meeting_link=appt.meeting_link,
            assigned_to_user_id=appt.assigned_to_user_id,
            attendee_name=appt.attendee_name,
            attendee_email=appt.attendee_email,
            attendee_phone=appt.attendee_phone,
            documents_to_discuss=appt.documents_to_discuss,
            rescheduled_from_id=appt.id,
        )
        self.db.add(new_appt)
        self.db.flush()

        # Mark original as rescheduled
        appt.status = AppointmentStatus.RESCHEDULED

        logger.info(
            f"No-show for appointment {appointment_id}. "
            f"Rescheduled to {new_start.isoformat()} as appointment {new_appt.id}"
        )

        return RescheduleResult(
            original_appointment_id=appointment_id,
            action_taken="rescheduled",
            new_appointment_id=new_appt.id,
            new_time=new_start,
            no_show_count=no_show_count,
            follow_up_required=False,
            message=(
                f"Appointment rescheduled to {new_start.strftime('%m/%d/%Y %I:%M %p')}. "
                f"No-show count: {no_show_count}."
            ),
        )

    async def get_appointment_analytics(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        lo_user_id: Optional[int] = None,
    ) -> AppointmentAnalytics:
        """
        Compute appointment analytics for the organization.

        Args:
            start_date: Start of date range (defaults to 90 days ago).
            end_date: End of date range (defaults to today).
            lo_user_id: Filter to a specific LO (optional).

        Returns:
            AppointmentAnalytics with completion rates, durations, type breakdowns.
        """
        if not start_date:
            start_date = date.today() - timedelta(days=90)
        if not end_date:
            end_date = date.today()

        filters = [
            DocumentAppointment.organization_id == self.org_id,
            DocumentAppointment.scheduled_date >= start_date,
            DocumentAppointment.scheduled_date <= end_date,
        ]
        if lo_user_id:
            filters.append(DocumentAppointment.assigned_to_user_id == lo_user_id)

        appointments = (
            self.db.query(DocumentAppointment)
            .filter(and_(*filters))
            .all()
        )

        analytics = AppointmentAnalytics()
        analytics.total_scheduled = len(appointments)

        if not appointments:
            return analytics

        # Count by status
        status_counts: Dict[str, int] = {}
        type_counts: Dict[str, Dict[str, int]] = {}
        durations: List[int] = []
        day_counts: Dict[int, int] = {}  # weekday -> count
        hour_counts: Dict[int, int] = {}  # hour -> count
        lead_times: List[float] = []

        for appt in appointments:
            status_val = (
                appt.status.value
                if hasattr(appt.status, "value")
                else str(appt.status)
            )
            status_counts[status_val] = status_counts.get(status_val, 0) + 1

            # Type breakdown
            type_val = (
                appt.appointment_type.value
                if hasattr(appt.appointment_type, "value")
                else str(appt.appointment_type)
            )
            if type_val not in type_counts:
                type_counts[type_val] = {"scheduled": 0, "completed": 0, "no_show": 0, "cancelled": 0}
            type_counts[type_val]["scheduled"] += 1
            if status_val == AppointmentStatus.COMPLETED.value:
                type_counts[type_val]["completed"] += 1
            elif status_val == AppointmentStatus.NO_SHOW.value:
                type_counts[type_val]["no_show"] += 1
            elif status_val == AppointmentStatus.CANCELLED.value:
                type_counts[type_val]["cancelled"] += 1

            # Duration (only for completed)
            if status_val == AppointmentStatus.COMPLETED.value and appt.duration_minutes:
                durations.append(appt.duration_minutes)

            # Day-of-week and hour distribution
            if appt.scheduled_time_start:
                weekday = appt.scheduled_time_start.weekday()
                day_counts[weekday] = day_counts.get(weekday, 0) + 1
                hour = appt.scheduled_time_start.hour
                hour_counts[hour] = hour_counts.get(hour, 0) + 1

            # Lead time (days between creation and scheduled date)
            if appt.created_at and appt.scheduled_date:
                created_date = (
                    appt.created_at.date()
                    if isinstance(appt.created_at, datetime)
                    else appt.created_at
                )
                lt = (appt.scheduled_date - created_date).days
                if lt >= 0:
                    lead_times.append(lt)

        analytics.total_completed = status_counts.get(AppointmentStatus.COMPLETED.value, 0)
        analytics.total_cancelled = status_counts.get(AppointmentStatus.CANCELLED.value, 0)
        analytics.total_no_shows = status_counts.get(AppointmentStatus.NO_SHOW.value, 0)
        analytics.total_rescheduled = status_counts.get(AppointmentStatus.RESCHEDULED.value, 0)

        # Rates
        actionable = analytics.total_scheduled - analytics.total_cancelled
        if actionable > 0:
            analytics.completion_rate = (analytics.total_completed / actionable) * 100
            analytics.no_show_rate = (analytics.total_no_shows / actionable) * 100

        # Average duration
        if durations:
            analytics.avg_duration_minutes = sum(durations) / len(durations)

        analytics.by_type = type_counts
        analytics.by_outcome = status_counts

        # Busiest day
        if day_counts:
            busiest_weekday = max(day_counts, key=day_counts.get)
            analytics.busiest_day = _WEEKDAY_NAMES[busiest_weekday] if busiest_weekday < 7 else None

        # Busiest hour
        if hour_counts:
            analytics.busiest_hour = max(hour_counts, key=hour_counts.get)

        # Average lead time
        if lead_times:
            analytics.avg_lead_time_days = sum(lead_times) / len(lead_times)

        return analytics

    async def get_pending_reminders(
        self,
        reminder_window: timedelta = REMINDER_24H,
    ) -> List[Dict[str, Any]]:
        """
        Get appointments needing reminders within the specified window.

        Used by a background task to send 24-hour and 1-hour reminders.

        Args:
            reminder_window: How far ahead to look (default 24 hours).

        Returns:
            List of appointment dicts with reminder details and document checklists.
        """
        now = datetime.now(timezone.utc)
        window_end = now + reminder_window

        appointments = (
            self.db.query(DocumentAppointment)
            .filter(
                DocumentAppointment.organization_id == self.org_id,
                DocumentAppointment.status.in_([
                    AppointmentStatus.SCHEDULED,
                    AppointmentStatus.CONFIRMED,
                ]),
                DocumentAppointment.scheduled_time_start >= now,
                DocumentAppointment.scheduled_time_start <= window_end,
                DocumentAppointment.reminder_sent == False,  # noqa: E712
            )
            .order_by(DocumentAppointment.scheduled_time_start.asc())
            .all()
        )

        reminders = []
        for appt in appointments:
            checklist = self._build_document_preparation_checklist(appt)
            reminders.append({
                "appointment_id": appt.id,
                "loan_id": appt.loan_id,
                "attendee_name": appt.attendee_name,
                "attendee_email": appt.attendee_email,
                "attendee_phone": appt.attendee_phone,
                "appointment_type": (
                    appt.appointment_type.value
                    if hasattr(appt.appointment_type, "value")
                    else str(appt.appointment_type)
                ),
                "scheduled_at": appt.scheduled_time_start.isoformat(),
                "duration_minutes": appt.duration_minutes,
                "meeting_link": appt.meeting_link,
                "location_type": (
                    appt.location_type.value
                    if hasattr(appt.location_type, "value")
                    else str(appt.location_type)
                ) if appt.location_type else None,
                "document_checklist": checklist,
            })

        return reminders

    async def mark_reminder_sent(self, appointment_id: int) -> None:
        """Mark an appointment's reminder as sent."""
        appt = self._get_appointment_or_raise(appointment_id)
        appt.reminder_sent = True
        appt.reminder_sent_at = datetime.now(timezone.utc)
        self.db.flush()

    async def complete_appointment(
        self,
        appointment_id: int,
        outcome_notes: Optional[str] = None,
        documents_collected: Optional[List[int]] = None,
        action_items: Optional[List[Dict[str, str]]] = None,
        update_loan_stage: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Complete an appointment and trigger post-appointment follow-up.

        Actions performed:
        - Mark appointment as COMPLETED.
        - Record outcome notes and documents collected.
        - Create tasks for action items (if provided).
        - Optionally advance loan stage.
        - Return summary for borrower notification.

        Args:
            appointment_id: Appointment to complete.
            outcome_notes: Summary of what was discussed/decided.
            documents_collected: List of document IDs collected during appointment.
            action_items: List of dicts with "title" and "description" for follow-up tasks.
            update_loan_stage: New loan stage to set (if applicable).

        Returns:
            Dict with completion summary.
        """
        appt = self._get_appointment_or_raise(appointment_id)

        appt.status = AppointmentStatus.COMPLETED
        appt.completed_at = datetime.now(timezone.utc)
        if outcome_notes:
            appt.outcome_notes = outcome_notes
        if documents_collected:
            appt.documents_collected = documents_collected

        # Create follow-up tasks
        tasks_created = []
        if action_items:
            tasks_created = self._create_followup_tasks(appt, action_items)

        # Optionally update loan stage
        stage_updated = False
        if update_loan_stage:
            stage_updated = self._update_loan_stage(appt.loan_id, update_loan_stage)

        self.db.flush()

        logger.info(
            f"Completed appointment {appointment_id} for loan {appt.loan_id}. "
            f"{len(tasks_created)} tasks created. Stage updated: {stage_updated}."
        )

        return {
            "appointment_id": appointment_id,
            "status": AppointmentStatus.COMPLETED.value,
            "completed_at": appt.completed_at.isoformat(),
            "outcome_notes": outcome_notes,
            "documents_collected": documents_collected or [],
            "tasks_created": tasks_created,
            "loan_stage_updated": stage_updated,
            "new_loan_stage": update_loan_stage if stage_updated else None,
            "summary_for_borrower": self._build_post_appointment_summary(
                appt, outcome_notes, tasks_created,
            ),
        }

    async def cancel_appointment(
        self,
        appointment_id: int,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel an appointment with optional reason."""
        appt = self._get_appointment_or_raise(appointment_id)

        appt.status = AppointmentStatus.CANCELLED
        appt.cancelled_at = datetime.now(timezone.utc)
        if reason:
            appt.cancellation_reason = reason
        self.db.flush()

        logger.info(f"Cancelled appointment {appointment_id}. Reason: {reason or 'none given'}")

        return {
            "appointment_id": appointment_id,
            "status": AppointmentStatus.CANCELLED.value,
            "cancelled_at": appt.cancelled_at.isoformat(),
            "reason": reason,
        }

    def generate_ical_event(
        self,
        appointment_id: int,
    ) -> str:
        """
        Generate an iCal (RFC 5545) event string for a document appointment.

        Returns a VCALENDAR string suitable for .ics file attachment
        or calendar subscription.

        Args:
            appointment_id: Appointment to generate iCal for.

        Returns:
            iCal formatted string.
        """
        appt = self._get_appointment_or_raise(appointment_id)

        uid = f"doc-appt-{appt.id}-{self.org_id}@perenniaai.com"
        dtstart = self._format_ical_datetime(appt.scheduled_time_start)
        dtend = self._format_ical_datetime(appt.scheduled_time_end) if appt.scheduled_time_end else ""

        if not dtend:
            # Calculate from duration
            end_dt = appt.scheduled_time_start + timedelta(minutes=appt.duration_minutes or 30)
            dtend = self._format_ical_datetime(end_dt)

        dtstamp = self._format_ical_datetime(datetime.now(timezone.utc))

        summary = self._ical_escape(appt.title or "Document Appointment")
        description_parts = []
        if appt.description:
            description_parts.append(appt.description)
        if appt.meeting_link:
            description_parts.append(f"Join: {appt.meeting_link}")
        description = self._ical_escape("\\n".join(description_parts))

        location = ""
        if appt.location_details:
            location = f"LOCATION:{self._ical_escape(appt.location_details)}\r\n"
        elif appt.meeting_link:
            location = f"LOCATION:{self._ical_escape(appt.meeting_link)}\r\n"

        # Build attendee lines
        attendee_lines = ""
        if appt.attendee_email:
            attendee_name = appt.attendee_name or "Borrower"
            attendee_lines += (
                f"ATTENDEE;CN={self._ical_escape(attendee_name)};"
                f"RSVP=TRUE:mailto:{appt.attendee_email}\r\n"
            )

        # VALARM for 24h and 1h reminders
        alarms = (
            "BEGIN:VALARM\r\n"
            "TRIGGER:-P1D\r\n"
            "ACTION:DISPLAY\r\n"
            "DESCRIPTION:Reminder: Document appointment tomorrow\r\n"
            "END:VALARM\r\n"
            "BEGIN:VALARM\r\n"
            "TRIGGER:-PT1H\r\n"
            "ACTION:DISPLAY\r\n"
            "DESCRIPTION:Reminder: Document appointment in 1 hour\r\n"
            "END:VALARM\r\n"
        )

        ical = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//Perennia AI//Smart Docs//EN\r\n"
            "CALSCALE:GREGORIAN\r\n"
            "METHOD:REQUEST\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            f"DTSTAMP:{dtstamp}\r\n"
            f"DTSTART:{dtstart}\r\n"
            f"DTEND:{dtend}\r\n"
            f"SUMMARY:{summary}\r\n"
            f"DESCRIPTION:{description}\r\n"
            f"{location}"
            f"{attendee_lines}"
            f"{alarms}"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

        return ical

    # -------------------------------------------------------------------------
    # PRIVATE: LOAN & APPOINTMENT LOOKUPS
    # -------------------------------------------------------------------------

    def _get_loan_or_raise(self, loan_id: int) -> Dict[str, Any]:
        """Fetch loan and verify it belongs to this org."""
        row = self.db.execute(
            text("""
                SELECT
                    l.id, l.loan_number, l.stage, l.loan_type, l.amount,
                    l.borrower_name, l.borrower_email, l.borrower_phone,
                    l.loan_officer_id, l.organization_id,
                    l.closing_date, l.lock_expiration_date,
                    l.stage_changed_at,
                    CONCAT(u.first_name, ' ', u.last_name) AS lo_name
                FROM loans l
                LEFT JOIN users u ON u.id = l.loan_officer_id
                WHERE l.id = :loan_id
            """),
            {"loan_id": loan_id},
        ).fetchone()

        if not row:
            raise LoanNotFoundError(loan_id)

        loan = dict(row._mapping)

        if loan.get("organization_id") and loan["organization_id"] != self.org_id:
            raise TenantIsolationError(
                message=f"Loan {loan_id} belongs to org {loan['organization_id']}, not {self.org_id}",
                requesting_org_id=self.org_id,
                target_org_id=loan["organization_id"],
            )

        return loan

    def _get_appointment_or_raise(self, appointment_id: int) -> DocumentAppointment:
        """Fetch appointment and verify org ownership."""
        appt = (
            self.db.query(DocumentAppointment)
            .filter(DocumentAppointment.id == appointment_id)
            .first()
        )
        if not appt:
            raise EntityNotFoundError("DocumentAppointment", appointment_id)

        if appt.organization_id and appt.organization_id != self.org_id:
            raise TenantIsolationError(
                message=f"Appointment {appointment_id} belongs to org {appt.organization_id}",
                requesting_org_id=self.org_id,
                target_org_id=appt.organization_id,
            )

        return appt

    # -------------------------------------------------------------------------
    # PRIVATE: AVAILABILITY & SLOT GENERATION
    # -------------------------------------------------------------------------

    def _get_business_hours(self) -> Dict[str, Dict[str, Any]]:
        """Get business hours from org scheduler settings or fall back to defaults."""
        try:
            row = self.db.execute(
                text("""
                    SELECT business_hours
                    FROM scheduler_settings
                    WHERE organization_id = :org_id
                    LIMIT 1
                """),
                {"org_id": self.org_id},
            ).fetchone()
            if row and row[0]:
                return row[0]
        except Exception as e:
            logger.debug(f"Could not fetch business hours for org {self.org_id}: {e}")

        return _DEFAULT_BUSINESS_HOURS

    def _get_all_busy_times(
        self,
        user_id: int,
        start_dt: datetime,
        end_dt: datetime,
    ) -> List[Tuple[datetime, datetime]]:
        """
        Gather busy time blocks from all calendar sources for a user.

        Checks:
        1. DocumentAppointment (this service's appointments)
        2. ScheduledAppointment (general scheduler appointments)
        3. CalendarEvent (manual calendar entries)
        4. CRMCalendarEvent (Salesforce-synced events)
        """
        conflicts: List[Tuple[datetime, datetime]] = []

        # Source 1: DocumentAppointment (our own doc appointments)
        try:
            doc_appts = (
                self.db.query(DocumentAppointment)
                .filter(
                    DocumentAppointment.assigned_to_user_id == user_id,
                    DocumentAppointment.status.in_([
                        AppointmentStatus.SCHEDULED,
                        AppointmentStatus.CONFIRMED,
                        AppointmentStatus.IN_PROGRESS,
                    ]),
                    DocumentAppointment.scheduled_time_start >= start_dt,
                    DocumentAppointment.scheduled_time_start <= end_dt,
                )
                .all()
            )
            for a in doc_appts:
                if a.scheduled_time_start and a.scheduled_time_end:
                    conflicts.append((a.scheduled_time_start, a.scheduled_time_end))
                elif a.scheduled_time_start and a.duration_minutes:
                    conflicts.append((
                        a.scheduled_time_start,
                        a.scheduled_time_start + timedelta(minutes=a.duration_minutes),
                    ))
        except Exception as e:
            logger.debug(f"DocumentAppointment availability check: {e}")

        # Source 2: ScheduledAppointment (general scheduler)
        try:
            from services.smart_scheduler_service import ScheduledAppointment as SA
            sa_appts = (
                self.db.query(SA)
                .filter(
                    SA.loan_officer_id == user_id,
                    SA.status.in_(["scheduled", "confirmed"]),
                    SA.start_time >= start_dt,
                    SA.start_time <= end_dt,
                )
                .all()
            )
            for a in sa_appts:
                if a.start_time and a.end_time:
                    conflicts.append((a.start_time, a.end_time))
        except Exception as e:
            logger.debug(f"ScheduledAppointment cross-source check: {e}")

        # Source 3: CalendarEvent (manual calendar entries)
        try:
            import main
            CalendarEvent = main.CalendarEvent
            cal_events = (
                self.db.query(CalendarEvent)
                .filter(
                    CalendarEvent.user_id == user_id,
                    CalendarEvent.status != "cancelled",
                    CalendarEvent.start_time >= start_dt,
                    CalendarEvent.start_time <= end_dt,
                )
                .all()
            )
            for ev in cal_events:
                if ev.start_time and ev.end_time:
                    conflicts.append((ev.start_time, ev.end_time))
        except Exception as e:
            logger.debug(f"CalendarEvent cross-source check skipped: {e}")

        # Source 4: CRMCalendarEvent (Salesforce-synced)
        try:
            from models.calendar_sync_models import CRMCalendarEvent
            crm_events = (
                self.db.query(CRMCalendarEvent)
                .filter(
                    CRMCalendarEvent.owner_user_id == user_id,
                    CRMCalendarEvent.status != "canceled",
                    CRMCalendarEvent.start_at >= start_dt,
                    CRMCalendarEvent.start_at <= end_dt,
                )
                .all()
            )
            for ev in crm_events:
                if ev.start_at and ev.end_at:
                    conflicts.append((ev.start_at, ev.end_at))
        except Exception as e:
            logger.debug(f"CRMCalendarEvent cross-source check skipped: {e}")

        return conflicts

    def _generate_candidate_slots(
        self,
        search_start: datetime,
        search_end: datetime,
        duration_minutes: int,
        business_hours: Dict[str, Dict[str, Any]],
        busy_times: List[Tuple[datetime, datetime]],
        milestone_blackouts: List[Tuple[datetime, datetime]],
    ) -> List[TimeSlot]:
        """
        Generate available time slots within business hours that do not conflict
        with existing busy times or milestone blackouts.
        """
        all_blocked = busy_times + milestone_blackouts
        candidates: List[TimeSlot] = []
        buffer = timedelta(minutes=APPOINTMENT_BUFFER_MINUTES)
        slot_duration = timedelta(minutes=duration_minutes)

        # Iterate day by day
        current_date = search_start.date()
        end_date = search_end.date()

        while current_date <= end_date:
            weekday_name = _WEEKDAY_NAMES[current_date.weekday()]
            day_config = business_hours.get(weekday_name, {})

            if not day_config.get("enabled", False):
                current_date += timedelta(days=1)
                continue

            start_str = day_config.get("start", "09:00")
            end_str = day_config.get("end", "17:00")

            try:
                day_start_time = time.fromisoformat(start_str)
                day_end_time = time.fromisoformat(end_str)
            except (ValueError, TypeError):
                current_date += timedelta(days=1)
                continue

            day_start = datetime.combine(current_date, day_start_time, tzinfo=timezone.utc)
            day_end = datetime.combine(current_date, day_end_time, tzinfo=timezone.utc)

            # Ensure we don't start before search_start
            if day_start < search_start:
                day_start = search_start

            # Generate 30-minute interval candidates within business hours
            slot_start = day_start
            while slot_start + slot_duration <= day_end:
                slot_end = slot_start + slot_duration

                # Check for conflicts (including buffer)
                buffered_start = slot_start - buffer
                buffered_end = slot_end + buffer

                has_conflict = False
                conflict_reasons: List[str] = []
                for busy_start, busy_end in all_blocked:
                    if buffered_start < busy_end and buffered_end > busy_start:
                        has_conflict = True
                        conflict_reasons.append(
                            f"Conflict {busy_start.strftime('%H:%M')}-{busy_end.strftime('%H:%M')}"
                        )
                        break

                if not has_conflict:
                    candidates.append(TimeSlot(
                        start=slot_start,
                        end=slot_end,
                        duration_minutes=duration_minutes,
                    ))

                # Advance by 30-minute intervals
                slot_start += timedelta(minutes=30)

            current_date += timedelta(days=1)

        return candidates

    def _score_slots(
        self,
        candidates: List[TimeSlot],
        borrower_pattern: Dict[str, Any],
        preferred_dates: Optional[List[date]],
        lo_user_id: int,
        lo_name: str,
    ) -> List[TimeSlot]:
        """
        Score candidate slots based on multiple factors:
        - Borrower preferred hours (from activity patterns)
        - Preferred dates from caller
        - Morning/afternoon preference
        - Proximity (sooner is slightly better for urgency)
        """
        preferred_hour = borrower_pattern.get("preferred_hour")
        preferred_days = borrower_pattern.get("preferred_days", [])

        now = datetime.now(timezone.utc)

        for slot in candidates:
            score = 50.0  # Base score
            reasons: List[str] = []

            # Borrower preferred hour match (+20)
            if preferred_hour is not None:
                hour_diff = abs(slot.start.hour - preferred_hour)
                if hour_diff <= 1:
                    score += 20
                    reasons.append("Matches borrower preferred time")
                elif hour_diff <= 2:
                    score += 10

            # Borrower preferred day-of-week (+15)
            if slot.start.weekday() in preferred_days:
                score += 15
                reasons.append("Preferred day of week")

            # Caller-specified preferred dates (+25)
            if preferred_dates and slot.start.date() in preferred_dates:
                score += 25
                reasons.append("Requested date")

            # Mid-morning bonus (10-11am is generally best for appointments) (+10)
            if 10 <= slot.start.hour <= 11:
                score += 10
                reasons.append("Optimal mid-morning slot")
            elif 14 <= slot.start.hour <= 15:
                score += 5
                reasons.append("Good early-afternoon slot")

            # Sooner is slightly better (up to +10 based on proximity)
            days_out = (slot.start - now).days
            if days_out <= 2:
                score += 10
                reasons.append("Available soon")
            elif days_out <= 5:
                score += 5

            # Avoid Mondays and Fridays slightly (-5)
            if slot.start.weekday() in (0, 4):
                score -= 5

            slot.score = min(score, 100.0)
            slot.reason = "; ".join(reasons) if reasons else "Available slot"
            slot.lo_user_id = lo_user_id
            slot.lo_name = lo_name

        return candidates

    def _get_milestone_blackout_windows(
        self,
        loan: Dict[str, Any],
    ) -> List[Tuple[datetime, datetime]]:
        """
        Generate blackout windows around important loan milestones.

        Avoids scheduling doc appointments on the closing date or
        the day a rate lock expires, when the LO is likely fully occupied.
        """
        blackouts: List[Tuple[datetime, datetime]] = []

        closing_date = loan.get("closing_date")
        if closing_date:
            if isinstance(closing_date, datetime):
                closing_date = closing_date.date()
            if isinstance(closing_date, date):
                # Block the full closing day
                blackouts.append((
                    datetime.combine(closing_date, time.min, tzinfo=timezone.utc),
                    datetime.combine(closing_date, time.max, tzinfo=timezone.utc),
                ))

        lock_expiration = loan.get("lock_expiration_date")
        if lock_expiration:
            if isinstance(lock_expiration, datetime):
                lock_expiration = lock_expiration.date()
            if isinstance(lock_expiration, date):
                # Block the lock expiration day
                blackouts.append((
                    datetime.combine(lock_expiration, time.min, tzinfo=timezone.utc),
                    datetime.combine(lock_expiration, time.max, tzinfo=timezone.utc),
                ))

        return blackouts

    def _analyze_borrower_patterns(
        self,
        loan_id: int,
    ) -> Dict[str, Any]:
        """
        Analyze borrower activity patterns to determine preferred contact times.

        Looks at:
        - Document upload times
        - Activity/engagement timestamps on the associated lead
        - Prior appointment times

        Returns dict with preferred_hour (int) and preferred_days (list of weekday ints).
        """
        patterns: Dict[str, Any] = {
            "preferred_hour": None,
            "preferred_days": [],
        }

        # Get borrower activity timestamps from document uploads
        try:
            upload_rows = self.db.execute(
                text("""
                    SELECT
                        EXTRACT(HOUR FROM d.uploaded_at) AS upload_hour,
                        EXTRACT(DOW FROM d.uploaded_at) AS upload_dow
                    FROM documents d
                    WHERE d.loan_id = :loan_id
                        AND d.uploaded_at IS NOT NULL
                """),
                {"loan_id": loan_id},
            ).fetchall()

            hours: List[int] = []
            days: List[int] = []
            for row in upload_rows:
                if row[0] is not None:
                    hours.append(int(row[0]))
                if row[1] is not None:
                    # PostgreSQL DOW: Sunday=0, Monday=1, ..., Saturday=6
                    # Python weekday: Monday=0, ..., Sunday=6
                    pg_dow = int(row[1])
                    py_weekday = (pg_dow - 1) % 7
                    days.append(py_weekday)

            if hours:
                # Most common hour
                patterns["preferred_hour"] = max(set(hours), key=hours.count)

            if days:
                # Top 3 most common days
                unique_days = list(set(days))
                unique_days.sort(key=lambda d: days.count(d), reverse=True)
                patterns["preferred_days"] = unique_days[:3]

        except Exception as e:
            logger.debug(f"Borrower pattern analysis failed for loan {loan_id}: {e}")

        return patterns

    # -------------------------------------------------------------------------
    # PRIVATE: DOCUMENT & ISSUE GATHERING
    # -------------------------------------------------------------------------

    def _get_documents_for_appointment(
        self,
        appt: DocumentAppointment,
    ) -> List[Dict[str, Any]]:
        """Get document details for the appointment's linked document IDs."""
        doc_ids = appt.documents_to_discuss
        if not doc_ids:
            # Fall back to all pending documents for the loan
            return self._get_pending_documents_for_loan(appt.loan_id)

        try:
            rows = self.db.execute(
                text("""
                    SELECT id, doc_type, doc_category, status, filename, uploaded_at
                    FROM documents
                    WHERE loan_id = :loan_id
                        AND id = ANY(:doc_ids)
                    ORDER BY uploaded_at DESC NULLS LAST
                """),
                {"loan_id": appt.loan_id, "doc_ids": doc_ids},
            ).fetchall()

            return [
                {
                    "id": row[0],
                    "doc_type": row[1],
                    "doc_category": row[2],
                    "status": row[3],
                    "filename": row[4],
                    "uploaded_at": row[5].isoformat() if row[5] else None,
                }
                for row in rows
            ]
        except Exception as e:
            logger.debug(f"Error fetching documents for appointment {appt.id}: {e}")
            return self._get_pending_documents_for_loan(appt.loan_id)

    def _get_pending_documents_for_loan(
        self,
        loan_id: int,
    ) -> List[Dict[str, Any]]:
        """Get all pending/recently uploaded documents for a loan."""
        try:
            rows = self.db.execute(
                text("""
                    SELECT id, doc_type, doc_category, status, filename, uploaded_at
                    FROM documents
                    WHERE loan_id = :loan_id
                    ORDER BY uploaded_at DESC NULLS LAST
                    LIMIT 20
                """),
                {"loan_id": loan_id},
            ).fetchall()

            return [
                {
                    "id": row[0],
                    "doc_type": row[1],
                    "doc_category": row[2],
                    "status": row[3],
                    "filename": row[4],
                    "uploaded_at": row[5].isoformat() if row[5] else None,
                }
                for row in rows
            ]
        except Exception as e:
            logger.debug(f"Error fetching pending docs for loan {loan_id}: {e}")
            return []

    def _get_issues_for_loan(
        self,
        loan_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Gather issues to discuss: missing docs, expired docs, compliance alerts.
        """
        issues: List[Dict[str, Any]] = []

        # Check for open compliance alerts
        try:
            alert_rows = self.db.execute(
                text("""
                    SELECT id, alert_type, severity, title, status, deadline_date
                    FROM compliance_alerts
                    WHERE loan_id = :loan_id AND status = 'open'
                    ORDER BY
                        CASE severity
                            WHEN 'critical' THEN 1
                            WHEN 'high' THEN 2
                            WHEN 'medium' THEN 3
                            ELSE 4
                        END
                    LIMIT 10
                """),
                {"loan_id": loan_id},
            ).fetchall()

            for row in alert_rows:
                issues.append({
                    "type": "compliance_alert",
                    "id": row[0],
                    "alert_type": row[1],
                    "severity": row[2],
                    "title": row[3],
                    "deadline": row[5].isoformat() if row[5] else None,
                })
        except Exception as e:
            logger.debug(f"Error fetching compliance alerts for loan {loan_id}: {e}")

        # Check for expiring documents
        try:
            loan_dates = self.db.execute(
                text("""
                    SELECT credit_docs_expire_date, appraisal_docs_expire_date
                    FROM loans
                    WHERE id = :loan_id
                """),
                {"loan_id": loan_id},
            ).fetchone()

            if loan_dates:
                today = date.today()
                for col_idx, doc_type in [(0, "credit_docs"), (1, "appraisal_docs")]:
                    expire_dt = loan_dates[col_idx]
                    if expire_dt:
                        if isinstance(expire_dt, datetime):
                            expire_dt = expire_dt.date()
                        if isinstance(expire_dt, date) and expire_dt <= today + timedelta(days=30):
                            days_remaining = (expire_dt - today).days
                            issues.append({
                                "type": "expiring_document",
                                "doc_type": doc_type,
                                "expires_at": expire_dt.isoformat(),
                                "days_remaining": days_remaining,
                                "severity": "critical" if days_remaining < 0 else (
                                    "high" if days_remaining < 7 else "medium"
                                ),
                            })
        except Exception as e:
            logger.debug(f"Error checking document expiration for loan {loan_id}: {e}")

        return issues

    def _count_outstanding_conditions(self, loan_id: int) -> int:
        """Count open compliance alerts/conditions for a loan."""
        try:
            result = self.db.execute(
                text("""
                    SELECT COUNT(*)
                    FROM compliance_alerts
                    WHERE loan_id = :loan_id AND status = 'open'
                """),
                {"loan_id": loan_id},
            ).scalar()
            return result or 0
        except Exception as e:
            logger.debug(f"Error counting conditions for loan {loan_id}: {e}")
            return 0

    # -------------------------------------------------------------------------
    # PRIVATE: AGENDA & SUMMARY BUILDERS
    # -------------------------------------------------------------------------

    def _build_agenda(
        self,
        appointment_type,
        documents_to_review: List[Dict[str, Any]],
        issues: List[Dict[str, Any]],
        outstanding_conditions: int,
        loan_stage: Optional[str],
    ) -> List[str]:
        """Build a structured agenda for the appointment."""
        agenda: List[str] = []

        type_val = (
            appointment_type.value
            if hasattr(appointment_type, "value")
            else str(appointment_type)
        )

        # Opening
        agenda.append("Welcome and appointment overview")

        # Type-specific items
        if type_val in ("document_review", DocAppointmentType.DOCUMENT_REVIEW.value):
            if documents_to_review:
                agenda.append(f"Review {len(documents_to_review)} uploaded document(s)")
            agenda.append("Verify document completeness and accuracy")
            agenda.append("Discuss any missing information")

        elif type_val in ("notary_signing", DocAppointmentType.SIGNING_APPOINTMENT.value):
            agenda.append("Review signing package documents")
            agenda.append("Execute signatures on all required documents")
            agenda.append("Confirm notarization requirements")

        elif type_val == DocAppointmentType.CONDITION_CLEARANCE.value:
            if outstanding_conditions:
                agenda.append(f"Review {outstanding_conditions} outstanding condition(s)")
            agenda.append("Discuss required documentation for condition clearance")
            agenda.append("Establish timeline for condition resolution")

        elif type_val in ("general_consultation", DocAppointmentType.INITIAL_CONSULTATION.value):
            agenda.append("Review complete document requirements checklist")
            agenda.append("Explain document submission process")
            agenda.append("Address borrower questions about requirements")

        elif type_val == DocAppointmentType.CLOSING_PREP.value:
            agenda.append("Review pre-closing document checklist")
            agenda.append("Verify all conditions have been cleared")
            agenda.append("Confirm closing date, time, and logistics")
            if loan_stage:
                agenda.append(f"Current loan stage: {loan_stage}")

        # Issues
        critical_issues = [i for i in issues if i.get("severity") in ("critical", "high")]
        if critical_issues:
            agenda.append(f"Address {len(critical_issues)} high-priority issue(s)")

        # Wrap up
        agenda.append("Confirm next steps and action items")
        agenda.append("Schedule follow-up if needed")

        return agenda

    def _build_document_preparation_checklist(
        self,
        appt: DocumentAppointment,
    ) -> List[Dict[str, str]]:
        """
        Build a checklist of documents the borrower should prepare before the appointment.
        """
        checklist: List[Dict[str, str]] = []

        type_val = (
            appt.appointment_type.value
            if hasattr(appt.appointment_type, "value")
            else str(appt.appointment_type)
        )

        # Generic preparation items
        checklist.append({
            "item": "Valid government-issued photo ID",
            "status": "required",
        })

        if type_val in ("document_review", "document_collection"):
            checklist.append({
                "item": "Any outstanding documents requested by your loan officer",
                "status": "required",
            })
            checklist.append({
                "item": "Recent pay stubs (last 30 days) if requested",
                "status": "if_applicable",
            })
            checklist.append({
                "item": "Bank statements (last 2 months) if requested",
                "status": "if_applicable",
            })

        elif type_val == "notary_signing":
            checklist.append({
                "item": "Two forms of identification",
                "status": "required",
            })
            checklist.append({
                "item": "Certified check or wire transfer confirmation for closing costs",
                "status": "required",
            })

        elif type_val == "general_consultation":
            checklist.append({
                "item": "List of questions about the loan process",
                "status": "recommended",
            })

        # Add specific docs if linked
        if appt.documents_to_discuss:
            try:
                doc_rows = self.db.execute(
                    text("""
                        SELECT doc_type FROM documents
                        WHERE loan_id = :loan_id AND id = ANY(:doc_ids)
                    """),
                    {"loan_id": appt.loan_id, "doc_ids": appt.documents_to_discuss},
                ).fetchall()
                for row in doc_rows:
                    checklist.append({
                        "item": f"Updated {row[0]} document",
                        "status": "required",
                    })
            except Exception as e:
                logger.debug(f"Error building doc checklist for appointment {appt.id}: {e}")

        return checklist

    def _build_post_appointment_summary(
        self,
        appt: DocumentAppointment,
        outcome_notes: Optional[str],
        tasks_created: List[Dict[str, Any]],
    ) -> str:
        """Build a text summary suitable for sending to the borrower."""
        lines = [
            f"Summary of your {appt.title or 'document appointment'}:",
            "",
        ]

        if outcome_notes:
            lines.append(f"Discussion notes: {outcome_notes}")
            lines.append("")

        if appt.documents_collected:
            lines.append(f"Documents collected: {len(appt.documents_collected)}")
            lines.append("")

        if tasks_created:
            lines.append("Action items:")
            for i, task in enumerate(tasks_created, 1):
                lines.append(f"  {i}. {task.get('title', 'Follow-up item')}")
            lines.append("")

        lines.append(
            "If you have any questions, please contact your loan officer. "
            "Thank you for your time."
        )

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # PRIVATE: TASK CREATION & LOAN UPDATES
    # -------------------------------------------------------------------------

    def _create_followup_tasks(
        self,
        appt: DocumentAppointment,
        action_items: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """
        Create follow-up tasks from appointment action items.

        Inserts into the tasks table if it exists, otherwise returns
        the planned tasks without DB insertion.
        """
        tasks_created: List[Dict[str, Any]] = []

        for item in action_items:
            title = item.get("title", "Follow-up from document appointment")
            description = item.get("description", "")
            due_date = item.get("due_date")

            try:
                self.db.execute(
                    text("""
                        INSERT INTO tasks (
                            organization_id, title, description,
                            assigned_to, related_loan_id,
                            status, due_date, created_at
                        ) VALUES (
                            :org_id, :title, :description,
                            :assigned_to, :loan_id,
                            'pending', :due_date, NOW()
                        )
                        RETURNING id
                    """),
                    {
                        "org_id": self.org_id,
                        "title": title,
                        "description": (
                            f"{description}\n\n"
                            f"Created from appointment: {appt.title} "
                            f"(ID: {appt.id})"
                        ),
                        "assigned_to": appt.assigned_to_user_id,
                        "loan_id": appt.loan_id,
                        "due_date": due_date,
                    },
                )
                task_row = self.db.execute(text("SELECT lastval()")).scalar()
                tasks_created.append({
                    "id": task_row,
                    "title": title,
                    "assigned_to": appt.assigned_to_user_id,
                })
            except Exception as e:
                logger.warning(f"Could not create follow-up task: {e}")
                # Still track it even if DB insert fails
                tasks_created.append({
                    "id": None,
                    "title": title,
                    "assigned_to": appt.assigned_to_user_id,
                    "error": str(e),
                })

        return tasks_created

    def _create_no_show_followup_task(
        self,
        appt: DocumentAppointment,
        no_show_count: int,
    ) -> None:
        """Create a task for the LO to follow up on repeated no-shows."""
        try:
            self.db.execute(
                text("""
                    INSERT INTO tasks (
                        organization_id, title, description,
                        assigned_to, related_loan_id,
                        status, priority, created_at
                    ) VALUES (
                        :org_id, :title, :description,
                        :assigned_to, :loan_id,
                        'pending', 'high', NOW()
                    )
                """),
                {
                    "org_id": self.org_id,
                    "title": f"Follow up: Borrower missed {no_show_count} document appointment(s)",
                    "description": (
                        f"Borrower {appt.attendee_name or 'Unknown'} has missed "
                        f"{no_show_count} scheduled document appointment(s) for this loan. "
                        f"Please reach out to reschedule and discuss any issues preventing attendance."
                    ),
                    "assigned_to": appt.assigned_to_user_id,
                    "loan_id": appt.loan_id,
                },
            )
        except Exception as e:
            logger.warning(f"Could not create no-show follow-up task: {e}")

    def _update_loan_stage(self, loan_id: int, new_stage: str) -> bool:
        """Update loan stage if the new stage is valid."""
        valid_stages = {
            "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
            "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
            "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
            "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
        }
        if new_stage.upper() not in valid_stages:
            logger.warning(f"Invalid loan stage for update: {new_stage}")
            return False

        try:
            self.db.execute(
                text("""
                    UPDATE loans
                    SET stage = :stage, stage_changed_at = NOW(), updated_at = NOW()
                    WHERE id = :loan_id AND organization_id = :org_id
                """),
                {
                    "stage": new_stage.upper(),
                    "loan_id": loan_id,
                    "org_id": self.org_id,
                },
            )
            return True
        except Exception as e:
            logger.warning(f"Could not update loan stage for loan {loan_id}: {e}")
            return False

    # -------------------------------------------------------------------------
    # PRIVATE: MEETING LINK & ICAL HELPERS
    # -------------------------------------------------------------------------

    def _generate_meeting_link_placeholder(self, loan_id: int) -> str:
        """
        Generate a placeholder meeting link.

        In production, this hook should be replaced with actual video meeting
        integration (e.g., Zoom, Google Meet, or the platform's built-in
        video meeting service).

        Returns a URL that can be swapped by the video integration layer.
        """
        meeting_id = uuid.uuid4().hex[:12]
        return f"https://app.perenniaai.com/meet/{meeting_id}?loan={loan_id}"

    @staticmethod
    def _format_ical_datetime(dt: datetime) -> str:
        """Format a datetime for iCal (UTC)."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        utc_dt = dt.astimezone(timezone.utc)
        return utc_dt.strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def _ical_escape(text_val: str) -> str:
        """Escape special characters for iCal text fields."""
        return (
            text_val
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
        )

    # -------------------------------------------------------------------------
    # PRIVATE: DATE HELPERS
    # -------------------------------------------------------------------------

    @staticmethod
    def _next_business_day(
        from_dt: datetime,
        skip_days: int = 1,
    ) -> datetime:
        """
        Advance to the next business day, skipping weekends.

        Args:
            from_dt: Starting datetime.
            skip_days: Minimum number of business days to skip.

        Returns:
            datetime on the target business day (same time).
        """
        current = from_dt
        skipped = 0
        while skipped < skip_days:
            current += timedelta(days=1)
            if current.weekday() < 5:  # Monday-Friday
                skipped += 1
        return current

    @staticmethod
    def _resolve_appointment_type(type_str: str) -> DocAppointmentType:
        """Resolve a string to a DocAppointmentType enum value."""
        # Try direct match
        try:
            return DocAppointmentType(type_str.lower())
        except ValueError:
            pass

        # Try uppercase/enum-name match
        try:
            return DocAppointmentType[type_str.upper()]
        except KeyError:
            pass

        # Default
        logger.warning(f"Unknown appointment type '{type_str}', defaulting to DOCUMENT_REVIEW")
        return DocAppointmentType.DOCUMENT_REVIEW


# =============================================================================
# MODULE-LEVEL FACTORY
# =============================================================================

def get_appointment_intelligence_service(
    db: Session,
    org_id: int,
    user_id: Optional[int] = None,
) -> AppointmentIntelligenceService:
    """Factory function for creating an AppointmentIntelligenceService instance."""
    return AppointmentIntelligenceService(db=db, org_id=org_id, user_id=user_id)
