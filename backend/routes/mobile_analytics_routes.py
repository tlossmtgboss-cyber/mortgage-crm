"""
Mobile Analytics Routes

POST /api/v1/analytics/mobile — Receive batched mobile analytics events

Lightweight log-sink endpoint for the frontend mobileAnalytics.js service.
Events are logged for observability; no database storage yet.
"""

import logging

from fastapi import APIRouter, Depends, Request

from routes.auth_deps import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["Mobile Analytics"],
    dependencies=[Depends(require_auth)],
)


@router.post("/mobile")
async def receive_mobile_analytics(request: Request):
    """Receive batched mobile analytics events. Currently logs only."""
    try:
        body = await request.json()
        events = body.get("events", [])
        session_info = body.get("session", {}) or {}
        session_id = session_info.get("sessionId", "unknown")
        platform = session_info.get("platform", "unknown")

        logger.info(
            "[MobileAnalytics] Received %d events | session=%s platform=%s",
            len(events),
            session_id,
            platform,
        )
        return {"success": True, "received": len(events)}
    except Exception as e:
        logger.warning("[MobileAnalytics] Parse error: %s", e)
        return {"success": True, "received": 0}
