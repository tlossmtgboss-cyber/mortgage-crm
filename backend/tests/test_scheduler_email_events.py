"""
Scheduler Email Events Route Tests

Tests for the email event handling endpoints in routes/scheduler/email_events.py.
Covers:
  - POST /email-events/sendgrid      SendGrid webhook (bounce, delivered, open, click)
  - POST /email-events/unsubscribe   RFC 8058 one-click unsubscribe
  - GET  /email-events/unsubscribe   Browser unsubscribe confirmation page
  - GET  /email-events/suppressions  List suppressions (admin, auth required)
  - DELETE /email-events/suppressions/{email}  Remove suppression (admin, auth required)
  - Org-id resolution from appointment email
  - Invalid HMAC tokens on unsubscribe
  - Duplicate event processing (upsert behavior)
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
    """Mock user for authenticated admin tests."""
    def __init__(self, role="admin", org_id=1, user_id=10):
        self.id = user_id
        self.organization_id = org_id
        self.role = role
        self.permission_role = role
        self.email = "admin@test.com"


class MockSuppression:
    """Mock EmailSuppression row."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.email = kwargs.get("email", "bounced@example.com")
        self.reason = kwargs.get("reason", "hard bounce")
        self.event_type = kwargs.get("event_type", "bounce")
        self.organization_id = kwargs.get("organization_id", 1)
        self.suppressed_at = kwargs.get(
            "suppressed_at", datetime.now(timezone.utc)
        )


@pytest.fixture
def admin_user():
    return MockUser(role="admin")


@pytest.fixture
def lo_user():
    return MockUser(role="loan_officer")


# Patch targets
_EMAIL_EVENTS = "routes.scheduler.email_events"
_HELPERS = "routes.scheduler._helpers"

# Use a stable secret for HMAC token generation/verification in tests
_TEST_SECRET = "test-secret-key-for-hmac-signing-1234"


def _get_client():
    """Build a TestClient with the FastAPI app."""
    from main import app
    return TestClient(app)


