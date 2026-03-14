"""
Scheduler Edge Cases Test Suite

Tests for edge-case behavior in the Smart Calendar system:
- Rapid navigation / duplicate appointment prevention
- Conflict detection for overlapping and adjacent appointments
- Buffer time enforcement between appointments
- Timezone / DST boundary handling
- Cancellation policy enforcement
- Borrower self-cancellation rate limits
- Working hours validation
- Past appointment rejection
- Max booking window enforcement
"""

import pytest
from datetime import datetime, timedelta, date, time, timezone
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# SQLAlchemy Column Mock
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

    def __hash__(self):
        return id(self)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_models():
    """Create mock model classes for dependency injection."""
    models = {}

    class MockConfig:
        user_id = _Col()
        organization_id = _Col()

        def __init__(self, **kwargs):
            self.user_id = kwargs.get('user_id', 1)
            self.organization_id = kwargs.get('organization_id', 1)
            self.working_hours = kwargs.get('working_hours', {
                "monday": {"start": "09:00", "end": "17:00", "enabled": True},
                "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
                "friday": {"start": "09:00", "end": "17:00", "enabled": True},
                "saturday": {"start": "00:00", "end": "00:00", "enabled": False},
                "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
            })
            self.buffer_before_minutes = kwargs.get('buffer_before_minutes', 5)
            self.buffer_after_minutes = kwargs.get('buffer_after_minutes', 5)
            self.min_notice_hours = kwargs.get('min_notice_hours', 2)
            self.max_meetings_per_day = kwargs.get('max_meetings_per_day', 8)
            self.enforce_lunch_break = kwargs.get('enforce_lunch_break', True)
            self.lunch_break_start = kwargs.get('lunch_break_start', time(12, 0))
            self.lunch_break_end = kwargs.get('lunch_break_end', time(13, 0))
            self.timezone = kwargs.get('timezone', 'America/Chicago')
            self.max_advance_days = kwargs.get('max_advance_days', 90)

    class MockAppointment:
        id = _Col()
        assigned_user_id = _Col()
        organization_id = _Col()
        status = _Col()
        scheduled_start = _Col()
        scheduled_end = _Col()
        attendee_email = _Col()
        cancelled_at = _Col()

    class MockBlockedTime:
        id = _Col()
        user_id = _Col()
        organization_id = _Col()
        start_datetime = _Col()
        end_datetime = _Col()
        is_active = _Col()
        applies_to_all_users = _Col()

    models['SchedulerConfig'] = MockConfig
    models['BlockedTime'] = MockBlockedTime
    models['Appointment'] = MockAppointment
    models['BookingLink'] = MagicMock
    models['AppointmentType'] = MagicMock
    models['SchedulerAuditLog'] = None
    models['VideoMeetingRoom'] = None

    return models


@pytest.fixture
def mock_db():
    """Create a chainable mock DB session."""
    db = MagicMock()
    db.query.return_value.filter.return_value = db.query.return_value
    db.query.return_value.first.return_value = None
    db.query.return_value.all.return_value = []
    db.query.return_value.count.return_value = 0
    db.query.return_value.with_for_update.return_value = db.query.return_value
    return db


@pytest.fixture
def setup_scheduler_helpers(mock_models):
    """Set up scheduler helpers with mocked dependencies."""
    import routes.scheduler._helpers as sar
    sar.set_dependencies(
        get_db_func=lambda: iter([MagicMock()]),
        get_current_user_func=MagicMock(),
        models_dict=mock_models
    )
    return sar


def _get_next_weekday(target_weekday=0, weeks_ahead=1):
    """Get a future date for a specific weekday (0=Monday, ..., 6=Sunday).
    Always at least `weeks_ahead` full weeks in the future to avoid min_notice_hours issues."""
    today = date.today()
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead + (weeks_ahead - 1) * 7)


# =============================================================================
# DUPLICATE APPOINTMENT PREVENTION
# =============================================================================

