"""
Tests for aria/core/session_store.py

Covers:
- AriaSessionStore initialization with in-memory fallback
- get_or_create() new session creation
- get_or_create() returning existing session
- save() + get_or_create() round-trip persistence
- HumanMessage / AIMessage serialization round-trip
- Expected keys in session state
- Sensible defaults for empty sessions
- Session isolation across distinct session IDs
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from aria.core.session_store import (
    AriaSessionStore,
    _deserialize_messages,
    _memory_store,
    _serialize_messages,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_memory_store():
    """Ensure the in-memory store is empty before and after every test."""
    _memory_store.clear()
    yield
    _memory_store.clear()


@pytest.fixture
def store():
    """Return a fresh AriaSessionStore with Redis disabled (in-memory fallback)."""
    return AriaSessionStore()


@pytest.fixture
def user_kwargs():
    """Default keyword args for get_or_create()."""
    return {
        "session_id": "sess-001",
        "user_id": "user-42",
        "org_id": "org-7",
        "user_name": "Jane Doe",
        "user_role": "loan_officer",
    }


# Patch _get_redis to always return None so every test uses the memory store.
pytestmark = pytest.mark.asyncio


@patch("aria.core.session_store._get_redis", return_value=None)
class TestAriaSessionStoreInit:
    """Initialization and fallback behaviour."""

    async def test_store_initializes(self, _mock_redis, store):
        """AriaSessionStore can be instantiated without error."""
        assert store is not None

    async def test_falls_back_to_memory_when_redis_unavailable(
        self, _mock_redis, store, user_kwargs
    ):
        """When Redis returns None, save/load still works via _memory_store."""
        state = await store.get_or_create(**user_kwargs)
        state["intent"] = "check_rate"
        await store.save(user_kwargs["session_id"], state)

        # The data should be in the module-level _memory_store dict.
        assert user_kwargs["session_id"] in _memory_store


@patch("aria.core.session_store._get_redis", return_value=None)
class TestGetOrCreate:
    """get_or_create() — new and existing sessions."""

    async def test_creates_new_session_with_correct_initial_state(
        self, _mock_redis, store, user_kwargs
    ):
        state = await store.get_or_create(**user_kwargs)

        assert state["user_id"] == "user-42"
        assert state["org_id"] == "org-7"
        assert state["user_name"] == "Jane Doe"
        assert state["user_role"] == "loan_officer"
        assert state["messages"] == []
        assert state["intent"] is None
        assert state["slots"] == {}
        assert state["missing_slots"] == []
        assert state["current_slot_question"] is None
        assert state["phase"] == "understanding"
        assert state["task_result"] is None
        assert state["confirmation_preview"] is None
        assert state["iteration_count"] == 0
        assert state["error"] is None

    async def test_returns_existing_session_if_saved(
        self, _mock_redis, store, user_kwargs
    ):
        state = await store.get_or_create(**user_kwargs)
        state["intent"] = "schedule_call"
        state["phase"] = "executing"
        await store.save(user_kwargs["session_id"], state)

        reloaded = await store.get_or_create(**user_kwargs)
        assert reloaded["intent"] == "schedule_call"
        assert reloaded["phase"] == "executing"

    async def test_new_session_has_expected_keys(
        self, _mock_redis, store, user_kwargs
    ):
        state = await store.get_or_create(**user_kwargs)
        expected_keys = {
            "messages",
            "intent",
            "slots",
            "missing_slots",
            "current_slot_question",
            "phase",
            "task_result",
            "confirmation_preview",
            "user_id",
            "org_id",
            "user_name",
            "user_role",
            "iteration_count",
            "error",
        }
        assert set(state.keys()) == expected_keys


@patch("aria.core.session_store._get_redis", return_value=None)
class TestSaveAndRetrieve:
    """save() persists state that get_or_create() can retrieve."""

    async def test_round_trip_persistence(self, _mock_redis, store, user_kwargs):
        state = await store.get_or_create(**user_kwargs)
        state["messages"].append(HumanMessage(content="What are today's rates?"))
        state["messages"].append(AIMessage(content="Current 30yr fixed is 6.5%."))
        state["intent"] = "rate_inquiry"
        state["slots"] = {"loan_type": "conventional", "term": 30}
        state["phase"] = "responding"
        state["iteration_count"] = 2
        await store.save(user_kwargs["session_id"], state)

        reloaded = await store.get_or_create(**user_kwargs)
        assert reloaded["intent"] == "rate_inquiry"
        assert reloaded["slots"] == {"loan_type": "conventional", "term": 30}
        assert reloaded["phase"] == "responding"
        assert reloaded["iteration_count"] == 2
        assert len(reloaded["messages"]) == 2

    async def test_empty_session_defaults_survive_round_trip(
        self, _mock_redis, store, user_kwargs
    ):
        """An empty session saved and reloaded retains sensible defaults."""
        state = await store.get_or_create(**user_kwargs)
        await store.save(user_kwargs["session_id"], state)

        reloaded = await store.get_or_create(**user_kwargs)
        assert reloaded["messages"] == []
        assert reloaded["intent"] is None
        assert reloaded["slots"] == {}
        assert reloaded["missing_slots"] == []
        assert reloaded["phase"] == "understanding"
        assert reloaded["iteration_count"] == 0
        assert reloaded["error"] is None


@patch("aria.core.session_store._get_redis", return_value=None)
class TestMessageSerialization:
    """HumanMessage / AIMessage serialize to JSON and deserialize correctly."""

    async def test_human_message_round_trip(self, _mock_redis):
        original = [HumanMessage(content="Hello Aria")]
        serialized = _serialize_messages(original)
        assert serialized == [{"role": "human", "content": "Hello Aria"}]

        deserialized = _deserialize_messages(serialized)
        assert len(deserialized) == 1
        assert isinstance(deserialized[0], HumanMessage)
        assert deserialized[0].content == "Hello Aria"

    async def test_ai_message_round_trip(self, _mock_redis):
        original = [AIMessage(content="I can help with that.")]
        serialized = _serialize_messages(original)
        assert serialized == [{"role": "ai", "content": "I can help with that."}]

        deserialized = _deserialize_messages(serialized)
        assert len(deserialized) == 1
        assert isinstance(deserialized[0], AIMessage)
        assert deserialized[0].content == "I can help with that."

    async def test_mixed_message_sequence(self, _mock_redis):
        original = [
            HumanMessage(content="Pull up my pipeline"),
            AIMessage(content="You have 12 active loans."),
            HumanMessage(content="Which ones close this week?"),
            AIMessage(content="3 loans are scheduled to close."),
        ]
        serialized = _serialize_messages(original)
        assert len(serialized) == 4
        assert [m["role"] for m in serialized] == ["human", "ai", "human", "ai"]

        deserialized = _deserialize_messages(serialized)
        assert len(deserialized) == 4
        assert isinstance(deserialized[0], HumanMessage)
        assert isinstance(deserialized[1], AIMessage)
        assert deserialized[2].content == "Which ones close this week?"

    async def test_empty_message_list_serializes(self, _mock_redis):
        assert _serialize_messages([]) == []
        assert _deserialize_messages([]) == []

    async def test_serialized_messages_are_json_safe(self, _mock_redis):
        msgs = [
            HumanMessage(content="rate for 700k purchase"),
            AIMessage(content="Here's what I found..."),
        ]
        serialized = _serialize_messages(msgs)
        # Must survive a full JSON encode/decode cycle.
        json_str = json.dumps(serialized)
        decoded = json.loads(json_str)
        restored = _deserialize_messages(decoded)
        assert len(restored) == 2
        assert restored[0].content == "rate for 700k purchase"


@patch("aria.core.session_store._get_redis", return_value=None)
class TestSessionIsolation:
    """Multiple sessions must not interfere with each other."""

    async def test_two_sessions_are_independent(self, _mock_redis, store):
        kwargs_a = {
            "session_id": "sess-a",
            "user_id": "user-1",
            "org_id": "org-1",
            "user_name": "Alice",
            "user_role": "loan_officer",
        }
        kwargs_b = {
            "session_id": "sess-b",
            "user_id": "user-2",
            "org_id": "org-2",
            "user_name": "Bob",
            "user_role": "processor",
        }

        state_a = await store.get_or_create(**kwargs_a)
        state_a["intent"] = "schedule_call"
        state_a["messages"].append(HumanMessage(content="Call my borrower"))
        await store.save("sess-a", state_a)

        state_b = await store.get_or_create(**kwargs_b)
        state_b["intent"] = "doc_status"
        state_b["messages"].append(HumanMessage(content="Where is the appraisal?"))
        await store.save("sess-b", state_b)

        reloaded_a = await store.get_or_create(**kwargs_a)
        reloaded_b = await store.get_or_create(**kwargs_b)

        assert reloaded_a["intent"] == "schedule_call"
        assert reloaded_b["intent"] == "doc_status"
        assert reloaded_a["user_name"] == "Alice"
        assert reloaded_b["user_name"] == "Bob"
        assert len(reloaded_a["messages"]) == 1
        assert len(reloaded_b["messages"]) == 1
        assert reloaded_a["messages"][0].content == "Call my borrower"
        assert reloaded_b["messages"][0].content == "Where is the appraisal?"

    async def test_saving_one_session_does_not_overwrite_another(
        self, _mock_redis, store
    ):
        kwargs_x = {
            "session_id": "sess-x",
            "user_id": "u1",
            "org_id": "o1",
            "user_name": "X",
            "user_role": "lo",
        }
        kwargs_y = {
            "session_id": "sess-y",
            "user_id": "u2",
            "org_id": "o2",
            "user_name": "Y",
            "user_role": "lo",
        }

        state_x = await store.get_or_create(**kwargs_x)
        state_x["phase"] = "executing"
        await store.save("sess-x", state_x)

        # Create and save sess-y -- should NOT touch sess-x.
        state_y = await store.get_or_create(**kwargs_y)
        state_y["phase"] = "responding"
        await store.save("sess-y", state_y)

        reloaded_x = await store.get_or_create(**kwargs_x)
        assert reloaded_x["phase"] == "executing"


@patch("aria.core.session_store._get_redis")
class TestRedisFallback:
    """Verify behaviour when Redis is present but fails at runtime."""

    async def test_save_falls_back_on_redis_error(self, mock_get_redis, store, user_kwargs):
        """If Redis.setex raises, state should still land in _memory_store."""
        broken_redis = MagicMock()
        broken_redis.setex.side_effect = ConnectionError("Redis went away")
        mock_get_redis.return_value = broken_redis

        state = await store.get_or_create(**user_kwargs)
        state["intent"] = "saved_via_fallback"
        await store.save(user_kwargs["session_id"], state)

        assert user_kwargs["session_id"] in _memory_store
        assert _memory_store[user_kwargs["session_id"]]["intent"] == "saved_via_fallback"

    async def test_load_falls_back_on_redis_error(self, mock_get_redis, store, user_kwargs):
        """If Redis.get raises, _load should fall through to _memory_store."""
        # Pre-populate memory store directly.
        from aria.core.session_store import _serialize_messages

        _memory_store[user_kwargs["session_id"]] = {
            "messages": _serialize_messages([]),
            "intent": "from_memory",
            "slots": {},
            "missing_slots": [],
            "current_slot_question": None,
            "phase": "understanding",
            "task_result": None,
            "confirmation_preview": None,
            "user_id": "user-42",
            "org_id": "org-7",
            "user_name": "Jane Doe",
            "user_role": "loan_officer",
            "iteration_count": 0,
            "error": None,
            "saved_at": "2026-04-13T00:00:00+00:00",
        }

        broken_redis = MagicMock()
        broken_redis.get.side_effect = ConnectionError("Redis timeout")
        mock_get_redis.return_value = broken_redis

        reloaded = await store.get_or_create(**user_kwargs)
        assert reloaded["intent"] == "from_memory"

    async def test_save_uses_redis_when_available(self, mock_get_redis, store, user_kwargs):
        """When Redis is healthy, data should be written via setex and NOT in _memory_store."""
        healthy_redis = MagicMock()
        mock_get_redis.return_value = healthy_redis

        state = await store.get_or_create(**user_kwargs)
        state["intent"] = "redis_path"
        await store.save(user_kwargs["session_id"], state)

        healthy_redis.setex.assert_called_once()
        call_args = healthy_redis.setex.call_args
        assert call_args[0][0] == "aria:session:sess-001"
        assert call_args[0][1] == 86400  # SESSION_TTL

        # Verify the payload is valid JSON with expected content.
        payload = json.loads(call_args[0][2])
        assert payload["intent"] == "redis_path"

        # Memory store should NOT have received it.
        assert user_kwargs["session_id"] not in _memory_store
