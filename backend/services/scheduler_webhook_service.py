"""
Scheduler Webhook Service - Dispatches appointment lifecycle events to registered webhooks.

Provides:
  - WebhookEvent enum for all appointment lifecycle event types
  - dispatch_webhook() to send events to matching subscriptions
  - register_webhook() to create new webhook subscriptions
  - HMAC-SHA256 signature generation for payload verification
  - Retry logic with exponential backoff (3 attempts)
  - Dead-letter queue for failed deliveries with admin notifications
  - retry_failed_webhook() for manual retry of dead-lettered deliveries
  - get_failed_webhooks() for admin review of failed deliveries
  - check_webhook_health() for subscription health monitoring
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
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
    against the X-Webhook-Signature header value using verify_signature().
    """
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def verify_signature(payload_bytes: bytes, secret: str, received_signature: str) -> bool:
    """Verify a webhook signature using constant-time comparison.

    Args:
        payload_bytes: The raw request body bytes.
        secret: The shared webhook secret.
        received_signature: The signature from X-Webhook-Signature header
                           (with or without 'sha256=' prefix).

    Returns:
        True if the signature is valid.
    """
    expected = compute_signature(payload_bytes, secret)
    # Strip 'sha256=' prefix if present
    received = received_signature
    if received.startswith("sha256="):
        received = received[7:]
    return hmac.compare_digest(expected, received)


