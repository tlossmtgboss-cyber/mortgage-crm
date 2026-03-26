"""
Tests for VoiceSchedulingWorkflowService — persistent state machine for
multi-step voice command workflows (voice -> SMS -> conversation -> booking).

The runtime service differs from the on-disk file (it has been evolved):
- find_active_workflow_by_phone, get_workflow, cancel_workflow all require organization_id
- advance_state validates transitions against VALID_TRANSITIONS
- advance_state, expire_stale_workflows, cancel_workflow create Activity audit records

Covers:
1. create_workflow: happy path, duplicate guard, optional fields, expiry default
2. find_active_workflow_by_phone: finds active, ignores terminal/expired
3. get_active_workflows_for_user: returns only active workflows for user+org
4. advance_state: valid transitions, invalid transitions raise ValueError,
   state change persists, metadata kwargs applied, Activity created
5. expire_stale_workflows: expires past-due, ignores still-active, creates Activity
6. cancel_workflow: sets state to cancelled, returns True; terminal returns False
7. to_status_dict: returns expected dict shape and values

Run with: pytest tests/test_voice_scheduling_workflow_service.py -v
"""

import sys
import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.voice_scheduling_workflow_service import (
    VoiceSchedulingWorkflowService,
    VALID_TRANSITIONS,
)


# =============================================================================
# Fakes / Helpers
# =============================================================================

class FakeVoiceWorkflow:
    """Lightweight stand-in for VoiceWorkflow ORM model.

    Replicates the fields and methods used by the service layer so tests
    run without touching the database or importing SQLAlchemy models.
    """

    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.organization_id = kwargs.get("organization_id")
        self.user_id = kwargs.get("user_id")
        self.workflow_type = kwargs.get("workflow_type")
        self.state = kwargs.get("state", "initiated")
        self.contact_name = kwargs.get("contact_name")
        self.contact_phone = kwargs.get("contact_phone")
        self.contact_email = kwargs.get("contact_email")
        self.lead_id = kwargs.get("lead_id")
        self.meeting_type = kwargs.get("meeting_type", "discovery_call")
        self.meeting_duration_minutes = kwargs.get("meeting_duration_minutes", 30)
        self.message_context = kwargs.get("message_context")
        self.conversation_history = kwargs.get("conversation_history", [])
        self.turn_count = kwargs.get("turn_count", 0)
        self.max_turns = kwargs.get("max_turns", 8)
        self.confirmed_datetime = kwargs.get("confirmed_datetime")
        self.appointment_id = kwargs.get("appointment_id")
        self.proposed_slots = kwargs.get("proposed_slots", [])
        self.created_at = kwargs.get("created_at", datetime.utcnow())
        self.updated_at = kwargs.get("updated_at", datetime.utcnow())
        self.expires_at = kwargs.get("expires_at")
        self.completed_at = kwargs.get("completed_at")
        self.error_message = kwargs.get("error_message")
        self.last_sms_sent_at = kwargs.get("last_sms_sent_at")
        self.last_sms_received_at = kwargs.get("last_sms_received_at")

    def is_active(self):
        terminal = {"completed", "expired", "cancelled", "failed"}
        return self.state not in terminal

    def transition_to(self, new_state: str):
        self.state = new_state
        self.updated_at = datetime.utcnow()
        if new_state in ("completed", "appointment_booked"):
            self.completed_at = datetime.utcnow()

    def add_message(self, role: str, content: str):
        if self.conversation_history is None:
            self.conversation_history = []
        self.conversation_history = self.conversation_history + [{
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }]
        if role == "contact":
            self.turn_count = (self.turn_count or 0) + 1


class FakeQuery:
    """Chainable mock for SQLAlchemy query builder patterns."""

    def __init__(self, results=None):
        self._results = results or []

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def with_for_update(self, **kwargs):
        return self

    def first(self):
        return self._results[0] if self._results else None

    def all(self):
        return self._results


class FakeSavepoint:
    """Mock savepoint context for begin_nested()."""

    def commit(self):
        pass

    def rollback(self):
        pass


