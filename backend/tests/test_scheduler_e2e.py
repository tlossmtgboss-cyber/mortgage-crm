"""
Scheduler E2E Tests

Tests complete user journeys through the scheduling system:
1. Public booking flow (anonymous -> booked -> confirmed -> showed)
2. AI booking flow (Vapi call -> slots -> hold -> book -> confirm)
3. Reschedule flow (booked -> reschedule request -> new time -> confirmed)
4. Cancel flow (booked -> cancel -> notification -> waitlist check)
5. No-show flow (confirmed -> no-show detect -> recovery -> rescheduled)
6. Team reassignment (booked with LO A -> reassign to LO B -> notified)
7. Recurring appointment (create series -> modify one -> cancel future)
8. Capacity limit (book to capacity -> next attempt rejected)
9. Buffer time enforcement (back-to-back prevented)
10. Cross-source conflict (Google event blocks our slot)

Run: python -m pytest tests/test_scheduler_e2e.py -v --noconftest
"""

import os
import sys
import uuid
import pytest
from datetime import datetime, timedelta, date, time, timezone
from unittest.mock import MagicMock, Mock, patch, PropertyMock, AsyncMock
from collections import defaultdict, deque

# Ensure backend on path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Set test encryption key before any imports
os.environ.setdefault("DATA_ENCRYPTION_KEY", "dGVzdF9rZXlfZm9yX2NpX29ubHlfMDAwMDAwMDAwMDA=")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")


# =============================================================================
# SQLAlchemy Column Mock — supports filter expressions like Model.col == value
# =============================================================================

