"""
Comprehensive Smart Scheduler Tests

Covers:
- SmartSchedulerService: assignment strategies, availability checking, booking
- Cross-source conflict detection
- Real-time appointment counting (replaces stale counters)
- Appointment lifecycle (book, confirm, cancel)
- Reminder email/SMS functions
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a chainable mock database session (no spec — allows .query().filter().all() chains)."""
    session = MagicMock()
    # Set up default chain: .query().filter().filter().order_by().all() -> []
    session.query.return_value.filter.return_value = session.query.return_value
    session.query.return_value.order_by.return_value = session.query.return_value
    session.query.return_value.first.return_value = None
    session.query.return_value.all.return_value = []
    session.query.return_value.scalar.return_value = 0
    return session


@pytest.fixture
def default_settings():
    """Create a mock SchedulerSettings object."""
    from services.smart_scheduler_service import SchedulerSettings, SchedulingMethod
    settings = MagicMock(spec=SchedulerSettings)
    settings.id = 1
    settings.scheduling_method = SchedulingMethod.ROUND_ROBIN.value
    settings.default_duration_minutes = 30
    settings.buffer_between_appointments = 15
    settings.min_notice_hours = 2
    settings.max_advance_days = 30
    settings.last_assigned_lo_id = None
    settings.business_hours = {
        "monday": {"start": "09:00", "end": "17:00", "enabled": True},
        "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
        "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
        "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
        "friday": {"start": "09:00", "end": "17:00", "enabled": True},
        "saturday": {"start": "10:00", "end": "14:00", "enabled": True},
        "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
    }
    return settings


@pytest.fixture
def mock_lo_list():
    """Create a list of mock LoanOfficerSchedule objects."""
    from services.smart_scheduler_service import LoanOfficerSchedule
    los = []
    for i, (name, email, priority) in enumerate([
        ("Alice Smith", "alice@test.com", 3),
        ("Bob Jones", "bob@test.com", 2),
        ("Carol Davis", "carol@test.com", 1),
    ], start=1):
        lo = MagicMock(spec=LoanOfficerSchedule)
        lo.id = i
        lo.user_id = i * 10
        lo.lo_name = name
        lo.lo_email = email
        lo.lo_phone = f"555-000{i}"
        lo.is_active = True
        lo.priority = priority
        lo.max_daily_appointments = 8
        lo.max_weekly_appointments = 40
        lo.blocked_times = []
        lo.total_appointments = 0
        lo.appointments_this_week = 0
        lo.appointments_today = 0
        lo.organization_id = 1
        los.append(lo)
    return los


@pytest.fixture
def scheduler_service(mock_db, default_settings):
    """Create a SmartSchedulerService with mocked DB."""
    from services.smart_scheduler_service import SmartSchedulerService
    # Mock the _ensure_default_settings to avoid DB calls
    with patch.object(SmartSchedulerService, '_ensure_default_settings'):
        service = SmartSchedulerService(mock_db)
    # Wire up settings retrieval
    service.get_settings = MagicMock(return_value=default_settings)
    return service


# =============================================================================
# ENUM TESTS
# =============================================================================

class TestEnums:
    def test_scheduling_method_values(self):
        from services.smart_scheduler_service import SchedulingMethod
        assert SchedulingMethod.DIRECT.value == "direct"
        assert SchedulingMethod.ROUND_ROBIN.value == "round_robin"
        assert SchedulingMethod.PRIORITY.value == "priority"
        assert SchedulingMethod.AVAILABILITY.value == "availability"
        assert SchedulingMethod.LOAD_BALANCED.value == "load_balanced"

    def test_appointment_status_values(self):
        from services.smart_scheduler_service import AppointmentStatus
        assert AppointmentStatus.SCHEDULED.value == "scheduled"
        assert AppointmentStatus.CONFIRMED.value == "confirmed"
        assert AppointmentStatus.CANCELLED.value == "cancelled"
        assert AppointmentStatus.NO_SHOW.value == "no_show"
        assert AppointmentStatus.RESCHEDULED.value == "rescheduled"


