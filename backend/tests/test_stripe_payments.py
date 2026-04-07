"""
Stripe Payment Processing Test Suite

Comprehensive tests for Stripe webhook handling, signature verification,
event idempotency, subscription lifecycle, and error handling.

Covers:
- Webhook signature verification (valid, invalid, missing, misconfigured, replay)
- Event idempotency (first delivery, duplicate, concurrent)
- Event handling (all subscription lifecycle events + unknowns)
- Error handling (invalid JSON, DB errors, missing fields)
"""

import json
import time
import hmac
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, PropertyMock

import pytest
from fastapi import HTTPException

from routes.stripe_webhook_routes import (
    verify_stripe_webhook,
    is_event_processed,
    record_event,
    mark_event_processed,
    handle_invoice_paid,
    handle_invoice_payment_failed,
    handle_subscription_created,
    handle_subscription_updated,
    handle_subscription_deleted,
    handle_payment_method_attached,
    handle_payment_method_detached,
    EVENT_HANDLERS,
)
from models.billing import (
    OrgSubscription,
    Invoice,
    PaymentMethod,
    StripeEvent,
    SubscriptionStatus,
    InvoiceStatus,
    Plan,
)


# =============================================================================
# HELPERS
# =============================================================================

def _generate_stripe_signature(payload: bytes, secret: str, timestamp: int = None) -> str:
    """Generate a Stripe-Signature header value matching Stripe's v1 scheme."""
    if timestamp is None:
        timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode() + payload
    signature = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def _build_stripe_event(
    event_type: str,
    data_object: dict,
    event_id: str = None,
) -> dict:
    """Build a Stripe event payload dict."""
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex[:24]}",
        "type": event_type,
        "object": "event",
        "api_version": "2023-10-16",
        "created": int(time.time()),
        "data": {
            "object": data_object,
        },
    }


# =============================================================================
# 1. WEBHOOK SIGNATURE VERIFICATION
# =============================================================================

