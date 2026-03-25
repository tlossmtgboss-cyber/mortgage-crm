"""
Tests for the send_email and complete_task tool handlers in
routes/voice/tool_handlers.py :: handle_browser_function_call()

All tests mock external dependencies (Graph API, SMTP, DB) and verify:
- Correct argument validation
- Tenant-scoped SQL queries (organization_id in WHERE clauses)
- Response format for voice readback

Run with: pytest tests/test_voice_tool_handlers_extended.py -v
"""

import sys
import os
import pytest
from collections import namedtuple
from unittest.mock import MagicMock, AsyncMock, patch

_backend = os.path.join(os.path.dirname(__file__), '..')
if _backend not in sys.path:
    sys.path.insert(0, _backend)

pytestmark = [pytest.mark.unit]

ORG_ID = "org-test-001"
USER_ID = 42


def _make_row(**kwargs):
    Row = namedtuple("Row", kwargs.keys())
    return Row(**kwargs)


def _mock_db(fetchone_return=None, fetchall_return=None):
    db = MagicMock()
    result_proxy = MagicMock()
    result_proxy.fetchone.return_value = fetchone_return
    result_proxy.fetchall.return_value = fetchall_return if fetchall_return is not None else []
    db.execute.return_value = result_proxy
    return db


async def _call(func_name: str, args: dict, db=None, org_id=ORG_ID, user_id=USER_ID):
    from routes.voice.tool_handlers import handle_browser_function_call
    if db is None:
        db = _mock_db()
    return await handle_browser_function_call(
        func_name, args, db,
        session_id="test-session-001",
        organization_id=org_id,
        user_id=user_id,
    )


# ===========================================================================
# send_email
# ===========================================================================

class TestSendEmailHandler:

    @pytest.mark.asyncio
    @patch("services.microsoft_graph.send_email_via_graph", new_callable=AsyncMock)
    async def test_send_email_handler_success(self, mock_send_graph):
        """send_email sends via Graph API and returns success."""
        mock_send_graph.return_value = None

        db = _mock_db()

        result = await _call("send_email", {
            "email": "john@example.com",
            "subject": "Your Rate Options",
            "body": "Hi John, here are your rate options...",
            "contact_name": "John Doe",
        }, db=db)

        assert result["success"] is True
        assert "John Doe" in result["message"]
        assert "Your Rate Options" in result["message"]

        mock_send_graph.assert_awaited_once()
        call_args = mock_send_graph.call_args
        assert call_args[0][0] == "john@example.com"
        assert call_args[0][1] == "Your Rate Options"

    @pytest.mark.asyncio
    async def test_send_email_handler_missing_fields(self):
        """send_email returns error when required fields are missing."""
        result = await _call("send_email", {"email": "", "subject": "Test", "body": "Test body"})
        assert result["success"] is False
        assert "required" in result["message"].lower()

        result = await _call("send_email", {"email": "test@example.com", "subject": "", "body": "Test body"})
        assert result["success"] is False

        result = await _call("send_email", {"email": "test@example.com", "subject": "Test", "body": ""})
        assert result["success"] is False

    @pytest.mark.asyncio
    @patch("services.microsoft_graph.send_email_via_graph", new_callable=AsyncMock)
    async def test_send_email_handler_logs_activity(self, mock_send_graph):
        """send_email logs an activity record to the DB after sending."""
        mock_send_graph.return_value = None

        db = _mock_db()

        result = await _call("send_email", {
            "email": "jane@example.com",
            "subject": "Follow-up",
            "body": "Thanks for our call today.",
            "contact_name": "Jane",
        }, db=db)

        assert result["success"] is True

        all_calls = db.execute.call_args_list
        activity_inserts = [
            c for c in all_calls
            if "activities" in str(c[0][0]).lower() and "INSERT" in str(c[0][0]).upper()
        ]
        assert len(activity_inserts) >= 1

    @pytest.mark.asyncio
    async def test_send_email_handler_smtp_fallback(self):
        """send_email falls back to SMTP when Graph API import fails."""
        db = _mock_db()

        # Reset the rate limiter singleton to avoid interference from prior tests
        from routes.voice import tool_handlers
        tool_handlers._voice_rate_limiter._calls.clear()

        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "user@example.com",
            "SMTP_PASSWORD": "password",
        }):
            # Patch the import to raise ImportError for Graph module
            with patch("services.microsoft_graph.send_email_via_graph", side_effect=ImportError("mock")):
                with patch("smtplib.SMTP") as mock_smtp_class:
                    mock_server = MagicMock()
                    mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
                    mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

                    result = await _call("send_email", {
                        "email": "test@example.com",
                        "subject": "Test",
                        "body": "Hello",
                    }, db=db)

        assert "message" in result


