"""
Tests for scheduler webhook routes.

Covers:
  - POST   /webhooks             Register a new webhook (admin required)
  - GET    /webhooks             List webhooks for the org (admin required)
  - DELETE /webhooks/{id}        Deactivate a webhook (admin required)
  - POST   /webhooks/{id}/test   Send a test event
  - GET    /webhooks/{id}/deliveries  Recent delivery log
  - 401 without auth, 404 for missing webhooks
  - URL validation (HTTPS required)
  - Duplicate URL detection (409)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockUser:
    def __init__(self, id=1, organization_id=1, role="admin", email="admin@test.com"):
        self.id = id
        self.organization_id = organization_id
        self.role = role
        self.permission_role = role
        self.email = email
        self.first_name = "Test"
        self.last_name = "Admin"


class MockWebhookSubscription:
    """Mock WebhookSubscription ORM object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.name = kwargs.get("name", "Test Webhook")
        self.url = kwargs.get("url", "https://example.com/webhook")
        self.events = kwargs.get("events", ["appointment.created"])
        self.is_active = kwargs.get("is_active", True)
        self.success_count = kwargs.get("success_count", 0)
        self.failure_count = kwargs.get("failure_count", 0)
        self.last_triggered_at = kwargs.get("last_triggered_at", None)
        self.created_at = kwargs.get("created_at", datetime(2026, 3, 1, tzinfo=timezone.utc))
        self.updated_at = kwargs.get("updated_at", datetime(2026, 3, 1, tzinfo=timezone.utc))


