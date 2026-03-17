"""
Tests for the Appointment State Machine.

Covers:
- All valid transitions succeed
- All invalid transitions raise InvalidStateTransitionError
- Terminal states reject all transitions
- History records are created on valid transitions
- Status-specific timestamps are set correctly
- Change source and reason are recorded
"""

import sys
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.appointment_state_machine import AppointmentStateMachine
from exceptions import InvalidStateTransitionError


# =============================================================================
# Fixtures
# =============================================================================

class FakeAppointmentStatusHistory:
    """Mock for the AppointmentStatusHistory model class."""
    instances = []

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        FakeAppointmentStatusHistory.instances.append(self)

    @classmethod
    def reset(cls):
        cls.instances = []


class FakeAppointment:
    """Mock appointment with status tracking."""
    def __init__(self, id=1, status="booked"):
        self.id = id
        self.status = status
        self.status_changed_at = None
        self.status_changed_by = None
        self.completed_at = None
        self.no_show_at = None
        self.cancelled_at = None
        self.cancellation_reason = None


class FakeDB:
    """Mock DB session."""
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def appointment():
    return FakeAppointment(id=42, status="booked")


@pytest.fixture(autouse=True)
def reset_history():
    FakeAppointmentStatusHistory.reset()
    yield
    FakeAppointmentStatusHistory.reset()


# =============================================================================
# Test: can_transition
# =============================================================================

class TestCanTransition:
    """Tests for AppointmentStateMachine.can_transition()."""

    @pytest.mark.parametrize("from_status,to_status", [
        ("tentative", "booked"),
        ("tentative", "cancelled"),
        ("booked", "confirmed"),
        ("booked", "cancelled"),
        ("booked", "rescheduled"),
        ("confirmed", "in_progress"),
        ("confirmed", "no_show"),
        ("confirmed", "cancelled"),
        ("confirmed", "rescheduled"),
        ("in_progress", "completed"),
        ("in_progress", "no_show"),
        ("no_show", "rescheduled"),
        ("rescheduled", "booked"),
        ("rescheduled", "confirmed"),
    ])
    def test_valid_transitions(self, from_status, to_status):
        """All transitions defined in the TRANSITIONS map should be allowed."""
        assert AppointmentStateMachine.can_transition(from_status, to_status) is True

    @pytest.mark.parametrize("from_status,to_status", [
        # Terminal states cannot go anywhere
        ("completed", "booked"),
        ("completed", "cancelled"),
        ("completed", "rescheduled"),
        ("cancelled", "booked"),
        ("cancelled", "completed"),
        ("cancelled", "rescheduled"),
        # Backward/illegal transitions
        ("booked", "tentative"),
        ("confirmed", "tentative"),
        ("confirmed", "booked"),
        ("in_progress", "booked"),
        ("in_progress", "confirmed"),
        ("in_progress", "cancelled"),
        ("in_progress", "rescheduled"),
        ("tentative", "completed"),
        ("tentative", "confirmed"),
        ("tentative", "in_progress"),
        ("tentative", "no_show"),
        ("tentative", "rescheduled"),
        ("booked", "completed"),
        ("booked", "in_progress"),
        ("booked", "no_show"),
        ("no_show", "booked"),
        ("no_show", "completed"),
        ("no_show", "cancelled"),
        ("no_show", "confirmed"),
        ("rescheduled", "completed"),
        ("rescheduled", "cancelled"),
        ("rescheduled", "in_progress"),
        ("rescheduled", "no_show"),
        ("rescheduled", "tentative"),
    ])
    def test_invalid_transitions(self, from_status, to_status):
        """Transitions not in the TRANSITIONS map should be rejected."""
        assert AppointmentStateMachine.can_transition(from_status, to_status) is False

    def test_unknown_from_status(self):
        """Unknown from_status should return False."""
        assert AppointmentStateMachine.can_transition("nonexistent", "booked") is False

    def test_same_status_transition(self):
        """Transitioning to the same status should not be allowed (not in any transition list)."""
        for status in AppointmentStateMachine.TRANSITIONS:
            assert AppointmentStateMachine.can_transition(status, status) is False


# =============================================================================
# Test: get_allowed_transitions
# =============================================================================