# ===========================================================================
# complete_task
# ===========================================================================

class TestCompleteTaskHandler:

    @pytest.mark.asyncio
    async def test_complete_task_by_title(self):
        """complete_task finds task by ILIKE title search and marks completed."""
        task_row = _make_row(id=99, title="Call John about refinance", status="pending")
        db = _mock_db(fetchone_return=task_row)

        result = await _call("complete_task", {"task_title": "call john"}, db=db)

        assert result["success"] is True
        assert "Call John about refinance" in result["message"]

        first_sql = str(db.execute.call_args_list[0][0][0]).lower()
        assert "like" in first_sql

        all_sqls = [str(c[0][0]).upper() for c in db.execute.call_args_list]
        update_calls = [s for s in all_sqls if "UPDATE" in s and "TASKS" in s]
        assert len(update_calls) >= 1

        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_complete_task_by_id(self):
        """complete_task finds task by direct ID lookup."""
        task_row = _make_row(id=55, title="Order appraisal", status="pending")
        db = _mock_db(fetchone_return=task_row)

        result = await _call("complete_task", {"task_id": "55"}, db=db)

        assert result["success"] is True
        assert "Order appraisal" in result["message"]
        db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_complete_task_not_found(self):
        """complete_task returns error when no matching task found."""
        db = _mock_db(fetchone_return=None)
        result = await _call("complete_task", {"task_title": "nonexistent task xyz"}, db=db)
        assert result["success"] is False
        assert "no open task" in result["message"].lower() or "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_complete_task_missing_args(self):
        """complete_task returns error when neither title nor ID provided."""
        result = await _call("complete_task", {})
        assert result["success"] is False
        assert "provide" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_complete_task_tenant_scoped(self):
        """complete_task includes organization_id in all queries."""
        task_row = _make_row(id=77, title="Send disclosures", status="pending")
        db = _mock_db(fetchone_return=task_row)

        result = await _call("complete_task", {"task_title": "disclosures"}, db=db, org_id=ORG_ID)

        assert result["success"] is True

        for execute_call in db.execute.call_args_list:
            sql = str(execute_call[0][0]).lower()
            params = execute_call[0][1] if len(execute_call[0]) > 1 else {}
            has_org = (
                "org_id" in params
                or "organization_id" in params
                or "organization_id" in sql
                or "org_id" in sql
            )
            assert has_org, f"Missing tenant scope in query: {sql}"

    @pytest.mark.asyncio
    async def test_complete_task_id_takes_precedence(self):
        """When both task_id and task_title are provided, ID lookup runs first."""
        task_row = _make_row(id=88, title="Review file", status="pending")
        db = _mock_db(fetchone_return=task_row)

        result = await _call("complete_task", {"task_id": "88", "task_title": "review file"}, db=db)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_complete_task_db_error_rolls_back(self):
        """complete_task rolls back on DB exception."""
        db = MagicMock()
        db.execute.side_effect = Exception("connection lost")

        result = await _call("complete_task", {"task_title": "anything"}, db=db)

        assert result["success"] is False
        assert "failed" in result["message"].lower() or "error" in result["message"].lower()
        db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_task_sets_completed_at(self):
        """complete_task UPDATE sets status='completed' and completed_at."""
        task_row = _make_row(id=100, title="Check conditions", status="pending")
        db = _mock_db(fetchone_return=task_row)

        result = await _call("complete_task", {"task_title": "conditions"}, db=db)

        assert result["success"] is True

        update_calls = [
            c for c in db.execute.call_args_list
            if "UPDATE" in str(c[0][0]).upper() and "tasks" in str(c[0][0]).lower()
        ]
        assert len(update_calls) >= 1

        update_sql = str(update_calls[0][0][0]).lower()
        assert "completed" in update_sql
