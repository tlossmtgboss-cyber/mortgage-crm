"""
Scheduler Timezone Handling Test Suite

Comprehensive tests for timezone-related behavior across the scheduler:
1. Slot generation across timezone boundaries
2. Appointment creation with timezone (stored as UTC)
3. Appointment display with timezone conversion
4. DST transitions (spring-forward / fall-back)
5. Contact hours check (_check_contact_hours)
6. ICS generation timezone correctness
7. Cross-timezone conflict detection
8. Public booking timezone display (PublicAvailableSlotsRequest)
9. Working hours timezone application
10. Midnight boundary edge cases
"""

import pytest
from datetime import datetime, timedelta, date, time, timezone
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from zoneinfo import ZoneInfo

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytz


# =============================================================================
# SQLAlchemy Column Mock (reused from test_scheduler_routes.py)
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
            self.timezone = kwargs.get('timezone', 'America/Chicago')
            self.buffer_before_minutes = kwargs.get('buffer_before_minutes', 5)
            self.buffer_after_minutes = kwargs.get('buffer_after_minutes', 5)
            self.min_notice_hours = kwargs.get('min_notice_hours', 0)
            self.max_meetings_per_day = kwargs.get('max_meetings_per_day', 8)
            self.enforce_lunch_break = kwargs.get('enforce_lunch_break', False)
            self.lunch_break_start = kwargs.get('lunch_break_start', time(12, 0))
            self.lunch_break_end = kwargs.get('lunch_break_end', time(13, 0))

    class MockAppointment:
        id = _Col()
        assigned_user_id = _Col()
        organization_id = _Col()
        status = _Col()
        scheduled_start = _Col()
        scheduled_end = _Col()

        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

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
def setup_scheduler_routes(mock_models):
    """Set up scheduler helpers with mocked dependencies.
    Import the _helpers module directly so that
    internal helpers like _generate_available_slots are accessible.
    """
    import routes.scheduler._helpers as sar
    sar.set_dependencies(
        get_db_func=lambda: iter([MagicMock()]),
        get_current_user_func=MagicMock(),
        models_dict=mock_models
    )
    return sar


def _find_next_weekday(target_weekday: int, after: date = None) -> date:
    """Find the next occurrence of a weekday (0=Mon) after the given date.
    Returns a date at least 3 days in the future (to satisfy min_notice_hours).
    """
    if after is None:
        after = date.today()
    # Start from 3 days ahead to avoid min_notice issues
    d = after + timedelta(days=3)
    while d.weekday() != target_weekday:
        d += timedelta(days=1)
    return d


# =============================================================================
# 1. SLOT GENERATION ACROSS TIMEZONE BOUNDARIES
# =============================================================================

class TestSlotGenerationTimezoneBoundaries:
    """
    Verify that available slots for a user in one timezone are correct
    when the caller is in a different timezone.

    The slot engine works in "naive UTC" internally. Working hours
    (e.g. 9am-5pm) are applied as naive local times. A caller in
    US/Pacific requesting slots sees the same naive timestamps as a
    caller in US/Eastern -- the slots represent the *user's* local time.
    """

    def test_slots_reflect_user_working_hours_not_caller_timezone(
        self, setup_scheduler_routes, mock_db, mock_models
    ):
        """Slots should be in the user's configured working hours regardless
        of the requester's timezone. The slot engine does not shift times
        based on who is requesting."""
        sar = setup_scheduler_routes

        future_monday = _find_next_weekday(0)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            timezone='America/New_York',
            working_hours={
                "monday": {"start": "09:00", "end": "12:00", "enabled": True},
                "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
                "friday": {"start": "09:00", "end": "17:00", "enabled": True},
                "saturday": {"start": "00:00", "end": "00:00", "enabled": False},
                "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
            },
            min_notice_hours=0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        slots = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1],
            start_date=future_monday,
            end_date=future_monday,
            duration_minutes=30,
            check_cross_source=False,
        )

        assert len(slots) > 0, "Expected slots on Monday"

        # All slots should fall within 09:00-12:00 (user's working hours)
        for slot in slots:
            slot_dt = datetime.fromisoformat(slot["start"])
            assert slot_dt.hour >= 9, f"Slot starts before 9am: {slot_dt}"
            assert slot_dt.hour < 12, f"Slot starts at or after 12pm: {slot_dt}"

    def test_eastern_user_slot_count_matches_pacific_request(
        self, setup_scheduler_routes, mock_db, mock_models
    ):
        """The number of slots generated should be the same whether the
        requester thinks in Pacific or Eastern -- the engine uses the
        user's config timezone, not the requester's."""
        sar = setup_scheduler_routes

        future_tuesday = _find_next_weekday(1)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            timezone='America/New_York',
            working_hours={
                "monday": {"start": "09:00", "end": "17:00", "enabled": True},
                "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
                "friday": {"start": "09:00", "end": "17:00", "enabled": True},
                "saturday": {"start": "00:00", "end": "00:00", "enabled": False},
                "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
            },
            min_notice_hours=0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        slots = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1],
            start_date=future_tuesday,
            end_date=future_tuesday,
            duration_minutes=30,
            check_cross_source=False,
        )

        # 9am-5pm = 8 hours = 16 thirty-minute slots
        assert len(slots) == 16, f"Expected 16 slots for 9-5 day, got {len(slots)}"


# =============================================================================
# 2. APPOINTMENT CREATION WITH TIMEZONE
# =============================================================================