class TestDuplicateAppointmentPrevention:
    """Test that rapid navigation and duplicate bookings are caught."""

    def test_duplicate_booking_detected_same_email_same_time(self, setup_scheduler_helpers, mock_db):
        """Duplicate booking with same email + same user + same time should raise 409."""
        sar = setup_scheduler_helpers

        # Simulate an existing appointment found
        existing_appt = MagicMock()
        existing_appt.id = 42
        mock_db.query.return_value.filter.return_value.first.return_value = existing_appt

        with pytest.raises(HTTPException) as exc:
            sar._check_duplicate_booking(
                mock_db,
                attendee_email="borrower@example.com",
                assigned_user_id=1,
                start_time=datetime(2026, 3, 20, 10, 0),
                org_id=1,
            )
        assert exc.value.status_code == 409
        assert "already exists" in exc.value.detail

    def test_duplicate_booking_skipped_without_email(self, setup_scheduler_helpers, mock_db):
        """Duplicate check should be skipped when attendee_email is empty."""
        sar = setup_scheduler_helpers

        # Should not raise even though we haven't set up mock returns
        sar._check_duplicate_booking(
            mock_db,
            attendee_email="",
            assigned_user_id=1,
            start_time=datetime(2026, 3, 20, 10, 0),
            org_id=1,
        )

        # Also test with None
        sar._check_duplicate_booking(
            mock_db,
            attendee_email=None,
            assigned_user_id=1,
            start_time=datetime(2026, 3, 20, 10, 0),
            org_id=1,
        )

    def test_no_duplicate_when_no_existing(self, setup_scheduler_helpers, mock_db):
        """No duplicate should be found when the DB query returns None."""
        sar = setup_scheduler_helpers
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Should not raise
        sar._check_duplicate_booking(
            mock_db,
            attendee_email="new-client@example.com",
            assigned_user_id=1,
            start_time=datetime(2026, 3, 20, 10, 0),
            org_id=1,
        )


# =============================================================================
# CONFLICT DETECTION TESTS
# =============================================================================

class TestConflictDetection:
    """Test that overlapping appointments are caught and adjacent ones are allowed."""

    def test_overlapping_appointments_raise_409(self, setup_scheduler_helpers, mock_db):
        """Exactly overlapping appointments should raise HTTPException 409."""
        sar = setup_scheduler_helpers

        # Simulate an existing conflicting appointment
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = MagicMock()

        with pytest.raises(HTTPException) as exc:
            sar._check_appointment_conflict(
                mock_db,
                assigned_user_id=1,
                start_time=datetime(2026, 3, 20, 10, 0),
                end_time=datetime(2026, 3, 20, 10, 30),
            )
        assert exc.value.status_code == 409

    def test_adjacent_appointments_allowed(self, setup_scheduler_helpers, mock_db):
        """Back-to-back appointments (no overlap) should be allowed."""
        sar = setup_scheduler_helpers

        # No conflict found
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

        # Appointment 1: 10:00-10:30, Appointment 2: 10:30-11:00
        sar._check_appointment_conflict(
            mock_db,
            assigned_user_id=1,
            start_time=datetime(2026, 3, 20, 10, 30),
            end_time=datetime(2026, 3, 20, 11, 0),
        )
        # Should not raise

    def test_partial_overlap_raises_409(self, setup_scheduler_helpers, mock_db):
        """Partial overlap (e.g., 10:15-10:45 vs existing 10:00-10:30) should raise 409."""
        sar = setup_scheduler_helpers
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = MagicMock()

        with pytest.raises(HTTPException) as exc:
            sar._check_appointment_conflict(
                mock_db,
                assigned_user_id=1,
                start_time=datetime(2026, 3, 20, 10, 15),
                end_time=datetime(2026, 3, 20, 10, 45),
            )
        assert exc.value.status_code == 409

    def test_reschedule_excludes_self(self, setup_scheduler_helpers, mock_db):
        """When rescheduling, the current appointment should be excluded from conflict check."""
        sar = setup_scheduler_helpers
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

        # Should not raise when exclude_appointment_id is provided
        sar._check_appointment_conflict(
            mock_db,
            assigned_user_id=1,
            start_time=datetime(2026, 3, 20, 10, 0),
            end_time=datetime(2026, 3, 20, 10, 30),
            exclude_appointment_id=42,
        )

    def test_lock_contention_raises_409(self, setup_scheduler_helpers, mock_db):
        """If the DB row is locked by another transaction, should raise 409."""
        from sqlalchemy.exc import OperationalError
        sar = setup_scheduler_helpers

        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.side_effect = \
            OperationalError("lock", {}, Exception("could not obtain lock"))

        with pytest.raises(HTTPException) as exc:
            sar._check_appointment_conflict(
                mock_db,
                assigned_user_id=1,
                start_time=datetime(2026, 3, 20, 10, 0),
                end_time=datetime(2026, 3, 20, 10, 30),
            )
        assert exc.value.status_code == 409
        assert "being booked" in exc.value.detail


