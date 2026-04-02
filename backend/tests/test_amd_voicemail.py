"""
Tests for AMD (Answering Machine Detection) Voicemail Drop flow.

Validates:
  - Machine detection triggers Slybroadcast voicemail drop
  - Human detection does nothing (call proceeds)
  - Fax detection hangs up the call
  - TCPA blocking on voicemail drops
  - Per-org AMD config loading
  - Slybroadcast API integration (mocked)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from routes.amd_voicemail_routes import (
    AMDConfig,
    _get_org_amd_config,
    _log_amd_event,
    trigger_slybroadcast_drop,
    SLYBROADCAST_URL,
)


# =============================================================================
# AMDConfig model tests
# =============================================================================

class TestAMDConfig:
    """Test the AMDConfig Pydantic model defaults."""

    def test_default_config_values(self):
        """Default config should have AMD enabled with drop_voicemail action."""
        config = AMDConfig()
        assert config.amd_enabled is True
        assert config.amd_action == "drop_voicemail"
        assert config.default_vm_audio_url == ""
        assert config.ring_timeout_seconds == 25
        assert config.caller_id == ""

    def test_custom_config(self):
        config = AMDConfig(
            amd_enabled=False,
            amd_action="hangup",
            default_vm_audio_url="https://cdn.example.com/vm.mp3",
            ring_timeout_seconds=30,
            caller_id="+18431234567",
        )
        assert config.amd_enabled is False
        assert config.amd_action == "hangup"
        assert config.default_vm_audio_url == "https://cdn.example.com/vm.mp3"


# =============================================================================
# Org AMD config loading
# =============================================================================

class TestGetOrgAMDConfig:
    """Test _get_org_amd_config reads from DB or returns defaults."""

    def test_returns_defaults_when_no_config_exists(self):
        """No config row in DB should return AMDConfig defaults."""
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = None

        config = _get_org_amd_config(mock_db, organization_id=1)
        assert config.amd_enabled is True
        assert config.amd_action == "drop_voicemail"

    def test_reads_config_from_db(self):
        """Should populate config from DB row."""
        mock_db = MagicMock()
        mock_row = MagicMock()
        mock_row.amd_enabled = False
        mock_row.amd_action = "hangup"
        mock_row.default_vm_audio_url = "https://cdn.example.com/greeting.mp3"
        mock_row.ring_timeout_seconds = 30
        mock_row.caller_id = "+18431234567"
        mock_db.execute.return_value.fetchone.return_value = mock_row

        config = _get_org_amd_config(mock_db, organization_id=1)
        assert config.amd_enabled is False
        assert config.amd_action == "hangup"
        assert config.default_vm_audio_url == "https://cdn.example.com/greeting.mp3"
        assert config.ring_timeout_seconds == 30

    def test_handles_null_fields_gracefully(self):
        """NULL DB values should fall back to defaults."""
        mock_db = MagicMock()
        mock_row = MagicMock()
        mock_row.amd_enabled = None
        mock_row.amd_action = None
        mock_row.default_vm_audio_url = None
        mock_row.ring_timeout_seconds = None
        mock_row.caller_id = None
        mock_db.execute.return_value.fetchone.return_value = mock_row

        config = _get_org_amd_config(mock_db, organization_id=1)
        assert config.amd_enabled is True  # None → True
        assert config.amd_action == "drop_voicemail"  # None → default
        assert config.default_vm_audio_url == ""
        assert config.ring_timeout_seconds == 25  # None → 25


# =============================================================================
# AMD callback webhook endpoint tests
# =============================================================================

class TestAMDCallbackEndpoint:
    """Test POST /api/v1/telephony/amd-callback."""

    def _make_amd_payload(self, result: str, to: str = "+15551234567", from_: str = "+18438838956"):
        """Build a Telnyx AMD callback payload."""
        return {
            "data": {
                "event_type": "call.machine.detection.ended",
                "payload": {
                    "result": result,
                    "call_control_id": "test-call-ctrl-123",
                    "to": to,
                    "from": from_,
                },
            }
        }

    @patch("routes.amd_voicemail_routes.trigger_slybroadcast_drop", new_callable=AsyncMock, return_value={"success": True, "session_id": "123"})
    @patch("routes.amd_voicemail_routes._get_org_amd_config", return_value=AMDConfig(default_vm_audio_url="https://cdn.example.com/vm.mp3"))
    @patch("routes.amd_voicemail_routes.httpx.AsyncClient")
    def test_machine_detection_triggers_voicemail_drop(self, mock_httpx, mock_config, mock_sly, client):
        """AMD result 'machine' should trigger Slybroadcast drop."""
        # Mock the httpx hangup call
        mock_client_instance = AsyncMock()
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = client.post(
            "/api/v1/telephony/amd-callback",
            json=self._make_amd_payload("machine"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "voicemail_dropped"

    def test_human_detection_does_nothing(self, client):
        """AMD result 'human' should return human_detected, no voicemail drop."""
        response = client.post(
            "/api/v1/telephony/amd-callback",
            json=self._make_amd_payload("human"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "human_detected"

    @patch("routes.amd_voicemail_routes.httpx.AsyncClient")
    def test_fax_detection_hangs_up(self, mock_httpx, client):
        """AMD result 'fax' should hang up the call."""
        mock_client_instance = AsyncMock()
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = client.post(
            "/api/v1/telephony/amd-callback",
            json=self._make_amd_payload("fax"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "fax_hangup"

    def test_not_sure_treated_as_human(self, client):
        """AMD result 'not_sure' should be treated like human (call proceeds)."""
        response = client.post(
            "/api/v1/telephony/amd-callback",
            json=self._make_amd_payload("not_sure"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "human_detected"

    @patch("routes.amd_voicemail_routes.trigger_slybroadcast_drop", new_callable=AsyncMock)
    @patch("routes.amd_voicemail_routes._get_org_amd_config", return_value=AMDConfig(amd_enabled=True, amd_action="drop_voicemail", default_vm_audio_url="https://cdn.example.com/vm.mp3"))
    @patch("routes.amd_voicemail_routes.httpx.AsyncClient")
    def test_tcpa_blocks_voicemail_drop(self, mock_httpx, mock_config, mock_sly, client):
        """When TCPA quiet hours are active, voicemail drop should be blocked."""
        mock_client_instance = AsyncMock()
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("routes.amd_voicemail_routes.check_calling_hours", return_value=(False, "TCPA blocked")):
            response = client.post(
                "/api/v1/telephony/amd-callback",
                json=self._make_amd_payload("machine"),
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "tcpa_blocked"
            mock_sly.assert_not_called()

    @patch("routes.amd_voicemail_routes._get_org_amd_config", return_value=AMDConfig(amd_enabled=False))
    @patch("routes.amd_voicemail_routes.httpx.AsyncClient")
    def test_amd_disabled_skips_drop(self, mock_httpx, mock_config, client):
        """When AMD is disabled for the org, machine detection should skip the drop."""
        mock_client_instance = AsyncMock()
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = client.post(
            "/api/v1/telephony/amd-callback",
            json=self._make_amd_payload("machine"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skipped"

    @patch("routes.amd_voicemail_routes._get_org_amd_config", return_value=AMDConfig(amd_action="hangup"))
    @patch("routes.amd_voicemail_routes.httpx.AsyncClient")
    def test_amd_action_hangup_skips_drop(self, mock_httpx, mock_config, client):
        """When amd_action is 'hangup' (not 'drop_voicemail'), should skip the drop."""
        mock_client_instance = AsyncMock()
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

        response = client.post(
            "/api/v1/telephony/amd-callback",
            json=self._make_amd_payload("machine"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skipped"


# =============================================================================
# Slybroadcast trigger function (mocked HTTP)
# =============================================================================

class TestTriggerSlybroadcastDrop:
    """Test the trigger_slybroadcast_drop function."""

    @pytest.mark.asyncio
    async def test_success_response_parsing(self):
        """Successful Slybroadcast response should parse session_id."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK\nsession_id=12345\nnumber of phone=1"

        with patch.dict("os.environ", {
            "SLYBROADCAST_EMAIL": "test@test.com",
            "SLYBROADCAST_PASSWORD": "testpass",
            "TELNYX_FROM_NUMBER": "+18438838956",
        }), patch("routes.amd_voicemail_routes.httpx.AsyncClient") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await trigger_slybroadcast_drop(
                phone_number="+15551234567",
                audio_url="https://cdn.example.com/voicemail.mp3",
                caller_id="+18438838956",
            )

            assert result["success"] is True
            assert result["session_id"] == "12345"
            assert result["provider"] == "slybroadcast"

    @pytest.mark.asyncio
    async def test_missing_credentials_returns_error(self):
        """No Slybroadcast credentials should return error."""
        with patch.dict("os.environ", {"SLYBROADCAST_EMAIL": "", "SLYBROADCAST_PASSWORD": ""}, clear=False):
            result = await trigger_slybroadcast_drop(
                phone_number="+15551234567",
                audio_url="https://cdn.example.com/vm.mp3",
            )
            assert result["success"] is False
            assert "not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_audio_url_returns_error(self):
        """No audio URL should return error."""
        with patch.dict("os.environ", {
            "SLYBROADCAST_EMAIL": "test@test.com",
            "SLYBROADCAST_PASSWORD": "testpass",
        }):
            result = await trigger_slybroadcast_drop(
                phone_number="+15551234567",
                audio_url="",
            )
            assert result["success"] is False
            assert "No audio URL" in result["error"]

    @pytest.mark.asyncio
    async def test_phone_number_normalization(self):
        """Phone numbers should be normalized to 11-digit US format."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK\nsession_id=99999"

        with patch.dict("os.environ", {
            "SLYBROADCAST_EMAIL": "test@test.com",
            "SLYBROADCAST_PASSWORD": "testpass",
            "TELNYX_FROM_NUMBER": "+18438838956",
        }), patch("routes.amd_voicemail_routes.httpx.AsyncClient") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            # 10-digit number should get "1" prepended
            await trigger_slybroadcast_drop(
                phone_number="5551234567",
                audio_url="https://cdn.example.com/vm.mp3",
            )

            # Verify the cleaned number in the POST payload
            call_args = mock_client.post.call_args
            payload = call_args.kwargs.get("data") or call_args[1].get("data")
            assert payload["c_phone"] == "15551234567"

    @pytest.mark.asyncio
    async def test_http_error_returns_failure(self):
        """Non-200 HTTP response should return failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch.dict("os.environ", {
            "SLYBROADCAST_EMAIL": "test@test.com",
            "SLYBROADCAST_PASSWORD": "testpass",
        }), patch("routes.amd_voicemail_routes.httpx.AsyncClient") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await trigger_slybroadcast_drop(
                phone_number="+15551234567",
                audio_url="https://cdn.example.com/vm.mp3",
            )
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_slybroadcast_error_response(self):
        """Slybroadcast returning non-OK first line should be treated as failure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ERROR\ninvalid credentials"

        with patch.dict("os.environ", {
            "SLYBROADCAST_EMAIL": "test@test.com",
            "SLYBROADCAST_PASSWORD": "testpass",
        }), patch("routes.amd_voicemail_routes.httpx.AsyncClient") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await trigger_slybroadcast_drop(
                phone_number="+15551234567",
                audio_url="https://cdn.example.com/vm.mp3",
            )
            assert result["success"] is False


# =============================================================================
# AMD event logging
# =============================================================================

class TestAMDEventLogging:
    """Test _log_amd_event best-effort logging."""

    def test_log_event_commits(self):
        """Should INSERT into amd_events and commit."""
        mock_db = MagicMock()
        _log_amd_event(mock_db, "+15551234567", "amd_detection", "machine", 1, {"key": "value"})
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_log_event_handles_missing_table(self):
        """Should not raise if amd_events table doesn't exist."""
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("relation 'amd_events' does not exist")

        # Should not raise
        _log_amd_event(mock_db, "+15551234567", "amd_detection", "machine", 1, {})
        mock_db.rollback.assert_called_once()

    def test_log_event_truncates_meta(self):
        """Meta dict serialization should be truncated to 2000 chars."""
        mock_db = MagicMock()
        large_meta = {"data": "x" * 3000}
        _log_amd_event(mock_db, "+15551234567", "test", "test", 1, large_meta)

        # Extract the params dict from the execute call
        # db.execute(text(...), {...params...})
        call_args = mock_db.execute.call_args
        # call_args is a tuple of (args, kwargs)
        # The params dict is the second positional argument
        args, kwargs = call_args
        params = args[1] if len(args) > 1 else kwargs
        assert len(params["meta"]) <= 2000