def _make_unsubscribe_token(email: str, secret: str = _TEST_SECRET) -> str:
    """Generate an HMAC-signed unsubscribe token (mirrors production logic)."""
    import base64
    import hashlib
    import hmac as hmac_mod

    email_b64 = base64.urlsafe_b64encode(email.lower().strip().encode()).decode()
    sig = hmac_mod.new(secret.encode(), email_b64.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{email_b64}.{sig}"


# =============================================================================
# POST /email-events/sendgrid — SendGrid Event Webhook
# =============================================================================

class TestSendGridWebhook:
    """POST /api/v1/scheduler/email-events/sendgrid."""

    @patch(f"{_EMAIL_EVENTS}._check_rate_limit", new_callable=AsyncMock)
    @patch(f"{_EMAIL_EVENTS}.add_email_suppression")
    @patch(f"{_EMAIL_EVENTS}._resolve_org_id_for_email", return_value=1)
    @patch(f"{_EMAIL_EVENTS}._SENDGRID_WEBHOOK_KEY", None)
    def test_bounce_event_creates_suppression(
        self, mock_resolve, mock_add_sup, mock_rate_limit
    ):
        """A bounce event should add the email to the suppression list."""
        client = _get_client()
        events = [
            {
                "event": "bounce",
                "email": "bad@example.com",
                "reason": "550 User unknown",
            }
        ]
        resp = client.post(
            "/api/v1/scheduler/email-events/sendgrid",
            json=events,
        )
        assert resp.status_code == 200
        assert resp.json()["processed"] == 1
        mock_add_sup.assert_called_once()
        call_kwargs = mock_add_sup.call_args
        assert call_kwargs.kwargs["email"] == "bad@example.com"
        assert call_kwargs.kwargs["event_type"] == "bounce"

    @patch(f"{_EMAIL_EVENTS}._check_rate_limit", new_callable=AsyncMock)
    @patch(f"{_EMAIL_EVENTS}.add_email_suppression")
    @patch(f"{_EMAIL_EVENTS}._resolve_org_id_for_email", return_value=1)
    @patch(f"{_EMAIL_EVENTS}._SENDGRID_WEBHOOK_KEY", None)
    def test_multiple_event_types_processed(
        self, mock_resolve, mock_add_sup, mock_rate_limit
    ):
        """bounce, dropped, spamreport, and unsubscribe events should all be processed."""
        client = _get_client()
        events = [
            {"event": "bounce", "email": "a@example.com", "reason": "hard bounce"},
            {"event": "dropped", "email": "b@example.com", "reason": "bounced address"},
            {"event": "spamreport", "email": "c@example.com"},
            {"event": "unsubscribe", "email": "d@example.com"},
        ]
        resp = client.post(
            "/api/v1/scheduler/email-events/sendgrid",
            json=events,
        )
        assert resp.status_code == 200
        assert resp.json()["processed"] == 4
        assert mock_add_sup.call_count == 4

    @patch(f"{_EMAIL_EVENTS}._check_rate_limit", new_callable=AsyncMock)
    @patch(f"{_EMAIL_EVENTS}.add_email_suppression")
    @patch(f"{_EMAIL_EVENTS}._resolve_org_id_for_email", return_value=1)
    @patch(f"{_EMAIL_EVENTS}._SENDGRID_WEBHOOK_KEY", None)
    def test_non_suppression_events_ignored(
        self, mock_resolve, mock_add_sup, mock_rate_limit
    ):
        """delivered, open, click events should NOT create suppressions."""
        client = _get_client()
        events = [
            {"event": "delivered", "email": "ok@example.com"},
            {"event": "open", "email": "ok@example.com"},
            {"event": "click", "email": "ok@example.com", "url": "https://example.com"},
        ]
        resp = client.post(
            "/api/v1/scheduler/email-events/sendgrid",
            json=events,
        )
        assert resp.status_code == 200
        assert resp.json()["processed"] == 0
        mock_add_sup.assert_not_called()

    @patch(f"{_EMAIL_EVENTS}._check_rate_limit", new_callable=AsyncMock)
    @patch(f"{_EMAIL_EVENTS}._SENDGRID_WEBHOOK_KEY", None)
    def test_invalid_json_returns_400(self, mock_rate_limit):
        """Non-array payloads should be rejected with 400."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/email-events/sendgrid",
            json={"event": "bounce", "email": "bad@example.com"},
        )
        assert resp.status_code == 400

    @patch(f"{_EMAIL_EVENTS}._check_rate_limit", new_callable=AsyncMock)
    @patch(f"{_EMAIL_EVENTS}.add_email_suppression")
    @patch(f"{_EMAIL_EVENTS}._resolve_org_id_for_email", return_value=None)
    @patch(f"{_EMAIL_EVENTS}._SENDGRID_WEBHOOK_KEY", None)
    def test_org_id_resolution_failure_still_processes(
        self, mock_resolve, mock_add_sup, mock_rate_limit
    ):
        """Events should still be processed even when org_id cannot be resolved."""
        client = _get_client()
        events = [
            {"event": "bounce", "email": "unknown@example.com", "reason": "no such user"},
        ]
        resp = client.post(
            "/api/v1/scheduler/email-events/sendgrid",
            json=events,
        )
        assert resp.status_code == 200
        assert resp.json()["processed"] == 1
        mock_add_sup.assert_called_once()
        assert mock_add_sup.call_args.kwargs["org_id"] is None


# =============================================================================
# POST /email-events/unsubscribe/{token} — RFC 8058 One-Click Unsubscribe
# =============================================================================

class TestUnsubscribePost:
    """POST /api/v1/scheduler/email-events/unsubscribe/{token}."""

    @patch(f"{_EMAIL_EVENTS}._check_rate_limit", new_callable=AsyncMock)
    @patch(f"{_EMAIL_EVENTS}.add_email_suppression")
    @patch(f"{_EMAIL_EVENTS}._resolve_org_id_for_email", return_value=1)
    @patch(f"{_EMAIL_EVENTS}._get_unsubscribe_secret", return_value=_TEST_SECRET)
    def test_valid_token_unsubscribes(
        self, mock_secret, mock_resolve, mock_add_sup, mock_rate_limit
    ):
        """A valid HMAC token should add the email to the suppression list."""
        token = _make_unsubscribe_token("user@example.com")
        client = _get_client()
        resp = client.post(
            f"/api/v1/scheduler/email-events/unsubscribe/{token}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        mock_add_sup.assert_called_once()
        assert mock_add_sup.call_args.kwargs["email"] == "user@example.com"
        assert mock_add_sup.call_args.kwargs["event_type"] == "unsubscribe"

    @patch(f"{_EMAIL_EVENTS}._check_rate_limit", new_callable=AsyncMock)
    @patch(f"{_EMAIL_EVENTS}._get_unsubscribe_secret", return_value=_TEST_SECRET)
    def test_invalid_token_returns_400(self, mock_secret, mock_rate_limit):
        """A forged or corrupted token should be rejected."""
        client = _get_client()
        resp = client.post(
            "/api/v1/scheduler/email-events/unsubscribe/invalid.token.garbage",
        )
        assert resp.status_code == 400

    @patch(f"{_EMAIL_EVENTS}._check_rate_limit", new_callable=AsyncMock)
    @patch(f"{_EMAIL_EVENTS}._get_unsubscribe_secret", return_value=_TEST_SECRET)
    def test_tampered_signature_returns_400(self, mock_secret, mock_rate_limit):
        """A token with correct email but wrong signature should fail."""
        import base64
        email_b64 = base64.urlsafe_b64encode(b"user@example.com").decode()
        forged_token = f"{email_b64}.00000000000000000000000000000000"
        client = _get_client()
        resp = client.post(
            f"/api/v1/scheduler/email-events/unsubscribe/{forged_token}",
        )
        assert resp.status_code == 400


# =============================================================================
# GET /email-events/unsubscribe/{token} — Browser Unsubscribe Page
# =============================================================================

class TestUnsubscribeGet:
    """GET /api/v1/scheduler/email-events/unsubscribe/{token}."""

    @patch(f"{_EMAIL_EVENTS}._check_rate_limit", new_callable=AsyncMock)
    @patch(f"{_EMAIL_EVENTS}.add_email_suppression")
    @patch(f"{_EMAIL_EVENTS}._resolve_org_id_for_email", return_value=1)
    @patch(f"{_EMAIL_EVENTS}._get_unsubscribe_secret", return_value=_TEST_SECRET)
    def test_valid_token_returns_html_page(
        self, mock_secret, mock_resolve, mock_add_sup, mock_rate_limit
    ):
        """A valid token should render the HTML confirmation page and suppress the email."""
        token = _make_unsubscribe_token("browser@example.com")
        client = _get_client()
        resp = client.get(
            f"/api/v1/scheduler/email-events/unsubscribe/{token}",
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Unsubscribed" in resp.text
        assert "successfully unsubscribed" in resp.text.lower()
        mock_add_sup.assert_called_once()
        assert mock_add_sup.call_args.kwargs["reason"] == "User unsubscribed via browser link"

    @patch(f"{_EMAIL_EVENTS}._check_rate_limit", new_callable=AsyncMock)
    @patch(f"{_EMAIL_EVENTS}._get_unsubscribe_secret", return_value=_TEST_SECRET)
    def test_invalid_token_returns_400(self, mock_secret, mock_rate_limit):
        """An invalid token should return 400, not an HTML page."""
        client = _get_client()
        resp = client.get(
            "/api/v1/scheduler/email-events/unsubscribe/totally.invalid",
        )
        assert resp.status_code == 400


# =============================================================================
# GET /email-events/suppressions — List Suppressions (Admin)
# =============================================================================

class TestListSuppressions:
    """GET /api/v1/scheduler/email-events/suppressions."""

    @patch(f"{_EMAIL_EVENTS}._audit_log")
    @patch(f"{_EMAIL_EVENTS}._get_org_id", return_value=1)
    @patch(f"{_EMAIL_EVENTS}.get_current_user", new_callable=AsyncMock)
    def test_lists_suppressions_for_org(self, mock_auth, mock_org, mock_audit, admin_user):
        """Admin should see suppression list for their org."""
        mock_auth.return_value = admin_user

        mock_suppression = MockSuppression(
            id=42,
            email="bounced@example.com",
            reason="hard bounce",
            event_type="bounce",
        )

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_suppression]

        with patch(f"{_EMAIL_EVENTS}.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.query.return_value = mock_query
            mock_get_db.return_value = mock_db

            client = _get_client()
            resp = client.get(
                "/api/v1/scheduler/email-events/suppressions",
                headers={"Authorization": "Bearer test-token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "suppressions" in data
        assert data["total"] >= 0

    def test_list_suppressions_no_auth_fails(self):
        """Unauthenticated requests to suppressions list should fail."""
        client = _get_client()
        resp = client.get("/api/v1/scheduler/email-events/suppressions")
        assert resp.status_code in (401, 403, 500)


# =============================================================================
# DELETE /email-events/suppressions/{email} — Remove Suppression (Admin)
# =============================================================================

class TestRemoveSuppression:
    """DELETE /api/v1/scheduler/email-events/suppressions/{email}."""

    @patch(f"{_EMAIL_EVENTS}._audit_log")
    @patch(f"{_EMAIL_EVENTS}.remove_email_suppression", return_value=True)
    @patch(f"{_EMAIL_EVENTS}._get_org_id", return_value=1)
    @patch(f"{_EMAIL_EVENTS}.get_current_user", new_callable=AsyncMock)
    def test_remove_existing_suppression(
        self, mock_auth, mock_org, mock_remove, mock_audit, admin_user
    ):
        """Removing an existing suppressed email should return success=True."""
        mock_auth.return_value = admin_user

        client = _get_client()
        resp = client.delete(
            "/api/v1/scheduler/email-events/suppressions/bounced@example.com",
            headers={"Authorization": "Bearer test-token"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "removed" in data["message"].lower()
        mock_remove.assert_called_once()
        call_args = mock_remove.call_args
        assert call_args[0][0] == "bounced@example.com"  # positional: email
        assert "db" in call_args.kwargs                   # keyword: db session
        mock_audit.assert_called_once()

    @patch(f"{_EMAIL_EVENTS}._audit_log")
    @patch(f"{_EMAIL_EVENTS}.remove_email_suppression", return_value=False)
    @patch(f"{_EMAIL_EVENTS}._get_org_id", return_value=1)
    @patch(f"{_EMAIL_EVENTS}.get_current_user", new_callable=AsyncMock)
    def test_remove_nonexistent_suppression(
        self, mock_auth, mock_org, mock_remove, mock_audit, admin_user
    ):
        """Removing a non-suppressed email should return success=False."""
        mock_auth.return_value = admin_user

        client = _get_client()
        resp = client.delete(
            "/api/v1/scheduler/email-events/suppressions/clean@example.com",
            headers={"Authorization": "Bearer test-token"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not suppressed" in data["message"].lower()
        mock_audit.assert_not_called()


# =============================================================================
# Org-ID Resolution Unit Tests
# =============================================================================

class TestOrgIdResolution:
    """Unit tests for _resolve_org_id_for_email helper."""

    def test_resolves_org_from_appointment(self):
        """Should find org_id from the most recent appointment matching the email."""
        mock_db = MagicMock()
        mock_row = MagicMock()
        mock_row.organization_id = 42

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_row
        mock_db.query.return_value = mock_query

        with patch(f"{_EMAIL_EVENTS}.Appointment", create=True) as mock_appt:
            mock_appt.organization_id = MagicMock()
            mock_appt.attendee_email = MagicMock()
            mock_appt.created_at = MagicMock()

            from routes.scheduler.email_events import _resolve_org_id_for_email
            result = _resolve_org_id_for_email("Test@Example.COM", mock_db)

        assert result == 42

    def test_returns_none_for_empty_email(self):
        """Empty email should return None without querying."""
        mock_db = MagicMock()

        from routes.scheduler.email_events import _resolve_org_id_for_email
        result = _resolve_org_id_for_email("", mock_db)

        assert result is None
        mock_db.query.assert_not_called()

    def test_returns_none_for_no_match(self):
        """Unknown email with no matching appointment should return None."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with patch(f"{_EMAIL_EVENTS}.Appointment", create=True) as mock_appt:
            mock_appt.organization_id = MagicMock()
            mock_appt.attendee_email = MagicMock()
            mock_appt.created_at = MagicMock()

            from routes.scheduler.email_events import _resolve_org_id_for_email
            result = _resolve_org_id_for_email("nobody@example.com", mock_db)

        assert result is None


# =============================================================================
# Duplicate Event Processing (Upsert Behavior)
# =============================================================================

class TestDuplicateEventProcessing:
    """Verify that processing the same bounce email twice updates rather than errors."""

    @patch(f"{_EMAIL_EVENTS}._check_rate_limit", new_callable=AsyncMock)
    @patch(f"{_EMAIL_EVENTS}._resolve_org_id_for_email", return_value=1)
    @patch(f"{_EMAIL_EVENTS}._SENDGRID_WEBHOOK_KEY", None)
    def test_duplicate_bounce_events_both_processed(
        self, mock_resolve, mock_rate_limit
    ):
        """Sending the same bounce email twice should process both (upsert in add_email_suppression)."""
        # Patch add_email_suppression to track calls without touching DB
        with patch(f"{_EMAIL_EVENTS}.add_email_suppression") as mock_add:
            client = _get_client()
            events = [
                {"event": "bounce", "email": "dup@example.com", "reason": "550 unknown"},
                {"event": "bounce", "email": "dup@example.com", "reason": "550 unknown retry"},
            ]
            resp = client.post(
                "/api/v1/scheduler/email-events/sendgrid",
                json=events,
            )
            assert resp.status_code == 200
            assert resp.json()["processed"] == 2
            assert mock_add.call_count == 2