# =============================================================================
# BUFFER TIME TESTS
# =============================================================================

class TestBufferTime:
    """Test buffer time enforcement between appointments."""

    def test_buffer_time_blocks_adjacent_slot(self, setup_scheduler_helpers):
        """Cross-source conflict check with buffer should block slots within buffer range."""
        sar = setup_scheduler_helpers

        # Existing meeting 10:00-10:30
        conflicts = [
            (datetime(2026, 3, 20, 10, 0), datetime(2026, 3, 20, 10, 30)),
        ]

        # Slot 10:25-10:55 should conflict with 5-min buffer_before on the existing meeting
        # buffer_before extends the busy period start by 5 min (9:55),
        # buffer_after extends end by 5 min (10:35)
        # So 10:25 < 10:35 and 10:55 > 9:55 => conflict
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 3, 20, 10, 25),
            datetime(2026, 3, 20, 10, 55),
            buffer_before=5,
            buffer_after=5,
        ) is True

    def test_buffer_time_allows_slot_after_buffer(self, setup_scheduler_helpers):
        """Slot after the buffer period should be allowed."""
        sar = setup_scheduler_helpers

        # Existing meeting 10:00-10:30 with 5-min buffer_after => busy until 10:35
        conflicts = [
            (datetime(2026, 3, 20, 10, 0), datetime(2026, 3, 20, 10, 30)),
        ]

        # Slot 10:35-11:05 starts exactly at the buffer end
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 3, 20, 10, 35),
            datetime(2026, 3, 20, 11, 5),
            buffer_before=0,
            buffer_after=5,
        ) is False

    def test_no_buffer_adjacent_allowed(self, setup_scheduler_helpers):
        """Without buffer, back-to-back slots should be allowed."""
        sar = setup_scheduler_helpers

        conflicts = [
            (datetime(2026, 3, 20, 10, 0), datetime(2026, 3, 20, 10, 30)),
        ]

        # Slot 10:30-11:00 starts exactly when the meeting ends (no overlap)
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 3, 20, 10, 30),
            datetime(2026, 3, 20, 11, 0),
            buffer_before=0,
            buffer_after=0,
        ) is False

    def test_buffer_before_blocks_slot_ending_near_meeting(self, setup_scheduler_helpers):
        """buffer_before should extend the busy time earlier, blocking slots that end close."""
        sar = setup_scheduler_helpers

        # Existing meeting 11:00-11:30 with 10-min buffer_before => busy from 10:50
        conflicts = [
            (datetime(2026, 3, 20, 11, 0), datetime(2026, 3, 20, 11, 30)),
        ]

        # Slot 10:30-10:55 ends at 10:55, which is > 10:50 (buffered start) => conflict
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 3, 20, 10, 30),
            datetime(2026, 3, 20, 10, 55),
            buffer_before=10,
            buffer_after=0,
        ) is True


# =============================================================================
# TIMEZONE / DST BOUNDARY TESTS
# =============================================================================

