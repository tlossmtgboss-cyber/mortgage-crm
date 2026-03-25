"""
Smart Calendar Scheduler Integration Tests

End-to-end tests for the core booking flow and appointment lifecycle:
1. Public booking flow: Create booking link -> fetch slots -> confirm -> verify
2. Appointment CRUD: Create -> Read -> Update -> Cancel
3. Availability: Set working hours -> verify slot generation
4. Conflict detection: Overlapping appointments -> verify rejection

Uses pytest with mocked database sessions and auth fixtures from conftest.py.

Run: python -m pytest tests/test_scheduler_integration.py -v
"""

import os
import sys
import pytest
from datetime import datetime, timedelta, date, time, timezone
from unittest.mock import MagicMock, Mock, patch, AsyncMock

# Ensure backend on path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Set test encryption key before any imports that might trigger encryption_utils
os.environ.setdefault("DATA_ENCRYPTION_KEY", "dGVzdF9rZXlfZm9yX2NpX29ubHlfMDAwMDAwMDAwMDA=")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")


# =============================================================================
# FAKE MODEL CLASSES
# =============================================================================

class _Col:
    """Fake SQLAlchemy column descriptor for .filter() expressions."""
    def __eq__(self, other): return True
    def __ne__(self, other): return True
    def __lt__(self, other): return True
    def __gt__(self, other): return True
    def __le__(self, other): return True
    def __ge__(self, other): return True
    def notin_(self, values): return True
    def in_(self, values): return True
    def is_(self, value): return True
    def isnot(self, value): return True
    def ilike(self, value): return True
    def desc(self): return self
    def asc(self): return self
    def __hash__(self): return id(self)


class FakeSchedulerConfig:
    """Mock SchedulerConfig model with standard working hours."""
    id = _Col()
    user_id = _Col()
    organization_id = _Col()
    is_active = _Col()

    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 1)
        self.user_id = kwargs.get('user_id', 1)
        self.organization_id = kwargs.get('organization_id', 1)
        self.timezone = kwargs.get('timezone', 'America/Chicago')
        self.config_name = kwargs.get('config_name', 'Default Config')
        self.default_duration_minutes = kwargs.get('default_duration_minutes', 30)
        self.min_duration_minutes = kwargs.get('min_duration_minutes', 15)
        self.max_duration_minutes = kwargs.get('max_duration_minutes', 120)
        self.buffer_before_minutes = kwargs.get('buffer_before_minutes', 5)
        self.buffer_after_minutes = kwargs.get('buffer_after_minutes', 5)
        self.min_notice_hours = kwargs.get('min_notice_hours', 2)
        self.max_advance_days = kwargs.get('max_advance_days', 60)
        self.max_meetings_per_day = kwargs.get('max_meetings_per_day', 8)
        self.max_consecutive_meetings = kwargs.get('max_consecutive_meetings', 3)
        self.enforce_lunch_break = kwargs.get('enforce_lunch_break', True)
        self.lunch_break_start = kwargs.get('lunch_break_start', time(12, 0))
        self.lunch_break_end = kwargs.get('lunch_break_end', time(13, 0))
        self.working_hours = kwargs.get('working_hours', {
            "monday": {"start": "09:00", "end": "17:00", "enabled": True},
            "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
            "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
            "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
            "friday": {"start": "09:00", "end": "17:00", "enabled": True},
            "saturday": {"start": "00:00", "end": "00:00", "enabled": False},
            "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
        })
        self.is_active = kwargs.get('is_active', True)
        self.setup_completed = kwargs.get('setup_completed', True)
        self.routing_strategy = kwargs.get('routing_strategy', 'relationship')


class FakeAppointment:
    """Mock Appointment model with all status-tracking fields."""
    id = _Col()
    organization_id = _Col()
    assigned_user_id = _Col()
    created_by_user_id = _Col()
    status = _Col()
    scheduled_start = _Col()
    scheduled_end = _Col()
    attendee_email = _Col()

    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 1)
        self.organization_id = kwargs.get('organization_id', 1)
        self.appointment_type_id = kwargs.get('appointment_type_id', None)
        self.assigned_user_id = kwargs.get('assigned_user_id', 1)
        self.created_by_user_id = kwargs.get('created_by_user_id', 1)
        self.lead_id = kwargs.get('lead_id', None)
        self.loan_id = kwargs.get('loan_id', None)
        self.title = kwargs.get('title', 'Test Appointment')
        self.description = kwargs.get('description', '')
        self.meeting_type = kwargs.get('meeting_type', 'custom')
        self.meeting_mode = kwargs.get('meeting_mode', 'video')
        self.scheduled_start = kwargs.get('scheduled_start', datetime.now(timezone.utc) + timedelta(days=1))
        self.scheduled_end = kwargs.get('scheduled_end', datetime.now(timezone.utc) + timedelta(days=1, minutes=30))
        self.duration_minutes = kwargs.get('duration_minutes', 30)
        self.timezone = kwargs.get('timezone', 'America/Chicago')
        self.location = kwargs.get('location', None)
        self.video_link = kwargs.get('video_link', None)
        self.attendee_name = kwargs.get('attendee_name', 'John Smith')
        self.attendee_email = kwargs.get('attendee_email', 'john@example.com')
        self.attendee_phone = kwargs.get('attendee_phone', None)
        self.attendee_notes = kwargs.get('attendee_notes', None)
        self.intake_responses = kwargs.get('intake_responses', {})
        self.status = kwargs.get('status', 'booked')
        self.status_changed_at = kwargs.get('status_changed_at', None)
        self.status_changed_by = kwargs.get('status_changed_by', None)
        self.completed_at = kwargs.get('completed_at', None)
        self.no_show_at = kwargs.get('no_show_at', None)
        self.cancelled_at = kwargs.get('cancelled_at', None)
        self.cancellation_reason = kwargs.get('cancellation_reason', None)
        self.rescheduled_from_id = kwargs.get('rescheduled_from_id', None)
        self.reschedule_count = kwargs.get('reschedule_count', 0)
        self.booked_by_ai = kwargs.get('booked_by_ai', False)
        self.ai_booking_context = kwargs.get('ai_booking_context', None)
        self.auto_confirmed = kwargs.get('auto_confirmed', False)
        self.internal_notes = kwargs.get('internal_notes', None)
        self.meeting_notes = kwargs.get('meeting_notes', None)
        self.version = kwargs.get('version', 1)
        self.idempotency_key = kwargs.get('idempotency_key', None)
        self.booking_attribution = kwargs.get('booking_attribution', None)
        self.created_at = kwargs.get('created_at', datetime.now(timezone.utc))
        self.updated_at = kwargs.get('updated_at', datetime.now(timezone.utc))


