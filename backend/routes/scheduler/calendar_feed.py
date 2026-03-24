"""
Scheduler Calendar Feed Routes — iCalendar (ICS) feed subscription endpoints.

Endpoints:
  - GET    /feed/{token}.ics         Public ICS feed (token-authenticated, no login)
  - POST   /feed/generate-token      Generate a unique feed URL token (auth required)
  - POST   /feed/refresh-token       Refresh (re-issue) an expiring feed token (auth required)
  - DELETE /feed/revoke              Revoke the active feed token (auth required)
  - GET    /feed/status              Check if a feed is active (auth required)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import logging
import secrets

from routes.scheduler._helpers import get_current_user, _get_org_id, _audit_log
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# Token length: 32 bytes -> 43 chars URL-safe base64
_TOKEN_BYTES = 32

# Feed tokens expire after 90 days; users must refresh before expiry
_TOKEN_LIFETIME_DAYS = 90


# ============================================================================
# PUBLIC ENDPOINT — ICS FEED (no login required, token-authenticated)
# ============================================================================

@router.get("/feed/{token}.ics")
async def get_ics_feed(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Serve the iCalendar feed for the given token.

    This is a public endpoint — no Authorization header required.
    Authentication is via the URL token itself. Calendar clients
    (Apple Calendar, Google Calendar, Outlook) will poll this URL
    periodically to sync events.

    Returns Content-Type: text/calendar; charset=utf-8
    """
    from database.models.calendar_feed import CalendarFeedToken
    from services.ical_feed_service import generate_ical_feed

    # Validate token
    if not token or len(token) < 20:
        raise HTTPException(status_code=404, detail="Not found")

    feed_token = (
        db.query(CalendarFeedToken)
        .filter(
            CalendarFeedToken.token == token,
            CalendarFeedToken.is_active == True,
        )
        .first()
    )

    if not feed_token:
        raise HTTPException(status_code=404, detail="Calendar feed not found or revoked")

    # Check token expiration
    now = datetime.now(timezone.utc)
    if feed_token.expires_at is None or feed_token.expires_at < now:
        # Deactivate expired token
        try:
            feed_token.is_active = False
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to deactivate expired feed token: {e}")
            db.rollback()
        raise HTTPException(
            status_code=401,
            detail="Calendar feed link has expired. Please regenerate your feed URL in calendar settings.",
        )

    # Update access tracking (non-blocking — don't fail the request on tracking errors)
    try:
        feed_token.access_count = (feed_token.access_count or 0) + 1
        feed_token.last_accessed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to update feed access tracking: {e}")
        db.rollback()

    # Generate the ICS content
    try:
        ics_content = generate_ical_feed(
            db=db,
            user_id=feed_token.user_id,
            org_id=feed_token.organization_id,
            days_ahead=90,
            include_details=feed_token.include_details,
        )
    except Exception as e:
        logger.error(f"Failed to generate iCal feed for user {feed_token.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate calendar feed")

    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="perennia-calendar.ics"',
            # Cache for 5 minutes — calendar clients have their own refresh intervals
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


# ============================================================================
# GENERATE TOKEN (auth required)
# ============================================================================

