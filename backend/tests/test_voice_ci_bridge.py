"""
Tests for VoiceCIBridgeService — the service layer that bridges
voice tool commands to Call Intelligence database operations.

VoiceCIBridgeService wraps tenant-scoped SQL queries for:
- Starting / stopping CI sessions (call_sessions table)
- Querying session summaries and artifacts (call_artifacts table)
- Approving artifacts and executing them into CRM entities (tasks, appointments)

All queries MUST include organization_id for tenant isolation (CRIT-2).

Run with: pytest tests/test_voice_ci_bridge.py -v
"""

import sys
import os
import uuid
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, call
from collections import namedtuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ORG_ID = "org-test-001"
USER_ID = 42
SESSION_UUID = str(uuid.uuid4())

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(**kwargs):
    """Create a namedtuple that mimics a SQLAlchemy Row."""
    Row = namedtuple("Row", kwargs.keys())
    return Row(**kwargs)


def _mock_db_chain(*execute_returns):
    """Build a mock DB whose successive .execute() calls return different ResultProxy mocks.

    Each entry is a dict with optional keys:
        fetchone: return for .fetchone()
        fetchall: return for .fetchall()
        scalar: return for .scalar()
    """
    db = MagicMock()
    proxies = []
    for ret in execute_returns:
        rp = MagicMock()
        rp.fetchone.return_value = ret.get("fetchone")
        rp.fetchall.return_value = ret.get("fetchall", [])
        rp.scalar.return_value = ret.get("scalar", 0)
        proxies.append(rp)
    db.execute.side_effect = proxies
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStartCISession:

    @pytest.mark.asyncio
    async def test_start_ci_session_creates_record(self):
        """start_ci_session INSERTs into call_sessions and returns a session ID."""
        db = MagicMock()
        db.execute.return_value = MagicMock()

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)

        session_id = await bridge.start_ci_session(
            context="Follow-up call about refinance",
            client_name="John Doe",
            client_phone="+15551234567",
        )

        assert db.execute.called
        sql_text = str(db.execute.call_args_list[0][0][0])
        assert "INSERT" in sql_text.upper()
        assert "call_sessions" in sql_text

        params = db.execute.call_args_list[0][0][1]
        assert params.get("org_id") == ORG_ID

        assert isinstance(session_id, str)
        assert len(session_id) > 0

        # Uses flush, not commit
        db.flush.assert_called()


class TestStopCISession:

    @pytest.mark.asyncio
    async def test_stop_ci_session_updates_status(self):
        """stop_ci_session UPDATEs the session status."""
        db = MagicMock()
        db.execute.return_value = MagicMock()

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)

        # Pass explicit session_id to skip _get_latest_session_id
        result = await bridge.stop_ci_session(session_id=SESSION_UUID, run_agents=True)

        # Should execute UPDATE
        assert db.execute.call_count >= 1
        sql = str(db.execute.call_args_list[0][0][0])
        assert "UPDATE" in sql.upper()
        assert "processing" in sql or "new_status" in sql

        assert result.get("success") is True
        assert result.get("session_id") == SESSION_UUID
        db.flush.assert_called()

    @pytest.mark.asyncio
    async def test_stop_ci_session_no_active_returns_error(self):
        """stop_ci_session returns error when no active session found."""
        rp = MagicMock()
        rp.fetchone.return_value = None
        db = MagicMock()
        db.execute.return_value = rp

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)

        # No session_id → _get_latest_session_id returns None
        result = await bridge.stop_ci_session(session_id=None, run_agents=False)

        assert result.get("success") is False or "error" in result


class TestGetLatestSession:

    @pytest.mark.asyncio
    async def test_get_latest_session_returns_most_recent(self):
        """get_session_summary fetches ordered by started_at DESC."""
        now = datetime.now(timezone.utc)

        # get_session_summary with session_id=None calls:
        # 1. _get_latest_session_id → fetchone
        # 2. session query → fetchone
        # 3. summaries query → fetchall
        # 4. actions query → fetchall
        # 5. count query → scalar
        db = _mock_db_chain(
            {"fetchone": _make_row(id=uuid.UUID(SESSION_UUID))},  # _get_latest_session_id
            {"fetchone": _make_row(                                # session info
                id=uuid.UUID(SESSION_UUID), status="completed",
                full_transcript="Hello...",
                started_at=now - timedelta(hours=1), ended_at=now,
                transcript_word_count=50,
            )},
            {"fetchall": []},  # summaries
            {"fetchall": []},  # actions
            {"scalar": 0},     # count
        )

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)

        summary = await bridge.get_session_summary(session_id=None)

        # First call is _get_latest_session_id which has ORDER BY
        first_sql = str(db.execute.call_args_list[0][0][0])
        assert "ORDER BY" in first_sql.upper()
        assert "started_at" in first_sql.lower()


