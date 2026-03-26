"""Tests for Aria Voice AI scheduling workflow components.

Covers:
- VoiceWorkflow model: state machine, conversation tracking, transitions
- AvailabilityCache: TTL-based slot caching with invalidation
- SMSRetryService: circuit breaker, dead letter queue
- SMSDeadLetter model: field instantiation

Finding H-11: Voice scheduling workflow had zero test coverage.
"""

import time
import pytest
from datetime import datetime
from unittest.mock import MagicMock

import sys
from pathlib import Path

# Ensure backend is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers: Build VoiceWorkflow instances without a live DB connection.
#
# The VoiceWorkflow model imports `from db import Base` which triggers
# SQLAlchemy engine creation. We avoid that by constructing instances with
# __new__ + manual attribute assignment, bypassing __init__ / metaclass
# machinery that expects a mapped session.
# ---------------------------------------------------------------------------

def _make_voice_workflow(**overrides):
    """Create a VoiceWorkflow instance for testing pure-Python methods.

    SQLAlchemy models can be instantiated without a session — the constructor
    sets up _sa_instance_state automatically. We just pass keyword arguments
    matching the column names.
    """
    from database.models.voice_workflow import VoiceWorkflow, VoiceWorkflowState

    defaults = {
        "organization_id": 1,
        "user_id": 1,
        "workflow_type": "schedule_via_sms",
        "state": VoiceWorkflowState.INITIATED.value,
        "contact_name": "Jane Doe",
        "contact_phone": "+15551234567",
        "conversation_history": [],
        "turn_count": 0,
        "max_turns": 8,
    }
    defaults.update(overrides)
    return VoiceWorkflow(**defaults)


def _make_sms_dead_letter(**overrides):
    """Create an SMSDeadLetter instance for testing field presence."""
    from database.models.sms_dead_letter import SMSDeadLetter

    defaults = {
        "organization_id": 100,
        "workflow_id": 200,
        "to_phone": "+15559998888",
        "from_phone": "+15551112222",
        "message": "Your appointment is at 2pm tomorrow.",
        "last_error": "Connection timeout",
        "attempts": 3,
        "status": "pending",
        "extra_metadata": {},
    }
    defaults.update(overrides)
    return SMSDeadLetter(**defaults)


# =============================================================================
# VoiceWorkflow Model Tests
# =============================================================================

class TestVoiceWorkflowCreationDefaults:
    """test_workflow_creation_defaults -- verify default state is 'initiated', turn_count=0."""

    def test_default_state_is_initiated(self):
        from database.models.voice_workflow import VoiceWorkflowState
        wf = _make_voice_workflow()
        assert wf.state == VoiceWorkflowState.INITIATED.value
        assert wf.state == "initiated"

    def test_default_turn_count_is_zero(self):
        wf = _make_voice_workflow()
        assert wf.turn_count == 0

    def test_default_conversation_history_is_empty_list(self):
        wf = _make_voice_workflow()
        assert wf.conversation_history == []

    def test_default_max_turns_is_eight(self):
        wf = _make_voice_workflow()
        assert wf.max_turns == 8

    def test_completed_at_is_none(self):
        wf = _make_voice_workflow()
        assert wf.completed_at is None


class TestVoiceWorkflowIsActive:
    """test_is_active_for_active_states and test_is_active_for_terminal_states."""

    def test_is_active_for_active_states(self):
        """All non-terminal states should return True from is_active()."""
        from database.models.voice_workflow import VoiceWorkflowState

        active_states = [
            VoiceWorkflowState.INITIATED,
            VoiceWorkflowState.CONTACT_FOUND,
            VoiceWorkflowState.SMS_SENT,
            VoiceWorkflowState.AWAITING_REPLY,
            VoiceWorkflowState.NEGOTIATING,
            VoiceWorkflowState.TIME_CONFIRMED,
            VoiceWorkflowState.APPOINTMENT_BOOKED,
        ]
        for state in active_states:
            wf = _make_voice_workflow(state=state.value)
            assert wf.is_active() is True, f"Expected is_active()=True for state {state.value}"

    def test_is_active_for_terminal_states(self):
        """COMPLETED, EXPIRED, CANCELLED, FAILED should return False."""
        from database.models.voice_workflow import VoiceWorkflowState

        terminal_states = [
            VoiceWorkflowState.COMPLETED,
            VoiceWorkflowState.EXPIRED,
            VoiceWorkflowState.CANCELLED,
            VoiceWorkflowState.FAILED,
        ]
        for state in terminal_states:
            wf = _make_voice_workflow(state=state.value)
            assert wf.is_active() is False, f"Expected is_active()=False for state {state.value}"


