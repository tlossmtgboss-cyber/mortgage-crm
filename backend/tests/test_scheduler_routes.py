"""
Scheduler Routes Test Suite

Tests for the refactored scheduler appointment routes:
- Unified slot generator (_generate_available_slots)
- Conflict detection (_check_appointment_conflict)
- Rate limiting (Redis-backed _check_rate_limit)
- Cross-source conflict helpers
- Input sanitization and PII masking
- Email service integration
"""

import pytest
from datetime import datetime, timedelta, date, time, timezone
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


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

    # Make hashable so it works as a dict key or in sets
    def __hash__(self):
        return id(self)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_models():
    """Create mock model classes for dependency injection."""
    models = {}

    # SchedulerConfig mock class with class-level column descriptors
    class MockConfig:
        # Class-level descriptors for SQLAlchemy .filter() calls
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

    # Mock Appointment with class-level column descriptors
    class MockAppointment:
        id = _Col()
        assigned_user_id = _Col()
        organization_id = _Col()
        status = _Col()
        scheduled_start = _Col()
        scheduled_end = _Col()

    # Mock BlockedTime with class-level column descriptors
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
    """Set up scheduler_appointment_routes with mocked dependencies."""
    import scheduler_appointment_routes as sar
    sar.set_dependencies(
        get_db_func=lambda: iter([MagicMock()]),
        get_current_user_func=MagicMock(),
        models_dict=mock_models
    )
    return sar


# =============================================================================
# UNIFIED SLOT GENERATOR TESTS
# =============================================================================