def _validate_webhook_url(url: str) -> None:
    """Reject webhook URLs targeting private/internal networks (SSRF protection).

    Raises ValueError if the URL resolves to a private IP range or uses
    a non-HTTPS scheme (except for localhost in development).
    """
    from urllib.parse import urlparse
    import ipaddress
    import socket

    parsed = urlparse(url)

    # Require http(s) scheme
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Webhook URL must use http or https scheme, got: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Webhook URL must have a hostname")

    # Block obviously internal hostnames
    _BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]", "metadata.google.internal"}
    if hostname.lower() in _BLOCKED_HOSTS:
        raise ValueError(f"Webhook URL cannot target internal host: {hostname}")

    # Resolve hostname and check for private IP ranges
    try:
        addrs = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
        for family, type_, proto, canonname, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError(f"Webhook URL resolves to private/reserved IP: {ip}")
    except socket.gaierror:
        raise ValueError(f"Webhook URL hostname cannot be resolved: {hostname}")


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
        "X-Webhook-Event": event_type,
        "X-Webhook-Delivery-Id": str(delivery.id),
        "User-Agent": "PerenniaAI-Webhooks/1.0",
    }

    # SEC-006: Merge custom headers but protect system headers from override
    _PROTECTED_HEADERS = frozenset({"Content-Type", "X-Webhook-Event", "X-Webhook-Delivery-Id", "X-Webhook-Signature", "User-Agent"})
    if subscription.headers and isinstance(subscription.headers, dict):
        for key, value in subscription.headers.items():
            if key not in _PROTECTED_HEADERS:
                headers[key] = value

    # NC6 fix: Set HMAC signature AFTER custom headers to prevent override
    headers["X-Webhook-Signature"] = f"sha256={signature}"

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

    # All attempts exhausted — enter dead-letter queue
    delivery.status = "failed"
    delivery.error_message = last_error
    delivery.dead_letter_at = datetime.now(timezone.utc)
    subscription.failure_count = (subscription.failure_count or 0) + 1
    subscription.last_triggered_at = datetime.now(timezone.utc)
    db.commit()

    logger.warning(
        "Webhook dead-lettered: subscription_id=%s subscription_name=%s "
        "url=%s event=%s delivery_id=%s attempts=%d last_error=%s",
        subscription.id,
        subscription.name,
        subscription.url,
        event_type,
        delivery.id,
        _MAX_ATTEMPTS,
        last_error,
    )

    # Create admin notification for failed webhook delivery
    _create_dead_letter_notification(
        db=db,
        subscription=subscription,
        delivery=delivery,
        event_type=event_type,
        last_error=last_error,
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

    # PERF-010: Deliver to all matching subscriptions concurrently.
    # Each coroutine gets its own DB session to avoid transaction corruption
    # (SQLAlchemy sessions are not coroutine-safe).
    import asyncio
    from db import SessionLocal

    async def _safe_deliver(sub):
        session = SessionLocal()
        try:
            # Re-load the subscription in the new session to avoid detached state
            local_sub = session.merge(sub, load=False)
            return await _deliver_to_subscription(session, local_sub, payload)
        except Exception as exc:
            logger.exception("Unexpected error dispatching to subscription=%s: %s", sub.id, exc)
            return None
        finally:
            session.close()

    results = await asyncio.gather(*[_safe_deliver(sub) for sub in matching])
    deliveries = [r for r in results if r is not None]

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

    # SSRF protection: reject URLs targeting private/internal networks
    _validate_webhook_url(url)

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


# ============================================================================
# DEAD-LETTER NOTIFICATION
# ============================================================================

def _create_dead_letter_notification(
    db: Session,
    subscription: WebhookSubscription,
    delivery: WebhookDeliveryLog,
    event_type: str,
    last_error: str,
) -> None:
    """Create an in-app notification for org admins when a webhook enters the dead-letter queue.

    Targets users with permission_role 'admin' or 'site_admin' in the same
    organization as the webhook subscription.
    """
    try:
        from database.models.core import User
        from database.models.security import Notification

        admin_users = (
            db.query(User)
            .filter(
                User.organization_id == subscription.organization_id,
                User.permission_role.in_(["admin", "site_admin"]),
                User.is_active == True,  # noqa: E712
            )
            .all()
        )

        if not admin_users:
            logger.debug(
                "No admin users found for org=%s to notify about dead-lettered webhook",
                subscription.organization_id,
            )
            return

        truncated_error = (last_error or "Unknown error")[:500]

        for admin in admin_users:
            notification = Notification(
                organization_id=subscription.organization_id,
                user_id=admin.id,
                type="webhook_delivery_failed",
                title=f"Webhook delivery failed: {subscription.name}",
                message=(
                    f"Webhook \"{subscription.name}\" ({subscription.url}) failed to deliver "
                    f"event \"{event_type}\" after {_MAX_ATTEMPTS} attempts. "
                    f"Error: {truncated_error}"
                ),
                link=f"/settings/webhooks?delivery_id={delivery.id}",
                is_read=False,
            )
            db.add(notification)

        db.commit()

        logger.info(
            "Dead-letter notifications created for %d admin(s) in org=%s",
            len(admin_users),
            subscription.organization_id,
        )
    except Exception as e:
        logger.exception(
            "Failed to create dead-letter notification for delivery=%s: %s",
            delivery.id, e,
        )
        # Don't let notification failure break the main flow
        try:
            db.rollback()
        except Exception:
            pass


# ============================================================================
# DEAD-LETTER QUEUE — MANUAL RETRY
# ============================================================================

async def retry_failed_webhook(
    db: Session,
    delivery_id: int,
    organization_id: int,
) -> WebhookDeliveryLog:
    """Manually retry a failed/dead-lettered webhook delivery.

    Resets the delivery status to 'pending', clears attempt tracking,
    and re-executes delivery against the original subscription with
    full retry logic.

    Args:
        db: SQLAlchemy session.
        delivery_id: The WebhookDeliveryLog.id to retry.
        organization_id: Tenant org scope — only deliveries belonging to
            subscriptions in this org can be retried.

    Returns:
        The updated WebhookDeliveryLog after re-delivery attempt.

    Raises:
        ValueError: If delivery_id not found or not in a retryable state.
    """
    delivery = (
        db.query(WebhookDeliveryLog)
        .join(WebhookSubscription, WebhookDeliveryLog.subscription_id == WebhookSubscription.id)
        .filter(
            WebhookDeliveryLog.id == delivery_id,
            WebhookSubscription.organization_id == organization_id,
        )
        .first()
    )

    if not delivery:
        raise ValueError(f"Webhook delivery {delivery_id} not found")

    if delivery.status not in ("failed",):
        raise ValueError(
            f"Webhook delivery {delivery_id} is in status '{delivery.status}' "
            f"and cannot be retried. Only 'failed' deliveries can be retried."
        )

    subscription = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.id == delivery.subscription_id,
            WebhookSubscription.organization_id == organization_id,
        )
        .first()
    )

    if not subscription:
        raise ValueError(
            f"Subscription {delivery.subscription_id} not found for delivery {delivery_id}"
        )

    if not subscription.is_active:
        raise ValueError(
            f"Subscription {subscription.id} ({subscription.name}) is inactive. "
            f"Re-activate it before retrying."
        )

    # Reset delivery for fresh attempt
    delivery.status = "pending"
    delivery.attempt_number = 0
    delivery.error_message = None
    delivery.response_code = None
    delivery.response_body = None
    delivery.response_time_ms = None
    delivery.delivered_at = None
    delivery.dead_letter_at = None
    db.flush()

    logger.info(
        "Manual retry initiated: delivery_id=%s subscription=%s event=%s",
        delivery_id, subscription.id, delivery.event_type,
    )

    # Re-deliver using the stored payload
    result = await _deliver_to_subscription(db, subscription, delivery.payload)

    # The _deliver_to_subscription creates a new delivery log, but we want
    # to keep the original entry updated. Copy final state back.
    delivery.status = result.status
    delivery.attempt_number = result.attempt_number
    delivery.response_code = result.response_code
    delivery.response_body = result.response_body
    delivery.response_time_ms = result.response_time_ms
    delivery.error_message = result.error_message
    delivery.delivered_at = result.delivered_at
    delivery.dead_letter_at = result.dead_letter_at

    # Remove the duplicate delivery log that _deliver_to_subscription created
    if result.id != delivery.id:
        db.delete(result)

    db.commit()

    return delivery


# ============================================================================
# DEAD-LETTER QUEUE — QUERY
# ============================================================================