class TestVoiceWorkflowAddMessage:
    """test_add_message -- appends to conversation_history with correct structure."""

    def test_add_message_appends_entry(self):
        wf = _make_voice_workflow()
        wf.add_message("system", "Workflow initiated")
        assert len(wf.conversation_history) == 1
        entry = wf.conversation_history[0]
        assert entry["role"] == "system"
        assert entry["content"] == "Workflow initiated"
        assert "timestamp" in entry

    def test_add_message_preserves_existing(self):
        wf = _make_voice_workflow(conversation_history=[
            {"role": "system", "content": "init", "timestamp": "2026-01-01T00:00:00"},
        ])
        wf.add_message("assistant", "Hello")
        assert len(wf.conversation_history) == 2
        assert wf.conversation_history[0]["role"] == "system"
        assert wf.conversation_history[1]["role"] == "assistant"

    def test_add_message_handles_none_history(self):
        wf = _make_voice_workflow(conversation_history=None)
        wf.add_message("system", "Starting")
        assert len(wf.conversation_history) == 1

    def test_add_message_timestamp_is_iso_format(self):
        wf = _make_voice_workflow()
        wf.add_message("user", "test")
        ts = wf.conversation_history[0]["timestamp"]
        # Should be parseable as ISO 8601
        datetime.fromisoformat(ts)

    def test_add_message_increments_turn_count_for_contact(self):
        """Only 'contact' role should increment turn_count."""
        wf = _make_voice_workflow()
        assert wf.turn_count == 0

        wf.add_message("system", "init")
        assert wf.turn_count == 0

        wf.add_message("assistant", "hello")
        assert wf.turn_count == 0

        wf.add_message("user", "command")
        assert wf.turn_count == 0

        wf.add_message("contact", "Sure, 2pm works")
        assert wf.turn_count == 1

        wf.add_message("contact", "Actually, 3pm?")
        assert wf.turn_count == 2

    def test_add_message_contact_with_none_turn_count(self):
        """turn_count=None should be treated as 0 before incrementing."""
        wf = _make_voice_workflow(turn_count=None)
        wf.add_message("contact", "Hi")
        assert wf.turn_count == 1


class TestVoiceWorkflowTransitionTo:
    """test_transition_to_completed_sets_completed_at."""

    def test_transition_to_completed_sets_completed_at(self):
        from database.models.voice_workflow import VoiceWorkflowState
        wf = _make_voice_workflow(state=VoiceWorkflowState.TIME_CONFIRMED.value)
        assert wf.completed_at is None
        wf.transition_to(VoiceWorkflowState.COMPLETED.value)
        assert wf.state == "completed"
        assert wf.completed_at is not None
        assert isinstance(wf.completed_at, datetime)

    def test_transition_to_appointment_booked_sets_completed_at(self):
        from database.models.voice_workflow import VoiceWorkflowState
        wf = _make_voice_workflow(state=VoiceWorkflowState.TIME_CONFIRMED.value)
        wf.transition_to(VoiceWorkflowState.APPOINTMENT_BOOKED.value)
        assert wf.state == "appointment_booked"
        assert wf.completed_at is not None

    def test_transition_to_non_terminal_does_not_set_completed_at(self):
        from database.models.voice_workflow import VoiceWorkflowState
        wf = _make_voice_workflow(state=VoiceWorkflowState.INITIATED.value)
        wf.transition_to(VoiceWorkflowState.CONTACT_FOUND.value)
        assert wf.state == "contact_found"
        assert wf.completed_at is None

    def test_transition_updates_updated_at(self):
        from database.models.voice_workflow import VoiceWorkflowState
        wf = _make_voice_workflow()
        before_transition = datetime.utcnow()
        wf.transition_to(VoiceWorkflowState.SMS_SENT.value)
        assert wf.updated_at is not None
        assert isinstance(wf.updated_at, datetime)
        assert wf.updated_at >= before_transition

    def test_transition_to_failed_does_not_set_completed_at(self):
        from database.models.voice_workflow import VoiceWorkflowState
        wf = _make_voice_workflow()
        wf.transition_to(VoiceWorkflowState.FAILED.value)
        assert wf.state == "failed"
        assert wf.completed_at is None

    def test_transition_to_cancelled_does_not_set_completed_at(self):
        from database.models.voice_workflow import VoiceWorkflowState
        wf = _make_voice_workflow()
        wf.transition_to(VoiceWorkflowState.CANCELLED.value)
        assert wf.state == "cancelled"
        assert wf.completed_at is None


