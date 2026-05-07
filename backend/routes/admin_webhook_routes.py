"""
Admin Webhook Routes
====================
Endpoints for inspecting and retrying failed webhook events from the
dead-letter queue.  Requires admin authentication.
"""

import logging
import os
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from middleware.webhook_idempotency import (
    get_failed_webhooks,
    get_webhook_stats,
    retry_webhook,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/webhooks", tags=["Admin Webhooks"])

_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def _verify_admin(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
) -> bool:
    """
    Verify admin access via one of:
      1. X-Admin-Key header matching ADMIN_API_KEY env var
      2. X-API-Key header matching ADMIN_API_KEY env var
      3. Valid admin JWT Bearer token
    """
    admin_key = _ADMIN_API_KEY or os.getenv("MIGRATION_ADMIN_KEY", "")
    if not admin_key:
        raise HTTPException(status_code=503, detail="Admin key not configured")

    # Check API key headers
    for provided in (x_admin_key, x_api_key):
        if provided and secrets.compare_digest(provided, admin_key):
            return True

    # Check JWT Bearer for admin user
    if authorization and authorization.startswith("Bearer "):
        try:
            from auth.tokens import verify_access_token
            payload = verify_access_token(authorization.replace("Bearer ", ""))
            if payload:
                email = payload.get("sub")
                if email:
                    from database import SessionLocal
                    from sqlalchemy import text
                    db = SessionLocal()
                    try:
                        row = db.execute(
                            text("SELECT is_admin FROM users WHERE email = :email"),
                            {"email": email},
                        ).fetchone()
                        if row and row[0]:
                            return True
                    finally:
                        db.close()
        except Exception as e:
            logger.debug("Admin JWT check failed: %s", e)

    raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/stats")
async def webhook_stats(
    _admin: bool = Depends(_verify_admin),
):
    """
    Return webhook health metrics: total processed, duplicates caught,
    average check latency, DLQ sizes per provider, and circuit breaker state.
    """
    return get_webhook_stats()


@router.get("/failed")
async def list_failed_webhooks(
    provider: Optional[str] = Query(None, description="Filter by provider (vapi, telnyx, stripe)"),
    limit: int = Query(50, ge=1, le=200, description="Max entries to return"),
    _admin: bool = Depends(_verify_admin),
):
    """
    List failed webhook events from the dead-letter queue.

    Returns newest-first. Optionally filter by provider name.
    """
    failed = get_failed_webhooks(provider=provider, limit=limit)
    return {
        "count": len(failed),
        "provider_filter": provider,
        "events": failed,
    }


@router.post("/retry/{event_key:path}")
async def retry_failed_webhook(
    event_key: str,
    _admin: bool = Depends(_verify_admin),
):
    """
    Remove a failed event from the DLQ and clear its idempotency record
    so it can be reprocessed on the next provider retry.

    The event_key should match the value from the ``/failed`` listing.
    """
    removed = retry_webhook(event_key)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"Event key not found in dead-letter queue: {event_key}",
        )
    return {
        "status": "retried",
        "event_key": event_key,
        "message": "Event removed from DLQ and idempotency cleared. "
                   "It will be reprocessed on the next provider retry.",
    }