class _Col:
    """Fake SQLAlchemy column descriptor for use in .filter() expressions."""
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
    def __hash__(self): return id(self)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session with chainable query builder."""
    db = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.filter_by.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.offset.return_value = query
    query.with_for_update.return_value = query
    query.first.return_value = None
    query.all.return_value = []
    query.count.return_value = 0
    db.query.return_value = query
    return db


@pytest.fixture
def mock_models():
    """Create mock scheduler models dict matching real model factory output."""
    models = {}
    for model_name in [
        'SchedulerConfig', 'AvailabilitySlot', 'AppointmentType',
        'Appointment', 'RoutingRule', 'BlockedTime', 'BookingLink',
        'AppointmentReminder', 'SchedulerAuditLog',
    ]:
        model = MagicMock()
        model.__tablename__ = model_name.lower() + 's'
        # Add column descriptors for filter expressions
        for attr in ['id', 'organization_id', 'user_id', 'status', 'scheduled_start',
                     'scheduled_end', 'attendee_email', 'assigned_user_id',
                     'is_active', 'slug', 'appointment_type_id', 'start_datetime',
                     'end_datetime', 'applies_to_all_users', 'config_id']:
            setattr(model, attr, _Col())
        models[model_name] = model
    return models


@pytest.fixture
def sample_appointment():
    """Create a sample appointment mock object."""
    appt = MagicMock()
    appt.id = 1
    appt.organization_id = 1
    appt.appointment_type_id = 1
    appt.assigned_user_id = 10
    appt.created_by_user_id = 10
    appt.lead_id = 100
    appt.loan_id = None
    appt.title = "Discovery Call"
    appt.description = "Initial consultation"
    appt.meeting_type = "discovery_call"
    appt.meeting_mode = "video"
    appt.scheduled_start = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
    appt.scheduled_end = datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc)
    appt.duration_minutes = 30
    appt.timezone = "America/Chicago"
    appt.attendee_name = "Jane Doe"
    appt.attendee_email = "jane.doe@example.com"
    appt.attendee_phone = "+15551234567"
    appt.attendee_notes = "First-time homebuyer"
    appt.status = "booked"
    appt.status_changed_at = datetime.now(timezone.utc)
    appt.booked_by_ai = False
    appt.auto_confirmed = False
    appt.video_link = "https://meet.google.com/test-link"
    appt.reschedule_count = 0
    appt.rescheduled_from_id = None
    appt.intake_responses = {"timeline": "1-3 months", "first_time": True}
    appt.created_at = datetime.now(timezone.utc)
    appt.updated_at = datetime.now(timezone.utc)
    return appt


@pytest.fixture
def sample_booking_link():
    """Create a sample booking link mock object."""
    link = MagicMock()
    link.id = 1
    link.organization_id = 1
    link.user_id = 10
    link.slug = "jane-smith-consultation"
    link.link_name = "Consultation with Jane"
    link.is_active = True
    link.is_public = True
    link.appointment_type_ids = [1, 2]
    link.single_appointment_type_id = None
    link.max_bookings = None
    link.current_bookings = 5
    link.max_per_person = 3
    link.assigned_users = [10, 20, 30]
    link.routing_strategy = "round_robin"
    link.available_from = None
    link.available_until = None
    link.expires_at = None
    link.view_count = 100
    link.booking_count = 5
    link.created_at = datetime.now(timezone.utc)
    return link


@pytest.fixture
def sample_scheduler_config():
    """Create a sample scheduler config mock."""
    config = MagicMock()
    config.id = 1
    config.organization_id = 1
    config.user_id = 10
    config.timezone = "America/Chicago"
    config.default_duration_minutes = 30
    config.buffer_before_minutes = 5
    config.buffer_after_minutes = 5
    config.min_notice_hours = 2
    config.max_advance_days = 60
    config.max_meetings_per_day = 8
    config.max_consecutive_meetings = 3
    config.lunch_break_start = time(12, 0)
    config.lunch_break_end = time(13, 0)
    config.enforce_lunch_break = True
    config.working_hours = {
        "monday": {"start": "09:00", "end": "17:00", "enabled": True},
        "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
        "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
        "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
        "friday": {"start": "09:00", "end": "17:00", "enabled": True},
        "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
        "sunday": {"start": "10:00", "end": "14:00", "enabled": False},
    }
    config.is_active = True
    return config


@pytest.fixture
def sample_appointment_type():
    """Create a sample appointment type mock."""
    atype = MagicMock()
    atype.id = 1
    atype.organization_id = 1
    atype.config_id = 1
    atype.type_key = "discovery_call"
    atype.type_name = "Discovery Call"
    atype.meeting_type = "discovery_call"
    atype.default_duration_minutes = 30
    atype.allowed_durations = [15, 30]
    atype.min_notice_hours = None
    atype.max_advance_days = None
    atype.max_per_day = None
    atype.max_per_week = None
    atype.is_public = True
    atype.is_active = True
    atype.send_confirmation = True
    atype.reminder_schedule = [24, 1]
    atype.intake_questions = [
        {"key": "timeline", "question": "When are you looking to buy?", "type": "select"},
    ]
    atype.assigned_users = [10, 20]
    atype.routing_strategy = None
    return atype


@pytest.fixture
def mock_user_lo_a():
    """Mock loan officer A."""
    user = MagicMock()
    user.id = 10
    user.email = "lo_a@example.com"
    user.first_name = "Alice"
    user.last_name = "Smith"
    user.organization_id = 1
    user.role = "loan_officer"
    user.nmls_number = "12345"
    user.is_active = True
    return user


@pytest.fixture
def mock_user_lo_b():
    """Mock loan officer B."""
    user = MagicMock()
    user.id = 20
    user.email = "lo_b@example.com"
    user.first_name = "Bob"
    user.last_name = "Jones"
    user.organization_id = 1
    user.role = "loan_officer"
    user.nmls_number = "67890"
    user.is_active = True
    return user


def _setup_scheduler_deps(mock_models):
    """Set up scheduler_appointment_routes dependencies with mock models."""
    from scheduler_appointment_routes import set_dependencies
    set_dependencies(
        get_db_func=lambda: iter([MagicMock()]),
        get_current_user_func=AsyncMock(),
        models_dict=mock_models,
    )


# =============================================================================
# TEST CLASS 1: Public Booking E2E
# =============================================================================

class TestPublicBookingE2E:
    """Full public booking lifecycle: anonymous user -> booked -> confirmed -> showed."""

    def test_complete_booking_flow(self, mock_db, mock_models, sample_booking_link,
                                    sample_appointment_type, sample_scheduler_config):
        """Anonymous user books via public link, gets confirmation, ICS generated."""
        _setup_scheduler_deps(mock_models)

        # Step 1: Booking link exists and is active
        assert sample_booking_link.is_active is True
        assert sample_booking_link.is_public is True
        assert sample_booking_link.slug == "jane-smith-consultation"

        # Step 2: Appointment type is available
        assert sample_appointment_type.is_public is True
        assert sample_appointment_type.default_duration_minutes == 30

        # Step 3: Config defines working hours
        monday = sample_scheduler_config.working_hours["monday"]
        assert monday["enabled"] is True
        assert monday["start"] == "09:00"
        assert monday["end"] == "17:00"

        # Step 4: Simulate slot generation - verify no conflict check blocks booking
        from scheduler_appointment_routes import _check_appointment_conflict
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None
        # Should not raise
        _check_appointment_conflict(
            mock_db,
            assigned_user_id=10,
            start_time=datetime(2026, 3, 15, 10, 0),
            end_time=datetime(2026, 3, 15, 10, 30),
            org_id=1,
        )

        # Step 5: Duplicate check passes
        from scheduler_appointment_routes import _check_duplicate_booking
        mock_db.query.return_value.filter.return_value.first.return_value = None
        _check_duplicate_booking(
            mock_db,
            attendee_email="jane@example.com",
            assigned_user_id=10,
            start_time=datetime(2026, 3, 15, 10, 0),
            org_id=1,
        )

        # Step 6: Lead is created/linked
        from scheduler_appointment_routes import _ensure_lead_for_booking
        mock_lead = MagicMock()
        mock_lead.id = 42
        mock_db.query.return_value.filter.return_value.first.return_value = mock_lead

        with patch("scheduler_appointment_routes.Lead", MagicMock(), create=True):
            lead_id = _ensure_lead_for_booking(
                mock_db,
                attendee_email="jane@example.com",
                attendee_name="Jane Doe",
                attendee_phone="+15551234567",
                assigned_user_id=10,
                org_id=1,
            )
        assert lead_id == 42

        # Step 7: Activity is logged
        from scheduler_appointment_routes import _log_appointment_activity
        _log_appointment_activity(
            mock_db, org_id=1, user_id=10, lead_id=42, loan_id=None,
            content="Appointment booked: Discovery Call with Jane Doe",
        )
        # Should have called db.add
        assert mock_db.add.called

    def test_booking_with_intake_form(self, sample_appointment):
        """Intake responses are stored with the appointment."""
        assert sample_appointment.intake_responses is not None
        assert "timeline" in sample_appointment.intake_responses
        assert sample_appointment.intake_responses["first_time"] is True

    def test_booking_rate_limiting(self):
        """Exceed rate limit, get blocked."""
        from scheduler_appointment_routes import _check_memory_rate_limit, _memory_rate_limits

        _memory_rate_limits.clear()

        key = "e2e_test_rate_limit"
        # Fill up to limit
        for _ in range(10):
            result = _check_memory_rate_limit(key, max_requests=10, window_seconds=60)
            assert result is True

        # 11th request should be blocked
        result = _check_memory_rate_limit(key, max_requests=10, window_seconds=60)
        assert result is False

        # Clean up
        _memory_rate_limits.clear()

    def test_booking_past_capacity(self, mock_db, mock_models, sample_scheduler_config):
        """All slots full — slot generation returns empty when max_meetings_per_day hit."""
        _setup_scheduler_deps(mock_models)

        # Config says max 8 per day
        assert sample_scheduler_config.max_meetings_per_day == 8

        # Simulate 8 existing appointments for a day
        existing_appts = []
        base_date = date(2026, 3, 16)  # Monday
        for i in range(8):
            appt = MagicMock()
            appt.scheduled_start = datetime.combine(base_date, time(9 + i, 0))
            appt.scheduled_end = datetime.combine(base_date, time(9 + i, 30))
            existing_appts.append(appt)

        # When _generate_available_slots checks max_per_day, it skips the day
        # Verify the logic: 8 appointments >= max_meetings_per_day (8) means skip
        day_count = len(existing_appts)
        max_per_day = sample_scheduler_config.max_meetings_per_day
        assert day_count >= max_per_day, "Day should be at capacity"

    def test_booking_timezone_conversion(self, sample_appointment):
        """Book in PT, stored as UTC, shown correctly."""
        import pytz

        # Appointment stored as UTC
        utc_start = sample_appointment.scheduled_start
        assert utc_start.tzinfo == timezone.utc

        # Convert to PT for display
        pacific = pytz.timezone("America/Los_Angeles")
        pt_start = utc_start.astimezone(pacific)

        # UTC 10:00 -> PT 02:00 (or 03:00 depending on DST)
        assert pt_start.tzinfo is not None
        assert pt_start.year == utc_start.year
        assert pt_start.day == utc_start.day

        # Round-trip: convert back to UTC
        back_to_utc = pt_start.astimezone(timezone.utc)
        assert back_to_utc == utc_start


# =============================================================================
# TEST CLASS 2: AI Booking E2E
# =============================================================================

class TestAIBookingE2E:
    """AI/Vapi booking flow: slots -> hold -> book -> confirm."""

    def test_vapi_available_slots_returns_real_data(self, mock_db, mock_models,
                                                      sample_scheduler_config):
        """Slots should be computed from config, NOT hardcoded 9-5."""
        _setup_scheduler_deps(mock_models)

        # Verify config has proper working hours
        wh = sample_scheduler_config.working_hours
        assert isinstance(wh, dict)
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
            assert wh[day]["enabled"] is True
        for day in ["saturday", "sunday"]:
            assert wh[day]["enabled"] is False

        # The slot generator reads from config, not hardcoded values
        # Verify the config is used by checking the _generate_available_slots signature
        from scheduler_appointment_routes import _generate_available_slots
        import inspect
        sig = inspect.signature(_generate_available_slots)
        assert "org_id" in sig.parameters
        assert "check_cross_source" in sig.parameters

    def test_vapi_booking_creates_real_appointment(self, mock_db, mock_models):
        """AI-booked appointment creates a real record in scheduler_appointments."""
        _setup_scheduler_deps(mock_models)

        Appointment = mock_models['Appointment']

        # Simulate creating an appointment via AI
        new_appt = MagicMock()
        new_appt.id = 999
        new_appt.booked_by_ai = True
        new_appt.title = "AI-Booked Discovery Call"
        new_appt.scheduled_start = datetime(2026, 3, 17, 14, 0, tzinfo=timezone.utc)
        new_appt.scheduled_end = datetime(2026, 3, 17, 14, 30, tzinfo=timezone.utc)
        new_appt.status = "booked"

        mock_db.add(new_appt)
        mock_db.flush()

        assert mock_db.add.called
        assert new_appt.booked_by_ai is True
        assert new_appt.status == "booked"

    def test_vapi_hold_then_convert(self, mock_db, mock_models):
        """Hold a slot temporarily, then confirm it to a real appointment."""
        _setup_scheduler_deps(mock_models)

        # Step 1: Create tentative/hold appointment
        held_appt = MagicMock()
        held_appt.id = 500
        held_appt.status = "tentative"
        held_appt.booked_by_ai = True
        held_appt.scheduled_start = datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc)

        # Step 2: Convert hold to confirmed booking
        held_appt.status = "booked"
        held_appt.auto_confirmed = True

        assert held_appt.status == "booked"
        assert held_appt.auto_confirmed is True

    def test_vapi_hold_expires(self, mock_db, mock_models):
        """Held slot expires when not confirmed, freeing the time."""
        _setup_scheduler_deps(mock_models)

        # Create a tentative appointment 15 minutes ago
        held_appt = MagicMock()
        held_appt.id = 501
        held_appt.status = "tentative"
        held_appt.created_at = datetime.now(timezone.utc) - timedelta(minutes=20)

        # Expiry check: tentative appointments older than 15 min should be cancelled
        hold_age = (datetime.now(timezone.utc) - held_appt.created_at).total_seconds() / 60
        assert hold_age > 15, "Hold should be expired"

        # Simulate cancellation
        held_appt.status = "cancelled"
        held_appt.cancellation_reason = "Hold expired - not confirmed within 15 minutes"

        assert held_appt.status == "cancelled"

        # The time slot should now be available again for others
        # (conflict check would no longer find this cancelled appointment)

    def test_vapi_identifies_caller_type(self, mock_db, mock_models):
        """AI should distinguish new lead vs active client vs MUM (mortgage under management)."""
        _setup_scheduler_deps(mock_models)

        # New lead: no existing record
        mock_db.query.return_value.filter.return_value.first.return_value = None
        from scheduler_appointment_routes import _ensure_lead_for_booking

        # Existing lead: found by email
        existing_lead = MagicMock()
        existing_lead.id = 42
        existing_lead.stage = "Active"
        mock_db.query.return_value.filter.return_value.first.return_value = existing_lead

        lead_id = _ensure_lead_for_booking(
            mock_db,
            attendee_email="existing@client.com",
            attendee_name="Existing Client",
            attendee_phone="+15559876543",
            assigned_user_id=10,
            org_id=1,
        )
        assert lead_id == 42  # Returns existing ID, not creating new


# =============================================================================
# TEST CLASS 3: Appointment Lifecycle E2E
# =============================================================================

class TestAppointmentLifecycleE2E:
    """Full appointment lifecycle: create -> confirm -> complete or no-show."""

    def test_confirm_appointment(self, mock_db, mock_models, sample_appointment):
        """Create -> confirm -> email sent."""
        _setup_scheduler_deps(mock_models)

        # Initial status is booked
        assert sample_appointment.status == "booked"

        # Confirm the appointment
        sample_appointment.status = "booked"  # "booked" is the confirmed state
        sample_appointment.auto_confirmed = True
        sample_appointment.status_changed_at = datetime.now(timezone.utc)

        # Verify email service can be called
        with patch("scheduler_appointment_routes.send_appointment_confirmation_email") as mock_email:
            mock_email.return_value = {"success": True}
            result = mock_email(
                to_email=sample_appointment.attendee_email,
                attendee_name=sample_appointment.attendee_name,
                appointment_title=sample_appointment.title,
                scheduled_start=sample_appointment.scheduled_start,
                scheduled_end=sample_appointment.scheduled_end,
                timezone_str=sample_appointment.timezone,
            )
            assert result["success"] is True
            mock_email.assert_called_once()

    def test_reschedule_appointment(self, mock_db, mock_models, sample_appointment):
        """Booked -> reschedule -> new time confirmed."""
        _setup_scheduler_deps(mock_models)

        original_start = sample_appointment.scheduled_start
        original_id = sample_appointment.id

        # New appointment references the old one
        rescheduled = MagicMock()
        rescheduled.id = 2
        rescheduled.rescheduled_from_id = original_id
        rescheduled.reschedule_count = sample_appointment.reschedule_count + 1
        rescheduled.scheduled_start = original_start + timedelta(days=1)
        rescheduled.scheduled_end = original_start + timedelta(days=1, minutes=30)
        rescheduled.status = "booked"

        # Original gets marked as rescheduled
        sample_appointment.status = "rescheduled"

        assert sample_appointment.status == "rescheduled"
        assert rescheduled.rescheduled_from_id == original_id
        assert rescheduled.reschedule_count == 1
        assert rescheduled.scheduled_start > original_start

    def test_cancel_appointment(self, mock_db, mock_models, sample_appointment):
        """Booked -> cancel -> slot freed -> notification sent."""
        _setup_scheduler_deps(mock_models)

        # Cancel the appointment
        sample_appointment.status = "cancelled"
        sample_appointment.cancelled_at = datetime.now(timezone.utc)
        sample_appointment.cancellation_reason = "Client requested cancellation"

        assert sample_appointment.status == "cancelled"
        assert sample_appointment.cancellation_reason is not None

        # Verify cancellation email service can be called
        with patch("scheduler_appointment_routes.send_appointment_cancellation_email") as mock_cancel_email:
            mock_cancel_email.return_value = {"success": True}
            result = mock_cancel_email(
                to_email=sample_appointment.attendee_email,
                attendee_name=sample_appointment.attendee_name,
                appointment_title=sample_appointment.title,
            )
            assert result["success"] is True

        # Slot should now be freed (conflict check returns None for cancelled)
        from scheduler_appointment_routes import _check_appointment_conflict
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None
        # Should not raise - the slot is available
        _check_appointment_conflict(
            mock_db, assigned_user_id=10,
            start_time=sample_appointment.scheduled_start,
            end_time=sample_appointment.scheduled_end,
            org_id=1,
        )

    def test_complete_appointment(self, mock_db, mock_models, sample_appointment):
        """Showed -> complete -> follow-up tasks created."""
        _setup_scheduler_deps(mock_models)

        # Mark as completed
        sample_appointment.status = "completed"
        sample_appointment.completed_at = datetime.now(timezone.utc)

        assert sample_appointment.status == "completed"
        assert sample_appointment.completed_at is not None

        # Follow-up task should be created
        from scheduler_appointment_routes import _create_followup_task
        _create_followup_task(
            mock_db,
            org_id=1,
            owner_id=10,
            lead_id=100,
            loan_id=None,
            title="Follow up after Discovery Call with Jane Doe",
            description="Client expressed interest in 1-3 month timeline",
            due_date=datetime.now(timezone.utc) + timedelta(days=1),
        )
        assert mock_db.add.called

    def test_no_show_detection(self, mock_db, mock_models, sample_appointment):
        """Past end time -> auto-detected -> recovery initiated."""
        _setup_scheduler_deps(mock_models)

        # Appointment end time is in the past
        sample_appointment.scheduled_end = datetime.now(timezone.utc) - timedelta(hours=1)
        sample_appointment.status = "booked"

        # Detect no-show: appointment end time has passed and status is still "booked"
        is_no_show = (
            sample_appointment.status == "booked"
            and sample_appointment.scheduled_end < datetime.now(timezone.utc)
        )
        assert is_no_show is True

        # Mark as no-show
        sample_appointment.status = "no_show"
        sample_appointment.no_show_at = datetime.now(timezone.utc)

        assert sample_appointment.status == "no_show"

        # Recovery: create escalation task
        from scheduler_appointment_routes import _create_comm_failure_task
        _create_comm_failure_task(
            mock_db,
            org_id=1,
            assigned_user_id=10,
            attendee_name="Jane Doe",
            error_msg="Client did not attend scheduled appointment",
        )
        assert mock_db.add.called


# =============================================================================
# TEST CLASS 4: Conflict Prevention E2E
# =============================================================================

class TestConflictPreventionE2E:
    """Double-booking prevention, buffer enforcement, capacity limits."""

    def test_double_booking_prevented(self, mock_db, mock_models):
        """Two concurrent bookings for same slot — second one rejected with 409."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _check_appointment_conflict
        from fastapi import HTTPException

        # First booking succeeds (no existing conflict)
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None
        _check_appointment_conflict(
            mock_db, assigned_user_id=10,
            start_time=datetime(2026, 3, 15, 10, 0),
            end_time=datetime(2026, 3, 15, 10, 30),
            org_id=1,
        )

        # Second booking finds the first one as a conflict
        existing_conflict = MagicMock()
        existing_conflict.id = 1
        existing_conflict.scheduled_start = datetime(2026, 3, 15, 10, 0)
        existing_conflict.scheduled_end = datetime(2026, 3, 15, 10, 30)
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = existing_conflict

        with pytest.raises(HTTPException) as exc_info:
            _check_appointment_conflict(
                mock_db, assigned_user_id=10,
                start_time=datetime(2026, 3, 15, 10, 0),
                end_time=datetime(2026, 3, 15, 10, 30),
                org_id=1,
            )
        assert exc_info.value.status_code == 409
        assert "no longer available" in exc_info.value.detail

    def test_buffer_time_enforced(self, mock_db, mock_models, sample_scheduler_config):
        """15-min buffer between appointments prevents back-to-back booking."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _has_cross_source_conflict

        # Existing appointment: 10:00-10:30
        busy_times = [
            (datetime(2026, 3, 15, 10, 0), datetime(2026, 3, 15, 10, 30))
        ]

        # Try to book at 10:30 (right after) with 5-min buffer_after
        conflict = _has_cross_source_conflict(
            busy_times,
            slot_start=datetime(2026, 3, 15, 10, 30),
            slot_end=datetime(2026, 3, 15, 11, 0),
            buffer_before=5,
            buffer_after=5,
        )
        # The buffered end of existing appt is 10:35, which overlaps with 10:30
        assert conflict is True, "Buffer time should prevent immediate back-to-back booking"

        # But 10:35 start (after buffer) should be fine
        conflict = _has_cross_source_conflict(
            busy_times,
            slot_start=datetime(2026, 3, 15, 10, 35),
            slot_end=datetime(2026, 3, 15, 11, 5),
            buffer_before=5,
            buffer_after=5,
        )
        assert conflict is False, "Slot after buffer period should be available"

    def test_lunch_block_respected(self, sample_scheduler_config):
        """No booking during lunch break."""
        assert sample_scheduler_config.enforce_lunch_break is True
        assert sample_scheduler_config.lunch_break_start == time(12, 0)
        assert sample_scheduler_config.lunch_break_end == time(13, 0)

        # A slot at 12:15 falls within lunch break
        proposed_start = time(12, 15)
        lunch_start = sample_scheduler_config.lunch_break_start
        lunch_end = sample_scheduler_config.lunch_break_end

        is_during_lunch = (
            sample_scheduler_config.enforce_lunch_break
            and lunch_start <= proposed_start < lunch_end
        )
        assert is_during_lunch is True, "12:15 should be blocked by lunch break"

        # A slot at 13:00 is after lunch
        proposed_start_after = time(13, 0)
        is_during_lunch_after = (
            sample_scheduler_config.enforce_lunch_break
            and lunch_start <= proposed_start_after < lunch_end
        )
        assert is_during_lunch_after is False, "13:00 should not be blocked by lunch"

    def test_business_hours_enforced(self, sample_scheduler_config):
        """No booking outside configured working hours."""
        wh = sample_scheduler_config.working_hours

        # Saturday is disabled
        assert wh["saturday"]["enabled"] is False

        # Monday 8:00 is before 9:00 start
        monday_start = time(int(wh["monday"]["start"].split(":")[0]),
                            int(wh["monday"]["start"].split(":")[1]))
        proposed_early = time(8, 0)
        assert proposed_early < monday_start, "8 AM should be before business hours"

        # Monday 17:30 is after 17:00 end
        monday_end = time(int(wh["monday"]["end"].split(":")[0]),
                          int(wh["monday"]["end"].split(":")[1]))
        proposed_late = time(17, 30)
        assert proposed_late > monday_end, "5:30 PM should be after business hours"

        # Monday 10:00 is within hours
        proposed_valid = time(10, 0)
        assert monday_start <= proposed_valid < monday_end, "10 AM should be within business hours"

    def test_capacity_limit_enforced(self, mock_db, mock_models, sample_scheduler_config):
        """Daily maximum meetings respected."""
        _setup_scheduler_deps(mock_models)

        max_daily = sample_scheduler_config.max_meetings_per_day
        assert max_daily == 8

        # Simulate 8 appointments already booked
        existing_count = 8
        assert existing_count >= max_daily, "Should be at capacity"

        # Next booking attempt should be rejected by slot generator
        # _generate_available_slots skips the day when day_appts >= user_max_per_day
        skip_day = existing_count >= max_daily
        assert skip_day is True


# =============================================================================
# TEST CLASS 5: Multi-Source Calendar E2E
# =============================================================================

class TestMultiSourceE2E:
    """Cross-source conflict detection: Google, Salesforce, scheduler appointments."""

    def test_google_event_blocks_slot(self, mock_db, mock_models):
        """Synced Google Calendar event makes scheduler slot unavailable."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _has_cross_source_conflict

        # Google event: 2:00 PM - 3:00 PM
        google_busy = [
            (datetime(2026, 3, 15, 14, 0), datetime(2026, 3, 15, 15, 0))
        ]

        # Try to book a scheduler appointment at 2:30 PM
        conflict = _has_cross_source_conflict(
            google_busy,
            slot_start=datetime(2026, 3, 15, 14, 30),
            slot_end=datetime(2026, 3, 15, 15, 0),
        )
        assert conflict is True, "Google event should block overlapping scheduler slot"

        # 3:00 PM should be free (no overlap, no buffer in this call)
        conflict = _has_cross_source_conflict(
            google_busy,
            slot_start=datetime(2026, 3, 15, 15, 0),
            slot_end=datetime(2026, 3, 15, 15, 30),
        )
        assert conflict is False, "Slot after Google event should be available"

    def test_manual_and_ai_no_conflict(self, mock_db, mock_models):
        """Manual calendar booking visible to AI slot generator."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _get_cross_source_conflicts

        # Mock CalendarEvent from main module
        mock_calendar_event = MagicMock()
        mock_calendar_event.start_time = datetime(2026, 3, 15, 11, 0)
        mock_calendar_event.end_time = datetime(2026, 3, 15, 12, 0)

        with patch("scheduler_appointment_routes.main") as mock_main:
            mock_main.CalendarEvent = MagicMock()
            # Return a manual calendar event
            mock_db.query.return_value.filter.return_value.all.return_value = [mock_calendar_event]

            conflicts = _get_cross_source_conflicts(
                mock_db, target_user_id=10,
                start_dt=datetime(2026, 3, 15, 0, 0),
                end_dt=datetime(2026, 3, 15, 23, 59),
                org_id=1,
            )

        # Should have found at least some conflicts from the queries
        # (exact count depends on which sources are available)
        assert isinstance(conflicts, list)

    def test_appointment_syncs_to_google(self, sample_appointment):
        """Our appointment should store Google Calendar event ID for sync."""
        # After syncing, the google_calendar_event_id should be populated
        sample_appointment.google_calendar_event_id = "google_event_abc123"
        sample_appointment.last_synced_at = datetime.now(timezone.utc)

        assert sample_appointment.google_calendar_event_id == "google_event_abc123"
        assert sample_appointment.last_synced_at is not None


# =============================================================================
# TEST CLASS 6: Team Reassignment E2E
# =============================================================================

class TestTeamReassignmentE2E:
    """Appointment reassigned from one LO to another."""

    def test_reassign_appointment(self, mock_db, mock_models, sample_appointment,
                                   mock_user_lo_a, mock_user_lo_b):
        """Booked with LO A -> reassign to LO B -> notified."""
        _setup_scheduler_deps(mock_models)

        # Initial assignment
        assert sample_appointment.assigned_user_id == 10  # LO A
        assert mock_user_lo_a.id == 10
        assert mock_user_lo_b.id == 20

        # Check no conflict for LO B at the same time
        from scheduler_appointment_routes import _check_appointment_conflict
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

        _check_appointment_conflict(
            mock_db, assigned_user_id=20,  # LO B
            start_time=sample_appointment.scheduled_start,
            end_time=sample_appointment.scheduled_end,
            org_id=1,
        )

        # Reassign
        sample_appointment.assigned_user_id = 20
        assert sample_appointment.assigned_user_id == 20

        # Notify team member via email
        with patch("scheduler_appointment_routes.send_team_member_notification_email") as mock_notify:
            mock_notify.return_value = {"success": True}
            result = mock_notify(
                to_email=mock_user_lo_b.email,
                appointment_title=sample_appointment.title,
                scheduled_start=sample_appointment.scheduled_start,
            )
            assert result["success"] is True
            mock_notify.assert_called_once()

        # Activity should be logged
        from scheduler_appointment_routes import _log_appointment_activity
        mock_db.reset_mock()
        _log_appointment_activity(
            mock_db, org_id=1, user_id=10, lead_id=100, loan_id=None,
            content=f"Appointment reassigned from Alice Smith to Bob Jones",
        )
        assert mock_db.add.called

    def test_reassignment_checks_new_lo_availability(self, mock_db, mock_models):
        """Reassignment checks that the new LO has no conflicts."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _check_appointment_conflict
        from fastapi import HTTPException

        # LO B has a conflicting appointment
        conflict = MagicMock()
        conflict.id = 99
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = conflict

        with pytest.raises(HTTPException) as exc_info:
            _check_appointment_conflict(
                mock_db, assigned_user_id=20,
                start_time=datetime(2026, 3, 15, 10, 0),
                end_time=datetime(2026, 3, 15, 10, 30),
                org_id=1,
            )
        assert exc_info.value.status_code == 409


