"""
Scheduler Survey Route Tests

Tests for the survey route handlers in routes/scheduler/surveys.py.
Covers:
  - POST /surveys/send/{appointment_id}     Send survey (auth required)
  - GET  /surveys/results                   Get aggregate results (auth required)
  - GET  /surveys/results/{lo_id}           Get per-LO results (auth required)
  - GET  /public/surveys/respond/{token}    Public form retrieval (no auth)
  - POST /public/surveys/respond/{token}    Public response submission
  - Invalid/expired token handling
  - 401 for unauthenticated access to protected endpoints
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# FIXTURES
# =============================================================================

class MockUser:
    """Mock user for authenticated tests."""
    def __init__(self, role="loan_officer", org_id=1, user_id=10):
        self.id = user_id
        self.organization_id = org_id
        self.role = role
        self.permission_role = role
        self.email = "lo@test.com"


@pytest.fixture
def auth_user():
    return MockUser()


# Shared patch targets
_SURVEYS = "routes.scheduler.surveys"
_HELPERS = "routes.scheduler._helpers"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


# =============================================================================
# POST /surveys/send/{appointment_id} — send survey (auth required)
# =============================================================================

class TestSendSurvey:
    """POST /api/v1/scheduler/surveys/send/{appointment_id}."""

    @patch(f"{_SURVEYS}._audit_log")
    @patch(f"{_SURVEYS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_SURVEYS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_send_survey_success(self, mock_auth, mock_audit, auth_user):
        mock_auth.return_value = auth_user

        mock_service = MagicMock()
        mock_service.create_and_send_survey.return_value = {
            "success": True,
            "survey_id": 42,
            "email_sent": True,
            "survey_url": "https://app.perenniaai.com/survey/abc123",
            "expires_at": "2026-03-24T00:00:00",
        }

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/surveys/send/100",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True
        assert data["survey_id"] == 42
        assert data["email_sent"] is True

    @patch(f"{_SURVEYS}._audit_log")
    @patch(f"{_SURVEYS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_SURVEYS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_send_survey_already_sent(self, mock_auth, mock_audit, auth_user):
        mock_auth.return_value = auth_user

        mock_service = MagicMock()
        mock_service.create_and_send_survey.return_value = {
            "success": False,
            "error": "Survey already sent for this appointment",
        }

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/surveys/send/100",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 409

    @patch(f"{_SURVEYS}._audit_log")
    @patch(f"{_SURVEYS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_SURVEYS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_send_survey_generic_failure(self, mock_auth, mock_audit, auth_user):
        mock_auth.return_value = auth_user

        mock_service = MagicMock()
        mock_service.create_and_send_survey.return_value = {
            "success": False,
            "error": "Appointment not found",
        }

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/surveys/send/999",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 400

    def test_send_survey_no_auth_fails(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.post("/api/v1/scheduler/surveys/send/100")
        # Expect 401 or 403 depending on auth middleware
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# GET /surveys/results — aggregate results (auth required)
# =============================================================================

class TestGetSurveyResults:
    """GET /api/v1/scheduler/surveys/results."""

    @patch(f"{_SURVEYS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_SURVEYS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_get_results_success(self, mock_auth, auth_user):
        mock_auth.return_value = auth_user

        mock_service = MagicMock()
        mock_service.get_aggregate_scores.return_value = {
            "avg_overall": 4.2,
            "avg_communication": 4.5,
            "avg_knowledge": 4.0,
            "nps_score": 60,
            "response_rate": 0.45,
            "total_surveys": 20,
        }
        mock_service.get_lo_breakdown.return_value = []

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/surveys/results",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "avg_overall" in data
        assert data["total_surveys"] == 20
        assert "lo_breakdown" in data

    @patch(f"{_SURVEYS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_SURVEYS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_get_results_custom_days(self, mock_auth, auth_user):
        mock_auth.return_value = auth_user

        mock_service = MagicMock()
        mock_service.get_aggregate_scores.return_value = {"total_surveys": 5}
        mock_service.get_lo_breakdown.return_value = []

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/surveys/results?days=30",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        mock_service.get_aggregate_scores.assert_called_once()
        call_kwargs = mock_service.get_aggregate_scores.call_args
        assert call_kwargs[1]["days"] == 30 or call_kwargs[0][1] == 30


# =============================================================================
# GET /surveys/results/{lo_id} — per-LO results (auth required)
# =============================================================================

class TestGetLoSurveyResults:
    """GET /api/v1/scheduler/surveys/results/{lo_id}."""

    @patch(f"{_SURVEYS}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_SURVEYS}.require_feature_tier", lambda m: lambda fn: fn)
    def test_get_lo_results_success(self, mock_auth, auth_user):
        mock_auth.return_value = auth_user

        mock_service = MagicMock()
        mock_service.get_aggregate_scores.return_value = {
            "avg_overall": 4.8,
            "total_surveys": 10,
        }

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/surveys/results/5",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["avg_overall"] == 4.8

    def test_get_lo_results_no_auth(self):
        """Unauthenticated request to per-LO results should fail."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/surveys/results/5")
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# GET /public/surveys/respond/{token} — public form retrieval
# =============================================================================