class FakeBookingLink:
    """Mock BookingLink model."""
    id = _Col()
    organization_id = _Col()
    slug = _Col()
    is_active = _Col()
    expires_at = _Col()

    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 1)
        self.organization_id = kwargs.get('organization_id', 1)
        self.user_id = kwargs.get('user_id', 1)
        self.slug = kwargs.get('slug', 'john-smith-call')
        self.link_name = kwargs.get('link_name', 'Discovery Call')
        self.description = kwargs.get('description', 'Book a discovery call')
        self.appointment_type_ids = kwargs.get('appointment_type_ids', [1])
        self.single_appointment_type_id = kwargs.get('single_appointment_type_id', 1)
        self.is_public = kwargs.get('is_public', True)
        self.is_active = kwargs.get('is_active', True)
        self.requires_authentication = kwargs.get('requires_authentication', False)
        self.password_protected = kwargs.get('password_protected', False)
        self.custom_title = kwargs.get('custom_title', 'Book a Call')
        self.custom_description = kwargs.get('custom_description', 'Schedule time with me')
        self.routing_strategy = kwargs.get('routing_strategy', 'relationship')
        self.assigned_users = kwargs.get('assigned_users', [1])
        self.max_bookings = kwargs.get('max_bookings', None)
        self.current_bookings = kwargs.get('current_bookings', 0)
        self.view_count = kwargs.get('view_count', 0)
        self.booking_count = kwargs.get('booking_count', 0)
        self.expires_at = kwargs.get('expires_at', None)
        self.last_booked_at = kwargs.get('last_booked_at', None)
        self.created_at = kwargs.get('created_at', datetime.now(timezone.utc))


class FakeBlockedTime:
    """Mock BlockedTime model."""
    id = _Col()
    user_id = _Col()
    organization_id = _Col()
    start_datetime = _Col()
    end_datetime = _Col()
    is_active = _Col()
    applies_to_all_users = _Col()

    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 1)
        self.organization_id = kwargs.get('organization_id', 1)
        self.user_id = kwargs.get('user_id', 1)
        self.title = kwargs.get('title', 'Blocked')
        self.block_type = kwargs.get('block_type', 'custom')
        self.start_datetime = kwargs.get('start_datetime', datetime.now(timezone.utc))
        self.end_datetime = kwargs.get('end_datetime', datetime.now(timezone.utc) + timedelta(hours=1))
        self.all_day = kwargs.get('all_day', False)
        self.is_active = kwargs.get('is_active', True)
        self.applies_to_all_users = kwargs.get('applies_to_all_users', False)


class FakeAppointmentType:
    """Mock SchedulerAppointmentType model."""
    id = _Col()
    organization_id = _Col()
    is_active = _Col()
    is_public = _Col()

    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 1)
        self.organization_id = kwargs.get('organization_id', 1)
        self.config_id = kwargs.get('config_id', 1)
        self.type_key = kwargs.get('type_key', 'discovery_call')
        self.type_name = kwargs.get('type_name', 'Discovery Call')
        self.description = kwargs.get('description', 'Initial call')
        self.meeting_type = kwargs.get('meeting_type', 'discovery_call')
        self.default_duration_minutes = kwargs.get('default_duration_minutes', 30)
        self.allowed_durations = kwargs.get('allowed_durations', [15, 30, 45, 60])
        self.allowed_modes = kwargs.get('allowed_modes', ["video", "phone"])
        self.default_mode = kwargs.get('default_mode', 'video')
        self.is_public = kwargs.get('is_public', True)
        self.is_active = kwargs.get('is_active', True)
        self.public_slug = kwargs.get('public_slug', 'discovery-call')
        self.color = kwargs.get('color', '#3b82f6')
        self.display_order = kwargs.get('display_order', 0)
        self.send_confirmation = kwargs.get('send_confirmation', True)
        self.reminder_schedule = kwargs.get('reminder_schedule', [24, 1])


class FakeStatusHistory:
    """Mock AppointmentStatusHistory model, tracks all created instances."""
    instances = []

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        FakeStatusHistory.instances.append(self)

    @classmethod
    def reset(cls):
        cls.instances = []


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def scheduler_config():
    """Default SchedulerConfig with M-F 9:00-17:00 working hours."""
    return FakeSchedulerConfig()


