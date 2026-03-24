"""
Tests for inbound calendar sync endpoints.

Covers:
  POST /calendar/sync/google/webhook    Google push notification handling
  POST /calendar/sync/outlook/webhook   Outlook change notification handling
  POST /calendar/sync/google/register   Register Google watch channel
  POST /calendar/sync/outlook/register  Register Outlook subscription

Tested scenarios:
  - Valid Google webhook with signed token triggers sync processing
  - Google sync confirmation (resource_state=sync) returns sync_confirmed
  - Invalid/missing Google headers rejected with 400
  - Invalid HMAC channel token rejected with 403
  - Outlook validation token echoed back as text/plain
  - Outlook change notification with valid clientState triggers processing
  - Outlook notification with invalid clientState counted as error
  - Rate limiting: rapid webhook fire returns 429
  - Deduplication: same notification ID twice is deduplicated
  - Google register calls Google Calendar API
  - Outlook register calls Microsoft Graph API
  - Register endpoints reject when calendar not connected
  - Edge case: expired/unknown resource ID
"""

import pytest
import time
import hashlib
import hmac as hmac_mod
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
from collections import OrderedDict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockUser:
    """Lightweight mock for the authenticated user dependency."""
    def __init__(self, id=1, organization_id=1, role="admin", email="lo@test.com"):
        self.id = id
        self.organization_id = organization_id
        self.role = role
        self.permission_role = role
        self.email = email
        self.first_name = "Test"
        self.last_name = "User"


class MockRequest:
    """Lightweight mock for FastAPI Request used by webhook endpoints."""
    def __init__(self, headers=None, query_params=None, body=None, client_host="1.2.3.4"):
        self._headers = headers or {}
        self._query_params = query_params or {}
        self._body = body
        self._client_host = client_host

    @property
    def headers(self):
        return self._headers

    @property
    def query_params(self):
        return self._query_params

    @property
    def url(self):
        mock_url = MagicMock()
        mock_url.path = "/api/v1/scheduler/calendar/sync/google/webhook"
        return mock_url

    @property
    def client(self):
        mock_client = MagicMock()
        mock_client.host = self._client_host
        return mock_client

    async def json(self):
        if self._body is not None:
            return self._body
        raise ValueError("No JSON body")


def _make_signed_token(org_id: int, user_id: int, secret_key: str = "dev-only-calendar-webhook-key") -> str:
    """Create a valid HMAC-signed channel token matching the module's signing logic."""
    signing_key = hashlib.sha256(f"calendar-sync:{secret_key}".encode()).digest()
    payload = f"{org_id}:{user_id}"
    sig = hmac_mod.new(signing_key, payload.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload}:{sig}"


def _make_db_mock():
    """Build a MagicMock db session with chainable query/filter/first/all."""
    db = MagicMock()
    query_mock = MagicMock()
    query_mock.filter = MagicMock(return_value=query_mock)
    query_mock.order_by = MagicMock(return_value=query_mock)
    query_mock.first = MagicMock(return_value=None)
    query_mock.all = MagicMock(return_value=[])
    db.query = MagicMock(return_value=query_mock)
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_dedup_cache():
    """Clear the module-level dedup cache before each test to avoid cross-test pollution."""
    from routes.scheduler.calendar_sync_inbound import _dedup_cache
    _dedup_cache.clear()
    yield
    _dedup_cache.clear()


@pytest.fixture(autouse=True)
def clear_rate_limit_state():
    """Clear in-memory rate limit state before each test."""
    from routes.scheduler._rate_limiting import _memory_rate_limits
    _memory_rate_limits.clear()
    yield
    _memory_rate_limits.clear()


@pytest.fixture
def signed_token():
    """A valid HMAC-signed channel token for org_id=1, user_id=42."""
    return _make_signed_token(1, 42)


@pytest.fixture
def mock_db():
    return _make_db_mock()


# ---------------------------------------------------------------------------
# Tests: Google Calendar Webhook
# ---------------------------------------------------------------------------

