"""
Scheduler Waitlist Route Tests

Tests for the waitlist route handlers in routes/scheduler/waitlist.py.
Covers:
  - GET  /waitlist                  List waitlist entries (admin only)
  - POST /waitlist/{entry_id}/offer Offer a slot (admin only, 403 for non-admin)
  - POST /waitlist/{entry_id}/reorder  Reorder (admin only)
  - POST /public/waitlist/join      Public join (no auth, rate limited)
  - POST /public/waitlist/accept    Public accept (token-based)
  - GET  /public/waitlist/position  Public position check (token-based)
  - 404 for non-existent entries
  - Input validation (missing required fields)
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
    def __init__(self, role="admin", org_id=1, user_id=10):
        self.id = user_id
        self.organization_id = org_id
        self.role = role
        self.permission_role = role
        self.email = "admin@test.com"


class MockWaitlistEntry:
    """Mock WaitlistEntry returned by WaitlistService."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.position = kwargs.get("position", 1)
        self.name = kwargs.get("name", "John Doe")
        self.email = kwargs.get("email", "john@example.com")
        self.phone = kwargs.get("phone", "555-0100")
        self.status = kwargs.get("status", "waiting")
        self.offered_at = kwargs.get("offered_at", None)
        self.offered_slot_time = kwargs.get("offered_slot_time", None)
        self.expires_at = kwargs.get("expires_at", None)
        self.appointment_id = kwargs.get("appointment_id", None)
        self.organization_id = kwargs.get("organization_id", 1)
        self.appointment_type_id = kwargs.get("appointment_type_id", 1)


@pytest.fixture
def admin_user():
    return MockUser(role="admin")


@pytest.fixture
def lo_user():
    return MockUser(role="loan_officer")


@pytest.fixture
def mock_entry():
    return MockWaitlistEntry()


@pytest.fixture
def entry_dict():
    """Dict representation returned by _entry_to_dict."""
    return {
        "id": 1,
        "position": 1,
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "555-0100",
        "status": "waiting",
        "offered_at": None,
        "offered_slot_time": None,
        "expires_at": None,
        "appointment_id": None,
    }


# Shared patch targets (routes/scheduler/waitlist module)
_WAITLIST = "routes.scheduler.waitlist"
_HELPERS = "routes.scheduler._helpers"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


# =============================================================================
# GET /waitlist — list entries (admin only)
# =============================================================================

class TestGetWaitlist:
    """GET /api/v1/scheduler/waitlist."""

    @patch(f"{_WAITLIST}._get_waitlist_service")
    @patch(f"{_WAITLIST}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_WAITLIST}.require_feature_tier", lambda m: lambda fn: fn)
    def test_get_waitlist_success(self, mock_auth, mock_svc_factory, admin_user):
        mock_auth.return_value = admin_user
        mock_service = MagicMock()
        mock_service.get_waitlist.return_value = {
            "entries": [],
            "total": 0,
        }
        mock_svc_factory.return_value = mock_service

        with patch(f"{_HELPERS}._is_scheduler_admin", return_value=True):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/waitlist",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert data["total"] == 0

    @patch(f"{_WAITLIST}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_WAITLIST}.require_feature_tier", lambda m: lambda fn: fn)
    def test_get_waitlist_non_admin_forbidden(self, mock_auth, lo_user):
        mock_auth.return_value = lo_user

        with patch(f"{_HELPERS}._is_scheduler_admin", return_value=False):
            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/waitlist",
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 403


# =============================================================================
# POST /waitlist/{entry_id}/offer — offer slot (admin only)
# =============================================================================

class TestOfferSlot:
    """POST /api/v1/scheduler/waitlist/{entry_id}/offer."""

    @patch(f"{_WAITLIST}._audit_log")
    @patch(f"{_WAITLIST}._get_waitlist_service")
    @patch(f"{_WAITLIST}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_WAITLIST}.require_feature_tier", lambda m: lambda fn: fn)
    def test_offer_slot_success(self, mock_auth, mock_svc_factory, mock_audit, admin_user, mock_entry, entry_dict):
        mock_auth.return_value = admin_user
        mock_service = MagicMock()
        mock_service.offer_slot.return_value = mock_entry
        mock_service._entry_to_dict.return_value = entry_dict
        mock_svc_factory.return_value = mock_service

        with patch(f"{_HELPERS}._is_scheduler_admin", return_value=True):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/waitlist/1/offer",
                json={"slot_time": "2026-03-20T14:00:00+00:00"},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @patch(f"{_WAITLIST}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_WAITLIST}.require_feature_tier", lambda m: lambda fn: fn)
    def test_offer_slot_non_admin_forbidden(self, mock_auth, lo_user):
        mock_auth.return_value = lo_user

        with patch(f"{_HELPERS}._is_scheduler_admin", return_value=False):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/waitlist/1/offer",
                json={"slot_time": "2026-03-20T14:00:00+00:00"},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 403

    @patch(f"{_WAITLIST}._audit_log")
    @patch(f"{_WAITLIST}._get_waitlist_service")
    @patch(f"{_WAITLIST}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_WAITLIST}.require_feature_tier", lambda m: lambda fn: fn)
    def test_offer_slot_invalid_time_format(self, mock_auth, mock_svc_factory, mock_audit, admin_user):
        mock_auth.return_value = admin_user
        mock_svc_factory.return_value = MagicMock()

        with patch(f"{_HELPERS}._is_scheduler_admin", return_value=True):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/waitlist/1/offer",
                json={"slot_time": "not-a-date"},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 400

    @patch(f"{_WAITLIST}._audit_log")
    @patch(f"{_WAITLIST}._get_waitlist_service")
    @patch(f"{_WAITLIST}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_WAITLIST}.require_feature_tier", lambda m: lambda fn: fn)
    def test_offer_slot_entry_not_found(self, mock_auth, mock_svc_factory, mock_audit, admin_user):
        mock_auth.return_value = admin_user
        mock_service = MagicMock()
        mock_service.offer_slot.side_effect = ValueError("Entry not found")
        mock_svc_factory.return_value = mock_service

        with patch(f"{_HELPERS}._is_scheduler_admin", return_value=True):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/waitlist/999/offer",
                json={"slot_time": "2026-03-20T14:00:00+00:00"},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"].lower()


