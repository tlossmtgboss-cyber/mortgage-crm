"""
Integration tests for webhook delivery reliability.
Tests retry logic, dead-letter handling, and health checks.

Tests the scheduler_webhook_service module which provides:
  - Exponential backoff retry (3 attempts, 2s/4s/8s)
  - Dead-letter queue for permanently failed deliveries
  - Admin notifications for dead-lettered webhooks
  - Health check monitoring (healthy/degraded/unhealthy/inactive)
  - Manual retry of dead-lettered deliveries
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
import asyncio
import json
import httpx


# ---------------------------------------------------------------------------
# Helpers — lightweight stand-ins for ORM models so tests don't need a live DB
# ---------------------------------------------------------------------------

class FakeDeliveryLog:
    """In-memory stand-in for WebhookDeliveryLog."""

    _next_id = 1

    def __init__(self, **kwargs):
        self.id = FakeDeliveryLog._next_id
        FakeDeliveryLog._next_id += 1
        self.subscription_id = kwargs.get("subscription_id")
        self.event_type = kwargs.get("event_type", "appointment.created")
        self.payload = kwargs.get("payload", {})
        self.status = kwargs.get("status", "pending")
        self.attempt_number = kwargs.get("attempt_number", 0)
        self.max_attempts = kwargs.get("max_attempts", 3)
        self.response_code = kwargs.get("response_code")
        self.response_body = kwargs.get("response_body")
        self.response_time_ms = kwargs.get("response_time_ms")
        self.error_message = kwargs.get("error_message")
        self.next_retry_at = kwargs.get("next_retry_at")
        self.dead_letter_at = kwargs.get("dead_letter_at")
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
        self.delivered_at = kwargs.get("delivered_at")
        self.subscription = kwargs.get("subscription")


class FakeSubscription:
    """In-memory stand-in for WebhookSubscription."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.name = kwargs.get("name", "Test Webhook")
        self.url = kwargs.get("url", "https://example.com/webhook")
        self.secret = kwargs.get("secret", "test-secret-key")
        self.events = kwargs.get("events", ["appointment.created"])
        self.headers = kwargs.get("headers", {})
        self.retry_count = kwargs.get("retry_count", 3)
        self.timeout_seconds = kwargs.get("timeout_seconds", 30)
        self.is_active = kwargs.get("is_active", True)
        self.success_count = kwargs.get("success_count", 0)
        self.failure_count = kwargs.get("failure_count", 0)
        self.last_triggered_at = kwargs.get("last_triggered_at")
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
        self.updated_at = kwargs.get("updated_at", datetime.now(timezone.utc))
        self.delivery_logs = kwargs.get("delivery_logs", [])


class FakeSession:
    """Minimal mock of SQLAlchemy Session for unit-level webhook tests."""

    def __init__(self):
        self.added = []
        self.deleted = []
        self.committed = False
        self.flushed = False
        self.rolled_back = False
        self._query_results = []

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def flush(self):
        self.flushed = True

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def refresh(self, obj):
        pass

    def query(self, model):
        return FakeQuery(self._query_results)


class FakeQuery:
    """Chainable fake query for simple tests."""

    def __init__(self, results):
        self._results = results

    def filter(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, n):
        return self

    def limit(self, n):
        return self

    def count(self):
        return len(self._results)

    def first(self):
        return self._results[0] if self._results else None

    def all(self):
        return self._results


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_subscription():
    return FakeSubscription(
        id=10,
        organization_id=1,
        name="CRM Integration Webhook",
        url="https://crm.example.com/hooks/appointments",
        secret="s3cr3t-hmac-key",
        events=["appointment.created", "appointment.cancelled"],
        success_count=0,
        failure_count=0,
    )


@pytest.fixture
def sample_payload():
    return {
        "id": "evt-001",
        "event_type": "appointment.created",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "organization_id": 1,
        "data": {
            "appointment_id": 42,
            "title": "Initial consultation",
            "borrower": {"name": "Jane Doe", "email": "jane@example.com"},
            "scheduled_start": "2026-03-20T14:00:00Z",
        },
    }