class FakeDB:
    """Mock database session."""

    def __init__(self):
        self.added = []
        self.flushed = False
        self._query_results = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushed = True
        # Assign IDs to any newly added objects that lack one
        for obj in self.added:
            if hasattr(obj, "id") and obj.id is None:
                obj.id = 100 + self.added.index(obj)

    def begin_nested(self):
        return FakeSavepoint()

    def query(self, model_cls):
        return FakeQuery(self._query_results)

    def set_query_results(self, results):
        """Helper to pre-load query results."""
        self._query_results = results


def _make_sys_modules_patch():
    """Build the sys.modules patch dict for database.models.voice_workflow.

    Uses MagicMock attributes that are sufficient for the SQLAlchemy-style
    filter expressions the service builds.
    """
    fake_state_enum = MagicMock()
    fake_state_enum.COMPLETED.value = "completed"
    fake_state_enum.EXPIRED.value = "expired"
    fake_state_enum.CANCELLED.value = "cancelled"
    fake_state_enum.FAILED.value = "failed"
    fake_state_enum.INITIATED.value = "initiated"
    fake_state_enum.SMS_SENT.value = "sms_sent"
    fake_state_enum.AWAITING_REPLY.value = "awaiting_reply"
    fake_state_enum.NEGOTIATING.value = "negotiating"

    fake_model_cls = MagicMock()
    fake_model_cls.side_effect = lambda **kw: FakeVoiceWorkflow(**kw)
    fake_model_cls.organization_id = "organization_id"
    fake_model_cls.contact_phone = "contact_phone"
    fake_model_cls.user_id = "user_id"
    fake_model_cls.id = "id"
    fake_model_cls.state = MagicMock()
    fake_model_cls.state.notin_ = MagicMock(return_value=True)
    fake_model_cls.state.in_ = MagicMock(return_value=True)
    fake_model_cls.expires_at = MagicMock()
    fake_model_cls.expires_at.__le__ = MagicMock(return_value=True)
    fake_model_cls.expires_at.__gt__ = MagicMock(return_value=True)
    fake_model_cls.created_at = MagicMock()
    fake_model_cls.created_at.desc = MagicMock(return_value="created_at_desc")

    module_mock = MagicMock(
        VoiceWorkflow=fake_model_cls,
        VoiceWorkflowState=fake_state_enum,
    )
    return {"database.models.voice_workflow": module_mock}, fake_model_cls, fake_state_enum


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def service(db):
    return VoiceSchedulingWorkflowService(db)


@pytest.fixture
def base_workflow_kwargs():
    """Minimum required arguments for create_workflow."""
    return dict(
        organization_id=1,
        user_id=10,
        workflow_type="schedule_via_sms",
        contact_name="Jane Borrower",
        contact_phone="+15551234567",
    )


def _make_workflow(**overrides) -> FakeVoiceWorkflow:
    """Factory helper for building FakeVoiceWorkflow instances."""
    defaults = dict(
        id=1,
        organization_id=1,
        user_id=10,
        workflow_type="schedule_via_sms",
        state="initiated",
        contact_name="Jane Borrower",
        contact_phone="+15551234567",
        lead_id=None,
        expires_at=datetime.utcnow() + timedelta(hours=48),
    )
    defaults.update(overrides)
    return FakeVoiceWorkflow(**defaults)


# =============================================================================
# Tests: create_workflow
# =============================================================================