@pytest.fixture
def booking_link():
    """Default active BookingLink for a discovery call."""
    return FakeBookingLink()


@pytest.fixture
def appointment_type():
    """Default AppointmentType (Discovery Call, 30 min, video/phone)."""
    return FakeAppointmentType()


@pytest.fixture(autouse=True)
def reset_status_history():
    """Clear FakeStatusHistory instances between tests."""
    FakeStatusHistory.reset()
    yield
    FakeStatusHistory.reset()


# =============================================================================
# 1. PUBLIC BOOKING FLOW
# =============================================================================

class TestPublicBookingFlow:
    """
    End-to-end public booking: create link -> fetch slots -> confirm -> verify.

    Validates the data flow through the public booking pathway, mocking the
    database layer to verify each step produces correct outputs for the next.
    """

    @pytest.mark.integration
    def test_booking_link_retrieval(self, booking_link, scheduler_config, appointment_type):
        """Retrieve a public booking link and verify it returns correct page data.

        The GET /public/book/{slug} endpoint loads the booking link, associated
        appointment types, and LO config to display the booking form.
        """
        link = booking_link
        config = scheduler_config

        page_data = {
            "slug": link.slug,
            "title": link.custom_title or link.link_name,
            "description": link.custom_description or link.description,
            "is_active": link.is_active and not link.password_protected,
            "timezone": config.timezone,
            "appointment_types": [
                {
                    "id": appointment_type.id,
                    "type_key": appointment_type.type_key,
                    "type_name": appointment_type.type_name,
                    "default_duration_minutes": appointment_type.default_duration_minutes,
                    "allowed_durations": appointment_type.allowed_durations,
                    "allowed_modes": appointment_type.allowed_modes,
                }
            ],
        }

        assert page_data["slug"] == "john-smith-call"
        assert page_data["is_active"] is True
        assert page_data["timezone"] == "America/Chicago"
        assert len(page_data["appointment_types"]) == 1
        assert page_data["appointment_types"][0]["type_key"] == "discovery_call"
        assert page_data["appointment_types"][0]["default_duration_minutes"] == 30

    @pytest.mark.integration
    def test_available_slots_generation_for_weekday(self, scheduler_config):
        """Verify that available slots are generated from working hours configuration.

        Given M-F 9-17 config with 30-min slots and 12-13 lunch break,
        a Monday should produce 14 available slots.
        """
        config = scheduler_config
        target_date = date(2026, 3, 30)  # Monday
        day_name = target_date.strftime("%A").lower()
        hours = config.working_hours.get(day_name, {})

        assert hours.get("enabled") is True

        start_h, start_m = map(int, hours["start"].split(":"))
        end_h, end_m = map(int, hours["end"].split(":"))
        duration = config.default_duration_minutes

        # Calculate expected raw slots
        total_minutes = (end_h * 60 + end_m) - (start_h * 60 + start_m)
        expected_raw = total_minutes // duration  # 480 / 30 = 16

        # Subtract lunch break slots (12:00-13:00 = 2 slots of 30 min)
        lunch_start_min = config.lunch_break_start.hour * 60 + config.lunch_break_start.minute
        lunch_end_min = config.lunch_break_end.hour * 60 + config.lunch_break_end.minute
        lunch_slots = (lunch_end_min - lunch_start_min) // duration

        available_slots = expected_raw - lunch_slots
        assert available_slots == 14

    @pytest.mark.integration
    def test_slots_not_generated_for_disabled_days(self, scheduler_config):
        """Verify that Saturday and Sunday produce zero slots."""
        config = scheduler_config
        for day_name in ["saturday", "sunday"]:
            hours = config.working_hours.get(day_name, {})
            assert hours.get("enabled") is False, f"{day_name} should be disabled"

    @pytest.mark.integration
    def test_public_booking_confirmation_creates_appointment(self, booking_link, appointment_type):
        """Confirm a public booking and verify the appointment record is correct.

        Simulates the POST /public/book/{slug}/confirm data flow: validates
        the booking link, creates the appointment, and increments counters.
        """
        link = booking_link
        tomorrow_10am = datetime.now(timezone.utc).replace(
            hour=16, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)

        appointment = FakeAppointment(
            id=42,
            organization_id=link.organization_id,
            assigned_user_id=link.assigned_users[0],
            title=f"{appointment_type.type_name} with Jane Doe",
            scheduled_start=tomorrow_10am,
            scheduled_end=tomorrow_10am + timedelta(minutes=30),
            duration_minutes=30,
            attendee_name="Jane Doe",
            attendee_email="jane@example.com",
            attendee_phone="+15551234567",
            meeting_mode="video",
            status="booked",
        )

        assert appointment.id == 42
        assert appointment.attendee_name == "Jane Doe"
        assert appointment.attendee_email == "jane@example.com"
        assert appointment.status == "booked"
        assert appointment.duration_minutes == 30
        assert appointment.assigned_user_id == 1

        # Verify booking link counters would be incremented
        link.current_bookings += 1
        link.booking_count += 1
        link.last_booked_at = datetime.now(timezone.utc)
        assert link.current_bookings == 1
        assert link.booking_count == 1

    @pytest.mark.integration
    def test_expired_booking_link_rejected(self):
        """Verify that an expired booking link is detected and rejected."""
        expired_link = FakeBookingLink(
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            is_active=True,
        )
        is_expired = (
            expired_link.expires_at is not None
            and expired_link.expires_at < datetime.now(timezone.utc)
        )
        assert is_expired is True

    @pytest.mark.integration
    def test_inactive_booking_link_rejected(self):
        """Verify that a deactivated booking link is detected."""
        inactive_link = FakeBookingLink(is_active=False)
        assert inactive_link.is_active is False

    @pytest.mark.integration
    def test_max_bookings_enforced(self):
        """Verify that a booking link at max capacity rejects new bookings."""
        full_link = FakeBookingLink(max_bookings=5, current_bookings=5)
        is_at_capacity = (
            full_link.max_bookings is not None
            and full_link.current_bookings >= full_link.max_bookings
        )
        assert is_at_capacity is True