class MockDeliveryLog:
    """Mock WebhookDeliveryLog ORM object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.subscription_id = kwargs.get("subscription_id", 1)
        self.event_type = kwargs.get("event_type", "appointment.created")
        self.status = kwargs.get("status", "success")
        self.response_code = kwargs.get("response_code", 200)
        self.response_time_ms = kwargs.get("response_time_ms", 150)
        self.error_message = kwargs.get("error_message", None)
        self.attempt_number = kwargs.get("attempt_number", 1)
        self.max_attempts = kwargs.get("max_attempts", 3)
        self.created_at = kwargs.get("created_at", datetime(2026, 3, 1, tzinfo=timezone.utc))
        self.delivered_at = kwargs.get("delivered_at", datetime(2026, 3, 1, tzinfo=timezone.utc))


def _make_db_mock(query_return=None, first_return=None, all_return=None):
    """Build a MagicMock db session with chainable query/filter/first/all."""
    db = MagicMock()
    query_mock = MagicMock()
    query_mock.filter = MagicMock(return_value=query_mock)
    query_mock.order_by = MagicMock(return_value=query_mock)
    query_mock.offset = MagicMock(return_value=query_mock)
    query_mock.limit = MagicMock(return_value=query_mock)
    query_mock.count = MagicMock(return_value=len(all_return) if all_return else 0)
    if first_return is not None:
        query_mock.first = MagicMock(return_value=first_return)
    else:
        query_mock.first = MagicMock(return_value=None)
    if all_return is not None:
        query_mock.all = MagicMock(return_value=all_return)
    else:
        query_mock.all = MagicMock(return_value=[])
    db.query = MagicMock(return_value=query_mock)
    return db


# ---------------------------------------------------------------------------
# Tests: Authentication
# ---------------------------------------------------------------------------

class TestWebhookAuth:
    """Tests for auth enforcement on webhook endpoints."""

    @pytest.mark.asyncio
    async def test_create_webhook_requires_auth(self):
        """POST /webhooks without auth should return 401."""
        from routes.scheduler.webhooks import create_webhook, WebhookRegisterRequest

        body = WebhookRegisterRequest(
            url="https://example.com/hook",
            events=["appointment.created"],
            secret="a_secret_key_at_least_16_chars",
        )

        with patch("routes.scheduler.webhooks.get_current_user",
                    new_callable=AsyncMock,
                    side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await create_webhook(body, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_list_webhooks_requires_auth(self):
        """GET /webhooks without auth should return 401."""
        from routes.scheduler.webhooks import list_webhooks

        with patch("routes.scheduler.webhooks.get_current_user",
                    new_callable=AsyncMock,
                    side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await list_webhooks(MagicMock(), False, MagicMock())
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_create_webhook_requires_admin(self):
        """Non-admin users should get 403."""
        from routes.scheduler.webhooks import create_webhook, WebhookRegisterRequest

        non_admin = MockUser(role="loan_officer")
        body = WebhookRegisterRequest(
            url="https://example.com/hook",
            events=["appointment.created"],
            secret="a_secret_key_at_least_16_chars",
        )

        with patch("routes.scheduler.webhooks.get_current_user",
                    new_callable=AsyncMock, return_value=non_admin):
            with pytest.raises(HTTPException) as exc_info:
                await create_webhook(body, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Tests: Create Webhook
# ---------------------------------------------------------------------------

class TestCreateWebhook:
    """Tests for POST /webhooks."""

    @pytest.mark.asyncio
    async def test_create_rejects_http_url(self):
        """Webhook URLs must be HTTPS (except localhost)."""
        from routes.scheduler.webhooks import create_webhook, WebhookRegisterRequest

        admin = MockUser(role="admin")
        body = WebhookRegisterRequest(
            url="http://insecure-site.com/hook",
            events=["appointment.created"],
            secret="a_secret_key_at_least_16_chars",
        )

        db = _make_db_mock()

        with patch("routes.scheduler.webhooks.get_current_user",
                    new_callable=AsyncMock, return_value=admin):
            with pytest.raises(HTTPException) as exc_info:
                await create_webhook(body, MagicMock(), db)
            assert exc_info.value.status_code == 400
            assert "HTTPS" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_events(self):
        """Invalid event types should return 400."""
        from routes.scheduler.webhooks import create_webhook, WebhookRegisterRequest

        admin = MockUser(role="admin")
        body = WebhookRegisterRequest(
            url="https://example.com/hook",
            events=["totally_fake_event"],
            secret="a_secret_key_at_least_16_chars",
        )

        db = _make_db_mock()

        with patch("routes.scheduler.webhooks.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.webhooks.VALID_EVENTS", {"appointment.created", "appointment.cancelled"}):
            with pytest.raises(HTTPException) as exc_info:
                await create_webhook(body, MagicMock(), db)
            assert exc_info.value.status_code == 400
            assert "Invalid event types" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_duplicate_url_returns_409(self):
        """Duplicate active webhook URL in same org should return 409."""
        from routes.scheduler.webhooks import create_webhook, WebhookRegisterRequest

        admin = MockUser(role="admin")
        body = WebhookRegisterRequest(
            url="https://example.com/hook",
            events=["appointment.created"],
            secret="a_secret_key_at_least_16_chars",
        )

        existing = MockWebhookSubscription(id=5, url="https://example.com/hook")
        db = _make_db_mock(first_return=existing)

        with patch("routes.scheduler.webhooks.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.webhooks.VALID_EVENTS", {"appointment.created"}):
            with pytest.raises(HTTPException) as exc_info:
                await create_webhook(body, MagicMock(), db)
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_happy_path(self):
        """Admin can register a valid webhook successfully."""
        from routes.scheduler.webhooks import create_webhook, WebhookRegisterRequest

        admin = MockUser(role="admin")
        body = WebhookRegisterRequest(
            name="My Webhook",
            url="https://example.com/hook",
            events=["appointment.created"],
            secret="a_secret_key_at_least_16_chars",
        )

        new_sub = MockWebhookSubscription(id=42, name="My Webhook")
        db = _make_db_mock(first_return=None)

        with patch("routes.scheduler.webhooks.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.webhooks.VALID_EVENTS", {"appointment.created"}), \
             patch("routes.scheduler.webhooks.register_webhook",
                    new_callable=AsyncMock, return_value=new_sub), \
             patch("routes.scheduler.webhooks._audit_log"):
            result = await create_webhook(body, MagicMock(), db)

        assert result["status"] == "ok"
        assert result["webhook"]["id"] == 42
        assert result["webhook"]["name"] == "My Webhook"


# ---------------------------------------------------------------------------
# Tests: Delete Webhook
# ---------------------------------------------------------------------------

class TestDeleteWebhook:
    """Tests for DELETE /webhooks/{webhook_id}."""

    @pytest.mark.asyncio
    async def test_delete_not_found_returns_404(self):
        """Deleting a non-existent webhook should return 404."""
        from routes.scheduler.webhooks import delete_webhook

        admin = MockUser(role="admin")
        db = _make_db_mock(first_return=None)

        with patch("routes.scheduler.webhooks.get_current_user",
                    new_callable=AsyncMock, return_value=admin):
            with pytest.raises(HTTPException) as exc_info:
                await delete_webhook(999, MagicMock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_happy_path(self):
        """Admin can deactivate an existing webhook."""
        from routes.scheduler.webhooks import delete_webhook

        admin = MockUser(role="admin")
        sub = MockWebhookSubscription(id=1)
        db = _make_db_mock(first_return=sub)

        with patch("routes.scheduler.webhooks.get_current_user",
                    new_callable=AsyncMock, return_value=admin), \
             patch("routes.scheduler.webhooks._audit_log"):
            result = await delete_webhook(1, MagicMock(), db)

        assert result["status"] == "ok"
        assert sub.is_active is False


# ---------------------------------------------------------------------------
# Tests: Test Webhook & Deliveries
# ---------------------------------------------------------------------------

class TestWebhookTestAndDeliveries:
    """Tests for POST /webhooks/{id}/test and GET /webhooks/{id}/deliveries."""

    @pytest.mark.asyncio
    async def test_test_webhook_not_found(self):
        """Testing a non-existent webhook returns 404."""
        from routes.scheduler.webhooks import test_webhook

        admin = MockUser(role="admin")
        db = _make_db_mock(first_return=None)

        with patch("routes.scheduler.webhooks.get_current_user",
                    new_callable=AsyncMock, return_value=admin):
            with pytest.raises(HTTPException) as exc_info:
                await test_webhook(999, MagicMock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_test_deactivated_webhook_returns_400(self):
        """Testing a deactivated webhook returns 400."""
        from routes.scheduler.webhooks import test_webhook

        admin = MockUser(role="admin")
        sub = MockWebhookSubscription(id=1, is_active=False)
        db = _make_db_mock(first_return=sub)

        with patch("routes.scheduler.webhooks.get_current_user",
                    new_callable=AsyncMock, return_value=admin):
            with pytest.raises(HTTPException) as exc_info:
                await test_webhook(1, MagicMock(), db)
            assert exc_info.value.status_code == 400
            assert "deactivated" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_deliveries_not_found_webhook(self):
        """Listing deliveries for a non-existent webhook returns 404."""
        from routes.scheduler.webhooks import list_deliveries

        admin = MockUser(role="admin")
        db = _make_db_mock(first_return=None)

        with patch("routes.scheduler.webhooks.get_current_user",
                    new_callable=AsyncMock, return_value=admin):
            with pytest.raises(HTTPException) as exc_info:
                await list_deliveries(999, MagicMock(), 50, 0, None, None, db)
            assert exc_info.value.status_code == 404