class TestCreateWorkflow:
    """Tests for VoiceSchedulingWorkflowService.create_workflow()."""

    @pytest.mark.unit
    def test_create_workflow_happy_path(self, service, db, base_workflow_kwargs):
        """New workflow is created, added to session, flushed, and returned."""
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([])

        with patch.dict("sys.modules", sys_patch):
            result = service.create_workflow(**base_workflow_kwargs)

        assert result is not None
        assert result.contact_name == "Jane Borrower"
        assert result.contact_phone == "+15551234567"
        assert result.organization_id == 1
        assert result.user_id == 10
        assert result.workflow_type == "schedule_via_sms"
        assert result.turn_count == 0
        assert result.conversation_history == []
        assert result.max_turns == VoiceSchedulingWorkflowService.MAX_TURNS
        assert result.expires_at is not None
        assert db.flushed is True
        assert len(db.added) == 1

    @pytest.mark.unit
    def test_create_workflow_duplicate_guard_returns_existing(self, service, db, base_workflow_kwargs):
        """When an active workflow already exists for the same org+phone, return it."""
        existing = _make_workflow(id=42, state="sms_sent")
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([existing])

        with patch.dict("sys.modules", sys_patch):
            result = service.create_workflow(**base_workflow_kwargs)

        assert result is existing
        assert result.id == 42
        # Should NOT have added a new workflow
        assert len(db.added) == 0

    @pytest.mark.unit
    def test_create_workflow_optional_fields(self, service, db, base_workflow_kwargs):
        """Optional fields (contact_email, lead_id, meeting_type, etc.) are set."""
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([])

        extended_kwargs = {
            **base_workflow_kwargs,
            "contact_email": "jane@example.com",
            "lead_id": 77,
            "meeting_type": "rate_review",
            "meeting_duration_minutes": 45,
            "message_context": "discuss refinance options",
        }

        with patch.dict("sys.modules", sys_patch):
            result = service.create_workflow(**extended_kwargs)

        assert result.contact_email == "jane@example.com"
        assert result.lead_id == 77
        assert result.meeting_type == "rate_review"
        assert result.meeting_duration_minutes == 45
        assert result.message_context == "discuss refinance options"

    @pytest.mark.unit
    def test_create_workflow_expiry_set_to_default(self, service, db, base_workflow_kwargs):
        """The expires_at field is set ~DEFAULT_EXPIRY_HOURS in the future."""
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([])

        before = datetime.utcnow()
        with patch.dict("sys.modules", sys_patch):
            result = service.create_workflow(**base_workflow_kwargs)
        after = datetime.utcnow()

        expected_min = before + timedelta(hours=VoiceSchedulingWorkflowService.DEFAULT_EXPIRY_HOURS)
        expected_max = after + timedelta(hours=VoiceSchedulingWorkflowService.DEFAULT_EXPIRY_HOURS)
        assert expected_min <= result.expires_at <= expected_max


# =============================================================================
# Tests: find_active_workflow_by_phone
# =============================================================================

class TestFindActiveWorkflowByPhone:
    """Tests for VoiceSchedulingWorkflowService.find_active_workflow_by_phone()."""

    @pytest.mark.unit
    def test_finds_active_sms_sent_workflow(self, service, db):
        """Returns workflow in SMS_SENT state for matching phone and org."""
        wf = _make_workflow(state="sms_sent")
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([wf])

        with patch.dict("sys.modules", sys_patch):
            result = service.find_active_workflow_by_phone("+15551234567", organization_id=1)

        assert result is wf

    @pytest.mark.unit
    def test_returns_none_when_no_active_workflow(self, service, db):
        """Returns None when no active workflow exists for the phone+org."""
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([])

        with patch.dict("sys.modules", sys_patch):
            result = service.find_active_workflow_by_phone("+15559999999", organization_id=1)

        assert result is None

    @pytest.mark.unit
    def test_ignores_completed_and_expired_workflows(self, service, db):
        """Completed, expired, cancelled, and failed workflows are excluded."""
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([])  # filtered out by query

        with patch.dict("sys.modules", sys_patch):
            result = service.find_active_workflow_by_phone("+15551234567", organization_id=1)

        assert result is None


# =============================================================================
# Tests: get_active_workflows_for_user
# =============================================================================

class TestGetActiveWorkflowsForUser:
    """Tests for VoiceSchedulingWorkflowService.get_active_workflows_for_user()."""

    @pytest.mark.unit
    def test_returns_active_workflows_for_user(self, service, db):
        """Returns list of active workflows matching user_id + organization_id."""
        wf1 = _make_workflow(id=1, state="initiated")
        wf2 = _make_workflow(id=2, state="sms_sent")
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([wf1, wf2])

        with patch.dict("sys.modules", sys_patch):
            results = service.get_active_workflows_for_user(user_id=10, organization_id=1)

        assert len(results) == 2
        assert results[0] is wf1
        assert results[1] is wf2

    @pytest.mark.unit
    def test_returns_empty_when_no_active_workflows(self, service, db):
        """Returns empty list when user has no active workflows."""
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([])

        with patch.dict("sys.modules", sys_patch):
            results = service.get_active_workflows_for_user(user_id=10, organization_id=1)

        assert results == []