@pytest.fixture
def fake_db():
    return FakeSession()


# ---------------------------------------------------------------------------
# TestWebhookRetryLogic
# ---------------------------------------------------------------------------

class TestWebhookRetryLogic:
    """Test exponential backoff retry on webhook delivery failure."""

    @pytest.mark.asyncio
    async def test_retries_on_timeout(self, sample_subscription, sample_payload, fake_db):
        """Should retry up to 3 times on timeout, then mark as failed."""
        from services.scheduler_webhook_service import _deliver_to_subscription

        # Patch WebhookDeliveryLog constructor to return our fake
        delivery_instance = FakeDeliveryLog(subscription_id=sample_subscription.id)

        with patch(
            "services.scheduler_webhook_service.WebhookDeliveryLog",
            return_value=delivery_instance,
        ), patch(
            "httpx.AsyncClient",
        ) as mock_client_cls, patch(
            "asyncio.sleep", new_callable=AsyncMock,
        ) as mock_sleep:
            # Every request raises TimeoutException
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("timed out")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Patch dead-letter notification to avoid model imports
            with patch(
                "services.scheduler_webhook_service._create_dead_letter_notification"
            ):
                result = await _deliver_to_subscription(
                    fake_db, sample_subscription, sample_payload,
                    _synchronous=True,
                )

            # Verify 3 POST attempts were made
            assert mock_client.post.call_count == 3

            # Delivery should be marked failed
            assert result.status == "failed"
            assert "Timeout" in (result.error_message or "")

            # Subscription failure_count incremented
            assert sample_subscription.failure_count == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff(self, sample_subscription, sample_payload, fake_db):
        """Retry delays should follow exponential backoff: 2s, 4s between attempts."""
        from services.scheduler_webhook_service import _deliver_to_subscription

        delivery_instance = FakeDeliveryLog(subscription_id=sample_subscription.id)

        with patch(
            "services.scheduler_webhook_service.WebhookDeliveryLog",
            return_value=delivery_instance,
        ), patch(
            "httpx.AsyncClient",
        ) as mock_client_cls, patch(
            "asyncio.sleep", new_callable=AsyncMock,
        ) as mock_sleep:
            # All attempts fail with non-2xx
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch(
                "services.scheduler_webhook_service._create_dead_letter_notification"
            ):
                await _deliver_to_subscription(
                    fake_db, sample_subscription, sample_payload,
                    _synchronous=True,
                )

            # asyncio.sleep called twice: after attempt 1 and after attempt 2
            # (no sleep after the final attempt 3)
            assert mock_sleep.call_count == 2
            delays = [call.args[0] for call in mock_sleep.call_args_list]
            # _BASE_BACKOFF_SECONDS=2: 2*(2^0)=2, 2*(2^1)=4
            assert delays == [2, 4]

    @pytest.mark.asyncio
    async def test_marks_failed_after_max_retries(
        self, sample_subscription, sample_payload, fake_db,
    ):
        """After 3 failed attempts, delivery should be marked as failed with dead_letter_at set."""
        from services.scheduler_webhook_service import _deliver_to_subscription

        delivery_instance = FakeDeliveryLog(subscription_id=sample_subscription.id)

        with patch(
            "services.scheduler_webhook_service.WebhookDeliveryLog",
            return_value=delivery_instance,
        ), patch(
            "httpx.AsyncClient",
        ) as mock_client_cls, patch(
            "asyncio.sleep", new_callable=AsyncMock,
        ):
            mock_response = MagicMock()
            mock_response.status_code = 503
            mock_response.text = "Service Unavailable"
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch(
                "services.scheduler_webhook_service._create_dead_letter_notification"
            ):
                result = await _deliver_to_subscription(
                    fake_db, sample_subscription, sample_payload,
                    _synchronous=True,
                )

            assert result.status == "failed"
            assert result.dead_letter_at is not None
            assert result.attempt_number == 3
            assert result.error_message is not None
            assert "503" in result.error_message

    @pytest.mark.asyncio
    async def test_successful_delivery_no_retry(
        self, sample_subscription, sample_payload, fake_db,
    ):
        """Successful delivery on first attempt should not trigger retry or sleep."""
        from services.scheduler_webhook_service import _deliver_to_subscription

        delivery_instance = FakeDeliveryLog(subscription_id=sample_subscription.id)

        with patch(
            "services.scheduler_webhook_service.WebhookDeliveryLog",
            return_value=delivery_instance,
        ), patch(
            "httpx.AsyncClient",
        ) as mock_client_cls, patch(
            "asyncio.sleep", new_callable=AsyncMock,
        ) as mock_sleep:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = '{"ok": true}'
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await _deliver_to_subscription(
                fake_db, sample_subscription, sample_payload,
                _synchronous=True,
            )

            # Only 1 POST call, no sleep
            assert mock_client.post.call_count == 1
            assert mock_sleep.call_count == 0

            assert result.status == "success"
            assert result.delivered_at is not None
            assert result.dead_letter_at is None
            assert sample_subscription.success_count == 1

    @pytest.mark.asyncio
    async def test_success_after_transient_failure(
        self, sample_subscription, sample_payload, fake_db,
    ):
        """Delivery that fails then succeeds on retry should be marked success."""
        from services.scheduler_webhook_service import _deliver_to_subscription

        delivery_instance = FakeDeliveryLog(subscription_id=sample_subscription.id)

        with patch(
            "services.scheduler_webhook_service.WebhookDeliveryLog",
            return_value=delivery_instance,
        ), patch(
            "httpx.AsyncClient",
        ) as mock_client_cls, patch(
            "asyncio.sleep", new_callable=AsyncMock,
        ):
            fail_response = MagicMock()
            fail_response.status_code = 502
            fail_response.text = "Bad Gateway"

            ok_response = MagicMock()
            ok_response.status_code = 200
            ok_response.text = '{"received": true}'

            mock_client = AsyncMock()
            # First call fails, second succeeds
            mock_client.post.side_effect = [fail_response, ok_response]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await _deliver_to_subscription(
                fake_db, sample_subscription, sample_payload,
                _synchronous=True,
            )

            assert result.status == "success"
            assert result.delivered_at is not None
            assert result.dead_letter_at is None
            assert mock_client.post.call_count == 2
            assert sample_subscription.success_count == 1