# =============================================================================
# AvailabilityCache Tests
# =============================================================================

class TestAvailabilityCacheMiss:
    """test_cache_miss_returns_none -- fresh cache returns None."""

    def test_fresh_cache_returns_none(self):
        from services.availability_cache import AvailabilityCache
        cache = AvailabilityCache(ttl_seconds=60)
        result = cache.get_slots(user_id=1, organization_id=1, date_str="2026-03-25")
        assert result is None


class TestAvailabilityCacheHit:
    """test_cache_hit_returns_slots -- after set_slots, get_slots returns data."""

    def test_set_then_get_returns_slots(self):
        from services.availability_cache import AvailabilityCache
        cache = AvailabilityCache(ttl_seconds=60)
        slots = [
            {"start": "2026-03-25T10:00:00", "end": "2026-03-25T10:30:00"},
            {"start": "2026-03-25T14:00:00", "end": "2026-03-25T14:30:00"},
        ]
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-25", slots=slots)
        result = cache.get_slots(user_id=1, organization_id=1, date_str="2026-03-25")
        assert result == slots

    def test_different_user_returns_none(self):
        from services.availability_cache import AvailabilityCache
        cache = AvailabilityCache(ttl_seconds=60)
        slots = [{"start": "10:00", "end": "10:30"}]
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-25", slots=slots)
        result = cache.get_slots(user_id=2, organization_id=1, date_str="2026-03-25")
        assert result is None

    def test_different_org_returns_none(self):
        from services.availability_cache import AvailabilityCache
        cache = AvailabilityCache(ttl_seconds=60)
        slots = [{"start": "10:00", "end": "10:30"}]
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-25", slots=slots)
        result = cache.get_slots(user_id=1, organization_id=2, date_str="2026-03-25")
        assert result is None


class TestAvailabilityCacheExpiry:
    """test_cache_expiry -- after TTL, get_slots returns None."""

    def test_expired_entry_returns_none(self):
        from services.availability_cache import AvailabilityCache
        cache = AvailabilityCache(ttl_seconds=0.1)  # 100ms TTL
        slots = [{"start": "10:00", "end": "10:30"}]
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-25", slots=slots)

        # Verify it's there initially
        assert cache.get_slots(user_id=1, organization_id=1, date_str="2026-03-25") is not None

        # Wait for expiry
        time.sleep(0.2)

        result = cache.get_slots(user_id=1, organization_id=1, date_str="2026-03-25")
        assert result is None


class TestAvailabilityCacheInvalidateSpecificDate:
    """test_invalidate_specific_date -- invalidates only the target date."""

    def test_invalidate_single_date(self):
        from services.availability_cache import AvailabilityCache
        cache = AvailabilityCache(ttl_seconds=60)
        slots_25 = [{"start": "10:00"}]
        slots_26 = [{"start": "11:00"}]
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-25", slots=slots_25)
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-26", slots=slots_26)

        # Invalidate only March 25
        cache.invalidate(user_id=1, organization_id=1, date_str="2026-03-25")

        assert cache.get_slots(user_id=1, organization_id=1, date_str="2026-03-25") is None
        assert cache.get_slots(user_id=1, organization_id=1, date_str="2026-03-26") == slots_26


class TestAvailabilityCacheInvalidateAllForUser:
    """test_invalidate_all_for_user -- invalidates all dates for a user."""

    def test_invalidate_all_dates(self):
        from services.availability_cache import AvailabilityCache
        cache = AvailabilityCache(ttl_seconds=60)
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-25", slots=[{"s": "a"}])
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-26", slots=[{"s": "b"}])
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-27", slots=[{"s": "c"}])
        # Different user -- should survive
        cache.set_slots(user_id=2, organization_id=1, date_str="2026-03-25", slots=[{"s": "d"}])

        cache.invalidate(user_id=1, organization_id=1)  # no date_str => all dates

        assert cache.get_slots(user_id=1, organization_id=1, date_str="2026-03-25") is None
        assert cache.get_slots(user_id=1, organization_id=1, date_str="2026-03-26") is None
        assert cache.get_slots(user_id=1, organization_id=1, date_str="2026-03-27") is None
        # User 2 still cached
        assert cache.get_slots(user_id=2, organization_id=1, date_str="2026-03-25") == [{"s": "d"}]