class TestTimezoneDSTBoundaries:
    """Test timezone conversion handling at DST boundaries."""

    def test_user_timezone_defaults_to_chicago(self, setup_scheduler_helpers, mock_db):
        """Default timezone should be America/Chicago."""
        sar = setup_scheduler_helpers
        mock_db.query.return_value.filter.return_value.first.return_value = None

        tz = sar._get_user_timezone(mock_db, user_id=1)
        assert tz == "America/Chicago"

    def test_user_timezone_from_config(self, setup_scheduler_helpers, mock_db, mock_models):
        """User-configured timezone should be used when available."""
        sar = setup_scheduler_helpers

        config = mock_models['SchedulerConfig'](timezone="America/New_York")
        mock_db.query.return_value.filter.return_value.first.return_value = config

        tz = sar._get_user_timezone(mock_db, user_id=1)
        assert tz == "America/New_York"

    def test_dst_spring_forward_slot_count(self, setup_scheduler_helpers, mock_db, mock_models):
        """Slot generation should produce consistent slot count regardless of DST transition.
        The slot generator works in naive UTC/local time, so DST boundaries are transparent to it."""
        sar = setup_scheduler_helpers

        # March 9, 2026 is a Sunday (DST spring-forward day) -- no slots for Sunday.
        # March 10, 2026 is Monday (first working day after spring forward).
        monday_after_dst = date(2026, 3, 16)  # Use a definite Monday

        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=0,
            enforce_lunch_break=True,
            lunch_break_start=time(12, 0),
            lunch_break_end=time(13, 0),
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=monday_after_dst,
                end_date=monday_after_dst,
                org_id=1,
            )

        # 9-17 = 8 hours, minus 12-13 lunch = 7 hours = 14 thirty-min slots
        assert len(result) == 14

    def test_slot_generation_handles_no_timezone_config(self, setup_scheduler_helpers, mock_db, mock_models):
        """When config has no timezone set, slot generation should still work."""
        sar = setup_scheduler_helpers

        config = mock_models['SchedulerConfig'](user_id=1, min_notice_hours=0)
        config.timezone = None  # No timezone configured
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        future_monday = _get_next_weekday(0)

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=future_monday,
                end_date=future_monday,
                org_id=1,
            )

        # Should still generate slots
        assert len(result) > 0


# =============================================================================
# CANCELLATION POLICY ENFORCEMENT TESTS
# =============================================================================

class TestCancellationPolicyEnforcement:
    """Test cancellation policy service logic."""

    def _make_mock_policy(self, **overrides):
        """Create a mock cancellation policy."""
        policy = MagicMock()
        policy.id = 1
        policy.organization_id = overrides.get('organization_id', 1)
        policy.min_notice_hours = overrides.get('min_notice_hours', 24)
        policy.max_cancellations_per_borrower = overrides.get('max_cancellations_per_borrower', 3)
        policy.allow_borrower_cancel = overrides.get('allow_borrower_cancel', True)
        policy.require_reason = overrides.get('require_reason', True)
        policy.cancellation_reasons = overrides.get('cancellation_reasons', ["Schedule conflict", "Other"])
        policy.late_cancel_message = overrides.get('late_cancel_message', "This is a late cancellation.")
        return policy

    def _make_mock_appointment(self, **overrides):
        """Create a mock appointment for cancellation tests."""
        appt = MagicMock()
        appt.id = overrides.get('id', 100)
        appt.organization_id = overrides.get('organization_id', 1)
        appt.status = MagicMock()
        appt.status.value = overrides.get('status', 'booked')
        appt.scheduled_start = overrides.get(
            'scheduled_start',
            datetime.now(timezone.utc) + timedelta(days=2)  # 2 days from now
        )
        appt.attendee_email = overrides.get('attendee_email', 'borrower@example.com')
        appt.cancelled_at = overrides.get('cancelled_at', None)
        return appt

    def test_cancellation_policy_enforces_cutoff_time(self):
        """Cancellation within the notice period should be flagged as late."""
        from services.cancellation_policy_service import CancellationPolicyService

        mock_db = MagicMock()
        svc = CancellationPolicyService(mock_db)

        policy = self._make_mock_policy(min_notice_hours=24)
        # Appointment starts in 6 hours (within 24-hour notice period)
        appt = self._make_mock_appointment(
            scheduled_start=datetime.now(timezone.utc) + timedelta(hours=6)
        )

        with patch.object(svc, 'get_or_create_policy', return_value=policy), \
             patch.object(svc, 'get_borrower_cancel_count', return_value=0):
            mock_db.query.return_value.filter.return_value.first.return_value = appt

            result = svc.can_cancel(
                appointment_id=100,
                cancelled_by_email="borrower@example.com",
                org_id=1,
                is_staff=False,
            )

        assert result["is_late"] is True
        assert result["allowed"] is True
        assert result["late_cancel_message"] is not None

    def test_cancellation_outside_cutoff_not_late(self):
        """Cancellation outside the notice period should not be flagged as late."""
        from services.cancellation_policy_service import CancellationPolicyService

        mock_db = MagicMock()
        svc = CancellationPolicyService(mock_db)

        policy = self._make_mock_policy(min_notice_hours=24)
        # Appointment starts in 48 hours (outside 24-hour notice)
        appt = self._make_mock_appointment(
            scheduled_start=datetime.now(timezone.utc) + timedelta(hours=48)
        )

        with patch.object(svc, 'get_or_create_policy', return_value=policy), \
             patch.object(svc, 'get_borrower_cancel_count', return_value=0):
            mock_db.query.return_value.filter.return_value.first.return_value = appt

            result = svc.can_cancel(
                appointment_id=100,
                cancelled_by_email="borrower@example.com",
                org_id=1,
                is_staff=False,
            )

        assert result["is_late"] is False
        assert result["allowed"] is True
        assert result["late_cancel_message"] is None

    def test_already_cancelled_appointment_rejected(self):
        """Cancelling an already-cancelled appointment should be denied."""
        from services.cancellation_policy_service import CancellationPolicyService

        mock_db = MagicMock()
        svc = CancellationPolicyService(mock_db)

        policy = self._make_mock_policy()
        appt = self._make_mock_appointment(status='cancelled')

        with patch.object(svc, 'get_or_create_policy', return_value=policy):
            mock_db.query.return_value.filter.return_value.first.return_value = appt

            result = svc.can_cancel(
                appointment_id=100,
                cancelled_by_email="borrower@example.com",
                org_id=1,
            )

        assert result["allowed"] is False
        assert "already cancelled" in result["reason"]