# =============================================================================
# POST /waitlist/{entry_id}/reorder — reorder (admin only)
# =============================================================================

class TestReorderWaitlist:
    """POST /api/v1/scheduler/waitlist/{entry_id}/reorder."""

    @patch(f"{_WAITLIST}._get_waitlist_service")
    @patch(f"{_WAITLIST}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_WAITLIST}.require_feature_tier", lambda m: lambda fn: fn)
    def test_reorder_success(self, mock_auth, mock_svc_factory, admin_user, mock_entry, entry_dict):
        mock_auth.return_value = admin_user
        mock_service = MagicMock()
        mock_service.reorder_entry.return_value = mock_entry
        mock_service._entry_to_dict.return_value = entry_dict
        mock_svc_factory.return_value = mock_service

        with patch(f"{_HELPERS}._is_scheduler_admin", return_value=True):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/waitlist/1/reorder",
                json={"new_position": 3},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @patch(f"{_WAITLIST}.get_current_user", new_callable=AsyncMock)
    @patch(f"{_WAITLIST}.require_feature_tier", lambda m: lambda fn: fn)
    def test_reorder_non_admin_forbidden(self, mock_auth, lo_user):
        mock_auth.return_value = lo_user

        with patch(f"{_HELPERS}._is_scheduler_admin", return_value=False):
            client = _get_client()
            resp = client.post(
                "/api/v1/scheduler/waitlist/1/reorder",
                json={"new_position": 2},
                headers={"Authorization": "Bearer test"},
            )

        assert resp.status_code == 403

    def test_reorder_invalid_position_zero(self):
        """new_position must be >= 1 per the Pydantic model."""
        client = _get_client()
        # Pydantic validation should reject position=0 with 422
        resp = client.post(
            "/api/v1/scheduler/waitlist/1/reorder",
            json={"new_position": 0},
            headers={"Authorization": "Bearer test"},
        )
        assert resp.status_code == 422


# =============================================================================
# POST /public/waitlist/join — public join (no auth)
# =============================================================================

class TestPublicJoinWaitlist:
    """POST /api/v1/scheduler/public/waitlist/join."""

    @patch(f"{_WAITLIST}._generate_waitlist_token", return_value="signed.jwt.token")
    @patch(f"{_WAITLIST}._resolve_org_from_appointment_type", return_value=1)
    @patch(f"{_WAITLIST}._get_waitlist_service")
    @patch(f"{_WAITLIST}._check_rate_limit", new_callable=AsyncMock)
    def test_public_join_success(self, mock_rl, mock_svc_factory, mock_resolve, mock_token):
        mock_service = MagicMock()
        entry = MockWaitlistEntry(id=5, position=3)
        mock_service.join_waitlist.return_value = entry
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/public/waitlist/join",
            json={
                "appointment_type_id": 1,
                "name": "Jane Smith",
                "email": "jane@example.com",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["token"] == "signed.jwt.token"
        assert data["position"] == 3

    @patch(f"{_WAITLIST}._check_rate_limit", new_callable=AsyncMock)
    def test_public_join_missing_name(self, mock_rl):
        """Missing required field 'name' should return 422."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/public/waitlist/join",
            json={
                "appointment_type_id": 1,
                "email": "jane@example.com",
            },
        )
        assert resp.status_code == 422

    @patch(f"{_WAITLIST}._check_rate_limit", new_callable=AsyncMock)
    def test_public_join_missing_email(self, mock_rl):
        """Missing required field 'email' should return 422."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/public/waitlist/join",
            json={
                "appointment_type_id": 1,
                "name": "Jane Smith",
            },
        )
        assert resp.status_code == 422

    @patch(f"{_WAITLIST}._resolve_org_from_appointment_type")
    @patch(f"{_WAITLIST}._check_rate_limit", new_callable=AsyncMock)
    def test_public_join_invalid_appointment_type(self, mock_rl, mock_resolve):
        """Should return 404 when appointment type doesn't exist."""
        from fastapi import HTTPException
        mock_resolve.side_effect = HTTPException(status_code=404, detail="Appointment type not found")

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/public/waitlist/join",
            json={
                "appointment_type_id": 999,
                "name": "Jane Smith",
                "email": "jane@example.com",
            },
        )
        assert resp.status_code == 404


