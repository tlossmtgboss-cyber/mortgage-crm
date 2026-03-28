"""
Tests for the start_scheduling_workflow tool handler in
routes/voice/tool_handlers.py :: handle_browser_function_call()

Verifies that the handler now creates a VoiceWorkflow record via the
state machine rather than sending SMS directly (stateless).

All tests mock external dependencies (VoiceSchedulingWorkflowService,
SchedulingConversationService, DB) and verify:
- Correct argument validation (missing name/phone)
- VoiceWorkflow is created via create_workflow()
- SchedulingConversationService.initiate_scheduling() is called
- workflow_id is returned in the response
- Error handling rolls back the DB session

Run with: pytest tests/test_voice_tool_handler_scheduling.py -v
"""

import sys
import os
import itertools
import pytest
from unittest.mock import MagicMock, patch

_backend = os.path.join(os.path.dirname(__file__), '..')
if _backend not in sys.path:
    sys.path.insert(0, _backend)

pytestmark = [pytest.mark.unit]

ORG_ID = "org-test-001"
USER_ID = 42

# Each test call gets a unique session ID to avoid hitting the in-memory rate
# limiter (start_scheduling_workflow is capped at 2 per 300 seconds).
_session_counter = itertools.count()


def _mock_db():
    db = MagicMock()
    result_proxy = MagicMock()
    result_proxy.fetchone.return_value = None
    result_proxy.fetchall.return_value = []
    db.execute.return_value = result_proxy
    return db


async def _call(func_name: str, args: dict, db=None, org_id=ORG_ID, user_id=USER_ID):
    from routes.voice.tool_handlers import handle_browser_function_call
    if db is None:
        db = _mock_db()
    session_id = f"test-sched-{next(_session_counter)}"
    return await handle_browser_function_call(
        func_name, args, db,
        session_id=session_id,
        organization_id=org_id,
        user_id=user_id,
    )


# ===========================================================================
# Argument Validation
# ===========================================================================

class TestSchedulingWorkflowValidation:

    @pytest.mark.asyncio
    async def test_missing_contact_name_returns_error(self):
        result = await _call("start_scheduling_workflow", {
            "contact_phone": "+15551234567",
        })
        assert result["success"] is False
        assert "Contact name and phone number are required" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_contact_phone_returns_error(self):
        result = await _call("start_scheduling_workflow", {
            "contact_name": "John Doe",
        })
        assert result["success"] is False
        assert "Contact name and phone number are required" in result["message"]

    @pytest.mark.asyncio
    async def test_empty_strings_returns_error(self):
        result = await _call("start_scheduling_workflow", {
            "contact_name": "",
            "contact_phone": "",
        })
        assert result["success"] is False
        assert "Contact name and phone number are required" in result["message"]


# ===========================================================================
# Happy Path — workflow creation
# ===========================================================================

