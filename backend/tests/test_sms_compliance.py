"""
Tests for A2P SMS Compliance — STOP/HELP/START keyword handling.

Validates:
  - All STOP keywords trigger opt-out (STOP, STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT)
  - HELP/INFO keyword replies with company info
  - START/YES/UNSTOP/SUBSCRIBE keywords re-subscribe
  - is_opted_out() correctly reads consent state
  - Case-insensitive keyword matching
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from routes.sms_compliance_routes import (
    STOP_KEYWORDS,
    HELP_KEYWORDS,
    START_KEYWORDS,
    STOP_REPLY,
    HELP_REPLY,
    START_REPLY,
    _opt_out,
    _opt_in,
    is_opted_out,
    _resolve_org,
)


# =============================================================================
# Keyword set completeness
# =============================================================================

class TestKeywordSets:
    """Verify all required A2P 10DLC keywords are covered."""

    def test_stop_keywords_complete(self):
        """All carrier-required STOP keywords must be present."""
        required = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
        assert STOP_KEYWORDS == required

    def test_help_keywords_complete(self):
        required = {"help", "info"}
        assert HELP_KEYWORDS == required

    def test_start_keywords_complete(self):
        required = {"start", "yes", "unstop", "subscribe"}
        assert START_KEYWORDS == required

    def test_no_overlap_between_keyword_sets(self):
        """STOP, HELP, and START keywords must be disjoint."""
        assert STOP_KEYWORDS.isdisjoint(HELP_KEYWORDS)
        assert STOP_KEYWORDS.isdisjoint(START_KEYWORDS)
        assert HELP_KEYWORDS.isdisjoint(START_KEYWORDS)


# =============================================================================
# Reply template compliance
# =============================================================================

class TestReplyTemplates:
    """Verify reply templates meet carrier requirements."""

    def test_stop_reply_mentions_start(self):
        """STOP reply must tell user how to re-subscribe."""
        assert "START" in STOP_REPLY

    def test_help_reply_has_contact_info(self):
        """HELP reply must include contact information."""
        assert "support@perenniaai.com" in HELP_REPLY or "perenniaai" in HELP_REPLY.lower()

    def test_help_reply_mentions_stop(self):
        """HELP reply must mention how to opt out."""
        assert "STOP" in HELP_REPLY

    def test_help_reply_mentions_rates(self):
        """HELP reply must include msg & data rates disclaimer."""
        assert "Msg & data rates" in HELP_REPLY or "rates may apply" in HELP_REPLY

    def test_start_reply_mentions_stop(self):
        """START reply must mention how to opt out."""
        assert "STOP" in START_REPLY

    def test_start_reply_mentions_rates(self):
        """START reply must include msg & data rates disclaimer."""
        assert "rates may apply" in START_REPLY


# =============================================================================
# Case-insensitive matching
# =============================================================================

class TestCaseInsensitiveMatching:
    """Verify keywords match regardless of case."""

    @pytest.mark.parametrize("keyword", [
        "STOP", "Stop", "stop", "sToP",
        "STOPALL", "StopAll", "stopall",
        "UNSUBSCRIBE", "Unsubscribe", "unsubscribe",
        "CANCEL", "Cancel", "cancel",
        "END", "End", "end",
        "QUIT", "Quit", "quit",
    ])
    def test_stop_keyword_case_insensitive(self, keyword):
        """All case variants of STOP keywords should match."""
        assert keyword.lower().strip() in STOP_KEYWORDS

    @pytest.mark.parametrize("keyword", [
        "HELP", "Help", "help", "hElP",
        "INFO", "Info", "info",
    ])
    def test_help_keyword_case_insensitive(self, keyword):
        assert keyword.lower().strip() in HELP_KEYWORDS

    @pytest.mark.parametrize("keyword", [
        "START", "Start", "start",
        "YES", "Yes", "yes",
        "UNSTOP", "Unstop", "unstop",
        "SUBSCRIBE", "Subscribe", "subscribe",
    ])
    def test_start_keyword_case_insensitive(self, keyword):
        assert keyword.lower().strip() in START_KEYWORDS


# =============================================================================
# Opt-out / Opt-in persistence (mocked DB)
# =============================================================================

class TestOptOutPersistence:
    """Test _opt_out writes correct data to sms_consent and dnc_numbers."""

    def test_opt_out_new_record(self):
        """First STOP from a number should INSERT into sms_consent."""
        mock_db = MagicMock()
        # No existing record
        mock_db.execute.return_value.fetchone.return_value = None

        _opt_out(mock_db, "+15551234567", org_id=1, keyword="stop")

        # Should have called execute at least twice: SELECT + INSERT + DNC insert
        assert mock_db.execute.call_count >= 2
        mock_db.commit.assert_called()

    def test_opt_out_existing_record(self):
        """Second STOP from same number should UPDATE existing record."""
        mock_db = MagicMock()
        existing = MagicMock()
        existing.id = 42
        mock_db.execute.return_value.fetchone.return_value = existing

        _opt_out(mock_db, "+15551234567", org_id=1, keyword="stopall")

        # Should UPDATE (not INSERT) since record exists
        assert mock_db.execute.call_count >= 2
        mock_db.commit.assert_called()

    def test_opt_out_handles_db_error_gracefully(self):
        """DB errors during opt-out should not raise."""
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("DB connection lost")

        # Should not raise
        _opt_out(mock_db, "+15551234567", org_id=1, keyword="stop")
        mock_db.rollback.assert_called()


class TestOptInPersistence:
    """Test _opt_in removes opt-out flag and DNC entry."""

    def test_opt_in_updates_consent_record(self):
        """START keyword should set opted_out=FALSE."""
        mock_db = MagicMock()
        _opt_in(mock_db, "+15551234567", org_id=1, keyword="start")
        mock_db.commit.assert_called()

    def test_opt_in_removes_from_dnc(self):
        """START should also DELETE from dnc_numbers."""
        mock_db = MagicMock()
        _opt_in(mock_db, "+15551234567", org_id=1, keyword="start")

        # Should have at least 2 execute calls: UPDATE sms_consent + DELETE dnc_numbers
        assert mock_db.execute.call_count >= 2

    def test_opt_in_handles_db_error_gracefully(self):
        """DB errors during opt-in should not raise."""
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("DB error")

        _opt_in(mock_db, "+15551234567", org_id=1, keyword="start")
        mock_db.rollback.assert_called()


# =============================================================================
# is_opted_out() function
# =============================================================================

class TestIsOptedOut:
    """Test the is_opted_out() check function."""

    def test_opted_out_true(self):
        """Should return True when opted_out flag is True."""
        mock_db = MagicMock()
        mock_row = MagicMock()
        mock_row.opted_out = True
        mock_db.execute.return_value.fetchone.return_value = mock_row

        assert is_opted_out(mock_db, "+15551234567", org_id=1) is True

    def test_opted_out_false(self):
        """Should return False when opted_out flag is False."""
        mock_db = MagicMock()
        mock_row = MagicMock()
        mock_row.opted_out = False
        mock_db.execute.return_value.fetchone.return_value = mock_row

        assert is_opted_out(mock_db, "+15551234567", org_id=1) is False

    def test_no_record_returns_false(self):
        """Should return False when no consent record exists (never messaged)."""
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = None

        assert is_opted_out(mock_db, "+15559999999", org_id=1) is False

    def test_opted_out_is_org_scoped(self):
        """Opt-out for org 1 should not affect org 2."""
        mock_db = MagicMock()

        # Mock: opted out for org 1
        def side_effect(query, params):
            result = MagicMock()
            if params.get("org_id") == 1:
                row = MagicMock()
                row.opted_out = True
                result.fetchone.return_value = row
            else:
                result.fetchone.return_value = None
            return result

        mock_db.execute.side_effect = side_effect

        assert is_opted_out(mock_db, "+15551234567", org_id=1) is True
        assert is_opted_out(mock_db, "+15551234567", org_id=2) is False

    def test_opted_out_with_none_org(self):
        """is_opted_out with org_id=None should still query without error."""
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = None

        result = is_opted_out(mock_db, "+15551234567", org_id=None)
        assert result is False


# =============================================================================
# Webhook endpoint tests (via TestClient)
# =============================================================================

class TestInboundWebhook:
    """Test the POST /sms/inbound-webhook Telnyx handler."""

    def _make_telnyx_payload(self, text_body: str, from_phone: str = "+15551234567", to_phone: str = "+18438838956"):
        """Build a Telnyx inbound message webhook payload."""
        return {
            "data": {
                "event_type": "message.received",
                "payload": {
                    "from": {"phone_number": from_phone},
                    "to": [{"phone_number": to_phone}],
                    "text": text_body,
                },
            }
        }

    @patch("routes.sms_compliance_routes._send_sms", new_callable=AsyncMock)
    @patch("routes.sms_compliance_routes._resolve_org", return_value=1)
    def test_stop_keyword_returns_opt_out(self, mock_resolve, mock_sms, client):
        """STOP keyword should return opt_out status and send STOP_REPLY."""
        response = client.post(
            "/api/v1/sms/inbound-webhook",
            json=self._make_telnyx_payload("STOP"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "opt_out"
        assert data["keyword"] == "stop"

    @patch("routes.sms_compliance_routes._send_sms", new_callable=AsyncMock)
    @patch("routes.sms_compliance_routes._resolve_org", return_value=1)
    def test_help_keyword_returns_help_sent(self, mock_resolve, mock_sms, client):
        """HELP keyword should return help_sent status."""
        response = client.post(
            "/api/v1/sms/inbound-webhook",
            json=self._make_telnyx_payload("HELP"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "help_sent"

    @patch("routes.sms_compliance_routes._send_sms", new_callable=AsyncMock)
    @patch("routes.sms_compliance_routes._resolve_org", return_value=1)
    def test_start_keyword_returns_opt_in(self, mock_resolve, mock_sms, client):
        """START keyword should return opt_in status."""
        response = client.post(
            "/api/v1/sms/inbound-webhook",
            json=self._make_telnyx_payload("START"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "opt_in"

    @patch("routes.sms_compliance_routes._send_sms", new_callable=AsyncMock)
    @patch("routes.sms_compliance_routes._resolve_org", return_value=1)
    def test_non_keyword_returns_not_keyword(self, mock_resolve, mock_sms, client):
        """Regular message text should return not_keyword status."""
        response = client.post(
            "/api/v1/sms/inbound-webhook",
            json=self._make_telnyx_payload("What are today's rates?"),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_keyword"

    def test_non_message_event_returns_ignored(self, client):
        """Non message.received events should be ignored."""
        response = client.post(
            "/api/v1/sms/inbound-webhook",
            json={"data": {"event_type": "message.sent", "payload": {}}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ignored"

    @patch("routes.sms_compliance_routes._send_sms", new_callable=AsyncMock)
    @patch("routes.sms_compliance_routes._resolve_org", return_value=1)
    @pytest.mark.parametrize("keyword", ["STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"])
    def test_all_stop_keywords_trigger_opt_out(self, mock_resolve, mock_sms, keyword, client):
        """Every STOP variant should trigger opt-out."""
        response = client.post(
            "/api/v1/sms/inbound-webhook",
            json=self._make_telnyx_payload(keyword),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "opt_out"

    @patch("routes.sms_compliance_routes._send_sms", new_callable=AsyncMock)
    @patch("routes.sms_compliance_routes._resolve_org", return_value=1)
    @pytest.mark.parametrize("keyword", ["start", "yes", "unstop", "subscribe"])
    def test_all_start_keywords_trigger_opt_in(self, mock_resolve, mock_sms, keyword, client):
        """Every START variant should trigger opt-in."""
        response = client.post(
            "/api/v1/sms/inbound-webhook",
            json=self._make_telnyx_payload(keyword),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "opt_in"


# =============================================================================
# Check opt-out API endpoint
# =============================================================================

class TestCheckOptOutEndpoint:
    """Test the POST /sms/check-opt-out endpoint."""

    @patch("routes.sms_compliance_routes.is_opted_out", return_value=True)
    def test_check_opted_out_phone(self, mock_check, client):
        """Should return opted_out: true for opted-out phone."""
        response = client.post(
            "/api/v1/sms/check-opt-out",
            json={"phone": "+15551234567", "organization_id": 1},
        )
        assert response.status_code == 200
        assert response.json()["opted_out"] is True

    @patch("routes.sms_compliance_routes.is_opted_out", return_value=False)
    def test_check_not_opted_out_phone(self, mock_check, client):
        """Should return opted_out: false for active phone."""
        response = client.post(
            "/api/v1/sms/check-opt-out",
            json={"phone": "+15559999999", "organization_id": 1},
        )
        assert response.status_code == 200
        assert response.json()["opted_out"] is False