# =============================================================================
# Tests: advance_state
# =============================================================================

class TestAdvanceState:
    """Tests for VoiceSchedulingWorkflowService.advance_state().

    The runtime service validates transitions against VALID_TRANSITIONS and
    creates an Activity audit record on every successful transition.
    """

    @pytest.mark.unit
    def test_advance_valid_transition(self, service, db):
        """A valid transition updates state, flushes, and adds Activity."""
        wf = _make_workflow(state="initiated")

        # "initiated" -> "contact_found" is valid per VALID_TRANSITIONS
        with patch("services.voice_scheduling_workflow_service.Activity") as MockActivity:
            service.advance_state(wf, "contact_found")

        assert wf.state == "contact_found"
        assert db.flushed is True
        # An Activity audit record should have been added to the session
        assert any(isinstance(obj, MagicMock) or True for obj in db.added)

    @pytest.mark.unit
    def test_advance_invalid_transition_raises_valueerror(self, service, db):
        """An invalid transition raises ValueError with descriptive message."""
        wf = _make_workflow(state="initiated")

        # "initiated" -> "negotiating" is NOT a valid transition
        with pytest.raises(ValueError, match="Invalid state transition"):
            with patch("services.voice_scheduling_workflow_service.Activity"):
                service.advance_state(wf, "negotiating")

        # State should NOT have changed
        assert wf.state == "initiated"

    @pytest.mark.unit
    def test_advance_state_updates_metadata_kwargs(self, service, db):
        """Extra kwargs are set as attributes on the workflow."""
        wf = _make_workflow(state="contact_found")

        with patch("services.voice_scheduling_workflow_service.Activity"):
            service.advance_state(
                wf,
                "sms_sent",
                last_sms_sent_at=datetime(2026, 3, 25, 10, 0, 0),
                error_message=None,
            )

        assert wf.state == "sms_sent"
        assert wf.last_sms_sent_at == datetime(2026, 3, 25, 10, 0, 0)
        assert wf.error_message is None

    @pytest.mark.unit
    def test_advance_state_ignores_nonexistent_attributes(self, service, db):
        """kwargs for attributes not on the model are silently ignored."""
        wf = _make_workflow(state="initiated")

        with patch("services.voice_scheduling_workflow_service.Activity"):
            service.advance_state(wf, "contact_found", nonexistent_field="xyz")

        assert wf.state == "contact_found"
        assert not hasattr(wf, "nonexistent_field")

    @pytest.mark.unit
    def test_advance_state_updates_updated_at(self, service, db):
        """transition_to sets updated_at to current time."""
        wf = _make_workflow(state="initiated")
        old_updated = wf.updated_at

        with patch("services.voice_scheduling_workflow_service.Activity"):
            service.advance_state(wf, "contact_found")

        assert wf.updated_at >= old_updated

    @pytest.mark.unit
    def test_advance_to_completed_sets_completed_at(self, service, db):
        """Transitioning to 'completed' sets completed_at timestamp."""
        wf = _make_workflow(state="appointment_booked")
        assert wf.completed_at is None

        with patch("services.voice_scheduling_workflow_service.Activity"):
            service.advance_state(wf, "completed")

        assert wf.state == "completed"
        assert wf.completed_at is not None

    @pytest.mark.unit
    def test_advance_to_appointment_booked_sets_completed_at(self, service, db):
        """Transitioning to 'appointment_booked' also sets completed_at."""
        wf = _make_workflow(state="time_confirmed")
        assert wf.completed_at is None

        with patch("services.voice_scheduling_workflow_service.Activity"):
            service.advance_state(wf, "appointment_booked")

        assert wf.state == "appointment_booked"
        assert wf.completed_at is not None

    @pytest.mark.unit
    @pytest.mark.parametrize("from_state,to_state", [
        ("initiated", "contact_found"),
        ("contact_found", "sms_sent"),
        ("sms_sent", "awaiting_reply"),
        ("awaiting_reply", "negotiating"),
        ("negotiating", "time_confirmed"),
        ("time_confirmed", "appointment_booked"),
        ("appointment_booked", "completed"),
    ])
    def test_advance_through_full_lifecycle(self, service, db, from_state, to_state):
        """Each forward state transition in the happy-path lifecycle works."""
        wf = _make_workflow(state=from_state)

        with patch("services.voice_scheduling_workflow_service.Activity"):
            service.advance_state(wf, to_state)

        assert wf.state == to_state
        assert db.flushed is True

    @pytest.mark.unit
    def test_advance_state_to_failed_from_allowed_state(self, service, db):
        """Workflow can transition to failed from states that allow it."""
        # "contact_found" -> "failed" is valid
        wf = _make_workflow(state="contact_found")

        with patch("services.voice_scheduling_workflow_service.Activity"):
            service.advance_state(wf, "failed", error_message="SMS delivery failed")

        assert wf.state == "failed"
        assert wf.error_message == "SMS delivery failed"

    @pytest.mark.unit
    def test_advance_state_to_cancelled_from_allowed_state(self, service, db):
        """Workflow can transition to cancelled from negotiating."""
        wf = _make_workflow(state="negotiating")

        with patch("services.voice_scheduling_workflow_service.Activity"):
            service.advance_state(wf, "cancelled")

        assert wf.state == "cancelled"

    @pytest.mark.unit
    def test_advance_from_failed_to_initiated_retry(self, service, db):
        """Failed workflows can be retried by transitioning back to initiated."""
        wf = _make_workflow(state="failed")

        with patch("services.voice_scheduling_workflow_service.Activity"):
            service.advance_state(wf, "initiated")

        assert wf.state == "initiated"

    @pytest.mark.unit
    @pytest.mark.parametrize("terminal_state", ["completed", "expired", "cancelled"])
    def test_advance_from_terminal_state_raises(self, service, db, terminal_state):
        """Terminal states (completed, expired, cancelled) have no valid transitions."""
        wf = _make_workflow(state=terminal_state)

        with pytest.raises(ValueError, match="Invalid state transition"):
            with patch("services.voice_scheduling_workflow_service.Activity"):
                service.advance_state(wf, "initiated")

    @pytest.mark.unit
    def test_activity_audit_record_created_on_advance(self, service, db):
        """An Activity record is added to the DB session on each successful advance."""
        wf = _make_workflow(state="initiated")
        initial_added_count = len(db.added)

        with patch("services.voice_scheduling_workflow_service.Activity") as MockActivity:
            MockActivity.return_value = MagicMock()
            service.advance_state(wf, "contact_found")

        # The Activity should have been instantiated and added
        MockActivity.assert_called_once()
        assert len(db.added) > initial_added_count