class TestGoogleCalendarWebhook:
    """Tests for POST /calendar/sync/google/webhook."""

    @pytest.mark.asyncio
    async def test_sync_confirmation_returns_sync_confirmed(self, mock_db):
        """Google sends resource_state=sync when watch channel is created. Should return sync_confirmed."""
        from routes.scheduler.calendar_sync_inbound import google_calendar_webhook

        request = MockRequest(headers={
            "X-Goog-Channel-ID": "ch-001",
            "X-Goog-Resource-ID": "res-001",
            "X-Goog-Resource-State": "sync",
            "X-Goog-Channel-Token": "irrelevant-for-sync",
        })

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock):
            result = await google_calendar_webhook(request, mock_db)

        assert result["status"] == "sync_confirmed"

    @pytest.mark.asyncio
    async def test_missing_headers_returns_400(self, mock_db):
        """Missing required Google headers should return 400."""
        from routes.scheduler.calendar_sync_inbound import google_calendar_webhook
        from fastapi import HTTPException

        # Missing X-Goog-Channel-ID and X-Goog-Resource-State
        request = MockRequest(headers={})

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await google_calendar_webhook(request, mock_db)
            assert exc_info.value.status_code == 400
            assert "Missing required Google headers" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_channel_token_returns_403(self, mock_db):
        """Invalid HMAC token should be rejected with 403."""
        from routes.scheduler.calendar_sync_inbound import google_calendar_webhook
        from fastapi import HTTPException

        request = MockRequest(headers={
            "X-Goog-Channel-ID": "ch-001",
            "X-Goog-Resource-ID": "res-001",
            "X-Goog-Resource-State": "exists",
            "X-Goog-Message-Number": "1",
            "X-Goog-Channel-Token": "1:42:bad_signature_here",
        })

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await google_calendar_webhook(request, mock_db)
            assert exc_info.value.status_code == 403
            assert "Invalid channel token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_unsigned_legacy_token_rejected(self, mock_db):
        """Legacy unsigned token (org:user without HMAC) should be rejected with 403."""
        from routes.scheduler.calendar_sync_inbound import google_calendar_webhook
        from fastapi import HTTPException

        request = MockRequest(headers={
            "X-Goog-Channel-ID": "ch-001",
            "X-Goog-Resource-ID": "res-001",
            "X-Goog-Resource-State": "exists",
            "X-Goog-Message-Number": "1",
            "X-Goog-Channel-Token": "1:42",  # Two parts = unsigned
        })

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await google_calendar_webhook(request, mock_db)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_valid_webhook_triggers_sync(self, mock_db, signed_token):
        """Valid webhook with signed token should call _process_google_changes and return processed."""
        from routes.scheduler.calendar_sync_inbound import google_calendar_webhook

        request = MockRequest(headers={
            "X-Goog-Channel-ID": "ch-001",
            "X-Goog-Resource-ID": "res-001",
            "X-Goog-Resource-State": "exists",
            "X-Goog-Message-Number": "1",
            "X-Goog-Channel-Token": signed_token,
        })

        mock_sync_result = {"events_processed": 3, "errors": 0}

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock), \
             patch("routes.scheduler.calendar_sync_inbound._process_google_changes",
                   new_callable=AsyncMock, return_value=mock_sync_result):
            result = await google_calendar_webhook(request, mock_db)

        assert result["status"] == "processed"
        assert result["events_processed"] == 3
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_sync_processing_error_returns_200(self, mock_db, signed_token):
        """Processing errors should still return 200 (to prevent Google retries on app errors)."""
        from routes.scheduler.calendar_sync_inbound import google_calendar_webhook

        request = MockRequest(headers={
            "X-Goog-Channel-ID": "ch-001",
            "X-Goog-Resource-ID": "res-001",
            "X-Goog-Resource-State": "exists",
            "X-Goog-Message-Number": "2",
            "X-Goog-Channel-Token": signed_token,
        })

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock), \
             patch("routes.scheduler.calendar_sync_inbound._process_google_changes",
                   new_callable=AsyncMock, side_effect=Exception("Google API timeout")):
            result = await google_calendar_webhook(request, mock_db)

        assert result["status"] == "error"
        assert "Google API timeout" in result["message"]

    @pytest.mark.asyncio
    async def test_unknown_resource_state_ignored(self, mock_db, signed_token):
        """Unknown resource_state values should be acknowledged but ignored."""
        from routes.scheduler.calendar_sync_inbound import google_calendar_webhook

        request = MockRequest(headers={
            "X-Goog-Channel-ID": "ch-001",
            "X-Goog-Resource-ID": "res-001",
            "X-Goog-Resource-State": "unknown_state",
            "X-Goog-Message-Number": "99",
            "X-Goog-Channel-Token": signed_token,
        })

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock):
            result = await google_calendar_webhook(request, mock_db)

        assert result["status"] == "ignored"
        assert "unknown state" in result["reason"]