# ---------------------------------------------------------------------------
# TestDeadLetterHandling
# ---------------------------------------------------------------------------

class TestDeadLetterHandling:
    """Test dead-letter queue for permanently failed webhooks."""

    @pytest.mark.asyncio
    async def test_failed_webhook_enters_dead_letter(
        self, sample_subscription, sample_payload, fake_db,
    ):
        """Failed webhook should be recorded with dead_letter_at timestamp."""
        from services.scheduler_webhook_service import _deliver_to_subscription

        delivery_instance = FakeDeliveryLog(subscription_id=sample_subscription.id)

        with patch(
            "services.scheduler_webhook_service.WebhookDeliveryLog",
            return_value=delivery_instance,
        ), patch(
            "httpx.AsyncClient",
        ) as mock_client_cls, patch(
            "asyncio.sleep", new_callable=AsyncMock,
        ), patch(
            "services.scheduler_webhook_service._create_dead_letter_notification"
        ) as mock_notify:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await _deliver_to_subscription(
                fake_db, sample_subscription, sample_payload,
                _synchronous=True,
            )

            assert result.status == "failed"
            assert result.dead_letter_at is not None
            assert "Connection refused" in result.error_message

            # Notification function should have been called once
            mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_manual_retry_from_dead_letter(self):
        """Admin should be able to manually retry a dead-letter webhook."""
        from services.scheduler_webhook_service import retry_failed_webhook

        subscription = FakeSubscription(id=5, is_active=True)
        stored_payload = {
            "id": "evt-retry-001",
            "event_type": "appointment.cancelled",
            "data": {"appointment_id": 99},
        }

        delivery = FakeDeliveryLog(
            subscription_id=5,
            event_type="appointment.cancelled",
            payload=stored_payload,
            status="failed",
            attempt_number=3,
            error_message="HTTP 500",
            dead_letter_at=datetime.now(timezone.utc),
        )
        delivery.subscription = subscription

        db = FakeSession()
        db._query_results = [delivery]

        # Patch _deliver_to_subscription to simulate success on retry
        retry_result = FakeDeliveryLog(
            subscription_id=5,
            status="success",
            attempt_number=1,
            response_code=200,
            response_body='{"ok":true}',
            response_time_ms=150,
            delivered_at=datetime.now(timezone.utc),
        )

        with patch(
            "services.scheduler_webhook_service._deliver_to_subscription",
            new_callable=AsyncMock,
            return_value=retry_result,
        ):
            # query().filter().first() needs to return the right objects:
            # first call returns the delivery, second call returns the subscription
            first_call = True

            original_query = db.query

            def patched_query(model):
                nonlocal first_call
                fq = FakeQuery([delivery] if first_call else [subscription])
                first_call = False
                return fq

            db.query = patched_query

            result = await retry_failed_webhook(db, delivery_id=delivery.id, organization_id=1)

            # The delivery should reflect the successful retry result
            assert result.status == "success"
            assert result.response_code == 200

    @pytest.mark.asyncio
    async def test_dead_letter_notification_created(
        self, sample_subscription, sample_payload, fake_db,
    ):
        """Admin should be notified when webhooks enter dead-letter state."""
        from services.scheduler_webhook_service import _deliver_to_subscription

        delivery_instance = FakeDeliveryLog(subscription_id=sample_subscription.id)

        with patch(
            "services.scheduler_webhook_service.WebhookDeliveryLog",
            return_value=delivery_instance,
        ), patch(
            "httpx.AsyncClient",
        ) as mock_client_cls, patch(
            "asyncio.sleep", new_callable=AsyncMock,
        ), patch(
            "services.scheduler_webhook_service._create_dead_letter_notification"
        ) as mock_notify:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Server Error"
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await _deliver_to_subscription(
                fake_db, sample_subscription, sample_payload,
                _synchronous=True,
            )

            # _create_dead_letter_notification called with correct args
            mock_notify.assert_called_once()
            call_kwargs = mock_notify.call_args
            assert call_kwargs[1]["subscription"] is sample_subscription
            assert call_kwargs[1]["event_type"] == "appointment.created"
            assert "500" in call_kwargs[1]["last_error"]