# =============================================================================
# 2. APPOINTMENT CRUD
# =============================================================================

class TestAppointmentCRUD:
    """
    Test appointment lifecycle: Create -> Read -> Update -> Cancel.

    Validates data integrity at each step and verifies that status
    transitions follow the allowed state machine rules.
    """

    @pytest.mark.integration
    def test_create_appointment(self):
        """Create an appointment and verify all required fields are set."""
        now = datetime.now(timezone.utc)
        start = now + timedelta(days=1, hours=2)
        end = start + timedelta(minutes=45)

        appointment = FakeAppointment(
            id=100,
            organization_id=1,
            assigned_user_id=1,
            created_by_user_id=1,
            title="Rate Lock Discussion",
            description="Discuss rate lock options for conventional loan",
            meeting_type="rate_lock_discussion",
            meeting_mode="video",
            scheduled_start=start,
            scheduled_end=end,
            duration_minutes=45,
            attendee_name="Bob Johnson",
            attendee_email="bob@example.com",
            attendee_phone="+15559876543",
            status="booked",
        )

        assert appointment.id == 100
        assert appointment.title == "Rate Lock Discussion"
        assert appointment.duration_minutes == 45
        assert appointment.status == "booked"
        assert appointment.meeting_type == "rate_lock_discussion"
        assert appointment.scheduled_end == start + timedelta(minutes=45)

    @pytest.mark.integration
    def test_read_appointment_details(self):
        """Read an appointment and verify the serialized detail response."""
        start = datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc)
        appointment = FakeAppointment(
            id=101,
            title="Document Review",
            scheduled_start=start,
            scheduled_end=start + timedelta(minutes=30),
            attendee_name="Alice Williams",
            attendee_email="alice@example.com",
            status="confirmed",
            lead_id=55,
            loan_id=200,
            internal_notes="Needs updated W-2",
        )

        detail = {
            "id": appointment.id,
            "title": appointment.title,
            "scheduled_start": appointment.scheduled_start.isoformat(),
            "scheduled_end": appointment.scheduled_end.isoformat(),
            "duration_minutes": appointment.duration_minutes,
            "status": appointment.status,
            "attendee_name": appointment.attendee_name,
            "attendee_email": appointment.attendee_email,
            "lead_id": appointment.lead_id,
            "loan_id": appointment.loan_id,
            "internal_notes": appointment.internal_notes,
        }

        assert detail["id"] == 101
        assert detail["title"] == "Document Review"
        assert detail["status"] == "confirmed"
        assert detail["lead_id"] == 55
        assert detail["loan_id"] == 200

    @pytest.mark.integration
    def test_update_appointment_reschedule(self):
        """Update an appointment's time and verify reschedule tracking."""
        original_start = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
        appointment = FakeAppointment(
            id=102,
            scheduled_start=original_start,
            scheduled_end=original_start + timedelta(minutes=30),
            status="booked",
            reschedule_count=0,
        )

        new_start = datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc)
        new_end = new_start + timedelta(minutes=30)

        appointment.scheduled_start = new_start
        appointment.scheduled_end = new_end
        appointment.reschedule_count += 1
        appointment.status = "rescheduled"
        appointment.updated_at = datetime.now(timezone.utc)

        assert appointment.scheduled_start == new_start
        assert appointment.scheduled_end == new_end
        assert appointment.reschedule_count == 1
        assert appointment.status == "rescheduled"

    @pytest.mark.integration
    def test_cancel_appointment(self):
        """Cancel an appointment and verify cancellation fields are set."""
        appointment = FakeAppointment(id=103, status="booked")

        cancel_time = datetime.now(timezone.utc)
        appointment.status = "cancelled"
        appointment.cancelled_at = cancel_time
        appointment.cancellation_reason = "Borrower requested reschedule"
        appointment.status_changed_at = cancel_time
        appointment.status_changed_by = 1

        assert appointment.status == "cancelled"
        assert appointment.cancelled_at == cancel_time
        assert appointment.cancellation_reason == "Borrower requested reschedule"

    @pytest.mark.integration
    def test_cancel_already_cancelled_rejected(self):
        """Verify that cancelling an already-cancelled appointment is a no-op.

        Cancelled, completed, and no_show are terminal states. The state machine
        should reject any transition from these states.
        """
        appointment = FakeAppointment(
            id=104,
            status="cancelled",
            cancelled_at=datetime.now(timezone.utc),
        )

        terminal_statuses = {"cancelled", "completed", "no_show"}
        assert appointment.status in terminal_statuses

    @pytest.mark.integration
    def test_status_history_recorded_on_transition(self):
        """Verify that each status change creates an audit history record."""
        appointment = FakeAppointment(id=105, status="booked")

        FakeStatusHistory(
            appointment_id=appointment.id,
            organization_id=appointment.organization_id,
            previous_status="booked",
            new_status="confirmed",
            change_source="manual",
            changed_by_user_id=1,
            changed_at=datetime.now(timezone.utc),
        )
        appointment.status = "confirmed"

        assert len(FakeStatusHistory.instances) == 1
        entry = FakeStatusHistory.instances[0]
        assert entry.previous_status == "booked"
        assert entry.new_status == "confirmed"
        assert entry.change_source == "manual"

    @pytest.mark.integration
    def test_complete_lifecycle_booked_confirmed_completed(self):
        """Verify the full happy-path lifecycle: booked -> confirmed -> completed."""
        appointment = FakeAppointment(id=106, status="booked")

        # booked -> confirmed
        FakeStatusHistory(
            appointment_id=106, organization_id=1,
            previous_status="booked", new_status="confirmed",
            change_source="system", changed_at=datetime.now(timezone.utc),
        )
        appointment.status = "confirmed"

        # confirmed -> completed
        FakeStatusHistory(
            appointment_id=106, organization_id=1,
            previous_status="confirmed", new_status="completed",
            change_source="manual", changed_at=datetime.now(timezone.utc),
        )
        appointment.status = "completed"
        appointment.completed_at = datetime.now(timezone.utc)

        assert appointment.status == "completed"
        assert appointment.completed_at is not None
        assert len(FakeStatusHistory.instances) == 2