# =============================================================================
# POST /public/waitlist/accept — public accept (token-based)
# =============================================================================

class TestPublicAcceptOffer:
    """POST /api/v1/scheduler/public/waitlist/accept?token=..."""

    @patch(f"{_WAITLIST}._get_waitlist_service")
    @patch(f"{_WAITLIST}._verify_waitlist_token")
    @patch(f"{_WAITLIST}._check_rate_limit", new_callable=AsyncMock)
    def test_public_accept_success(self, mock_rl, mock_verify, mock_svc_factory):
        mock_verify.return_value = {"entry_id": 1, "email": "john@example.com"}

        mock_service = MagicMock()
        mock_service.accept_offer.return_value = {
            "appointment": {"id": 100, "scheduled_start": "2026-03-20T14:00:00"},
            "waitlist_entry": {"id": 1, "status": "accepted"},
        }
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/public/waitlist/accept?token=valid.jwt.token",
            json={"email": "john@example.com"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "appointment" in data

    @patch(f"{_WAITLIST}._verify_waitlist_token")
    @patch(f"{_WAITLIST}._check_rate_limit", new_callable=AsyncMock)
    def test_public_accept_email_mismatch(self, mock_rl, mock_verify):
        mock_verify.return_value = {"entry_id": 1, "email": "john@example.com"}

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/public/waitlist/accept?token=valid.jwt.token",
            json={"email": "wrong@example.com"},
        )

        assert resp.status_code == 403

    @patch(f"{_WAITLIST}._verify_waitlist_token")
    @patch(f"{_WAITLIST}._check_rate_limit", new_callable=AsyncMock)
    def test_public_accept_expired_token(self, mock_rl, mock_verify):
        from fastapi import HTTPException
        mock_verify.side_effect = HTTPException(status_code=401, detail="Waitlist link has expired")

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/public/waitlist/accept?token=expired.jwt.token",
            json={"email": "john@example.com"},
        )

        assert resp.status_code == 401


# =============================================================================
# GET /public/waitlist/position — public position check (token-based)
# =============================================================================

class TestPublicCheckPosition:
    """GET /api/v1/scheduler/public/waitlist/position?token=..."""

    @patch(f"{_WAITLIST}._get_waitlist_service")
    @patch(f"{_WAITLIST}._verify_waitlist_token")
    @patch(f"{_WAITLIST}._check_rate_limit", new_callable=AsyncMock)
    def test_public_position_success(self, mock_rl, mock_verify, mock_svc_factory):
        mock_verify.return_value = {"entry_id": 1, "email": "john@example.com"}

        mock_service = MagicMock()
        mock_service.get_position.return_value = {
            "position": 2,
            "total_waiting": 5,
            "status": "waiting",
        }
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/public/waitlist/position?token=valid.jwt.token",
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["position"] == 2
        assert data["total_waiting"] == 5
        assert data["status"] == "waiting"

    @patch(f"{_WAITLIST}._get_waitlist_service")
    @patch(f"{_WAITLIST}._verify_waitlist_token")
    @patch(f"{_WAITLIST}._check_rate_limit", new_callable=AsyncMock)
    def test_public_position_entry_not_found(self, mock_rl, mock_verify, mock_svc_factory):
        mock_verify.return_value = {"entry_id": 999, "email": "gone@example.com"}

        mock_service = MagicMock()
        mock_service.get_position.side_effect = ValueError("Entry not found")
        mock_svc_factory.return_value = mock_service

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/public/waitlist/position?token=valid.jwt.token",
        )

        assert resp.status_code == 404

    @patch(f"{_WAITLIST}._verify_waitlist_token")
    @patch(f"{_WAITLIST}._check_rate_limit", new_callable=AsyncMock)
    def test_public_position_invalid_token(self, mock_rl, mock_verify):
        from fastapi import HTTPException
        mock_verify.side_effect = HTTPException(status_code=401, detail="Invalid waitlist link")

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/public/waitlist/position?token=bad.token",
        )

        assert resp.status_code == 401

    @patch(f"{_WAITLIST}._check_rate_limit", new_callable=AsyncMock)
    def test_public_position_missing_token(self, mock_rl):
        """Missing query param 'token' should return 422."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/public/waitlist/position")
        assert resp.status_code == 422