# ---------------------------------------------------------------------------
# TestWebhookHealthCheck
# ---------------------------------------------------------------------------

class TestWebhookHealthCheck:
    """Test webhook health monitoring via check_webhook_health()."""

    @pytest.mark.asyncio
    async def test_healthy_webhook_detected(self):
        """Webhook with >= 90% success rate should be marked healthy."""
        from services.scheduler_webhook_service import check_webhook_health

        subscription = FakeSubscription(id=1, success_count=50, failure_count=2)
        now = datetime.now(timezone.utc)

        # 10 deliveries: 9 success, 1 failed = 90%
        deliveries = []
        for i in range(9):
            d = FakeDeliveryLog(
                status="success",
                created_at=now - timedelta(hours=i),
            )
            deliveries.append(d)
        deliveries.append(FakeDeliveryLog(
            status="failed",
            created_at=now - timedelta(hours=10),
        ))

        db = FakeSession()

        # query(WebhookSubscription) -> subscription,
        # query(WebhookDeliveryLog) -> deliveries
        call_count = [0]
        def patched_query(model):
            call_count[0] += 1
            if call_count[0] == 1:
                return FakeQuery([subscription])
            return FakeQuery(deliveries)

        db.query = patched_query

        result = await check_webhook_health(db, subscription_id=1, organization_id=1, window_hours=24)

        assert result["health_status"] == "healthy"
        assert result["success_rate"] == 90.0
        assert result["total_deliveries"] == 10
        assert result["successful"] == 9
        assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_degraded_webhook_detected(self):
        """Webhook with 50-89% success rate should be marked degraded."""
        from services.scheduler_webhook_service import check_webhook_health

        subscription = FakeSubscription(id=2)
        now = datetime.now(timezone.utc)

        # 10 deliveries: 6 success, 4 failed = 60%
        deliveries = []
        for i in range(6):
            deliveries.append(FakeDeliveryLog(
                status="success",
                created_at=now - timedelta(hours=i),
            ))
        for i in range(4):
            deliveries.append(FakeDeliveryLog(
                status="failed",
                created_at=now - timedelta(hours=6 + i),
            ))

        db = FakeSession()
        call_count = [0]
        def patched_query(model):
            call_count[0] += 1
            if call_count[0] == 1:
                return FakeQuery([subscription])
            return FakeQuery(deliveries)

        db.query = patched_query

        result = await check_webhook_health(db, subscription_id=2, organization_id=1, window_hours=24)

        assert result["health_status"] == "degraded"
        assert result["success_rate"] == 60.0
        assert result["successful"] == 6
        assert result["failed"] == 4

    @pytest.mark.asyncio
    async def test_unhealthy_webhook_detected(self):
        """Webhook with < 50% success rate should be marked unhealthy."""
        from services.scheduler_webhook_service import check_webhook_health

        subscription = FakeSubscription(id=3)
        now = datetime.now(timezone.utc)

        # 10 deliveries: 3 success, 7 failed = 30%
        deliveries = []
        for i in range(3):
            deliveries.append(FakeDeliveryLog(
                status="success",
                created_at=now - timedelta(hours=i),
            ))
        for i in range(7):
            deliveries.append(FakeDeliveryLog(
                status="failed",
                created_at=now - timedelta(hours=3 + i),
            ))

        db = FakeSession()
        call_count = [0]
        def patched_query(model):
            call_count[0] += 1
            if call_count[0] == 1:
                return FakeQuery([subscription])
            return FakeQuery(deliveries)

        db.query = patched_query

        result = await check_webhook_health(db, subscription_id=3, organization_id=1, window_hours=24)

        assert result["health_status"] == "unhealthy"
        assert result["success_rate"] == 30.0
        assert result["failed"] == 7

    @pytest.mark.asyncio
    async def test_inactive_webhook_no_deliveries(self):
        """Webhook with no recent deliveries should be marked inactive."""
        from services.scheduler_webhook_service import check_webhook_health

        subscription = FakeSubscription(id=4)

        db = FakeSession()
        call_count = [0]
        def patched_query(model):
            call_count[0] += 1
            if call_count[0] == 1:
                return FakeQuery([subscription])
            return FakeQuery([])  # no deliveries

        db.query = patched_query

        result = await check_webhook_health(db, subscription_id=4, organization_id=1, window_hours=24)

        assert result["health_status"] == "inactive"
        assert result["total_deliveries"] == 0
        assert result["success_rate"] is None

    @pytest.mark.asyncio
    async def test_consecutive_failures_counted(self):
        """Health check should report consecutive recent failures."""
        from services.scheduler_webhook_service import check_webhook_health

        subscription = FakeSubscription(id=5)
        now = datetime.now(timezone.utc)

        # Most recent 3 are failures, then a success, then a failure
        deliveries = [
            FakeDeliveryLog(status="failed", created_at=now - timedelta(minutes=5)),
            FakeDeliveryLog(status="failed", created_at=now - timedelta(minutes=10)),
            FakeDeliveryLog(status="failed", created_at=now - timedelta(minutes=15)),
            FakeDeliveryLog(status="success", created_at=now - timedelta(minutes=20)),
            FakeDeliveryLog(status="failed", created_at=now - timedelta(minutes=25)),
        ]

        db = FakeSession()
        call_count = [0]
        def patched_query(model):
            call_count[0] += 1
            if call_count[0] == 1:
                return FakeQuery([subscription])
            return FakeQuery(deliveries)

        db.query = patched_query

        result = await check_webhook_health(db, subscription_id=5, organization_id=1, window_hours=24)

        assert result["consecutive_recent_failures"] == 3
        assert result["health_status"] == "unhealthy"


