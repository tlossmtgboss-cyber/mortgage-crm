"""Tests for P5: SmartTaskExecutor service."""
import sys, os, uuid, pytest, json
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
pytestmark = [pytest.mark.unit]

ORG_ID = 1
USER_ID = 42
SESSION_ID = str(uuid.uuid4())
LOAN_ID = str(uuid.uuid4())


class TestSmartTaskExecutor:

    def _make_artifact(self, **kwargs):
        artifact = MagicMock()
        artifact.artifact_type = kwargs.get("artifact_type", "action_item")
        artifact.title = kwargs.get("title", "Send rate sheet")
        artifact.content = kwargs.get("content", "Send rate comparison to borrower")
        artifact.structured_data = kwargs.get("structured_data", {})
        artifact.priority = kwargs.get("priority", "high")
        artifact.confidence = kwargs.get("confidence", 0.85)
        artifact.id = str(uuid.uuid4())
        return artifact

    @pytest.mark.asyncio
    async def test_creates_task_with_due_date(self):
        from services.call_monitoring.smart_task_executor import SmartTaskExecutor, PRIORITY_DUE_DAYS
        db = MagicMock()
        # Mock session context
        mock_session = MagicMock()
        mock_session.loan_id = LOAN_ID
        mock_session.lead_id = None
        mock_session.user_id = USER_ID
        mock_session.metadata = {}
        # First call = session context, second = duplicate check (None = no dup),
        # third = resolve_assignee, fourth = INSERT RETURNING
        db.execute.return_value.fetchone.side_effect = [mock_session, None, MagicMock(loan_officer_id=USER_ID), MagicMock(id="new-task")]

        executor = SmartTaskExecutor(db, ORG_ID, USER_ID)
        artifact = self._make_artifact(priority="high")
        result = await executor.execute_artifact(artifact, SESSION_ID)
        assert result["type"] == "task_created"
        assert result["due_date"] is not None
        assert result["priority"] == "high"

    @pytest.mark.asyncio
    async def test_duplicate_detection_skips(self):
        from services.call_monitoring.smart_task_executor import SmartTaskExecutor
        db = MagicMock()
        mock_session = MagicMock()
        mock_session.loan_id = LOAN_ID
        mock_session.lead_id = None
        mock_session.user_id = USER_ID
        mock_session.metadata = {}

        existing_task = MagicMock()
        existing_task.id = str(uuid.uuid4())

        # First call = session context, second = duplicate check
        db.execute.return_value.fetchone.side_effect = [mock_session, existing_task]

        executor = SmartTaskExecutor(db, ORG_ID, USER_ID)
        artifact = self._make_artifact(title="Send rate sheet")
        result = await executor.execute_artifact(artifact, SESSION_ID)
        assert result["type"] == "duplicate_skipped"

    @pytest.mark.asyncio
    async def test_appointment_creation(self):
        from services.call_monitoring.smart_task_executor import SmartTaskExecutor
        db = MagicMock()
        mock_session = MagicMock()
        mock_session.loan_id = None
        mock_session.lead_id = None
        mock_session.user_id = USER_ID
        mock_session.metadata = '{"client_name": "John Smith"}'
        db.execute.return_value.fetchone.return_value = mock_session

        executor = SmartTaskExecutor(db, ORG_ID, USER_ID)
        artifact = self._make_artifact(
            artifact_type="scheduled_appointment",
            title="Follow-up call with borrower",
        )
        result = await executor.execute_artifact(artifact, SESSION_ID)
        assert result["type"] == "appointment_created"