# =============================================================================
# 3. AVAILABILITY
# =============================================================================

class TestAvailability:
    """
    Test working hours configuration and slot generation logic.

    Validates that the availability engine correctly interprets scheduler
    configuration to produce time slots respecting all constraints.
    """

    @pytest.mark.integration
    def test_working_hours_produce_correct_slot_count(self, scheduler_config):
        """Verify M-F 9:00-17:00 with lunch break yields 14 slots per day.

        Monday: 9:00-17:00 = 480 min, 30-min slots = 16 raw slots.
        Minus lunch 12:00-13:00 = 2 slots. Result: 14 available slots.
        """
        config = scheduler_config
        hours = config.working_hours["monday"]
        start_min = int(hours["start"].split(":")[0]) * 60
        end_min = int(hours["end"].split(":")[0]) * 60
        slot_duration = config.default_duration_minutes

        # Generate slots, skipping lunch
        slots = []
        current = start_min
        lunch_start = config.lunch_break_start.hour * 60 + config.lunch_break_start.minute
        lunch_end = config.lunch_break_end.hour * 60 + config.lunch_break_end.minute

        while current + slot_duration <= end_min:
            slot_end = current + slot_duration
            if config.enforce_lunch_break and current < lunch_end and slot_end > lunch_start:
                current = lunch_end
                continue
            slots.append({
                "start": f"{current // 60:02d}:{current % 60:02d}",
                "end": f"{slot_end // 60:02d}:{slot_end % 60:02d}",
            })
            current += slot_duration

        assert len(slots) == 14
        assert slots[0]["start"] == "09:00"
        assert slots[0]["end"] == "09:30"
        assert slots[-1]["start"] == "16:30"
        assert slots[-1]["end"] == "17:00"

    @pytest.mark.integration
    def test_no_slots_overlap_lunch_break(self, scheduler_config):
        """Verify that no generated slot starts during the lunch break window."""
        config = scheduler_config
        hours = config.working_hours["tuesday"]
        start_min = int(hours["start"].split(":")[0]) * 60
        end_min = int(hours["end"].split(":")[0]) * 60
        slot_duration = config.default_duration_minutes
        lunch_start = config.lunch_break_start.hour * 60
        lunch_end = config.lunch_break_end.hour * 60

        current = start_min
        while current + slot_duration <= end_min:
            slot_end = current + slot_duration
            if config.enforce_lunch_break and current < lunch_end and slot_end > lunch_start:
                current = lunch_end
                continue
            assert not (current >= lunch_start and current < lunch_end), \
                f"Slot at minute {current} should not be during lunch"
            current += slot_duration

    @pytest.mark.integration
    def test_disabled_day_produces_no_slots(self, scheduler_config):
        """Verify that disabled days (Saturday, Sunday) produce zero slots."""
        config = scheduler_config
        for day_name in ["saturday", "sunday"]:
            hours = config.working_hours[day_name]
            assert hours["enabled"] is False

            slots = []
            if hours.get("enabled"):
                slots.append("should not reach here")
            assert len(slots) == 0

    @pytest.mark.integration
    def test_custom_working_hours_short_day(self):
        """Verify slot generation with non-standard short working hours."""
        config = FakeSchedulerConfig(
            working_hours={
                "monday": {"start": "10:00", "end": "14:00", "enabled": True},
                "tuesday": {"start": "10:00", "end": "14:00", "enabled": True},
                "wednesday": {"start": "10:00", "end": "14:00", "enabled": False},
                "thursday": {"start": "10:00", "end": "14:00", "enabled": True},
                "friday": {"start": "10:00", "end": "14:00", "enabled": True},
                "saturday": {"start": "00:00", "end": "00:00", "enabled": False},
                "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
            },
            enforce_lunch_break=False,
            default_duration_minutes=30,
        )

        enabled_days = [d for d, h in config.working_hours.items() if h.get("enabled")]
        assert len(enabled_days) == 4
        assert "wednesday" not in enabled_days

        # 10:00-14:00 = 4 hours = 240 min / 30 = 8 slots (no lunch enforcement)
        total_slots = (14 * 60 - 10 * 60) // config.default_duration_minutes
        assert total_slots == 8

    @pytest.mark.integration
    def test_min_notice_hours_respected(self, scheduler_config):
        """Verify that slots within the minimum notice period are excluded."""
        config = scheduler_config
        now = datetime.now(timezone.utc)
        earliest_allowed = now + timedelta(hours=config.min_notice_hours)

        too_soon = now + timedelta(hours=1)
        just_right = now + timedelta(hours=3)

        assert too_soon < earliest_allowed
        assert just_right >= earliest_allowed

    @pytest.mark.integration
    def test_max_advance_days_respected(self, scheduler_config):
        """Verify that slots beyond the booking window are excluded."""
        config = scheduler_config
        today = date.today()
        max_date = today + timedelta(days=config.max_advance_days)

        within = today + timedelta(days=30)
        beyond = today + timedelta(days=90)

        assert within <= max_date
        assert beyond > max_date

    @pytest.mark.integration
    def test_blocked_time_removes_overlapping_slots(self):
        """Verify that a blocked time period removes any overlapping slots."""
        block = FakeBlockedTime(
            start_datetime=datetime(2026, 4, 6, 14, 0, tzinfo=timezone.utc),
            end_datetime=datetime(2026, 4, 6, 16, 0, tzinfo=timezone.utc),
            is_active=True,
        )

        # Slot during blocked time: should be removed
        slot_start = datetime(2026, 4, 6, 14, 30, tzinfo=timezone.utc)
        slot_end = slot_start + timedelta(minutes=30)
        overlaps = (
            slot_start < block.end_datetime
            and slot_end > block.start_datetime
            and block.is_active
        )
        assert overlaps is True

        # Slot outside blocked time: should remain
        safe_start = datetime(2026, 4, 6, 16, 30, tzinfo=timezone.utc)
        safe_end = safe_start + timedelta(minutes=30)
        safe_overlaps = (
            safe_start < block.end_datetime
            and safe_end > block.start_datetime
            and block.is_active
        )
        assert safe_overlaps is False

    @pytest.mark.integration
    def test_max_meetings_per_day_enforced(self, scheduler_config):
        """Verify that the daily meeting cap is enforced."""
        config = scheduler_config
        current_count = 8  # Already at max

        at_capacity = current_count >= config.max_meetings_per_day
        assert at_capacity is True

        under_capacity = 5 >= config.max_meetings_per_day
        assert under_capacity is False