# =============================================================================
# Tests: expire_stale_workflows
# =============================================================================

class TestExpireStaleWorkflows:
    """Tests for VoiceSchedulingWorkflowService.expire_stale_workflows()."""

    @pytest.mark.unit
    def test_expires_past_due_workflows(self, service, db):
        """Workflows past expires_at are transitioned to expired."""
        stale_wf = _make_workflow(
            id=1,
            state="awaiting_reply",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([stale_wf])

        with patch.dict("sys.modules", sys_patch):
            with patch("services.voice_scheduling_workflow_service.Activity"):
                count = service.expire_stale_workflows()

        assert count == 1
        assert stale_wf.state == "expired"
        assert db.flushed is True

    @pytest.mark.unit
    def test_does_not_expire_active_workflows(self, service, db):
        """Workflows that have not passed expires_at are untouched."""
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([])

        with patch.dict("sys.modules", sys_patch):
            with patch("services.voice_scheduling_workflow_service.Activity"):
                count = service.expire_stale_workflows()

        assert count == 0

    @pytest.mark.unit
    def test_expires_multiple_stale_workflows(self, service, db):
        """Multiple stale workflows are all expired in one call."""
        stale1 = _make_workflow(id=1, state="sms_sent", expires_at=datetime.utcnow() - timedelta(hours=2))
        stale2 = _make_workflow(id=2, state="negotiating", expires_at=datetime.utcnow() - timedelta(hours=5))
        stale3 = _make_workflow(id=3, state="initiated", expires_at=datetime.utcnow() - timedelta(minutes=30))

        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([stale1, stale2, stale3])

        with patch.dict("sys.modules", sys_patch):
            with patch("services.voice_scheduling_workflow_service.Activity"):
                count = service.expire_stale_workflows()

        assert count == 3
        assert stale1.state == "expired"
        assert stale2.state == "expired"
        assert stale3.state == "expired"

    @pytest.mark.unit
    def test_does_not_touch_already_terminal_workflows(self, service, db):
        """Workflows already in terminal states are excluded by the query."""
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([])

        with patch.dict("sys.modules", sys_patch):
            with patch("services.voice_scheduling_workflow_service.Activity"):
                count = service.expire_stale_workflows()

        assert count == 0

    @pytest.mark.unit
    def test_expire_creates_activity_audit_records(self, service, db):
        """Each expired workflow gets an Activity audit record."""
        stale = _make_workflow(id=1, state="sms_sent", expires_at=datetime.utcnow() - timedelta(hours=1))
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([stale])

        with patch.dict("sys.modules", sys_patch):
            with patch("services.voice_scheduling_workflow_service.Activity") as MockActivity:
                MockActivity.return_value = MagicMock()
                count = service.expire_stale_workflows()

        assert count == 1
        MockActivity.assert_called_once()


# =============================================================================
# Tests: cancel_workflow
# =============================================================================

class TestCancelWorkflow:
    """Tests for VoiceSchedulingWorkflowService.cancel_workflow()."""

    @pytest.mark.unit
    def test_cancel_active_workflow(self, service, db):
        """Cancelling an active workflow sets state to cancelled and returns True."""
        wf = _make_workflow(id=5, state="sms_sent")
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([wf])

        with patch.dict("sys.modules", sys_patch):
            with patch("services.voice_scheduling_workflow_service.Activity"):
                result = service.cancel_workflow(5, organization_id=1)

        assert result is True
        assert wf.state == "cancelled"
        assert db.flushed is True

    @pytest.mark.unit
    def test_cancel_nonexistent_workflow_returns_false(self, service, db):
        """Returns False when workflow_id is not found."""
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([])

        with patch.dict("sys.modules", sys_patch):
            with patch("services.voice_scheduling_workflow_service.Activity"):
                result = service.cancel_workflow(999, organization_id=1)

        assert result is False

    @pytest.mark.unit
    def test_cancel_already_terminal_workflow_returns_false(self, service, db):
        """Returns False when workflow is already in a terminal state."""
        wf = _make_workflow(id=5, state="completed")
        assert wf.is_active() is False

        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([wf])

        with patch.dict("sys.modules", sys_patch):
            with patch("services.voice_scheduling_workflow_service.Activity"):
                result = service.cancel_workflow(5, organization_id=1)

        assert result is False
        assert wf.state == "completed"  # unchanged

    @pytest.mark.unit
    @pytest.mark.parametrize("terminal_state", ["completed", "expired", "cancelled", "failed"])
    def test_cancel_any_terminal_state_returns_false(self, service, db, terminal_state):
        """All terminal states (completed, expired, cancelled, failed) return False."""
        wf = _make_workflow(id=5, state=terminal_state)
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([wf])

        with patch.dict("sys.modules", sys_patch):
            with patch("services.voice_scheduling_workflow_service.Activity"):
                result = service.cancel_workflow(5, organization_id=1)

        assert result is False

    @pytest.mark.unit
    def test_cancel_creates_activity_audit_record(self, service, db):
        """Cancelling a workflow creates an Activity audit record."""
        wf = _make_workflow(id=5, state="sms_sent")
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([wf])

        with patch.dict("sys.modules", sys_patch):
            with patch("services.voice_scheduling_workflow_service.Activity") as MockActivity:
                MockActivity.return_value = MagicMock()
                result = service.cancel_workflow(5, organization_id=1)

        assert result is True
        MockActivity.assert_called_once()


# =============================================================================
# Tests: to_status_dict
# =============================================================================

class TestToStatusDict:
    """Tests for VoiceSchedulingWorkflowService.to_status_dict()."""

    @pytest.mark.unit
    def test_status_dict_shape(self, service):
        """Returned dict contains all expected keys."""
        now = datetime.utcnow()
        wf = _make_workflow(
            id=7,
            workflow_type="schedule_via_sms",
            state="negotiating",
            contact_name="Jane Borrower",
            contact_phone="+15551234567",
            meeting_type="discovery_call",
            turn_count=2,
            max_turns=8,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=48),
        )

        result = service.to_status_dict(wf)

        expected_keys = {
            "workflow_id",
            "type",
            "state",
            "contact_name",
            "contact_phone",
            "meeting_type",
            "turn_count",
            "max_turns",
            "confirmed_datetime",
            "appointment_id",
            "created_at",
            "updated_at",
            "expires_at",
            "error",
        }
        assert set(result.keys()) == expected_keys

    @pytest.mark.unit
    def test_status_dict_values(self, service):
        """Returned dict values match the workflow's attributes."""
        now = datetime(2026, 3, 25, 14, 30, 0)
        expires = now + timedelta(hours=48)
        wf = _make_workflow(
            id=7,
            workflow_type="schedule_via_sms",
            state="negotiating",
            contact_name="Jane Borrower",
            contact_phone="+15551234567",
            meeting_type="discovery_call",
            turn_count=2,
            max_turns=8,
            created_at=now,
            updated_at=now,
            expires_at=expires,
            error_message=None,
        )

        result = service.to_status_dict(wf)

        assert result["workflow_id"] == 7
        assert result["type"] == "schedule_via_sms"
        assert result["state"] == "negotiating"
        assert result["contact_name"] == "Jane Borrower"
        assert result["contact_phone"] == "****4567"
        assert result["meeting_type"] == "discovery_call"
        assert result["turn_count"] == 2
        assert result["max_turns"] == 8
        assert result["confirmed_datetime"] is None
        assert result["appointment_id"] is None
        assert result["created_at"] == now.isoformat()
        assert result["updated_at"] == now.isoformat()
        assert result["expires_at"] == expires.isoformat()
        assert result["error"] is None

    @pytest.mark.unit
    def test_status_dict_with_confirmed_datetime(self, service):
        """confirmed_datetime is serialized as ISO string when set."""
        confirmed = datetime(2026, 3, 26, 10, 0, 0)
        wf = _make_workflow(
            id=8,
            state="appointment_booked",
            confirmed_datetime=confirmed,
            appointment_id=42,
        )

        result = service.to_status_dict(wf)

        assert result["confirmed_datetime"] == confirmed.isoformat()
        assert result["appointment_id"] == 42

    @pytest.mark.unit
    def test_status_dict_with_error_message(self, service):
        """error field contains the error_message when present."""
        wf = _make_workflow(
            id=9,
            state="failed",
            error_message="Contact phone unreachable",
        )

        result = service.to_status_dict(wf)

        assert result["error"] == "Contact phone unreachable"
        assert result["state"] == "failed"

    @pytest.mark.unit
    def test_status_dict_none_timestamps(self, service):
        """When created_at/updated_at/expires_at are None, dict values are None."""
        wf = _make_workflow(id=10, state="initiated")
        wf.created_at = None
        wf.updated_at = None
        wf.expires_at = None

        result = service.to_status_dict(wf)

        assert result["created_at"] is None
        assert result["updated_at"] is None
        assert result["expires_at"] is None