class TestGetAllowedTransitions:
    """Tests for AppointmentStateMachine.get_allowed_transitions()."""

    def test_tentative_transitions(self):
        assert set(AppointmentStateMachine.get_allowed_transitions("tentative")) == {"booked", "cancelled"}

    def test_booked_transitions(self):
        assert set(AppointmentStateMachine.get_allowed_transitions("booked")) == {"confirmed", "cancelled", "rescheduled"}

    def test_confirmed_transitions(self):
        assert set(AppointmentStateMachine.get_allowed_transitions("confirmed")) == {"in_progress", "no_show", "cancelled", "rescheduled"}

    def test_in_progress_transitions(self):
        assert set(AppointmentStateMachine.get_allowed_transitions("in_progress")) == {"completed", "no_show"}

    def test_completed_no_transitions(self):
        assert AppointmentStateMachine.get_allowed_transitions("completed") == []

    def test_cancelled_no_transitions(self):
        assert AppointmentStateMachine.get_allowed_transitions("cancelled") == []

    def test_no_show_transitions(self):
        assert set(AppointmentStateMachine.get_allowed_transitions("no_show")) == {"rescheduled"}

    def test_rescheduled_transitions(self):
        assert set(AppointmentStateMachine.get_allowed_transitions("rescheduled")) == {"booked", "confirmed"}

    def test_unknown_status(self):
        assert AppointmentStateMachine.get_allowed_transitions("unknown_status") == []


# =============================================================================
# Test: is_terminal
# =============================================================================

class TestIsTerminal:
    """Tests for AppointmentStateMachine.is_terminal()."""

    def test_completed_is_terminal(self):
        assert AppointmentStateMachine.is_terminal("completed") is True

    def test_cancelled_is_terminal(self):
        assert AppointmentStateMachine.is_terminal("cancelled") is True

    def test_booked_is_not_terminal(self):
        assert AppointmentStateMachine.is_terminal("booked") is False

    def test_tentative_is_not_terminal(self):
        assert AppointmentStateMachine.is_terminal("tentative") is False

    def test_confirmed_is_not_terminal(self):
        assert AppointmentStateMachine.is_terminal("confirmed") is False

    def test_in_progress_is_not_terminal(self):
        assert AppointmentStateMachine.is_terminal("in_progress") is False

    def test_no_show_is_not_terminal(self):
        assert AppointmentStateMachine.is_terminal("no_show") is False

    def test_rescheduled_is_not_terminal(self):
        assert AppointmentStateMachine.is_terminal("rescheduled") is False


# =============================================================================
# Test: transition (valid)
# =============================================================================

class TestTransitionValid:
    """Tests for valid transitions via AppointmentStateMachine.transition()."""

    def _do_transition(self, db, appt, to_status, changed_by=1, reason=None, change_source="manual"):
        """Helper to perform a transition with mocked history model."""
        with patch.object(
            AppointmentStateMachine, '_get_history_model',
            return_value=FakeAppointmentStatusHistory
        ):
            AppointmentStateMachine.transition(
                db=db,
                appointment=appt,
                to_status=to_status,
                changed_by=changed_by,
                reason=reason,
                change_source=change_source,
            )

    def test_booked_to_confirmed(self, db, appointment):
        self._do_transition(db, appointment, "confirmed", changed_by=5)
        assert appointment.status.value == "confirmed"
        assert appointment.status_changed_at is not None
        assert appointment.status_changed_by == 5

    def test_booked_to_cancelled(self, db, appointment):
        self._do_transition(db, appointment, "cancelled", changed_by=3, reason="Customer requested")
        assert appointment.status.value == "cancelled"
        assert appointment.cancelled_at is not None
        assert appointment.cancellation_reason == "Customer requested"

    def test_confirmed_to_completed(self, db):
        appt = FakeAppointment(id=10, status="confirmed")
        # First confirm -> in_progress
        self._do_transition(db, appt, "in_progress", changed_by=1)
        assert appt.status.value == "in_progress"
        # Then in_progress -> completed
        self._do_transition(db, appt, "completed", changed_by=1)
        assert appt.status.value == "completed"
        assert appt.completed_at is not None

    def test_confirmed_to_no_show(self, db):
        appt = FakeAppointment(id=11, status="confirmed")
        self._do_transition(db, appt, "no_show", changed_by=2)
        assert appt.status.value == "no_show"
        assert appt.no_show_at is not None

    def test_in_progress_to_completed(self, db):
        appt = FakeAppointment(id=12, status="in_progress")
        self._do_transition(db, appt, "completed", changed_by=1)
        assert appt.status.value == "completed"
        assert appt.completed_at is not None

    def test_no_show_to_rescheduled(self, db):
        appt = FakeAppointment(id=13, status="no_show")
        self._do_transition(db, appt, "rescheduled", changed_by=1, reason="Rescheduling after missed")
        assert appt.status.value == "rescheduled"

    def test_rescheduled_to_booked(self, db):
        appt = FakeAppointment(id=14, status="rescheduled")
        self._do_transition(db, appt, "booked", changed_by=1)
        assert appt.status.value == "booked"

    def test_tentative_to_booked(self, db):
        appt = FakeAppointment(id=15, status="tentative")
        self._do_transition(db, appt, "booked", changed_by=1)
        assert appt.status.value == "booked"