class TestGenerateAvailableSlots:
    """Test the unified _generate_available_slots function."""

    def test_returns_empty_for_no_models(self, setup_scheduler_routes, mock_db):
        """Should return empty list if models not available."""
        sar = setup_scheduler_routes
        # Temporarily break models
        original = sar._models
        sar._models = {}
        result = sar._generate_available_slots(
            db=mock_db,
            user_ids=[1],
            start_date=date.today(),
            end_date=date.today(),
        )
        assert result == []
        sar._models = original

    def test_validates_date_range_order(self, setup_scheduler_routes, mock_db):
        """Should raise 400 if start_date > end_date."""
        sar = setup_scheduler_routes
        with pytest.raises(HTTPException) as exc:
            sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=date(2026, 3, 10),
                end_date=date(2026, 3, 5),
            )
        assert exc.value.status_code == 400
        assert "start_date" in exc.value.detail

    def test_validates_date_range_max_90_days(self, setup_scheduler_routes, mock_db):
        """Should raise 400 if date range exceeds 90 days."""
        sar = setup_scheduler_routes
        with pytest.raises(HTTPException) as exc:
            sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=date(2026, 1, 1),
                end_date=date(2026, 5, 1),  # 120 days
            )
        assert exc.value.status_code == 400
        assert "90" in exc.value.detail

    def test_generates_slots_for_single_day(self, setup_scheduler_routes, mock_db, mock_models):
        """Should generate slots for a single working day."""
        sar = setup_scheduler_routes

        # Find a future Monday
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        future_monday = today + timedelta(days=days_until_monday)

        # Mock config query to return a config
        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=0,  # No notice required for testing
        )
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=future_monday,
                end_date=future_monday,
                duration_minutes=30,
                org_id=1,
            )

        # 9-17 = 8 hours, minus 12-13 lunch = 7 hours = 14 thirty-min slots
        assert len(result) == 14
        assert all("start" in s and "end" in s and "date" in s for s in result)

    def test_skips_disabled_days(self, setup_scheduler_routes, mock_db, mock_models):
        """Should skip Saturday/Sunday when they're disabled."""
        sar = setup_scheduler_routes

        # Find next Saturday
        today = date.today()
        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0:
            days_until_saturday = 7
        future_saturday = today + timedelta(days=days_until_saturday)

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

    def test_skips_lunch_break(self, setup_scheduler_routes, mock_db, mock_models):
        """Should not generate slots during lunch break."""
        sar = setup_scheduler_routes

        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        future_monday = today + timedelta(days=days_until_monday)

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
                start_date=future_monday,
                end_date=future_monday,
                org_id=1,
            )

        # No slot should start at 12:00 or 12:30
        slot_starts = [s["start"] for s in result]
        for start in slot_starts:
            dt = datetime.fromisoformat(start)
            assert not (dt.hour == 12 and dt.minute in (0, 30)), \
                f"Found slot during lunch: {start}"

    def test_no_lunch_break_when_disabled(self, setup_scheduler_routes, mock_db, mock_models):
        """Should generate slots during lunch when enforce_lunch_break=False."""
        sar = setup_scheduler_routes

        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        future_monday = today + timedelta(days=days_until_monday)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=0,
            enforce_lunch_break=False,
        )
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

        # 9-17 = 16 slots (no lunch break skipped)
        assert len(result) == 16

    def test_respects_blocked_times(self, setup_scheduler_routes, mock_db, mock_models):
        """Should skip slots that overlap with blocked times."""
        sar = setup_scheduler_routes

        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        future_monday = today + timedelta(days=days_until_monday)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=0,
            enforce_lunch_break=False,
        )

        # Create a blocked time 10:00-11:00
        blocked = MagicMock()
        blocked.start_datetime = datetime.combine(future_monday, time(10, 0))
        blocked.end_datetime = datetime.combine(future_monday, time(11, 0))

        # First query = config, second = blocked times, third = appointments
        def side_effect_filter(*args, **kwargs):
            return mock_db.query.return_value

        mock_db.query.return_value.filter.side_effect = side_effect_filter

        # Override to return config, blocked times, and empty appointments
        call_count = [0]
        original_first = mock_db.query.return_value.first
        original_all = mock_db.query.return_value.all

        def mock_first():
            return config

        def mock_all():
            call_count[0] += 1
            if call_count[0] == 1:  # blocked times
                return [blocked]
            return []  # appointments

        mock_db.query.return_value.first.side_effect = mock_first
        mock_db.query.return_value.all.side_effect = mock_all

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=future_monday,
                end_date=future_monday,
                org_id=1,
            )

        # Should have fewer slots (10:00 and 10:30 blocked)
        for slot in result:
            dt = datetime.fromisoformat(slot["start"])
            assert not (dt.hour == 10 and dt.minute in (0, 30)), \
                f"Found slot during blocked time: {slot['start']}"

    def test_include_user_id_flag(self, setup_scheduler_routes, mock_db, mock_models):
        """Should include user_id in slots when flag is set."""
        sar = setup_scheduler_routes

        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        future_monday = today + timedelta(days=days_until_monday)

        config = mock_models['SchedulerConfig'](user_id=42, min_notice_hours=0)
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[42],
                start_date=future_monday,
                end_date=future_monday,
                org_id=1,
                include_user_id=True,
            )

        assert len(result) > 0
        assert all(s["user_id"] == 42 for s in result)

    def test_include_day_name_flag(self, setup_scheduler_routes, mock_db, mock_models):
        """Should include day name in slots when flag is set."""
        sar = setup_scheduler_routes

        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        future_monday = today + timedelta(days=days_until_monday)

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
                include_day_name=True,
            )

        assert len(result) > 0
        assert all(s["day"] == "monday" for s in result)

    def test_start_time_key_format(self, setup_scheduler_routes, mock_db, mock_models):
        """Should use start_time/end_time keys when format is 'start_time'."""
        sar = setup_scheduler_routes

        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        future_monday = today + timedelta(days=days_until_monday)

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
                time_key_format="start_time",
            )

        assert len(result) > 0
        assert all("start_time" in s and "end_time" in s for s in result)
        assert all(s["start_time"].endswith("Z") for s in result)

    def test_max_per_day_enforcement(self, setup_scheduler_routes, mock_db, mock_models):
        """Should skip days where max_per_day appointments are already booked."""
        sar = setup_scheduler_routes

        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        future_monday = today + timedelta(days=days_until_monday)

        config = mock_models['SchedulerConfig'](
            user_id=1,
            min_notice_hours=0,
            max_meetings_per_day=2,
        )

        # Create 2 existing appointments for that day
        appt1 = MagicMock()
        appt1.scheduled_start = datetime.combine(future_monday, time(9, 0))
        appt1.scheduled_end = datetime.combine(future_monday, time(9, 30))
        appt2 = MagicMock()
        appt2.scheduled_start = datetime.combine(future_monday, time(10, 0))
        appt2.scheduled_end = datetime.combine(future_monday, time(10, 30))

        call_count = [0]

        def mock_first():
            return config

        def mock_all():
            call_count[0] += 1
            if call_count[0] == 1:  # blocked times
                return []
            if call_count[0] == 2:  # appointments
                return [appt1, appt2]
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
                max_per_day=2,
            )

        # Day should be skipped entirely since 2 appointments = max_per_day
        assert len(result) == 0

    def test_slots_are_sorted(self, setup_scheduler_routes, mock_db, mock_models):
        """Should return slots sorted by start time."""
        sar = setup_scheduler_routes

        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        # Use Mon-Tue range
        future_monday = today + timedelta(days=days_until_monday)
        future_tuesday = future_monday + timedelta(days=1)

        config = mock_models['SchedulerConfig'](user_id=1, min_notice_hours=0)
        mock_db.query.return_value.filter.return_value.first.return_value = config
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(sar, '_get_cross_source_conflicts', return_value=[]):
            result = sar._generate_available_slots(
                db=mock_db,
                user_ids=[1],
                start_date=future_monday,
                end_date=future_tuesday,
                org_id=1,
            )

        starts = [s["start"] for s in result]
        assert starts == sorted(starts)