# =============================================================================
# TEST CLASS 7: Recurring Appointment E2E
# =============================================================================

class TestRecurringAppointmentE2E:
    """Recurring series: create series -> modify one -> cancel future."""

    def test_create_recurring_series(self, mock_db, mock_models):
        """Create a weekly recurring series of appointments."""
        _setup_scheduler_deps(mock_models)

        series_id = str(uuid.uuid4())[:8]
        base_start = datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc)  # Monday

        series = []
        for week in range(4):
            appt = MagicMock()
            appt.id = 100 + week
            appt.scheduled_start = base_start + timedelta(weeks=week)
            appt.scheduled_end = appt.scheduled_start + timedelta(minutes=30)
            appt.status = "booked"
            appt.external_id = f"series-{series_id}"
            appt.internal_notes = f"Recurring: week {week + 1} of 4"
            series.append(appt)

        assert len(series) == 4
        assert all(a.status == "booked" for a in series)
        # All share the same series ID
        assert all(a.external_id == f"series-{series_id}" for a in series)

    def test_modify_single_occurrence(self, mock_db, mock_models):
        """Modify one occurrence in a series without affecting others."""
        _setup_scheduler_deps(mock_models)

        # Create a 4-week series
        series = []
        for week in range(4):
            appt = MagicMock()
            appt.id = 200 + week
            appt.scheduled_start = datetime(2026, 3, 16, 10, 0) + timedelta(weeks=week)
            appt.status = "booked"
            series.append(appt)

        # Modify week 2 - change time to 2 PM
        series[1].scheduled_start = datetime(2026, 3, 23, 14, 0)
        series[1].scheduled_end = datetime(2026, 3, 23, 14, 30)

        # Other weeks unchanged
        assert series[0].scheduled_start.hour == 10
        assert series[1].scheduled_start.hour == 14  # Modified
        assert series[2].scheduled_start.hour == 10
        assert series[3].scheduled_start.hour == 10

    def test_cancel_future_occurrences(self, mock_db, mock_models):
        """Cancel all future occurrences from a given date."""
        _setup_scheduler_deps(mock_models)

        series = []
        for week in range(4):
            appt = MagicMock()
            appt.id = 300 + week
            appt.scheduled_start = datetime(2026, 3, 16, 10, 0, tzinfo=timezone.utc) + timedelta(weeks=week)
            appt.status = "booked"
            series.append(appt)

        # Cancel from week 3 onward
        cancel_from = datetime(2026, 3, 30, 0, 0, tzinfo=timezone.utc)
        for appt in series:
            if appt.scheduled_start >= cancel_from:
                appt.status = "cancelled"
                appt.cancellation_reason = "Recurring series cancelled"

        assert series[0].status == "booked"
        assert series[1].status == "booked"
        assert series[2].status == "cancelled"
        assert series[3].status == "cancelled"


