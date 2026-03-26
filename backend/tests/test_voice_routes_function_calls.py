"""
Tests for handle_browser_function_call() in voice_routes.py

Covers all 7 CRM tool dispatches, unknown tool handling,
missing/invalid arguments, and correct output formatting for
OpenAI function_call_output.
"""
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
from collections import namedtuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db_row(**kwargs):
    """Create a namedtuple row that mimics a SQLAlchemy Row (attribute access)."""
    Row = namedtuple("Row", kwargs.keys())
    return Row(**kwargs)


def _mock_db(execute_return=None, fetchone_return=None, fetchall_return=None):
    """
    Build a mock db session.

    - execute().fetchone() -> fetchone_return
    - execute().fetchall() -> fetchall_return
    - execute_return: raw return from execute() if custom chaining needed
    """
    db = MagicMock()
    result_proxy = MagicMock()
    result_proxy.fetchone.return_value = fetchone_return
    result_proxy.fetchall.return_value = fetchall_return if fetchall_return is not None else []
    db.execute.return_value = result_proxy
    return db


# ---------------------------------------------------------------------------
# Import the function under test
# ---------------------------------------------------------------------------

# We import lazily inside each test via a helper so that module-level import
# side-effects (heavy FastAPI app, DB engine creation, etc.) don't block the
# test collection.  All external dependencies used by the function at import
# time are patched.

import importlib
import sys
from pathlib import Path