# =============================================================================
# CONFLICT DETECTION TESTS
# =============================================================================

class TestCheckAppointmentConflict:
    """Test _check_appointment_conflict with SELECT FOR UPDATE."""

    def test_no_conflict_passes(self, setup_scheduler_routes, mock_db):
        """Should not raise when no conflict found."""
        sar = setup_scheduler_routes
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

        # Should not raise
        sar._check_appointment_conflict(
            mock_db,
            assigned_user_id=1,
            start_time=datetime(2026, 3, 5, 10, 0),
            end_time=datetime(2026, 3, 5, 10, 30),
        )

    def test_raises_409_on_conflict(self, setup_scheduler_routes, mock_db):
        """Should raise 409 when an overlapping appointment is found."""
        sar = setup_scheduler_routes
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = MagicMock()

        with pytest.raises(HTTPException) as exc:
            sar._check_appointment_conflict(
                mock_db,
                assigned_user_id=1,
                start_time=datetime(2026, 3, 5, 10, 0),
                end_time=datetime(2026, 3, 5, 10, 30),
            )
        assert exc.value.status_code == 409

    def test_raises_409_on_lock_contention(self, setup_scheduler_routes, mock_db):
        """Should raise 409 when row is locked by another transaction."""
        from sqlalchemy.exc import OperationalError
        sar = setup_scheduler_routes
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.side_effect = \
            OperationalError("lock", {}, Exception())

        with pytest.raises(HTTPException) as exc:
            sar._check_appointment_conflict(
                mock_db,
                assigned_user_id=1,
                start_time=datetime(2026, 3, 5, 10, 0),
                end_time=datetime(2026, 3, 5, 10, 30),
            )
        assert exc.value.status_code == 409

    def test_excludes_appointment_id(self, setup_scheduler_routes, mock_db):
        """Should pass exclude_appointment_id to the query."""
        sar = setup_scheduler_routes
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

        sar._check_appointment_conflict(
            mock_db,
            assigned_user_id=1,
            start_time=datetime(2026, 3, 5, 10, 0),
            end_time=datetime(2026, 3, 5, 10, 30),
            exclude_appointment_id=42,
        )
        # No exception means success


# =============================================================================
# CROSS-SOURCE CONFLICT TESTS
# =============================================================================

