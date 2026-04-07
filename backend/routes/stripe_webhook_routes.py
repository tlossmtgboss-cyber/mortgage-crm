"""
Stripe Webhook Routes

Handles Stripe webhook events for billing and subscription management.

Events handled:
- invoice.paid: Mark invoices as paid, update subscription period
- invoice.payment_failed: Handle failed payments, send notifications
- customer.subscription.created: New subscription activation
- customer.subscription.updated: Plan changes, cancellations
- customer.subscription.deleted: Subscription termination
- payment_method.attached: New payment method added
- payment_method.detached: Payment method removed
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

import stripe
from fastapi import APIRouter, Request, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from sqlalchemy import select

from database import get_db
from models.billing import (
    OrgSubscription, Invoice, PaymentMethod, StripeEvent,
    SubscriptionStatus, InvoiceStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/stripe", tags=["stripe", "billing"])


def verify_stripe_webhook(payload: bytes, signature: str) -> dict:
    """Verify and construct Stripe webhook event using SDK."""
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(status_code=503, detail="Stripe webhook not configured")
    try:
        event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
        return event
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=401, detail="Invalid Stripe signature")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")


def is_event_processed(db: Session, event_id: str) -> bool:
    """Check if we've already processed this event (idempotency)."""
    existing = db.execute(
        select(StripeEvent).where(StripeEvent.id == event_id)
    ).scalar_one_or_none()
    return existing is not None and existing.processed


def record_event(
    db: Session,
    event_id: str,
    event_type: str,
    data: Dict[str, Any],
    organization_id: Optional[int] = None,
) -> StripeEvent:
    """Record a Stripe event for idempotency and audit."""
    event = StripeEvent(
        id=event_id,
        event_type=event_type,
        data=data,
        organization_id=organization_id,
        processed=False,
    )
    db.add(event)
    db.flush()
    return event


def mark_event_processed(
    db: Session,
    event: StripeEvent,
    error: Optional[str] = None,
) -> None:
    """Mark an event as processed."""
    event.processed = True
    event.processed_at = datetime.now(timezone.utc)
    if error:
        event.processing_error = error


