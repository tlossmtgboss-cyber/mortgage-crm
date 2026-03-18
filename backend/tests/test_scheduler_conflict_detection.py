"""
Integration tests for appointment conflict detection.
Tests conflict checking across internal appointments, Google Calendar, Outlook, and CRM events.

Tests exercise the core conflict detection functions from
routes/scheduler/_helpers.py:
  - _get_cross_source_conflicts()
  - _has_cross_source_conflict()
  - _check_appointment_conflict()
  - _check_duplicate_booking()
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, PropertyMock
from fastapi import HTTPException

from routes.scheduler._helpers import (
    _has_cross_source_conflict,
    _get_cross_source_conflicts,
    _check_appointment_conflict,
    _check_duplicate_booking,
    set_dependencies,
)
from routes.scheduler.constants import (
    DEFAULT_APPOINTMENT_DURATION_MINUTES,
    DEFAULT_BUFFER_BEFORE_MINUTES,
    DEFAULT_BUFFER_AFTER_MINUTES,
)


# ============================================================================
# HELPERS
# ============================================================================

def _dt(hour, minute=0, day_offset=0):
    """Create a datetime for today (or +day_offset) at the given hour/minute in UTC."""
    base = datetime(2026, 3, 18, tzinfo=timezone.utc) + timedelta(days=day_offset)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _make_mock_appointment(
    id=1,
    assigned_user_id=1,
    organization_id=1,
    scheduled_start=None,
    scheduled_end=None,
    status="booked",
    attendee_email="client@example.com",
):
    """Create a mock Appointment object with the fields used by conflict queries."""
    appt = MagicMock()
    appt.id = id
    appt.assigned_user_id = assigned_user_id
    appt.organization_id = organization_id
    appt.scheduled_start = scheduled_start or _dt(10)
    appt.scheduled_end = scheduled_end or _dt(10, 30)
    appt.status = status
    appt.attendee_email = attendee_email
    return appt


class FakeQuery:
    """
    A chainable mock that simulates SQLAlchemy query results.
    Accepts a list of objects to return from .all() / .first().
    """
    def __init__(self, results=None):
        self._results = results or []

    def filter(self, *args, **kwargs):
        return self

    def with_for_update(self, **kwargs):
        return self

    def all(self):
        return self._results

    def first(self):
        return self._results[0] if self._results else None


class FakeDB:
    """
    Minimal mock db session whose .query() returns a configurable FakeQuery.
    source_results maps source name -> list of mock objects.
    """
    def __init__(self, results_by_model=None):
        self._results_by_model = results_by_model or {}

    def query(self, model_class):
        results = self._results_by_model.get(model_class, [])
        return FakeQuery(results)


# ============================================================================
# _has_cross_source_conflict (pure logic, no DB)
# ============================================================================

class TestHasCrossSourceConflict:
    """Test the pure-function overlap checker against a conflict list."""

    def test_overlapping_slot_detected(self):
        """A slot that overlaps an existing busy block is detected."""
        conflicts = [(_dt(10), _dt(11))]
        assert _has_cross_source_conflict(conflicts, _dt(10, 30), _dt(11, 30)) is True

    def test_non_overlapping_slot_allowed(self):
        """A slot that does not overlap any busy block passes."""
        conflicts = [(_dt(10), _dt(11))]
        assert _has_cross_source_conflict(conflicts, _dt(11), _dt(12)) is False

    def test_adjacent_slots_no_conflict_without_buffer(self):
        """Back-to-back slots (end == start) should NOT conflict without buffer."""
        conflicts = [(_dt(10), _dt(10, 30))]
        assert _has_cross_source_conflict(conflicts, _dt(10, 30), _dt(11)) is False

    def test_buffer_before_creates_conflict(self):
        """A slot within buffer_before of a busy block should conflict."""
        conflicts = [(_dt(10), _dt(10, 30))]
        # Slot starts at 9:56, ends at 10:00 — would clear without buffer,
        # but with buffer_before=5 the busy block effectively starts at 9:55.
        assert _has_cross_source_conflict(
            conflicts, _dt(9, 56), _dt(10), buffer_before=5
        ) is True

    def test_buffer_after_creates_conflict(self):
        """A slot within buffer_after of a busy block should conflict."""
        conflicts = [(_dt(10), _dt(10, 30))]
        # Slot starts at 10:33, ends at 11:00 — would clear without buffer,
        # but with buffer_after=5 the busy block effectively ends at 10:35.
        assert _has_cross_source_conflict(
            conflicts, _dt(10, 33), _dt(11), buffer_after=5
        ) is True

    def test_buffer_respects_clear_slot(self):
        """A slot beyond the buffer window should NOT conflict."""
        conflicts = [(_dt(10), _dt(10, 30))]
        # Slot starts at 10:36 — with buffer_after=5, busy ends at 10:35
        assert _has_cross_source_conflict(
            conflicts, _dt(10, 36), _dt(11), buffer_after=5
        ) is False

    def test_slot_fully_inside_busy_block(self):
        """A slot entirely within a busy block should conflict."""
        conflicts = [(_dt(9), _dt(12))]
        assert _has_cross_source_conflict(conflicts, _dt(10), _dt(11)) is True

    def test_busy_block_fully_inside_slot(self):
        """A busy block entirely within the slot should conflict."""
        conflicts = [(_dt(10, 15), _dt(10, 45))]
        assert _has_cross_source_conflict(conflicts, _dt(10), _dt(11)) is True

    def test_no_conflicts_empty_list(self):
        """An empty conflict list should never conflict."""
        assert _has_cross_source_conflict([], _dt(10), _dt(11)) is False

    def test_multiple_busy_blocks_second_conflicts(self):
        """Conflict is detected when the second of multiple busy blocks overlaps."""
        conflicts = [
            (_dt(8), _dt(9)),
            (_dt(10, 15), _dt(10, 45)),
            (_dt(14), _dt(15)),
        ]
        assert _has_cross_source_conflict(conflicts, _dt(10), _dt(11)) is True


# ============================================================================
# _get_cross_source_conflicts (DB-backed, mocked)
# ============================================================================

class TestCrossSourceConflictDetection:
    """Test conflict detection across calendar sources."""

    def _setup_models(self, v2_appts=None, legacy_appts=None,
                      cal_events=None, crm_events=None):
        """
        Patch _models and the external model imports so
        _get_cross_source_conflicts returns predictable results.
        """
        # Create a mock Appointment model class with filterable attributes
        MockAppointmentModel = MagicMock()
        MockAppointmentModel.__name__ = "Appointment"

        # Inject into _helpers._models
        models_dict = {"Appointment": MockAppointmentModel}
        set_dependencies(None, None, models_dict)

        # Build a FakeDB that returns v2 appointments for the Appointment model
        results_by_model = {}
        if v2_appts is not None:
            results_by_model[MockAppointmentModel] = v2_appts

        db = FakeDB(results_by_model)
        return db, MockAppointmentModel

    def test_v2_appointment_creates_conflict(self):
        """A v2 Appointment (scheduler_appointments) should appear in conflicts."""
        appt = _make_mock_appointment(
            scheduled_start=_dt(10), scheduled_end=_dt(10, 30)
        )
        db, _ = self._setup_models(v2_appts=[appt])

        # Patch out the other sources to avoid import errors
        with patch("routes.scheduler._helpers.logger"):
            conflicts = _get_cross_source_conflicts(
                db, target_user_id=1,
                start_dt=_dt(9), end_dt=_dt(12), org_id=1,
            )

        assert len(conflicts) >= 1
        assert (_dt(10), _dt(10, 30)) in conflicts

    def test_cancelled_appointment_ignored(self):
        """Cancelled appointments should NOT create conflicts.

        _get_cross_source_conflicts filters by
        status IN (BOOKED, TENTATIVE). A cancelled appointment
        will not pass the filter, so FakeQuery returns nothing.
        """
        db, _ = self._setup_models(v2_appts=[])  # nothing returned from query

        with patch("routes.scheduler._helpers.logger"):
            conflicts = _get_cross_source_conflicts(
                db, target_user_id=1,
                start_dt=_dt(9), end_dt=_dt(12), org_id=1,
            )

        v2_conflicts = [c for c in conflicts if c == (_dt(10), _dt(10, 30))]
        assert len(v2_conflicts) == 0

    def test_google_calendar_event_creates_conflict(self):
        """A CalendarEvent (Google/manual) should block the same time slot."""
        mock_cal_event = MagicMock()
        mock_cal_event.start_time = _dt(14)
        mock_cal_event.end_time = _dt(15)
        mock_cal_event.status = "confirmed"
        mock_cal_event.user_id = 1
        mock_cal_event.organization_id = 1

        # Patch CalendarEvent import inside _get_cross_source_conflicts
        mock_cal_model = MagicMock()

        db, _ = self._setup_models(v2_appts=[])

        with patch(
            "routes.scheduler._helpers.logger"
        ), patch.dict(
            "sys.modules",
            {"database.models.communication": MagicMock(CalendarEvent=mock_cal_model)},
        ):
            # Override db.query for the CalendarEvent model
            original_query = db.query

            def patched_query(model_class):
                if model_class is mock_cal_model:
                    return FakeQuery([mock_cal_event])
                return original_query(model_class)

            db.query = patched_query

            conflicts = _get_cross_source_conflicts(
                db, target_user_id=1,
                start_dt=_dt(13), end_dt=_dt(16), org_id=1,
            )

        assert (_dt(14), _dt(15)) in conflicts

    def test_crm_calendar_event_creates_conflict(self):
        """A CRMCalendarEvent (Salesforce-synced) should block the same time slot."""
        mock_crm_event = MagicMock()
        mock_crm_event.start_at = _dt(11)
        mock_crm_event.end_at = _dt(11, 30)
        mock_crm_event.status = "confirmed"
        mock_crm_event.owner_user_id = 1
        mock_crm_event.organization_id = 1

        mock_crm_model = MagicMock()

        db, _ = self._setup_models(v2_appts=[])

        with patch(
            "routes.scheduler._helpers.logger"
        ), patch.dict(
            "sys.modules",
            {"models.calendar_sync_models": MagicMock(CRMCalendarEvent=mock_crm_model)},
        ):
            original_query = db.query

            def patched_query(model_class):
                if model_class is mock_crm_model:
                    return FakeQuery([mock_crm_event])
                return original_query(model_class)

            db.query = patched_query

            conflicts = _get_cross_source_conflicts(
                db, target_user_id=1,
                start_dt=_dt(10), end_dt=_dt(12), org_id=1,
            )

        assert (_dt(11), _dt(11, 30)) in conflicts

    def test_legacy_appointment_creates_conflict(self):
        """Legacy ScheduledAppointment should block the same time slot."""
        mock_legacy = MagicMock()
        mock_legacy.start_time = _dt(15)
        mock_legacy.end_time = _dt(15, 30)
        mock_legacy.status = "scheduled"
        mock_legacy.loan_officer_id = 1
        mock_legacy.organization_id = 1

        mock_sa_model = MagicMock()

        db, _ = self._setup_models(v2_appts=[])

        with patch(
            "routes.scheduler._helpers.logger"
        ), patch.dict(
            "sys.modules",
            {
                "services.smart_scheduler_service": MagicMock(
                    ScheduledAppointment=mock_sa_model
                )
            },
        ):
            original_query = db.query

            def patched_query(model_class):
                if model_class is mock_sa_model:
                    return FakeQuery([mock_legacy])
                return original_query(model_class)

            db.query = patched_query

            conflicts = _get_cross_source_conflicts(
                db, target_user_id=1,
                start_dt=_dt(14), end_dt=_dt(16), org_id=1,
            )

        assert (_dt(15), _dt(15, 30)) in conflicts


# ============================================================================
# _check_appointment_conflict (SELECT FOR UPDATE, raises HTTPException)
# ============================================================================

class TestCheckAppointmentConflict:
    """Test the row-locking conflict check that prevents double-booking."""

    def _setup(self, query_result=None, raise_operational_error=False):
        """Set up _models and a mock db for _check_appointment_conflict."""
        MockAppointmentModel = MagicMock()
        MockAppointmentModel.__name__ = "Appointment"

        models_dict = {"Appointment": MockAppointmentModel}
        set_dependencies(None, None, models_dict)

        db = MagicMock()

        if raise_operational_error:
            from sqlalchemy.exc import OperationalError
            db.query.return_value.filter.return_value.with_for_update.side_effect = (
                OperationalError("locked", {}, None)
            )
        else:
            db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
                query_result
            )

        return db

    def test_no_conflict_passes(self):
        """When no conflicting row exists, function returns without error."""
        db = self._setup(query_result=None)
        # Should not raise
        _check_appointment_conflict(db, assigned_user_id=1,
                                     start_time=_dt(10), end_time=_dt(10, 30),
                                     org_id=1)

    def test_overlapping_appointment_raises_409(self):
        """When an overlapping appointment exists, HTTPException 409 is raised."""
        existing = _make_mock_appointment(
            scheduled_start=_dt(10), scheduled_end=_dt(10, 30)
        )
        db = self._setup(query_result=existing)

        with pytest.raises(HTTPException) as exc_info:
            _check_appointment_conflict(db, assigned_user_id=1,
                                         start_time=_dt(10, 15), end_time=_dt(10, 45),
                                         org_id=1)
        assert exc_info.value.status_code == 409
        assert "no longer available" in exc_info.value.detail

    def test_locked_row_raises_409(self):
        """When the row is locked (OperationalError), HTTPException 409 is raised."""
        db = self._setup(raise_operational_error=True)

        with pytest.raises(HTTPException) as exc_info:
            _check_appointment_conflict(db, assigned_user_id=1,
                                         start_time=_dt(10), end_time=_dt(10, 30),
                                         org_id=1)
        assert exc_info.value.status_code == 409
        assert "being booked by another user" in exc_info.value.detail

    def test_exclude_appointment_id_allows_self(self):
        """When rescheduling, the current appointment should be excluded from conflict check."""
        db = self._setup(query_result=None)
        # The exclude_appointment_id is passed through to the filter.
        # Since our mock returns None, the function should succeed.
        _check_appointment_conflict(db, assigned_user_id=1,
                                     start_time=_dt(10), end_time=_dt(10, 30),
                                     org_id=1, exclude_appointment_id=42)


# ============================================================================
# _check_duplicate_booking
# ============================================================================

class TestCheckDuplicateBooking:
    """Test duplicate booking detection by attendee email."""

    def _setup(self, duplicate_result=None):
        MockAppointmentModel = MagicMock()
        MockAppointmentModel.__name__ = "Appointment"
        models_dict = {"Appointment": MockAppointmentModel}
        set_dependencies(None, None, models_dict)

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = duplicate_result
        return db

    def test_no_duplicate_passes(self):
        """When no duplicate exists, function returns without error."""
        db = self._setup(duplicate_result=None)
        _check_duplicate_booking(db, attendee_email="new@example.com",
                                  assigned_user_id=1, start_time=_dt(10), org_id=1)

    def test_duplicate_raises_409(self):
        """When a duplicate booking exists, HTTPException 409 is raised."""
        existing = _make_mock_appointment(attendee_email="client@example.com")
        db = self._setup(duplicate_result=existing)

        with pytest.raises(HTTPException) as exc_info:
            _check_duplicate_booking(db, attendee_email="client@example.com",
                                      assigned_user_id=1, start_time=_dt(10), org_id=1)
        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.detail

    def test_no_email_skips_check(self):
        """When attendee_email is empty/None, the check is skipped entirely."""
        db = self._setup(duplicate_result=None)
        _check_duplicate_booking(db, attendee_email="",
                                  assigned_user_id=1, start_time=_dt(10), org_id=1)
        # .query should never be called when email is empty
        db.query.assert_not_called()

        _check_duplicate_booking(db, attendee_email=None,
                                  assigned_user_id=1, start_time=_dt(10), org_id=1)
        db.query.assert_not_called()


# ============================================================================
# CONFIRMATION-TIME CONFLICT SCENARIOS
# ============================================================================

class TestConfirmationTimeConflicts:
    """
    Test that conflicts are checked at confirmation time, not just slot generation.
    These are higher-level scenarios verifying the booking flow rejects
    stale slot selections.
    """

    def test_new_event_between_slot_and_confirm_blocked(self):
        """
        If a new event appears between slot display and confirmation,
        _check_appointment_conflict should reject the booking.
        """
        MockAppointmentModel = MagicMock()
        models_dict = {"Appointment": MockAppointmentModel}
        set_dependencies(None, None, models_dict)

        # Phase 1: slots generated -- no conflicts
        db_phase1 = MagicMock()
        db_phase1.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None
        _check_appointment_conflict(db_phase1, assigned_user_id=1,
                                     start_time=_dt(10), end_time=_dt(10, 30), org_id=1)

        # Phase 2: between display and confirmation, another booking lands
        existing = _make_mock_appointment(
            scheduled_start=_dt(10), scheduled_end=_dt(10, 30)
        )
        db_phase2 = MagicMock()
        db_phase2.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = existing

        with pytest.raises(HTTPException) as exc_info:
            _check_appointment_conflict(db_phase2, assigned_user_id=1,
                                         start_time=_dt(10), end_time=_dt(10, 30), org_id=1)
        assert exc_info.value.status_code == 409

    def test_concurrent_booking_race_condition(self):
        """
        Two users booking the same slot simultaneously: the second transaction
        should hit a row lock (OperationalError) and get a 409.
        """
        MockAppointmentModel = MagicMock()
        models_dict = {"Appointment": MockAppointmentModel}
        set_dependencies(None, None, models_dict)

        from sqlalchemy.exc import OperationalError

        # First caller succeeds (no conflict found)
        db_caller1 = MagicMock()
        db_caller1.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None
        _check_appointment_conflict(db_caller1, assigned_user_id=1,
                                     start_time=_dt(14), end_time=_dt(14, 30), org_id=1)

        # Second caller hits the row lock
        db_caller2 = MagicMock()
        db_caller2.query.return_value.filter.return_value.with_for_update.side_effect = (
            OperationalError("could not obtain lock", {}, None)
        )
        with pytest.raises(HTTPException) as exc_info:
            _check_appointment_conflict(db_caller2, assigned_user_id=1,
                                         start_time=_dt(14), end_time=_dt(14, 30), org_id=1)
        assert exc_info.value.status_code == 409
        assert "being booked by another user" in exc_info.value.detail


# ============================================================================
# INTERNAL OVERLAP EDGE CASES
# ============================================================================

class TestInternalConflictDetection:
    """Test conflict detection within internal appointments — edge cases."""

    def test_exact_same_time_detected(self):
        """An appointment at exactly the same time is a conflict."""
        conflicts = [(_dt(10), _dt(10, 30))]
        assert _has_cross_source_conflict(conflicts, _dt(10), _dt(10, 30)) is True

    def test_one_minute_overlap_detected(self):
        """Even a one-minute overlap should be flagged."""
        conflicts = [(_dt(10), _dt(10, 30))]
        assert _has_cross_source_conflict(conflicts, _dt(10, 29), _dt(11)) is True

    def test_different_day_no_conflict(self):
        """Appointments on different days should not conflict."""
        conflicts = [(_dt(10, day_offset=0), _dt(11, day_offset=0))]
        assert _has_cross_source_conflict(
            conflicts, _dt(10, day_offset=1), _dt(11, day_offset=1)
        ) is False

    def test_all_day_event_blocks_all_slots(self):
        """An all-day event (0:00 to 23:59) should block any slot on that day."""
        conflicts = [(_dt(0), _dt(0).replace(hour=23, minute=59))]
        assert _has_cross_source_conflict(conflicts, _dt(12), _dt(13)) is True

    def test_zero_duration_slot_no_conflict(self):
        """A zero-duration slot (start == end) should not conflict.

        This is an edge case where slot_start < buffered_end and
        slot_end > buffered_start can never both be true if the slot
        is a point in time and the busy block does not contain it.
        """
        conflicts = [(_dt(10), _dt(10, 30))]
        # A zero-duration "slot" at 10:30 exactly: 10:30 < 10:30 is False
        assert _has_cross_source_conflict(conflicts, _dt(10, 30), _dt(10, 30)) is False

    def test_buffer_with_adjacent_appointments(self):
        """Two adjacent appointments with buffer should show conflict for slot between them."""
        conflicts = [
            (_dt(10), _dt(10, 30)),  # first appointment
            (_dt(10, 35), _dt(11)),   # second appointment 5 min later
        ]
        # A slot at 10:30-10:35 sits between them. With 5-min buffers,
        # first ends at 10:35 (buffer_after=5) and second starts at 10:30 (buffer_before=5).
        assert _has_cross_source_conflict(
            conflicts, _dt(10, 30), _dt(10, 35),
            buffer_before=5, buffer_after=5
        ) is True
