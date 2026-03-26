"""Tests for P8: AgentFeedbackService."""
import sys, os, uuid, pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
pytestmark = [pytest.mark.unit]

ORG_ID = 1


class TestAgentFeedbackService:

    def test_get_approval_stats_empty(self):
        from services.call_monitoring.feedback_service import AgentFeedbackService
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        svc = AgentFeedbackService(db, ORG_ID)
        result = svc.get_approval_stats()
        assert result["agents"] == {}

    def test_get_approval_stats_calculates_rate(self):
        from services.call_monitoring.feedback_service import AgentFeedbackService
        db = MagicMock()
        mock_row = MagicMock()
        mock_row.agent_type = "scribe"
        mock_row.artifact_type = "action_item"
        mock_row.total = 10
        mock_row.approved = 8
        mock_row.rejected = 2
        mock_row.pending = 0
        mock_row.avg_confidence = 0.85
        db.execute.return_value.fetchall.return_value = [mock_row]
        svc = AgentFeedbackService(db, ORG_ID)
        result = svc.get_approval_stats()
        assert "scribe" in result["agents"]
        assert result["agents"]["scribe"]["approval_rate"] == 80.0

    def test_generate_feedback_low_approval(self):
        from services.call_monitoring.feedback_service import AgentFeedbackService
        db = MagicMock()
        # Stats row: 10 total, 3 approved, 7 rejected
        mock_row = MagicMock()
        mock_row.agent_type = "marketing"
        mock_row.artifact_type = "content_idea"
        mock_row.total = 10
        mock_row.approved = 3
        mock_row.rejected = 7
        mock_row.pending = 0
        mock_row.avg_confidence = 0.6
        db.execute.return_value.fetchall.return_value = [mock_row]
        # Mock rejected titles query
        db.execute.return_value.fetchall.side_effect = [
            [mock_row],  # stats query
            [],  # rejected titles query
        ]
        svc = AgentFeedbackService(db, ORG_ID)
        feedback = svc.generate_feedback_prompt("marketing")
        assert feedback is not None
        assert "approval rate" in feedback.lower() or "WARNING" in feedback

    def test_generate_feedback_well_calibrated_returns_none(self):
        from services.call_monitoring.feedback_service import AgentFeedbackService
        db = MagicMock()
        mock_row = MagicMock()
        mock_row.agent_type = "scribe"
        mock_row.artifact_type = "summary"
        mock_row.total = 20
        mock_row.approved = 19
        mock_row.rejected = 1
        mock_row.pending = 0
        mock_row.avg_confidence = 0.9
        db.execute.return_value.fetchall.return_value = [mock_row]
        svc = AgentFeedbackService(db, ORG_ID)
        feedback = svc.generate_feedback_prompt("scribe")
        assert feedback is None  # Well-calibrated, no feedback needed

    def test_generate_feedback_insufficient_samples_returns_none(self):
        from services.call_monitoring.feedback_service import AgentFeedbackService
        db = MagicMock()
        mock_row = MagicMock()
        mock_row.agent_type = "calculator"
        mock_row.artifact_type = "calculator_results"
        mock_row.total = 3
        mock_row.approved = 1
        mock_row.rejected = 2
        mock_row.pending = 0
        mock_row.avg_confidence = 0.7
        db.execute.return_value.fetchall.return_value = [mock_row]
        svc = AgentFeedbackService(db, ORG_ID)
        feedback = svc.generate_feedback_prompt("calculator")
        assert feedback is None  # Not enough samples