@router.post("")
async def handle_stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
):
    """
    Main Stripe webhook handler.

    Verifies signature via Stripe SDK, ensures idempotency, and routes to
    specific handlers.
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify signature and construct event via Stripe SDK
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    event = verify_stripe_webhook(body, stripe_signature)

    event_id = event.get("id")
    event_type = event.get("type")
    event_data = event.get("data", {}).get("object", {})

    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Missing event id or type")

    logger.info(f"Received Stripe webhook: {event_type} ({event_id})")

    # Check idempotency - skip if already processed
    if is_event_processed(db, event_id):
        logger.info(f"Event {event_id} already processed, skipping")
        return {"status": "already_processed"}

    # Record the event
    stripe_event = record_event(db, event_id, event_type, event)

    try:
        # Route to specific handler
        handler = EVENT_HANDLERS.get(event_type)
        if handler:
            result = await handler(event_data, db)
            mark_event_processed(db, stripe_event)
            db.commit()
            return {"status": "processed", "result": result}
        else:
            # Unhandled event type - acknowledge but don't process
            mark_event_processed(db, stripe_event)
            db.commit()
            logger.debug(f"Unhandled event type: {event_type}")
            return {"status": "ignored", "reason": f"Unhandled event type: {event_type}"}

    except Exception as e:
        logger.exception(f"Error processing Stripe event {event_id}: {e}")
        mark_event_processed(db, stripe_event, error=str(e))
        db.commit()
        # Return 200 to prevent Stripe retries for processing errors
        return {"status": "error", "error": "Internal server error"}


# =============================================================================
# Event Handlers
# =============================================================================

async def handle_invoice_paid(data: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """Handle invoice.paid event."""
    stripe_invoice_id = data.get("id")
    stripe_subscription_id = data.get("subscription")

    # Find or create invoice
    invoice = db.execute(
        select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id)
    ).scalar_one_or_none()

    if invoice:
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = datetime.now(timezone.utc)
        invoice.amount_paid = data.get("amount_paid", 0)
        invoice.amount_due = 0

        # Store URLs
        invoice.invoice_pdf_url = data.get("invoice_pdf")
        invoice.hosted_invoice_url = data.get("hosted_invoice_url")

        logger.info(f"Marked invoice {stripe_invoice_id} as paid")
    else:
        logger.warning(f"Invoice {stripe_invoice_id} not found in database")

    # Update subscription period if applicable
    if stripe_subscription_id:
        subscription = db.execute(
            select(OrgSubscription).where(
                OrgSubscription.stripe_subscription_id == stripe_subscription_id
            )
        ).scalar_one_or_none()

        if subscription:
            period_start = data.get("period_start")
            period_end = data.get("period_end")
            if period_start:
                subscription.current_period_start = datetime.fromtimestamp(
                    period_start, tz=timezone.utc
                )
            if period_end:
                subscription.current_period_end = datetime.fromtimestamp(
                    period_end, tz=timezone.utc
                )
            # Clear grace period and restore active status on successful payment
            if subscription.grace_period_ends_at:
                subscription.grace_period_ends_at = None
                subscription.status = SubscriptionStatus.ACTIVE
                logger.info(f"Subscription {stripe_subscription_id} grace period cleared, restored to ACTIVE")

    return {"invoice_id": stripe_invoice_id, "status": "paid"}


async def handle_invoice_payment_failed(data: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """Handle invoice.payment_failed event."""
    stripe_invoice_id = data.get("id")
    stripe_subscription_id = data.get("subscription")
    attempt_count = data.get("attempt_count", 1)

    # Update invoice status
    invoice = db.execute(
        select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id)
    ).scalar_one_or_none()

    if invoice:
        invoice.status = InvoiceStatus.OPEN
        invoice.meta_data = invoice.meta_data or {}
        invoice.meta_data["last_payment_error"] = data.get("last_payment_error", {})
        invoice.meta_data["attempt_count"] = attempt_count

    # Update subscription status if past_due
    if stripe_subscription_id:
        subscription = db.execute(
            select(OrgSubscription).where(
                OrgSubscription.stripe_subscription_id == stripe_subscription_id
            )
        ).scalar_one_or_none()

        if subscription:
            subscription.status = SubscriptionStatus.PAST_DUE
            # Set 14-day grace period on first failure only (don't extend on retries)
            if not subscription.grace_period_ends_at:
                subscription.grace_period_ends_at = datetime.now(timezone.utc) + timedelta(days=14)
                logger.info(
                    f"Subscription {stripe_subscription_id} grace period set: "
                    f"expires {subscription.grace_period_ends_at.isoformat()}"
                )
            logger.warning(
                f"Subscription {stripe_subscription_id} marked past_due "
                f"(attempt {attempt_count})"
            )

    return {
        "invoice_id": stripe_invoice_id,
        "attempt_count": attempt_count,
        "status": "payment_failed",
    }


async def handle_subscription_created(data: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """Handle customer.subscription.created event."""
    stripe_subscription_id = data.get("id")
    stripe_customer_id = data.get("customer")

    # Check if subscription already exists
    existing = db.execute(
        select(OrgSubscription).where(
            OrgSubscription.stripe_subscription_id == stripe_subscription_id
        )
    ).scalar_one_or_none()

    if existing:
        logger.info(f"Subscription {stripe_subscription_id} already exists")
        return {"subscription_id": stripe_subscription_id, "status": "exists"}

    # Find organization by Stripe customer ID
    org_sub = db.execute(
        select(OrgSubscription).where(
            OrgSubscription.stripe_customer_id == stripe_customer_id
        )
    ).scalar_one_or_none()

    if not org_sub:
        logger.warning(f"No organization found for customer {stripe_customer_id}")
        return {"status": "organization_not_found", "customer_id": stripe_customer_id}

    # Update the subscription with Stripe details
    org_sub.stripe_subscription_id = stripe_subscription_id
    org_sub.status = SubscriptionStatus(data.get("status", "active"))

    # Set period dates
    if data.get("current_period_start"):
        org_sub.current_period_start = datetime.fromtimestamp(
            data["current_period_start"], tz=timezone.utc
        )
    if data.get("current_period_end"):
        org_sub.current_period_end = datetime.fromtimestamp(
            data["current_period_end"], tz=timezone.utc
        )
    if data.get("trial_end"):
        org_sub.trial_end = datetime.fromtimestamp(
            data["trial_end"], tz=timezone.utc
        )

    logger.info(f"Linked subscription {stripe_subscription_id} to organization")
    return {"subscription_id": stripe_subscription_id, "status": "created"}


async def handle_subscription_updated(data: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """Handle customer.subscription.updated event."""
    stripe_subscription_id = data.get("id")

    subscription = db.execute(
        select(OrgSubscription).where(
            OrgSubscription.stripe_subscription_id == stripe_subscription_id
        )
    ).scalar_one_or_none()

    if not subscription:
        logger.warning(f"Subscription {stripe_subscription_id} not found")
        return {"status": "not_found", "subscription_id": stripe_subscription_id}

    # Update status
    new_status = data.get("status")
    if new_status:
        subscription.status = SubscriptionStatus(new_status)

    # Update period
    if data.get("current_period_start"):
        subscription.current_period_start = datetime.fromtimestamp(
            data["current_period_start"], tz=timezone.utc
        )
    if data.get("current_period_end"):
        subscription.current_period_end = datetime.fromtimestamp(
            data["current_period_end"], tz=timezone.utc
        )

    # Handle cancellation
    subscription.cancel_at_period_end = data.get("cancel_at_period_end", False)
    if data.get("canceled_at"):
        subscription.canceled_at = datetime.fromtimestamp(
            data["canceled_at"], tz=timezone.utc
        )

    # Update plan if changed
    items = data.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id")
        # TODO: Map Stripe price ID to internal plan_id

    logger.info(f"Updated subscription {stripe_subscription_id}: status={new_status}")
    return {"subscription_id": stripe_subscription_id, "status": new_status}


async def handle_subscription_deleted(data: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """Handle customer.subscription.deleted event."""
    stripe_subscription_id = data.get("id")

    subscription = db.execute(
        select(OrgSubscription).where(
            OrgSubscription.stripe_subscription_id == stripe_subscription_id
        )
    ).scalar_one_or_none()

    if not subscription:
        logger.warning(f"Subscription {stripe_subscription_id} not found")
        return {"status": "not_found"}

    subscription.status = SubscriptionStatus.CANCELED
    subscription.canceled_at = datetime.now(timezone.utc)

    logger.info(f"Subscription {stripe_subscription_id} canceled")
    return {"subscription_id": stripe_subscription_id, "status": "canceled"}


async def handle_payment_method_attached(data: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """Handle payment_method.attached event."""
    stripe_pm_id = data.get("id")
    stripe_customer_id = data.get("customer")
    pm_type = data.get("type", "card")

    # Find organization
    subscription = db.execute(
        select(OrgSubscription).where(
            OrgSubscription.stripe_customer_id == stripe_customer_id
        )
    ).scalar_one_or_none()

    if not subscription:
        logger.warning(f"No subscription found for customer {stripe_customer_id}")
        return {"status": "customer_not_found"}

    # Create payment method record
    card_details = data.get("card", {})

    payment_method = PaymentMethod(
        organization_id=subscription.organization_id,
        stripe_payment_method_id=stripe_pm_id,
        stripe_customer_id=stripe_customer_id,
        type=pm_type,
        card_brand=card_details.get("brand"),
        card_last4=card_details.get("last4"),
        card_exp_month=card_details.get("exp_month"),
        card_exp_year=card_details.get("exp_year"),
        is_default=False,
    )
    db.add(payment_method)

    logger.info(f"Added payment method {stripe_pm_id} for customer {stripe_customer_id}")
    return {"payment_method_id": stripe_pm_id, "status": "attached"}


async def handle_payment_method_detached(data: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """Handle payment_method.detached event."""
    stripe_pm_id = data.get("id")

    payment_method = db.execute(
        select(PaymentMethod).where(
            PaymentMethod.stripe_payment_method_id == stripe_pm_id
        )
    ).scalar_one_or_none()

    if payment_method:
        payment_method.is_active = False
        logger.info(f"Deactivated payment method {stripe_pm_id}")
        return {"payment_method_id": stripe_pm_id, "status": "detached"}

    return {"payment_method_id": stripe_pm_id, "status": "not_found"}


# Map event types to handlers
EVENT_HANDLERS = {
    "invoice.paid": handle_invoice_paid,
    "invoice.payment_failed": handle_invoice_payment_failed,
    "customer.subscription.created": handle_subscription_created,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
    "payment_method.attached": handle_payment_method_attached,
    "payment_method.detached": handle_payment_method_detached,
}
