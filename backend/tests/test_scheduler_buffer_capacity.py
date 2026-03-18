"""
Integration tests for buffer time enforcement and daily capacity limits.

Tests the core scheduling invariants:
- Buffer times between appointments are respected in slot generation
- Daily booking capacity limits are enforced
- Protected time blocks (focus, lunch) are not bookable
"""

import pytest
from datetime import datetime, timedelta, date, time, timezone
from unittest.mock import MagicMock, patch
from collections import defaultdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# SQLAlchemy Column Mock (matches test_scheduler_edge_cases.py pattern)
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

def _get_next_weekday(target_weekday=0, weeks_ahead=1):
    """Get a future date for a specific weekday (0=Monday).
    Always at least `weeks_ahead` full weeks in the future to avoid min_notice_hours issues."""
    today = date.today()
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead + (weeks_ahead - 1) * 7)


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
            self.min_notice_hours = kwargs.get('min_notice_hours', 0)
            self.max_meetings_per_day = kwargs.get('max_meetings_per_day', 8)
            self.enforce_lunch_break = kwargs.get('enforce_lunch_break', False)
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


def _make_mock_appointment(scheduled_start, scheduled_end, user_id=1, org_id=1,
                           status_value="booked", booked_by_ai=False):
    """Create a mock appointment instance with the given time range."""
    appt = MagicMock()
    appt.assigned_user_id = user_id
    appt.organization_id = org_id
    appt.scheduled_start = scheduled_start
    appt.scheduled_end = scheduled_end
    appt.status = MagicMock()
    appt.status.value = status_value
    appt.booked_by_ai = booked_by_ai
    return appt


def _make_mock_blocked_time(start_dt, end_dt, user_id=1, org_id=1,
                            block_type="focus", applies_to_all=False):
    """Create a mock blocked time instance."""
    bt = MagicMock()
    bt.user_id = user_id
    bt.organization_id = org_id
    bt.start_datetime = start_dt
    bt.end_datetime = end_dt
    bt.block_type = block_type
    bt.is_active = True
    bt.applies_to_all_users = applies_to_all
    return bt


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


# =============================================================================
# BUFFER TIME ENFORCEMENT
# =============================================================================