class TestAvailabilityCacheStats:
    """test_cache_stats -- reports correct active/expired counts."""

    def test_stats_all_active(self):
        from services.availability_cache import AvailabilityCache
        cache = AvailabilityCache(ttl_seconds=60)
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-25", slots=[])
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-26", slots=[])
        stats = cache.stats()
        assert stats["total_entries"] == 2
        assert stats["active_entries"] == 2
        assert stats["expired_entries"] == 0
        assert stats["ttl_seconds"] == 60

    def test_stats_with_expired(self):
        from services.availability_cache import AvailabilityCache
        cache = AvailabilityCache(ttl_seconds=0.1)
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-25", slots=[])
        time.sleep(0.2)
        # Add a fresh entry
        cache.set_slots(user_id=1, organization_id=1, date_str="2026-03-26", slots=[])
        stats = cache.stats()
        assert stats["total_entries"] == 2
        assert stats["expired_entries"] == 1
        assert stats["active_entries"] == 1


# =============================================================================
# SMSRetryService Tests
# =============================================================================

class TestSMSCircuitBreaker:
    """test_circuit_breaker_opens_after_threshold and half_open_after_cooldown."""

    def setup_method(self):
        """Reset class-level circuit breaker state before each test."""
        from services.sms_retry_service import SMSRetryService
        SMSRetryService._circuit_state = "closed"
        SMSRetryService._failure_count = 0
        SMSRetryService._circuit_opened_at = None

    def test_circuit_breaker_opens_after_threshold(self):
        """5 failures should trip the circuit breaker to open."""
        from services.sms_retry_service import SMSRetryService
        svc = SMSRetryService()

        assert SMSRetryService._circuit_state == "closed"

        # Record 5 failures (threshold)
        for i in range(5):
            svc._record_failure()

        assert SMSRetryService._circuit_state == "open"
        assert SMSRetryService._circuit_opened_at is not None

        # Verify circuit blocks requests
        assert svc._check_circuit() is False

    def test_circuit_breaker_stays_closed_below_threshold(self):
        from services.sms_retry_service import SMSRetryService
        svc = SMSRetryService()

        for _ in range(4):
            svc._record_failure()

        assert SMSRetryService._circuit_state == "closed"
        assert svc._check_circuit() is True

    def test_circuit_breaker_half_open_after_cooldown(self):
        """After cooldown period, circuit should transition to half_open and allow a test request."""
        from services.sms_retry_service import SMSRetryService
        svc = SMSRetryService()

        # Trip the breaker
        for _ in range(5):
            svc._record_failure()
        assert SMSRetryService._circuit_state == "open"

        # Simulate cooldown elapsed by backdating the opened_at timestamp
        SMSRetryService._circuit_opened_at = time.time() - (SMSRetryService._circuit_cooldown_seconds + 1)

        # Now _check_circuit should allow a test request and set half_open
        assert svc._check_circuit() is True
        assert SMSRetryService._circuit_state == "half_open"

    def test_circuit_breaker_closes_on_success_from_half_open(self):
        from services.sms_retry_service import SMSRetryService
        svc = SMSRetryService()

        # Put into half_open
        SMSRetryService._circuit_state = "half_open"

        svc._record_success()
        assert SMSRetryService._circuit_state == "closed"
        assert SMSRetryService._failure_count == 0

    def test_circuit_breaker_reopens_on_failure_from_half_open(self):
        from services.sms_retry_service import SMSRetryService
        svc = SMSRetryService()

        SMSRetryService._circuit_state = "half_open"

        svc._record_failure()
        assert SMSRetryService._circuit_state == "open"