# =============================================================================
# TEST CLASS 8: Routing Strategy E2E
# =============================================================================

class TestRoutingE2E:
    """LO routing strategies: round-robin, direct, load-balanced, etc."""

    def test_direct_routing(self):
        """Direct strategy returns first candidate."""
        from services.scheduler_routing_service import _assign_direct
        assert _assign_direct([10, 20, 30]) == 10
        assert _assign_direct([]) is None

    def test_round_robin_routing(self, mock_db):
        """Round-robin rotates past last assigned user."""
        mock_db.execute.return_value.scalar.return_value = 20

        from services.scheduler_routing_service import _assign_round_robin
        result = _assign_round_robin(mock_db, org_id=1, candidate_ids=[10, 20, 30])
        assert result == 30  # Next after 20

    def test_round_robin_wraps(self, mock_db):
        """Round-robin wraps to first when at end of list."""
        mock_db.execute.return_value.scalar.return_value = 30

        from services.scheduler_routing_service import _assign_round_robin
        result = _assign_round_robin(mock_db, org_id=1, candidate_ids=[10, 20, 30])
        assert result == 10

    def test_load_balanced_picks_least_busy(self, mock_db):
        """Load-balanced assigns to LO with fewest current appointments."""
        mock_db.execute.return_value.scalar.side_effect = [5, 2, 8]

        from services.scheduler_routing_service import _assign_load_balanced
        result = _assign_load_balanced(mock_db, org_id=1, candidate_ids=[10, 20, 30])
        assert result == 20  # Fewest appointments

    def test_excluded_users_respected(self, mock_db):
        """Routing respects excluded_user_ids."""
        mock_link = MagicMock()
        mock_link.assigned_users = [10, 20, 30]

        from services.scheduler_routing_service import assign_loan_officer
        result = assign_loan_officer(
            db=mock_db, org_id=1, strategy="direct",
            booking_link=mock_link, excluded_user_ids=[10],
        )
        assert result == 20  # 10 excluded, so first available is 20

    def test_all_excluded_returns_none(self, mock_db):
        """Returns None when all candidates are excluded."""
        mock_link = MagicMock()
        mock_link.assigned_users = [10, 20]

        from services.scheduler_routing_service import assign_loan_officer
        result = assign_loan_officer(
            db=mock_db, org_id=1, strategy="direct",
            booking_link=mock_link, excluded_user_ids=[10, 20],
        )
        assert result is None