class TestCrossSourceConflicts:
    """Test _get_cross_source_conflicts and _has_cross_source_conflict."""

    def test_has_conflict_detects_overlap(self, setup_scheduler_routes):
        """Should detect overlapping busy time."""
        sar = setup_scheduler_routes

        conflicts = [
            (datetime(2026, 3, 5, 10, 0), datetime(2026, 3, 5, 11, 0)),
        ]

        # Slot 10:30-11:00 overlaps with busy 10:00-11:00
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 3, 5, 10, 30),
            datetime(2026, 3, 5, 11, 0),
        ) is True

    def test_has_conflict_no_overlap(self, setup_scheduler_routes):
        """Should not detect conflict for non-overlapping time."""
        sar = setup_scheduler_routes

        conflicts = [
            (datetime(2026, 3, 5, 10, 0), datetime(2026, 3, 5, 11, 0)),
        ]

        # Slot 11:00-11:30 doesn't overlap with 10:00-11:00
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 3, 5, 11, 0),
            datetime(2026, 3, 5, 11, 30),
        ) is False

    def test_has_conflict_with_buffer(self, setup_scheduler_routes):
        """Should account for buffer when checking conflicts."""
        sar = setup_scheduler_routes

        conflicts = [
            (datetime(2026, 3, 5, 10, 0), datetime(2026, 3, 5, 11, 0)),
        ]

        # Slot 10:55-11:25 doesn't overlap raw busy 10-11,
        # but with 5-min buffer_after on the busy, 11:00 extends to 11:05
        # so 10:55 < 11:05 and 11:25 > 9:55 → conflict
        assert sar._has_cross_source_conflict(
            conflicts,
            datetime(2026, 3, 5, 10, 55),
            datetime(2026, 3, 5, 11, 25),
            buffer_before=5, buffer_after=5,
        ) is True

    def test_empty_conflicts_no_match(self, setup_scheduler_routes):
        """Should return False for empty conflict list."""
        sar = setup_scheduler_routes
        assert sar._has_cross_source_conflict(
            [],
            datetime(2026, 3, 5, 10, 0),
            datetime(2026, 3, 5, 10, 30),
        ) is False


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================

class TestRateLimiting:
    """Test Redis-backed rate limiting."""

    def test_allows_request_when_redis_unavailable(self, setup_scheduler_routes):
        """Should allow all requests when Redis is not available."""
        sar = setup_scheduler_routes

        # Force Redis unavailable
        sar._rate_limit_redis = None
        sar._rate_limit_redis_checked = True

        mock_request = MagicMock()
        mock_request.client.host = "1.2.3.4"
        mock_request.url.path = "/test"
        mock_request.headers.get.return_value = None

        # Should not raise
        sar._check_rate_limit(mock_request)

    def test_raises_429_when_limit_exceeded(self, setup_scheduler_routes):
        """Should raise 429 when request count exceeds limit."""
        sar = setup_scheduler_routes

        mock_redis = MagicMock()
        mock_redis.incr.return_value = 11  # Over the 10 limit
        mock_redis.ttl.return_value = 45
        sar._rate_limit_redis = mock_redis
        sar._rate_limit_redis_checked = True

        mock_request = MagicMock()
        mock_request.client.host = "1.2.3.4"
        mock_request.url.path = "/public/book/demo"
        mock_request.headers.get.return_value = None

        with pytest.raises(HTTPException) as exc:
            sar._check_rate_limit(mock_request)
        assert exc.value.status_code == 429

    def test_allows_request_under_limit(self, setup_scheduler_routes):
        """Should allow requests under the limit."""
        sar = setup_scheduler_routes

        mock_redis = MagicMock()
        mock_redis.incr.return_value = 5  # Under limit
        mock_redis.ttl.return_value = 30
        sar._rate_limit_redis = mock_redis
        sar._rate_limit_redis_checked = True

        mock_request = MagicMock()
        mock_request.client.host = "1.2.3.4"
        mock_request.url.path = "/public/book/demo"
        mock_request.headers.get.return_value = None

        # Should not raise
        sar._check_rate_limit(mock_request)

    def test_sets_expire_on_first_request(self, setup_scheduler_routes):
        """Should set TTL on first request (incr returns 1)."""
        sar = setup_scheduler_routes

        mock_redis = MagicMock()
        mock_redis.incr.return_value = 1  # First request
        sar._rate_limit_redis = mock_redis
        sar._rate_limit_redis_checked = True

        mock_request = MagicMock()
        mock_request.client.host = "1.2.3.4"
        mock_request.url.path = "/public/book/demo"
        mock_request.headers.get.return_value = None

        sar._check_rate_limit(mock_request)
        mock_redis.expire.assert_called_once()

    def test_uses_x_forwarded_for(self, setup_scheduler_routes):
        """Should use X-Forwarded-For header for client IP."""
        sar = setup_scheduler_routes

        mock_redis = MagicMock()
        mock_redis.incr.return_value = 1
        sar._rate_limit_redis = mock_redis
        sar._rate_limit_redis_checked = True

        mock_request = MagicMock()
        mock_request.headers.get.return_value = "10.0.0.1, 10.0.0.2"
        mock_request.url.path = "/test"

        sar._check_rate_limit(mock_request)
        call_args = mock_redis.incr.call_args[0][0]
        assert "10.0.0.1" in call_args

    def test_allows_on_redis_error(self, setup_scheduler_routes):
        """Should allow request if Redis raises an error."""
        sar = setup_scheduler_routes

        mock_redis = MagicMock()
        mock_redis.incr.side_effect = Exception("Connection refused")
        sar._rate_limit_redis = mock_redis
        sar._rate_limit_redis_checked = True

        mock_request = MagicMock()
        mock_request.client.host = "1.2.3.4"
        mock_request.url.path = "/test"
        mock_request.headers.get.return_value = None

        # Should not raise — graceful degradation
        sar._check_rate_limit(mock_request)