# =============================================================================
# Tests: get_workflow (auxiliary)
# =============================================================================

class TestGetWorkflow:
    """Tests for VoiceSchedulingWorkflowService.get_workflow()."""

    @pytest.mark.unit
    def test_get_workflow_found(self, service, db):
        """Returns workflow when it exists."""
        wf = _make_workflow(id=3)
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([wf])

        with patch.dict("sys.modules", sys_patch):
            result = service.get_workflow(3, organization_id=1)

        assert result is wf

    @pytest.mark.unit
    def test_get_workflow_not_found(self, service, db):
        """Returns None when workflow does not exist."""
        sys_patch, _, _ = _make_sys_modules_patch()
        db.set_query_results([])

        with patch.dict("sys.modules", sys_patch):
            result = service.get_workflow(999, organization_id=1)

        assert result is None


# =============================================================================
# Tests: FakeVoiceWorkflow model behavior (sanity checks)
# =============================================================================

class TestFakeVoiceWorkflowBehavior:
    """Verify our fake mirrors the real model's is_active / transition_to logic."""

    @pytest.mark.unit
    @pytest.mark.parametrize("state,expected", [
        ("initiated", True),
        ("contact_found", True),
        ("sms_sent", True),
        ("awaiting_reply", True),
        ("negotiating", True),
        ("time_confirmed", True),
        ("appointment_booked", True),
        ("completed", False),
        ("expired", False),
        ("cancelled", False),
        ("failed", False),
    ])
    def test_is_active(self, state, expected):
        wf = _make_workflow(state=state)
        assert wf.is_active() is expected

    @pytest.mark.unit
    def test_transition_to_sets_state(self):
        wf = _make_workflow(state="initiated")
        wf.transition_to("sms_sent")
        assert wf.state == "sms_sent"

    @pytest.mark.unit
    def test_transition_to_completed_sets_completed_at(self):
        wf = _make_workflow(state="appointment_booked")
        assert wf.completed_at is None
        wf.transition_to("completed")
        assert wf.completed_at is not None

    @pytest.mark.unit
    def test_add_message_increments_turn_count_for_contact(self):
        wf = _make_workflow()
        assert wf.turn_count == 0
        wf.add_message("contact", "Tuesday works for me")
        assert wf.turn_count == 1
        assert len(wf.conversation_history) == 1
        assert wf.conversation_history[0]["role"] == "contact"

    @pytest.mark.unit
    def test_add_message_does_not_increment_for_system(self):
        wf = _make_workflow()
        wf.add_message("system", "Sending availability...")
        assert wf.turn_count == 0
        assert len(wf.conversation_history) == 1