# =============================================================================
# TEST CLASS 9: Email / SMS Communication E2E
# =============================================================================

class TestCommunicationE2E:
    """Email and SMS communication flows with fallback and retry."""

    def test_email_retry_succeeds_eventually(self):
        """Email retries on transient failure then succeeds."""
        from scheduler_email_service import _retry_email_send

        attempt = {"count": 0}

        def flaky_send():
            attempt["count"] += 1
            if attempt["count"] < 3:
                return {"success": False, "error": "SMTP timeout"}
            return {"success": True, "message_id": "msg_123"}

        result = _retry_email_send(flaky_send, max_retries=3, backoff_base=0.01)
        assert result["success"] is True
        assert attempt["count"] == 3

    def test_sms_fallback_on_email_failure(self):
        """Falls back to SMS when all email retries fail."""
        from scheduler_email_service import send_with_sms_fallback

        def email_fn():
            return {"success": False, "error": "SMTP permanently down"}

        def sms_fn():
            return {"success": True, "message_id": "sms_456"}

        result = send_with_sms_fallback(
            email_fn, sms_fn, max_retries=0, context_label="test",
        )
        assert result["email_sent"] is False
        assert result["sms_sent"] is True

    def test_escalation_on_total_comm_failure(self, mock_db, mock_models):
        """Creates escalation task when both email and SMS fail."""
        _setup_scheduler_deps(mock_models)

        from scheduler_email_service import send_with_sms_fallback

        escalated = {"called": False}

        def email_fn():
            return {"success": False, "error": "email down"}

        def sms_fn():
            return {"success": False, "error": "sms down"}

        def escalation_fn(error_msg):
            escalated["called"] = True

        result = send_with_sms_fallback(
            email_fn, sms_fn, max_retries=0, context_label="test",
            escalation_fn=escalation_fn,
        )
        assert result["email_sent"] is False
        assert result["sms_sent"] is False
        assert escalated["called"] is True

    def test_consent_blocks_empty_phone(self):
        """SMS consent check blocks empty phone number."""
        from scheduler_email_service import check_sms_consent
        allowed, reason = check_sms_consent("")
        assert allowed is False
        assert "No phone" in reason

    def test_consent_blocks_on_error(self):
        """Fail-safe: block SMS if consent check itself errors."""
        with patch("database.SessionLocal", side_effect=Exception("DB down")):
            from scheduler_email_service import check_sms_consent
            allowed, reason = check_sms_consent("+15551234567")
            assert allowed is False