async def get_failed_webhooks(
    db: Session,
    organization_id: int,
    subscription_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """Get list of failed/dead-lettered webhook deliveries for admin review.

    Args:
        db: SQLAlchemy session.
        organization_id: Tenant org scope — required for tenant isolation.
        subscription_id: Filter by specific subscription (optional).
        limit: Max results to return (default 50).
        offset: Pagination offset (default 0).

    Returns:
        Dict with 'deliveries' list, 'total' count, and 'pagination' info.
    """
    query = (
        db.query(WebhookDeliveryLog)
        .join(WebhookSubscription, WebhookDeliveryLog.subscription_id == WebhookSubscription.id)
        .filter(
            WebhookDeliveryLog.status == "failed",
            WebhookSubscription.organization_id == organization_id,
        )
    )

    if subscription_id is not None:
        query = query.filter(WebhookDeliveryLog.subscription_id == subscription_id)

    total = query.count()

    deliveries = (
        query
        .order_by(WebhookDeliveryLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []
    for d in deliveries:
        sub = d.subscription
        results.append({
            "delivery_id": d.id,
            "subscription_id": d.subscription_id,
            "subscription_name": sub.name if sub else None,
            "subscription_url": sub.url if sub else None,
            "organization_id": sub.organization_id if sub else None,
            "event_type": d.event_type,
            "status": d.status,
            "attempt_number": d.attempt_number,
            "max_attempts": d.max_attempts,
            "response_code": d.response_code,
            "error_message": d.error_message,
            "dead_letter_at": _isoformat(d.dead_letter_at),
            "created_at": _isoformat(d.created_at),
            "payload_event_id": (d.payload or {}).get("id"),
        })

    return {
        "deliveries": results,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }


# ============================================================================
# WEBHOOK HEALTH CHECK
# ============================================================================

async def check_webhook_health(
    db: Session,
    subscription_id: int,
    organization_id: int,
    window_hours: int = 24,
) -> Dict[str, Any]:
    """Check if a webhook subscription is healthy based on recent delivery success rate.

    Examines deliveries within the specified time window and computes a
    success rate.  A subscription is considered:
      - 'healthy' if success rate >= 90%
      - 'degraded' if success rate >= 50%
      - 'unhealthy' if success rate < 50%
      - 'inactive' if no deliveries in the window

    Args:
        db: SQLAlchemy session.
        subscription_id: The WebhookSubscription.id to check.
        organization_id: Tenant org scope — only subscriptions in this org
            can be queried.
        window_hours: How far back to look (default 24 hours).

    Returns:
        Dict with health status, success rate, and delivery counts.

    Raises:
        ValueError: If subscription_id not found.
    """
    subscription = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.organization_id == organization_id,
        )
        .first()
    )

    if not subscription:
        raise ValueError(f"Webhook subscription {subscription_id} not found")

    window_start = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    recent_deliveries = (
        db.query(WebhookDeliveryLog)
        .filter(
            WebhookDeliveryLog.subscription_id == subscription_id,
            WebhookDeliveryLog.created_at >= window_start,
        )
        .all()
    )

    total = len(recent_deliveries)
    if total == 0:
        return {
            "subscription_id": subscription_id,
            "subscription_name": subscription.name,
            "subscription_url": subscription.url,
            "is_active": subscription.is_active,
            "health_status": "inactive",
            "window_hours": window_hours,
            "total_deliveries": 0,
            "successful": 0,
            "failed": 0,
            "success_rate": None,
            "last_triggered_at": _isoformat(subscription.last_triggered_at),
            "lifetime_success_count": subscription.success_count or 0,
            "lifetime_failure_count": subscription.failure_count or 0,
        }

    successful = sum(1 for d in recent_deliveries if d.status == "success")
    failed = sum(1 for d in recent_deliveries if d.status == "failed")
    pending_or_retrying = total - successful - failed
    success_rate = round((successful / total) * 100, 1) if total > 0 else 0.0

    if success_rate >= 90:
        health_status = "healthy"
    elif success_rate >= 50:
        health_status = "degraded"
    else:
        health_status = "unhealthy"

    # Count consecutive recent failures (most recent first)
    consecutive_failures = 0
    sorted_deliveries = sorted(recent_deliveries, key=lambda d: d.created_at, reverse=True)
    for d in sorted_deliveries:
        if d.status == "failed":
            consecutive_failures += 1
        else:
            break

    return {
        "subscription_id": subscription_id,
        "subscription_name": subscription.name,
        "subscription_url": subscription.url,
        "is_active": subscription.is_active,
        "health_status": health_status,
        "window_hours": window_hours,
        "total_deliveries": total,
        "successful": successful,
        "failed": failed,
        "pending_or_retrying": pending_or_retrying,
        "success_rate": success_rate,
        "consecutive_recent_failures": consecutive_failures,
        "last_triggered_at": _isoformat(subscription.last_triggered_at),
        "lifetime_success_count": subscription.success_count or 0,
        "lifetime_failure_count": subscription.failure_count or 0,
    }