# ---------------------------------------------------------------------------
# Tests: Outlook Calendar Webhook
# ---------------------------------------------------------------------------

class TestOutlookCalendarWebhook:
    """Tests for POST /calendar/sync/outlook/webhook."""

    @pytest.mark.asyncio
    async def test_validation_token_echoed_as_plaintext(self, mock_db):
        """Microsoft sends validationToken on subscription creation; must echo it as text/plain."""
        from routes.scheduler.calendar_sync_inbound import outlook_calendar_webhook

        token_value = "Validation: Testing-123-ABC"
        request = MockRequest(
            query_params={"validationToken": token_value},
            headers={},
        )

        result = await outlook_calendar_webhook(request, mock_db)

        # Result should be a Response object with text/plain
        assert result.body.decode("utf-8") == token_value
        assert result.media_type == "text/plain"
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_json_body_returns_400(self, mock_db):
        """Non-JSON body should return 400."""
        from routes.scheduler.calendar_sync_inbound import outlook_calendar_webhook
        from fastapi import HTTPException

        request = MockRequest(headers={}, body=None)
        # Override json() to raise
        async def bad_json():
            raise ValueError("Invalid JSON")
        request.json = bad_json

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await outlook_calendar_webhook(request, mock_db)
            assert exc_info.value.status_code == 400
            assert "Invalid JSON" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_empty_notification_list_returns_zero_processed(self, mock_db):
        """Empty value array should return events_processed=0."""
        from routes.scheduler.calendar_sync_inbound import outlook_calendar_webhook

        request = MockRequest(headers={}, body={"value": []})

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock):
            result = await outlook_calendar_webhook(request, mock_db)

        assert result["status"] == "ok"
        assert result["events_processed"] == 0

    @pytest.mark.asyncio
    async def test_invalid_client_state_counted_as_error(self, mock_db):
        """Notification with invalid clientState HMAC should be counted as an error."""
        from routes.scheduler.calendar_sync_inbound import outlook_calendar_webhook

        request = MockRequest(headers={}, body={
            "value": [
                {
                    "resource": "me/events/evt-001",
                    "changeType": "updated",
                    "subscriptionId": "sub-001",
                    "clientState": "1:42:forged_hmac",
                    "id": "notif-001",
                },
            ],
        })

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock):
            result = await outlook_calendar_webhook(request, mock_db)

        assert result["status"] == "processed"
        assert result["errors"] == 1
        assert result["events_processed"] == 0

    @pytest.mark.asyncio
    async def test_valid_notification_triggers_processing(self, mock_db, signed_token):
        """Valid notification with correct clientState should trigger _process_outlook_notification."""
        from routes.scheduler.calendar_sync_inbound import outlook_calendar_webhook

        request = MockRequest(headers={}, body={
            "value": [
                {
                    "resource": "me/events/evt-001",
                    "changeType": "updated",
                    "subscriptionId": "sub-001",
                    "clientState": signed_token,
                    "id": "notif-001",
                },
            ],
        })

        mock_sync_result = {"events_processed": 1, "errors": 0}

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock), \
             patch("routes.scheduler.calendar_sync_inbound._process_outlook_notification",
                   new_callable=AsyncMock, return_value=mock_sync_result):
            result = await outlook_calendar_webhook(request, mock_db)

        assert result["status"] == "processed"
        assert result["events_processed"] == 1
        assert result["errors"] == 0


# ---------------------------------------------------------------------------
# Tests: Deduplication
# ---------------------------------------------------------------------------