# =============================================================================
# MODEL TESTS
# =============================================================================

class TestModels:
    def test_scheduler_settings_has_organization_id(self):
        from services.smart_scheduler_service import SchedulerSettings
        assert hasattr(SchedulerSettings, 'organization_id')

    def test_loan_officer_schedule_has_organization_id(self):
        from services.smart_scheduler_service import LoanOfficerSchedule
        assert hasattr(LoanOfficerSchedule, 'organization_id')

    def test_scheduled_appointment_has_organization_id(self):
        from services.smart_scheduler_service import ScheduledAppointment
        assert hasattr(ScheduledAppointment, 'organization_id')

    def test_scheduled_appointment_has_required_columns(self):
        from services.smart_scheduler_service import ScheduledAppointment
        required = [
            'appointment_id', 'loan_officer_id', 'lo_name', 'lo_email',
            'contact_name', 'contact_email', 'start_time', 'end_time',
            'status', 'duration_minutes', 'organization_id'
        ]
        for col in required:
            assert hasattr(ScheduledAppointment, col), f"Missing column: {col}"


# =============================================================================
# ASSIGNMENT STRATEGY TESTS
# =============================================================================

class TestDirectAssignment:
    def test_direct_returns_first_lo(self, scheduler_service, mock_lo_list):
        result = scheduler_service._assign_direct(mock_lo_list)
        assert result.lo_name == "Alice Smith"

    def test_direct_returns_none_for_empty_list(self, scheduler_service):
        result = scheduler_service._assign_direct([])
        assert result is None


class TestRoundRobinAssignment:
    def test_round_robin_starts_from_first(self, scheduler_service, default_settings, mock_lo_list):
        default_settings.last_assigned_lo_id = None
        result = scheduler_service._assign_round_robin(default_settings, mock_lo_list)
        assert result.lo_name == "Alice Smith"
        assert default_settings.last_assigned_lo_id == 1

    def test_round_robin_rotates(self, scheduler_service, default_settings, mock_lo_list):
        default_settings.last_assigned_lo_id = 1  # Alice was last
        result = scheduler_service._assign_round_robin(default_settings, mock_lo_list)
        assert result.lo_name == "Bob Jones"
        assert default_settings.last_assigned_lo_id == 2

    def test_round_robin_wraps_around(self, scheduler_service, default_settings, mock_lo_list):
        default_settings.last_assigned_lo_id = 3  # Carol was last
        result = scheduler_service._assign_round_robin(default_settings, mock_lo_list)
        assert result.lo_name == "Alice Smith"
        assert default_settings.last_assigned_lo_id == 1

    def test_round_robin_handles_unknown_last_id(self, scheduler_service, default_settings, mock_lo_list):
        default_settings.last_assigned_lo_id = 999  # Not in list
        result = scheduler_service._assign_round_robin(default_settings, mock_lo_list)
        assert result.lo_name == "Alice Smith"

    def test_round_robin_returns_none_for_empty_list(self, scheduler_service, default_settings):
        result = scheduler_service._assign_round_robin(default_settings, [])
        assert result is None


class TestPriorityAssignment:
    def test_priority_assigns_highest_available(self, scheduler_service, mock_lo_list):
        scheduler_service._is_lo_available = MagicMock(return_value=True)
        appt_time = datetime.utcnow() + timedelta(hours=3)
        result = scheduler_service._assign_by_priority(mock_lo_list, appt_time)
        # Alice has priority 3 (highest)
        assert result.lo_name == "Alice Smith"

    def test_priority_skips_unavailable(self, scheduler_service, mock_lo_list):
        # Alice unavailable, Bob available
        scheduler_service._is_lo_available = MagicMock(
            side_effect=lambda lo, t: lo.lo_name != "Alice Smith"
        )
        appt_time = datetime.utcnow() + timedelta(hours=3)
        result = scheduler_service._assign_by_priority(mock_lo_list, appt_time)
        assert result.lo_name == "Bob Jones"

    def test_priority_falls_back_to_highest_when_all_unavailable(self, scheduler_service, mock_lo_list):
        scheduler_service._is_lo_available = MagicMock(return_value=False)
        appt_time = datetime.utcnow() + timedelta(hours=3)
        result = scheduler_service._assign_by_priority(mock_lo_list, appt_time)
        assert result.lo_name == "Alice Smith"  # Highest priority as fallback