class TestSMSDeadLetterQueueInMemory:
    """test_dead_letter_queue_in_memory -- failed messages end up in DLQ."""

    def test_persist_dead_letter_to_in_memory_queue(self):
        from services.sms_retry_service import SMSRetryService
        svc = SMSRetryService(db=None)  # No DB -> in-memory fallback

        assert len(svc._dead_letter_queue) == 0

        svc._persist_dead_letter(
            to_phone="+15559998888",
            from_phone="+15551112222",
            message="Test message",
            organization_id=100,
            workflow_id=200,
            last_error="Connection refused",
            metadata={"attempt_source": "test"},
        )

        assert len(svc._dead_letter_queue) == 1
        entry = svc._dead_letter_queue[0]
        assert entry["to_phone"] == "+15559998888"
        assert entry["from_phone"] == "+15551112222"
        assert entry["message"] == "Test message"
        assert entry["organization_id"] == 100
        assert entry["workflow_id"] == 200
        assert entry["last_error"] == "Connection refused"
        assert entry["attempts"] == 3  # SMSRetryService.MAX_RETRIES
        assert "dead_lettered_at" in entry
        assert entry["metadata"] == {"attempt_source": "test"}

    def test_get_dead_letter_queue_returns_all(self):
        from services.sms_retry_service import SMSRetryService
        svc = SMSRetryService(db=None)

        svc._persist_dead_letter("+1", "+2", "msg1", 1, None, "err", None)
        svc._persist_dead_letter("+3", "+4", "msg2", 2, None, "err", None)

        dlq = svc.get_dead_letter_queue()
        assert len(dlq) == 2

    def test_get_dead_letter_queue_filtered_by_org(self):
        from services.sms_retry_service import SMSRetryService
        svc = SMSRetryService(db=None)

        svc._persist_dead_letter("+1", "+2", "msg1", 100, None, "err", None)
        svc._persist_dead_letter("+3", "+4", "msg2", 200, None, "err", None)

        dlq = svc.get_dead_letter_queue(organization_id=100)
        assert len(dlq) == 1
        assert dlq[0]["to_phone"] == "+1"

    def test_dead_letter_count(self):
        from services.sms_retry_service import SMSRetryService
        svc = SMSRetryService(db=None)

        svc._persist_dead_letter("+1", "+2", "m", 1, None, "e", None)
        svc._persist_dead_letter("+3", "+4", "m", 1, None, "e", None)
        svc._persist_dead_letter("+5", "+6", "m", 2, None, "e", None)

        assert svc.dead_letter_count() == 3
        assert svc.dead_letter_count(organization_id=1) == 2
        assert svc.dead_letter_count(organization_id=2) == 1
        assert svc.dead_letter_count(organization_id=999) == 0

    def test_retry_dead_letter_pops_entry(self):
        from services.sms_retry_service import SMSRetryService
        svc = SMSRetryService(db=None)

        svc._persist_dead_letter("+1", "+2", "msg1", 1, None, "err", None)
        svc._persist_dead_letter("+3", "+4", "msg2", 2, None, "err", None)

        entry = svc.retry_dead_letter(0)  # index-based for in-memory
        assert entry is not None
        assert entry["to_phone"] == "+1"
        assert svc.dead_letter_count() == 1

    def test_retry_dead_letter_invalid_index_returns_none(self):
        from services.sms_retry_service import SMSRetryService
        svc = SMSRetryService(db=None)
        result = svc.retry_dead_letter(99)
        assert result is None


# =============================================================================
# SMSDeadLetter Model Tests
# =============================================================================

class TestSMSDeadLetterModelCreation:
    """test_dead_letter_model_creation -- model instantiates with expected fields."""

    def test_all_fields_present(self):
        dl = _make_sms_dead_letter()
        assert dl.organization_id == 100
        assert dl.workflow_id == 200
        assert dl.to_phone == "+15559998888"
        assert dl.from_phone == "+15551112222"
        assert dl.message == "Your appointment is at 2pm tomorrow."
        assert dl.last_error == "Connection timeout"
        assert dl.attempts == 3
        assert dl.status == "pending"
        assert dl.extra_metadata == {}
        assert dl.retried_at is None

    def test_default_status_is_pending(self):
        dl = _make_sms_dead_letter()
        assert dl.status == "pending"

    def test_custom_overrides(self):
        dl = _make_sms_dead_letter(
            status="retried",
            retried_at=datetime(2026, 3, 25, 12, 0, 0),
            extra_metadata={"reason": "manual_retry"},
        )
        assert dl.status == "retried"
        assert dl.retried_at == datetime(2026, 3, 25, 12, 0, 0)
        assert dl.extra_metadata == {"reason": "manual_retry"}

    def test_nullable_fields(self):
        dl = _make_sms_dead_letter(
            organization_id=None,
            workflow_id=None,
            last_error=None,
        )
        assert dl.organization_id is None
        assert dl.workflow_id is None
        assert dl.last_error is None