class TestWebhookDeduplication:
    """Tests for notification deduplication within the dedup window."""

    @pytest.mark.asyncio
    async def test_duplicate_google_notification_deduplicated(self, mock_db, signed_token):
        """Same Google resource_id + message_number within dedup window should be deduplicated."""
        from routes.scheduler.calendar_sync_inbound import google_calendar_webhook

        headers = {
            "X-Goog-Channel-ID": "ch-dedup",
            "X-Goog-Resource-ID": "res-dedup-001",
            "X-Goog-Resource-State": "exists",
            "X-Goog-Message-Number": "5",
            "X-Goog-Channel-Token": signed_token,
        }

        mock_sync_result = {"events_processed": 1, "errors": 0}

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock), \
             patch("routes.scheduler.calendar_sync_inbound._process_google_changes",
                   new_callable=AsyncMock, return_value=mock_sync_result) as mock_process:

            # First call -- should be processed
            request1 = MockRequest(headers=headers)
            result1 = await google_calendar_webhook(request1, mock_db)
            assert result1["status"] == "processed"

            # Second call with same resource_id + message_number -- should be deduplicated
            request2 = MockRequest(headers=headers)
            result2 = await google_calendar_webhook(request2, mock_db)
            assert result2["status"] == "deduplicated"

            # _process_google_changes should only be called once
            assert mock_process.call_count == 1

    @pytest.mark.asyncio
    async def test_duplicate_outlook_notification_deduplicated(self, mock_db, signed_token):
        """Same Outlook notification ID within dedup window should be deduplicated."""
        from routes.scheduler.calendar_sync_inbound import outlook_calendar_webhook

        notification = {
            "resource": "me/events/evt-dedup",
            "changeType": "updated",
            "subscriptionId": "sub-dedup",
            "clientState": signed_token,
            "id": "notif-dedup-001",
        }

        mock_sync_result = {"events_processed": 1, "errors": 0}

        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit", new_callable=AsyncMock), \
             patch("routes.scheduler.calendar_sync_inbound._process_outlook_notification",
                   new_callable=AsyncMock, return_value=mock_sync_result) as mock_process:

            # First call
            request1 = MockRequest(headers={}, body={"value": [notification]})
            result1 = await outlook_calendar_webhook(request1, mock_db)
            assert result1["events_processed"] == 1

            # Second call with same notification -- should be deduplicated
            request2 = MockRequest(headers={}, body={"value": [notification]})
            result2 = await outlook_calendar_webhook(request2, mock_db)
            assert result2.get("deduplicated", 0) == 1
            assert result2["events_processed"] == 0

            # Processing only called once
            assert mock_process.call_count == 1


# ---------------------------------------------------------------------------
# Tests: Rate Limiting
# ---------------------------------------------------------------------------

class TestWebhookRateLimiting:
    """Tests for webhook rate limiting."""

    @pytest.mark.asyncio
    async def test_rapid_google_webhooks_get_429(self, mock_db, signed_token):
        """Exceeding the per-provider rate limit should return 429."""
        from routes.scheduler.calendar_sync_inbound import google_calendar_webhook
        from fastapi import HTTPException

        # Patch rate limit to very low threshold
        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit",
                   new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=429, detail="Too many requests")):
            request = MockRequest(headers={
                "X-Goog-Channel-ID": "ch-rl",
                "X-Goog-Resource-ID": "res-rl",
                "X-Goog-Resource-State": "exists",
                "X-Goog-Channel-Token": signed_token,
            })
            with pytest.raises(HTTPException) as exc_info:
                await google_calendar_webhook(request, mock_db)
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_rapid_outlook_webhooks_get_429(self, mock_db):
        """Exceeding rate limit on Outlook webhook should return 429."""
        from routes.scheduler.calendar_sync_inbound import outlook_calendar_webhook
        from fastapi import HTTPException

        # Note: validation requests bypass rate limiting; only change notifications
        # are rate limited.
        with patch("routes.scheduler.calendar_sync_inbound._check_rate_limit",
                   new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=429, detail="Too many requests")):
            request = MockRequest(headers={}, body={"value": [{"resource": "me/events/x"}]})
            with pytest.raises(HTTPException) as exc_info:
                await outlook_calendar_webhook(request, mock_db)
            assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# Tests: Register Google Watch Channel
# ---------------------------------------------------------------------------