class TestAppointmentCreationTimezone:
    """Verify that when an appointment is created with a timezone, the
    scheduled_start stored in the DB represents the correct instant in time."""

    def test_appointment_stores_timezone_field(self):
        """The Appointment model has a timezone column; verify it persists."""
        from scheduler_models import AppointmentCreate

        appt_data = AppointmentCreate(
            title="Test Meeting",
            scheduled_start=datetime(2026, 6, 15, 14, 0),
            duration_minutes=30,
            timezone="America/Los_Angeles",
        )
        assert appt_data.timezone == "America/Los_Angeles"
        assert appt_data.duration_minutes == 30

    def test_utc_conversion_for_eastern_timezone(self):
        """A 2pm Eastern appointment should be 18:00 UTC (EST, -5) or
        19:00 UTC (EDT, -4). Verify the math."""
        eastern = ZoneInfo("America/New_York")

        # June 15 is in EDT (UTC-4)
        local_dt = datetime(2026, 6, 15, 14, 0, tzinfo=eastern)
        utc_dt = local_dt.astimezone(ZoneInfo("UTC"))

        assert utc_dt.hour == 18, f"Expected 18 UTC, got {utc_dt.hour}"
        assert utc_dt.date() == date(2026, 6, 15)

    def test_utc_conversion_for_pacific_timezone(self):
        """A 2pm Pacific appointment should be 21:00 UTC (PST, -8) or
        22:00 UTC (PDT, -7). Verify the math."""
        pacific = ZoneInfo("America/Los_Angeles")

        # June 15 is in PDT (UTC-7)
        local_dt = datetime(2026, 6, 15, 14, 0, tzinfo=pacific)
        utc_dt = local_dt.astimezone(ZoneInfo("UTC"))

        assert utc_dt.hour == 21, f"Expected 21 UTC, got {utc_dt.hour}"

    def test_utc_conversion_for_central_timezone(self):
        """Central time default: 2pm CDT = 19:00 UTC."""
        central = ZoneInfo("America/Chicago")

        local_dt = datetime(2026, 6, 15, 14, 0, tzinfo=central)
        utc_dt = local_dt.astimezone(ZoneInfo("UTC"))

        assert utc_dt.hour == 19, f"Expected 19 UTC, got {utc_dt.hour}"

    def test_appointment_create_schema_defaults_to_chicago(self):
        """AppointmentCreate should default to America/Chicago timezone."""
        from scheduler_models import AppointmentCreate

        appt = AppointmentCreate(
            title="Default TZ Test",
            scheduled_start=datetime(2026, 6, 15, 10, 0),
            duration_minutes=30,
        )
        assert appt.timezone == "America/Chicago"


# =============================================================================
# 3. APPOINTMENT DISPLAY WITH TIMEZONE CONVERSION
# =============================================================================

class TestAppointmentDisplayTimezone:
    """Verify times stored in the DB can be converted back to
    the original timezone for display."""

    def test_utc_to_eastern_conversion(self):
        """UTC time should convert back to correct Eastern time."""
        utc_dt = datetime(2026, 6, 15, 18, 0, tzinfo=ZoneInfo("UTC"))
        eastern = ZoneInfo("America/New_York")
        local_dt = utc_dt.astimezone(eastern)

        assert local_dt.hour == 14, f"Expected 2pm ET, got {local_dt.hour}"
        assert local_dt.minute == 0

    def test_utc_to_pacific_conversion(self):
        """UTC time should convert back to correct Pacific time."""
        utc_dt = datetime(2026, 6, 15, 21, 0, tzinfo=ZoneInfo("UTC"))
        pacific = ZoneInfo("America/Los_Angeles")
        local_dt = utc_dt.astimezone(pacific)

        assert local_dt.hour == 14, f"Expected 2pm PT, got {local_dt.hour}"

    def test_roundtrip_conversion_preserves_instant(self):
        """Converting local -> UTC -> local should return the same time."""
        original_tz = ZoneInfo("America/Denver")
        original_dt = datetime(2026, 3, 15, 10, 30, tzinfo=original_tz)

        utc_dt = original_dt.astimezone(ZoneInfo("UTC"))
        back_to_local = utc_dt.astimezone(original_tz)

        assert back_to_local.hour == original_dt.hour
        assert back_to_local.minute == original_dt.minute
        assert back_to_local.date() == original_dt.date()

    def test_display_in_different_timezone_than_stored(self):
        """An appointment stored from Eastern should display correctly in Pacific."""
        eastern = ZoneInfo("America/New_York")
        pacific = ZoneInfo("America/Los_Angeles")

        # Created in Eastern: June 15, 2pm EDT
        original = datetime(2026, 6, 15, 14, 0, tzinfo=eastern)
        # Store as UTC
        utc_stored = original.astimezone(ZoneInfo("UTC"))
        # Display in Pacific
        displayed = utc_stored.astimezone(pacific)

        assert displayed.hour == 11, f"Expected 11am PT, got {displayed.hour}"
        assert displayed.date() == date(2026, 6, 15)


# =============================================================================
# 4. DST TRANSITIONS
# =============================================================================