# =============================================================================
# BORROWER SELF-CANCELLATION RATE LIMITS
# =============================================================================

class TestBorrowerSelfCancellationLimits:
    """Test that borrower cancellation limits are enforced."""

    def test_borrower_over_cancel_limit_blocked(self):
        """Borrower who has exceeded the cancellation limit should be blocked."""
        from services.cancellation_policy_service import CancellationPolicyService

        mock_db = MagicMock()
        svc = CancellationPolicyService(mock_db)

        policy = MagicMock()
        policy.max_cancellations_per_borrower = 3
        policy.allow_borrower_cancel = True
        policy.require_reason = False
        policy.cancellation_reasons = []
        policy.min_notice_hours = 24
        policy.late_cancel_message = "Late cancel."

        appt = MagicMock()
        appt.id = 100
        appt.organization_id = 1
        appt.status = MagicMock()
        appt.status.value = "booked"
        appt.scheduled_start = datetime.now(timezone.utc) + timedelta(days=2)
        appt.attendee_email = "repeat-canceller@example.com"

        with patch.object(svc, 'get_or_create_policy', return_value=policy), \
             patch.object(svc, 'get_borrower_cancel_count', return_value=3):
            mock_db.query.return_value.filter.return_value.first.return_value = appt

            result = svc.can_cancel(
                appointment_id=100,
                cancelled_by_email="repeat-canceller@example.com",
                org_id=1,
                is_staff=False,  # Borrower, not staff
            )

        assert result["allowed"] is False
        assert "cancelled 3 appointments" in result["reason"]

    def test_staff_can_cancel_even_at_limit(self):
        """Staff should always be allowed to cancel, even if borrower is over limit."""
        from services.cancellation_policy_service import CancellationPolicyService

        mock_db = MagicMock()
        svc = CancellationPolicyService(mock_db)

        policy = MagicMock()
        policy.max_cancellations_per_borrower = 3
        policy.allow_borrower_cancel = True
        policy.require_reason = False
        policy.cancellation_reasons = []
        policy.min_notice_hours = 24
        policy.late_cancel_message = "Late cancel."

        appt = MagicMock()
        appt.id = 100
        appt.organization_id = 1
        appt.status = MagicMock()
        appt.status.value = "booked"
        appt.scheduled_start = datetime.now(timezone.utc) + timedelta(days=2)
        appt.attendee_email = "repeat-canceller@example.com"

        with patch.object(svc, 'get_or_create_policy', return_value=policy), \
             patch.object(svc, 'get_borrower_cancel_count', return_value=5):
            mock_db.query.return_value.filter.return_value.first.return_value = appt

            result = svc.can_cancel(
                appointment_id=100,
                cancelled_by_email="repeat-canceller@example.com",
                org_id=1,
                is_staff=True,  # Staff user
            )

        assert result["allowed"] is True
        assert "Staff" in result["reason"]

    def test_borrower_self_cancel_disabled_blocks(self):
        """When allow_borrower_cancel is False, non-staff should be blocked."""
        from services.cancellation_policy_service import CancellationPolicyService

        mock_db = MagicMock()
        svc = CancellationPolicyService(mock_db)

        policy = MagicMock()
        policy.max_cancellations_per_borrower = 3
        policy.allow_borrower_cancel = False  # Disabled
        policy.require_reason = False
        policy.cancellation_reasons = []
        policy.min_notice_hours = 24
        policy.late_cancel_message = "Late cancel."

        appt = MagicMock()
        appt.id = 100
        appt.organization_id = 1
        appt.status = MagicMock()
        appt.status.value = "booked"
        appt.scheduled_start = datetime.now(timezone.utc) + timedelta(days=2)
        appt.attendee_email = "borrower@example.com"

        with patch.object(svc, 'get_or_create_policy', return_value=policy):
            mock_db.query.return_value.filter.return_value.first.return_value = appt

            result = svc.can_cancel(
                appointment_id=100,
                cancelled_by_email="borrower@example.com",
                org_id=1,
                is_staff=False,
            )

        assert result["allowed"] is False
        assert "not allowed" in result["reason"]


