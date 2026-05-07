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

3. **Dead-letter queue** (``record_webhook_failure``, ``get_failed_webhooks``,
   ``retry_webhook``): Stores failed webhook events for later inspection and
   reprocessing.  Uses Redis list with in-memory deque fallback.  Capped at
   1000 entries per provider (FIFO eviction).

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

Usage — dead-letter queue:
    from middleware.webhook_idempotency import record_webhook_failure, get_failed_webhooks, retry_webhook

    try:
        process_webhook(payload)
    except Exception as e:
        record_webhook_failure("vapi:end-of-call:call_123", "vapi", str(e), payload)

    # Admin: list and retry
    failed = get_failed_webhooks(provider="vapi", limit=20)
    retry_webhook("vapi:end-of-call:call_123")
"""

import collections
import hashlib
import json
import logging
import threading
import time
from typing import List, Optional

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
# Dead-letter queue (DLQ) for failed webhook events
# ---------------------------------------------------------------------------

_DLQ_MAX_PER_PROVIDER = 1000
_DLQ_REDIS_PREFIX = "webhook:dlq:"

# In-memory fallback: provider -> deque of serialized JSON entries
_dlq_store: dict[str, collections.deque] = {}
_dlq_lock = threading.Lock()


def _dlq_entry(event_key: str, provider: str, error: str, payload: dict) -> dict:
    """Build a dead-letter entry dict."""
    from datetime import datetime, timezone
    return {
        "event_key": event_key,
        "provider": provider,
        "error": error,
        "payload": payload,
        "failed_at": datetime.now(timezone.utc).isoformat(),
    }


def record_webhook_failure(
    event_key: str, provider: str, error: str, payload: dict,
) -> None:
    """
    Store a failed webhook event in the dead-letter queue.

    Args:
        event_key: Unique key for this event (same format as idempotency key).
        provider: Provider name (e.g. "vapi", "telnyx", "stripe").
        error: Error message / traceback summary.
        payload: The original webhook payload (will be JSON-serialized).
    """
    entry = _dlq_entry(event_key, provider, error, payload)
    entry_json = json.dumps(entry, default=str)
    redis_key = f"{_DLQ_REDIS_PREFIX}{provider}"

    redis = _get_redis()
    if redis is not None:
        try:
            redis.lpush(redis_key, entry_json)
            # Trim to cap — keep the newest _DLQ_MAX_PER_PROVIDER entries
            redis.ltrim(redis_key, 0, _DLQ_MAX_PER_PROVIDER - 1)
            logger.info(
                "Webhook DLQ [redis]: recorded failure for %s (provider=%s)",
                event_key[:80], provider,
            )
            return
        except Exception as e:
            logger.warning("Webhook DLQ: Redis error, falling back to memory: %s", e)

    # In-memory fallback
    with _dlq_lock:
        if provider not in _dlq_store:
            _dlq_store[provider] = collections.deque(maxlen=_DLQ_MAX_PER_PROVIDER)
        _dlq_store[provider].appendleft(entry_json)
    logger.info(
        "Webhook DLQ [memory]: recorded failure for %s (provider=%s)",
        event_key[:80], provider,
    )


def get_failed_webhooks(
    provider: str = None, limit: int = 50,
) -> List[dict]:
    """
    Retrieve failed webhook events from the dead-letter queue.

    Args:
        provider: Filter by provider name.  None returns all providers.
        limit: Maximum number of entries to return (default 50).

    Returns:
        List of dicts, each with keys: event_key, provider, error, payload, failed_at.
        Ordered newest-first.
    """
    results: list[dict] = []

    providers_to_check = [provider] if provider else None

    redis = _get_redis()
    if redis is not None:
        try:
            if providers_to_check is None:
                # Discover all DLQ keys
                cursor_keys = redis.keys(f"{_DLQ_REDIS_PREFIX}*")
                providers_to_check = [
                    k.decode() if isinstance(k, bytes) else k
                    for k in cursor_keys
                ]
                # Strip prefix to get provider names, then re-add for fetching
                providers_to_check = [
                    k.replace(_DLQ_REDIS_PREFIX, "") for k in providers_to_check
                ]

            for prov in providers_to_check:
                rkey = f"{_DLQ_REDIS_PREFIX}{prov}"
                entries = redis.lrange(rkey, 0, limit - 1)
                for raw in entries:
                    try:
                        entry = json.loads(raw)
                        results.append(entry)
                    except (json.JSONDecodeError, TypeError):
                        continue
                if len(results) >= limit:
                    break

            # Sort by failed_at descending and cap
            results.sort(key=lambda x: x.get("failed_at", ""), reverse=True)
            return results[:limit]
        except Exception as e:
            logger.warning("Webhook DLQ: Redis read error, falling back to memory: %s", e)

    # In-memory fallback
    with _dlq_lock:
        if providers_to_check is None:
            providers_to_check = list(_dlq_store.keys())

        for prov in providers_to_check:
            dq = _dlq_store.get(prov)
            if not dq:
                continue
            for raw in list(dq)[:limit]:
                try:
                    entry = json.loads(raw)
                    results.append(entry)
                except (json.JSONDecodeError, TypeError):
                    continue
            if len(results) >= limit:
                break

    results.sort(key=lambda x: x.get("failed_at", ""), reverse=True)
    return results[:limit]


def retry_webhook(event_key: str) -> bool:
    """
    Mark a failed event for retry: remove it from the DLQ and clear
    its idempotency record so it can be reprocessed on next delivery.

    Args:
        event_key: The event_key of the failed entry to retry.

    Returns:
        True if the entry was found and removed, False otherwise.
    """
    found = False

    redis = _get_redis()
    if redis is not None:
        try:
            # Scan all DLQ lists for the matching entry
            cursor_keys = redis.keys(f"{_DLQ_REDIS_PREFIX}*")
            for rkey in cursor_keys:
                rkey_str = rkey.decode() if isinstance(rkey, bytes) else rkey
                entries = redis.lrange(rkey_str, 0, -1)
                for raw in entries:
                    try:
                        entry = json.loads(raw)
                        if entry.get("event_key") == event_key:
                            redis.lrem(rkey_str, 1, raw)
                            found = True
                            break
                    except (json.JSONDecodeError, TypeError):
                        continue
                if found:
                    break

            # Clear the idempotency key so the event can be reprocessed
            if found:
                # The lightweight layer uses "webhook:idem:{provider}:{event_key}"
                # but event_key here is already the full composite key.
                # Try removing both possible Redis key formats.
                redis.delete(f"webhook:idem:{event_key}")
                logger.info("Webhook DLQ [redis]: removed %s for retry", event_key[:80])
                return True

        except Exception as e:
            logger.warning("Webhook DLQ: Redis retry error, falling back to memory: %s", e)

    # In-memory fallback
    with _dlq_lock:
        for prov, dq in _dlq_store.items():
            for i, raw in enumerate(list(dq)):
                try:
                    entry = json.loads(raw)
                    if entry.get("event_key") == event_key:
                        dq.remove(raw)
                        found = True
                        break
                except (json.JSONDecodeError, TypeError):
                    continue
            if found:
                break

    # Clear in-memory idempotency cache
    if found:
        with _seen_lock:
            # Try both possible key formats
            _seen_events.pop(f"webhook:idem:{event_key}", None)
            # Also try with provider prefix already included
            for k in list(_seen_events.keys()):
                if event_key in k:
                    _seen_events.pop(k, None)
                    break
        logger.info("Webhook DLQ [memory]: removed %s for retry", event_key[:80])

    return found


# Backward-compatibility alias — some callers may use the DB-backed name
# for the lightweight check. Keep both names available.
check_duplicate_webhook = is_duplicate_webhook


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
