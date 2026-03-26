"""Tests for P4: Progressive artifact streaming via WebSocket."""
import sys, os, uuid, pytest, json
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
pytestmark = [pytest.mark.unit]

ORG_ID = 1
SESSION_ID = str(uuid.uuid4())


class TestProgressiveStreaming:
    """Test that the orchestrator supports per-agent callbacks."""

    @pytest.mark.asyncio
    async def test_run_agents_accepts_callback(self):
        """Verify run_agents accepts on_agent_complete callback parameter."""
        from services.call_monitoring.orchestrator_service import CallMonitoringOrchestrator
        db = MagicMock()
        # Mock the session query
        mock_session = {
            "id": SESSION_ID,
            "full_transcript": "Hi I want to refinance my home at 123 Main St",
            "loan_id": None,
            "lead_id": None,
            "participants": [],
            "capture_mode": "mobile_app",
            "metadata": {},
        }
        orch = CallMonitoringOrchestrator(db, organization_id=ORG_ID)
        orch.get_session = MagicMock(return_value=mock_session)
        orch._enrich_context = AsyncMock(side_effect=lambda ctx: ctx)
        orch._run_agents_parallel = AsyncMock(return_value={})
        orch._merge_artifacts = MagicMock(return_value=MagicMock())
        orch._store_artifacts = AsyncMock(return_value=[])

        callback = AsyncMock()
        # run_agents should accept on_agent_complete kwarg
        try:
            await orch.run_agents(SESSION_ID, on_agent_complete=callback)
        except TypeError:
            pytest.fail("run_agents does not accept on_agent_complete callback yet")