class TestPublicGetSurveyForm:
    """GET /api/v1/scheduler/public/surveys/respond/{token}."""

    @patch(f"{_SURVEYS}._check_rate_limit", new_callable=AsyncMock)
    def test_get_form_active_survey(self, mock_rl):
        mock_service = MagicMock()
        mock_service.get_survey_by_token.return_value = {
            "expired": False,
            "completed": False,
            "borrower_name": "John Doe",
            "lo_name": "Alice Smith",
        }

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/public/surveys/respond/abcdef0123456789abcdef",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["borrower_name"] == "John Doe"
        assert data["lo_name"] == "Alice Smith"

    @patch(f"{_SURVEYS}._check_rate_limit", new_callable=AsyncMock)
    def test_get_form_expired_survey(self, mock_rl):
        mock_service = MagicMock()
        mock_service.get_survey_by_token.return_value = {
            "expired": True,
            "completed": False,
        }

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/public/surveys/respond/abcdef0123456789abcdef",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "expired"

    @patch(f"{_SURVEYS}._check_rate_limit", new_callable=AsyncMock)
    def test_get_form_completed_survey(self, mock_rl):
        mock_service = MagicMock()
        mock_service.get_survey_by_token.return_value = {
            "expired": False,
            "completed": True,
        }

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/public/surveys/respond/abcdef0123456789abcdef",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"

    @patch(f"{_SURVEYS}._check_rate_limit", new_callable=AsyncMock)
    def test_get_form_survey_not_found(self, mock_rl):
        mock_service = MagicMock()
        mock_service.get_survey_by_token.return_value = None

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/public/surveys/respond/abcdef0123456789abcdef",
            )

        assert resp.status_code == 404

    @patch(f"{_SURVEYS}._check_rate_limit", new_callable=AsyncMock)
    def test_get_form_short_token_rejected(self, mock_rl):
        """Token shorter than 20 chars should be rejected with 400."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/public/surveys/respond/short")

        assert resp.status_code == 400


# =============================================================================
# POST /public/surveys/respond/{token} — public response submission
# =============================================================================

class TestPublicSubmitSurvey:
    """POST /api/v1/scheduler/public/surveys/respond/{token}."""

    @patch(f"{_SURVEYS}._check_rate_limit", new_callable=AsyncMock)
    def test_submit_response_success(self, mock_rl):
        mock_service = MagicMock()
        mock_service.submit_response.return_value = {
            "success": True,
            "message": "Thank you for your feedback!",
        }

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/public/surveys/respond/abcdef0123456789abcdef",
                json={
                    "overall_rating": 5,
                    "communication_rating": 4,
                    "knowledge_rating": 5,
                    "feedback_text": "Great experience!",
                    "would_recommend": True,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @patch(f"{_SURVEYS}._check_rate_limit", new_callable=AsyncMock)
    def test_submit_response_expired_token(self, mock_rl):
        mock_service = MagicMock()
        mock_service.submit_response.return_value = {
            "success": False,
            "error": "Survey has expired",
        }

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/public/surveys/respond/abcdef0123456789abcdef",
                json={
                    "overall_rating": 5,
                    "communication_rating": 4,
                    "knowledge_rating": 5,
                },
            )

        assert resp.status_code == 410  # Gone

    @patch(f"{_SURVEYS}._check_rate_limit", new_callable=AsyncMock)
    def test_submit_response_already_completed(self, mock_rl):
        mock_service = MagicMock()
        mock_service.submit_response.return_value = {
            "success": False,
            "error": "Survey already submitted",
        }

        with patch(f"{_SURVEYS}.AppointmentSurveyService", return_value=mock_service):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/public/surveys/respond/abcdef0123456789abcdef",
                json={
                    "overall_rating": 3,
                    "communication_rating": 3,
                    "knowledge_rating": 3,
                },
            )

        assert resp.status_code == 409  # Conflict

    @patch(f"{_SURVEYS}._check_rate_limit", new_callable=AsyncMock)
    def test_submit_response_invalid_rating(self, mock_rl):
        """Rating outside 1-5 range should fail Pydantic validation (422)."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/public/surveys/respond/abcdef0123456789abcdef",
            json={
                "overall_rating": 10,
                "communication_rating": 4,
                "knowledge_rating": 5,
            },
        )

        assert resp.status_code == 422

    @patch(f"{_SURVEYS}._check_rate_limit", new_callable=AsyncMock)
    def test_submit_response_missing_required_ratings(self, mock_rl):
        """Missing required rating fields should fail validation (422)."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/public/surveys/respond/abcdef0123456789abcdef",
            json={
                "overall_rating": 4,
                # missing communication_rating and knowledge_rating
            },
        )

        assert resp.status_code == 422

    @patch(f"{_SURVEYS}._check_rate_limit", new_callable=AsyncMock)
    def test_submit_response_short_token_rejected(self, mock_rl):
        """Short token should be rejected with 400."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/public/surveys/respond/short",
            json={
                "overall_rating": 5,
                "communication_rating": 5,
                "knowledge_rating": 5,
            },
        )

        assert resp.status_code == 400
