"""
Tests for voice CI tool handler functions in routes/voice/ci_tools.py.

Each handler delegates to VoiceCIBridgeService (lazy-imported from
services.voice_ci_bridge_service), so we patch the class at its source module.

Run with: pytest tests/test_voice_ci_tools.py -v
"""

import sys
import os
import uuid
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ORG_ID = "org-test-001"
USER_ID = 42
SESSION_ID = str(uuid.uuid4())

pytestmark = [pytest.mark.unit]

PATCH_TARGET = "services.voice_ci_bridge_service.VoiceCIBridgeService"


def _make_mock_bridge(**method_returns):
    """Create a mock VoiceCIBridgeService with async return values."""
    bridge = MagicMock()
    for method_name, return_value in method_returns.items():
        setattr(bridge, method_name, AsyncMock(return_value=return_value))
    return bridge


# ---------------------------------------------------------------------------
# 1. handle_start_call_recording
# ---------------------------------------------------------------------------

class TestHandleStartCallRecording:

    @pytest.mark.asyncio
    @patch(PATCH_TARGET)
    async def test_handle_start_call_recording_returns_session_id(self, MockBridgeClass):
        mock_bridge = _make_mock_bridge(start_ci_session=SESSION_ID)
        MockBridgeClass.return_value = mock_bridge

        from routes.voice.ci_tools import handle_start_call_recording

        result = await handle_start_call_recording(
            args={"context": "Refi discussion", "client_name": "John", "client_phone": "+15551234567"},
            db=MagicMock(),
            organization_id=ORG_ID,
            user_id=USER_ID,
        )

        assert result["success"] is True
        assert result["session_id"] == SESSION_ID
        assert "message" in result
        mock_bridge.start_ci_session.assert_awaited_once_with(
            context="Refi discussion",
            client_name="John",
            client_phone="+15551234567",
        )


# ---------------------------------------------------------------------------
# 2. handle_stop_call_recording
# ---------------------------------------------------------------------------

class TestHandleStopCallRecording:

    @pytest.mark.asyncio
    @patch(PATCH_TARGET)
    async def test_handle_stop_call_recording_triggers_agents(self, MockBridgeClass):
        mock_bridge = _make_mock_bridge(
            stop_ci_session={"success": True, "session_id": SESSION_ID}
        )
        MockBridgeClass.return_value = mock_bridge

        from routes.voice.ci_tools import handle_stop_call_recording

        result = await handle_stop_call_recording(
            args={"session_id": SESSION_ID},
            db=MagicMock(),
            organization_id=ORG_ID,
            user_id=USER_ID,
        )

        assert result["success"] is True
        assert "analyzing" in result["message"].lower() or "stopped" in result["message"].lower()
        mock_bridge.stop_ci_session.assert_awaited_once_with(
            session_id=SESSION_ID,
            run_agents=True,
        )


# ---------------------------------------------------------------------------
# 3. handle_get_recent_call_summary
# ---------------------------------------------------------------------------

class TestHandleGetRecentCallSummary:

    @pytest.mark.asyncio
    @patch(PATCH_TARGET)
    async def test_handle_get_recent_call_summary_formats_for_voice(self, MockBridgeClass):
        mock_bridge = _make_mock_bridge(
            get_session_summary={
                "summary": "Borrower wants to refinance. Good credit, 720 FICO.",
                "action_items": [
                    {"title": "Send rate sheet"},
                    {"title": "Pull credit report"},
                    {"title": "Order appraisal"},
                ],
                "total_artifacts": 5,
            }
        )
        MockBridgeClass.return_value = mock_bridge

        from routes.voice.ci_tools import handle_get_recent_call_summary

        result = await handle_get_recent_call_summary(
            args={"session_id": SESSION_ID},
            db=MagicMock(),
            organization_id=ORG_ID,
            user_id=USER_ID,
        )

        assert result["success"] is True
        assert "refinance" in result["message"].lower() or "720" in result["message"]
        assert "3 action item" in result["message"].lower() or "action items" in result["message"].lower()
        assert "rate sheet" in result["message"].lower()
        assert "5" in result["message"] or "total" in result["message"].lower()

    @pytest.mark.asyncio
    @patch(PATCH_TARGET)
    async def test_handle_get_recent_call_summary_error(self, MockBridgeClass):
        mock_bridge = _make_mock_bridge(
            get_session_summary={"error": "No sessions found"}
        )
        MockBridgeClass.return_value = mock_bridge

        from routes.voice.ci_tools import handle_get_recent_call_summary

        result = await handle_get_recent_call_summary(
            args={},
            db=MagicMock(),
            organization_id=ORG_ID,
            user_id=USER_ID,
        )

        assert result["success"] is False
        assert "No sessions found" in result["message"]