class TestBufferTimeEnforcement:
    """Test that buffer times between appointments are respected in slot generation."""

    def test_buffer_before_respected(self, setup_scheduler_helpers, mock_db, mock_models):
        """Slots should not be generated within buffer_before_minutes of an existing appointment."""
        sar = setup_scheduler_helpers
        target_date = _get_next_weekday(0)  # Future Monday

        # Config: 15-min buffer before, 0 after, no lunch break
        config = mock_models['SchedulerConfig'](
            user_id=1,
            buffer_before_minutes=15,
            buffer_after_minutes=0,
            min_notice_hours=0,
            enforce_lunch_break=False,
        )

        # Existing appointment at 10:00-10:30
        existing_appt = _make_mock_appointment(
            datetime.combine(target_date, time(10, 0)),
            datetime.combine(target_date, time(10, 30)),
        )

        # Set up DB mocks
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = [existing_appt]

        # Override per-batch queries: config returns [config], blocked returns [],
        # appointments returns [existing_appt]
        call_count = [0]
        original_all = mock_db.query.return_value.filter.return_value.all

        def mock_all_side_effect():
            call_count[0] += 1
            # The batch queries are: configs, blocked_times, appointments
            # We rely on the order: first .all() = configs, second .all() = blocked,
            # third .all() = appointments
            if call_count[0] == 1:
                return [config]       # SchedulerConfig batch
            elif call_count[0] == 2:
                return []             # BlockedTime batch
            elif call_count[0] == 3:
                return [existing_appt]  # Appointment batch
            return []

        mock_db.query.return_value.filter.return_value.all.side_effect = mock_all_side_effect

        with patch.object(sar, '_get_cross_source_conflicts_batch', return_value={}):
            slots = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=target_date,
                end_date=target_date,
                org_id=1,
                check_cross_source=False,
            )

        # Verify no slots exist in the range [09:45, 10:30) -- the appointment itself
        # blocks 10:00-10:30 and buffer_before extends to 09:45
        for slot in slots:
            slot_start = datetime.fromisoformat(slot["start"])
            slot_end = datetime.fromisoformat(slot["end"])
            # The effective busy window is [09:45, 10:30]
            busy_start = datetime.combine(target_date, time(9, 45))
            busy_end = datetime.combine(target_date, time(10, 30))
            overlaps = slot_start < busy_end and slot_end > busy_start
            assert not overlaps, (
                f"Slot {slot['start']}-{slot['end']} should not overlap with "
                f"buffer zone {busy_start.isoformat()}-{busy_end.isoformat()}"
            )

    def test_buffer_after_respected(self, setup_scheduler_helpers, mock_db, mock_models):
        """Slots should not be generated within buffer_after_minutes after an existing appointment."""
        sar = setup_scheduler_helpers
        target_date = _get_next_weekday(0)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            buffer_before_minutes=0,
            buffer_after_minutes=15,
            min_notice_hours=0,
            enforce_lunch_break=False,
        )

        # Existing appointment at 10:00-10:30
        existing_appt = _make_mock_appointment(
            datetime.combine(target_date, time(10, 0)),
            datetime.combine(target_date, time(10, 30)),
        )

        call_count = [0]

        def mock_all_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return [config]
            elif call_count[0] == 2:
                return []
            elif call_count[0] == 3:
                return [existing_appt]
            return []

        mock_db.query.return_value.filter.return_value.all.side_effect = mock_all_side_effect

        with patch.object(sar, '_get_cross_source_conflicts_batch', return_value={}):
            slots = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=target_date,
                end_date=target_date,
                org_id=1,
                check_cross_source=False,
            )

        # Busy window: appointment 10:00-10:30, buffer_after extends to 10:45
        # No slot should start in [10:00, 10:45)
        for slot in slots:
            slot_start = datetime.fromisoformat(slot["start"])
            slot_end = datetime.fromisoformat(slot["end"])
            busy_start = datetime.combine(target_date, time(10, 0))
            busy_end = datetime.combine(target_date, time(10, 45))
            overlaps = slot_start < busy_end and slot_end > busy_start
            assert not overlaps, (
                f"Slot {slot['start']}-{slot['end']} should not overlap with "
                f"buffer zone {busy_start.isoformat()}-{busy_end.isoformat()}"
            )

    def test_zero_buffer_allows_adjacent(self, setup_scheduler_helpers, mock_db, mock_models):
        """With 0 buffer, back-to-back appointments should be allowed."""
        sar = setup_scheduler_helpers
        target_date = _get_next_weekday(0)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            buffer_before_minutes=0,
            buffer_after_minutes=0,
            min_notice_hours=0,
            enforce_lunch_break=False,
        )

        # Existing appointment at 10:00-10:30
        existing_appt = _make_mock_appointment(
            datetime.combine(target_date, time(10, 0)),
            datetime.combine(target_date, time(10, 30)),
        )

        call_count = [0]

        def mock_all_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return [config]
            elif call_count[0] == 2:
                return []
            elif call_count[0] == 3:
                return [existing_appt]
            return []

        mock_db.query.return_value.filter.return_value.all.side_effect = mock_all_side_effect

        with patch.object(sar, '_get_cross_source_conflicts_batch', return_value={}):
            slots = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=target_date,
                end_date=target_date,
                org_id=1,
                check_cross_source=False,
            )

        # With zero buffer, a slot starting at 10:30 should exist
        slot_starts = [datetime.fromisoformat(s["start"]) for s in slots]
        adjacent_start = datetime.combine(target_date, time(10, 30))
        assert adjacent_start in slot_starts, (
            f"Slot at {adjacent_start.isoformat()} should be available with zero buffer. "
            f"Available starts: {[s.isoformat() for s in slot_starts[:5]]}..."
        )

    def test_custom_buffer_per_appointment_type(self, setup_scheduler_helpers):
        """Different buffer values produce different conflict detection results."""
        sar = setup_scheduler_helpers

        # Existing meeting 10:00-10:30
        conflicts = [
            (datetime(2026, 4, 6, 10, 0), datetime(2026, 4, 6, 10, 30)),
        ]

        # With 5-min buffer_after: slot at 10:30 conflicts (busy until 10:35)
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 4, 6, 10, 30),
            datetime(2026, 4, 6, 11, 0),
            buffer_before=0,
            buffer_after=5,
        ) is True

        # With 0 buffer_after: slot at 10:30 is clear
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 4, 6, 10, 30),
            datetime(2026, 4, 6, 11, 0),
            buffer_before=0,
            buffer_after=0,
        ) is False

        # With 30-min buffer_before: slot at 09:30-10:00 conflicts (busy from 09:30)
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 4, 6, 9, 30),
            datetime(2026, 4, 6, 10, 0),
            buffer_before=30,
            buffer_after=0,
        ) is True

        # With 30-min buffer_before: slot at 09:00-09:30 is clear (ends exactly at buffered start)
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 4, 6, 9, 0),
            datetime(2026, 4, 6, 9, 30),
            buffer_before=30,
            buffer_after=0,
        ) is False