class TestGetSessionSummary:

    @pytest.mark.asyncio
    async def test_get_session_summary_with_artifacts(self):
        """get_session_summary joins summary + action items from call_artifacts."""
        now = datetime.now(timezone.utc)

        # When session_id is provided, no _get_latest_session_id call.
        # Calls: session, summaries, actions, count
        db = _mock_db_chain(
            {"fetchone": _make_row(
                id=uuid.UUID(SESSION_UUID), status="completed",
                full_transcript="Discussed refinance options...",
                started_at=now - timedelta(minutes=30), ended_at=now,
                transcript_word_count=200,
            )},
            {"fetchall": [
                _make_row(
                    id=uuid.uuid4(), artifact_type="summary",
                    title="Call Summary", content="Borrower interested in refi",
                    confidence=0.95, approval_status="pending",
                ),
            ]},
            {"fetchall": [
                _make_row(
                    id=uuid.uuid4(), artifact_type="action_item",
                    title="Send rate sheet", content=json.dumps({"description": "Email rate sheet"}),
                    confidence=0.90, approval_status="pending", priority="high",
                ),
                _make_row(
                    id=uuid.uuid4(), artifact_type="action_item",
                    title="Pull credit", content=json.dumps({"description": "Run credit report"}),
                    confidence=0.88, approval_status="pending", priority="medium",
                ),
            ]},
            {"scalar": 3},
        )

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)

        summary = await bridge.get_session_summary(session_id=SESSION_UUID)

        assert summary.get("summary") is not None
        action_items = summary.get("action_items", [])
        assert len(action_items) >= 2
        assert summary.get("total_artifacts", 0) >= 3


class TestGetArtifacts:

    @pytest.mark.asyncio
    async def test_get_artifacts_filtered_by_type(self):
        """get_artifacts with artifact_type adds a filter to SQL."""
        # Without session_id: _get_latest_session_id + artifacts query
        db = _mock_db_chain(
            {"fetchone": _make_row(id=uuid.UUID(SESSION_UUID))},
            {"fetchall": [
                _make_row(
                    id=uuid.uuid4(), artifact_type="action_item",
                    title="Follow up", content=json.dumps({}),
                    confidence=0.9, approval_status="pending",
                    execution_status=None, priority="high",
                    created_at=datetime.now(timezone.utc),
                ),
            ]},
        )

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)

        result = await bridge.get_artifacts(session_id=None, artifact_type="action_item")

        artifact_sql = str(db.execute.call_args_list[-1][0][0])
        assert "artifact_type" in artifact_sql.lower()
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_artifacts_all_types(self):
        """get_artifacts without type filter returns all artifacts."""
        db = _mock_db_chain(
            {"fetchone": _make_row(id=uuid.UUID(SESSION_UUID))},
            {"fetchall": [
                _make_row(
                    id=uuid.uuid4(), artifact_type="summary",
                    title="Summary", content="text",
                    confidence=0.95, approval_status="pending",
                    execution_status=None, priority=None,
                    created_at=datetime.now(timezone.utc),
                ),
                _make_row(
                    id=uuid.uuid4(), artifact_type="action_item",
                    title="Do thing", content=json.dumps({}),
                    confidence=0.8, approval_status="pending",
                    execution_status=None, priority="medium",
                    created_at=datetime.now(timezone.utc),
                ),
            ]},
        )

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)

        result = await bridge.get_artifacts(session_id=None, artifact_type=None)
        assert len(result) == 2