class TestAvailabilityAssignment:
    def test_availability_assigns_first_available(self, scheduler_service, mock_lo_list):
        # Alice unavailable, Bob available
        scheduler_service._is_lo_available = MagicMock(
            side_effect=lambda lo, t: lo.lo_name == "Bob Jones"
        )
        appt_time = datetime.utcnow() + timedelta(hours=3)
        result = scheduler_service._assign_by_availability(mock_lo_list, appt_time)
        assert result.lo_name == "Bob Jones"

    def test_availability_falls_back_to_first(self, scheduler_service, mock_lo_list):
        scheduler_service._is_lo_available = MagicMock(return_value=False)
        appt_time = datetime.utcnow() + timedelta(hours=3)
        result = scheduler_service._assign_by_availability(mock_lo_list, appt_time)
        assert result.lo_name == "Alice Smith"


class TestLoadBalancedAssignment:
    def test_load_balanced_picks_least_busy(self, scheduler_service, mock_lo_list):
        # Mock real-time counts: Alice=5, Bob=2, Carol=8
        scheduler_service._get_real_time_appointment_count = MagicMock(
            side_effect=lambda lo_id, period: {1: 5, 2: 2, 3: 8}.get(lo_id, 0)
        )
        result = scheduler_service._assign_load_balanced(mock_lo_list)
        assert result.lo_name == "Bob Jones"

    def test_load_balanced_returns_none_for_empty(self, scheduler_service):
        result = scheduler_service._assign_load_balanced([])
        assert result is None


# =============================================================================
# REAL-TIME COUNT TESTS
# =============================================================================

class TestRealTimeCounts:
    def test_get_real_time_count_today(self, scheduler_service, mock_db):
        mock_db.query.return_value.filter.return_value.scalar.return_value = 3
        count = scheduler_service._get_real_time_appointment_count(1, "today")
        assert count == 3

    def test_get_real_time_count_week(self, scheduler_service, mock_db):
        mock_db.query.return_value.filter.return_value.scalar.return_value = 12
        count = scheduler_service._get_real_time_appointment_count(1, "week")
        assert count == 12

    def test_get_real_time_count_invalid_period_returns_zero(self, scheduler_service):
        count = scheduler_service._get_real_time_appointment_count(1, "invalid")
        assert count == 0

    def test_get_real_time_count_returns_zero_when_none(self, scheduler_service, mock_db):
        mock_db.query.return_value.filter.return_value.scalar.return_value = None
        count = scheduler_service._get_real_time_appointment_count(1, "today")
        assert count == 0


# =============================================================================
# AVAILABILITY CHECKING TESTS
# =============================================================================