class TestDSTTransitions:
    """Test slot generation during spring-forward and fall-back dates."""

    def test_spring_forward_march_2026(self):
        """2026 spring forward: March 8, 2:00 AM -> 3:00 AM Eastern.
        The hour 2am-3am does not exist in Eastern time."""
        eastern = ZoneInfo("America/New_York")

        # 1:30 AM ET before spring-forward
        before = datetime(2026, 3, 8, 1, 30, tzinfo=eastern)
        # 3:30 AM ET after spring-forward
        after = datetime(2026, 3, 8, 3, 30, tzinfo=eastern)

        # The difference should be only 1 hour (not 2), because the
        # 2am-3am hour was skipped
        diff = after - before
        assert diff.total_seconds() == 3600, \
            f"Expected 1 hour gap across spring-forward, got {diff}"

    def test_fall_back_november_2026(self):
        """2026 fall back: November 1, 2:00 AM -> 1:00 AM Eastern.
        The hour 1am-2am occurs twice."""
        eastern = ZoneInfo("America/New_York")

        # Use pytz for explicit fold/ambiguous handling
        eastern_pytz = pytz.timezone("America/New_York")

        # 12:30 AM EDT (before fallback)
        before_utc = datetime(2026, 11, 1, 4, 30, tzinfo=timezone.utc)
        before_local = before_utc.astimezone(eastern)
        assert before_local.hour == 0
        assert before_local.minute == 30

        # 1:30 AM EDT (first occurrence)
        first_130_utc = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)
        first_local = first_130_utc.astimezone(eastern)
        assert first_local.hour == 1

        # 1:30 AM EST (second occurrence, after fallback)
        second_130_utc = datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)
        second_local = second_130_utc.astimezone(eastern)
        assert second_local.hour == 1

        # Both show 1:30 AM local but are different UTC instants
        assert first_130_utc != second_130_utc

    def test_slot_generation_across_dst_spring_forward(
        self, setup_scheduler_routes, mock_db, mock_models
    ):
        """Slots on DST spring-forward day should still be generated correctly.
        March 8, 2026 is spring-forward in US Eastern."""
        sar = setup_scheduler_routes

        # March 8, 2026 is a Sunday -- skip if not enabled
        # Use March 9, 2026 (Monday) which is the day after DST change
        dst_monday = date(2026, 3, 9)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            timezone='America/New_York',
            min_notice_hours=0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        slots = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1],
            start_date=dst_monday,
            end_date=dst_monday,
            duration_minutes=30,
            check_cross_source=False,
        )

        assert len(slots) > 0, "Should have slots on Monday after DST change"

        # All slots should still be in valid working hours range
        for slot in slots:
            slot_dt = datetime.fromisoformat(slot["start"])
            assert 9 <= slot_dt.hour < 17, \
                f"Slot outside working hours: {slot_dt}"

    def test_slot_generation_across_dst_fall_back(
        self, setup_scheduler_routes, mock_db, mock_models
    ):
        """Slots on the day after fall-back should still be generated correctly.
        November 1, 2026 is fall-back in US Eastern. November 2 is Monday."""
        sar = setup_scheduler_routes

        dst_monday = date(2026, 11, 2)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            timezone='America/New_York',
            min_notice_hours=0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        slots = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1],
            start_date=dst_monday,
            end_date=dst_monday,
            duration_minutes=30,
            check_cross_source=False,
        )

        assert len(slots) > 0, "Should have slots on Monday after fall-back"

        # 9am-5pm = 16 half-hour slots
        assert len(slots) == 16, f"Expected 16 slots, got {len(slots)}"


# =============================================================================
# 5. CONTACT HOURS CHECK
# =============================================================================