# =============================================================================
# Test: transition (invalid - should raise)
# =============================================================================

class TestTransitionInvalid:
    """Tests that invalid transitions raise InvalidStateTransitionError."""

    def _expect_failure(self, db, appt, to_status):
        with patch.object(
            AppointmentStateMachine, '_get_history_model',
            return_value=FakeAppointmentStatusHistory
        ):
            with pytest.raises(InvalidStateTransitionError) as exc_info:
                AppointmentStateMachine.transition(
                    db=db,
                    appointment=appt,
                    to_status=to_status,
                    changed_by=1,
                )
            return exc_info.value

    def test_completed_to_anything(self, db):
        """Terminal state 'completed' cannot transition."""
        appt = FakeAppointment(id=20, status="completed")
        for target in ["booked", "confirmed", "cancelled", "rescheduled", "in_progress", "no_show", "tentative"]:
            err = self._expect_failure(db, appt, target)
            assert err.from_status == "completed"
            assert err.to_status == target
            assert err.allowed_transitions == []

    def test_cancelled_to_anything(self, db):
        """Terminal state 'cancelled' cannot transition."""
        appt = FakeAppointment(id=21, status="cancelled")
        for target in ["booked", "confirmed", "completed", "rescheduled", "in_progress", "no_show", "tentative"]:
            err = self._expect_failure(db, appt, target)
            assert err.from_status == "cancelled"
            assert err.to_status == target
            assert err.allowed_transitions == []

    def test_booked_to_completed_skipping_stages(self, db, appointment):
        """Cannot jump from booked directly to completed."""
        err = self._expect_failure(db, appointment, "completed")
        assert "confirmed" in err.allowed_transitions
        assert "completed" not in err.allowed_transitions

    def test_tentative_to_completed(self, db):
        """Cannot jump from tentative to completed."""
        appt = FakeAppointment(id=22, status="tentative")
        self._expect_failure(db, appt, "completed")

    def test_in_progress_to_cancelled(self, db):
        """Cannot cancel an in-progress appointment (must complete or no_show)."""
        appt = FakeAppointment(id=23, status="in_progress")
        err = self._expect_failure(db, appt, "cancelled")
        assert set(err.allowed_transitions) == {"completed", "no_show"}

    def test_no_show_to_completed(self, db):
        """Cannot complete a no-show (can only reschedule)."""
        appt = FakeAppointment(id=24, status="no_show")
        self._expect_failure(db, appt, "completed")

    def test_exception_has_correct_code(self, db, appointment):
        """InvalidStateTransitionError should have the INVALID_STATE_TRANSITION code."""
        err = self._expect_failure(db, appointment, "completed")
        assert err.code == "INVALID_STATE_TRANSITION"

    def test_exception_has_details(self, db, appointment):
        """The exception details dict should contain transition metadata."""
        err = self._expect_failure(db, appointment, "completed")
        assert err.details["from_status"] == "booked"
        assert err.details["to_status"] == "completed"
        assert err.details["entity_type"] == "Appointment"


# =============================================================================
# Test: History record creation
# =============================================================================