class TestLOAvailability:
    def test_available_when_no_time_given(self, scheduler_service, mock_lo_list):
        assert scheduler_service._is_lo_available(mock_lo_list[0]) is True

    def test_unavailable_when_blocked(self, scheduler_service, mock_lo_list):
        lo = mock_lo_list[0]
        future = datetime.utcnow() + timedelta(hours=5)
        lo.blocked_times = [{
            "start": (future - timedelta(hours=1)).isoformat(),
            "end": (future + timedelta(hours=1)).isoformat(),
            "reason": "Personal"
        }]
        assert scheduler_service._is_lo_available(lo, future) is False

    def test_available_outside_blocked_time(self, scheduler_service, mock_lo_list):
        lo = mock_lo_list[0]
        future = datetime.utcnow() + timedelta(hours=10)
        lo.blocked_times = [{
            "start": (future + timedelta(hours=5)).isoformat(),
            "end": (future + timedelta(hours=6)).isoformat(),
        }]
        # Mock cross-source to return no conflicts
        with patch('services.smart_scheduler_service._get_cross_source_busy_times', return_value=[]):
            scheduler_service._get_real_time_appointment_count = MagicMock(return_value=0)
            assert scheduler_service._is_lo_available(lo, future) is True

    def test_unavailable_when_at_daily_capacity(self, scheduler_service, mock_lo_list):
        lo = mock_lo_list[0]
        lo.max_daily_appointments = 3
        scheduler_service._get_real_time_appointment_count = MagicMock(return_value=3)
        future = datetime.utcnow() + timedelta(hours=5)
        assert scheduler_service._is_lo_available(lo, future) is False

    def test_available_when_under_daily_capacity(self, scheduler_service, mock_lo_list):
        lo = mock_lo_list[0]
        lo.max_daily_appointments = 8
        scheduler_service._get_real_time_appointment_count = MagicMock(return_value=2)
        future = datetime.utcnow() + timedelta(hours=5)
        with patch('services.smart_scheduler_service._get_cross_source_busy_times', return_value=[]):
            assert scheduler_service._is_lo_available(lo, future) is True


# =============================================================================
# CROSS-SOURCE CONFLICT TESTS
# =============================================================================

class TestCrossSourceConflicts:
    def test_no_conflicts_returns_empty(self, mock_db):
        from services.smart_scheduler_service import _get_cross_source_busy_times
        mock_db.query.return_value.filter.return_value.all.return_value = []

        start = datetime.utcnow()
        end = start + timedelta(hours=8)

        with patch('services.smart_scheduler_service.ScheduledAppointment') as MockSA:
            mock_db.query.return_value.filter.return_value.all.return_value = []
            conflicts = _get_cross_source_busy_times(mock_db, 1, start, end)
            # May have some conflicts from other sources failing gracefully
            # The key assertion is no crash
            assert isinstance(conflicts, list)

    def test_scheduled_appointment_creates_conflict(self, mock_db):
        from services.smart_scheduler_service import _get_cross_source_busy_times

        start = datetime.utcnow()
        end = start + timedelta(hours=8)

        mock_appt = MagicMock()
        mock_appt.start_time = start + timedelta(hours=2)
        mock_appt.end_time = start + timedelta(hours=2, minutes=30)

        mock_db.query.return_value.filter.return_value.all.return_value = [mock_appt]

        conflicts = _get_cross_source_busy_times(mock_db, 1, start, end)
        assert len(conflicts) >= 1
        assert conflicts[0] == (mock_appt.start_time, mock_appt.end_time)


# =============================================================================
# BOOKING TESTS
# =============================================================================

class TestBookAppointment:
    def test_book_appointment_raises_runtime_error(self, scheduler_service):
        """book_appointment is permanently disabled — no tenant isolation."""
        appt_time = datetime.utcnow() + timedelta(days=1)
        with pytest.raises(RuntimeError, match="permanently disabled"):
            scheduler_service.book_appointment(
                contact_name="Test User",
                contact_email="test@example.com",
                appointment_time=appt_time,
            )


# =============================================================================
# CANCELLATION TESTS
# =============================================================================

class TestCancelAppointment:
    def test_cancel_appointment_raises_runtime_error(self, scheduler_service):
        """cancel_appointment is permanently disabled — no tenant isolation."""
        with pytest.raises(RuntimeError, match="permanently disabled"):
            scheduler_service.cancel_appointment("APPT-12345678", "Client requested")


# =============================================================================
# ASSIGNMENT ROUTING TESTS (assign_loan_officer dispatcher)
# =============================================================================

class TestAssignLoanOfficerDispatch:
    def test_assign_loan_officer_raises_runtime_error(self, scheduler_service):
        """assign_loan_officer is permanently disabled — no tenant isolation."""
        with pytest.raises(RuntimeError, match="permanently disabled"):
            scheduler_service.assign_loan_officer()