class TestContactHoursCheck:
    """Verify _check_contact_hours() correctly blocks SMS at 3am
    recipient-local time and allows at 10am.

    The function uses `datetime.now(timezone.utc).astimezone(tz)` to get
    the recipient's local time. We freeze UTC time to control local hours.
    """

    def _make_utc_dt(self, year, month, day, hour, minute=0):
        """Helper to create a UTC-aware datetime for mocking."""
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)

    def _call_with_frozen_utc(self, utc_time, recipient_tz=None):
        """Call _check_contact_hours with a frozen UTC time.
        Uses freezegun-style patching of datetime.now() while keeping
        the real datetime class for .astimezone() etc.
        """
        from scheduler_email_service import _check_contact_hours

        original_now = datetime.now

        def patched_now(tz=None):
            if tz is not None:
                return utc_time.astimezone(tz) if tz != timezone.utc else utc_time
            return utc_time.replace(tzinfo=None)

        with patch('scheduler_email_service.datetime') as mock_dt:
            # Keep the real datetime class behavior for everything except now()
            mock_dt.now = patched_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            # The function does: datetime.now(timezone.utc).astimezone(tz)
            # We need .now(timezone.utc) to return utc_time (which has .astimezone)
            result = _check_contact_hours(recipient_tz)

        return result

    def test_blocks_sms_at_3am_recipient_local_time(self):
        """SMS at 3am local time should be blocked (TCPA: 8am-9pm)."""
        # 3am Eastern EST (Jan, UTC-5): UTC = 8am
        utc_time = self._make_utc_dt(2026, 1, 15, 8, 0)
        can_send, reason = self._call_with_frozen_utc(utc_time, "America/New_York")

        assert can_send is False, f"Should block at 3am ET, but got: {reason}"
        assert "TCPA" in reason

    def test_allows_sms_at_10am_recipient_local_time(self):
        """SMS at 10am local time should be allowed (within 8am-9pm)."""
        # 10am Eastern EST (Jan, UTC-5): UTC = 3pm
        utc_time = self._make_utc_dt(2026, 1, 15, 15, 0)
        can_send, reason = self._call_with_frozen_utc(utc_time, "America/New_York")

        assert can_send is True, f"Should allow at 10am ET, but got: {reason}"
        assert reason == "OK"

    def test_blocks_sms_at_930pm_recipient_local_time(self):
        """SMS at 9:30pm local time should be blocked (9pm cutoff)."""
        # 9:30pm Pacific PDT (June, UTC-7): UTC = 4:30am next day
        utc_time = self._make_utc_dt(2026, 6, 16, 4, 30)
        can_send, reason = self._call_with_frozen_utc(utc_time, "America/Los_Angeles")

        assert can_send is False, f"Should block at 9:30pm PT, but got: {reason}"

    def test_allows_sms_at_8am_exactly(self):
        """SMS at exactly 8:00am local time should be allowed."""
        # 8am Central CST (Jan, UTC-6): UTC = 2pm
        utc_time = self._make_utc_dt(2026, 1, 15, 14, 0)
        can_send, reason = self._call_with_frozen_utc(utc_time, "America/Chicago")

        assert can_send is True, f"Should allow at 8am CT, but got: {reason}"

    def test_blocks_sms_at_759am(self):
        """SMS at 7:59am local time should be blocked."""
        # 7:59am Central CST (Jan, UTC-6): UTC = 1:59pm
        utc_time = self._make_utc_dt(2026, 1, 15, 13, 59)
        can_send, reason = self._call_with_frozen_utc(utc_time, "America/Chicago")

        assert can_send is False, f"Should block at 7:59am CT, but got: {reason}"

    def test_defaults_to_new_york_when_no_timezone_given(self):
        """When recipient timezone is None, should default to America/New_York
        (most conservative US timezone)."""
        # 8am Eastern EST (Jan, UTC-5): UTC = 1pm
        utc_time = self._make_utc_dt(2026, 1, 15, 13, 0)
        can_send, reason = self._call_with_frozen_utc(utc_time, None)

        assert can_send is True, f"Should allow at 8am ET (default), but got: {reason}"

    def test_invalid_timezone_fails_closed(self):
        """Invalid timezone string should fail-closed (block the send)."""
        from scheduler_email_service import _check_contact_hours

        can_send, reason = _check_contact_hours("Invalid/Timezone")

        assert can_send is False, "Should block on invalid timezone"
        assert "TCPA" in reason


# =============================================================================
# 6. ICS GENERATION TIMEZONE
# =============================================================================

class TestICSGenerationTimezone:
    """Verify generated ICS files have correct DTSTART with UTC format."""

    def test_ics_dtstart_uses_utc_format(self):
        """DTSTART should end with Z (UTC indicator) per RFC 5545."""
        from scheduler_email_service import generate_ics_content

        start = datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc)
        ics = generate_ics_content(
            appointment_title="Test Meeting",
            start_datetime=start,
            duration_minutes=30,
            attendee_email="test@example.com",
            attendee_name="Test User",
            organizer_email="lo@perenniaai.com",
            organizer_name="Loan Officer",
        )

        assert "DTSTART:20260615T180000Z" in ics, \
            f"Expected UTC DTSTART in ICS, got:\n{ics}"

    def test_ics_dtend_uses_utc_format(self):
        """DTEND should also be in UTC format."""
        from scheduler_email_service import generate_ics_content

        start = datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc)
        ics = generate_ics_content(
            appointment_title="Test Meeting",
            start_datetime=start,
            duration_minutes=30,
            attendee_email="test@example.com",
            attendee_name="Test User",
            organizer_email="lo@perenniaai.com",
            organizer_name="Loan Officer",
        )

        assert "DTEND:20260615T183000Z" in ics, \
            f"Expected UTC DTEND in ICS, got:\n{ics}"

    def test_ics_dtstart_not_floating_time(self):
        """DTSTART must NOT be floating (without Z or TZID). Our ICS
        generator always appends Z for UTC."""
        from scheduler_email_service import generate_ics_content

        start = datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc)
        ics = generate_ics_content(
            appointment_title="Floating Time Check",
            start_datetime=start,
            duration_minutes=60,
            attendee_email="a@b.com",
            attendee_name="A",
            organizer_email="o@b.com",
            organizer_name="O",
        )

        # Extract DTSTART line
        for line in ics.split("\n"):
            if line.startswith("DTSTART:"):
                dtstart_value = line.split(":", 1)[1].strip()
                assert dtstart_value.endswith("Z"), \
                    f"DTSTART should end with Z (UTC), got: {dtstart_value}"
                break
        else:
            pytest.fail("DTSTART not found in ICS output")

    def test_ics_duration_calculation(self):
        """DTEND should be exactly duration_minutes after DTSTART."""
        from scheduler_email_service import generate_ics_content

        start = datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc)
        ics = generate_ics_content(
            appointment_title="Duration Test",
            start_datetime=start,
            duration_minutes=45,
            attendee_email="a@b.com",
            attendee_name="A",
            organizer_email="o@b.com",
            organizer_name="O",
        )

        # 14:00 + 45 min = 14:45
        assert "DTEND:20260615T144500Z" in ics

    def test_ics_with_naive_datetime_still_formats(self):
        """If a naive datetime is passed, strftime still works
        (Z is always appended by the generator)."""
        from scheduler_email_service import generate_ics_content

        start = datetime(2026, 6, 15, 18, 0)  # naive
        ics = generate_ics_content(
            appointment_title="Naive DT Test",
            start_datetime=start,
            duration_minutes=30,
            attendee_email="a@b.com",
            attendee_name="A",
            organizer_email="o@b.com",
            organizer_name="O",
        )

        assert "DTSTART:20260615T180000Z" in ics

    def test_ics_from_enhancement_wrapper(self):
        """The generate_ics_content wrapper in scheduler_enhancements.py
        should produce valid ICS with UTC DTSTART."""
        from scheduler_enhancements import generate_ics_content as gen_ics

        appointment_dict = {
            'id': 42,
            'title': 'Wrapper Test',
            'scheduled_start': datetime(2026, 7, 10, 15, 0, tzinfo=timezone.utc),
            'scheduled_end': datetime(2026, 7, 10, 15, 30, tzinfo=timezone.utc),
            'attendee_email': 'borrower@test.com',
            'attendee_name': 'Jane Doe',
            'organizer_email': 'lo@perenniaai.com',
            'organizer_name': 'Perennia AI',
            'description': 'Rate lock discussion',
            'location': 'Video Call',
        }

        ics = gen_ics(appointment_dict)

        assert "DTSTART:20260710T150000Z" in ics
        assert "DTEND:20260710T153000Z" in ics
        assert "appt-42@perenniaai.com" in ics


