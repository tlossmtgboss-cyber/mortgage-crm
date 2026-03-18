"""
Scheduler Reschedule Route Tests

Tests for the reschedule route handlers in routes/scheduler/reschedule.py.
Covers:
  - POST /reschedule/{appointment_id}             LO-initiated reschedule (auth required)
  - GET  /reschedule/history/{appointment_id}      Reschedule history (auth required)
  - POST /reschedule/{appointment_id}/link         Generate self-service link (auth required)
  - GET  /public/reschedule/{token}/slots          Public slot retrieval
  - POST /public/reschedule/{token}/confirm        Public reschedule confirmation
  - Expired token handling
  - 404 for non-existent appointment
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta, timezone
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


class MockAppointment:
    """Mock appointment object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 100)
        self.organization_id = kwargs.get("organization_id", 1)
        self.scheduled_start = kwargs.get("scheduled_start", datetime(2026, 3, 25, 14, 0))
        self.scheduled_end = kwargs.get("scheduled_end", datetime(2026, 3, 25, 14, 30))
        self.duration_minutes = kwargs.get("duration_minutes", 30)
        self.attendee_name = kwargs.get("attendee_name", "John Doe")
        self.title = kwargs.get("title", "Mortgage Consultation")
        self.status = kwargs.get("status", "booked")


@pytest.fixture
def auth_user():
    return MockUser()


@pytest.fixture
def mock_appt():
    return MockAppointment()


# Shared patch targets
_RESCHEDULE = "routes.scheduler.reschedule"
_HELPERS = "routes.scheduler._helpers"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


# =============================================================================
# POST /reschedule/{appointment_id} — LO-initiated reschedule
# =============================================================================