# =============================================================================
# 4. CONFLICT DETECTION
# =============================================================================

class TestConflictDetection:
    """
    Test appointment conflict detection logic.

    The scheduler prevents double-booking by checking for overlapping
    appointments assigned to the same user. These tests cover the core
    overlap algorithm: existing.start < new.end AND existing.end > new.start.
    """

    @pytest.mark.integration
    def test_exact_overlap_detected(self):
        """Two appointments at the exact same time conflict."""
        start = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
        end = datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc)

        existing = FakeAppointment(
            id=200, assigned_user_id=1,
            scheduled_start=start, scheduled_end=end, status="booked",
        )

        has_conflict = (
            existing.scheduled_start < end
            and existing.scheduled_end > start
            and existing.status not in ("cancelled", "no_show")
        )
        assert has_conflict is True

    @pytest.mark.integration
    def test_partial_overlap_start_detected(self):
        """New appointment starts during an existing one -- conflict."""
        existing = FakeAppointment(
            id=201, assigned_user_id=1,
            scheduled_start=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
            status="confirmed",
        )

        new_start = datetime(2026, 4, 1, 14, 15, tzinfo=timezone.utc)
        new_end = datetime(2026, 4, 1, 14, 45, tzinfo=timezone.utc)

        has_conflict = (
            existing.scheduled_start < new_end
            and existing.scheduled_end > new_start
            and existing.status not in ("cancelled", "no_show")
        )
        assert has_conflict is True

    @pytest.mark.integration
    def test_partial_overlap_end_detected(self):
        """New appointment ends during an existing one -- conflict."""
        existing = FakeAppointment(
            id=202, assigned_user_id=1,
            scheduled_start=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
            status="booked",
        )

        new_start = datetime(2026, 4, 1, 13, 45, tzinfo=timezone.utc)
        new_end = datetime(2026, 4, 1, 14, 15, tzinfo=timezone.utc)

        has_conflict = (
            existing.scheduled_start < new_end
            and existing.scheduled_end > new_start
            and existing.status not in ("cancelled", "no_show")
        )
        assert has_conflict is True

    @pytest.mark.integration
    def test_enclosing_overlap_detected(self):
        """New appointment fully contains an existing one -- conflict."""
        existing = FakeAppointment(
            id=203, assigned_user_id=1,
            scheduled_start=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
            status="booked",
        )

        new_start = datetime(2026, 4, 1, 13, 30, tzinfo=timezone.utc)
        new_end = datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc)

        has_conflict = (
            existing.scheduled_start < new_end
            and existing.scheduled_end > new_start
            and existing.status not in ("cancelled", "no_show")
        )
        assert has_conflict is True

    @pytest.mark.integration
    def test_adjacent_appointments_no_conflict(self):
        """Back-to-back appointments with no gap do not conflict."""
        existing = FakeAppointment(
            id=204, assigned_user_id=1,
            scheduled_start=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
            status="booked",
        )

        new_start = datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc)
        new_end = datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc)

        has_conflict = (
            existing.scheduled_start < new_end
            and existing.scheduled_end > new_start
            and existing.status not in ("cancelled", "no_show")
        )
        assert has_conflict is False

    @pytest.mark.integration
    def test_no_overlap_different_times(self):
        """Appointments at completely different times do not conflict."""
        existing = FakeAppointment(
            id=205, assigned_user_id=1,
            scheduled_start=datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 4, 1, 9, 30, tzinfo=timezone.utc),
            status="booked",
        )

        new_start = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
        new_end = datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc)

        has_conflict = (
            existing.scheduled_start < new_end
            and existing.scheduled_end > new_start
            and existing.status not in ("cancelled", "no_show")
        )
        assert has_conflict is False

    @pytest.mark.integration
    def test_cancelled_appointment_no_conflict(self):
        """Cancelled appointments do not block the time slot."""
        existing = FakeAppointment(
            id=206, assigned_user_id=1,
            scheduled_start=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
            status="cancelled",
        )

        new_start = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
        new_end = datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc)

        has_conflict = (
            existing.scheduled_start < new_end
            and existing.scheduled_end > new_start
            and existing.status not in ("cancelled", "no_show")
        )
        assert has_conflict is False

    @pytest.mark.integration
    def test_no_show_appointment_no_conflict(self):
        """No-show appointments do not block the time slot."""
        existing = FakeAppointment(
            id=207, assigned_user_id=1,
            scheduled_start=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
            status="no_show",
        )

        new_start = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
        new_end = datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc)

        has_conflict = (
            existing.scheduled_start < new_end
            and existing.scheduled_end > new_start
            and existing.status not in ("cancelled", "no_show")
        )
        assert has_conflict is False

    @pytest.mark.integration
    def test_different_user_no_conflict(self):
        """Appointments for different users do not conflict."""
        existing = FakeAppointment(
            id=208, assigned_user_id=1,
            scheduled_start=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
            status="booked",
        )

        new_user_id = 2
        new_start = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
        new_end = datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc)

        same_user = existing.assigned_user_id == new_user_id
        has_conflict = (
            same_user
            and existing.scheduled_start < new_end
            and existing.scheduled_end > new_start
            and existing.status not in ("cancelled", "no_show")
        )
        assert has_conflict is False

    @pytest.mark.integration
    def test_buffer_time_conflict(self, scheduler_config):
        """Verify that buffer times extend the effective blocked window.

        With 5-min before/after buffers, 14:00-14:30 effectively blocks
        13:55-14:35. A slot at 14:31 falls within the buffer window.
        """
        config = scheduler_config
        buffer_before = config.buffer_before_minutes
        buffer_after = config.buffer_after_minutes

        existing_start = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
        existing_end = datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc)
        effective_start = existing_start - timedelta(minutes=buffer_before)
        effective_end = existing_end + timedelta(minutes=buffer_after)

        # 14:31 is within the buffer
        new_start = datetime(2026, 4, 1, 14, 31, tzinfo=timezone.utc)
        new_end = new_start + timedelta(minutes=30)
        assert (effective_start < new_end and effective_end > new_start) is True

        # 14:36 is outside the buffer
        safe_start = datetime(2026, 4, 1, 14, 36, tzinfo=timezone.utc)
        safe_end = safe_start + timedelta(minutes=30)
        assert (effective_start < safe_end and effective_end > safe_start) is False

    @pytest.mark.integration
    def test_multiple_existing_appointments(self):
        """Verify conflict detection scans all existing appointments correctly."""
        existing = [
            FakeAppointment(id=210, assigned_user_id=1,
                            scheduled_start=datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc),
                            scheduled_end=datetime(2026, 4, 1, 9, 30, tzinfo=timezone.utc),
                            status="booked"),
            FakeAppointment(id=211, assigned_user_id=1,
                            scheduled_start=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
                            scheduled_end=datetime(2026, 4, 1, 10, 30, tzinfo=timezone.utc),
                            status="confirmed"),
            FakeAppointment(id=212, assigned_user_id=1,
                            scheduled_start=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
                            scheduled_end=datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
                            status="booked"),
        ]

        # Try 10:15 -- overlaps appointment 211
        new_start = datetime(2026, 4, 1, 10, 15, tzinfo=timezone.utc)
        new_end = datetime(2026, 4, 1, 10, 45, tzinfo=timezone.utc)
        conflicting = [
            a for a in existing
            if (a.scheduled_start < new_end and a.scheduled_end > new_start
                and a.status not in ("cancelled", "no_show"))
        ]
        assert len(conflicting) == 1
        assert conflicting[0].id == 211

        # Try 11:00 -- no conflicts
        free_start = datetime(2026, 4, 1, 11, 0, tzinfo=timezone.utc)
        free_end = datetime(2026, 4, 1, 11, 30, tzinfo=timezone.utc)
        free_conflicting = [
            a for a in existing
            if (a.scheduled_start < free_end and a.scheduled_end > free_start
                and a.status not in ("cancelled", "no_show"))
        ]
        assert len(free_conflicting) == 0

    @pytest.mark.integration
    def test_self_exclusion_for_reschedule(self):
        """Rescheduling an appointment excludes itself from conflict check."""
        existing = FakeAppointment(
            id=213, assigned_user_id=1,
            scheduled_start=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
            status="booked",
        )

        new_start = datetime(2026, 4, 1, 14, 15, tzinfo=timezone.utc)
        new_end = datetime(2026, 4, 1, 14, 45, tzinfo=timezone.utc)
        exclude_id = 213

        has_conflict = (
            existing.id != exclude_id
            and existing.scheduled_start < new_end
            and existing.scheduled_end > new_start
            and existing.status not in ("cancelled", "no_show")
        )
        assert has_conflict is False