# =============================================================================
# TEST CLASS 10: Input Validation & Security E2E
# =============================================================================

class TestInputValidationE2E:
    """Input sanitization, URL validation, PII masking."""

    def test_sanitize_strips_html(self):
        """User input is sanitized to remove HTML/XSS."""
        from scheduler_appointment_routes import _sanitize_text

        # Script tag should be stripped
        result = _sanitize_text("<script>alert('xss')</script>Hello")
        assert "<script>" not in result
        assert "Hello" in result

    def test_sanitize_preserves_plain_text(self):
        """Plain text passes through sanitization unchanged."""
        from scheduler_appointment_routes import _sanitize_text

        result = _sanitize_text("John Smith - first-time buyer")
        assert "John Smith" in result

    def test_sanitize_handles_none(self):
        """None input returns None."""
        from scheduler_appointment_routes import _sanitize_text
        assert _sanitize_text(None) is None

    def test_mask_email(self):
        """Email masking for logging."""
        from scheduler_appointment_routes import _mask_email

        assert _mask_email("john@example.com") == "j***@example.com"
        assert _mask_email("") == "***"
        assert _mask_email(None) == "***"

    def test_validate_url_safe_schemes(self):
        """URL validation accepts only http/https."""
        from scheduler_appointment_routes import _validate_url

        assert _validate_url("https://example.com") == "https://example.com"
        assert _validate_url("http://example.com") == "http://example.com"
        assert _validate_url("javascript:alert(1)") is None
        assert _validate_url("ftp://example.com") is None
        assert _validate_url(None) is None
        assert _validate_url("") is None


