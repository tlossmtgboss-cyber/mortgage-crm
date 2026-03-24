"""
Scheduler Meetings Route Tests

Tests for the meeting integration endpoints in routes/scheduler/meetings.py.
Covers:
  - GET  /meetings/settings               Get virtual meeting provider settings
  - POST /meetings/settings               Save/update meeting provider config
  - POST /meetings/test-connection         Test meeting provider connectivity
  - Validation: invalid provider, missing credentials
  - Edge cases: no provider configured, expired OAuth token, provider error
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


@pytest.fixture
def admin_user():
    return MockUser(role="admin")


# Shared patch targets
_MEETINGS = "routes.scheduler.meetings"
_SERVICE = "services.virtual_meeting_service"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


def _mock_provider_settings(
    default_provider="auto",
    auto_create_for_video=True,
    default_meeting_duration=30,
    user_id=10,
    org_id=1,
):
    """Create a mock MeetingProviderSettings object."""
    settings = MagicMock()
    settings.default_provider = default_provider
    settings.auto_create_for_video = auto_create_for_video
    settings.default_meeting_duration = default_meeting_duration
    settings.user_id = user_id
    settings.organization_id = org_id
    return settings


# =============================================================================
# GET /meetings/settings — Get provider settings
# =============================================================================

class TestGetProviderSettings:
    """GET /api/v1/scheduler/meetings/settings."""

    @patch(f"{_MEETINGS}._get_connected_providers")
    @patch(f"{_MEETINGS}.MeetingProviderFactory")
    @patch(f"{_MEETINGS}.get_meeting_provider_settings")
    @patch(f"{_MEETINGS}.get_current_user", new_callable=AsyncMock)
    def test_get_settings_success(
        self, mock_auth, mock_get_settings, mock_factory, mock_connected, auth_user
    ):
        """Should return current provider settings with available and connected providers."""
        mock_auth.return_value = auth_user
        mock_get_settings.return_value = _mock_provider_settings(
            default_provider="zoom",
            auto_create_for_video=True,
            default_meeting_duration=45,
        )
        mock_factory.get_available_providers.return_value = [
            "zoom", "google_meet", "teams", "perennia", "manual"
        ]
        mock_connected.return_value = ["zoom", "perennia", "manual"]

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/meetings/settings",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["default_provider"] == "zoom"
        assert data["auto_create_for_video"] is True
        assert data["default_meeting_duration"] == 45
        assert "zoom" in data["available_providers"]
        assert "zoom" in data["connected_providers"]

    @patch(f"{_MEETINGS}._get_connected_providers")
    @patch(f"{_MEETINGS}.MeetingProviderFactory")
    @patch(f"{_MEETINGS}.get_meeting_provider_settings")
    @patch(f"{_MEETINGS}.get_current_user", new_callable=AsyncMock)
    def test_get_settings_no_provider_configured(
        self, mock_auth, mock_get_settings, mock_factory, mock_connected, auth_user
    ):
        """When user has no provider configured, should return defaults."""
        mock_auth.return_value = auth_user
        mock_get_settings.return_value = _mock_provider_settings(
            default_provider="auto",
            auto_create_for_video=True,
            default_meeting_duration=30,
        )
        mock_factory.get_available_providers.return_value = [
            "zoom", "google_meet", "teams", "perennia", "manual"
        ]
        mock_connected.return_value = ["perennia", "manual"]

        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/meetings/settings",
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["default_provider"] == "auto"
        assert data["default_meeting_duration"] == 30
        # Only perennia and manual are connected (no OAuth integrations)
        assert "perennia" in data["connected_providers"]
        assert "zoom" not in data["connected_providers"]

    def test_get_settings_no_auth(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/meetings/settings")
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# POST /meetings/settings — Save provider settings
# =============================================================================

class TestSaveProviderSettings:
    """POST /api/v1/scheduler/meetings/settings."""

    @patch(f"{_MEETINGS}._get_connected_providers")
    @patch(f"{_MEETINGS}.MeetingProviderFactory")
    @patch(f"{_MEETINGS}._audit_log")
    @patch(f"{_MEETINGS}.save_meeting_provider_settings")
    @patch(f"{_MEETINGS}.get_current_user", new_callable=AsyncMock)
    def test_save_settings_zoom(
        self, mock_auth, mock_save, mock_audit, mock_factory, mock_connected, auth_user
    ):
        """Should save Zoom as default provider and return updated settings."""
        mock_auth.return_value = auth_user
        mock_save.return_value = _mock_provider_settings(
            default_provider="zoom",
            auto_create_for_video=False,
            default_meeting_duration=60,
        )
        mock_factory.get_available_providers.return_value = [
            "zoom", "google_meet", "teams", "perennia", "manual"
        ]
        mock_connected.return_value = ["zoom", "perennia", "manual"]

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/meetings/settings",
            json={
                "default_provider": "zoom",
                "auto_create_for_video": False,
                "default_meeting_duration": 60,
            },
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["default_provider"] == "zoom"
        assert data["auto_create_for_video"] is False
        assert data["default_meeting_duration"] == 60
        mock_save.assert_called_once()
        mock_audit.assert_called_once()

    @patch(f"{_MEETINGS}._get_connected_providers")
    @patch(f"{_MEETINGS}.MeetingProviderFactory")
    @patch(f"{_MEETINGS}._audit_log")
    @patch(f"{_MEETINGS}.save_meeting_provider_settings")
    @patch(f"{_MEETINGS}.get_current_user", new_callable=AsyncMock)
    def test_save_settings_google_meet(
        self, mock_auth, mock_save, mock_audit, mock_factory, mock_connected, auth_user
    ):
        """Should accept google_meet as a valid provider."""
        mock_auth.return_value = auth_user
        mock_save.return_value = _mock_provider_settings(default_provider="google_meet")
        mock_factory.get_available_providers.return_value = [
            "zoom", "google_meet", "teams", "perennia", "manual"
        ]
        mock_connected.return_value = ["google_meet", "perennia", "manual"]

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/meetings/settings",
            json={"default_provider": "google_meet"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        assert resp.json()["default_provider"] == "google_meet"

    @patch(f"{_MEETINGS}._get_connected_providers")
    @patch(f"{_MEETINGS}.MeetingProviderFactory")
    @patch(f"{_MEETINGS}._audit_log")
    @patch(f"{_MEETINGS}.save_meeting_provider_settings")
    @patch(f"{_MEETINGS}.get_current_user", new_callable=AsyncMock)
    def test_save_settings_teams(
        self, mock_auth, mock_save, mock_audit, mock_factory, mock_connected, auth_user
    ):
        """Should accept teams as a valid provider."""
        mock_auth.return_value = auth_user
        mock_save.return_value = _mock_provider_settings(default_provider="teams")
        mock_factory.get_available_providers.return_value = [
            "zoom", "google_meet", "teams", "perennia", "manual"
        ]
        mock_connected.return_value = ["teams", "perennia", "manual"]

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/meetings/settings",
            json={"default_provider": "teams"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        assert resp.json()["default_provider"] == "teams"

    @patch(f"{_MEETINGS}.save_meeting_provider_settings")
    @patch(f"{_MEETINGS}.get_current_user", new_callable=AsyncMock)
    def test_save_settings_invalid_provider_raises_value_error(
        self, mock_auth, mock_save, auth_user
    ):
        """When save_meeting_provider_settings raises ValueError for invalid provider, return 400."""
        mock_auth.return_value = auth_user
        mock_save.side_effect = ValueError("Invalid provider 'webex'. Valid: zoom, google_meet, teams, perennia, manual")

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/meetings/settings",
            json={"default_provider": "webex"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "Invalid provider" in resp.json()["detail"]

    @patch(f"{_MEETINGS}.save_meeting_provider_settings")
    @patch(f"{_MEETINGS}.get_current_user", new_callable=AsyncMock)
    def test_save_settings_service_failure_returns_500(
        self, mock_auth, mock_save, auth_user
    ):
        """When save raises an unexpected exception, return 500."""
        mock_auth.return_value = auth_user
        mock_save.side_effect = RuntimeError("Database connection lost")

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/meetings/settings",
            json={"default_provider": "zoom"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 500
        assert "Failed to save settings" in resp.json()["detail"]

    def test_save_settings_duration_below_minimum_rejected(self):
        """Duration below 5 minutes should be rejected by Pydantic validation (422)."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/meetings/settings",
            json={"default_meeting_duration": 2},
            headers={"Authorization": "Bearer test"},
        )

        # Pydantic ge=5 constraint triggers 422 before the handler runs
        assert resp.status_code == 422

    def test_save_settings_duration_above_maximum_rejected(self):
        """Duration above 480 minutes should be rejected by Pydantic validation (422)."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/meetings/settings",
            json={"default_meeting_duration": 999},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 422


# =============================================================================
# POST /meetings/test-connection — Test provider connectivity
# =============================================================================

class TestMeetingConnection:
    """POST /api/v1/scheduler/meetings/test-connection."""

    @patch(f"{_MEETINGS}.MeetingProviderFactory")
    @patch(f"{_MEETINGS}.get_current_user", new_callable=AsyncMock)
    def test_connection_success(self, mock_auth, mock_factory, auth_user):
        """Successful provider connectivity test should return success=True."""
        mock_auth.return_value = auth_user
        mock_factory.get_available_providers.return_value = [
            "zoom", "google_meet", "teams", "perennia", "manual"
        ]

        mock_provider = AsyncMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.provider = "zoom"
        mock_result.error = ""
        mock_result.metadata = {"account_email": "user@test.com"}
        mock_provider.test_connection.return_value = mock_result
        mock_factory.get_provider.return_value = mock_provider

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/meetings/test-connection",
            json={"provider": "zoom"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["provider"] == "zoom"
        assert data["message"] == "Connection successful"

    @patch(f"{_MEETINGS}.MeetingProviderFactory")
    @patch(f"{_MEETINGS}.get_current_user", new_callable=AsyncMock)
    def test_connection_invalid_provider(self, mock_auth, mock_factory, auth_user):
        """Invalid provider name should return 400."""
        mock_auth.return_value = auth_user
        mock_factory.get_available_providers.return_value = [
            "zoom", "google_meet", "teams", "perennia", "manual"
        ]

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/meetings/test-connection",
            json={"provider": "skype"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 400
        assert "Invalid provider" in resp.json()["detail"]

    @patch(f"{_MEETINGS}.MeetingProviderFactory")
    @patch(f"{_MEETINGS}.get_current_user", new_callable=AsyncMock)
    def test_connection_expired_oauth_token(self, mock_auth, mock_factory, auth_user):
        """When OAuth token is expired, test_connection should return success=False with error message."""
        mock_auth.return_value = auth_user
        mock_factory.get_available_providers.return_value = [
            "zoom", "google_meet", "teams", "perennia", "manual"
        ]

        mock_provider = AsyncMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.provider = "zoom"
        mock_result.error = "OAuth token expired. Please re-authorize Zoom."
        mock_result.metadata = {}
        mock_provider.test_connection.return_value = mock_result
        mock_factory.get_provider.return_value = mock_provider

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/meetings/test-connection",
            json={"provider": "zoom"},
            headers={"Authorization": "Bearer test"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "expired" in data["message"].lower()

    @patch(f"{_MEETINGS}.MeetingProviderFactory")
    @patch(f"{_MEETINGS}.get_current_user", new_callable=AsyncMock)
    def test_connection_provider_exception(self, mock_auth, mock_factory, auth_user):
        """When provider raises an exception during test, should return success=False gracefully."""
        mock_auth.return_value = auth_user
        mock_factory.get_available_providers.return_value = [
            "zoom", "google_meet", "teams", "perennia", "manual"
        ]
        mock_factory.get_provider.side_effect = Exception("Provider initialization failed: missing credentials")

        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/meetings/test-connection",
            json={"provider": "teams"},
            headers={"Authorization": "Bearer test"},
        )

        # The endpoint catches all exceptions and returns a response (not a 500)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "missing credentials" in data["message"].lower()

    def test_connection_no_auth(self):
        """Unauthenticated requests should be rejected."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/meetings/test-connection",
            json={"provider": "zoom"},
        )
        assert resp.status_code in (401, 403, 500)