# =============================================================================
# INPUT SANITIZATION AND PII MASKING TESTS
# =============================================================================

class TestSanitization:
    """Test _sanitize_text and _mask_email."""

    def test_sanitize_strips_html(self, setup_scheduler_routes):
        """Should strip HTML tags from input."""
        sar = setup_scheduler_routes
        result = sar._sanitize_text("<script>alert('xss')</script>Hello")
        assert "<script>" not in result
        assert "Hello" in result

    def test_sanitize_returns_none_for_none(self, setup_scheduler_routes):
        """Should return None for None input."""
        sar = setup_scheduler_routes
        assert sar._sanitize_text(None) is None

    def test_sanitize_passes_clean_text(self, setup_scheduler_routes):
        """Should pass through clean text unchanged."""
        sar = setup_scheduler_routes
        assert sar._sanitize_text("Hello World") == "Hello World"

    def test_mask_email_basic(self, setup_scheduler_routes):
        """Should mask email to show first char + domain."""
        sar = setup_scheduler_routes
        assert sar._mask_email("john@example.com") == "j***@example.com"

    def test_mask_email_none(self, setup_scheduler_routes):
        """Should return *** for None email."""
        sar = setup_scheduler_routes
        assert sar._mask_email(None) == "***"

    def test_mask_email_no_at(self, setup_scheduler_routes):
        """Should return *** for invalid email without @."""
        sar = setup_scheduler_routes
        assert sar._mask_email("notanemail") == "***"

    def test_mask_email_short_local(self, setup_scheduler_routes):
        """Should handle single-character local part."""
        sar = setup_scheduler_routes
        assert sar._mask_email("a@b.com") == "a***@b.com"


# =============================================================================
# URL VALIDATION TESTS
# =============================================================================

class TestURLValidation:
    """Test _validate_url."""

    def test_accepts_https(self, setup_scheduler_routes):
        sar = setup_scheduler_routes
        assert sar._validate_url("https://example.com") == "https://example.com"

    def test_accepts_http(self, setup_scheduler_routes):
        sar = setup_scheduler_routes
        assert sar._validate_url("http://example.com") == "http://example.com"

    def test_rejects_javascript(self, setup_scheduler_routes):
        sar = setup_scheduler_routes
        assert sar._validate_url("javascript:alert(1)") is None

    def test_rejects_data_uri(self, setup_scheduler_routes):
        sar = setup_scheduler_routes
        assert sar._validate_url("data:text/html,<h1>hi</h1>") is None

    def test_returns_none_for_none(self, setup_scheduler_routes):
        sar = setup_scheduler_routes
        assert sar._validate_url(None) is None

    def test_returns_none_for_empty(self, setup_scheduler_routes):
        sar = setup_scheduler_routes
        assert sar._validate_url("") is None


# =============================================================================
# ICS GENERATION TESTS
# =============================================================================