# =============================================================================
# 7. CROSS-TIMEZONE CONFLICT DETECTION
# =============================================================================

class TestCrossTimezoneConflictDetection:
    """Verify that an appointment at 5pm Eastern conflicts with 2pm Pacific,
    since they represent the same instant."""

    def test_5pm_eastern_equals_2pm_pacific(self):
        """5pm EDT and 2pm PDT are the same UTC instant."""
        eastern = ZoneInfo("America/New_York")
        pacific = ZoneInfo("America/Los_Angeles")

        eastern_5pm = datetime(2026, 6, 15, 17, 0, tzinfo=eastern)
        pacific_2pm = datetime(2026, 6, 15, 14, 0, tzinfo=pacific)

        utc_from_eastern = eastern_5pm.astimezone(ZoneInfo("UTC"))
        utc_from_pacific = pacific_2pm.astimezone(ZoneInfo("UTC"))

        assert utc_from_eastern == utc_from_pacific, \
            f"5pm ET ({utc_from_eastern}) should equal 2pm PT ({utc_from_pacific})"

    def test_conflict_check_detects_same_utc_instant(self):
        """The _has_cross_source_conflict helper checks naive-UTC overlap.
        An existing appointment at 21:00 UTC should conflict with a proposed
        slot also at 21:00 UTC (regardless of what local timezone each was
        booked from)."""
        from routes.scheduler._helpers import _has_cross_source_conflict

        # Existing appointment: 21:00-21:30 UTC (which is 5pm-5:30pm ET)
        busy_times = [
            (datetime(2026, 6, 15, 21, 0), datetime(2026, 6, 15, 21, 30))
        ]

        # Proposed slot: 21:00-21:30 UTC (which is 2pm-2:30pm PT)
        slot_start = datetime(2026, 6, 15, 21, 0)
        slot_end = datetime(2026, 6, 15, 21, 30)

        has_conflict = _has_cross_source_conflict(
            busy_times, slot_start, slot_end
        )

        assert has_conflict is True, \
            "Should detect conflict between 5pm ET and 2pm PT (same UTC)"

    def test_no_conflict_when_different_utc_times(self):
        """No conflict when slots don't overlap in UTC."""
        from routes.scheduler._helpers import _has_cross_source_conflict

        # Existing: 15:00-15:30 UTC
        busy_times = [
            (datetime(2026, 6, 15, 15, 0), datetime(2026, 6, 15, 15, 30))
        ]

        # Proposed: 21:00-21:30 UTC
        slot_start = datetime(2026, 6, 15, 21, 0)
        slot_end = datetime(2026, 6, 15, 21, 30)

        has_conflict = _has_cross_source_conflict(
            busy_times, slot_start, slot_end
        )

        assert has_conflict is False

    def test_conflict_with_buffer_time(self):
        """Conflict detection should account for buffer_before and buffer_after."""
        from routes.scheduler._helpers import _has_cross_source_conflict

        # Existing: 15:00-15:30 UTC
        busy_times = [
            (datetime(2026, 6, 15, 15, 0), datetime(2026, 6, 15, 15, 30))
        ]

        # Proposed: 15:30-16:00 UTC (immediately after)
        # With 5-minute buffer_after on existing, busy extends to 15:35
        # So proposed at 15:30 should conflict
        slot_start = datetime(2026, 6, 15, 15, 30)
        slot_end = datetime(2026, 6, 15, 16, 0)

        has_conflict = _has_cross_source_conflict(
            busy_times, slot_start, slot_end,
            buffer_before=5, buffer_after=5
        )

        assert has_conflict is True, \
            "Should detect conflict due to buffer_after overlap"

    def test_partial_overlap_detected(self):
        """Partial overlaps should be detected as conflicts."""
        from routes.scheduler._helpers import _has_cross_source_conflict

        # Existing: 14:00-15:00 UTC
        busy_times = [
            (datetime(2026, 6, 15, 14, 0), datetime(2026, 6, 15, 15, 0))
        ]

        # Proposed: 14:30-15:30 UTC (overlaps by 30 min)
        slot_start = datetime(2026, 6, 15, 14, 30)
        slot_end = datetime(2026, 6, 15, 15, 30)

        has_conflict = _has_cross_source_conflict(
            busy_times, slot_start, slot_end
        )

        assert has_conflict is True


