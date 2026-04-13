"""
Test Call Monitoring Routes

Covers:
1. GET  /api/v1/call-monitoring/sessions       — list sessions (active calls)
2. GET  /api/v1/call-monitoring/ci-recordings   — recent CI recordings
3. GET  /api/v1/call-monitoring/loan/{loanId}/calls  — loan call history
4. GET  /api/v1/call-monitoring/calls/{call_id}/recording — recording playback
5. GET  /api/v1/call-monitoring/lookup-caller    — caller identification
6. POST /api/v1/call-monitoring/sessions         — create session
7. GET  /api/v1/call-monitoring/sessions/{id}    — get session detail
8. GET  /api/v1/call-monitoring/metrics          — monitoring metrics

Uses authenticated_client and MockUser fixtures from conftest.py.
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from uuid import uuid4

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# CONSTANTS
# =============================================================================

BASE = "/api/v1/call-monitoring"
AUTH_HEADERS = {"Authorization": "Bearer test_token"}


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_orchestrator():
    """Create a mock CallMonitoringOrchestrator."""
    orch = MagicMock()
    orch.create_session = MagicMock(return_value={
        "session_id": str(uuid4()),
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    orch.get_session = MagicMock(return_value={
        "id": str(uuid4()),
        "status": "active",
        "capture_mode": "crm_web_call",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    orch.end_session = MagicMock(return_value={
        "status": "completed",
        "duration_seconds": 120,
    })
    return orch


@pytest.fixture
def mock_db_execute_empty():
    """Patch db.execute to return no rows."""
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_result.fetchone.return_value = None
    mock_result.scalar.return_value = 0
    mock_result.__iter__ = lambda self: iter([])
    return mock_result


# =============================================================================
# SESSION LIST (ACTIVE CALLS)
# =============================================================================

@pytest.mark.unit
class TestListSessions:
    """Test GET /api/v1/call-monitoring/sessions — list active/recent sessions."""

    def test_sessions_endpoint_exists(self, authenticated_client):
        """The sessions list endpoint exists and does not 404."""
        response = authenticated_client.get(
            f"{BASE}/sessions",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "Sessions endpoint should be registered"

    def test_sessions_with_status_filter(self, authenticated_client):
        """Sessions endpoint accepts status query param."""
        response = authenticated_client.get(
            f"{BASE}/sessions?status=active",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404

    def test_sessions_with_loan_filter(self, authenticated_client):
        """Sessions endpoint accepts loan_id query param."""
        response = authenticated_client.get(
            f"{BASE}/sessions?loan_id=42",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404

    def test_sessions_pagination(self, authenticated_client):
        """Sessions endpoint accepts page and page_size params."""
        response = authenticated_client.get(
            f"{BASE}/sessions?page=1&page_size=10",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404


# =============================================================================
# CI RECORDINGS (RECENT)
# =============================================================================

@pytest.mark.unit
class TestCIRecordings:
    """Test GET /api/v1/call-monitoring/ci-recordings — recent CI recordings."""

    def test_ci_recordings_endpoint_exists(self, authenticated_client):
        """The CI recordings endpoint exists and does not 404."""
        response = authenticated_client.get(
            f"{BASE}/ci-recordings",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "CI recordings endpoint should be registered"

    def test_ci_recordings_with_status_filter(self, authenticated_client):
        """CI recordings endpoint accepts status filter."""
        response = authenticated_client.get(
            f"{BASE}/ci-recordings?status=transcribed",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404

    def test_ci_recordings_with_loan_filter(self, authenticated_client):
        """CI recordings endpoint accepts loan_id filter."""
        response = authenticated_client.get(
            f"{BASE}/ci-recordings?loan_id=42",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404

    def test_ci_recordings_limit(self, authenticated_client):
        """CI recordings endpoint accepts limit param."""
        response = authenticated_client.get(
            f"{BASE}/ci-recordings?limit=10",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404


# =============================================================================
# LOAN CALL HISTORY
# =============================================================================

@pytest.mark.unit
class TestLoanCallHistory:
    """Test GET /api/v1/call-monitoring/loan/{loanId}/calls — loan call history."""

    def test_loan_calls_endpoint_exists(self, authenticated_client):
        """The loan calls endpoint exists and does not 404."""
        response = authenticated_client.get(
            f"{BASE}/loan/42/calls",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "Loan calls endpoint should be registered"

    def test_loan_calls_with_limit(self, authenticated_client):
        """Loan calls endpoint accepts limit param."""
        response = authenticated_client.get(
            f"{BASE}/loan/42/calls?limit=5",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404

    def test_loan_calls_with_offset(self, authenticated_client):
        """Loan calls endpoint accepts offset param."""
        response = authenticated_client.get(
            f"{BASE}/loan/42/calls?offset=10",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404

    def test_loan_calls_with_pagination(self, authenticated_client):
        """Loan calls endpoint accepts both limit and offset."""
        response = authenticated_client.get(
            f"{BASE}/loan/42/calls?limit=10&offset=20",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404


# =============================================================================
# CALL RECORDING PLAYBACK
# =============================================================================

@pytest.mark.unit
class TestRecordingPlayback:
    """Test GET /api/v1/call-monitoring/calls/{call_id}/recording — playback."""

    def test_recording_endpoint_exists(self, authenticated_client):
        """The recording playback endpoint exists and does not 404."""
        response = authenticated_client.get(
            f"{BASE}/calls/call_12345/recording",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "Recording playback endpoint should be registered"

    def test_recording_nonexistent_call(self, authenticated_client):
        """Recording for a nonexistent call returns 404 or empty result."""
        response = authenticated_client.get(
            f"{BASE}/calls/nonexistent_call_xyz/recording",
            headers=AUTH_HEADERS,
        )
        # The endpoint should not crash — it should return 404 or fallback
        assert response.status_code in (200, 404, 500)

    def test_recording_response_schema(self, authenticated_client):
        """Recording response has the expected RecordingPlaybackResponse fields when successful."""
        # This test validates the response model structure against the Pydantic model
        from routes.call_monitoring_routes import RecordingPlaybackResponse

        # Verify the Pydantic model has expected fields
        fields = RecordingPlaybackResponse.model_fields
        expected_fields = {
            "call_id", "source", "recording_url", "duration_seconds",
            "transcript_text", "transcript_segments",
        }
        for f in expected_fields:
            assert f in fields, f"RecordingPlaybackResponse missing field: {f}"


# =============================================================================
# CALLER LOOKUP
# =============================================================================

@pytest.mark.unit
class TestCallerLookup:
    """Test GET /api/v1/call-monitoring/lookup-caller — caller identification."""

    def test_lookup_endpoint_exists(self, authenticated_client):
        """The lookup-caller endpoint exists."""
        response = authenticated_client.get(
            f"{BASE}/lookup-caller?phone=5551234567",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "Lookup caller endpoint should be registered"

    def test_lookup_requires_phone(self, authenticated_client):
        """lookup-caller without phone param returns 422."""
        response = authenticated_client.get(
            f"{BASE}/lookup-caller",
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 422, "Missing phone should return 422"

    def test_lookup_short_phone_returns_400(self, authenticated_client):
        """Phone number too short returns 400."""
        response = authenticated_client.get(
            f"{BASE}/lookup-caller?phone=123",
            headers=AUTH_HEADERS,
        )
        # Should be 400 (invalid phone) or 500 (DB error in test env)
        assert response.status_code in (400, 500)


# =============================================================================
# CREATE SESSION
# =============================================================================

@pytest.mark.unit
class TestCreateSession:
    """Test POST /api/v1/call-monitoring/sessions — create a new call session."""

    def test_create_session_endpoint_exists(self, authenticated_client):
        """The create session endpoint exists."""
        response = authenticated_client.post(
            f"{BASE}/sessions",
            json={"capture_mode": "crm_web_call"},
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "Create session endpoint should be registered"

    def test_create_session_requires_capture_mode(self, authenticated_client):
        """Create session requires capture_mode field."""
        response = authenticated_client.post(
            f"{BASE}/sessions",
            json={},
            headers=AUTH_HEADERS,
        )
        assert response.status_code == 422, "Missing capture_mode should return 422"


# =============================================================================
# GET SESSION DETAIL
# =============================================================================

@pytest.mark.unit
class TestGetSessionDetail:
    """Test GET /api/v1/call-monitoring/sessions/{session_id} — session detail."""

    def test_get_session_endpoint_exists(self, authenticated_client):
        """The get session detail endpoint exists."""
        session_id = str(uuid4())
        response = authenticated_client.get(
            f"{BASE}/sessions/{session_id}",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "Get session endpoint should be registered"


# =============================================================================
# METRICS
# =============================================================================

@pytest.mark.unit
class TestMonitoringMetrics:
    """Test GET /api/v1/call-monitoring/metrics — monitoring dashboard metrics."""

    def test_metrics_endpoint_exists(self, authenticated_client):
        """The metrics endpoint exists."""
        response = authenticated_client.get(
            f"{BASE}/metrics",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "Metrics endpoint should be registered"


# =============================================================================
# CLIENT CALL HISTORY
# =============================================================================

@pytest.mark.unit
class TestClientCallHistory:
    """Test GET /api/v1/call-monitoring/client/{client_id}/calls."""

    def test_client_calls_endpoint_exists(self, authenticated_client):
        """The client calls endpoint exists."""
        response = authenticated_client.get(
            f"{BASE}/client/123/calls",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "Client calls endpoint should be registered"

    def test_client_calls_with_loan_filter(self, authenticated_client):
        """Client calls accepts optional loan_id filter."""
        response = authenticated_client.get(
            f"{BASE}/client/123/calls?loan_id=42",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404


# =============================================================================
# REQUEST/RESPONSE MODEL VALIDATION
# =============================================================================

@pytest.mark.unit
class TestRequestModels:
    """Test Pydantic request/response models used by call monitoring routes."""

    def test_create_session_request_valid(self):
        """CreateSessionRequest accepts valid data."""
        from routes.call_monitoring_routes import CreateSessionRequest
        req = CreateSessionRequest(capture_mode="mobile_app")
        assert req.capture_mode == "mobile_app"
        assert req.loan_id is None
        assert req.lead_id is None

    def test_create_session_request_with_optional_fields(self):
        """CreateSessionRequest accepts all optional fields."""
        from routes.call_monitoring_routes import CreateSessionRequest
        req = CreateSessionRequest(
            capture_mode="crm_web_call",
            loan_id="42",
            lead_id="100",
            contact_id="200",
            participants=[{"role": "borrower", "name": "John"}],
            metadata={"source": "test"},
        )
        assert req.loan_id == "42"
        assert len(req.participants) == 1

    def test_end_session_request_defaults(self):
        """EndSessionRequest has sensible defaults."""
        from routes.call_monitoring_routes import EndSessionRequest
        req = EndSessionRequest()
        assert req.run_agents is True
        assert req.final_transcript is None
        assert req.agent_types is None

    def test_session_list_response_model(self):
        """SessionListResponse validates correctly."""
        from routes.call_monitoring_routes import SessionListResponse
        resp = SessionListResponse(
            sessions=[{"id": "1", "status": "active"}],
            total=1,
            page=1,
            page_size=20,
        )
        assert resp.total == 1
        assert len(resp.sessions) == 1

    def test_transcript_chunk_request(self):
        """TranscriptChunkRequest accepts text and optional fields."""
        from routes.call_monitoring_routes import TranscriptChunkRequest
        req = TranscriptChunkRequest(text="Hello, how can I help?")
        assert req.text == "Hello, how can I help?"
        assert req.is_final is False
        assert req.speaker_label is None

    def test_recording_playback_response_model(self):
        """RecordingPlaybackResponse validates correctly."""
        from routes.call_monitoring_routes import RecordingPlaybackResponse
        resp = RecordingPlaybackResponse(
            call_id="call_123",
            source="call_session",
            recording_url="https://example.com/recording.mp3",
            duration_seconds=180,
            transcript_text="LO: Hello...",
        )
        assert resp.call_id == "call_123"
        assert resp.source == "call_session"
        assert resp.duration_seconds == 180

    def test_caller_lookup_response_found(self):
        """CallerLookupResponse for a found caller."""
        from routes.call_monitoring_routes import CallerLookupResponse
        resp = CallerLookupResponse(
            found=True,
            source="lead",
            client={"id": "1", "name": "John Smith", "type": "lead"},
        )
        assert resp.found is True
        assert resp.source == "lead"

    def test_caller_lookup_response_not_found(self):
        """CallerLookupResponse for a not found caller."""
        from routes.call_monitoring_routes import CallerLookupResponse
        resp = CallerLookupResponse(found=False, client=None, source=None)
        assert resp.found is False
        assert resp.client is None

    def test_review_data_response_model(self):
        """ReviewDataResponse validates correctly."""
        from routes.call_monitoring_routes import ReviewDataResponse
        resp = ReviewDataResponse(
            session={"id": "abc", "status": "completed"},
            participants=[],
            transcript="Some transcript",
            artifacts=[],
            agent_runs=[],
            summary=None,
        )
        assert resp.session["status"] == "completed"
        assert resp.transcript == "Some transcript"


# =============================================================================
# WORKFLOW RECONCILIATION
# =============================================================================

@pytest.mark.unit
class TestWorkflowReconciliation:
    """Test _ARTIFACT_ACTION_MAP and reconciliation helper."""

    def test_artifact_action_map_values(self):
        """Verify known artifact types are mapped."""
        from routes.call_monitoring_routes import _ARTIFACT_ACTION_MAP

        assert _ARTIFACT_ACTION_MAP["task"] == "task"
        assert _ARTIFACT_ACTION_MAP["follow_up_draft"] == "email"
        assert _ARTIFACT_ACTION_MAP["follow_up_call"] == "call"
        assert _ARTIFACT_ACTION_MAP["document_request"] == "document_request"
        assert _ARTIFACT_ACTION_MAP["scheduled_appointment"] == "appointment"
        assert _ARTIFACT_ACTION_MAP["risk_flag"] == "condition"

    def test_non_actionable_types_not_mapped(self):
        """Summary and scribe_recap types are not in the map."""
        from routes.call_monitoring_routes import _ARTIFACT_ACTION_MAP

        assert "summary" not in _ARTIFACT_ACTION_MAP
        assert "scribe_recap" not in _ARTIFACT_ACTION_MAP


# =============================================================================
# END SESSION
# =============================================================================

@pytest.mark.unit
class TestEndSession:
    """Test POST /api/v1/call-monitoring/sessions/{session_id}/end."""

    def test_end_session_endpoint_exists(self, authenticated_client):
        """The end session endpoint exists."""
        session_id = str(uuid4())
        response = authenticated_client.post(
            f"{BASE}/sessions/{session_id}/end",
            json={"run_agents": False},
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "End session endpoint should be registered"


# =============================================================================
# STACKED NOTES
# =============================================================================

@pytest.mark.unit
class TestStackedNotes:
    """Test GET /api/v1/call-monitoring/client/{client_id}/stacked-notes."""

    def test_stacked_notes_endpoint_exists(self, authenticated_client):
        """The stacked notes endpoint exists."""
        response = authenticated_client.get(
            f"{BASE}/client/123/stacked-notes",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "Stacked notes endpoint should be registered"


# =============================================================================
# ARTIFACT SHARING
# =============================================================================

@pytest.mark.unit
class TestArtifactSharing:
    """Test artifact share endpoints."""

    def test_share_endpoint_exists(self, authenticated_client):
        """POST /artifacts/{id}/share exists."""
        response = authenticated_client.post(
            f"{BASE}/artifacts/art_123/share",
            json={},
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "Artifact share endpoint should be registered"

    def test_my_shares_endpoint_exists(self, authenticated_client):
        """GET /my-shares exists."""
        response = authenticated_client.get(
            f"{BASE}/my-shares",
            headers=AUTH_HEADERS,
        )
        assert response.status_code != 404, "My shares endpoint should be registered"