# =============================================================================
# CAPACITY LIMITS
# =============================================================================

class TestCapacityLimits:
    """Test daily booking capacity enforcement in slot generation."""

    def test_max_daily_bookings_enforced(self, setup_scheduler_helpers, mock_db, mock_models):
        """When existing appointments equal max_meetings_per_day, no slots should be generated."""
        sar = setup_scheduler_helpers
        target_date = _get_next_weekday(0)

        max_per_day = 3
        config = mock_models['SchedulerConfig'](
            user_id=1,
            max_meetings_per_day=max_per_day,
            min_notice_hours=0,
            enforce_lunch_break=False,
            buffer_before_minutes=0,
            buffer_after_minutes=0,
        )

        # Create max_per_day existing appointments to fill the capacity
        existing_appts = []
        for i in range(max_per_day):
            start_hour = 9 + i
            existing_appts.append(_make_mock_appointment(
                datetime.combine(target_date, time(start_hour, 0)),
                datetime.combine(target_date, time(start_hour, 30)),
            ))

        call_count = [0]

        def mock_all_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return [config]
            elif call_count[0] == 2:
                return []
            elif call_count[0] == 3:
                return existing_appts
            return []

        mock_db.query.return_value.filter.return_value.all.side_effect = mock_all_side_effect

        with patch.object(sar, '_get_cross_source_conflicts_batch', return_value={}):
            slots = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=target_date,
                end_date=target_date,
                org_id=1,
                max_per_day=max_per_day,
                check_cross_source=False,
            )

        # No slots should be available -- day is at capacity
        assert len(slots) == 0, (
            f"Expected 0 slots when at capacity ({max_per_day} meetings), "
            f"but got {len(slots)}"
        )

    def test_under_capacity_generates_slots(self, setup_scheduler_helpers, mock_db, mock_models):
        """When existing appointments are below max, slots should still be generated."""
        sar = setup_scheduler_helpers
        target_date = _get_next_weekday(0)

        max_per_day = 5
        config = mock_models['SchedulerConfig'](
            user_id=1,
            max_meetings_per_day=max_per_day,
            min_notice_hours=0,
            enforce_lunch_break=False,
            buffer_before_minutes=0,
            buffer_after_minutes=0,
        )

        # Only 2 existing appointments -- below capacity
        existing_appts = [
            _make_mock_appointment(
                datetime.combine(target_date, time(9, 0)),
                datetime.combine(target_date, time(9, 30)),
            ),
            _make_mock_appointment(
                datetime.combine(target_date, time(10, 0)),
                datetime.combine(target_date, time(10, 30)),
            ),
        ]

        call_count = [0]

        def mock_all_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return [config]
            elif call_count[0] == 2:
                return []
            elif call_count[0] == 3:
                return existing_appts
            return []

        mock_db.query.return_value.filter.return_value.all.side_effect = mock_all_side_effect

        with patch.object(sar, '_get_cross_source_conflicts_batch', return_value={}):
            slots = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=target_date,
                end_date=target_date,
                org_id=1,
                max_per_day=max_per_day,
                check_cross_source=False,
            )

        # Should have slots in the remaining open times
        assert len(slots) > 0, "Should generate slots when under daily capacity"

    def test_capacity_resets_daily(self, setup_scheduler_helpers, mock_db, mock_models):
        """Capacity limit should reset on the next day -- a full day should not block the next."""
        sar = setup_scheduler_helpers
        monday = _get_next_weekday(0)
        tuesday = monday + timedelta(days=1)

        max_per_day = 2
        config = mock_models['SchedulerConfig'](
            user_id=1,
            max_meetings_per_day=max_per_day,
            min_notice_hours=0,
            enforce_lunch_break=False,
            buffer_before_minutes=0,
            buffer_after_minutes=0,
        )

        # Monday is fully booked (2 appointments = max)
        existing_appts = [
            _make_mock_appointment(
                datetime.combine(monday, time(9, 0)),
                datetime.combine(monday, time(9, 30)),
            ),
            _make_mock_appointment(
                datetime.combine(monday, time(10, 0)),
                datetime.combine(monday, time(10, 30)),
            ),
        ]

        call_count = [0]

        def mock_all_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return [config]
            elif call_count[0] == 2:
                return []
            elif call_count[0] == 3:
                return existing_appts
            return []

        mock_db.query.return_value.filter.return_value.all.side_effect = mock_all_side_effect

        with patch.object(sar, '_get_cross_source_conflicts_batch', return_value={}):
            slots = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=monday,
                end_date=tuesday,
                org_id=1,
                max_per_day=max_per_day,
                check_cross_source=False,
            )

        # Monday should have 0 slots (at capacity), but Tuesday should have slots
        monday_slots = [s for s in slots if s["date"] == monday.isoformat()]
        tuesday_slots = [s for s in slots if s["date"] == tuesday.isoformat()]

        assert len(monday_slots) == 0, (
            f"Monday should have 0 slots (at capacity), got {len(monday_slots)}"
        )
        assert len(tuesday_slots) > 0, (
            "Tuesday should have available slots -- capacity resets daily"
        )

    def test_team_capacity_distributed(self, setup_scheduler_helpers, mock_db, mock_models):
        """Team capacity: each user's limit is independent; one user at capacity
        should not block slots for another user."""
        sar = setup_scheduler_helpers
        target_date = _get_next_weekday(0)

        max_per_day = 2

        config_user1 = mock_models['SchedulerConfig'](user_id=1, max_meetings_per_day=max_per_day,
                                                       min_notice_hours=0, enforce_lunch_break=False,
                                                       buffer_before_minutes=0, buffer_after_minutes=0)
        config_user2 = mock_models['SchedulerConfig'](user_id=2, max_meetings_per_day=max_per_day,
                                                       min_notice_hours=0, enforce_lunch_break=False,
                                                       buffer_before_minutes=0, buffer_after_minutes=0)

        # User 1 at capacity, user 2 has no appointments
        user1_appts = [
            _make_mock_appointment(datetime.combine(target_date, time(9, 0)),
                                   datetime.combine(target_date, time(9, 30)), user_id=1),
            _make_mock_appointment(datetime.combine(target_date, time(10, 0)),
                                   datetime.combine(target_date, time(10, 30)), user_id=1),
        ]

        call_count = [0]

        def mock_all_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return [config_user1, config_user2]  # configs
            elif call_count[0] == 2:
                return []                              # blocked times
            elif call_count[0] == 3:
                return user1_appts                     # appointments (only user 1)
            return []

        mock_db.query.return_value.filter.return_value.all.side_effect = mock_all_side_effect

        with patch.object(sar, '_get_cross_source_conflicts_batch', return_value={}):
            slots = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1, 2],
                start_date=target_date,
                end_date=target_date,
                org_id=1,
                max_per_day=max_per_day,
                check_cross_source=False,
                include_user_id=True,
            )

        user1_slots = [s for s in slots if s.get("user_id") == 1]
        user2_slots = [s for s in slots if s.get("user_id") == 2]

        assert len(user1_slots) == 0, (
            f"User 1 should have 0 slots (at capacity), got {len(user1_slots)}"
        )
        assert len(user2_slots) > 0, (
            "User 2 should have available slots -- independent capacity"
        )