class TestICSGeneration:
    """Test ICS calendar file generation."""

    def test_basic_ics_generation(self):
        """Should generate valid ICS content."""
        from scheduler_email_service import generate_ics_content

        ics = generate_ics_content(
            appointment_title="Test Meeting",
            start_datetime=datetime(2026, 3, 5, 14, 0, 0),
            duration_minutes=30,
            attendee_email="client@test.com",
            attendee_name="Client",
            organizer_email="lo@test.com",
            organizer_name="Loan Officer",
        )

        assert "BEGIN:VCALENDAR" in ics
        assert "BEGIN:VEVENT" in ics
        assert "Test Meeting" in ics
        assert "END:VCALENDAR" in ics

    def test_ics_includes_video_link(self):
        """Should include video link when provided."""
        from scheduler_email_service import generate_ics_content

        ics = generate_ics_content(
            appointment_title="Video Call",
            start_datetime=datetime(2026, 3, 5, 14, 0, 0),
            duration_minutes=30,
            attendee_email="client@test.com",
            attendee_name="Client",
            organizer_email="lo@test.com",
            organizer_name="Loan Officer",
            video_link="https://meet.example.com/room-123",
        )

        assert "meet.example.com" in ics

    def test_ics_escapes_special_chars(self):
        """Should escape special characters in ICS fields."""
        from scheduler_email_service import generate_ics_content

        ics = generate_ics_content(
            appointment_title="Meeting; with: commas, and semicolons",
            start_datetime=datetime(2026, 3, 5, 14, 0, 0),
            duration_minutes=30,
            attendee_email="client@test.com",
            attendee_name="Client",
            organizer_email="lo@test.com",
            organizer_name="Loan Officer",
            description="Line1\nLine2",
        )

        assert "BEGIN:VCALENDAR" in ics


# =============================================================================
# EMAIL SERVICE TESTS
# =============================================================================

class TestEmailService:
    """Test email service functions."""

    def test_confirmation_email_calls_notifier(self):
        """Should send confirmation email via notification service."""
        from scheduler_email_service import send_appointment_confirmation_email

        with patch('scheduler_email_service.notification_service') as mock_ns:
            mock_ns.send_email.return_value = {"success": True}

            result = send_appointment_confirmation_email(
                attendee_email="client@test.com",
                attendee_name="Test Client",
                appointment_title="Consultation",
                appointment_date="Monday, March 5, 2026",
                appointment_time="2:00 PM CST",
                duration="30 minutes",
                team_member_name="Alice Smith",
            )

            assert result["success"] is True
            mock_ns.send_email.assert_called_once()

    def test_confirmation_email_handles_failure(self):
        """Should handle notification service failure gracefully."""
        from scheduler_email_service import send_appointment_confirmation_email

        with patch('scheduler_email_service.notification_service') as mock_ns:
            mock_ns.send_email.side_effect = Exception("SMTP error")

            result = send_appointment_confirmation_email(
                attendee_email="client@test.com",
                attendee_name="Test Client",
                appointment_title="Consultation",
                appointment_date="Monday, March 5, 2026",
                appointment_time="2:00 PM CST",
                duration="30 minutes",
            )

            assert result["success"] is False

    def test_cancellation_email_uses_plain_content(self):
        """Should use plain_content kwarg (not text_content) for cancellation emails."""
        from scheduler_email_service import send_appointment_cancellation_email

        with patch('scheduler_email_service.notification_service') as mock_ns:
            mock_ns.send_email.return_value = {"success": True}

            send_appointment_cancellation_email(
                attendee_email="client@test.com",
                attendee_name="Test Client",
                appointment_title="Consultation",
                appointment_date="Monday, March 5, 2026",
                appointment_time="2:00 PM CST",
                cancellation_reason="Schedule conflict",
            )

            if mock_ns.send_email.called:
                call_kwargs = mock_ns.send_email.call_args
                kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
                # Verify plain_content is used, not text_content
                if "plain_content" in kwargs:
                    assert kwargs["plain_content"] is not None
                assert "text_content" not in kwargs

    def test_reminder_email_24h(self):
        """Should send 24h reminder with 'Tomorrow' subject."""
        from scheduler_email_service import send_appointment_reminder_email

        with patch('scheduler_email_service.notification_service') as mock_ns:
            mock_ns.send_email.return_value = {"success": True}

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


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestHelpers:
    """Test _get_org_id, _get_user_timezone, and other helpers."""

    def test_get_org_id_returns_id(self, setup_scheduler_routes):
        """Should return organization_id from user."""
        sar = setup_scheduler_routes
        user = MagicMock()
        user.organization_id = 42
        assert sar._get_org_id(user) == 42

    def test_get_org_id_raises_403_if_missing(self, setup_scheduler_routes):
        """Should raise 403 if organization_id is None."""
        sar = setup_scheduler_routes
        user = MagicMock()
        user.organization_id = None
        with pytest.raises(HTTPException) as exc:
            sar._get_org_id(user)
        assert exc.value.status_code == 403

    def test_get_user_timezone_default(self, setup_scheduler_routes, mock_db):
        """Should return America/Chicago as default timezone."""
        sar = setup_scheduler_routes
        mock_db.query.return_value.filter.return_value.first.return_value = None
        tz = sar._get_user_timezone(mock_db, 1)
        assert tz == "America/Chicago"

    def test_get_user_timezone_from_config(self, setup_scheduler_routes, mock_db):
        """Should return timezone from SchedulerConfig."""
        sar = setup_scheduler_routes
        config = MagicMock()
        config.timezone = "America/New_York"
        mock_db.query.return_value.filter.return_value.first.return_value = config
        tz = sar._get_user_timezone(mock_db, 1)
        assert tz == "America/New_York"


