"""
Scheduler Webhook Service - Dispatches appointment lifecycle events to registered webhooks.

Provides:
  - WebhookEvent enum for all appointment lifecycle event types
  - dispatch_webhook() to send events to matching subscriptions
  - register_webhook() to create new webhook subscriptions
  - HMAC-SHA256 signature generation for payload verification
  - Retry logic with exponential backoff (3 attempts)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from database.models.webhook import WebhookSubscription, WebhookDeliveryLog

logger = logging.getLogger(__name__)


# ============================================================================
# WEBHOOK EVENT TYPES
# ============================================================================

class WebhookEvent(str, Enum):
    """Appointment lifecycle events dispatched to external webhook consumers."""
    APPOINTMENT_CREATED = "appointment.created"
    APPOINTMENT_UPDATED = "appointment.updated"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
    APPOINTMENT_COMPLETED = "appointment.completed"
    APPOINTMENT_NO_SHOW = "appointment.no_show"
    REMINDER_SENT = "appointment.reminder_sent"


# All valid event strings for validation
VALID_EVENTS = {e.value for e in WebhookEvent}


# ============================================================================
# PAYLOAD CONSTRUCTION
# ============================================================================

def _build_event_payload(
    event_type: WebhookEvent,
    appointment_data: Dict[str, Any],
    organization_id: int,
) -> Dict[str, Any]:
    """Build the canonical webhook event payload.

    Structure:
        {
            "id": "<unique event id>",
            "event_type": "appointment.created",
            "timestamp": "2026-03-16T12:00:00Z",
            "organization_id": 42,
            "data": {
                "appointment_id": 123,
                "loan_id": 456,
                "borrower": { "name": "...", "email": "...", "phone": "..." },
                "loan_officer": { "id": ..., "name": "..." },
                "title": "...",
                "scheduled_start": "...",
                "scheduled_end": "...",
                "status": "...",
                ...extra fields from appointment_data...
            }
        }
    """
    return {
        "id": str(uuid.uuid4()),
        "event_type": event_type.value if isinstance(event_type, WebhookEvent) else event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "organization_id": organization_id,
        "data": appointment_data,
    }


# ============================================================================
# HMAC SIGNATURE
# ============================================================================

def compute_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for webhook payload verification.

    The consumer should recompute this from the raw request body and compare
    against the X-Webhook-Signature header value.
    """
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


# ============================================================================
# DELIVERY (single subscription)
# ============================================================================

_MAX_ATTEMPTS = 3
_BASE_BACKOFF_SECONDS = 2  # 2s, 4s, 8s
_DELIVERY_TIMEOUT_SECONDS = 30