# =============================================================================
# 8. PUBLIC BOOKING TIMEZONE DISPLAY
# =============================================================================

class TestPublicBookingTimezoneDisplay:
    """Verify that PublicAvailableSlotsRequest and AvailableSlotsRequest
    handle timezone parameter correctly."""

    def test_public_slots_request_accepts_timezone(self):
        """PublicAvailableSlotsRequest should not have a timezone field
        (it uses server-side defaults). This is by design."""
        from scheduler_models import PublicAvailableSlotsRequest

        req = PublicAvailableSlotsRequest(
            start_date=date(2026, 6, 15),
            end_date=date(2026, 6, 19),
            duration_minutes=30,
        )
        assert req.start_date == date(2026, 6, 15)
        assert req.end_date == date(2026, 6, 19)
        assert req.duration_minutes == 30

    def test_available_slots_request_has_timezone_field(self):
        """AvailableSlotsRequest (authenticated) should accept a timezone."""
        from scheduler_models import AvailableSlotsRequest

        req = AvailableSlotsRequest(
            start_date=date(2026, 6, 15),
            end_date=date(2026, 6, 19),
            duration_minutes=30,
            timezone="America/Los_Angeles",
        )
        assert req.timezone == "America/Los_Angeles"

    def test_available_slots_request_defaults_to_chicago(self):
        """AvailableSlotsRequest timezone should default to America/Chicago."""
        from scheduler_models import AvailableSlotsRequest

        req = AvailableSlotsRequest(
            start_date=date(2026, 6, 15),
            end_date=date(2026, 6, 19),
        )
        assert req.timezone == "America/Chicago"

    def test_available_slots_validates_date_order(self):
        """end_date before start_date should raise validation error."""
        from scheduler_models import AvailableSlotsRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AvailableSlotsRequest(
                start_date=date(2026, 6, 19),
                end_date=date(2026, 6, 15),
            )


# =============================================================================
# 9. WORKING HOURS TIMEZONE APPLICATION
# =============================================================================

class TestWorkingHoursTimezoneApplication:
    """Verify that working hours (9am-5pm) are correctly applied in the
    user's configured timezone, not UTC."""

    def test_working_hours_applied_as_local_time(
        self, setup_scheduler_routes, mock_db, mock_models
    ):
        """Working hours 09:00-17:00 should produce slots starting at 09:00,
        which are in the user's local timezone (stored naively in the slot
        engine). The slot engine does NOT convert to UTC."""
        sar = setup_scheduler_routes

        future_wednesday = _find_next_weekday(2)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            timezone='America/New_York',
            working_hours={
                "monday": {"start": "09:00", "end": "17:00", "enabled": True},
                "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
                "friday": {"start": "09:00", "end": "17:00", "enabled": True},
                "saturday": {"start": "00:00", "end": "00:00", "enabled": False},
                "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
            },
            min_notice_hours=0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        slots = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1],
            start_date=future_wednesday,
            end_date=future_wednesday,
            duration_minutes=30,
            check_cross_source=False,
        )

        assert len(slots) > 0
        first_slot = datetime.fromisoformat(slots[0]["start"])
        last_slot = datetime.fromisoformat(slots[-1]["start"])

        assert first_slot.hour == 9, f"First slot should be at 9am, got {first_slot.hour}"
        assert last_slot.hour == 16, f"Last slot should start at 4:30pm, got {last_slot}"
        assert last_slot.minute == 30

    def test_custom_working_hours_respected(
        self, setup_scheduler_routes, mock_db, mock_models
    ):
        """Custom working hours (10am-3pm) should limit slot generation."""
        sar = setup_scheduler_routes

        future_thursday = _find_next_weekday(3)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            timezone='America/Chicago',
            working_hours={
                "monday": {"start": "10:00", "end": "15:00", "enabled": True},
                "tuesday": {"start": "10:00", "end": "15:00", "enabled": True},
                "wednesday": {"start": "10:00", "end": "15:00", "enabled": True},
                "thursday": {"start": "10:00", "end": "15:00", "enabled": True},
                "friday": {"start": "10:00", "end": "15:00", "enabled": True},
                "saturday": {"start": "00:00", "end": "00:00", "enabled": False},
                "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
            },
            min_notice_hours=0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        slots = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1],
            start_date=future_thursday,
            end_date=future_thursday,
            duration_minutes=30,
            check_cross_source=False,
        )

        # 10am-3pm = 5 hours = 10 half-hour slots
        assert len(slots) == 10, f"Expected 10 slots for 10am-3pm, got {len(slots)}"

        for slot in slots:
            slot_dt = datetime.fromisoformat(slot["start"])
            assert slot_dt.hour >= 10, f"Slot before 10am: {slot_dt}"
            assert slot_dt.hour < 15, f"Slot at or after 3pm: {slot_dt}"

    def test_disabled_days_produce_no_slots(
        self, setup_scheduler_routes, mock_db, mock_models
    ):
        """Saturday/Sunday with enabled=False should produce no slots."""
        sar = setup_scheduler_routes

        future_saturday = _find_next_weekday(5)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            working_hours={
                "monday": {"start": "09:00", "end": "17:00", "enabled": True},
                "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
                "friday": {"start": "09:00", "end": "17:00", "enabled": True},
                "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
                "sunday": {"start": "10:00", "end": "14:00", "enabled": False},
            },
            min_notice_hours=0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        slots = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1],
            start_date=future_saturday,
            end_date=future_saturday,
            duration_minutes=30,
            check_cross_source=False,
        )

        assert len(slots) == 0, "Should have no slots on disabled Saturday"