# =============================================================================
# TIME BLOCK PROTECTION
# =============================================================================

class TestTimeBlockProtection:
    """Test that protected time blocks are respected during slot generation."""

    def test_focus_time_blocks_not_bookable(self, setup_scheduler_helpers, mock_db, mock_models):
        """Slots should not be generated during focus time blocks."""
        sar = setup_scheduler_helpers
        target_date = _get_next_weekday(0)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=0,
            enforce_lunch_break=False,
            buffer_before_minutes=0,
            buffer_after_minutes=0,
        )

        # Focus block from 14:00-16:00
        focus_block = _make_mock_blocked_time(
            datetime.combine(target_date, time(14, 0)),
            datetime.combine(target_date, time(16, 0)),
            block_type="focus",
        )

        call_count = [0]

        def mock_all_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return [config]
            elif call_count[0] == 2:
                return [focus_block]   # blocked times
            elif call_count[0] == 3:
                return []              # appointments
            return []

        mock_db.query.return_value.filter.return_value.all.side_effect = mock_all_side_effect

        with patch.object(sar, '_get_cross_source_conflicts_batch', return_value={}):
            slots = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=target_date,
                end_date=target_date,
                org_id=1,
                check_cross_source=False,
            )

        # Verify no slots exist within the focus block window (14:00-16:00)
        focus_start = datetime.combine(target_date, time(14, 0))
        focus_end = datetime.combine(target_date, time(16, 0))

        for slot in slots:
            slot_start = datetime.fromisoformat(slot["start"])
            slot_end = datetime.fromisoformat(slot["end"])
            overlaps = slot_start < focus_end and slot_end > focus_start
            assert not overlaps, (
                f"Slot {slot['start']}-{slot['end']} should not overlap with "
                f"focus block {focus_start.isoformat()}-{focus_end.isoformat()}"
            )

        # But slots outside the focus block should still exist
        assert len(slots) > 0, "Should still have slots outside the focus block"

    def test_lunch_blocks_not_bookable(self, setup_scheduler_helpers, mock_db, mock_models):
        """Slots should not be generated during configured lunch break."""
        sar = setup_scheduler_helpers
        target_date = _get_next_weekday(0)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=0,
            enforce_lunch_break=True,
            lunch_break_start=time(12, 0),
            lunch_break_end=time(13, 0),
            buffer_before_minutes=0,
            buffer_after_minutes=0,
        )

        call_count = [0]

        def mock_all_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return [config]
            elif call_count[0] == 2:
                return []
            elif call_count[0] == 3:
                return []
            return []

        mock_db.query.return_value.filter.return_value.all.side_effect = mock_all_side_effect

        with patch.object(sar, '_get_cross_source_conflicts_batch', return_value={}):
            slots = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=target_date,
                end_date=target_date,
                org_id=1,
                check_cross_source=False,
            )

        # Verify no slots overlap with 12:00-13:00
        lunch_start = datetime.combine(target_date, time(12, 0))
        lunch_end = datetime.combine(target_date, time(13, 0))

        for slot in slots:
            slot_start = datetime.fromisoformat(slot["start"])
            slot_end = datetime.fromisoformat(slot["end"])
            overlaps = slot_start < lunch_end and slot_end > lunch_start
            assert not overlaps, (
                f"Slot {slot['start']}-{slot['end']} should not overlap with "
                f"lunch break 12:00-13:00"
            )

        # Working hours: 09:00-17:00, minus 12:00-13:00 lunch = 7 hours = 14 slots
        assert len(slots) == 14, (
            f"Expected 14 slots (8 hours - 1 hour lunch = 7 hours / 30 min), got {len(slots)}"
        )

    def test_all_day_block_removes_entire_day(self, setup_scheduler_helpers, mock_db, mock_models):
        """An all-day blocked time should remove the entire day from availability."""
        sar = setup_scheduler_helpers
        target_date = _get_next_weekday(0)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=0,
            enforce_lunch_break=False,
            buffer_before_minutes=0,
            buffer_after_minutes=0,
        )

        # All-day block covering entire working hours
        all_day_block = _make_mock_blocked_time(
            datetime.combine(target_date, time(0, 0)),
            datetime.combine(target_date, time(23, 59)),
            block_type="pto",
        )
        all_day_block.all_day = True

        call_count = [0]

        def mock_all_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return [config]
            elif call_count[0] == 2:
                return [all_day_block]
            elif call_count[0] == 3:
                return []
            return []

        mock_db.query.return_value.filter.return_value.all.side_effect = mock_all_side_effect

        with patch.object(sar, '_get_cross_source_conflicts_batch', return_value={}):
            slots = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=target_date,
                end_date=target_date,
                org_id=1,
                check_cross_source=False,
            )

        assert len(slots) == 0, (
            f"Expected 0 slots on an all-day blocked day, got {len(slots)}"
        )


