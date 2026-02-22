"""
Scheduling Service

Schedules follow-up calls, appointments, and tasks based on
call intelligence results and orchestration decisions.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================

class AppointmentType(str, Enum):
    """Types of appointments."""
    FOLLOWUP_CALL = "followup_call"
    CONSULTATION = "consultation"
    APPLICATION_REVIEW = "application_review"
    DOCUMENT_REVIEW = "document_review"
    CLOSING_PREP = "closing_prep"
    CUSTOM = "custom"


class AppointmentStatus(str, Enum):
    """Appointment status."""
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


class FollowupPriority(str, Enum):
    """Follow-up priority levels."""
    URGENT = "urgent"  # Same day
    HIGH = "high"      # Within 24 hours
    NORMAL = "normal"  # Within 2-3 days
    LOW = "low"        # Within a week


@dataclass
class TimeSlot:
    """Available time slot."""
    start_time: datetime
    end_time: datetime
    available: bool = True

    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() / 60)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_minutes": self.duration_minutes,
            "available": self.available,
        }


@dataclass
class ScheduledFollowup:
    """A scheduled follow-up appointment."""
    followup_id: str
    call_id: str
    appointment_type: AppointmentType
    status: AppointmentStatus = AppointmentStatus.SCHEDULED

    # Timing
    scheduled_date: Optional[datetime] = None
    duration_minutes: int = 30
    timezone: str = "America/New_York"

    # Participants
    borrower_name: str = ""
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    assigned_to: Optional[str] = None

    # Details
    subject: str = ""
    notes: str = ""
    preparation_items: List[str] = field(default_factory=list)
    meeting_link: Optional[str] = None

    # Reminders
    send_reminder: bool = True
    reminder_hours_before: int = 24

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    priority: FollowupPriority = FollowupPriority.NORMAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "followup_id": self.followup_id,
            "call_id": self.call_id,
            "appointment_type": self.appointment_type.value,
            "status": self.status.value,
            "scheduled_date": self.scheduled_date.isoformat() if self.scheduled_date else None,
            "duration_minutes": self.duration_minutes,
            "timezone": self.timezone,
            "borrower_name": self.borrower_name,
            "borrower_email": self.borrower_email,
            "borrower_phone": self.borrower_phone,
            "assigned_to": self.assigned_to,
            "subject": self.subject,
            "notes": self.notes,
            "preparation_items": self.preparation_items,
            "meeting_link": self.meeting_link,
            "send_reminder": self.send_reminder,
            "reminder_hours_before": self.reminder_hours_before,
            "created_at": self.created_at.isoformat(),
            "priority": self.priority.value,
        }


# Default business hours
DEFAULT_BUSINESS_HOURS = {
    0: None,  # Monday - use default
    1: None,  # Tuesday
    2: None,  # Wednesday
    3: None,  # Thursday
    4: None,  # Friday
    5: None,  # Saturday - closed by default
    6: None,  # Sunday - closed by default
}

DEFAULT_START_TIME = time(9, 0)   # 9 AM
DEFAULT_END_TIME = time(17, 0)    # 5 PM
DEFAULT_SLOT_DURATION = 30        # 30 minutes


class SchedulingService:
    """
    Manages scheduling of follow-up calls and appointments.

    Usage:
        service = SchedulingService(calendar_client)

        # Schedule based on urgency from call
        followup = await service.schedule_followup(
            extracted_data=extracted_data,
            call_id=call_id,
            appointment_type=AppointmentType.FOLLOWUP_CALL,
        )

        # Get available slots
        slots = await service.get_available_slots(
            assigned_to="user_123",
            start_date=datetime.now(),
            days=7,
        )
    """

    def __init__(
        self,
        calendar_client=None,
        business_hours: Optional[Dict] = None,
        slot_duration: int = DEFAULT_SLOT_DURATION,
    ):
        """
        Initialize scheduling service.

        Args:
            calendar_client: Calendar integration client (optional for testing)
            business_hours: Custom business hours by day of week
            slot_duration: Default appointment slot duration in minutes
        """
        self.calendar_client = calendar_client
        self.business_hours = business_hours or DEFAULT_BUSINESS_HOURS
        self.slot_duration = slot_duration

        # In-memory storage for testing
        self._scheduled: Dict[str, ScheduledFollowup] = {}

    async def schedule_followup(
        self,
        extracted_data: Dict[str, Any],
        call_id: str,
        appointment_type: AppointmentType = AppointmentType.FOLLOWUP_CALL,
        assigned_to: Optional[str] = None,
        preferred_date: Optional[datetime] = None,
        duration_minutes: Optional[int] = None,
    ) -> ScheduledFollowup:
        """
        Schedule a follow-up based on call data.

        Args:
            extracted_data: Data extracted from the call
            call_id: Unique call identifier
            appointment_type: Type of appointment
            assigned_to: User ID to assign the follow-up to
            preferred_date: Preferred date/time (if any)
            duration_minutes: Duration override

        Returns:
            ScheduledFollowup with appointment details
        """
        # Extract borrower information
        identity = extracted_data.get("identity", {})
        intent = extracted_data.get("intent", {})

        first_name = self._get_value(identity, "first_name") or "Borrower"
        last_name = self._get_value(identity, "last_name") or ""
        email = self._get_value(identity, "email")
        phone = self._get_value(identity, "phone")

        # Determine priority based on extracted data
        priority = self._determine_priority(extracted_data)

        # Determine when to schedule
        if preferred_date:
            scheduled_date = preferred_date
        else:
            scheduled_date = await self._find_next_available_slot(
                assigned_to=assigned_to,
                priority=priority,
                duration=duration_minutes or self.slot_duration,
            )

        # Generate follow-up ID
        followup_id = str(uuid.uuid4())[:8].upper()

        # Create follow-up record
        followup = ScheduledFollowup(
            followup_id=followup_id,
            call_id=call_id,
            appointment_type=appointment_type,
            scheduled_date=scheduled_date,
            duration_minutes=duration_minutes or self._get_default_duration(appointment_type),
            borrower_name=f"{first_name} {last_name}".strip(),
            borrower_email=email,
            borrower_phone=phone,
            assigned_to=assigned_to,
            subject=self._generate_subject(appointment_type, first_name),
            notes=self._generate_notes(extracted_data, appointment_type),
            preparation_items=self._get_preparation_items(appointment_type),
            priority=priority,
        )

        # Store the follow-up
        if self.calendar_client:
            try:
                event_id = await self.calendar_client.create_event(
                    title=followup.subject,
                    start=followup.scheduled_date,
                    duration_minutes=followup.duration_minutes,
                    attendees=[email] if email else [],
                    description=followup.notes,
                )
                followup.meeting_link = f"https://calendar.example.com/event/{event_id}"
            except Exception as e:
                logger.warning(f"Failed to create calendar event: {e}")

        # Store in memory
        self._scheduled[followup_id] = followup

        logger.info(
            f"Scheduled {appointment_type.value} for call {call_id}: "
            f"{followup.scheduled_date}, priority: {priority.value}"
        )

        return followup

    async def get_available_slots(
        self,
        assigned_to: Optional[str] = None,
        start_date: Optional[datetime] = None,
        days: int = 7,
        duration_minutes: int = 30,
    ) -> List[TimeSlot]:
        """
        Get available time slots.

        Args:
            assigned_to: User ID to check availability for
            start_date: Start date for slot search
            days: Number of days to check
            duration_minutes: Required slot duration

        Returns:
            List of available TimeSlots
        """
        start = start_date or datetime.now()
        slots: List[TimeSlot] = []

        for day_offset in range(days):
            current_date = start + timedelta(days=day_offset)
            day_of_week = current_date.weekday()

            # Check if business day
            if not self._is_business_day(day_of_week):
                continue

            # Get business hours for this day
            start_time, end_time = self._get_business_hours(day_of_week)

            # Generate slots for the day
            current_slot_start = datetime.combine(current_date.date(), start_time)
            end_of_day = datetime.combine(current_date.date(), end_time)

            while current_slot_start + timedelta(minutes=duration_minutes) <= end_of_day:
                slot_end = current_slot_start + timedelta(minutes=duration_minutes)

                # Check availability (would query calendar in production)
                is_available = await self._check_slot_availability(
                    assigned_to=assigned_to,
                    start=current_slot_start,
                    end=slot_end,
                )

                slots.append(TimeSlot(
                    start_time=current_slot_start,
                    end_time=slot_end,
                    available=is_available,
                ))

                current_slot_start = slot_end

        return slots

    async def reschedule(
        self,
        followup_id: str,
        new_date: datetime,
    ) -> ScheduledFollowup:
        """
        Reschedule an existing follow-up.

        Args:
            followup_id: Follow-up ID to reschedule
            new_date: New date/time

        Returns:
            Updated ScheduledFollowup
        """
        followup = self._scheduled.get(followup_id)
        if not followup:
            raise ValueError(f"Follow-up {followup_id} not found")

        old_date = followup.scheduled_date
        followup.scheduled_date = new_date
        followup.status = AppointmentStatus.RESCHEDULED

        if self.calendar_client:
            try:
                await self.calendar_client.update_event(
                    event_id=followup_id,
                    start=new_date,
                )
            except Exception as e:
                logger.warning(f"Failed to update calendar event: {e}")

        logger.info(f"Rescheduled {followup_id}: {old_date} -> {new_date}")

        return followup

    async def cancel(
        self,
        followup_id: str,
        reason: Optional[str] = None,
    ) -> ScheduledFollowup:
        """
        Cancel a scheduled follow-up.

        Args:
            followup_id: Follow-up ID to cancel
            reason: Cancellation reason

        Returns:
            Updated ScheduledFollowup
        """
        followup = self._scheduled.get(followup_id)
        if not followup:
            raise ValueError(f"Follow-up {followup_id} not found")

        followup.status = AppointmentStatus.CANCELLED
        if reason:
            followup.notes += f"\n\nCancellation reason: {reason}"

        if self.calendar_client:
            try:
                await self.calendar_client.delete_event(event_id=followup_id)
            except Exception as e:
                logger.warning(f"Failed to delete calendar event: {e}")

        logger.info(f"Cancelled follow-up {followup_id}: {reason}")

        return followup

    async def get_followup(self, followup_id: str) -> Optional[ScheduledFollowup]:
        """Get follow-up by ID."""
        return self._scheduled.get(followup_id)

    async def get_upcoming_followups(
        self,
        assigned_to: Optional[str] = None,
        days: int = 7,
    ) -> List[ScheduledFollowup]:
        """
        Get upcoming follow-ups.

        Args:
            assigned_to: Filter by assigned user
            days: Number of days to look ahead

        Returns:
            List of upcoming ScheduledFollowups
        """
        now = datetime.utcnow()
        cutoff = now + timedelta(days=days)

        upcoming = []
        for followup in self._scheduled.values():
            if followup.status not in [AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED]:
                if followup.scheduled_date and now <= followup.scheduled_date <= cutoff:
                    if assigned_to is None or followup.assigned_to == assigned_to:
                        upcoming.append(followup)

        # Sort by scheduled date
        upcoming.sort(key=lambda f: f.scheduled_date or datetime.max)

        return upcoming

    def _determine_priority(self, extracted_data: Dict[str, Any]) -> FollowupPriority:
        """Determine follow-up priority based on extracted data."""
        intent = extracted_data.get("intent", {})

        urgency = self._get_value(intent, "urgency")
        timeline = self._get_value(intent, "target_timeline")

        # Urgent if explicitly stated or very short timeline
        if urgency == "high":
            return FollowupPriority.URGENT

        if timeline:
            timeline_lower = str(timeline).lower()
            if any(term in timeline_lower for term in ["asap", "immediately", "this week", "urgent"]):
                return FollowupPriority.URGENT
            if any(term in timeline_lower for term in ["30 day", "month"]):
                return FollowupPriority.HIGH

        # High if has property or pre-approval
        if self._get_value(intent, "has_property_identified"):
            return FollowupPriority.HIGH
        if self._get_value(intent, "has_preapproval"):
            return FollowupPriority.HIGH

        # Low if long timeline
        if timeline and any(term in str(timeline).lower() for term in ["year", "6 month"]):
            return FollowupPriority.LOW

        return FollowupPriority.NORMAL

    async def _find_next_available_slot(
        self,
        assigned_to: Optional[str],
        priority: FollowupPriority,
        duration: int,
    ) -> datetime:
        """Find the next available time slot based on priority."""
        now = datetime.now()

        # Determine how soon to schedule based on priority
        if priority == FollowupPriority.URGENT:
            # Today or tomorrow
            search_start = now + timedelta(hours=1)
            search_days = 2
        elif priority == FollowupPriority.HIGH:
            # Within 24-48 hours
            search_start = now + timedelta(hours=4)
            search_days = 3
        elif priority == FollowupPriority.LOW:
            # Within a week
            search_start = now + timedelta(days=3)
            search_days = 10
        else:  # NORMAL
            # Within 2-3 days
            search_start = now + timedelta(days=1)
            search_days = 5

        # Get available slots
        slots = await self.get_available_slots(
            assigned_to=assigned_to,
            start_date=search_start,
            days=search_days,
            duration_minutes=duration,
        )

        # Find first available slot
        for slot in slots:
            if slot.available:
                return slot.start_time

        # Fallback: return a default time
        fallback = search_start.replace(hour=10, minute=0, second=0, microsecond=0)
        if fallback <= now:
            fallback += timedelta(days=1)

        return fallback

    async def _check_slot_availability(
        self,
        assigned_to: Optional[str],
        start: datetime,
        end: datetime,
    ) -> bool:
        """Check if a time slot is available."""
        if self.calendar_client:
            try:
                return await self.calendar_client.is_available(
                    user_id=assigned_to,
                    start=start,
                    end=end,
                )
            except Exception as e:
                logger.error(f"Error checking slot availability: {e}")

        # Check against in-memory scheduled items
        for followup in self._scheduled.values():
            if followup.status == AppointmentStatus.CANCELLED:
                continue
            if followup.assigned_to != assigned_to:
                continue
            if followup.scheduled_date:
                followup_end = followup.scheduled_date + timedelta(minutes=followup.duration_minutes)
                # Check for overlap
                if start < followup_end and end > followup.scheduled_date:
                    return False

        return True

    def _is_business_day(self, day_of_week: int) -> bool:
        """Check if a day is a business day."""
        # Monday = 0, Sunday = 6
        # Default: Monday-Friday are business days
        if day_of_week >= 5:  # Saturday or Sunday
            return self.business_hours.get(day_of_week) is not None
        return True

    def _get_business_hours(self, day_of_week: int) -> Tuple[time, time]:
        """Get business hours for a day."""
        custom = self.business_hours.get(day_of_week)
        if custom:
            return custom
        return DEFAULT_START_TIME, DEFAULT_END_TIME

    def _get_default_duration(self, appointment_type: AppointmentType) -> int:
        """Get default duration for appointment type."""
        durations = {
            AppointmentType.FOLLOWUP_CALL: 15,
            AppointmentType.CONSULTATION: 45,
            AppointmentType.APPLICATION_REVIEW: 30,
            AppointmentType.DOCUMENT_REVIEW: 20,
            AppointmentType.CLOSING_PREP: 60,
            AppointmentType.CUSTOM: 30,
        }
        return durations.get(appointment_type, 30)

    def _generate_subject(self, appointment_type: AppointmentType, borrower_name: str) -> str:
        """Generate appointment subject line."""
        subjects = {
            AppointmentType.FOLLOWUP_CALL: f"Follow-up Call with {borrower_name}",
            AppointmentType.CONSULTATION: f"Mortgage Consultation - {borrower_name}",
            AppointmentType.APPLICATION_REVIEW: f"Application Review - {borrower_name}",
            AppointmentType.DOCUMENT_REVIEW: f"Document Review - {borrower_name}",
            AppointmentType.CLOSING_PREP: f"Closing Preparation - {borrower_name}",
            AppointmentType.CUSTOM: f"Meeting with {borrower_name}",
        }
        return subjects.get(appointment_type, f"Appointment - {borrower_name}")

    def _generate_notes(
        self,
        extracted_data: Dict[str, Any],
        appointment_type: AppointmentType,
    ) -> str:
        """Generate appointment notes from extracted data."""
        intent = extracted_data.get("intent", {})
        property_info = extracted_data.get("property", {})

        notes_parts = []

        loan_purpose = self._get_value(intent, "loan_purpose")
        if loan_purpose:
            notes_parts.append(f"Loan Purpose: {loan_purpose}")

        purchase_price = self._get_value(property_info, "purchase_price")
        if purchase_price:
            notes_parts.append(f"Target Purchase Price: ${float(purchase_price):,.0f}")

        timeline = self._get_value(intent, "target_timeline")
        if timeline:
            notes_parts.append(f"Timeline: {timeline}")

        if self._get_value(intent, "has_preapproval"):
            notes_parts.append("Has pre-approval from another lender")

        if self._get_value(intent, "has_realtor"):
            realtor = self._get_value(intent, "realtor_name")
            if realtor:
                notes_parts.append(f"Working with realtor: {realtor}")
            else:
                notes_parts.append("Has a realtor")

        return "\n".join(notes_parts) if notes_parts else "Follow-up from initial call"

    def _get_preparation_items(self, appointment_type: AppointmentType) -> List[str]:
        """Get preparation items for appointment type."""
        items = {
            AppointmentType.FOLLOWUP_CALL: [
                "Review call notes and extracted data",
                "Have rate sheets ready",
                "Prepare loan scenarios",
            ],
            AppointmentType.CONSULTATION: [
                "Review borrower profile",
                "Prepare loan program comparisons",
                "Have pre-qualification ready",
                "Prepare affordability scenarios",
            ],
            AppointmentType.APPLICATION_REVIEW: [
                "Review submitted application",
                "Check for missing fields",
                "Prepare questions about discrepancies",
            ],
            AppointmentType.DOCUMENT_REVIEW: [
                "Review uploaded documents",
                "Note any missing or incomplete items",
                "Prepare list of additional items needed",
            ],
            AppointmentType.CLOSING_PREP: [
                "Review final CD",
                "Confirm wire instructions",
                "Prepare closing timeline overview",
                "Note any last-minute items",
            ],
        }
        return items.get(appointment_type, ["Review previous notes"])

    def _get_value(self, data: Dict, field: str) -> Any:
        """Get value from extraction dict."""
        if not data:
            return None

        value = data.get(field)
        if isinstance(value, dict):
            return value.get("value")
        return value


# =============================================================================
# Factory
# =============================================================================

def create_scheduling_service(
    calendar_client=None,
    business_hours: Optional[Dict] = None,
) -> SchedulingService:
    """Create scheduling service instance."""
    return SchedulingService(calendar_client, business_hours)