class TestSchedulingWorkflowCreation:

    @pytest.mark.asyncio
    @patch("routes.voice.tool_handlers.SchedulingConversationService", create=True)
    @patch("routes.voice.tool_handlers.VoiceSchedulingWorkflowService", create=True)
    async def test_creates_workflow_and_returns_id(self, mock_vw_cls, mock_sched_cls):
        """The handler should create a VoiceWorkflow and return its id."""
        # Because imports are lazy (inside the elif block), we patch the
        # service modules where they are imported from.
        fake_workflow = MagicMock()
        fake_workflow.id = 99

        mock_vw_instance = MagicMock()
        mock_vw_instance.create_workflow.return_value = fake_workflow

        mock_sched_instance = MagicMock()
        mock_sched_instance.initiate_scheduling.return_value = {
            "success": True,
            "message_sent": "Hi John...",
            "slots_offered": ["Monday 10:00 AM"],
        }

        db = _mock_db()

        with patch(
            "services.voice_scheduling_workflow_service.VoiceSchedulingWorkflowService",
            return_value=mock_vw_instance,
        ), patch(
            "services.scheduling_conversation_service.SchedulingConversationService",
            return_value=mock_sched_instance,
        ):
            result = await _call("start_scheduling_workflow", {
                "contact_name": "John Doe",
                "contact_phone": "+15551234567",
                "meeting_type": "discovery_call",
                "message_context": "discuss pre-approval",
            }, db=db)

        assert result["success"] is True
        assert result["workflow_id"] == 99
        assert "SMS sent to John Doe" in result["message"]

    @pytest.mark.asyncio
    async def test_create_workflow_is_called_with_correct_args(self):
        """Verify create_workflow receives the expected keyword arguments."""
        fake_workflow = MagicMock()
        fake_workflow.id = 42

        mock_vw_instance = MagicMock()
        mock_vw_instance.create_workflow.return_value = fake_workflow

        mock_sched_instance = MagicMock()
        mock_sched_instance.initiate_scheduling.return_value = {"success": True}

        db = _mock_db()

        with patch(
            "services.voice_scheduling_workflow_service.VoiceSchedulingWorkflowService",
            return_value=mock_vw_instance,
        ), patch(
            "services.scheduling_conversation_service.SchedulingConversationService",
            return_value=mock_sched_instance,
        ):
            await _call("start_scheduling_workflow", {
                "contact_name": "Jane Smith",
                "contact_phone": "+15559876543",
                "meeting_type": "rate_review",
                "message_context": "rate lock expiring",
            }, db=db, org_id="org-123", user_id=7)

        mock_vw_instance.create_workflow.assert_called_once_with(
            organization_id="org-123",
            user_id=7,
            workflow_type="voice_schedule",
            contact_name="Jane Smith",
            contact_phone="+15559876543",
            meeting_type="rate_review",
            message_context="rate lock expiring",
        )

    @pytest.mark.asyncio
    async def test_initiate_scheduling_is_called_with_correct_args(self):
        """Verify initiate_scheduling receives the workflow_id and contact info."""
        fake_workflow = MagicMock()
        fake_workflow.id = 55

        mock_vw_instance = MagicMock()
        mock_vw_instance.create_workflow.return_value = fake_workflow

        mock_sched_instance = MagicMock()
        mock_sched_instance.initiate_scheduling.return_value = {"success": True}

        db = _mock_db()

        with patch(
            "services.voice_scheduling_workflow_service.VoiceSchedulingWorkflowService",
            return_value=mock_vw_instance,
        ), patch(
            "services.scheduling_conversation_service.SchedulingConversationService",
            return_value=mock_sched_instance,
        ):
            await _call("start_scheduling_workflow", {
                "contact_name": "Bob Wilson",
                "contact_phone": "+15550001111",
                "meeting_type": "discovery_call",
                "message_context": "",
            }, db=db, org_id="org-456", user_id=10)

        mock_sched_instance.initiate_scheduling.assert_called_once_with(
            workflow_id=55,
            user_id=10,
            organization_id="org-456",
            contact_name="Bob Wilson",
            contact_phone="+15550001111",
            meeting_type="discovery_call",
            message_context="",
        )

    @pytest.mark.asyncio
    async def test_defaults_meeting_type_and_message_context(self):
        """When meeting_type and message_context are omitted, use defaults."""
        fake_workflow = MagicMock()
        fake_workflow.id = 1

        mock_vw_instance = MagicMock()
        mock_vw_instance.create_workflow.return_value = fake_workflow

        mock_sched_instance = MagicMock()
        mock_sched_instance.initiate_scheduling.return_value = {"success": True}

        db = _mock_db()

        with patch(
            "services.voice_scheduling_workflow_service.VoiceSchedulingWorkflowService",
            return_value=mock_vw_instance,
        ), patch(
            "services.scheduling_conversation_service.SchedulingConversationService",
            return_value=mock_sched_instance,
        ):
            result = await _call("start_scheduling_workflow", {
                "contact_name": "Alice",
                "contact_phone": "+15550002222",
            }, db=db)

        assert result["success"] is True
        # Verify defaults were used
        call_kwargs = mock_vw_instance.create_workflow.call_args
        assert call_kwargs.kwargs["meeting_type"] == "discovery_call"
        assert call_kwargs.kwargs["message_context"] == ""


# ===========================================================================
# Error Handling
# ===========================================================================

class TestSchedulingWorkflowErrorHandling:

    @pytest.mark.asyncio
    async def test_service_exception_rolls_back_and_returns_error(self):
        """If create_workflow raises, handler should rollback and return error."""
        mock_vw_instance = MagicMock()
        mock_vw_instance.create_workflow.side_effect = RuntimeError("DB connection lost")

        db = _mock_db()

        with patch(
            "services.voice_scheduling_workflow_service.VoiceSchedulingWorkflowService",
            return_value=mock_vw_instance,
        ):
            result = await _call("start_scheduling_workflow", {
                "contact_name": "Error Test",
                "contact_phone": "+15550003333",
            }, db=db)

        assert result["success"] is False
        assert "Failed to start scheduling workflow" in result["message"]
        db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_initiate_scheduling_exception_rolls_back(self):
        """If initiate_scheduling raises after workflow creation, handler rolls back."""
        fake_workflow = MagicMock()
        fake_workflow.id = 77

        mock_vw_instance = MagicMock()
        mock_vw_instance.create_workflow.return_value = fake_workflow

        mock_sched_instance = MagicMock()
        mock_sched_instance.initiate_scheduling.side_effect = ValueError("SMS send failed")

        db = _mock_db()

        with patch(
            "services.voice_scheduling_workflow_service.VoiceSchedulingWorkflowService",
            return_value=mock_vw_instance,
        ), patch(
            "services.scheduling_conversation_service.SchedulingConversationService",
            return_value=mock_sched_instance,
        ):
            result = await _call("start_scheduling_workflow", {
                "contact_name": "SMS Fail",
                "contact_phone": "+15550004444",
            }, db=db)

        assert result["success"] is False
        assert "Failed to start scheduling workflow" in result["message"]
        db.rollback.assert_called_once()