class TestRegisterGoogleWatch:
    """Tests for POST /calendar/sync/google/register."""

    @pytest.mark.asyncio
    async def test_register_google_watch_happy_path(self, mock_db):
        """Successful Google watch registration returns channel_id and resource_id."""
        from routes.scheduler.calendar_sync_inbound import (
            register_google_watch_channel,
            WatchChannelRegisterRequest,
        )

        user = MockUser(id=42, organization_id=1)
        body = WatchChannelRegisterRequest(calendar_id="primary", ttl_seconds=604800)

        mock_orchestrator = MagicMock()
        mock_orchestrator._get_user_providers.return_value = [
            ("google", {"access_token": "gtoken-abc123"}),
        ]

        mock_google_resp = MagicMock()
        mock_google_resp.status_code = 200
        mock_google_resp.json.return_value = {
            "resourceId": "google-res-001",
            "expiration": "1711900800000",
        }

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_google_resp
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("routes.scheduler.calendar_sync_inbound.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.calendar_sync_inbound._get_org_id", return_value=1), \
             patch("routes.scheduler.calendar_sync_inbound._audit_log"), \
             patch("services.calendar_sync_orchestrator.CalendarSyncOrchestrator",
                   return_value=mock_orchestrator), \
             patch("httpx.AsyncClient", return_value=mock_http_client):
            result = await register_google_watch_channel(body, MagicMock(), mock_db, user)

        assert result["status"] == "registered"
        assert result["resource_id"] == "google-res-001"
        assert "channel_id" in result
        assert "webhook_url" in result

    @pytest.mark.asyncio
    async def test_register_google_watch_no_credentials(self, mock_db):
        """Should return 400 when Google Calendar is not connected."""
        from routes.scheduler.calendar_sync_inbound import (
            register_google_watch_channel,
            WatchChannelRegisterRequest,
        )
        from fastapi import HTTPException

        user = MockUser(id=42, organization_id=1)
        body = WatchChannelRegisterRequest(calendar_id="primary")

        mock_orchestrator = MagicMock()
        mock_orchestrator._get_user_providers.return_value = []  # No providers

        with patch("routes.scheduler.calendar_sync_inbound.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.calendar_sync_inbound._get_org_id", return_value=1), \
             patch("services.calendar_sync_orchestrator.CalendarSyncOrchestrator",
                   return_value=mock_orchestrator):
            with pytest.raises(HTTPException) as exc_info:
                await register_google_watch_channel(body, MagicMock(), mock_db, user)
            assert exc_info.value.status_code == 400
            assert "not connected" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Tests: Register Outlook Subscription
# ---------------------------------------------------------------------------

class TestRegisterOutlookSubscription:
    """Tests for POST /calendar/sync/outlook/register."""

    @pytest.mark.asyncio
    async def test_register_outlook_subscription_happy_path(self, mock_db):
        """Successful Outlook subscription returns subscription_id and expiration."""
        from routes.scheduler.calendar_sync_inbound import (
            register_outlook_subscription,
            OutlookSubscriptionRegisterRequest,
        )

        user = MockUser(id=42, organization_id=1)
        body = OutlookSubscriptionRegisterRequest(expiration_minutes=4230)

        mock_orchestrator = MagicMock()
        mock_orchestrator._get_user_providers.return_value = [
            ("outlook", {"access_token": "ms-token-xyz"}),
        ]

        mock_graph_resp = MagicMock()
        mock_graph_resp.status_code = 201
        mock_graph_resp.json.return_value = {
            "id": "outlook-sub-001",
            "expirationDateTime": "2026-03-26T12:00:00Z",
        }

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_graph_resp
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch("routes.scheduler.calendar_sync_inbound.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.calendar_sync_inbound._get_org_id", return_value=1), \
             patch("routes.scheduler.calendar_sync_inbound._audit_log"), \
             patch("services.calendar_sync_orchestrator.CalendarSyncOrchestrator",
                   return_value=mock_orchestrator), \
             patch("httpx.AsyncClient", return_value=mock_http_client):
            result = await register_outlook_subscription(body, MagicMock(), mock_db, user)

        assert result["status"] == "registered"
        assert result["subscription_id"] == "outlook-sub-001"
        assert result["expiration"] == "2026-03-26T12:00:00Z"
        assert "webhook_url" in result

    @pytest.mark.asyncio
    async def test_register_outlook_no_credentials(self, mock_db):
        """Should return 400 when Outlook is not connected."""
        from routes.scheduler.calendar_sync_inbound import (
            register_outlook_subscription,
            OutlookSubscriptionRegisterRequest,
        )
        from fastapi import HTTPException

        user = MockUser(id=42, organization_id=1)
        body = OutlookSubscriptionRegisterRequest()

        mock_orchestrator = MagicMock()
        mock_orchestrator._get_user_providers.return_value = [
            ("google", {"access_token": "gtoken"}),  # Google but NOT Outlook
        ]

        with patch("routes.scheduler.calendar_sync_inbound.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.calendar_sync_inbound._get_org_id", return_value=1), \
             patch("services.calendar_sync_orchestrator.CalendarSyncOrchestrator",
                   return_value=mock_orchestrator):
            with pytest.raises(HTTPException) as exc_info:
                await register_outlook_subscription(body, MagicMock(), mock_db, user)
            assert exc_info.value.status_code == 400
            assert "not connected" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Tests: Token Signing / Verification