# ---------------------------------------------------------------------------
# 4. handle_get_call_artifacts
# ---------------------------------------------------------------------------

class TestHandleGetCallArtifacts:

    @pytest.mark.asyncio
    @patch(PATCH_TARGET)
    async def test_handle_get_call_artifacts_filters_by_type(self, MockBridgeClass):
        mock_artifacts = [
            {"id": str(uuid.uuid4()), "type": "action_item", "title": "Follow up call"},
            {"id": str(uuid.uuid4()), "type": "action_item", "title": "Send docs"},
        ]
        mock_bridge = _make_mock_bridge(get_artifacts=mock_artifacts)
        MockBridgeClass.return_value = mock_bridge

        from routes.voice.ci_tools import handle_get_call_artifacts

        result = await handle_get_call_artifacts(
            args={"artifact_type": "action_item", "session_id": SESSION_ID},
            db=MagicMock(),
            organization_id=ORG_ID,
            user_id=USER_ID,
        )

        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["artifacts"]) == 2
        mock_bridge.get_artifacts.assert_awaited_once_with(
            session_id=SESSION_ID,
            artifact_type="action_item",
        )
        assert "2 artifact" in result["message"].lower()

    @pytest.mark.asyncio
    @patch(PATCH_TARGET)
    async def test_handle_get_call_artifacts_empty(self, MockBridgeClass):
        mock_bridge = _make_mock_bridge(get_artifacts=[])
        MockBridgeClass.return_value = mock_bridge

        from routes.voice.ci_tools import handle_get_call_artifacts

        result = await handle_get_call_artifacts(
            args={},
            db=MagicMock(),
            organization_id=ORG_ID,
            user_id=USER_ID,
        )

        assert result["success"] is True
        assert result["count"] == 0
        assert "no artifact" in result["message"].lower()


# ---------------------------------------------------------------------------
# 5. handle_approve_artifact
# ---------------------------------------------------------------------------

class TestHandleApproveArtifact:

    @pytest.mark.asyncio
    @patch(PATCH_TARGET)
    async def test_handle_approve_artifact_by_id(self, MockBridgeClass):
        artifact_id = str(uuid.uuid4())
        mock_bridge = _make_mock_bridge(
            approve_artifact={"success": True, "title": "Send rate sheet"}
        )
        MockBridgeClass.return_value = mock_bridge

        from routes.voice.ci_tools import handle_approve_artifact

        result = await handle_approve_artifact(
            args={"artifact_id": artifact_id},
            db=MagicMock(),
            organization_id=ORG_ID,
            user_id=USER_ID,
        )

        assert result["success"] is True
        assert "Send rate sheet" in result["message"]
        mock_bridge.approve_artifact.assert_awaited_once_with(
            artifact_id=artifact_id,
            title_match=None,
        )

    @pytest.mark.asyncio
    @patch(PATCH_TARGET)
    async def test_handle_approve_artifact_by_title(self, MockBridgeClass):
        mock_bridge = _make_mock_bridge(
            approve_artifact={"success": True, "title": "Rate sheet for borrower"}
        )
        MockBridgeClass.return_value = mock_bridge

        from routes.voice.ci_tools import handle_approve_artifact

        result = await handle_approve_artifact(
            args={"artifact_title": "rate sheet"},
            db=MagicMock(),
            organization_id=ORG_ID,
            user_id=USER_ID,
        )

        assert result["success"] is True
        mock_bridge.approve_artifact.assert_awaited_once_with(
            artifact_id=None,
            title_match="rate sheet",
        )

    @pytest.mark.asyncio
    @patch(PATCH_TARGET)
    async def test_handle_approve_artifact_failure(self, MockBridgeClass):
        mock_bridge = _make_mock_bridge(
            approve_artifact={"success": False, "error": "Artifact not found"}
        )
        MockBridgeClass.return_value = mock_bridge

        from routes.voice.ci_tools import handle_approve_artifact

        result = await handle_approve_artifact(
            args={"artifact_id": "nonexistent"},
            db=MagicMock(),
            organization_id=ORG_ID,
            user_id=USER_ID,
        )

        assert result["success"] is False