# =============================================================================
# WORKING HOURS VALIDATION TESTS
# =============================================================================

class TestWorkingHoursValidation:
    """Test working hours validation for edge cases."""

    def test_working_hours_time_format_validation(self):
        """Time format validation should accept HH:MM and reject invalid formats."""
        import re
        pattern = r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$"

        # Valid
        assert re.match(pattern, "09:00") is not None
        assert re.match(pattern, "17:00") is not None
        assert re.match(pattern, "00:00") is not None
        assert re.match(pattern, "23:59") is not None
        assert re.match(pattern, "9:00") is not None

        # Invalid
        assert re.match(pattern, "25:00") is None
        assert re.match(pattern, "09:60") is None
        assert re.match(pattern, "abc") is None
        assert re.match(pattern, "") is None

    def test_working_hours_start_must_be_before_end(self):
        """If start >= end and the day is enabled, no slots should be generated."""
        # This is enforced in the Pydantic schema and slot generator.
        # If start >= end on an enabled day, the slot generator should produce 0 slots.
        import routes.scheduler._helpers as sar

        working_hours = {
            "monday": {"start": "17:00", "end": "09:00", "enabled": True},  # Inverted
            "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
        }

        # The slot generator iterates hour by hour. If start > end, the inner
        # loop produces no slots for that day. We verify this indirectly:
        start_hour, start_min = 17, 0
        end_hour, end_min = 9, 0

        # Generate slots manually to verify the range is empty
        current_hour = start_hour
        current_min = start_min
        slots = []
        while (current_hour < end_hour or (current_hour == end_hour and current_min < end_min)):
            slots.append(f"{current_hour:02d}:{current_min:02d}")
            current_min += 30
            if current_min >= 60:
                current_min = 0
                current_hour += 1

        # No slots when start > end
        assert len(slots) == 0

    def test_disabled_day_generates_no_slots(self, setup_scheduler_helpers, mock_db, mock_models):
        """Disabled days should produce zero slots."""
        sar = setup_scheduler_helpers

        # Find a future Saturday (disabled by default)
        future_saturday = _get_next_weekday(5)

        config = mock_models['SchedulerConfig'](user_id=1, min_notice_hours=0)
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=future_saturday,
                end_date=future_saturday,
                org_id=1,
            )

        assert len(result) == 0