# =============================================================================
# CROSS-SOURCE BUFFER INTEGRATION
# =============================================================================

class TestCrossSourceBufferIntegration:
    """Test buffer enforcement works with cross-source calendar conflicts."""

    def test_cross_source_conflicts_respect_buffer(self, setup_scheduler_helpers):
        """Buffer times should apply to cross-source (external calendar) conflicts too."""
        sar = setup_scheduler_helpers

        # External calendar event 11:00-11:30
        conflicts = [
            (datetime(2026, 4, 6, 11, 0), datetime(2026, 4, 6, 11, 30)),
        ]

        # With 10-min buffer_after, slot at 11:30 should conflict (busy until 11:40)
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 4, 6, 11, 30),
            datetime(2026, 4, 6, 12, 0),
            buffer_before=0,
            buffer_after=10,
        ) is True

        # Slot at 11:40 should be clear
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 4, 6, 11, 40),
            datetime(2026, 4, 6, 12, 10),
            buffer_before=0,
            buffer_after=10,
        ) is False

    def test_combined_buffer_before_and_after(self, setup_scheduler_helpers):
        """Both buffer_before and buffer_after should apply simultaneously."""
        sar = setup_scheduler_helpers

        # Meeting at 14:00-14:30, buffer_before=10, buffer_after=10
        # Effective busy window: 13:50 - 14:40
        conflicts = [
            (datetime(2026, 4, 6, 14, 0), datetime(2026, 4, 6, 14, 30)),
        ]

        # Slot 13:30-14:00 ends at 14:00 > 13:50 (buffered start) => conflict
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 4, 6, 13, 30),
            datetime(2026, 4, 6, 14, 0),
            buffer_before=10,
            buffer_after=10,
        ) is True

        # Slot 13:00-13:30 ends at 13:30 < 13:50 => no conflict
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 4, 6, 13, 0),
            datetime(2026, 4, 6, 13, 30),
            buffer_before=10,
            buffer_after=10,
        ) is False

        # Slot 14:35-15:05 starts at 14:35 < 14:40 (buffered end) => conflict
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 4, 6, 14, 35),
            datetime(2026, 4, 6, 15, 5),
            buffer_before=10,
            buffer_after=10,
        ) is True

        # Slot 14:40-15:10 starts exactly at buffered end => no conflict (boundary)
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 4, 6, 14, 40),
            datetime(2026, 4, 6, 15, 10),
            buffer_before=10,
            buffer_after=10,
        ) is False