# ---------------------------------------------------------------------------

class TestTokenSigningVerification:
    """Tests for _sign_channel_token and _verify_channel_token."""

    def test_sign_and_verify_roundtrip(self):
        """Signed tokens should verify successfully."""
        from routes.scheduler.calendar_sync_inbound import _sign_channel_token, _verify_channel_token

        token = _sign_channel_token(5, 99)
        org_id, user_id, is_valid = _verify_channel_token(token)

        assert org_id == 5
        assert user_id == 99
        assert is_valid is True

    def test_tampered_signature_rejected(self):
        """Altering the signature part should fail verification."""
        from routes.scheduler.calendar_sync_inbound import _sign_channel_token, _verify_channel_token

        token = _sign_channel_token(5, 99)
        # Tamper with the signature
        parts = token.split(":")
        parts[2] = "0000000000000000"
        tampered = ":".join(parts)

        org_id, user_id, is_valid = _verify_channel_token(tampered)
        assert is_valid is False

    def test_tampered_org_id_rejected(self):
        """Changing the org_id while keeping original signature should fail."""
        from routes.scheduler.calendar_sync_inbound import _sign_channel_token, _verify_channel_token

        token = _sign_channel_token(5, 99)
        parts = token.split(":")
        parts[0] = "999"  # Different org
        tampered = ":".join(parts)

        org_id, user_id, is_valid = _verify_channel_token(tampered)
        assert is_valid is False

    def test_empty_token_rejected(self):
        """Empty or None token should be rejected."""
        from routes.scheduler.calendar_sync_inbound import _verify_channel_token

        org_id, user_id, is_valid = _verify_channel_token("")
        assert is_valid is False

        org_id, user_id, is_valid = _verify_channel_token(None)
        assert is_valid is False

    def test_garbage_token_rejected(self):
        """Non-numeric token values should be rejected."""
        from routes.scheduler.calendar_sync_inbound import _verify_channel_token

        org_id, user_id, is_valid = _verify_channel_token("not:a:token")
        assert is_valid is False
        assert org_id is None


# ---------------------------------------------------------------------------
# Tests: Dedup Cache Internals
# ---------------------------------------------------------------------------

class TestDedupCache:
    """Tests for the internal dedup cache behavior."""

    @pytest.mark.asyncio
    async def test_new_notification_not_duplicate(self):
        """First-seen notification should not be flagged as duplicate."""
        from routes.scheduler.calendar_sync_inbound import _check_webhook_dedup

        is_dup = await _check_webhook_dedup("fresh-key-001")
        assert is_dup is False

    @pytest.mark.asyncio
    async def test_same_key_is_duplicate(self):
        """Same key within dedup window should be flagged as duplicate."""
        from routes.scheduler.calendar_sync_inbound import _check_webhook_dedup

        await _check_webhook_dedup("key-abc")
        is_dup = await _check_webhook_dedup("key-abc")
        assert is_dup is True

    @pytest.mark.asyncio
    async def test_expired_entry_not_duplicate(self):
        """Key seen outside the dedup window should NOT be flagged as duplicate."""
        from routes.scheduler.calendar_sync_inbound import (
            _check_webhook_dedup,
            _dedup_cache,
            _WEBHOOK_DEDUP_WINDOW_SECONDS,
        )

        # Insert a key with a timestamp that is expired
        expired_ts = time.time() - _WEBHOOK_DEDUP_WINDOW_SECONDS - 1
        _dedup_cache["expired-key"] = expired_ts

        # Should not be flagged as duplicate because entry is expired
        is_dup = await _check_webhook_dedup("expired-key")
        assert is_dup is False

    @pytest.mark.asyncio
    async def test_cache_bounded_to_max_entries(self):
        """Dedup cache should evict oldest entries when at capacity."""
        from routes.scheduler.calendar_sync_inbound import (
            _check_webhook_dedup,
            _dedup_cache,
            _MAX_DEDUP_ENTRIES,
        )

        # Fill the cache to capacity
        now = time.time()
        for i in range(_MAX_DEDUP_ENTRIES):
            _dedup_cache[f"fill-{i}"] = now

        # Adding one more should evict the oldest
        await _check_webhook_dedup("overflow-key")
        assert len(_dedup_cache) <= _MAX_DEDUP_ENTRIES
        assert "overflow-key" in _dedup_cache
        # The first entry should have been evicted
        assert "fill-0" not in _dedup_cache
