"""
Webhook Idempotency Dependency
==============================
FastAPI dependency that prevents duplicate processing of webhook callbacks
from Vapi, Telnyx, Stripe, and other providers that retry on timeout/failure.

Two layers are provided:

1. **Lightweight fast-path** (``is_duplicate_webhook``): Uses Redis SET with
   TTL and an in-memory dict fallback.  No database dependency.  Suitable for
   any webhook handler that just needs "have I seen this event ID before?"

2. **Database-backed** (``check_webhook_idempotency``): Uses the
   ``webhook_idempotency`` database table as the durable store.  Provides
   richer tracking (status, response_code) at the cost of a DB round-trip.

Usage — lightweight:
    from middleware.webhook_idempotency import is_duplicate_webhook

    @router.post("/webhook/vapi")
    async def handle_vapi(request: Request):
        payload = await request.json()
        call_id = payload.get("message", {}).get("call", {}).get("id")
        event_type = payload.get("message", {}).get("type", "")
        event_key = f"{event_type}:{call_id}" if call_id else None
        if event_key and is_duplicate_webhook("vapi", event_key):
            return {"status": "duplicate"}
        # ... process ...

Usage — database-backed:
    from middleware.webhook_idempotency import check_webhook_idempotency

    @router.post("/webhook/vapi")
    async def handle_vapi(
        request: Request,
        idem: dict = Depends(check_webhook_idempotency),
        db: Session = Depends(get_db),
    ):
        if idem["duplicate"]:
            return JSONResponse(status_code=200, content={"status": "already_processed"})
        try:
            # ... process the webhook ...
            mark_processed(db, idem["key"], response_code=200)
        except Exception:
            mark_failed(db, idem["key"], response_code=500)
            raise
"""

import hashlib
import json
import logging
import threading
import time
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.models.webhook_idempotency import WebhookIdempotencyRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lightweight Redis + in-memory dedup (fast-path, no DB needed)
# ---------------------------------------------------------------------------

_WEBHOOK_TTL_SECONDS = 86400  # 24 hours

# In-memory fallback: {key: expiry_timestamp}
_seen_events: dict[str, float] = {}
_seen_lock = threading.Lock()

# Cap in-memory store to prevent unbounded growth
_MAX_IN_MEMORY = 50_000


def _get_redis():
    """Get Redis client from the centralized service, or None."""
    try:
        from services.redis_service import get_redis_client
        return get_redis_client()
    except Exception:
        return None


def _cleanup_expired_memory():
    """Remove expired entries from the in-memory dict (call under lock)."""
    now = time.monotonic()
    expired = [k for k, exp in _seen_events.items() if exp <= now]
    for k in expired:
        del _seen_events[k]


def is_duplicate_webhook(provider: str, event_key: str) -> bool:
    """
    Check if a webhook event has already been seen.  Records it with a 24-hour
    TTL if new.

    Args:
        provider: Provider name (e.g. "vapi", "telnyx").
        event_key: A unique key for this event.  For Vapi this is typically
            ``f"{message_type}:{call_id}"``.  For Telnyx it is the
            ``data.id`` field from the webhook payload.

    Returns:
        True if the event was already seen (duplicate) — caller should skip.
        False if the event is new — caller should process it.
    """
    full_key = f"webhook:idem:{provider}:{event_key}"

    # Try Redis first
    redis = _get_redis()
    if redis is not None:
        try:
            # SET NX returns True if the key was set (new), False if it existed
            was_set = redis.set(full_key, "1", nx=True, ex=_WEBHOOK_TTL_SECONDS)
            if was_set:
                logger.debug("Webhook dedup [redis]: new event %s", full_key[:80])
                return False
            else:
                logger.info("Webhook dedup [redis]: duplicate event %s", full_key[:80])
                return True
        except Exception as e:
            logger.warning("Webhook dedup: Redis error, falling back to memory: %s", e)

    # In-memory fallback
    now = time.monotonic()
    with _seen_lock:
        # Periodic cleanup
        if len(_seen_events) > _MAX_IN_MEMORY:
            _cleanup_expired_memory()

        if full_key in _seen_events:
            if _seen_events[full_key] > now:
                logger.info("Webhook dedup [memory]: duplicate event %s", full_key[:80])
                return True
            # Expired — treat as new
            del _seen_events[full_key]

        _seen_events[full_key] = now + _WEBHOOK_TTL_SECONDS
        logger.debug("Webhook dedup [memory]: new event %s", full_key[:80])
        return False


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

def _detect_provider(request: Request) -> str:
    """Detect the webhook provider from request headers."""
    headers = request.headers
    if headers.get("telnyx-signature-ed25519") or headers.get("telnyx-timestamp"):
        return "telnyx"
    if headers.get("x-vapi-signature") or headers.get("x-vapi-secret"):
        return "vapi"
    if headers.get("stripe-signature"):
        return "stripe"
    return "unknown"


# ---------------------------------------------------------------------------
# Key extraction
# ---------------------------------------------------------------------------