class TestInitiateReschedule:
    """POST /api/v1/scheduler/reschedule/{appointment_id}."""

    @patch(f"{_RESCHEDULE}.scheduler_audit")
    @patch(f"{_RESCHEDULE}._audit_log")
    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_RESCHEDULE}.require_feature_tier", lambda m: lambda fn: fn)
    def test_initiate_reschedule_success(self, mock_auth, mock_svc_factory, mock_audit, mock_sched_audit, auth_user):
        mock_auth.return_value = auth_user
        mock_service = MagicMock()
        mock_service.initiate_reschedule.return_value = {
            "appointment_id": 100,
            "reschedule_count": 1,
            "message": "Reschedule initiated",
        }
        mock_svc_factory.return_value = mock_service

        # Mock the appointment query for audit logging
        mock_models = {"Appointment": MagicMock()}
        with patch(f"{_RESCHEDULE}.get_models", return_value=mock_models):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/reschedule/100",
                json={"reason": "Client requested different time"},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["reschedule_count"] == 1

    @patch(f"{_RESCHEDULE}._audit_log")
    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_RESCHEDULE}.require_feature_tier", lambda m: lambda fn: fn)
    def test_initiate_reschedule_not_found(self, mock_auth, mock_svc_factory, mock_audit, auth_user):
        mock_auth.return_value = auth_user
        mock_service = MagicMock()
        mock_service.initiate_reschedule.side_effect = ValueError("Appointment not found")
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reschedule/999",
            json={},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()

    @patch(f"{_RESCHEDULE}.scheduler_audit")
    @patch(f"{_RESCHEDULE}._audit_log")
    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_RESCHEDULE}.require_feature_tier", lambda m: lambda fn: fn)
    def test_initiate_reschedule_no_reason(self, mock_auth, mock_svc_factory, mock_audit, mock_sched_audit, auth_user):
        """Reason is optional; reschedule should succeed without it."""
        mock_auth.return_value = auth_user
        mock_service = MagicMock()
        mock_service.initiate_reschedule.return_value = {
            "appointment_id": 100,
            "reschedule_count": 1,
        }
        mock_svc_factory.return_value = mock_service

        with patch(f"{_RESCHEDULE}.get_models", return_value={"Appointment": MagicMock()}):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/reschedule/100",
                json={},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200

    def test_initiate_reschedule_no_auth(self):
        """Unauthenticated request should be rejected."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reschedule/100",
            json={},
        )
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# GET /reschedule/history/{appointment_id} — reschedule history
# =============================================================================

class TestRescheduleHistory:
    """GET /api/v1/scheduler/reschedule/history/{appointment_id}."""

    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}.get_current_user", new_callable=AsyncMock)
    def test_get_history_success(self, mock_auth, mock_svc_factory, auth_user):
        mock_auth.return_value = auth_user
        mock_service = MagicMock()
        mock_service.get_reschedule_history.return_value = [
            {
                "id": 1,
                "old_start": "2026-03-20T14:00:00",
                "new_start": "2026-03-22T10:00:00",
                "reason": "Scheduling conflict",
                "requested_by": "lo",
                "created_at": "2026-03-19T09:00:00",
            },
        ]
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/reschedule/history/100",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["appointment_id"] == 100
        assert data["count"] == 1
        assert len(data["history"]) == 1

    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}.get_current_user", new_callable=AsyncMock)
    def test_get_history_not_found(self, mock_auth, mock_svc_factory, auth_user):
        mock_auth.return_value = auth_user
        mock_service = MagicMock()
        mock_service.get_reschedule_history.side_effect = ValueError("Appointment not found")
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/reschedule/history/999",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 404


# =============================================================================
# POST /reschedule/{appointment_id}/link — generate self-service link
# =============================================================================

class TestGenerateRescheduleLink:
    """POST /api/v1/scheduler/reschedule/{appointment_id}/link."""

    @patch(f"{_RESCHEDULE}.scheduler_audit")
    @patch(f"{_RESCHEDULE}._audit_log")
    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}.get_current_user", new_callable=AsyncMock)
    def test_generate_link_success(self, mock_auth, mock_svc_factory, mock_audit, mock_sched_audit, auth_user):
        mock_auth.return_value = auth_user
        mock_service = MagicMock()
        mock_service.generate_reschedule_link.return_value = {
            "reschedule_url": "https://app.perenniaai.com/reschedule/abc123",
            "token": "abc123",
            "expires_at": "2026-03-20T12:00:00",
        }
        mock_svc_factory.return_value = mock_service

        with patch(f"{_RESCHEDULE}.get_models", return_value={"Appointment": MagicMock()}):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/reschedule/100/link",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "reschedule_url" in data

    @patch(f"{_RESCHEDULE}._audit_log")
    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}.get_current_user", new_callable=AsyncMock)
    def test_generate_link_appointment_not_found(self, mock_auth, mock_svc_factory, mock_audit, auth_user):
        mock_auth.return_value = auth_user
        mock_service = MagicMock()
        mock_service.generate_reschedule_link.side_effect = ValueError("Appointment not found")
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reschedule/999/link",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400

    @patch(f"{_RESCHEDULE}._audit_log")
    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}.get_current_user", new_callable=AsyncMock)
    def test_generate_link_server_error(self, mock_auth, mock_svc_factory, mock_audit, auth_user):
        mock_auth.return_value = auth_user
        mock_service = MagicMock()
        mock_service.generate_reschedule_link.side_effect = RuntimeError("SECRET_KEY not configured")
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/reschedule/100/link",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 500


# =============================================================================
# GET /public/reschedule/{token}/slots — public slot retrieval
# =============================================================================

class TestPublicRescheduleSlots:
    """GET /api/v1/scheduler/public/reschedule/{token}/slots."""

    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}._check_rate_limit", new_callable=AsyncMock)
    def test_get_slots_success(self, mock_rl, mock_svc_factory, mock_appt):
        mock_service = MagicMock()
        mock_service.verify_reschedule_token.return_value = {
            "appt_id": 100,
            "org_id": 1,
        }
        mock_service._get_appointment.return_value = mock_appt
        mock_service.get_available_slots.return_value = [
            {"start": "2026-03-26T10:00:00", "end": "2026-03-26T10:30:00"},
            {"start": "2026-03-26T14:00:00", "end": "2026-03-26T14:30:00"},
        ]
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/public/reschedule/valid.jwt.token/slots",
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["appointment_id"] == 100
        assert data["slots_count"] == 2
        assert len(data["slots"]) == 2
        assert data["attendee_name"] == "John Doe"
        assert data["duration_minutes"] == 30

    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}._check_rate_limit", new_callable=AsyncMock)
    def test_get_slots_expired_token(self, mock_rl, mock_svc_factory):
        mock_service = MagicMock()
        mock_service.verify_reschedule_token.side_effect = ValueError("Token expired")
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/public/reschedule/expired.jwt.token/slots",
        )

        assert resp.status_code == 401

    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}._check_rate_limit", new_callable=AsyncMock)
    def test_get_slots_appointment_not_found(self, mock_rl, mock_svc_factory):
        mock_service = MagicMock()
        mock_service.verify_reschedule_token.return_value = {
            "appt_id": 999,
            "org_id": 1,
        }
        mock_service._get_appointment.side_effect = ValueError("Appointment not found")
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/public/reschedule/valid.jwt.token/slots",
        )

        assert resp.status_code == 404

    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}._check_rate_limit", new_callable=AsyncMock)
    def test_get_slots_with_target_date(self, mock_rl, mock_svc_factory, mock_appt):
        mock_service = MagicMock()
        mock_service.verify_reschedule_token.return_value = {"appt_id": 100, "org_id": 1}
        mock_service._get_appointment.return_value = mock_appt
        mock_service.get_available_slots.return_value = []
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/public/reschedule/valid.jwt.token/slots?target_date=2026-04-01",
        )

        assert resp.status_code == 200
        # Verify service was called with parsed date
        mock_service.get_available_slots.assert_called_once()

    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}._check_rate_limit", new_callable=AsyncMock)
    def test_get_slots_invalid_target_date(self, mock_rl, mock_svc_factory):
        mock_service = MagicMock()
        mock_service.verify_reschedule_token.return_value = {"appt_id": 100, "org_id": 1}
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/public/reschedule/valid.jwt.token/slots?target_date=not-a-date",
        )

        assert resp.status_code == 400


# =============================================================================
# POST /public/reschedule/{token}/confirm — public reschedule confirmation
# =============================================================================

class TestPublicRescheduleConfirm:
    """POST /api/v1/scheduler/public/reschedule/{token}/confirm."""

    @patch(f"{_RESCHEDULE}.scheduler_audit")
    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}._check_rate_limit", new_callable=AsyncMock)
    def test_confirm_reschedule_success(self, mock_rl, mock_svc_factory, mock_sched_audit, mock_appt):
        mock_service = MagicMock()
        mock_service.verify_reschedule_token.return_value = {"appt_id": 100, "org_id": 1}
        mock_service._get_appointment.return_value = mock_appt
        mock_service.confirm_reschedule.return_value = {
            "appointment_id": 100,
            "new_start": "2026-03-26T10:00:00",
            "new_end": "2026-03-26T10:30:00",
        }
        mock_svc_factory.return_value = mock_service

        # Patch the models query for audit logging
        with patch(f"{_RESCHEDULE}.get_models", return_value={"Appointment": MagicMock()}):
            client = _get_client()
            future_start = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
            future_end = future_start + timedelta(minutes=30)
            resp = client.post(
                "/api/v1/scheduler/public/reschedule/valid.jwt.token/confirm",
                json={
                    "new_start": future_start.isoformat(),
                    "new_end": future_end.isoformat(),
                    "reason": "Need a later time",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["message"] == "Appointment rescheduled successfully"

    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}._check_rate_limit", new_callable=AsyncMock)
    def test_confirm_reschedule_expired_token(self, mock_rl, mock_svc_factory):
        mock_service = MagicMock()
        mock_service.verify_reschedule_token.side_effect = ValueError("Token expired")
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        future_start = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
        future_end = future_start + timedelta(minutes=30)
        resp = client.post(
            "/api/v1/scheduler/public/reschedule/expired.jwt.token/confirm",
            json={
                "new_start": future_start.isoformat(),
                "new_end": future_end.isoformat(),
            },
        )

        assert resp.status_code == 401

    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}._check_rate_limit", new_callable=AsyncMock)
    def test_confirm_reschedule_end_before_start(self, mock_rl, mock_svc_factory):
        mock_service = MagicMock()
        mock_service.verify_reschedule_token.return_value = {"appt_id": 100, "org_id": 1}
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        future = datetime.now(timezone.utc) + timedelta(days=3)
        resp = client.post(
            "/api/v1/scheduler/public/reschedule/valid.jwt.token/confirm",
            json={
                "new_start": future.isoformat(),
                "new_end": (future - timedelta(hours=1)).isoformat(),
            },
        )

        assert resp.status_code == 400

    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}._check_rate_limit", new_callable=AsyncMock)
    def test_confirm_reschedule_past_time(self, mock_rl, mock_svc_factory):
        mock_service = MagicMock()
        mock_service.verify_reschedule_token.return_value = {"appt_id": 100, "org_id": 1}
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        past = datetime.now(timezone.utc) - timedelta(days=1)
        resp = client.post(
            "/api/v1/scheduler/public/reschedule/valid.jwt.token/confirm",
            json={
                "new_start": past.isoformat(),
                "new_end": (past + timedelta(minutes=30)).isoformat(),
            },
        )

        assert resp.status_code == 400

    @patch(f"{_RESCHEDULE}._get_reschedule_service")
    @patch(f"{_RESCHEDULE}._check_rate_limit", new_callable=AsyncMock)
    def test_confirm_reschedule_invalid_datetime(self, mock_rl, mock_svc_factory):
        mock_service = MagicMock()
        mock_service.verify_reschedule_token.return_value = {"appt_id": 100, "org_id": 1}
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/public/reschedule/valid.jwt.token/confirm",
            json={
                "new_start": "not-a-date",
                "new_end": "also-not-a-date",
            },
        )

        assert resp.status_code == 400

    def test_confirm_reschedule_missing_fields(self):
        """Missing new_start/new_end should fail Pydantic validation (422)."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/public/reschedule/valid.jwt.token/confirm",
            json={"reason": "just a reason"},
        )

        assert resp.status_code == 422