async def _deliver_to_subscription(
    db: Session,
    subscription: WebhookSubscription,
    payload: Dict[str, Any],
) -> WebhookDeliveryLog:
    """Attempt to deliver a webhook payload to a single subscription with retries.

    Creates a WebhookDeliveryLog row for tracking, then performs up to
    _MAX_ATTEMPTS POST requests with exponential backoff on failure.
    """
    payload_bytes = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
    signature = compute_signature(payload_bytes, subscription.secret)

    event_type = payload.get("event_type", "unknown")

    # Create delivery log entry
    delivery = WebhookDeliveryLog(
        subscription_id=subscription.id,
        event_type=event_type,
        payload=payload,
        status="pending",
        attempt_number=0,
        max_attempts=_MAX_ATTEMPTS,
    )
    db.add(delivery)
    db.flush()  # get the id assigned

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Event": event_type,
        "X-Webhook-Delivery-Id": str(delivery.id),
        "User-Agent": "PerenniaAI-Webhooks/1.0",
    }

    # Merge any custom headers from the subscription
    if subscription.headers and isinstance(subscription.headers, dict):
        headers.update(subscription.headers)

    last_error = None
    timeout = subscription.timeout_seconds or _DELIVERY_TIMEOUT_SECONDS

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        delivery.attempt_number = attempt
        delivery.status = "retrying" if attempt > 1 else "pending"

        start_ms = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=float(timeout)) as client:
                response = await client.post(
                    subscription.url,
                    content=payload_bytes,
                    headers=headers,
                )

            elapsed_ms = int((time.monotonic() - start_ms) * 1000)
            delivery.response_code = response.status_code
            delivery.response_body = response.text[:2000]  # cap stored body
            delivery.response_time_ms = elapsed_ms

            if 200 <= response.status_code < 300:
                delivery.status = "success"
                delivery.delivered_at = datetime.now(timezone.utc)
                subscription.success_count = (subscription.success_count or 0) + 1
                subscription.last_triggered_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(
                    "Webhook delivered: subscription=%s event=%s attempt=%d status=%d ms=%d",
                    subscription.id, event_type, attempt, response.status_code, elapsed_ms,
                )
                return delivery

            # Non-2xx response -- retry
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            logger.warning(
                "Webhook delivery failed: subscription=%s attempt=%d/%d status=%d",
                subscription.id, attempt, _MAX_ATTEMPTS, response.status_code,
            )

        except httpx.TimeoutException as exc:
            elapsed_ms = int((time.monotonic() - start_ms) * 1000)
            delivery.response_time_ms = elapsed_ms
            last_error = f"Timeout after {timeout}s: {exc}"
            logger.warning(
                "Webhook delivery timeout: subscription=%s attempt=%d/%d",
                subscription.id, attempt, _MAX_ATTEMPTS,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start_ms) * 1000)
            delivery.response_time_ms = elapsed_ms
            last_error = str(exc)
            logger.exception(
                "Webhook delivery error: subscription=%s attempt=%d/%d",
                subscription.id, attempt, _MAX_ATTEMPTS,
            )

        # Exponential backoff before retry (skip on last attempt)
        if attempt < _MAX_ATTEMPTS:
            backoff = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            import asyncio
            await asyncio.sleep(backoff)

    # All attempts exhausted
    delivery.status = "failed"
    delivery.error_message = last_error
    subscription.failure_count = (subscription.failure_count or 0) + 1
    subscription.last_triggered_at = datetime.now(timezone.utc)
    db.commit()

    logger.error(
        "Webhook delivery exhausted: subscription=%s event=%s error=%s",
        subscription.id, event_type, last_error,
    )
    return delivery


# ============================================================================
# PUBLIC API — dispatch_webhook
# ============================================================================

async def dispatch_webhook(
    event_type: WebhookEvent,
    appointment_data: Dict[str, Any],
    organization_id: int,
    db: Session,
) -> List[WebhookDeliveryLog]:
    """Dispatch a webhook event to all active subscriptions for the given org.

    Args:
        event_type: The lifecycle event (e.g. WebhookEvent.APPOINTMENT_CREATED).
        appointment_data: Dict with appointment_id, loan_id, borrower info,
                          LO info, schedule details, status, etc.
        organization_id: Tenant org scope.
        db: SQLAlchemy session.

    Returns:
        List of WebhookDeliveryLog entries (one per matching subscription).
    """
    event_str = event_type.value if isinstance(event_type, WebhookEvent) else event_type

    # Find active subscriptions that are subscribed to this event
    subscriptions = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.organization_id == organization_id,
            WebhookSubscription.is_active == True,  # noqa: E712
        )
        .all()
    )

    # Filter to subscriptions whose events list includes our event
    matching = []
    for sub in subscriptions:
        events = sub.events or []
        if event_str in events or "*" in events:
            matching.append(sub)

    if not matching:
        logger.debug("No webhook subscriptions match event=%s org=%s", event_str, organization_id)
        return []

    payload = _build_event_payload(event_type, appointment_data, organization_id)

    deliveries = []
    for sub in matching:
        try:
            delivery = await _deliver_to_subscription(db, sub, payload)
            deliveries.append(delivery)
        except Exception as exc:
            logger.exception("Unexpected error dispatching to subscription=%s: %s", sub.id, exc)

    return deliveries