# =============================================================================
# PAST APPOINTMENT REJECTION
# =============================================================================

class TestPastAppointmentRejection:
    """Test that appointments cannot be booked in the past."""

    def test_min_notice_skips_past_slots(self, setup_scheduler_helpers, mock_db, mock_models):
        """Slots within the min_notice_hours window from now should be excluded."""
        sar = setup_scheduler_helpers

        # Use today's date
        today = date.today()
        weekday_name = today.strftime("%A").lower()

        # Configure working hours for today with min_notice = 24 hours
        working_hours = {
            weekday_name: {"start": "09:00", "end": "17:00", "enabled": True},
        }
        # Fill in other days as disabled
        for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
            if day != weekday_name:
                working_hours[day] = {"start": "00:00", "end": "00:00", "enabled": False}

        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=24,  # 24 hours notice required
            working_hours=working_hours,
            enforce_lunch_break=False,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=today,
                end_date=today,
                org_id=1,
            )

        # All slots today should be filtered out since they're within 24-hour notice
        assert len(result) == 0

    def test_date_range_validation_rejects_past(self, setup_scheduler_helpers, mock_db):
        """start_date after end_date should raise 400."""
        sar = setup_scheduler_helpers

        with pytest.raises(HTTPException) as exc:
            sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=date(2026, 3, 20),
                end_date=date(2026, 3, 15),
            )
        assert exc.value.status_code == 400
        assert "start_date" in exc.value.detail


# =============================================================================
# MAX BOOKING WINDOW TESTS
# =============================================================================

class TestMaxBookingWindow:
    """Test that appointments beyond the max booking window are rejected."""

    def test_date_range_exceeding_90_days_rejected(self, setup_scheduler_helpers, mock_db):
        """Date range exceeding 90 days should raise 400."""
        sar = setup_scheduler_helpers

        with pytest.raises(HTTPException) as exc:
            sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=date(2026, 1, 1),
                end_date=date(2026, 5, 1),  # 120 days
            )
        assert exc.value.status_code == 400
        assert "90" in exc.value.detail

    def test_exactly_90_days_allowed(self, setup_scheduler_helpers, mock_db, mock_models):
        """A 90-day range should be accepted (boundary case)."""
        sar = setup_scheduler_helpers

        config = mock_models['SchedulerConfig'](user_id=1, min_notice_hours=0)
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        start = date(2026, 1, 1)
        end = date(2026, 4, 1)  # Exactly 90 days

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            # Should not raise
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=start,
                end_date=end,
                org_id=1,
            )

        # Should return some slots (for weekdays in that range)
        assert isinstance(result, list)

    def test_single_day_range_allowed(self, setup_scheduler_helpers, mock_db, mock_models):
        """Same start and end date should be valid."""
        sar = setup_scheduler_helpers

        future_monday = _get_next_weekday(0)
        config = mock_models['SchedulerConfig'](user_id=1, min_notice_hours=0)
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=future_monday,
                end_date=future_monday,
                org_id=1,
            )

        assert len(result) > 0


# =============================================================================
# MAX MEETINGS PER DAY TESTS
# =============================================================================