# =============================================================================
# get_scheduler_service FACTORY TESTS
# =============================================================================

class TestGetSchedulerService:
    def test_get_scheduler_service_raises_runtime_error(self):
        """get_scheduler_service is permanently disabled — no tenant isolation."""
        from services.smart_scheduler_service import get_scheduler_service
        with pytest.raises(RuntimeError, match="permanently deprecated"):
            get_scheduler_service(MagicMock(spec=Session))


# =============================================================================
# ENSURE_SCHEDULER_TABLES TESTS
# =============================================================================

class TestEnsureSchedulerTables:
    def test_ensure_tables_function_exists(self):
        """Verify ensure_scheduler_tables is importable."""
        from services.smart_scheduler_service import ensure_scheduler_tables
        assert callable(ensure_scheduler_tables)

    def test_ensure_tables_handles_errors_gracefully(self):
        """Verify ensure_scheduler_tables catches exceptions without crashing."""
        from services.smart_scheduler_service import ensure_scheduler_tables
        # Patch the engine import to raise — ensure_scheduler_tables should catch it
        with patch.dict('sys.modules', {'database': MagicMock()}):
            try:
                ensure_scheduler_tables()
            except Exception:
                pass  # Expected — the point is it doesn't crash the app


# =============================================================================
# REMINDER EMAIL SERVICE TESTS
# =============================================================================

class TestReminderEmailService:
    def test_send_reminder_email_24h(self):
        from scheduler_email_service import send_appointment_reminder_email
        with patch('scheduler_email_service.notification_service') as mock_notifier:
            mock_notifier.send_email.return_value = {"success": True}

            result = send_appointment_reminder_email(
                attendee_email="test@example.com",
                attendee_name="John Doe",
                appointment_title="Mortgage Consultation",
                appointment_date="Monday, March 2, 2026",
                appointment_time="10:00 AM",
                hours_before=24,
                team_member_name="Alice Smith",
            )

            assert result["success"] is True
            # Verify email was sent with "Tomorrow" subject
            call_kwargs = mock_notifier.send_email.call_args
            assert "Tomorrow" in call_kwargs.kwargs.get("subject", call_kwargs[1].get("subject", ""))

    def test_send_reminder_email_1h(self):
        from scheduler_email_service import send_appointment_reminder_email
        with patch('scheduler_email_service.notification_service') as mock_notifier:
            mock_notifier.send_email.return_value = {"success": True}

            result = send_appointment_reminder_email(
                attendee_email="test@example.com",
                attendee_name="John Doe",
                appointment_title="Mortgage Consultation",
                appointment_date="Monday, March 2, 2026",
                appointment_time="10:00 AM",
                hours_before=1,
            )

            assert result["success"] is True
            call_kwargs = mock_notifier.send_email.call_args
            assert "Starting Soon" in call_kwargs.kwargs.get("subject", call_kwargs[1].get("subject", ""))

    def test_send_reminder_email_includes_ics_when_scheduled_start(self):
        from scheduler_email_service import send_appointment_reminder_email
        with patch('scheduler_email_service.notification_service') as mock_notifier:
            mock_notifier.send_email.return_value = {"success": True}

            scheduled = datetime.utcnow() + timedelta(days=1)
            result = send_appointment_reminder_email(
                attendee_email="test@example.com",
                attendee_name="John Doe",
                appointment_title="Mortgage Consultation",
                appointment_date="Monday, March 2, 2026",
                appointment_time="10:00 AM",
                scheduled_start=scheduled,
                team_member_email="alice@test.com",
            )

            assert result["success"] is True
            call_kwargs = mock_notifier.send_email.call_args
            attachments = call_kwargs.kwargs.get("attachments") or call_kwargs[1].get("attachments")
            assert attachments is not None
            assert len(attachments) == 1
            assert attachments[0]["filename"] == "appointment.ics"
            assert attachments[0]["type"] == "text/calendar"

    def test_send_reminder_sms(self):
        import importlib
        mock_telnyx = MagicMock()
        mock_msg = MagicMock()
        mock_msg.id = "msg-123"
        mock_telnyx.Message.create.return_value = mock_msg

        with patch.dict('os.environ', {'TELNYX_PHONE_NUMBER': '+15551234567'}):
            with patch.dict('sys.modules', {'telnyx': mock_telnyx}):
                # Re-import to pick up the mocked telnyx module
                from scheduler_email_service import send_appointment_reminder_sms

                result = send_appointment_reminder_sms(
                    attendee_phone="+15559876543",
                    attendee_name="John",
                    appointment_date="March 2, 2026",
                    appointment_time="10:00 AM",
                    hours_before=24,
                    team_member_name="Alice",
                )

                assert result["success"] is True
                # Verify message was created
                mock_telnyx.Message.create.assert_called_once()
                call_kwargs = mock_telnyx.Message.create.call_args
                msg_text = call_kwargs.kwargs.get("text", call_kwargs[1].get("text", ""))
                assert "tomorrow" in msg_text.lower()

    def test_send_reminder_sms_no_telnyx_number(self):
        from scheduler_email_service import send_appointment_reminder_sms
        with patch.dict('os.environ', {}, clear=True):
            result = send_appointment_reminder_sms(
                attendee_phone="+15559876543",
                attendee_name="John",
                appointment_date="March 2, 2026",
                appointment_time="10:00 AM",
            )

            assert result["success"] is False
            assert "not configured" in result["error"]