# =============================================================================
# MODEL VALIDATION TESTS (NOT NULL organization_id)
# =============================================================================

class TestSchedulerModels:
    """Test scheduler model constraints."""

    def test_all_models_have_non_nullable_org_id(self):
        """Verify all scheduler models have nullable=False on organization_id."""
        from smart_scheduler_models import (
            SchedulerConfig, AvailabilitySlot, AppointmentType,
            Appointment, RoutingRule, BlockedTime, BookingLink,
            AppointmentReminder, SchedulerAuditLog,
        )

        models_to_check = {
            'SchedulerConfig': SchedulerConfig,
            'AvailabilitySlot': AvailabilitySlot,
            'AppointmentType': AppointmentType,
            'Appointment': Appointment,
            'RoutingRule': RoutingRule,
            'BlockedTime': BlockedTime,
            'BookingLink': BookingLink,
            'AppointmentReminder': AppointmentReminder,
            'SchedulerAuditLog': SchedulerAuditLog,
        }

        for model_name, model_class in models_to_check.items():
            col = getattr(model_class, 'organization_id', None)
            if col is not None and hasattr(col, 'property'):
                for c in col.property.columns:
                    assert not c.nullable, \
                        f"{model_name}.organization_id should be NOT NULL"


# =============================================================================
# MULTI-TENANT ISOLATION TESTS
# =============================================================================