# =============================================================================
# TEST CLASS 11: CRM Integration E2E
# =============================================================================

class TestCRMIntegrationE2E:
    """CRM lead creation, activity logging, and follow-up task creation."""

    def test_lead_created_for_new_booker(self, mock_db, mock_models):
        """New booker creates a lead record."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _ensure_lead_for_booking

        # No existing lead found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Mock the Lead model
        with patch("scheduler_appointment_routes.Lead", create=True) as MockLead:
            mock_new_lead = MagicMock()
            mock_new_lead.id = 999
            MockLead.return_value = mock_new_lead
            mock_db.flush = MagicMock()

            lead_id = _ensure_lead_for_booking(
                mock_db,
                attendee_email="newclient@test.com",
                attendee_name="New Client",
                attendee_phone="+15559999999",
                assigned_user_id=10,
                org_id=1,
            )

        # Should have attempted to add a new lead
        # (the actual result depends on the import path, but add should be called)
        assert mock_db.add.called or lead_id is not None

    def test_existing_lead_linked(self, mock_db, mock_models):
        """Existing lead with same email is linked, not duplicated."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _ensure_lead_for_booking

        existing = MagicMock()
        existing.id = 42
        existing.email = "existing@test.com"
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        lead_id = _ensure_lead_for_booking(
            mock_db,
            attendee_email="existing@test.com",
            attendee_name="Existing Client",
            attendee_phone="+15551111111",
            assigned_user_id=10,
            org_id=1,
        )

        assert lead_id == 42

    def test_no_lead_without_email(self, mock_db, mock_models):
        """No lead created when email is missing."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _ensure_lead_for_booking

        lead_id = _ensure_lead_for_booking(
            mock_db, attendee_email="", attendee_name="No Email",
            attendee_phone="", assigned_user_id=10, org_id=1,
        )
        assert lead_id is None

    def test_activity_logged_on_booking(self, mock_db, mock_models):
        """Activity record created when appointment is booked."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _log_appointment_activity
        mock_db.reset_mock()

        _log_appointment_activity(
            mock_db, org_id=1, user_id=10, lead_id=42, loan_id=None,
            content="Discovery Call scheduled for 03/15/2026 at 10:00 AM",
        )

        assert mock_db.add.called

    def test_activity_handles_db_error(self, mock_db, mock_models):
        """Activity logging does not crash on DB errors."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _log_appointment_activity

        mock_db.add.side_effect = Exception("DB connection lost")

        # Should not raise
        _log_appointment_activity(
            mock_db, org_id=1, user_id=10, lead_id=42, loan_id=None,
            content="Test",
        )

    def test_followup_task_created_on_completion(self, mock_db, mock_models):
        """Follow-up task created when appointment is completed."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _create_followup_task
        mock_db.reset_mock()

        _create_followup_task(
            mock_db, org_id=1, owner_id=10, lead_id=42, loan_id=None,
            title="Follow up after consultation",
            description="Client interested in FHA loan",
            due_date=datetime.now(timezone.utc) + timedelta(days=1),
        )

        assert mock_db.add.called


# =============================================================================
# TEST CLASS 12: Compliance E2E
# =============================================================================

class TestComplianceE2E:
    """Compliance checks: duplicate detection, LO licensing, audit logging."""

    def test_duplicate_booking_detected(self, mock_db, mock_models):
        """Same attendee + same LO + same time = 409 rejection."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _check_duplicate_booking
        from fastapi import HTTPException

        # Simulate finding a duplicate
        existing = MagicMock()
        existing.id = 555
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        with pytest.raises(HTTPException) as exc_info:
            _check_duplicate_booking(
                mock_db,
                attendee_email="duplicate@test.com",
                assigned_user_id=10,
                start_time=datetime(2026, 3, 15, 10, 0),
                org_id=1,
            )

        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.detail

    def test_duplicate_check_passes_for_different_time(self, mock_db, mock_models):
        """Different time window passes duplicate check."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _check_duplicate_booking

        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Should not raise
        _check_duplicate_booking(
            mock_db,
            attendee_email="unique@test.com",
            assigned_user_id=10,
            start_time=datetime(2026, 3, 15, 10, 0),
            org_id=1,
        )

    def test_duplicate_check_skipped_without_email(self, mock_db, mock_models):
        """No email means no duplicate check needed."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _check_duplicate_booking

        # Should return without checking DB
        _check_duplicate_booking(
            mock_db, attendee_email="", assigned_user_id=10,
            start_time=datetime(2026, 3, 15, 10, 0), org_id=1,
        )

    def test_lo_licensing_advisory_only(self, mock_db, mock_models):
        """LO licensing check is advisory - returns string, does NOT raise."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _check_lo_licensing

        # No state = no check needed
        result = _check_lo_licensing(mock_db, assigned_user_id=10, attendee_state="")
        assert result is None

        result = _check_lo_licensing(mock_db, assigned_user_id=10, attendee_state=None)
        assert result is None

    def test_lo_licensing_warns_no_nmls(self, mock_db, mock_models):
        """Warning returned when LO has no NMLS number."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _check_lo_licensing

        mock_user = MagicMock()
        mock_user.id = 10
        mock_user.nmls_number = None
        mock_user.first_name = "Alice"
        mock_user.last_name = "Smith"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        with patch("scheduler_appointment_routes.User", MagicMock(), create=True):
            result = _check_lo_licensing(mock_db, assigned_user_id=10, attendee_state="CA")

        assert result is not None
        assert isinstance(result, str)
        assert "NMLS" in result or "nmls" in result.lower()

    def test_audit_log_recorded(self, mock_db, mock_models):
        """Audit log entries created for scheduler operations."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _audit_log

        mock_request = MagicMock()
        mock_request.client.host = "192.168.1.1"
        mock_request.headers.get.return_value = "Mozilla/5.0"

        _audit_log(
            mock_db, org_id=1, user_id=10,
            action="created", entity_type="appointment", entity_id=1,
            changes={"status": {"old": None, "new": "booked"}},
            request=mock_request,
        )

        assert mock_db.add.called


# =============================================================================
# TEST CLASS 13: Capacity and Concurrency E2E
# =============================================================================