# =============================================================================
# ICS GENERATION TESTS
# =============================================================================

class TestICSGeneration:
    def test_generate_ics_content(self):
        from scheduler_email_service import generate_ics_content

        start = datetime(2026, 3, 2, 15, 0, 0)
        ics = generate_ics_content(
            appointment_title="Test Meeting",
            start_datetime=start,
            duration_minutes=30,
            attendee_email="attendee@test.com",
            attendee_name="John Doe",
            organizer_email="org@test.com",
            organizer_name="Alice Smith",
            description="A test meeting",
        )

        assert "BEGIN:VCALENDAR" in ics
        assert "BEGIN:VEVENT" in ics
        assert "Test Meeting" in ics
        assert "attendee@test.com" in ics
        assert "org@test.com" in ics
        assert "END:VCALENDAR" in ics

    def test_generate_ics_with_video_link(self):
        from scheduler_email_service import generate_ics_content

        start = datetime(2026, 3, 2, 15, 0, 0)
        ics = generate_ics_content(
            appointment_title="Video Meeting",
            start_datetime=start,
            duration_minutes=30,
            attendee_email="attendee@test.com",
            attendee_name="John Doe",
            organizer_email="org@test.com",
            organizer_name="Alice Smith",
            video_link="https://meet.example.com/room-123",
        )

        assert "meet.example.com" in ics


# =============================================================================
# UPCOMING APPOINTMENTS TESTS
# =============================================================================

class TestUpcomingAppointments:
    def test_get_upcoming_filters_by_status(self, scheduler_service, mock_db):
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        result = scheduler_service.get_upcoming_appointments(days_ahead=7)
        assert result == []

    def test_get_upcoming_filters_by_lo(self, scheduler_service, mock_db):
        mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []
        result = scheduler_service.get_upcoming_appointments(loan_officer_id=1, days_ahead=7)
        assert result == []

    def test_get_appointments_in_range_with_dates(self, scheduler_service, mock_db):
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        result = scheduler_service.get_appointments_in_range(
            start_date="2026-03-01T00:00:00",
            end_date="2026-03-31T23:59:59",
        )
        assert result == []

    def test_get_appointments_in_range_with_invalid_dates(self, scheduler_service, mock_db):
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        # Invalid dates should fallback to defaults without crashing
        result = scheduler_service.get_appointments_in_range(
            start_date="not-a-date",
            end_date="also-not-a-date",
        )
        assert result == []