class TestApproveArtifact:

    @pytest.mark.asyncio
    async def test_approve_artifact_by_id(self):
        """approve_artifact by ID UPDATEs approval_status."""
        artifact_id = str(uuid.uuid4())
        rp = MagicMock()
        rp.fetchone.return_value = _make_row(
            id=uuid.UUID(artifact_id), title="Send rate sheet", artifact_type="action_item",
        )
        db = MagicMock()
        db.execute.return_value = rp

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)

        result = await bridge.approve_artifact(artifact_id=artifact_id, title_match=None)

        assert result.get("success") is True
        assert result.get("title") == "Send rate sheet"
        db.flush.assert_called()

        sql = str(db.execute.call_args_list[0][0][0])
        assert "UPDATE" in sql.upper()
        assert "approval_status" in sql.lower()

    @pytest.mark.asyncio
    async def test_approve_artifact_by_title(self):
        """approve_artifact by title uses LIKE to find and approve."""
        # title_match path: _get_latest_session_id + UPDATE with LIKE
        db = _mock_db_chain(
            {"fetchone": _make_row(id=uuid.UUID(SESSION_UUID))},  # _get_latest_session_id
            {"fetchone": _make_row(                                # UPDATE RETURNING
                id=uuid.uuid4(), title="Send rate sheet to John", artifact_type="action_item",
            )},
        )

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)

        result = await bridge.approve_artifact(artifact_id=None, title_match="rate sheet")

        assert result.get("success") is True

        # The UPDATE with LIKE is the second execute call
        update_sql = str(db.execute.call_args_list[1][0][0])
        assert "LIKE" in update_sql.upper()


class TestExecuteApproved:

    @pytest.mark.asyncio
    async def test_execute_approved_creates_tasks(self):
        """execute_approved creates tasks from action_item artifacts."""
        db = _mock_db_chain(
            {"fetchone": _make_row(id=uuid.UUID(SESSION_UUID))},  # _get_latest_session_id
            {"fetchall": [                                         # approved artifacts
                _make_row(
                    id=uuid.uuid4(), artifact_type="action_item",
                    title="Order appraisal",
                    content=json.dumps({"description": "Order appraisal for 123 Main St"}),
                    priority="high",
                ),
            ]},
            {"fetchone": None},  # task INSERT
            {"fetchone": None},  # mark executed UPDATE
        )

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)

        result = await bridge.execute_approved(session_id=None)

        assert result.get("success") is True
        assert result.get("count", 0) >= 1
        db.flush.assert_called()

        all_sqls = [str(c[0][0]) for c in db.execute.call_args_list]
        task_inserts = [s for s in all_sqls if "INSERT" in s.upper() and "tasks" in s.lower()]
        assert len(task_inserts) >= 1

    @pytest.mark.asyncio
    async def test_execute_approved_creates_appointments(self):
        """execute_approved creates appointments from scheduled_appointment artifacts."""
        # session_id is provided, so no _get_latest_session_id call
        # Calls: 1) SELECT artifacts, 2) INSERT appointment, 3) UPDATE mark executed
        db = _mock_db_chain(
            {"fetchall": [
                _make_row(
                    id=uuid.uuid4(), artifact_type="scheduled_appointment",
                    title="Discovery call with Jane",
                    content=json.dumps({
                        "date": "2026-04-01", "time": "14:00",
                        "contact_name": "Jane Smith",
                    }),
                    priority="high",
                ),
            ]},
            {"fetchone": None},  # appointment INSERT
            {"fetchone": None},  # mark executed UPDATE
        )

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)

        result = await bridge.execute_approved(session_id=SESSION_UUID)

        assert result.get("success") is True
        db.flush.assert_called()

        all_sqls = [str(c[0][0]) for c in db.execute.call_args_list]
        appt_inserts = [s for s in all_sqls if "INSERT" in s.upper() and "appointment" in s.lower()]
        assert len(appt_inserts) >= 1


class TestTenantIsolation:

    @pytest.mark.asyncio
    async def test_start_ci_session_includes_org_id(self):
        """start_ci_session includes org_id in params."""
        db = MagicMock()
        db.execute.return_value = MagicMock()

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)
        await bridge.start_ci_session()

        for execute_call in db.execute.call_args_list:
            params = execute_call[0][1] if len(execute_call[0]) > 1 else {}
            assert "org_id" in params or "organization_id" in params, \
                f"Missing tenant scope in params: {params}"

    @pytest.mark.asyncio
    async def test_get_artifacts_includes_org_id(self):
        """get_artifacts SQL includes org_id in params."""
        db = _mock_db_chain(
            {"fetchone": _make_row(id=uuid.UUID(SESSION_UUID))},
            {"fetchall": []},
        )

        from services.voice_ci_bridge_service import VoiceCIBridgeService
        bridge = VoiceCIBridgeService(db, ORG_ID, USER_ID)
        await bridge.get_artifacts(session_id=None, artifact_type=None)

        for execute_call in db.execute.call_args_list:
            params = execute_call[0][1] if len(execute_call[0]) > 1 else {}
            assert "org_id" in params or "organization_id" in params, \
                f"Missing tenant scope in params: {params}"