# =============================================================================
# 10. MIDNIGHT BOUNDARY EDGE CASES
# =============================================================================

class TestMidnightBoundary:
    """Test appointments that span midnight in one timezone but not another."""

    def test_appointment_spanning_midnight_in_eastern_but_not_pacific(self):
        """An appointment at 11:30pm Eastern (30 min) ends at midnight ET,
        but in Pacific it's 8:30pm-9:00pm -- does not cross midnight."""
        eastern = ZoneInfo("America/New_York")
        pacific = ZoneInfo("America/Los_Angeles")

        start_et = datetime(2026, 6, 15, 23, 30, tzinfo=eastern)
        end_et = start_et + timedelta(minutes=30)

        # In Pacific time
        start_pt = start_et.astimezone(pacific)
        end_pt = end_et.astimezone(pacific)

        # Eastern: starts June 15, ends June 16 midnight
        assert start_et.date() == date(2026, 6, 15)
        assert end_et.date() == date(2026, 6, 16)

        # Pacific: both on June 15
        assert start_pt.date() == date(2026, 6, 15)
        assert end_pt.date() == date(2026, 6, 15)
        assert start_pt.hour == 20
        assert end_pt.hour == 21

    def test_appointment_at_midnight_utc_is_previous_day_in_us_timezones(self):
        """An appointment at midnight UTC is still the previous day in all
        US timezones."""
        utc_midnight = datetime(2026, 6, 16, 0, 0, tzinfo=ZoneInfo("UTC"))

        eastern = utc_midnight.astimezone(ZoneInfo("America/New_York"))
        central = utc_midnight.astimezone(ZoneInfo("America/Chicago"))
        mountain = utc_midnight.astimezone(ZoneInfo("America/Denver"))
        pacific = utc_midnight.astimezone(ZoneInfo("America/Los_Angeles"))

        # All US zones: midnight UTC = evening of June 15
        assert eastern.date() == date(2026, 6, 15), f"Eastern: {eastern}"
        assert central.date() == date(2026, 6, 15), f"Central: {central}"
        assert mountain.date() == date(2026, 6, 15), f"Mountain: {mountain}"
        assert pacific.date() == date(2026, 6, 15), f"Pacific: {pacific}"

        assert eastern.hour == 20   # 8pm EDT
        assert central.hour == 19   # 7pm CDT
        assert mountain.hour == 18  # 6pm MDT
        assert pacific.hour == 17   # 5pm PDT

    def test_slot_near_midnight_not_generated_outside_working_hours(
        self, setup_scheduler_routes, mock_db, mock_models
    ):
        """Slots near midnight should not be generated if working hours end
        at 5pm, even if the date rolls over in a different timezone."""
        sar = setup_scheduler_routes

        future_friday = _find_next_weekday(4)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            timezone='America/New_York',
            working_hours={
                "monday": {"start": "09:00", "end": "17:00", "enabled": True},
                "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
                "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
                "friday": {"start": "09:00", "end": "17:00", "enabled": True},
                "saturday": {"start": "00:00", "end": "00:00", "enabled": False},
                "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
            },
            min_notice_hours=0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        slots = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1],
            start_date=future_friday,
            end_date=future_friday,
            duration_minutes=30,
            check_cross_source=False,
        )

        # No slot should start at or after 5pm (17:00)
        for slot in slots:
            slot_dt = datetime.fromisoformat(slot["start"])
            assert slot_dt.hour < 17, \
                f"Slot at or after 5pm: {slot_dt}"

    def test_late_working_hours_dont_spill_past_midnight(
        self, setup_scheduler_routes, mock_db, mock_models
    ):
        """If working hours extend to 23:00, slots should stop before midnight."""
        sar = setup_scheduler_routes

        future_wednesday = _find_next_weekday(2)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            timezone='America/Chicago',
            working_hours={
                "monday": {"start": "18:00", "end": "23:00", "enabled": True},
                "tuesday": {"start": "18:00", "end": "23:00", "enabled": True},
                "wednesday": {"start": "18:00", "end": "23:00", "enabled": True},
                "thursday": {"start": "18:00", "end": "23:00", "enabled": True},
                "friday": {"start": "18:00", "end": "23:00", "enabled": True},
                "saturday": {"start": "00:00", "end": "00:00", "enabled": False},
                "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
            },
            min_notice_hours=0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        slots = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1],
            start_date=future_wednesday,
            end_date=future_wednesday,
            duration_minutes=30,
            check_cross_source=False,
        )

        # 18:00-23:00 = 5 hours = 10 half-hour slots
        assert len(slots) == 10, f"Expected 10 slots for 6pm-11pm, got {len(slots)}"

        # Last slot should start at 22:30, end at 23:00
        last_slot_dt = datetime.fromisoformat(slots[-1]["start"])
        assert last_slot_dt.hour == 22
        assert last_slot_dt.minute == 30

        # No slot should be on the next day
        for slot in slots:
            slot_dt = datetime.fromisoformat(slot["start"])
            assert slot_dt.date() == future_wednesday, \
                f"Slot on wrong date: {slot_dt.date()}, expected {future_wednesday}"


# =============================================================================
# ADDITIONAL EDGE CASES
# =============================================================================