# Ensure backend is on sys.path
_backend = str(Path(__file__).resolve().parent.parent)
if _backend not in sys.path:
    sys.path.insert(0, _backend)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the voice tool rate limiter between tests to prevent cross-test interference."""
    from routes.voice import tool_handlers
    tool_handlers._voice_rate_limiter._calls.clear()
    yield
    tool_handlers._voice_rate_limiter._calls.clear()


async def _call(func_name: str, args: dict, db=None):
    """Convenience wrapper that imports and calls handle_browser_function_call."""
    from voice_routes import handle_browser_function_call
    if db is None:
        db = _mock_db()
    return await handle_browser_function_call(func_name, args, db)


# ===========================================================================
# 1. search_contact
# ===========================================================================

class TestSearchContact:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_contact_returns_matches(self):
        """search_contact returns matching contacts from the leads table."""
        rows = [
            _make_db_row(
                id=42, first_name="Phil", last_name="George",
                name=None, phone="+15551112222", email="phil@example.com",
                stage="New", source="website",
            ),
        ]
        db = _mock_db(fetchall_return=rows)

        result = await _call("search_contact", {"name": "Phil"}, db)

        assert result["success"] is True
        assert len(result["contacts"]) == 1
        assert result["contacts"][0]["name"] == "Phil George"
        assert result["contacts"][0]["phone"] == "+15551112222"
        assert result["contacts"][0]["email"] == "phil@example.com"
        assert result["contacts"][0]["id"] == "42"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_contact_no_results(self):
        """search_contact returns empty list when no matches found."""
        db = _mock_db(fetchall_return=[])

        result = await _call("search_contact", {"name": "Nonexistent"}, db)

        assert result["success"] is True
        assert result["contacts"] == []
        assert "No contacts found" in result["message"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_contact_empty_name(self):
        """search_contact returns error when name is empty."""
        result = await _call("search_contact", {"name": ""})

        assert result["success"] is False
        assert "provide a name" in result["message"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_contact_missing_name_key(self):
        """search_contact returns error when name key is absent."""
        result = await _call("search_contact", {})

        assert result["success"] is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_contact_db_error_rolls_back(self):
        """search_contact rolls back and returns error on DB exception."""
        db = MagicMock()
        db.execute.side_effect = Exception("connection lost")

        result = await _call("search_contact", {"name": "Test"}, db)

        assert result["success"] is False
        assert "Error" in result["message"]
        db.rollback.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_search_contact_fallback_name_field(self):
        """search_contact uses the 'name' column when first/last are None."""
        rows = [
            _make_db_row(
                id=99, first_name=None, last_name=None,
                name="Legacy Contact", phone="", email="legacy@test.com",
                stage="New", source="import",
            ),
        ]
        db = _mock_db(fetchall_return=rows)

        result = await _call("search_contact", {"name": "Legacy"}, db)

        assert result["success"] is True
        assert result["contacts"][0]["name"] == "Legacy Contact"


# ===========================================================================
# 2. send_sms
# ===========================================================================

class TestSendSms:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_sms_success(self):
        """send_sms sends via telephony.sms.send_sms helper and returns success."""
        with patch.dict("os.environ", {
            "TELNYX_API_KEY": "KEY_TEST",
            "TELNYX_FROM_NUMBER": "+18005551234",
            "TELNYX_MESSAGING_PROFILE_ID": "profile-123",
        }):
            with patch("telephony.sms.send_sms", return_value={"id": "msg-123", "status": "sent"}) as mock_send:
                result = await _call("send_sms", {
                    "phone_number": "+15559998888",
                    "message": "Hello from test",
                    "contact_name": "Jane Doe",
                })

        assert result["success"] is True
        assert "Jane Doe" in result["message"]
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        assert call_kwargs[1]["to"] == "+15559998888"
        assert call_kwargs[1]["text"] == "Hello from test"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_sms_missing_phone(self):
        """send_sms returns error when phone_number is missing."""
        result = await _call("send_sms", {"message": "Hello"})

        assert result["success"] is False
        assert "required" in result["message"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_sms_missing_message(self):
        """send_sms returns error when message text is missing."""
        result = await _call("send_sms", {"phone_number": "+15551234567"})

        assert result["success"] is False
        assert "required" in result["message"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_sms_missing_credentials(self):
        """send_sms returns error when Telnyx credentials are not set."""
        with patch.dict("os.environ", {
            "TELNYX_API_KEY": "",
            "TELNYX_FROM_NUMBER": "",
        }, clear=False):
            with patch("telephony.sms.send_sms", return_value={"id": "msg-123", "status": "sent"}):
                result = await _call("send_sms", {
                    "phone_number": "+15559998888",
                    "message": "Hi",
                })

        assert result["success"] is False
        assert "not configured" in result["message"].lower() or "missing" in result["message"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_sms_telnyx_exception(self):
        """send_sms handles Telnyx API errors gracefully."""
        with patch.dict("os.environ", {
            "TELNYX_API_KEY": "KEY_TEST",
            "TELNYX_FROM_NUMBER": "+18005551234",
        }):
            with patch("telephony.sms.send_sms", side_effect=Exception("rate limited")):
                result = await _call("send_sms", {
                    "phone_number": "+15559998888",
                    "message": "Hello",
                })

        assert result["success"] is False
        assert "Failed" in result["message"] or "rate limited" in result["message"]


# ===========================================================================
# 3. get_my_availability
# ===========================================================================

class TestGetMyAvailability:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_availability_returns_slots(self):
        """get_my_availability returns weekday slots excluding booked hours."""
        # Mock: no existing appointments
        db = _mock_db(fetchall_return=[])

        result = await _call("get_my_availability", {"days_ahead": 5}, db)

        assert result["success"] is True
        assert "slots" in result
        # Should have at least one day with slots (unless all 5 days are weekend)
        # Each slot day should have available_times list
        for slot in result["slots"]:
            assert "date" in slot
            assert "day" in slot
            assert "available_times" in slot
            assert len(slot["available_times"]) > 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_availability_with_booked_hours(self):
        """get_my_availability excludes hours that already have appointments."""
        # Find next weekday
        today = datetime.now()
        next_weekday = today + timedelta(days=1)
        while next_weekday.weekday() >= 5:
            next_weekday += timedelta(days=1)

        # Mock: 10 AM is booked
        booked_dt = next_weekday.replace(hour=10, minute=0, second=0, microsecond=0)
        booked_row = _make_db_row(appointment_datetime=booked_dt)

        db = MagicMock()
        call_count = [0]

        def side_effect(*args, **kwargs):
            result = MagicMock()
            # First call is for the first day checked
            if call_count[0] == 0:
                result.fetchall.return_value = [booked_row]
            else:
                result.fetchall.return_value = []
            call_count[0] += 1
            return result

        db.execute = MagicMock(side_effect=side_effect)

        result = await _call("get_my_availability", {"days_ahead": 5}, db)

        assert result["success"] is True
        # The first day's slots should NOT contain "10:00"
        if result["slots"]:
            first_day = result["slots"][0]
            assert "10:00" not in first_day["available_times"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_availability_defaults(self):
        """get_my_availability uses default days_ahead=5 when not specified."""
        db = _mock_db(fetchall_return=[])

        result = await _call("get_my_availability", {}, db)

        assert result["success"] is True
        assert "availability" in result["message"].lower() or "Found" in result["message"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_availability_db_error(self):
        """get_my_availability handles DB errors and rolls back."""
        db = MagicMock()
        db.execute.side_effect = Exception("timeout")

        result = await _call("get_my_availability", {"days_ahead": 3}, db)

        assert result["success"] is False
        assert "Error" in result["message"]
        db.rollback.assert_called_once()


# ===========================================================================
# 4. schedule_appointment
# ===========================================================================

class TestScheduleAppointment:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_appointment_success(self):
        """schedule_appointment inserts into appointments table and returns success."""
        db = MagicMock()

        result = await _call("schedule_appointment", {
            "contact_name": "John Smith",
            "contact_email": "john@example.com",
            "contact_phone": "+15551234567",
            "date": "2026-04-01",
            "time": "14:00",
            "duration_minutes": 30,
            "meeting_type": "discovery_call",
        }, db)

        assert result["success"] is True
        assert "John Smith" in result["message"]
        assert result["contact_name"] == "John Smith"
        assert "appointment_time" in result
        db.execute.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_appointment_missing_name(self):
        """schedule_appointment returns error when contact_name is missing."""
        result = await _call("schedule_appointment", {
            "date": "2026-04-01",
            "time": "14:00",
        })

        assert result["success"] is False
        assert "required" in result["message"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_appointment_missing_date(self):
        """schedule_appointment returns error when date is missing."""
        result = await _call("schedule_appointment", {
            "contact_name": "Jane",
            "time": "10:00",
        })

        assert result["success"] is False
        assert "required" in result["message"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_appointment_missing_time(self):
        """schedule_appointment returns error when time is missing."""
        result = await _call("schedule_appointment", {
            "contact_name": "Jane",
            "date": "2026-04-01",
        })

        assert result["success"] is False
        assert "required" in result["message"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_appointment_invalid_datetime(self):
        """schedule_appointment handles invalid date/time format gracefully."""
        db = MagicMock()

        result = await _call("schedule_appointment", {
            "contact_name": "Jane",
            "date": "not-a-date",
            "time": "25:99",
        }, db)

        assert result["success"] is False
        assert "Failed" in result["message"] or "Error" in result["message"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_appointment_db_error_rolls_back(self):
        """schedule_appointment rolls back on DB error."""
        db = MagicMock()
        db.execute.side_effect = Exception("FK violation")

        result = await _call("schedule_appointment", {
            "contact_name": "Jane",
            "date": "2026-04-01",
            "time": "10:00",
        }, db)

        assert result["success"] is False
        db.rollback.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_appointment_default_meeting_type(self):
        """schedule_appointment defaults meeting_type to discovery_call."""
        db = MagicMock()

        result = await _call("schedule_appointment", {
            "contact_name": "Bob",
            "date": "2026-04-01",
            "time": "09:00",
        }, db)

        assert result["success"] is True
        # Verify the INSERT was called with default values
        call_args = db.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert "discovery_call" in str(params.get("notes", "")) or "Discovery Call" in str(params.get("reason", ""))


# ===========================================================================
# 5. create_task
# ===========================================================================

class TestCreateTask:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_task_success(self):
        """create_task inserts task and returns success."""
        db = MagicMock()

        result = await _call("create_task", {
            "title": "Follow up with client",
            "description": "Call about rate lock",
            "due_date": "2026-04-05",
            "priority": "high",
        }, db)

        assert result["success"] is True
        assert "Follow up with client" in result["message"]
        assert "high" in result["message"]
        assert "2026-04-05" in result["message"]
        db.execute.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_task_missing_title(self):
        """create_task returns error when title is missing."""
        result = await _call("create_task", {"description": "Something"})

        assert result["success"] is False
        assert "title" in result["message"].lower() or "required" in result["message"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_task_empty_title(self):
        """create_task returns error when title is empty string."""
        result = await _call("create_task", {"title": ""})

        assert result["success"] is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_task_defaults(self):
        """create_task uses default priority=medium and no due date."""
        db = MagicMock()

        result = await _call("create_task", {"title": "Quick reminder"}, db)

        assert result["success"] is True
        assert "medium" in result["message"]
        db.commit.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_task_db_error_rolls_back(self):
        """create_task rolls back on DB exception."""
        db = MagicMock()
        db.execute.side_effect = Exception("disk full")

        result = await _call("create_task", {"title": "Test"}, db)

        assert result["success"] is False
        db.rollback.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_task_invalid_due_date(self):
        """create_task handles invalid due_date format."""
        db = MagicMock()

        result = await _call("create_task", {
            "title": "Something",
            "due_date": "next-tuesday",
        }, db)

        assert result["success"] is False


# ===========================================================================
# 6. start_scheduling_workflow
# ===========================================================================

class TestStartSchedulingWorkflow:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_scheduling_workflow_success(self):
        """start_scheduling_workflow sends SMS with available slots."""
        db = _mock_db(fetchall_return=[])  # no existing appointments

        with patch.dict("os.environ", {
            "TELNYX_API_KEY": "KEY_TEST",
            "TELNYX_FROM_NUMBER": "+18005551234",
            "TELNYX_MESSAGING_PROFILE_ID": "prof-1",
        }):
            with patch("telephony.sms.send_sms", return_value={"id": "msg-123", "status": "sent"}) as mock_send:
                result = await _call("start_scheduling_workflow", {
                    "contact_name": "Alice",
                    "contact_phone": "+15551112222",
                    "meeting_type": "rate_lock_discussion",
                    "message_context": "discuss rate options",
                }, db)

        assert result["success"] is True
        assert "Alice" in result["message"]
        assert "workflow started" in result["message"].lower() or "SMS sent" in result["message"]
        mock_send.assert_called_once()
        sms_text = mock_send.call_args[1]["text"]
        assert "Alice" in sms_text
        assert "discuss rate options" in sms_text

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_scheduling_workflow_missing_name(self):
        """start_scheduling_workflow returns error when contact_name is missing."""
        result = await _call("start_scheduling_workflow", {
            "contact_phone": "+15551234567",
        })

        assert result["success"] is False
        assert "required" in result["message"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_scheduling_workflow_missing_phone(self):
        """start_scheduling_workflow returns error when contact_phone is missing."""
        result = await _call("start_scheduling_workflow", {
            "contact_name": "Bob",
        })

        assert result["success"] is False
        assert "required" in result["message"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_scheduling_workflow_missing_telnyx_creds(self):
        """start_scheduling_workflow returns error when Telnyx is not configured."""
        db = _mock_db(fetchall_return=[])

        with patch.dict("os.environ", {
            "TELNYX_API_KEY": "",
            "TELNYX_FROM_NUMBER": "",
        }, clear=False):
            with patch("telephony.sms.send_sms", return_value={"id": "msg-123", "status": "sent"}):
                result = await _call("start_scheduling_workflow", {
                    "contact_name": "Alice",
                    "contact_phone": "+15551112222",
                }, db)

        assert result["success"] is False
        assert "not configured" in result["message"].lower() or "missing" in result["message"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_scheduling_workflow_telnyx_error(self):
        """start_scheduling_workflow handles Telnyx send failure."""
        db = _mock_db(fetchall_return=[])

        with patch.dict("os.environ", {
            "TELNYX_API_KEY": "KEY_TEST",
            "TELNYX_FROM_NUMBER": "+18005551234",
        }):
            with patch("telephony.sms.send_sms", side_effect=Exception("service unavailable")):
                result = await _call("start_scheduling_workflow", {
                    "contact_name": "Alice",
                    "contact_phone": "+15551112222",
                }, db)

        assert result["success"] is False


# ===========================================================================
# 7. get_pipeline_summary
# ===========================================================================

class TestGetPipelineSummary:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_pipeline_summary_success(self):
        """get_pipeline_summary returns pipeline metrics from loans table."""
        summary_row = _make_db_row(
            active_loans=25,
            active_volume=12500000,
            closing_soon=4,
            funded_last_30=8,
            funded_volume_30=3200000,
        )
        db = _mock_db(fetchone_return=summary_row)

        result = await _call("get_pipeline_summary", {}, db)

        assert result["success"] is True
        assert "pipeline" in result
        pipeline = result["pipeline"]
        assert pipeline["active_loans"] == 25
        assert pipeline["active_volume"] == 12500000.0
        assert pipeline["closing_soon"] == 4
        assert pipeline["funded_last_30_days"] == 8
        assert pipeline["funded_volume_30_days"] == 3200000.0
        assert "25 active loans" in result["message"]
        assert "12,500,000" in result["message"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_pipeline_summary_zero_values(self):
        """get_pipeline_summary handles zero/null volumes gracefully."""
        summary_row = _make_db_row(
            active_loans=0,
            active_volume=None,
            closing_soon=0,
            funded_last_30=0,
            funded_volume_30=None,
        )
        db = _mock_db(fetchone_return=summary_row)

        result = await _call("get_pipeline_summary", {}, db)

        assert result["success"] is True
        assert result["pipeline"]["active_volume"] == 0.0
        assert result["pipeline"]["funded_volume_30_days"] == 0.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_pipeline_summary_db_error(self):
        """get_pipeline_summary handles DB errors and rolls back."""
        db = MagicMock()
        db.execute.side_effect = Exception("relation does not exist")

        result = await _call("get_pipeline_summary", {}, db)

        assert result["success"] is False
        assert "Error" in result["message"]
        db.rollback.assert_called_once()


# ===========================================================================
# 8. Unknown tool name
# ===========================================================================

class TestUnknownTool:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        """Unknown function name returns error with available actions list."""
        result = await _call("nonexistent_tool", {"foo": "bar"})

        assert result["success"] is False
        assert "don't know" in result["message"].lower() or "nonexistent_tool" in result["message"]
        # Should mention available actions
        assert "search" in result["message"].lower() or "available" in result["message"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_tool_name_returns_error(self):
        """Empty function name falls through to unknown handler."""
        result = await _call("", {})

        assert result["success"] is False


# ===========================================================================
# 9. Output format for OpenAI function_call_output
# ===========================================================================

class TestOutputFormat:
    """
    Verify that results from handle_browser_function_call are JSON-serializable
    dicts with 'success' and 'message' keys, suitable for wrapping as
    function_call_output in the OpenAI Realtime API.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_success_result_is_json_serializable(self):
        """Successful results can be json.dumps'd for function_call_output."""
        rows = [
            _make_db_row(
                id=1, first_name="Test", last_name="User",
                name=None, phone="+15550001111", email="t@t.com",
                stage="New", source="web",
            ),
        ]
        db = _mock_db(fetchall_return=rows)

        result = await _call("search_contact", {"name": "Test"}, db)

        # Must be serializable
        serialized = json.dumps(result)
        assert isinstance(serialized, str)

        # Must have standard keys
        assert "success" in result
        assert "message" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_error_result_is_json_serializable(self):
        """Error results can be json.dumps'd for function_call_output."""
        result = await _call("search_contact", {"name": ""})

        serialized = json.dumps(result)
        assert isinstance(serialized, str)
        assert result["success"] is False
        assert "message" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pipeline_result_has_nested_dict(self):
        """Pipeline result with nested 'pipeline' dict is fully serializable."""
        summary_row = _make_db_row(
            active_loans=10, active_volume=5000000,
            closing_soon=2, funded_last_30=3, funded_volume_30=1000000,
        )
        db = _mock_db(fetchone_return=summary_row)

        result = await _call("get_pipeline_summary", {}, db)
        serialized = json.dumps(result)
        parsed = json.loads(serialized)

        assert parsed["success"] is True
        assert isinstance(parsed["pipeline"], dict)
        assert isinstance(parsed["pipeline"]["active_loans"], int)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_openai_function_call_output_envelope(self):
        """Result wraps correctly in the OpenAI conversation.item.create envelope."""
        result = await _call("create_task", {"title": ""})

        # Simulate the exact envelope voice_routes.py sends to OpenAI
        envelope = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": "call_abc123",
                "output": json.dumps(result),
            }
        }

        serialized = json.dumps(envelope)
        parsed = json.loads(serialized)

        assert parsed["item"]["type"] == "function_call_output"
        inner = json.loads(parsed["item"]["output"])
        assert "success" in inner
        assert "message" in inner

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_all_tools_return_dict_with_success_key(self):
        """Every tool branch returns a dict containing at minimum 'success' and 'message'."""
        db_empty = _mock_db(fetchall_return=[])

        # Tools that only need minimal args and no external services
        simple_calls = [
            ("search_contact", {"name": ""}),
            ("send_sms", {}),
            ("get_my_availability", {}),
            ("schedule_appointment", {}),
            ("create_task", {}),
            ("start_scheduling_workflow", {}),
            ("get_pipeline_summary", {}),
            ("totally_bogus_tool", {}),
        ]

        for func_name, args in simple_calls:
            # For get_my_availability and get_pipeline_summary, need mock DB
            # that doesn't raise when called with no args
            if func_name in ("get_my_availability",):
                result = await _call(func_name, args, db_empty)
            elif func_name == "get_pipeline_summary":
                summary_row = _make_db_row(
                    active_loans=0, active_volume=0,
                    closing_soon=0, funded_last_30=0, funded_volume_30=0,
                )
                pipeline_db = _mock_db(fetchone_return=summary_row)
                result = await _call(func_name, args, pipeline_db)
            else:
                result = await _call(func_name, args)

            assert isinstance(result, dict), f"{func_name} did not return a dict"
            assert "success" in result, f"{func_name} missing 'success' key"
            assert "message" in result, f"{func_name} missing 'message' key"