# ---------------------------------------------------------------------------
# 6. handle_execute_artifacts
# ---------------------------------------------------------------------------

class TestHandleExecuteArtifacts:

    @pytest.mark.asyncio
    @patch(PATCH_TARGET)
    async def test_handle_execute_artifacts_returns_count(self, MockBridgeClass):
        mock_bridge = _make_mock_bridge(
            execute_approved={
                "success": True,
                "count": 3,
                "results": [
                    {"title": "Order appraisal"},
                    {"title": "Send rate sheet"},
                    {"title": "Schedule follow-up"},
                ],
            }
        )
        MockBridgeClass.return_value = mock_bridge

        from routes.voice.ci_tools import handle_execute_artifacts

        result = await handle_execute_artifacts(
            args={"session_id": SESSION_ID},
            db=MagicMock(),
            organization_id=ORG_ID,
            user_id=USER_ID,
        )

        assert result["success"] is True
        assert "3" in result["message"]
        assert "Order appraisal" in result["message"] or "rate sheet" in result["message"].lower()


# ---------------------------------------------------------------------------
# 7. handle_send_document_checklist
# ---------------------------------------------------------------------------

class TestHandleSendDocumentChecklist:

    @pytest.mark.asyncio
    @patch(PATCH_TARGET)
    async def test_handle_send_document_checklist_formats_text(self, MockBridgeClass):
        mock_bridge = _make_mock_bridge(
            get_document_checklist={
                "documents": [
                    {"title": "Recent pay stubs", "details": "Last 30 days"},
                    {"title": "W-2 forms", "details": "Last 2 years"},
                    {"title": "Bank statements", "details": "Last 2 months"},
                ],
                "count": 3,
            }
        )
        MockBridgeClass.return_value = mock_bridge

        from routes.voice.ci_tools import handle_send_document_checklist

        # telnyx SDK v2+ uses Client, not telnyx.Message directly.
        # The handler code does `telnyx.Message.create(...)` so mock it with create=True.
        with patch("telnyx.Message", create=True) as mock_message:
            mock_message.create.return_value = MagicMock()
            with patch.dict(os.environ, {
                "TELNYX_API_KEY": "fake-key",
                "TELNYX_FROM_NUMBER": "+15550001111",
            }):
                result = await handle_send_document_checklist(
                    args={
                        "send_via": "sms",
                        "recipient_phone": "+15559876543",
                    },
                    db=MagicMock(),
                    organization_id=ORG_ID,
                    user_id=USER_ID,
                )

        assert result["success"] is True
        assert "3" in result["message"]
        assert result.get("documents_sent") == 3

    @pytest.mark.asyncio
    @patch(PATCH_TARGET)
    async def test_handle_send_document_checklist_no_documents(self, MockBridgeClass):
        mock_bridge = _make_mock_bridge(
            get_document_checklist={"documents": [], "count": 0}
        )
        MockBridgeClass.return_value = mock_bridge

        from routes.voice.ci_tools import handle_send_document_checklist

        result = await handle_send_document_checklist(
            args={},
            db=MagicMock(),
            organization_id=ORG_ID,
            user_id=USER_ID,
        )

        assert result["success"] is False
        assert "no document" in result["message"].lower()