# ============================================================================
# PUBLIC API — register_webhook
# ============================================================================

async def register_webhook(
    url: str,
    events: List[str],
    organization_id: int,
    secret: str,
    db: Session,
    name: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> WebhookSubscription:
    """Register a new webhook endpoint for appointment lifecycle events.

    Args:
        url: The HTTPS endpoint to receive POST requests.
        events: List of event strings to subscribe to (from WebhookEvent values).
        organization_id: Tenant org scope.
        secret: Shared secret for HMAC-SHA256 signature verification.
        db: SQLAlchemy session.
        name: Optional human-readable name for the webhook.
        headers: Optional custom headers to include on every delivery.

    Returns:
        The created WebhookSubscription row.

    Raises:
        ValueError: If any event string is not recognized.
    """
    # Validate event strings
    invalid = [e for e in events if e not in VALID_EVENTS and e != "*"]
    if invalid:
        raise ValueError(f"Invalid event types: {invalid}. Valid: {sorted(VALID_EVENTS)}")

    subscription = WebhookSubscription(
        organization_id=organization_id,
        name=name or f"Scheduler webhook ({url[:60]})",
        url=url,
        secret=secret,
        events=events,
        headers=headers or {},
        retry_count=_MAX_ATTEMPTS,
        timeout_seconds=_DELIVERY_TIMEOUT_SECONDS,
        is_active=True,
        success_count=0,
        failure_count=0,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)

    logger.info(
        "Webhook registered: id=%s org=%s url=%s events=%s",
        subscription.id, organization_id, url, events,
    )
    return subscription


# ============================================================================
# HELPER — build appointment data dict from model
# ============================================================================

def build_appointment_event_data(appointment, lo_user=None) -> Dict[str, Any]:
    """Build the data payload from an Appointment ORM instance.

    This normalizes the appointment into a flat dict suitable for the
    webhook payload's `data` key.
    """
    data: Dict[str, Any] = {
        "appointment_id": appointment.id,
        "title": getattr(appointment, "title", None),
        "status": str(getattr(appointment, "status", "")),
        "meeting_type": str(getattr(appointment, "meeting_type", "")),
        "meeting_mode": str(getattr(appointment, "meeting_mode", "")),
        "scheduled_start": _isoformat(getattr(appointment, "scheduled_start", None)),
        "scheduled_end": _isoformat(getattr(appointment, "scheduled_end", None)),
        "duration_minutes": getattr(appointment, "duration_minutes", None),
        "timezone": getattr(appointment, "timezone", None),
        "location": getattr(appointment, "location", None),
        "video_link": getattr(appointment, "video_link", None),
    }

    # Related entity IDs
    data["lead_id"] = getattr(appointment, "lead_id", None)
    data["loan_id"] = getattr(appointment, "loan_id", None)

    # Borrower / attendee info
    data["borrower"] = {
        "name": getattr(appointment, "attendee_name", None),
        "email": getattr(appointment, "attendee_email", None),
        "phone": getattr(appointment, "attendee_phone", None),
    }

    # Loan officer info
    if lo_user:
        data["loan_officer"] = {
            "id": getattr(lo_user, "id", None),
            "name": f"{getattr(lo_user, 'first_name', '') or ''} {getattr(lo_user, 'last_name', '') or ''}".strip(),
            "email": getattr(lo_user, "email", None),
        }
    else:
        data["loan_officer"] = {
            "id": getattr(appointment, "assigned_user_id", None),
        }

    # Cancellation / reschedule context
    if getattr(appointment, "cancellation_reason", None):
        data["cancellation_reason"] = appointment.cancellation_reason
    if getattr(appointment, "reschedule_count", 0):
        data["reschedule_count"] = appointment.reschedule_count
    if getattr(appointment, "rescheduled_from_id", None):
        data["rescheduled_from_id"] = appointment.rescheduled_from_id

    return data


def _isoformat(dt) -> Optional[str]:
    """Safely convert a datetime to ISO 8601 string."""
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)