# ---------------------------------------------------------------------------
# TestPayloadAndSignature
# ---------------------------------------------------------------------------

class TestPayloadAndSignature:
    """Test payload construction and HMAC signature generation."""

    def test_compute_signature_deterministic(self):
        """Same payload + secret should always produce the same signature."""
        from services.scheduler_webhook_service import compute_signature

        payload = b'{"event_type":"appointment.created","data":{"id":1}}'
        secret = "my-secret"

        sig1 = compute_signature(payload, secret)
        sig2 = compute_signature(payload, secret)

        assert sig1 == sig2
        assert len(sig1) == 64  # SHA-256 hex digest length

    def test_compute_signature_varies_with_secret(self):
        """Different secrets should produce different signatures."""
        from services.scheduler_webhook_service import compute_signature

        payload = b'{"event_type":"appointment.created"}'

        sig_a = compute_signature(payload, "secret-a")
        sig_b = compute_signature(payload, "secret-b")

        assert sig_a != sig_b

    def test_build_event_payload_structure(self):
        """Built payload should contain required top-level keys."""
        from services.scheduler_webhook_service import (
            _build_event_payload,
            WebhookEvent,
        )

        data = {"appointment_id": 1, "title": "Test"}
        result = _build_event_payload(
            WebhookEvent.APPOINTMENT_CREATED, data, organization_id=42,
        )

        assert "id" in result
        assert result["event_type"] == "appointment.created"
        assert result["organization_id"] == 42
        assert result["data"] == data
        assert "timestamp" in result