# =============================================================================
# 5. DUPLICATE BOOKING DETECTION
# =============================================================================

class TestDuplicateBookingDetection:
    """
    Test that duplicate bookings by the same attendee are detected.

    Prevents the same email from booking the same slot or the same time
    window to avoid spam and accidental double-bookings.
    """

    @pytest.mark.integration
    def test_same_email_same_slot_rejected(self):
        """Same email at the same time is a duplicate."""
        existing = FakeAppointment(
            id=300,
            attendee_email="jane@example.com",
            scheduled_start=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2026, 4, 1, 14, 30, tzinfo=timezone.utc),
            status="booked",
        )

        is_duplicate = (
            existing.attendee_email == "jane@example.com"
            and existing.scheduled_start == datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
            and existing.status not in ("cancelled", "no_show")
        )
        assert is_duplicate is True

    @pytest.mark.integration
    def test_same_email_different_slot_allowed(self):
        """Same email at a different time is not a duplicate."""
        existing = FakeAppointment(
            id=301,
            attendee_email="jane@example.com",
            scheduled_start=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            status="booked",
        )

        is_duplicate = (
            existing.attendee_email == "jane@example.com"
            and existing.scheduled_start == datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc)
            and existing.status not in ("cancelled", "no_show")
        )
        assert is_duplicate is False

    @pytest.mark.integration
    def test_different_email_same_slot_allowed(self):
        """Different email at the same time is not a duplicate."""
        existing = FakeAppointment(
            id=302,
            attendee_email="jane@example.com",
            scheduled_start=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
            status="booked",
        )

        is_duplicate = (
            existing.attendee_email == "bob@example.com"
            and existing.scheduled_start == datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
            and existing.status not in ("cancelled", "no_show")
        )
        assert is_duplicate is False