class TestHistoryRecords:
    """Tests that AppointmentStatusHistory records are created correctly."""

    def _do_transition(self, db, appt, to_status, changed_by=1, reason=None, change_source="manual"):
        with patch.object(
            AppointmentStateMachine, '_get_history_model',
            return_value=FakeAppointmentStatusHistory
        ):
            AppointmentStateMachine.transition(
                db=db,
                appointment=appt,
                to_status=to_status,
                changed_by=changed_by,
                reason=reason,
                change_source=change_source,
            )

    def test_history_record_created(self, db, appointment):
        """A history record should be added to the session on valid transition."""
        self._do_transition(db, appointment, "confirmed", changed_by=7)
        assert len(db.added) == 1
        history = db.added[0]
        assert history.from_status == "booked"
        assert history.to_status == "confirmed"
        assert history.changed_by == 7
        assert history.change_source == "manual"

    def test_history_record_with_reason(self, db, appointment):
        """Reason should be stored in the history record."""
        self._do_transition(db, appointment, "cancelled", reason="Weather emergency")
        history = db.added[0]
        assert history.reason == "Weather emergency"

    def test_history_record_change_source(self, db, appointment):
        """Change source should be recorded (ai, system, webhook, manual)."""
        self._do_transition(db, appointment, "confirmed", change_source="ai")
        history = db.added[0]
        assert history.change_source == "ai"

    def test_history_timestamp_is_set(self, db, appointment):
        """History record should have a changed_at timestamp."""
        self._do_transition(db, appointment, "confirmed")
        history = db.added[0]
        assert history.changed_at is not None
        assert isinstance(history.changed_at, datetime)

    def test_multiple_transitions_create_multiple_records(self, db):
        """Each transition should create its own history record."""
        appt = FakeAppointment(id=30, status="tentative")
        self._do_transition(db, appt, "booked")
        self._do_transition(db, appt, "confirmed")
        self._do_transition(db, appt, "in_progress")
        self._do_transition(db, appt, "completed")
        assert len(db.added) == 4
        assert db.added[0].from_status == "tentative"
        assert db.added[0].to_status == "booked"
        assert db.added[1].from_status == "booked"
        assert db.added[1].to_status == "confirmed"
        assert db.added[2].from_status == "confirmed"
        assert db.added[2].to_status == "in_progress"
        assert db.added[3].from_status == "in_progress"
        assert db.added[3].to_status == "completed"

    def test_no_history_when_model_not_found(self, db, appointment):
        """If the history model cannot be resolved, transition still succeeds but no record is added."""
        with patch.object(
            AppointmentStateMachine, '_get_history_model',
            return_value=None
        ):
            AppointmentStateMachine.transition(
                db=db,
                appointment=appointment,
                to_status="confirmed",
                changed_by=1,
            )
        # Transition still happens
        assert appointment.status.value == "confirmed"
        # But no history record
        assert len(db.added) == 0


# =============================================================================
# Test: Status-specific timestamp updates
# =============================================================================

class TestStatusTimestamps:
    """Tests that status-specific timestamps are set during transitions."""

    def _do_transition(self, db, appt, to_status, **kwargs):
        with patch.object(
            AppointmentStateMachine, '_get_history_model',
            return_value=FakeAppointmentStatusHistory
        ):
            AppointmentStateMachine.transition(db=db, appointment=appt, to_status=to_status, **kwargs)

    def test_completed_sets_completed_at(self, db):
        appt = FakeAppointment(id=40, status="in_progress")
        self._do_transition(db, appt, "completed", changed_by=1)
        assert appt.completed_at is not None
        assert appt.no_show_at is None
        assert appt.cancelled_at is None

    def test_no_show_sets_no_show_at(self, db):
        appt = FakeAppointment(id=41, status="confirmed")
        self._do_transition(db, appt, "no_show", changed_by=1)
        assert appt.no_show_at is not None
        assert appt.completed_at is None
        assert appt.cancelled_at is None

    def test_cancelled_sets_cancelled_at_and_reason(self, db):
        appt = FakeAppointment(id=42, status="booked")
        self._do_transition(db, appt, "cancelled", changed_by=1, reason="Double booked")
        assert appt.cancelled_at is not None
        assert appt.cancellation_reason == "Double booked"
        assert appt.completed_at is None
        assert appt.no_show_at is None

    def test_confirmed_does_not_set_terminal_timestamps(self, db):
        appt = FakeAppointment(id=43, status="booked")
        self._do_transition(db, appt, "confirmed", changed_by=1)
        assert appt.completed_at is None
        assert appt.no_show_at is None
        assert appt.cancelled_at is None

    def test_status_changed_at_always_set(self, db):
        appt = FakeAppointment(id=44, status="tentative")
        self._do_transition(db, appt, "booked", changed_by=1)
        assert appt.status_changed_at is not None