@router.post("/feed/generate-token")
async def generate_feed_token(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Generate a new calendar feed URL token for the authenticated user.

    If the user already has an active token, it is revoked and a new one
    is generated (one active token per user).

    Body (optional):
        include_details: bool (default true) — if false, events show only busy/free
    """
    from database.models.calendar_feed import CalendarFeedToken

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    # Parse optional body
    include_details = True
    try:
        body = await request.json()
        include_details = body.get("include_details", True)
    except Exception as e:
        logger.debug(f"No JSON body for feed token request (using defaults): {e}")

    # Revoke any existing active tokens for this user
    existing_tokens = (
        db.query(CalendarFeedToken)
        .filter(
            CalendarFeedToken.user_id == user_id,
            CalendarFeedToken.organization_id == org_id,
            CalendarFeedToken.is_active == True,
        )
        .all()
    )
    for old_token in existing_tokens:
        old_token.is_active = False

    # Generate a new URL-safe token
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    expires_at = now + timedelta(days=_TOKEN_LIFETIME_DAYS)

    feed_token = CalendarFeedToken(
        organization_id=org_id,
        user_id=user_id,
        token=token,
        is_active=True,
        include_details=bool(include_details),
        expires_at=expires_at,
    )
    db.add(feed_token)
    db.flush()

    _audit_log(
        db, org_id, user_id, "created",
        "calendar_feed_token", feed_token.id,
        changes={
            "include_details": include_details,
            "replaced_count": len(existing_tokens),
            "expires_at": expires_at.isoformat(),
        },
        request=request,
    )
    db.commit()

    # Build the feed URLs
    base_url = _get_api_base_url(request)
    ics_path = f"/api/v1/scheduler/feed/{token}.ics"
    https_url = f"{base_url}{ics_path}"
    webcal_url = https_url.replace("https://", "webcal://").replace("http://", "webcal://")

    return {
        "token": token,
        "feed_url": https_url,
        "webcal_url": webcal_url,
        "include_details": feed_token.include_details,
        "created_at": feed_token.created_at.isoformat() if feed_token.created_at else None,
        "expires_at": expires_at.isoformat(),
        "expires_in_days": _TOKEN_LIFETIME_DAYS,
        "instructions": {
            "apple_calendar": f"Open this URL on your device: {webcal_url}",
            "google_calendar": f"Go to Google Calendar Settings > Add calendar > From URL > paste: {https_url}",
            "outlook": f"In Outlook, go to Add Calendar > Subscribe from web > paste: {https_url}",
        },
    }


# ============================================================================
# REFRESH TOKEN (auth required)
# ============================================================================

@router.post("/feed/refresh-token")
async def refresh_feed_token(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Refresh the authenticated user's calendar feed token.

    Issues a new token with a fresh 90-day expiration. The old token
    is revoked. Calendar clients will need to be updated with the new URL.
    This is equivalent to generate-token but explicitly intended for renewal.
    """
    from database.models.calendar_feed import CalendarFeedToken

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    # Find active token to preserve settings
    existing = (
        db.query(CalendarFeedToken)
        .filter(
            CalendarFeedToken.user_id == user_id,
            CalendarFeedToken.organization_id == org_id,
            CalendarFeedToken.is_active == True,
        )
        .first()
    )

    include_details = existing.include_details if existing else True

    # Revoke all existing tokens
    existing_tokens = (
        db.query(CalendarFeedToken)
        .filter(
            CalendarFeedToken.user_id == user_id,
            CalendarFeedToken.organization_id == org_id,
            CalendarFeedToken.is_active == True,
        )
        .all()
    )
    for old_token in existing_tokens:
        old_token.is_active = False

    # Generate new token with fresh expiration
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    expires_at = now + timedelta(days=_TOKEN_LIFETIME_DAYS)

    feed_token = CalendarFeedToken(
        organization_id=org_id,
        user_id=user_id,
        token=token,
        is_active=True,
        include_details=bool(include_details),
        expires_at=expires_at,
    )
    db.add(feed_token)
    db.flush()

    _audit_log(
        db, org_id, user_id, "refreshed",
        "calendar_feed_token", feed_token.id,
        changes={
            "replaced_count": len(existing_tokens),
            "expires_at": expires_at.isoformat(),
        },
        request=request,
    )
    db.commit()

    base_url = _get_api_base_url(request)
    ics_path = f"/api/v1/scheduler/feed/{token}.ics"
    https_url = f"{base_url}{ics_path}"
    webcal_url = https_url.replace("https://", "webcal://").replace("http://", "webcal://")

    return {
        "token": token,
        "feed_url": https_url,
        "webcal_url": webcal_url,
        "include_details": feed_token.include_details,
        "created_at": feed_token.created_at.isoformat() if feed_token.created_at else None,
        "expires_at": expires_at.isoformat(),
        "expires_in_days": _TOKEN_LIFETIME_DAYS,
        "message": "Feed token refreshed. Update your calendar subscription with the new URL.",
    }


# ============================================================================
# REVOKE TOKEN (auth required)
# ============================================================================

@router.delete("/feed/revoke")
async def revoke_feed_token(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Revoke the authenticated user's active calendar feed token.
    After revocation, any calendar clients using the old URL will
    receive a 404 on their next sync attempt.
    """
    from database.models.calendar_feed import CalendarFeedToken

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    active_tokens = (
        db.query(CalendarFeedToken)
        .filter(
            CalendarFeedToken.user_id == user_id,
            CalendarFeedToken.organization_id == org_id,
            CalendarFeedToken.is_active == True,
        )
        .all()
    )

    if not active_tokens:
        raise HTTPException(status_code=404, detail="No active calendar feed to revoke")

    revoked_count = 0
    for token_obj in active_tokens:
        token_obj.is_active = False
        revoked_count += 1

    _audit_log(
        db, org_id, user_id, "revoked",
        "calendar_feed_token", None,
        changes={"revoked_count": revoked_count},
        request=request,
    )
    db.commit()

    return {
        "success": True,
        "revoked_count": revoked_count,
        "message": "Calendar feed has been revoked. Calendar clients will stop receiving updates.",
    }


# ============================================================================
# FEED STATUS (auth required)
# ============================================================================

@router.get("/feed/status")
async def get_feed_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Check whether the authenticated user has an active calendar feed
    and return its metadata (URL, access stats, etc.).
    """
    from database.models.calendar_feed import CalendarFeedToken

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_id = getattr(user, "id", None)

    feed_token = (
        db.query(CalendarFeedToken)
        .filter(
            CalendarFeedToken.user_id == user_id,
            CalendarFeedToken.organization_id == org_id,
            CalendarFeedToken.is_active == True,
        )
        .first()
    )

    if not feed_token:
        return {
            "is_active": False,
            "feed_url": None,
            "webcal_url": None,
            "include_details": None,
            "access_count": 0,
            "last_accessed_at": None,
            "created_at": None,
            "expires_at": None,
            "is_expired": False,
            "days_until_expiry": None,
        }

    base_url = _get_api_base_url(request)
    ics_path = f"/api/v1/scheduler/feed/{feed_token.token}.ics"
    https_url = f"{base_url}{ics_path}"
    webcal_url = https_url.replace("https://", "webcal://").replace("http://", "webcal://")

    # Calculate expiration status
    now = datetime.now(timezone.utc)
    is_expired = feed_token.expires_at is None or feed_token.expires_at < now
    days_until_expiry = None
    if feed_token.expires_at and not is_expired:
        days_until_expiry = (feed_token.expires_at - now).days

    return {
        "is_active": True and not is_expired,
        "feed_url": https_url,
        "webcal_url": webcal_url,
        "include_details": feed_token.include_details,
        "access_count": feed_token.access_count or 0,
        "last_accessed_at": feed_token.last_accessed_at.isoformat() if feed_token.last_accessed_at else None,
        "created_at": feed_token.created_at.isoformat() if feed_token.created_at else None,
        "expires_at": feed_token.expires_at.isoformat() if feed_token.expires_at else None,
        "is_expired": is_expired,
        "days_until_expiry": days_until_expiry,
    }


# ============================================================================
# HELPERS
# ============================================================================

def _get_api_base_url(request: Request) -> str:
    """
    Derive the API base URL from the request.
    In production, use the known API domain. In dev, use request host.
    """
    import os
    api_domain = os.getenv("API_DOMAIN", "")
    if api_domain:
        return f"https://{api_domain}"

    # Fallback: derive from request
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost"))
    return f"{scheme}://{host}"