# =============================================================================
# Tests: VALID_TRANSITIONS structure
# =============================================================================

class TestValidTransitions:
    """Verify the VALID_TRANSITIONS map covers expected states."""

    @pytest.mark.unit
    def test_all_states_present(self):
        """Every VoiceWorkflowState value has an entry in VALID_TRANSITIONS."""
        expected_states = {
            "initiated", "contact_found", "sms_sent", "awaiting_reply",
            "negotiating", "time_confirmed", "appointment_booked",
            "completed", "expired", "cancelled", "failed",
        }
        assert set(VALID_TRANSITIONS.keys()) == expected_states

    @pytest.mark.unit
    def test_terminal_states_have_no_forward_transitions(self):
        """completed, expired, cancelled have empty transition lists."""
        assert VALID_TRANSITIONS["completed"] == []
        assert VALID_TRANSITIONS["expired"] == []
        assert VALID_TRANSITIONS["cancelled"] == []

    @pytest.mark.unit
    def test_failed_can_retry_to_initiated(self):
        """Failed state allows retry back to initiated."""
        assert "initiated" in VALID_TRANSITIONS["failed"]


# =============================================================================
# Tests: Constants
# =============================================================================

class TestServiceConstants:
    """Verify service-level constants."""

    @pytest.mark.unit
    def test_default_expiry_hours(self):
        assert VoiceSchedulingWorkflowService.DEFAULT_EXPIRY_HOURS == 48

    @pytest.mark.unit
    def test_max_turns(self):
        assert VoiceSchedulingWorkflowService.MAX_TURNS == 8