# ---------------------------------------------------------------------------
# TestDispatchWebhook
# ---------------------------------------------------------------------------

class TestDispatchWebhook:
    """Test the top-level dispatch_webhook() orchestration."""

    @pytest.mark.asyncio
    async def test_dispatch_skips_when_no_subscriptions(self):
        """dispatch_webhook returns empty list when no subscriptions match."""
        from services.scheduler_webhook_service import dispatch_webhook, WebhookEvent

        db = FakeSession()
        db._query_results = []  # no subscriptions

        results = await dispatch_webhook(
            event_type=WebhookEvent.APPOINTMENT_CREATED,
            appointment_data={"appointment_id": 1},
            organization_id=1,
            db=db,
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_dispatch_filters_by_event_type(self):
        """Only subscriptions subscribed to the dispatched event should be called."""
        from services.scheduler_webhook_service import dispatch_webhook, WebhookEvent

        sub_match = FakeSubscription(
            id=1, events=["appointment.created"], is_active=True,
        )
        sub_no_match = FakeSubscription(
            id=2, events=["appointment.cancelled"], is_active=True,
        )

        db = FakeSession()
        db._query_results = [sub_match, sub_no_match]

        with patch(
            "services.scheduler_webhook_service._deliver_to_subscription",
            new_callable=AsyncMock,
        ) as mock_deliver:
            mock_delivery_log = FakeDeliveryLog(status="success")
            mock_deliver.return_value = mock_delivery_log

            results = await dispatch_webhook(
                event_type=WebhookEvent.APPOINTMENT_CREATED,
                appointment_data={"appointment_id": 1},
                organization_id=1,
                db=db,
            )

            # Only the matching subscription should be delivered to
            assert mock_deliver.call_count == 1
            delivered_sub = mock_deliver.call_args[0][1]
            assert delivered_sub.id == 1

    @pytest.mark.asyncio
    async def test_dispatch_wildcard_subscription_matches_all(self):
        """A subscription with '*' event should match any dispatched event."""
        from services.scheduler_webhook_service import dispatch_webhook, WebhookEvent

        wildcard_sub = FakeSubscription(id=1, events=["*"], is_active=True)

        db = FakeSession()
        db._query_results = [wildcard_sub]

        with patch(
            "services.scheduler_webhook_service._deliver_to_subscription",
            new_callable=AsyncMock,
            return_value=FakeDeliveryLog(status="success"),
        ) as mock_deliver:
            results = await dispatch_webhook(
                event_type=WebhookEvent.APPOINTMENT_NO_SHOW,
                appointment_data={"appointment_id": 7},
                organization_id=1,
                db=db,
            )

            assert mock_deliver.call_count == 1
            assert len(results) == 1