def _build_idempotency_key(
    provider: str,
    event_type: Optional[str],
    event_id: Optional[str],
    body_bytes: bytes,
) -> str:
    """
    Build a deterministic idempotency key.

    Priority:
    1. provider + event_id (most reliable — provider-assigned unique ID)
    2. provider + sha256(body) (fallback — body hash for providers that
       don't include a stable event ID)
    """
    if event_id:
        raw = f"{provider}:{event_type or ''}:{event_id}"
    else:
        body_hash = hashlib.sha256(body_bytes).hexdigest()[:32]
        raw = f"{provider}:{event_type or ''}:body:{body_hash}"
    # Truncate to 255 chars (column limit)
    return raw[:255]


def _extract_event_fields(body: dict, provider: str) -> tuple:
    """
    Extract event_type and event_id from the parsed webhook body.

    Returns (event_type, event_id) tuple.
    """
    event_type = None
    event_id = None

    if provider == "vapi":
        # Vapi sends {"message": {"type": "end-of-call-report", ...}}
        message = body.get("message", {})
        event_type = message.get("type") or body.get("type")
        event_id = (
            message.get("call", {}).get("id")
            or message.get("callId")
            or body.get("call", {}).get("id")
        )
        # Combine type + call ID for uniqueness (same call can have
        # multiple event types: status-update, end-of-call-report, etc.)
        if event_id and event_type:
            event_id = f"{event_type}:{event_id}"

    elif provider == "telnyx":
        # Telnyx sends {"data": {"event_type": "...", "id": "..."}}
        data = body.get("data", {})
        event_type = data.get("event_type")
        event_id = data.get("id") or body.get("id")
        # Also check meta.event_id for Telnyx v2 format
        meta = body.get("meta", {})
        if not event_id:
            event_id = meta.get("event_id")

    elif provider == "stripe":
        event_type = body.get("type")
        event_id = body.get("id")

    else:
        # Generic: look for common field names
        event_type = body.get("event_type") or body.get("type") or body.get("event")
        event_id = body.get("event_id") or body.get("id")

    return event_type, event_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def check_webhook_idempotency(request: Request, db: Session) -> dict:
    """
    Check if this webhook callback was already processed.

    Returns a dict:
        {
            "duplicate": bool,    # True if already processed — skip handler
            "key": str,           # Idempotency key for mark_processed/mark_failed
            "provider": str,      # Detected provider name
            "event_type": str | None,
            "event_id": str | None,
        }

    On duplicate detection, does NOT raise — returns the dict so the caller
    can decide how to respond (most webhook providers expect 200 OK).
    """
    provider = _detect_provider(request)

    # Read and cache the body (may already be cached by signature verification)
    body_bytes = await request.body()

    # Parse JSON body for event fields
    body = {}
    try:
        body = json.loads(body_bytes) if body_bytes else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    # Check for explicit idempotency header first
    header_key = request.headers.get("x-idempotency-key")

    event_type, event_id = _extract_event_fields(body, provider)

    if header_key:
        key = header_key[:255]
    else:
        key = _build_idempotency_key(provider, event_type, event_id, body_bytes)

    result = {
        "duplicate": False,
        "key": key,
        "provider": provider,
        "event_type": event_type,
        "event_id": event_id,
    }

    # Check for existing record
    existing = (
        db.query(WebhookIdempotencyRecord)
        .filter(WebhookIdempotencyRecord.idempotency_key == key)
        .first()
    )

    if existing and existing.status == "processed":
        logger.info(
            "Webhook idempotency: duplicate detected (key=%s, provider=%s, event=%s)",
            key[:60], provider, event_type,
        )
        result["duplicate"] = True
        return result

    # If no existing record, insert one with status='processing'
    if not existing:
        try:
            record = WebhookIdempotencyRecord(
                idempotency_key=key,
                provider=provider,
                event_type=event_type,
                event_id=event_id,
                status="processing",
            )
            db.add(record)
            db.flush()
        except IntegrityError:
            # Race condition: another request inserted between our check and insert
            db.rollback()
            logger.info(
                "Webhook idempotency: race-condition duplicate (key=%s)", key[:60],
            )
            result["duplicate"] = True

    return result


def mark_processed(db: Session, key: str, response_code: int = 200) -> None:
    """Mark a webhook event as successfully processed."""
    db.query(WebhookIdempotencyRecord).filter(
        WebhookIdempotencyRecord.idempotency_key == key,
    ).update({"status": "processed", "response_code": response_code})
    db.commit()


def mark_failed(db: Session, key: str, response_code: int = 500) -> None:
    """Mark a webhook event as failed (allows reprocessing on next retry)."""
    db.query(WebhookIdempotencyRecord).filter(
        WebhookIdempotencyRecord.idempotency_key == key,
    ).update({"status": "failed", "response_code": response_code})
    db.commit()


def purge_old_records(db: Session, hours: int = 72) -> int:
    """
    Delete idempotency records older than the given number of hours.
    Call from a scheduled cleanup job.  Returns number of rows deleted.
    """
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    count = (
        db.query(WebhookIdempotencyRecord)
        .filter(WebhookIdempotencyRecord.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    logger.info("Purged %d webhook idempotency records older than %dh", count, hours)
    return count