class TestWebhookSignatureVerification:
    """Tests for Stripe webhook signature verification."""

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.os.getenv")
    @patch("routes.stripe_webhook_routes.stripe.Webhook.construct_event")
    def test_valid_signature_accepted(self, mock_construct, mock_getenv):
        """Valid Stripe signature should be accepted and event returned."""
        mock_getenv.return_value = "whsec_test_secret"
        expected_event = {"id": "evt_123", "type": "invoice.paid"}
        mock_construct.return_value = expected_event

        result = verify_stripe_webhook(b'{"test": true}', "t=123,v1=abc")

        assert result == expected_event
        mock_construct.assert_called_once_with(
            b'{"test": true}', "t=123,v1=abc", "whsec_test_secret"
        )

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.os.getenv")
    @patch("routes.stripe_webhook_routes.stripe.Webhook.construct_event")
    def test_invalid_signature_rejected(self, mock_construct, mock_getenv):
        """Invalid signature should raise 401."""
        import stripe as stripe_module

        mock_getenv.return_value = "whsec_test_secret"
        mock_construct.side_effect = stripe_module.error.SignatureVerificationError(
            "Invalid signature", "sig_header"
        )

        with pytest.raises(HTTPException) as exc_info:
            verify_stripe_webhook(b'{"test": true}', "t=123,v1=bad")

        assert exc_info.value.status_code == 401
        assert "Invalid Stripe signature" in exc_info.value.detail

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.os.getenv")
    def test_missing_webhook_secret_returns_503(self, mock_getenv):
        """Missing STRIPE_WEBHOOK_SECRET should return 503 Service Unavailable."""
        mock_getenv.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            verify_stripe_webhook(b'{"test": true}', "t=123,v1=abc")

        assert exc_info.value.status_code == 503
        assert "not configured" in exc_info.value.detail

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.os.getenv")
    @patch("routes.stripe_webhook_routes.stripe.Webhook.construct_event")
    def test_invalid_payload_returns_400(self, mock_construct, mock_getenv):
        """Invalid JSON payload should raise 400."""
        mock_getenv.return_value = "whsec_test_secret"
        mock_construct.side_effect = ValueError("Invalid payload")

        with pytest.raises(HTTPException) as exc_info:
            verify_stripe_webhook(b"not json", "t=123,v1=abc")

        assert exc_info.value.status_code == 400
        assert "Invalid payload" in exc_info.value.detail

    @pytest.mark.unit
    def test_missing_signature_header_returns_400(self, client):
        """Request with no Stripe-Signature header should get 400."""
        response = client.post(
            "/webhooks/stripe",
            content=b'{"id": "evt_123"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert "Missing Stripe-Signature" in response.json()["detail"]

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.os.getenv")
    @patch("routes.stripe_webhook_routes.stripe.Webhook.construct_event")
    def test_replay_attack_old_timestamp_rejected(self, mock_construct, mock_getenv):
        """Stripe SDK rejects stale timestamps via construct_event; verify we propagate 401."""
        import stripe as stripe_module

        mock_getenv.return_value = "whsec_test_secret"
        # Stripe SDK raises SignatureVerificationError for stale timestamps
        mock_construct.side_effect = stripe_module.error.SignatureVerificationError(
            "Timestamp outside the tolerance zone", "sig_header"
        )

        with pytest.raises(HTTPException) as exc_info:
            old_timestamp = int(time.time()) - 600  # 10 minutes old
            sig = f"t={old_timestamp},v1=stale_sig"
            verify_stripe_webhook(b'{"test": true}', sig)

        assert exc_info.value.status_code == 401


# =============================================================================
# 2. EVENT IDEMPOTENCY
# =============================================================================

class TestEventIdempotency:
    """Tests for webhook event deduplication."""

    @pytest.mark.unit
    def test_new_event_not_processed(self, db_session):
        """An event that has never been seen should return False."""
        assert is_event_processed(db_session, "evt_never_seen") is False

    @pytest.mark.unit
    def test_recorded_but_unprocessed_event_returns_false(self, db_session):
        """An event recorded but not yet processed should return False."""
        event = record_event(
            db_session,
            "evt_recorded_not_done",
            "invoice.paid",
            {"id": "evt_recorded_not_done"},
        )
        db_session.flush()
        assert is_event_processed(db_session, "evt_recorded_not_done") is False

    @pytest.mark.unit
    def test_processed_event_returns_true(self, db_session):
        """An event that has been fully processed should return True."""
        event = record_event(
            db_session,
            "evt_already_done",
            "invoice.paid",
            {"id": "evt_already_done"},
        )
        mark_event_processed(db_session, event)
        db_session.flush()

        assert is_event_processed(db_session, "evt_already_done") is True

    @pytest.mark.unit
    def test_record_event_creates_stripe_event_row(self, db_session):
        """record_event should create a StripeEvent with correct fields."""
        event = record_event(
            db_session,
            "evt_audit_row",
            "customer.subscription.created",
            {"id": "evt_audit_row", "type": "customer.subscription.created"},
            organization_id=42,
        )
        db_session.flush()

        assert event.id == "evt_audit_row"
        assert event.event_type == "customer.subscription.created"
        assert event.organization_id == 42
        assert event.processed is False
        assert event.processing_error is None

    @pytest.mark.unit
    def test_mark_event_processed_sets_timestamp(self, db_session):
        """mark_event_processed should set processed=True and processed_at."""
        event = record_event(
            db_session,
            "evt_mark_ts",
            "invoice.paid",
            {"id": "evt_mark_ts"},
        )
        mark_event_processed(db_session, event)
        db_session.flush()

        assert event.processed is True
        assert event.processed_at is not None
        assert event.processing_error is None

    @pytest.mark.unit
    def test_mark_event_processed_with_error(self, db_session):
        """mark_event_processed with error string should record the error."""
        event = record_event(
            db_session,
            "evt_with_error",
            "invoice.paid",
            {"id": "evt_with_error"},
        )
        mark_event_processed(db_session, event, error="subscription not found")
        db_session.flush()

        assert event.processed is True
        assert event.processing_error == "subscription not found"

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.verify_stripe_webhook")
    def test_duplicate_delivery_returns_already_processed(self, mock_verify, client, db_session):
        """Second delivery of same event_id should return already_processed without reprocessing."""
        event_id = "evt_duplicate_test"
        mock_verify.return_value = {
            "id": event_id,
            "type": "invoice.paid",
            "data": {"object": {"id": "in_123", "subscription": None}},
        }

        # First delivery: processes
        resp1 = client.post(
            "/webhooks/stripe",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=sig"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] in ("processed", "ignored")

        # Second delivery with same event_id: should be skipped
        resp2 = client.post(
            "/webhooks/stripe",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=sig"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "already_processed"

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.verify_stripe_webhook")
    def test_concurrent_duplicate_deliveries(self, mock_verify, client, db_session):
        """
        Simulate rapid-fire duplicate deliveries. At most one should process;
        subsequent calls should see already_processed.
        """
        event_id = "evt_concurrent_race"
        mock_verify.return_value = {
            "id": event_id,
            "type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_123", "status": "active"}},
        }

        results = []
        for _ in range(3):
            resp = client.post(
                "/webhooks/stripe",
                content=b'{}',
                headers={"Stripe-Signature": "t=1,v1=sig"},
            )
            results.append(resp.json()["status"])

        # First call processes, rest are already_processed (or ignored for unknown sub)
        process_count = sum(1 for s in results if s not in ("already_processed",))
        already_count = sum(1 for s in results if s == "already_processed")
        assert process_count == 1, f"Expected exactly 1 processing, got statuses: {results}"
        assert already_count == 2


# =============================================================================
# 3. EVENT HANDLING
# =============================================================================

class TestCheckoutSessionCompleted:
    """Tests for checkout.session.completed event (handled via subscription.created)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subscription_created_links_to_org(self, db_session):
        """customer.subscription.created should link subscription to organization."""
        # Set up an org subscription with a customer ID but no subscription ID yet
        plan = Plan(
            id="professional",
            name="Professional",
            price_monthly=199,
        )
        db_session.add(plan)
        db_session.flush()

        org_sub = OrgSubscription(
            organization_id=1,
            plan_id="professional",
            stripe_customer_id="cus_test_123",
            status=SubscriptionStatus.TRIALING,
        )
        db_session.add(org_sub)
        db_session.flush()

        data = {
            "id": "sub_new_123",
            "customer": "cus_test_123",
            "status": "active",
            "current_period_start": int(time.time()),
            "current_period_end": int(time.time()) + 30 * 86400,
            "trial_end": None,
        }

        result = await handle_subscription_created(data, db_session)

        assert result["status"] == "created"
        assert result["subscription_id"] == "sub_new_123"
        assert org_sub.stripe_subscription_id == "sub_new_123"
        assert org_sub.status == SubscriptionStatus.ACTIVE

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subscription_created_already_exists(self, db_session):
        """If subscription already exists, return 'exists' without error."""
        plan = Plan(id="starter", name="Starter", price_monthly=99)
        db_session.add(plan)
        db_session.flush()

        org_sub = OrgSubscription(
            organization_id=1,
            plan_id="starter",
            stripe_customer_id="cus_existing",
            stripe_subscription_id="sub_existing_123",
            status=SubscriptionStatus.ACTIVE,
        )
        db_session.add(org_sub)
        db_session.flush()

        data = {
            "id": "sub_existing_123",
            "customer": "cus_existing",
            "status": "active",
        }

        result = await handle_subscription_created(data, db_session)
        assert result["status"] == "exists"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subscription_created_no_matching_org(self, db_session):
        """If no org matches the customer ID, return organization_not_found."""
        data = {
            "id": "sub_orphan_123",
            "customer": "cus_nonexistent",
            "status": "active",
        }

        result = await handle_subscription_created(data, db_session)
        assert result["status"] == "organization_not_found"


class TestSubscriptionUpdated:
    """Tests for customer.subscription.updated event."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subscription_status_updated(self, db_session):
        """subscription.updated should update status and period dates."""
        plan = Plan(id="pro_upd", name="Professional", price_monthly=199)
        db_session.add(plan)
        db_session.flush()

        org_sub = OrgSubscription(
            organization_id=1,
            plan_id="pro_upd",
            stripe_customer_id="cus_upd",
            stripe_subscription_id="sub_upd_123",
            status=SubscriptionStatus.ACTIVE,
        )
        db_session.add(org_sub)
        db_session.flush()

        now = int(time.time())
        data = {
            "id": "sub_upd_123",
            "status": "past_due",
            "current_period_start": now,
            "current_period_end": now + 30 * 86400,
            "cancel_at_period_end": False,
            "canceled_at": None,
            "items": {"data": []},
        }

        result = await handle_subscription_updated(data, db_session)

        assert result["status"] == "past_due"
        assert org_sub.status == SubscriptionStatus.PAST_DUE
        assert org_sub.current_period_start is not None
        assert org_sub.current_period_end is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subscription_updated_with_cancellation(self, db_session):
        """subscription.updated with cancel_at_period_end should record cancellation."""
        plan = Plan(id="pro_cancel", name="Professional", price_monthly=199)
        db_session.add(plan)
        db_session.flush()

        org_sub = OrgSubscription(
            organization_id=1,
            plan_id="pro_cancel",
            stripe_customer_id="cus_cancel",
            stripe_subscription_id="sub_cancel_123",
            status=SubscriptionStatus.ACTIVE,
        )
        db_session.add(org_sub)
        db_session.flush()

        canceled_ts = int(time.time())
        data = {
            "id": "sub_cancel_123",
            "status": "active",
            "cancel_at_period_end": True,
            "canceled_at": canceled_ts,
            "current_period_start": None,
            "current_period_end": None,
            "items": {"data": []},
        }

        result = await handle_subscription_updated(data, db_session)

        assert org_sub.cancel_at_period_end is True
        assert org_sub.canceled_at is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subscription_updated_not_found(self, db_session):
        """subscription.updated for unknown subscription should return not_found."""
        data = {
            "id": "sub_ghost_999",
            "status": "active",
            "items": {"data": []},
        }

        result = await handle_subscription_updated(data, db_session)
        assert result["status"] == "not_found"


class TestSubscriptionDeleted:
    """Tests for customer.subscription.deleted event."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subscription_deleted_cancels(self, db_session):
        """subscription.deleted should set status to CANCELED."""
        plan = Plan(id="pro_del", name="Professional", price_monthly=199)
        db_session.add(plan)
        db_session.flush()

        org_sub = OrgSubscription(
            organization_id=1,
            plan_id="pro_del",
            stripe_customer_id="cus_del",
            stripe_subscription_id="sub_del_123",
            status=SubscriptionStatus.ACTIVE,
        )
        db_session.add(org_sub)
        db_session.flush()

        data = {"id": "sub_del_123"}

        result = await handle_subscription_deleted(data, db_session)

        assert result["status"] == "canceled"
        assert org_sub.status == SubscriptionStatus.CANCELED
        assert org_sub.canceled_at is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subscription_deleted_not_found(self, db_session):
        """subscription.deleted for unknown subscription should return not_found."""
        data = {"id": "sub_nonexistent"}

        result = await handle_subscription_deleted(data, db_session)
        assert result["status"] == "not_found"


class TestInvoicePaymentFailed:
    """Tests for invoice.payment_failed event."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_payment_failed_sets_past_due(self, db_session):
        """First payment failure should set PAST_DUE and 14-day grace period."""
        plan = Plan(id="pro_fail", name="Professional", price_monthly=199)
        db_session.add(plan)
        db_session.flush()

        org_sub = OrgSubscription(
            organization_id=1,
            plan_id="pro_fail",
            stripe_customer_id="cus_fail",
            stripe_subscription_id="sub_fail_123",
            status=SubscriptionStatus.ACTIVE,
        )
        db_session.add(org_sub)

        invoice = Invoice(
            subscription_id=org_sub.id,
            organization_id=1,
            stripe_invoice_id="in_fail_123",
            invoice_date=datetime.now(timezone.utc).date(),
            status=InvoiceStatus.OPEN,
        )
        db_session.add(invoice)
        db_session.flush()

        data = {
            "id": "in_fail_123",
            "subscription": "sub_fail_123",
            "attempt_count": 1,
            "last_payment_error": {"message": "Card declined"},
        }

        result = await handle_invoice_payment_failed(data, db_session)

        assert result["status"] == "payment_failed"
        assert result["attempt_count"] == 1
        assert org_sub.status == SubscriptionStatus.PAST_DUE
        assert org_sub.grace_period_ends_at is not None
        # Grace period should be approximately 14 days from now
        delta = org_sub.grace_period_ends_at - datetime.now(timezone.utc)
        assert 13 <= delta.days <= 14

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_payment_failed_does_not_extend_grace_on_retry(self, db_session):
        """Subsequent payment failures should NOT extend the grace period."""
        plan = Plan(id="pro_retry", name="Professional", price_monthly=199)
        db_session.add(plan)
        db_session.flush()

        original_grace = datetime.now(timezone.utc) + timedelta(days=10)
        org_sub = OrgSubscription(
            organization_id=1,
            plan_id="pro_retry",
            stripe_customer_id="cus_retry",
            stripe_subscription_id="sub_retry_123",
            status=SubscriptionStatus.PAST_DUE,
            grace_period_ends_at=original_grace,
        )
        db_session.add(org_sub)
        db_session.flush()

        data = {
            "id": "in_retry_123",
            "subscription": "sub_retry_123",
            "attempt_count": 3,
        }

        await handle_invoice_payment_failed(data, db_session)

        # Grace period should remain unchanged
        assert org_sub.grace_period_ends_at == original_grace

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_payment_failed_invoice_metadata_updated(self, db_session):
        """Payment failure should record error details in invoice metadata."""
        plan = Plan(id="pro_meta", name="Professional", price_monthly=199)
        db_session.add(plan)
        db_session.flush()

        org_sub = OrgSubscription(
            organization_id=1,
            plan_id="pro_meta",
            stripe_customer_id="cus_meta",
            stripe_subscription_id="sub_meta_123",
            status=SubscriptionStatus.ACTIVE,
        )
        db_session.add(org_sub)

        invoice = Invoice(
            subscription_id=org_sub.id,
            organization_id=1,
            stripe_invoice_id="in_meta_123",
            invoice_date=datetime.now(timezone.utc).date(),
            status=InvoiceStatus.OPEN,
            meta_data={},
        )
        db_session.add(invoice)
        db_session.flush()

        data = {
            "id": "in_meta_123",
            "subscription": "sub_meta_123",
            "attempt_count": 2,
            "last_payment_error": {"code": "card_declined", "message": "Insufficient funds"},
        }

        await handle_invoice_payment_failed(data, db_session)

        assert invoice.meta_data["attempt_count"] == 2
        assert invoice.meta_data["last_payment_error"]["code"] == "card_declined"


class TestInvoicePaid:
    """Tests for invoice.paid event."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invoice_paid_marks_paid(self, db_session):
        """invoice.paid should update invoice status and amount."""
        plan = Plan(id="pro_paid", name="Professional", price_monthly=199)
        db_session.add(plan)
        db_session.flush()

        org_sub = OrgSubscription(
            organization_id=1,
            plan_id="pro_paid",
            stripe_customer_id="cus_paid",
            stripe_subscription_id="sub_paid_123",
            status=SubscriptionStatus.ACTIVE,
        )
        db_session.add(org_sub)

        invoice = Invoice(
            subscription_id=org_sub.id,
            organization_id=1,
            stripe_invoice_id="in_paid_123",
            invoice_date=datetime.now(timezone.utc).date(),
            status=InvoiceStatus.OPEN,
            amount_due=19900,
        )
        db_session.add(invoice)
        db_session.flush()

        data = {
            "id": "in_paid_123",
            "subscription": "sub_paid_123",
            "amount_paid": 19900,
            "invoice_pdf": "https://stripe.com/invoice.pdf",
            "hosted_invoice_url": "https://stripe.com/hosted",
            "period_start": int(time.time()),
            "period_end": int(time.time()) + 30 * 86400,
        }

        result = await handle_invoice_paid(data, db_session)

        assert result["status"] == "paid"
        assert invoice.status == InvoiceStatus.PAID
        assert invoice.amount_paid == 19900
        assert invoice.amount_due == 0
        assert invoice.invoice_pdf_url == "https://stripe.com/invoice.pdf"
        assert invoice.hosted_invoice_url == "https://stripe.com/hosted"
        assert invoice.paid_at is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invoice_paid_clears_grace_period(self, db_session):
        """Successful payment should clear grace period and restore ACTIVE status."""
        plan = Plan(id="pro_grace", name="Professional", price_monthly=199)
        db_session.add(plan)
        db_session.flush()

        org_sub = OrgSubscription(
            organization_id=1,
            plan_id="pro_grace",
            stripe_customer_id="cus_grace",
            stripe_subscription_id="sub_grace_123",
            status=SubscriptionStatus.PAST_DUE,
            grace_period_ends_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db_session.add(org_sub)
        db_session.flush()

        data = {
            "id": "in_grace_123",
            "subscription": "sub_grace_123",
            "amount_paid": 19900,
            "period_start": int(time.time()),
            "period_end": int(time.time()) + 30 * 86400,
        }

        await handle_invoice_paid(data, db_session)

        assert org_sub.grace_period_ends_at is None
        assert org_sub.status == SubscriptionStatus.ACTIVE

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invoice_paid_unknown_invoice_logs_warning(self, db_session):
        """invoice.paid for unknown invoice should not crash."""
        data = {
            "id": "in_unknown_999",
            "subscription": None,
            "amount_paid": 9900,
        }

        # Should not raise
        result = await handle_invoice_paid(data, db_session)
        assert result["status"] == "paid"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invoice_paid_updates_subscription_period(self, db_session):
        """invoice.paid should update subscription period dates."""
        plan = Plan(id="pro_period", name="Professional", price_monthly=199)
        db_session.add(plan)
        db_session.flush()

        org_sub = OrgSubscription(
            organization_id=1,
            plan_id="pro_period",
            stripe_customer_id="cus_period",
            stripe_subscription_id="sub_period_123",
            status=SubscriptionStatus.ACTIVE,
        )
        db_session.add(org_sub)
        db_session.flush()

        now_ts = int(time.time())
        end_ts = now_ts + 30 * 86400

        data = {
            "id": "in_period_123",
            "subscription": "sub_period_123",
            "amount_paid": 19900,
            "period_start": now_ts,
            "period_end": end_ts,
        }

        await handle_invoice_paid(data, db_session)

        assert org_sub.current_period_start is not None
        assert org_sub.current_period_end is not None
        # Verify timestamps round-trip correctly
        assert abs(org_sub.current_period_start.timestamp() - now_ts) < 2
        assert abs(org_sub.current_period_end.timestamp() - end_ts) < 2


class TestPaymentMethodAttached:
    """Tests for payment_method.attached event."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_payment_method_attached_creates_record(self, db_session):
        """payment_method.attached should create a PaymentMethod row."""
        plan = Plan(id="pro_pm", name="Professional", price_monthly=199)
        db_session.add(plan)
        db_session.flush()

        org_sub = OrgSubscription(
            organization_id=1,
            plan_id="pro_pm",
            stripe_customer_id="cus_pm_123",
            stripe_subscription_id="sub_pm_123",
            status=SubscriptionStatus.ACTIVE,
        )
        db_session.add(org_sub)
        db_session.flush()

        data = {
            "id": "pm_new_456",
            "customer": "cus_pm_123",
            "type": "card",
            "card": {
                "brand": "visa",
                "last4": "4242",
                "exp_month": 12,
                "exp_year": 2028,
            },
        }

        result = await handle_payment_method_attached(data, db_session)
        db_session.flush()

        assert result["status"] == "attached"

        from sqlalchemy import select
        pm = db_session.execute(
            select(PaymentMethod).where(
                PaymentMethod.stripe_payment_method_id == "pm_new_456"
            )
        ).scalar_one_or_none()

        assert pm is not None
        assert pm.card_brand == "visa"
        assert pm.card_last4 == "4242"
        assert pm.card_exp_month == 12
        assert pm.card_exp_year == 2028
        assert pm.organization_id == 1
        assert pm.is_default is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_payment_method_attached_no_customer(self, db_session):
        """payment_method.attached for unknown customer should return customer_not_found."""
        data = {
            "id": "pm_orphan",
            "customer": "cus_nonexistent",
            "type": "card",
            "card": {},
        }

        result = await handle_payment_method_attached(data, db_session)
        assert result["status"] == "customer_not_found"


class TestPaymentMethodDetached:
    """Tests for payment_method.detached event."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_payment_method_detached_deactivates(self, db_session):
        """payment_method.detached should set is_active=False."""
        pm = PaymentMethod(
            organization_id=1,
            stripe_payment_method_id="pm_to_detach",
            stripe_customer_id="cus_detach",
            type="card",
            card_brand="mastercard",
            card_last4="5555",
            is_active=True,
        )
        db_session.add(pm)
        db_session.flush()

        data = {"id": "pm_to_detach"}

        result = await handle_payment_method_detached(data, db_session)

        assert result["status"] == "detached"
        assert pm.is_active is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_payment_method_detached_not_found(self, db_session):
        """payment_method.detached for unknown PM should return not_found."""
        data = {"id": "pm_ghost"}

        result = await handle_payment_method_detached(data, db_session)
        assert result["status"] == "not_found"


class TestUnknownEventType:
    """Tests for unrecognized event types."""

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.verify_stripe_webhook")
    def test_unknown_event_type_returns_200(self, mock_verify, client):
        """Unknown event types should return 200 (don't reject)."""
        mock_verify.return_value = {
            "id": "evt_unknown_type",
            "type": "balance.available",
            "data": {"object": {"available": [{"amount": 100}]}},
        }

        response = client.post(
            "/webhooks/stripe",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=sig"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ignored"
        assert "Unhandled" in body.get("reason", "")

    @pytest.mark.unit
    def test_event_handlers_map_completeness(self):
        """Verify all expected event types have handlers registered."""
        expected_types = {
            "invoice.paid",
            "invoice.payment_failed",
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
            "payment_method.attached",
            "payment_method.detached",
        }
        assert set(EVENT_HANDLERS.keys()) == expected_types


# =============================================================================
# 4. ERROR HANDLING
# =============================================================================

class TestErrorHandling:
    """Tests for error resilience in webhook processing."""

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.verify_stripe_webhook")
    def test_missing_event_id_returns_400(self, mock_verify, client):
        """Event with no id field should return 400."""
        mock_verify.return_value = {
            "id": None,
            "type": "invoice.paid",
            "data": {"object": {}},
        }

        response = client.post(
            "/webhooks/stripe",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=sig"},
        )

        assert response.status_code == 400
        assert "Missing event id or type" in response.json()["detail"]

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.verify_stripe_webhook")
    def test_missing_event_type_returns_400(self, mock_verify, client):
        """Event with no type field should return 400."""
        mock_verify.return_value = {
            "id": "evt_no_type",
            "type": None,
            "data": {"object": {}},
        }

        response = client.post(
            "/webhooks/stripe",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=sig"},
        )

        assert response.status_code == 400

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.verify_stripe_webhook")
    def test_handler_exception_returns_200(self, mock_verify, client):
        """
        Processing error should return 200 to prevent Stripe retries.
        Error should be recorded on the StripeEvent.
        """
        mock_verify.return_value = {
            "id": "evt_handler_crash",
            "type": "invoice.paid",
            "data": {"object": {"id": "in_crash", "subscription": "sub_crash"}},
        }

        # Patch the handler to raise an exception
        original_handler = EVENT_HANDLERS["invoice.paid"]
        async def exploding_handler(data, db):
            raise RuntimeError("Unexpected DB error")

        EVENT_HANDLERS["invoice.paid"] = exploding_handler
        try:
            response = client.post(
                "/webhooks/stripe",
                content=b'{}',
                headers={"Stripe-Signature": "t=1,v1=sig"},
            )
        finally:
            EVENT_HANDLERS["invoice.paid"] = original_handler

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        assert "Internal server error" in body.get("error", "")

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.os.getenv")
    @patch("routes.stripe_webhook_routes.stripe.Webhook.construct_event")
    def test_malformed_json_body_returns_400(self, mock_construct, mock_getenv, client):
        """Completely invalid body should return 400 via construct_event ValueError."""
        mock_getenv.return_value = "whsec_test"
        mock_construct.side_effect = ValueError("No JSON object could be decoded")

        response = client.post(
            "/webhooks/stripe",
            content=b"this is not json at all {{{",
            headers={"Stripe-Signature": "t=1,v1=sig"},
        )

        assert response.status_code == 400

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.verify_stripe_webhook")
    def test_empty_data_object_handled_gracefully(self, mock_verify, client):
        """Event with empty data.object should still return 200."""
        mock_verify.return_value = {
            "id": "evt_empty_data",
            "type": "customer.subscription.deleted",
            "data": {"object": {}},
        }

        response = client.post(
            "/webhooks/stripe",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=sig"},
        )

        # Should not crash; handler returns not_found for missing subscription
        assert response.status_code == 200

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.verify_stripe_webhook")
    def test_missing_data_key_handled_gracefully(self, mock_verify, client):
        """Event with no 'data' key should default to empty object."""
        mock_verify.return_value = {
            "id": "evt_no_data_key",
            "type": "invoice.paid",
            # 'data' key intentionally missing -- .get("data", {}).get("object", {})
        }

        response = client.post(
            "/webhooks/stripe",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=sig"},
        )

        assert response.status_code == 200


# =============================================================================
# 5. FULL WEBHOOK ENDPOINT INTEGRATION
# =============================================================================

class TestWebhookEndpointIntegration:
    """Integration-style tests for the full POST /webhooks/stripe flow."""

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.verify_stripe_webhook")
    def test_full_invoice_paid_flow(self, mock_verify, client, db_session):
        """Full flow: webhook -> verify -> idempotency -> handler -> commit."""
        event_id = f"evt_full_{uuid.uuid4().hex[:12]}"
        mock_verify.return_value = {
            "id": event_id,
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": "in_full_flow",
                    "subscription": None,
                    "amount_paid": 9900,
                },
            },
        }

        response = client.post(
            "/webhooks/stripe",
            content=b'{"id": "evt_full"}',
            headers={"Stripe-Signature": "t=1,v1=valid"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "processed"
        assert body["result"]["status"] == "paid"

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.verify_stripe_webhook")
    def test_full_subscription_deleted_flow(self, mock_verify, client, db_session):
        """Full flow for subscription deletion through the webhook endpoint."""
        event_id = f"evt_del_{uuid.uuid4().hex[:12]}"
        mock_verify.return_value = {
            "id": event_id,
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_nonexistent_in_db",
                },
            },
        }

        response = client.post(
            "/webhooks/stripe",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=valid"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "processed"
        # Subscription not found in DB, but handler still returns successfully
        assert body["result"]["status"] == "not_found"

    @pytest.mark.unit
    @patch("routes.stripe_webhook_routes.verify_stripe_webhook")
    def test_webhook_response_time_is_fast(self, mock_verify, client):
        """Webhook should respond quickly (under 2 seconds) to avoid Stripe timeout."""
        mock_verify.return_value = {
            "id": f"evt_speed_{uuid.uuid4().hex[:12]}",
            "type": "balance.available",
            "data": {"object": {}},
        }

        start = time.time()
        response = client.post(
            "/webhooks/stripe",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=valid"},
        )
        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 2.0, f"Webhook took {elapsed:.2f}s, should be under 2s"