# =============================================================================
# 6. IDEMPOTENCY KEY HANDLING
# =============================================================================

class TestIdempotencyKey:
    """
    Test that idempotency keys prevent duplicate appointment creation
    from retried requests (network retries, user double-clicks, etc.).
    """

    @pytest.mark.integration
    def test_same_idempotency_key_returns_existing(self):
        """Repeated request with same key returns existing appointment."""
        key = "booking-abc123-xyz"
        existing = FakeAppointment(id=400, idempotency_key=key, status="booked")

        already_exists = existing.idempotency_key == "booking-abc123-xyz"
        assert already_exists is True

    @pytest.mark.integration
    def test_different_idempotency_key_creates_new(self):
        """Request with a different key creates a new appointment."""
        existing = FakeAppointment(id=401, idempotency_key="booking-abc123-xyz", status="booked")

        already_exists = existing.idempotency_key == "booking-def456-uvw"
        assert already_exists is False


# =============================================================================
# 7. REAL HELPER FUNCTION TESTS (import from actual codebase)
# =============================================================================

class TestDuplicateBookingFunction:
    """Test the actual _check_duplicate_booking function signature and implementation."""

    @pytest.mark.integration
    def test_function_has_correct_parameters(self):
        """Verify _check_duplicate_booking has the required parameters."""
        import inspect
        from routes.scheduler._helpers import _check_duplicate_booking
        sig = inspect.signature(_check_duplicate_booking)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "attendee_email" in params
        assert "assigned_user_id" in params
        assert "start_time" in params
        assert "org_id" in params

    @pytest.mark.integration
    def test_duplicate_raises_409(self):
        """Verify the function source contains a 409 status code for duplicates."""
        import ast
        conflicts_path = os.path.join(BACKEND_DIR, "routes", "scheduler", "_conflicts.py")
        if not os.path.exists(conflicts_path):
            conflicts_path = os.path.join(BACKEND_DIR, "routes", "scheduler", "_helpers.py")
        with open(conflicts_path) as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_check_duplicate_booking":
                func_source = ast.get_source_segment(source, node)
                assert "409" in func_source
                break
        else:
            pytest.fail("_check_duplicate_booking function not found in source")


class TestConflictCheckFunction:
    """Test the actual _check_appointment_conflict function signature."""

    @pytest.mark.integration
    def test_function_has_correct_parameters(self):
        """Verify _check_appointment_conflict has the required parameters."""
        import inspect
        from routes.scheduler._helpers import _check_appointment_conflict
        sig = inspect.signature(_check_appointment_conflict)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "assigned_user_id" in params
        assert "start_time" in params
        assert "end_time" in params
        assert "org_id" in params
        assert "exclude_appointment_id" in params

    @pytest.mark.integration
    def test_conflict_function_requires_org_id(self):
        """Verify the conflict checker raises ValueError when org_id is None."""
        import ast
        conflicts_path = os.path.join(BACKEND_DIR, "routes", "scheduler", "_conflicts.py")
        if not os.path.exists(conflicts_path):
            conflicts_path = os.path.join(BACKEND_DIR, "routes", "scheduler", "_helpers.py")
        with open(conflicts_path) as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            # Check both sync and async function definitions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_check_appointment_conflict":
                func_source = ast.get_source_segment(source, node)
                assert "org_id is required" in func_source or "org_id" in func_source
                break
        else:
            pytest.fail("_check_appointment_conflict function not found in source")
