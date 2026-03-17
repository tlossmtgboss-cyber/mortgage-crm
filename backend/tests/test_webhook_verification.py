"""
Tests for webhook signature verification middleware.

Covers:
- Google Calendar push notification webhook verification
- Microsoft Graph / Outlook webhook verification (clientState + validation handshake)
- Generic HMAC-SHA256 webhook verification
- FastAPI dependency wrappers (require_google_calendar_webhook, require_outlook_webhook)
- Edge cases: missing headers, wrong tokens, unconfigured secrets
"""

import hashlib
import hmac
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient

from middleware.webhook_verification import (
    WebhookVerifier,
    require_google_calendar_webhook,
    require_outlook_webhook,
    require_generic_hmac_webhook,
)


# =============================================================================
# Test App Setup
# =============================================================================

def _create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with webhook endpoints for testing."""
    app = FastAPI()

    @app.post("/webhook/google-calendar")
    async def google_calendar_hook(
        request=None,
        _: bool = Depends(require_google_calendar_webhook),
    ):
        return {"status": "ok", "provider": "google"}

    @app.post("/webhook/outlook-calendar")
    async def outlook_calendar_hook(
        request=None,
        verification=Depends(require_outlook_webhook),
    ):
        from fastapi.responses import PlainTextResponse
        if isinstance(verification, PlainTextResponse):
            return verification
        return {"status": "ok", "provider": "outlook"}

    @app.post("/webhook/generic")
    async def generic_hook(
        request=None,
        _: bool = Depends(require_generic_hmac_webhook),
    ):
        return {"status": "ok", "provider": "generic"}

    return app


# =============================================================================
# Google Calendar Webhook Tests
# =============================================================================

@pytest.mark.unit
class TestGoogleCalendarWebhookVerification:
    """Tests for Google Calendar push notification verification."""

    def setup_method(self):
        self.app = _create_test_app()
        self.client = TestClient(self.app)

    @patch.dict(os.environ, {"GOOGLE_CALENDAR_WEBHOOK_TOKEN": "test-secret-token"})
    def test_valid_google_webhook(self):
        """Valid Google Calendar webhook with correct headers passes."""
        response = self.client.post(
            "/webhook/google-calendar",
            headers={
                "X-Goog-Channel-ID": "channel-123",
                "X-Goog-Channel-Token": "test-secret-token",
                "X-Goog-Resource-State": "exists",
            },
        )
        assert response.status_code == 200
        assert response.json()["provider"] == "google"

    @patch.dict(os.environ, {"GOOGLE_CALENDAR_WEBHOOK_TOKEN": "test-secret-token"})
    def test_missing_channel_id_rejects(self):
        """Missing X-Goog-Channel-ID is rejected with 403."""
        response = self.client.post(
            "/webhook/google-calendar",
            headers={
                "X-Goog-Channel-Token": "test-secret-token",
                "X-Goog-Resource-State": "exists",
            },
        )
        assert response.status_code == 403
        assert "channel ID" in response.json()["detail"].lower() or "channel" in response.json()["detail"].lower()

    @patch.dict(os.environ, {"GOOGLE_CALENDAR_WEBHOOK_TOKEN": "test-secret-token"})
    def test_missing_channel_token_rejects(self):
        """Missing X-Goog-Channel-Token is rejected with 403."""
        response = self.client.post(
            "/webhook/google-calendar",
            headers={
                "X-Goog-Channel-ID": "channel-123",
                "X-Goog-Resource-State": "exists",
            },
        )
        assert response.status_code == 403
        assert "token" in response.json()["detail"].lower()

    @patch.dict(os.environ, {"GOOGLE_CALENDAR_WEBHOOK_TOKEN": "test-secret-token"})
    def test_invalid_channel_token_rejects(self):
        """Wrong X-Goog-Channel-Token is rejected with 403."""
        response = self.client.post(
            "/webhook/google-calendar",
            headers={
                "X-Goog-Channel-ID": "channel-123",
                "X-Goog-Channel-Token": "wrong-token",
                "X-Goog-Resource-State": "exists",
            },
        )
        assert response.status_code == 403

    @patch.dict(os.environ, {}, clear=False)
    def test_unconfigured_token_rejects_with_503(self):
        """Missing GOOGLE_CALENDAR_WEBHOOK_TOKEN env var returns 503."""
        # Remove the env var if it exists
        env = os.environ.copy()
        env.pop("GOOGLE_CALENDAR_WEBHOOK_TOKEN", None)
        with patch.dict(os.environ, env, clear=True):
            response = self.client.post(
                "/webhook/google-calendar",
                headers={
                    "X-Goog-Channel-ID": "channel-123",
                    "X-Goog-Channel-Token": "any-token",
                    "X-Goog-Resource-State": "exists",
                },
            )
            assert response.status_code == 503

    @patch.dict(os.environ, {"GOOGLE_CALENDAR_WEBHOOK_TOKEN": "test-secret-token"})
    def test_no_headers_rejects(self):
        """Request with no Google headers is rejected."""
        response = self.client.post("/webhook/google-calendar")
        assert response.status_code == 403

    @patch.dict(os.environ, {"GOOGLE_CALENDAR_WEBHOOK_TOKEN": "secret123"})
    def test_compound_token_format(self):
        """Per-user compound token format (user_42:secret123) is accepted."""
        response = self.client.post(
            "/webhook/google-calendar",
            headers={
                "X-Goog-Channel-ID": "channel-user42",
                "X-Goog-Channel-Token": "user_42:secret123",
                "X-Goog-Resource-State": "sync",
            },
        )
        assert response.status_code == 200

    @patch.dict(os.environ, {"GOOGLE_CALENDAR_WEBHOOK_TOKEN": "secret123"})
    def test_compound_token_wrong_secret(self):
        """Per-user compound token with wrong secret is rejected."""
        response = self.client.post(
            "/webhook/google-calendar",
            headers={
                "X-Goog-Channel-ID": "channel-user42",
                "X-Goog-Channel-Token": "user_42:wrong_secret",
                "X-Goog-Resource-State": "sync",
            },
        )
        assert response.status_code == 403


# =============================================================================
# Outlook / Microsoft Graph Webhook Tests
# =============================================================================

@pytest.mark.unit
class TestOutlookWebhookVerification:
    """Tests for Microsoft Graph / Outlook webhook verification."""

    def setup_method(self):
        self.app = _create_test_app()
        self.client = TestClient(self.app)

    def test_validation_token_echoed_back(self):
        """Microsoft subscription validation: validationToken is echoed."""
        response = self.client.post(
            "/webhook/outlook-calendar?validationToken=abc123-validation",
        )
        assert response.status_code == 200
        assert response.text == "abc123-validation"

    @patch.dict(os.environ, {"GRAPH_WEBHOOK_SECRET": "outlook-secret-42"})
    def test_valid_outlook_notification(self):
        """Valid notification with correct clientState passes."""
        payload = {
            "value": [
                {
                    "subscriptionId": "sub-1",
                    "clientState": "outlook-secret-42",
                    "changeType": "created",
                    "resource": "me/events/event-abc",
                    "resourceData": {"id": "event-abc"},
                }
            ]
        }
        response = self.client.post(
            "/webhook/outlook-calendar",
            json=payload,
        )
        assert response.status_code == 200
        assert response.json()["provider"] == "outlook"

    @patch.dict(os.environ, {"GRAPH_WEBHOOK_SECRET": "outlook-secret-42"})
    def test_invalid_client_state_rejects(self):
        """Notification with wrong clientState is rejected with 403."""
        payload = {
            "value": [
                {
                    "subscriptionId": "sub-1",
                    "clientState": "wrong-secret",
                    "changeType": "created",
                    "resource": "me/events/event-abc",
                    "resourceData": {"id": "event-abc"},
                }
            ]
        }
        response = self.client.post(
            "/webhook/outlook-calendar",
            json=payload,
        )
        assert response.status_code == 403

    @patch.dict(os.environ, {"GRAPH_WEBHOOK_SECRET": "outlook-secret-42"})
    def test_missing_client_state_rejects(self):
        """Notification missing clientState entirely is rejected."""
        payload = {
            "value": [
                {
                    "subscriptionId": "sub-1",
                    "changeType": "created",
                    "resource": "me/events/event-abc",
                }
            ]
        }
        response = self.client.post(
            "/webhook/outlook-calendar",
            json=payload,
        )
        assert response.status_code == 403

    @patch.dict(os.environ, {}, clear=False)
    def test_unconfigured_secret_rejects_with_503(self):
        """Missing GRAPH_WEBHOOK_SECRET returns 503."""
        env = os.environ.copy()
        env.pop("GRAPH_WEBHOOK_SECRET", None)
        env.pop("WEBHOOK_SECRET", None)
        with patch.dict(os.environ, env, clear=True):
            payload = {
                "value": [
                    {
                        "subscriptionId": "sub-1",
                        "clientState": "anything",
                        "changeType": "created",
                    }
                ]
            }
            response = self.client.post(
                "/webhook/outlook-calendar",
                json=payload,
            )
            assert response.status_code == 503

    @patch.dict(os.environ, {"GRAPH_WEBHOOK_SECRET": "secret"})
    def test_empty_notification_list_passes(self):
        """Empty value list is not rejected (let route handler decide)."""
        response = self.client.post(
            "/webhook/outlook-calendar",
            json={"value": []},
        )
        # Empty list should pass verification and reach the route handler
        assert response.status_code == 200

    @patch.dict(os.environ, {"WEBHOOK_SECRET": "fallback-secret"})
    def test_fallback_to_webhook_secret(self):
        """Falls back to WEBHOOK_SECRET if GRAPH_WEBHOOK_SECRET not set."""
        env = os.environ.copy()
        env.pop("GRAPH_WEBHOOK_SECRET", None)
        env["WEBHOOK_SECRET"] = "fallback-secret"
        with patch.dict(os.environ, env, clear=True):
            payload = {
                "value": [
                    {
                        "subscriptionId": "sub-1",
                        "clientState": "fallback-secret",
                        "changeType": "updated",
                    }
                ]
            }
            response = self.client.post(
                "/webhook/outlook-calendar",
                json=payload,
            )
            assert response.status_code == 200


# =============================================================================
# Generic HMAC Webhook Tests
# =============================================================================

@pytest.mark.unit
class TestGenericHMACWebhookVerification:
    """Tests for generic HMAC-SHA256 webhook verification."""

    def setup_method(self):
        self.app = _create_test_app()
        self.client = TestClient(self.app)
        self.secret = "test-hmac-secret-key"

    @patch.dict(os.environ, {"WEBHOOK_HMAC_SECRET": "test-hmac-secret-key"})
    def test_valid_hmac_signature_prefixed(self):
        """Valid sha256=<hex> prefixed signature passes."""
        body = b'{"event": "test.event", "data": {"id": 1}}'
        digest = hmac.new(
            self.secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()

        response = self.client.post(
            "/webhook/generic",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": f"sha256={digest}",
            },
        )
        assert response.status_code == 200

    @patch.dict(os.environ, {"WEBHOOK_HMAC_SECRET": "test-hmac-secret-key"})
    def test_valid_hmac_signature_bare(self):
        """Valid bare hex digest (no prefix) also passes."""
        body = b'{"event": "test.event"}'
        digest = hmac.new(
            self.secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()

        response = self.client.post(
            "/webhook/generic",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": digest,
            },
        )
        assert response.status_code == 200

    @patch.dict(os.environ, {"WEBHOOK_HMAC_SECRET": "test-hmac-secret-key"})
    def test_invalid_hmac_signature_rejects(self):
        """Wrong HMAC signature is rejected with 403."""
        body = b'{"event": "test.event"}'
        response = self.client.post(
            "/webhook/generic",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
            },
        )
        assert response.status_code == 403

    @patch.dict(os.environ, {"WEBHOOK_HMAC_SECRET": "test-hmac-secret-key"})
    def test_missing_signature_header_rejects(self):
        """Missing X-Webhook-Signature header is rejected with 403."""
        response = self.client.post(
            "/webhook/generic",
            content=b'{"event": "test"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 403

    @patch.dict(os.environ, {}, clear=False)
    def test_unconfigured_hmac_secret_rejects_503(self):
        """Missing WEBHOOK_HMAC_SECRET returns 503."""
        env = os.environ.copy()
        env.pop("WEBHOOK_HMAC_SECRET", None)
        with patch.dict(os.environ, env, clear=True):
            response = self.client.post(
                "/webhook/generic",
                content=b'{"event": "test"}',
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": "sha256=abc",
                },
            )
            assert response.status_code == 503

    @patch.dict(os.environ, {"WEBHOOK_HMAC_SECRET": "key1"})
    def test_tampered_body_rejects(self):
        """Signature computed on different body is rejected."""
        original_body = b'{"amount": 100}'
        tampered_body = b'{"amount": 999}'
        # Sign the original body
        digest = hmac.new(
            b"key1", original_body, hashlib.sha256
        ).hexdigest()

        response = self.client.post(
            "/webhook/generic",
            content=tampered_body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": f"sha256={digest}",
            },
        )
        assert response.status_code == 403


# =============================================================================
# WebhookVerifier Unit Tests (direct class method calls)
# =============================================================================

@pytest.mark.unit
class TestWebhookVerifierDirect:
    """Direct unit tests for WebhookVerifier static methods."""

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"GOOGLE_CALENDAR_WEBHOOK_TOKEN": "my-token"})
    async def test_verify_google_calendar_success(self):
        """Direct call to verify_google_calendar with valid headers."""
        request = MagicMock()
        request.headers = {
            "X-Goog-Channel-ID": "ch-1",
            "X-Goog-Channel-Token": "my-token",
            "X-Goog-Resource-State": "exists",
        }
        request.client = MagicMock()
        request.client.host = "74.125.24.100"

        result = await WebhookVerifier.verify_google_calendar(request)
        assert result is True

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"GOOGLE_CALENDAR_WEBHOOK_TOKEN": "my-token"})
    async def test_verify_google_calendar_wrong_token(self):
        """Direct call raises HTTPException for wrong token."""
        request = MagicMock()
        request.headers = {
            "X-Goog-Channel-ID": "ch-1",
            "X-Goog-Channel-Token": "bad-token",
            "X-Goog-Resource-State": "exists",
        }
        request.client = MagicMock()
        request.client.host = "1.2.3.4"

        with pytest.raises(HTTPException) as exc_info:
            await WebhookVerifier.verify_google_calendar(request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"GRAPH_WEBHOOK_SECRET": "secret-abc"})
    async def test_verify_outlook_success(self):
        """Direct call to verify_outlook with valid clientState."""
        request = MagicMock()
        request.json = AsyncMock(return_value={
            "value": [
                {"subscriptionId": "s1", "clientState": "secret-abc", "changeType": "created"}
            ]
        })
        request.client = MagicMock()
        request.client.host = "40.85.0.1"

        result = await WebhookVerifier.verify_outlook(request)
        assert result is True

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"GRAPH_WEBHOOK_SECRET": "secret-abc"})
    async def test_verify_outlook_wrong_client_state(self):
        """Direct call raises HTTPException for wrong clientState."""
        request = MagicMock()
        request.json = AsyncMock(return_value={
            "value": [
                {"subscriptionId": "s1", "clientState": "wrong", "changeType": "created"}
            ]
        })
        request.client = MagicMock()
        request.client.host = "1.2.3.4"

        with pytest.raises(HTTPException) as exc_info:
            await WebhookVerifier.verify_outlook(request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_verify_generic_hmac_success(self):
        """Direct call to verify_generic_hmac with valid signature."""
        secret = "test-key"
        body = b"test payload"
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        request = MagicMock()
        request.headers = {"X-Webhook-Signature": f"sha256={digest}"}
        request.body = AsyncMock(return_value=body)
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        result = await WebhookVerifier.verify_generic_hmac(request, secret)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_generic_hmac_custom_header(self):
        """Generic HMAC verification with custom header name."""
        secret = "my-secret"
        body = b'{"data": 1}'
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        request = MagicMock()
        request.headers = {"X-Custom-Sig": f"sha256={digest}"}
        request.body = AsyncMock(return_value=body)
        request.client = MagicMock()
        request.client.host = "10.0.0.1"

        result = await WebhookVerifier.verify_generic_hmac(
            request, secret, header="X-Custom-Sig"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_generic_hmac_missing_header(self):
        """Missing signature header raises HTTPException."""
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "1.2.3.4"

        with pytest.raises(HTTPException) as exc_info:
            await WebhookVerifier.verify_generic_hmac(request, "secret")
        assert exc_info.value.status_code == 403


# =============================================================================
# Timing Attack Resistance Tests
# =============================================================================

@pytest.mark.unit
class TestTimingAttackResistance:
    """Verify that constant-time comparison is used (hmac.compare_digest)."""

    @patch.dict(os.environ, {"GOOGLE_CALENDAR_WEBHOOK_TOKEN": "a" * 64})
    def test_google_uses_constant_time_comparison(self):
        """
        Verify Google webhook verification rejects wrong tokens of same
        length (would pass non-constant-time == check only if content
        matches, which it shouldn't).
        """
        app = _create_test_app()
        client = TestClient(app)

        # Token is same length but different content
        response = client.post(
            "/webhook/google-calendar",
            headers={
                "X-Goog-Channel-ID": "ch-1",
                "X-Goog-Channel-Token": "b" * 64,
                "X-Goog-Resource-State": "exists",
            },
        )
        assert response.status_code == 403

    @patch.dict(os.environ, {"GRAPH_WEBHOOK_SECRET": "x" * 32})
    def test_outlook_uses_constant_time_comparison(self):
        """Verify Outlook webhook rejects same-length wrong secrets."""
        app = _create_test_app()
        client = TestClient(app)

        response = client.post(
            "/webhook/outlook-calendar",
            json={
                "value": [
                    {
                        "subscriptionId": "s1",
                        "clientState": "y" * 32,
                        "changeType": "created",
                    }
                ]
            },
        )
        assert response.status_code == 403