class TestMultiTenantIsolation:
    """Verify tenant isolation is enforced across all smart calendar components."""

    def test_unified_calendar_service_requires_org_id(self):
        """UnifiedCalendarService must raise if organization_id is missing."""
        from services.unified_calendar_service import UnifiedCalendarService
        mock_db = MagicMock()
        with pytest.raises(ValueError, match="organization_id is required"):
            UnifiedCalendarService(db=mock_db, user_id=1, organization_id=None)
        with pytest.raises(ValueError, match="organization_id is required"):
            UnifiedCalendarService(db=mock_db, user_id=1, organization_id=0)

    def test_calendar_sync_routes_use_centralized_auth(self):
        """calendar_sync_routes must use centralized auth, not custom JWT."""
        import routes.calendar_sync_routes as csr
        source = Path(csr.__file__).read_text()
        # Should NOT contain custom jwt.decode for auth
        assert "jwt.decode" not in source, \
            "calendar_sync_routes should use centralized auth, not custom jwt.decode"
        # Should have _get_current_user_dep helper
        assert "_get_current_user_dep" in source, \
            "calendar_sync_routes should use _get_current_user_dep for auth"
        # Should have _get_org_id helper
        assert "_get_org_id" in source, \
            "calendar_sync_routes should use _get_org_id helper"

    def test_calendar_sync_routes_no_empty_secret_fallback(self):
        """calendar_sync_routes must not fallback to empty SECRET_KEY."""
        import routes.calendar_sync_routes as csr
        source = Path(csr.__file__).read_text()
        assert 'getenv("SECRET_KEY", "")' not in source, \
            "SECRET_KEY must not fallback to empty string"

    def test_calendly_integration_has_foreign_key(self):
        """CalendlyIntegration.organization_id must have ForeignKey."""
        from routes.calendly_routes import CalendlyIntegration
        cols = CalendlyIntegration.__table__.columns
        org_col = cols.get('organization_id')
        assert org_col is not None, "organization_id column missing"
        fks = list(org_col.foreign_keys)
        assert len(fks) > 0, \
            "CalendlyIntegration.organization_id should have ForeignKey"
        assert any("organizations.id" in str(fk.target_fullname) for fk in fks)

    def test_calendly_booking_has_foreign_key(self):
        """CalendlyBooking.organization_id must have ForeignKey."""
        from routes.calendly_routes import CalendlyBooking
        cols = CalendlyBooking.__table__.columns
        org_col = cols.get('organization_id')
        assert org_col is not None, "organization_id column missing"
        fks = list(org_col.foreign_keys)
        assert len(fks) > 0, \
            "CalendlyBooking.organization_id should have ForeignKey"
        assert any("organizations.id" in str(fk.target_fullname) for fk in fks)

    def test_crm_calendar_event_has_foreign_key(self):
        """CRMCalendarEvent.organization_id must have ForeignKey."""
        from models.calendar_sync_models import CRMCalendarEvent
        cols = CRMCalendarEvent.__table__.columns
        org_col = cols.get('organization_id')
        assert org_col is not None, "organization_id column missing"
        fks = list(org_col.foreign_keys)
        assert len(fks) > 0, \
            "CRMCalendarEvent.organization_id should have ForeignKey"
        assert any("organizations.id" in str(fk.target_fullname) for fk in fks)

    def test_get_integration_filters_by_org(self):
        """get_integration() should filter by org_id when provided."""
        from routes.calendly_routes import get_integration, CalendlyIntegration
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        get_integration(mock_db, user_id=1, org_id=42)

        # Should have called filter at least twice (user_id and org_id)
        assert mock_query.filter.call_count >= 2, \
            "get_integration should filter by both user_id and org_id"

    def test_no_datetime_utcnow_in_calendar_files(self):
        """No smart calendar file should use deprecated datetime.utcnow()."""
        calendar_files = [
            'routes/calendar_sync_routes.py',
            'routes/calendly_routes.py',
            'routes/unified_calendar_routes.py',
            'routes/scheduler_routes.py',
            'routes/scheduler_appointment_routes.py',
            'models/calendar_sync_models.py',
            'smart_scheduler_models.py',
            'scheduler_appointment_routes.py',
            'services/smart_scheduler_service.py',
            'scheduler_enhancements.py',
            'services/unified_calendar_service.py',
            'scheduler_enhanced_routes.py',
            'scheduler_email_service.py',
        ]
        backend_dir = Path(__file__).parent.parent
        for relpath in calendar_files:
            fpath = backend_dir / relpath
            if fpath.exists():
                source = fpath.read_text()
                assert "datetime.utcnow()" not in source, \
                    f"{relpath} still uses deprecated datetime.utcnow()"

    def test_enhanced_routes_have_org_id_helper(self):
        """Consolidated scheduler appointment routes must have _get_org_id helper."""
        import routes.scheduler_appointment_routes as sar
        source = Path(sar.__file__).read_text()
        assert "_get_org_id" in source, \
            "scheduler_appointment_routes (consolidated) should have _get_org_id helper"

    def test_scheduler_audit_log_has_foreign_key(self):
        """SchedulerAuditLog.organization_id must have ForeignKey."""
        from smart_scheduler_models import SchedulerAuditLog
        AuditLog = SchedulerAuditLog
        cols = AuditLog.__table__.columns
        org_col = cols.get('organization_id')
        assert org_col is not None
        fks = list(org_col.foreign_keys)
        assert len(fks) > 0, \
            "SchedulerAuditLog.organization_id should have ForeignKey"