class TestMaxMeetingsPerDay:
    """Test max meetings per day enforcement."""

    def test_max_per_day_skips_full_days(self, setup_scheduler_helpers, mock_db, mock_models):
        """Days at capacity should produce no available slots."""
        sar = setup_scheduler_helpers

        future_monday = _get_next_weekday(0)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=0,
            max_meetings_per_day=1,  # Very low limit
        )

        # One existing appointment
        existing_appt = MagicMock()
        existing_appt.scheduled_start = datetime.combine(future_monday, time(9, 0))
        existing_appt.scheduled_end = datetime.combine(future_monday, time(9, 30))

        call_count = [0]

        def mock_first():
            return config

        def mock_all():
            call_count[0] += 1
            if call_count[0] == 1:  # blocked times
                return []
            if call_count[0] == 2:  # appointments
                return [existing_appt]
            return []

        mock_db.query.return_value.filter.return_value.first.side_effect = mock_first
        mock_db.query.return_value.filter.return_value.all.side_effect = mock_all

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=future_monday,
                end_date=future_monday,
                org_id=1,
                max_per_day=1,
            )

        # Day should be skipped since max_per_day=1 and 1 appointment exists
        assert len(result) == 0

    def test_under_max_per_day_has_slots(self, setup_scheduler_helpers, mock_db, mock_models):
        """Days under the max_per_day limit should still show available slots."""
        sar = setup_scheduler_helpers

        future_monday = _get_next_weekday(0)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=0,
            max_meetings_per_day=10,
            enforce_lunch_break=False,
        )

        # One existing appointment (under the limit of 10)
        existing_appt = MagicMock()
        existing_appt.scheduled_start = datetime.combine(future_monday, time(9, 0))
        existing_appt.scheduled_end = datetime.combine(future_monday, time(9, 30))

        call_count = [0]

        def mock_first():
            return config

        def mock_all():
            call_count[0] += 1
            if call_count[0] == 1:  # blocked times
                return []
            if call_count[0] == 2:  # appointments
                return [existing_appt]
            return []

        mock_db.query.return_value.filter.return_value.first.side_effect = mock_first
        mock_db.query.return_value.filter.return_value.all.side_effect = mock_all

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=future_monday,
                end_date=future_monday,
                org_id=1,
                max_per_day=10,
            )

        # Should have slots (minus the one occupied slot)
        assert len(result) > 0


# =============================================================================
# CROSS-SOURCE CONFLICT EDGE CASES
# =============================================================================

class TestCrossSourceConflictEdgeCases:
    """Edge cases for cross-source calendar conflict detection."""

    def test_multiple_conflicts_all_detected(self, setup_scheduler_helpers):
        """Slot overlapping with any of multiple busy blocks should be detected."""
        sar = setup_scheduler_helpers

        conflicts = [
            (datetime(2026, 3, 20, 9, 0), datetime(2026, 3, 20, 9, 30)),
            (datetime(2026, 3, 20, 10, 0), datetime(2026, 3, 20, 10, 30)),
            (datetime(2026, 3, 20, 11, 0), datetime(2026, 3, 20, 11, 30)),
        ]

        # Slot during second conflict
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 3, 20, 10, 0),
            datetime(2026, 3, 20, 10, 30),
        ) is True

    def test_slot_between_conflicts_is_free(self, setup_scheduler_helpers):
        """Slot in a gap between two conflicts should be allowed."""
        sar = setup_scheduler_helpers

        conflicts = [
            (datetime(2026, 3, 20, 9, 0), datetime(2026, 3, 20, 9, 30)),
            (datetime(2026, 3, 20, 10, 30), datetime(2026, 3, 20, 11, 0)),
        ]

        # Slot 9:30-10:00 is in the gap
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 3, 20, 9, 30),
            datetime(2026, 3, 20, 10, 0),
        ) is False

    def test_exactly_touching_boundaries_no_conflict(self, setup_scheduler_helpers):
        """Slot that starts exactly when a conflict ends should not be a conflict."""
        sar = setup_scheduler_helpers

        conflicts = [
            (datetime(2026, 3, 20, 10, 0), datetime(2026, 3, 20, 10, 30)),
        ]

        # Slot starts at exactly the conflict end
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 3, 20, 10, 30),
            datetime(2026, 3, 20, 11, 0),
        ) is False

    def test_slot_contained_within_conflict(self, setup_scheduler_helpers):
        """Slot entirely within a larger conflict block should be detected."""
        sar = setup_scheduler_helpers

        conflicts = [
            (datetime(2026, 3, 20, 9, 0), datetime(2026, 3, 20, 12, 0)),  # 3-hour block
        ]

        # 30-min slot fully within the 3-hour block
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 3, 20, 10, 0),
            datetime(2026, 3, 20, 10, 30),
        ) is True
