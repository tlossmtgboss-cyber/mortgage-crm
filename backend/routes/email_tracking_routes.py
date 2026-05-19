"""Email open/click tracking routes — pixel, redirect, and stats endpoints."""
import logging
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response, RedirectResponse

from db import get_db
from services.email_tracking_service import (
    PIXEL_GIF, record_open, record_click, get_tracking_stats,
    verify_tracking_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/email-tracking", tags=["email-tracking"])


@router.get("/open/{tracking_id}.png")
async def track_open(tracking_id: str, request: Request, db=Depends(get_db), sig: str = Query("")):
    """Return 1x1 transparent GIF and log open event. No auth required.

    SEC-005: The `sig` query param must match the HMAC signature of the tracking_id.
    If missing or invalid, the pixel is still returned (to avoid broken images in
    email clients) but the open event is NOT recorded.
    """
    if not sig or not verify_tracking_signature(tracking_id, sig):
        logger.warning(
            "Invalid or missing tracking signature for open: tracking_id=%s",
            tracking_id,
        )
        # Return pixel but do not record — prevents spoofed open inflation
        return Response(content=PIXEL_GIF, media_type="image/gif",
                        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})
    try:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")
        record_open(db, tracking_id, ip=ip, user_agent=ua)
    except Exception as _exc:  # noqa: BLE001
        logger.debug(f"Failed to record open for {tracking_id}", exc_info=True)
    return Response(content=PIXEL_GIF, media_type="image/gif",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


@router.get("/click/{tracking_id}/{link_hash}")
async def track_click(tracking_id: str, link_hash: str, request: Request, db=Depends(get_db), sig: str = Query("")):
    """Log click event and redirect to original URL. No auth required.

    SEC-005: The `sig` query param must match the HMAC signature of the tracking_id.
    If missing or invalid, the click is NOT recorded but the user is still redirected
    to the root path to avoid a broken experience.
    """
    original_url = "/"
    if not sig or not verify_tracking_signature(tracking_id, sig):
        logger.warning(
            "Invalid or missing tracking signature for click: tracking_id=%s",
            tracking_id,
        )
        return RedirectResponse(url=original_url, status_code=302)
    try:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")
        result_url = record_click(db, tracking_id, link_hash, ip=ip, user_agent=ua)
        if result_url:
            original_url = result_url
    except Exception as _exc:  # noqa: BLE001
        logger.debug(f"Failed to record click for {tracking_id}/{link_hash}", exc_info=True)
    return RedirectResponse(url=original_url, status_code=302)


@router.get("/stats/{tracking_id}")
async def tracking_stats(tracking_id: str, db=Depends(get_db)):
    """Get tracking stats for an email. Auth required in production."""
    return get_tracking_stats(db, tracking_id)