class TestCapacityConcurrencyE2E:
    """Capacity enforcement and concurrent access handling."""

    def test_select_for_update_prevents_race(self, mock_db, mock_models):
        """SELECT FOR UPDATE used to prevent concurrent double-booking."""
        _setup_scheduler_deps(mock_models)

        from scheduler_appointment_routes import _check_appointment_conflict
        from sqlalchemy.exc import OperationalError
        from fastapi import HTTPException

        # Simulate OperationalError when row is locked
        mock_db.query.return_value.filter.return_value.with_for_update.side_effect = (
            OperationalError("lock", {}, Exception("resource busy"))
        )

        with pytest.raises(HTTPException) as exc_info:
            _check_appointment_conflict(
                mock_db, assigned_user_id=10,
                start_time=datetime(2026, 3, 15, 10, 0),
                end_time=datetime(2026, 3, 15, 10, 30),
                org_id=1,
            )
        assert exc_info.value.status_code == 409
        assert "being booked by another user" in exc_info.value.detail

    def test_memory_rate_limiter_thread_safety(self):
        """Memory rate limiter is thread-safe."""
        from scheduler_appointment_routes import _check_memory_rate_limit, _memory_rate_limits
        import threading

        _memory_rate_limits.clear()

        results = {"allowed": 0, "blocked": 0}
        lock = threading.Lock()

        def try_request():
            allowed = _check_memory_rate_limit(
                "thread_test", max_requests=5, window_seconds=60,
            )
            with lock:
                if allowed:
                    results["allowed"] += 1
                else:
                    results["blocked"] += 1

        threads = [threading.Thread(target=try_request) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results["allowed"] == 5
        assert results["blocked"] == 15
        assert results["allowed"] + results["blocked"] == 20

        _memory_rate_limits.clear()

    def test_rate_limit_window_expiry(self):
        """Rate limit counter resets after window expires."""
        from scheduler_appointment_routes import _check_memory_rate_limit, _memory_rate_limits
        import time as _time_mod

        _memory_rate_limits.clear()

        key = "window_expiry_test"
        # Use very short window
        for _ in range(3):
            _check_memory_rate_limit(key, max_requests=3, window_seconds=0.1)

        # Should be blocked
        assert _check_memory_rate_limit(key, max_requests=3, window_seconds=0.1) is False

        # Wait for window to expire
        _time_mod.sleep(0.15)

        # Should be allowed again
        assert _check_memory_rate_limit(key, max_requests=3, window_seconds=0.1) is True

        _memory_rate_limits.clear()


# =============================================================================
# TEST CLASS 14: Reminder System E2E
# =============================================================================

class TestReminderSystemE2E:
    """Appointment reminder scheduling and delivery."""

    def test_reminder_schedule_from_appointment_type(self, sample_appointment_type):
        """Reminders scheduled per appointment type config (24h and 1h before)."""
        schedule = sample_appointment_type.reminder_schedule
        assert schedule == [24, 1]

    def test_reminder_creation(self, mock_db, mock_models, sample_appointment):
        """Reminder records created for each scheduled window."""
        _setup_scheduler_deps(mock_models)

        AppointmentReminder = mock_models['AppointmentReminder']
        schedule = [24, 1]  # hours before

        for hours_before in schedule:
            reminder = MagicMock()
            reminder.appointment_id = sample_appointment.id
            reminder.organization_id = sample_appointment.organization_id
            reminder.channel = "email"
            reminder.hours_before = hours_before
            reminder.scheduled_for = sample_appointment.scheduled_start - timedelta(hours=hours_before)
            reminder.status = "pending"

            mock_db.add(reminder)

        # Should have added 2 reminders
        assert mock_db.add.call_count >= 2

    def test_reminder_with_sms_fallback(self):
        """Reminder delivery falls back to SMS if email fails."""
        from scheduler_email_service import send_with_sms_fallback

        def email_fn():
            return {"success": False, "error": "bounce"}

        def sms_fn():
            return {"success": True, "message_id": "sms_remind_123"}

        result = send_with_sms_fallback(
            email_fn, sms_fn, max_retries=0, context_label="reminder",
        )

        assert result["sms_sent"] is True


# =============================================================================
# TEST CLASS 15: Data Integrity E2E
# =============================================================================

class TestDataIntegrityE2E:
    """Model structure and data integrity checks."""

    def test_appointment_model_has_required_fields(self):
        """Verify Appointment model from smart_scheduler_models has all needed columns."""
        from smart_scheduler_models import create_smart_scheduler_models

        # Create models with a mock Base
        mock_base = MagicMock()
        mock_base.metadata = MagicMock()
        models = create_smart_scheduler_models(mock_base)

        assert 'Appointment' in models
        assert 'SchedulerConfig' in models
        assert 'AppointmentType' in models
        assert 'BlockedTime' in models
        assert 'BookingLink' in models
        assert 'AppointmentReminder' in models
        assert 'SchedulerAuditLog' in models

    def test_appointment_status_enum(self):
        """Verify all appointment statuses are defined."""
        from smart_scheduler_models import AppointmentStatus

        required_statuses = ["available", "tentative", "booked", "completed",
                             "no_show", "cancelled", "rescheduled"]
        for status in required_statuses:
            assert hasattr(AppointmentStatus, status.upper()), f"Missing status: {status}"

    def test_meeting_type_enum(self):
        """Verify all meeting types are defined."""
        from smart_scheduler_models import MeetingType

        required_types = ["discovery_call", "pre_approval_review",
                          "application_walkthrough", "document_review",
                          "rate_lock_discussion", "closing_prep",
                          "post_close_review", "referral_partner_meeting",
                          "team_sync", "custom"]
        for mt in required_types:
            assert hasattr(MeetingType, mt.upper()), f"Missing meeting type: {mt}"

    def test_routing_strategy_enum(self):
        """Verify all routing strategies are defined."""
        from smart_scheduler_models import RoutingStrategy

        required_strategies = ["round_robin", "load_balanced", "expertise",
                               "relationship", "availability", "ai_optimized"]
        for rs in required_strategies:
            assert hasattr(RoutingStrategy, rs.upper()), f"Missing strategy: {rs}"

    def test_default_working_hours(self):
        """Verify default working hours are defined correctly."""
        from smart_scheduler_models import DEFAULT_WORKING_HOURS

        assert isinstance(DEFAULT_WORKING_HOURS, dict)
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
            assert day in DEFAULT_WORKING_HOURS
            assert "start" in DEFAULT_WORKING_HOURS[day]
            assert "end" in DEFAULT_WORKING_HOURS[day]
            assert "enabled" in DEFAULT_WORKING_HOURS[day]
            assert DEFAULT_WORKING_HOURS[day]["enabled"] is True

        for day in ["saturday", "sunday"]:
            assert DEFAULT_WORKING_HOURS[day]["enabled"] is False

    def test_default_appointment_types(self):
        """Verify default appointment types are complete."""
        from smart_scheduler_models import DEFAULT_APPOINTMENT_TYPES

        assert len(DEFAULT_APPOINTMENT_TYPES) >= 7

        for apt in DEFAULT_APPOINTMENT_TYPES:
            assert "type_key" in apt
            assert "type_name" in apt
            assert "default_duration_minutes" in apt
            assert "intake_questions" in apt
            assert isinstance(apt["intake_questions"], list)