# =============================================================================
# Test: Enum handling
# =============================================================================

class TestEnumHandling:
    """Tests that the state machine handles enum vs string status values correctly."""

    def test_status_as_enum_object(self, db):
        """Appointment with status as an enum object should work."""
        from smart_scheduler_models import AppointmentStatus
        appt = FakeAppointment(id=50, status=AppointmentStatus.BOOKED)
        with patch.object(
            AppointmentStateMachine, '_get_history_model',
            return_value=FakeAppointmentStatusHistory
        ):
            AppointmentStateMachine.transition(db=db, appointment=appt, to_status="confirmed", changed_by=1)
        assert appt.status.value == "confirmed"

    def test_can_transition_with_enum(self):
        """can_transition should accept enum values."""
        from smart_scheduler_models import AppointmentStatus
        assert AppointmentStateMachine.can_transition(AppointmentStatus.BOOKED, "confirmed") is True
        assert AppointmentStateMachine.can_transition(AppointmentStatus.COMPLETED, "booked") is False

    def test_get_allowed_with_enum(self):
        """get_allowed_transitions should accept enum values."""
        from smart_scheduler_models import AppointmentStatus
        allowed = AppointmentStateMachine.get_allowed_transitions(AppointmentStatus.BOOKED)
        assert "confirmed" in allowed


# =============================================================================
# Test: Full lifecycle scenarios
# =============================================================================

class TestFullLifecycle:
    """Integration-style tests for complete appointment lifecycles."""

    def _do_transition(self, db, appt, to_status, **kwargs):
        with patch.object(
            AppointmentStateMachine, '_get_history_model',
            return_value=FakeAppointmentStatusHistory
        ):
            AppointmentStateMachine.transition(db=db, appointment=appt, to_status=to_status, **kwargs)

    def test_happy_path_lifecycle(self, db):
        """Complete lifecycle: tentative -> booked -> confirmed -> in_progress -> completed."""
        appt = FakeAppointment(id=60, status="tentative")
        self._do_transition(db, appt, "booked", changed_by=1, change_source="system")
        self._do_transition(db, appt, "confirmed", changed_by=1, change_source="webhook")
        self._do_transition(db, appt, "in_progress", changed_by=1, change_source="system")
        self._do_transition(db, appt, "completed", changed_by=1, change_source="manual")
        assert appt.status.value == "completed"
        assert appt.completed_at is not None
        assert len(db.added) == 4

    def test_reschedule_lifecycle(self, db):
        """Lifecycle with reschedule: booked -> rescheduled -> booked -> confirmed -> completed."""
        appt = FakeAppointment(id=61, status="booked")
        self._do_transition(db, appt, "rescheduled", changed_by=1, reason="Customer requested new time")
        self._do_transition(db, appt, "booked", changed_by=1)
        self._do_transition(db, appt, "confirmed", changed_by=2, change_source="ai")
        self._do_transition(db, appt, "in_progress", changed_by=2, change_source="system")
        self._do_transition(db, appt, "completed", changed_by=2)
        assert appt.status.value == "completed"
        assert len(db.added) == 5

    def test_no_show_then_reschedule(self, db):
        """Lifecycle: confirmed -> no_show -> rescheduled -> confirmed."""
        appt = FakeAppointment(id=62, status="confirmed")
        self._do_transition(db, appt, "no_show", changed_by=1)
        assert appt.no_show_at is not None
        self._do_transition(db, appt, "rescheduled", changed_by=1, reason="Will try again")
        self._do_transition(db, appt, "confirmed", changed_by=1)
        assert appt.status.value == "confirmed"

    def test_cannot_complete_after_cancel(self, db):
        """Once cancelled, cannot transition to completed."""
        appt = FakeAppointment(id=63, status="booked")
        self._do_transition(db, appt, "cancelled", changed_by=1, reason="Changed mind")
        with patch.object(
            AppointmentStateMachine, '_get_history_model',
            return_value=FakeAppointmentStatusHistory
        ):
            with pytest.raises(InvalidStateTransitionError):
                AppointmentStateMachine.transition(
                    db=db, appointment=appt, to_status="completed", changed_by=1
                )
        # Status should still be cancelled
        assert appt.status.value == "cancelled"