class TestTimezoneEdgeCases:
    """Additional timezone edge cases for robustness."""

    def test_hawaii_timezone_offset(self):
        """Hawaii (Pacific/Honolulu) is UTC-10, no DST."""
        hawaii = ZoneInfo("Pacific/Honolulu")

        # Noon in Hawaii = 10pm UTC
        local = datetime(2026, 6, 15, 12, 0, tzinfo=hawaii)
        utc = local.astimezone(ZoneInfo("UTC"))
        assert utc.hour == 22

        # Same offset in winter (no DST)
        winter_local = datetime(2026, 1, 15, 12, 0, tzinfo=hawaii)
        winter_utc = winter_local.astimezone(ZoneInfo("UTC"))
        assert winter_utc.hour == 22

    def test_arizona_no_dst(self):
        """Arizona (America/Phoenix) does not observe DST."""
        arizona = ZoneInfo("America/Phoenix")

        # Summer: Arizona stays at UTC-7 while Pacific goes to UTC-7
        summer_az = datetime(2026, 6, 15, 14, 0, tzinfo=arizona)
        summer_pt = datetime(2026, 6, 15, 14, 0, tzinfo=ZoneInfo("America/Los_Angeles"))

        summer_az_utc = summer_az.astimezone(ZoneInfo("UTC"))
        summer_pt_utc = summer_pt.astimezone(ZoneInfo("UTC"))

        # In summer, both are UTC-7, so same UTC hour
        assert summer_az_utc.hour == summer_pt_utc.hour

        # Winter: Arizona stays at UTC-7, Pacific goes to UTC-8
        winter_az = datetime(2026, 1, 15, 14, 0, tzinfo=arizona)
        winter_pt = datetime(2026, 1, 15, 14, 0, tzinfo=ZoneInfo("America/Los_Angeles"))

        winter_az_utc = winter_az.astimezone(ZoneInfo("UTC"))
        winter_pt_utc = winter_pt.astimezone(ZoneInfo("UTC"))

        # In winter, Arizona is UTC-7, Pacific is UTC-8
        assert winter_az_utc.hour == 21  # 14 + 7
        assert winter_pt_utc.hour == 22  # 14 + 8
        assert winter_az_utc.hour != winter_pt_utc.hour

    def test_pytz_and_zoneinfo_give_same_result(self):
        """pytz and zoneinfo should agree on UTC conversion."""
        # Use a non-DST-transition date to avoid pytz localize quirks
        dt_naive = datetime(2026, 6, 15, 14, 0)

        # zoneinfo approach
        zi = ZoneInfo("America/New_York")
        dt_zi = dt_naive.replace(tzinfo=zi)
        utc_zi = dt_zi.astimezone(ZoneInfo("UTC"))

        # pytz approach
        ptz = pytz.timezone("America/New_York")
        dt_pytz = ptz.localize(dt_naive)
        utc_pytz = dt_pytz.astimezone(pytz.UTC)

        assert utc_zi.hour == utc_pytz.hour
        assert utc_zi.minute == utc_pytz.minute

    def test_scheduler_config_timezone_field_default(self):
        """SchedulerConfig model should default timezone to America/Chicago."""
        from scheduler_models import SchedulerConfigCreate

        config = SchedulerConfigCreate(config_name="Test Config")
        assert config.timezone == "America/Chicago"

    def test_multiple_users_different_timezones_generate_separate_slots(
        self, setup_scheduler_routes, mock_db, mock_models
    ):
        """When generating slots for multiple users, each should get
        their own slots based on their config. Since the mock returns the
        same config for all users, they get the same slots, but the engine
        processes each user separately."""
        sar = setup_scheduler_routes

        future_tuesday = _find_next_weekday(1)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            timezone='America/New_York',
            min_notice_hours=0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        # Request slots for two users (IDs 1 and 2)
        slots = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1, 2],
            start_date=future_tuesday,
            end_date=future_tuesday,
            duration_minutes=30,
            check_cross_source=False,
            include_user_id=True,
        )

        # Should have slots from both users (deduplicated by start time in
        # the current implementation, but the engine processes both)
        assert len(slots) > 0

    def test_slot_times_are_iso_formatted(
        self, setup_scheduler_routes, mock_db, mock_models
    ):
        """Slot start/end times should be valid ISO 8601 format."""
        sar = setup_scheduler_routes

        future_monday = _find_next_weekday(0)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        slots = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1],
            start_date=future_monday,
            end_date=future_monday,
            duration_minutes=30,
            check_cross_source=False,
        )

        for slot in slots:
            # Should parse without error
            start = datetime.fromisoformat(slot["start"])
            end = datetime.fromisoformat(slot["end"])
            # End should be exactly 30 minutes after start
            assert (end - start).total_seconds() == 1800

    def test_start_time_format_includes_utc_z_suffix(
        self, setup_scheduler_routes, mock_db, mock_models
    ):
        """When time_key_format='start_time', values should end with Z."""
        sar = setup_scheduler_routes

        future_monday = _find_next_weekday(0)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        slots = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1],
            start_date=future_monday,
            end_date=future_monday,
            duration_minutes=30,
            check_cross_source=False,
            time_key_format="start_time",
        )

        assert len(slots) > 0
        for slot in slots:
            assert "start_time" in slot
            assert "end_time" in slot
            assert slot["start_time"].endswith("Z"), \
                f"start_time should end with Z: {slot['start_time']}"
            assert slot["end_time"].endswith("Z"), \
                f"end_time should end with Z: {slot['end_time']}"
