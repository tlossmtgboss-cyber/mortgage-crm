"""
Microsoft Graph Email OAuth Routes

Provides endpoints for connecting a Microsoft 365 account via OAuth2
and sending email through the Microsoft Graph API.

Endpoints (all under /api/v1/email/microsoft):
    GET  /connect      — Start OAuth2 flow (returns redirect URL)
    GET  /callback     — OAuth2 callback (exchanges code, stores tokens)
    GET  /status       — Check connection status
    POST /disconnect   — Deactivate Microsoft email connection
    POST /test         — Send a test email via Graph API

Registration:
    from routes.microsoft_email_routes import register_microsoft_email_routes
    register_microsoft_email_routes(app)
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from db import get_db
from database.models.microsoft_email import MicrosoftEmailToken
from services.microsoft_graph_email import MicrosoftGraphEmailService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
_FRONTEND_URL = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/v1/email/microsoft",
    tags=["Microsoft Email"],
)

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class ConnectResponse(BaseModel):
    authorization_url: str


class StatusResponse(BaseModel):
    connected: bool
    email_address: str | None = None
    connected_at: str | None = None


class DisconnectResponse(BaseModel):
    success: bool
    message: str


class TestEmailResponse(BaseModel):
    success: bool
    message: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_state_token(user_id: int, org_id: int) -> str:
    """Create a short-lived JWT encoding the user/org for the OAuth callback."""
    payload = {
        "user_id": user_id,
        "org_id": org_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "purpose": "microsoft_email_oauth",
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm="HS256")


def _decode_state_token(state: str) -> dict:
    """Decode and validate the OAuth state JWT.

    Raises:
        HTTPException 400 on invalid/expired token.
    """
    try:
        payload = jwt.decode(state, _SECRET_KEY, algorithms=["HS256"])
        if payload.get("purpose") != "microsoft_email_oauth":
            raise jwt.InvalidTokenError("wrong purpose")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="OAuth state token expired. Please try connecting again.")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=400, detail=f"Invalid OAuth state token: {e}")


def _get_org_id(user) -> int:
    """Extract organization_id from user, raising 400 if absent."""
    org_id = getattr(user, "organization_id", None)
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with an organization",
        )
    return org_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/connect", response_model=ConnectResponse)
async def microsoft_email_connect(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start the Microsoft OAuth2 flow.

    Returns the authorization URL that the frontend should redirect the
    user's browser to.
    """
    org_id = _get_org_id(user)
    state = _create_state_token(user.id, org_id)
    auth_url = MicrosoftGraphEmailService.get_authorization_url(state)
    logger.info("Microsoft email OAuth initiated for user %d, org %d", user.id, org_id)
    return ConnectResponse(authorization_url=auth_url)


@router.get("/callback")
async def microsoft_email_callback(
    code: str = Query(..., description="Authorization code from Microsoft"),
    state: str = Query(..., description="State parameter for CSRF validation"),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Handle the OAuth2 callback from Microsoft.

    Exchanges the authorization code for tokens, fetches the user's
    profile to get their email, and stores everything in the database.
    Redirects the browser back to the frontend settings page.
    """
    # Handle Microsoft-side errors (user denied consent, etc.)
    if error:
        logger.warning("Microsoft OAuth error: %s — %s", error, error_description)
        return RedirectResponse(
            url=f"{_FRONTEND_URL}/settings/email?error={error}",
            status_code=302,
        )

    # Validate state
    payload = _decode_state_token(state)
    user_id = payload["user_id"]
    org_id = payload["org_id"]

    # Exchange code for tokens
    try:
        token_data = MicrosoftGraphEmailService.exchange_code_for_tokens(code)
    except ValueError as e:
        logger.error("Token exchange failed for user %d: %s", user_id, str(e))
        return RedirectResponse(
            url=f"{_FRONTEND_URL}/settings/email?error=token_exchange_failed",
            status_code=302,
        )

    # Fetch user profile to get email address
    try:
        profile = MicrosoftGraphEmailService.get_user_profile(token_data["access_token"])
    except ValueError as e:
        logger.error("Profile fetch failed for user %d: %s", user_id, str(e))
        return RedirectResponse(
            url=f"{_FRONTEND_URL}/settings/email?error=profile_fetch_failed",
            status_code=302,
        )

    email_address = profile.get("mail") or profile.get("userPrincipalName", "")
    if not email_address:
        logger.error("No email found in Microsoft profile for user %d", user_id)
        return RedirectResponse(
            url=f"{_FRONTEND_URL}/settings/email?error=no_email_in_profile",
            status_code=302,
        )

    now = datetime.now(timezone.utc)
    expires_in = token_data.get("expires_in", 3600)
    token_expiry = now + timedelta(seconds=expires_in)

    # Upsert token record (deactivate any existing, then create new)
    existing = (
        db.query(MicrosoftEmailToken)
        .filter(
            MicrosoftEmailToken.organization_id == org_id,
            MicrosoftEmailToken.email_address == email_address,
        )
        .first()
    )

    if existing:
        existing.user_id = user_id
        existing.access_token = token_data["access_token"]
        existing.refresh_token = token_data["refresh_token"]
        existing.token_expiry = token_expiry
        existing.tenant_id = profile.get("id")
        existing.is_active = True
        existing.updated_at = now
    else:
        new_token = MicrosoftEmailToken(
            organization_id=org_id,
            user_id=user_id,
            email_address=email_address,
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            token_expiry=token_expiry,
            tenant_id=profile.get("id"),
            connected_at=now,
            is_active=True,
        )
        db.add(new_token)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to persist Microsoft email token for user %d: %s", user_id, str(e))
        return RedirectResponse(
            url=f"{_FRONTEND_URL}/settings/email?error=db_error",
            status_code=302,
        )

    logger.info(
        "Microsoft email connected for user %d, org %d, email %s",
        user_id,
        org_id,
        _mask(email_address),
    )
    return RedirectResponse(
        url=f"{_FRONTEND_URL}/settings/email?connected=true",
        status_code=302,
    )


@router.get("/status", response_model=StatusResponse)
async def microsoft_email_status(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check whether the organization has an active Microsoft email connection."""
    org_id = _get_org_id(user)

    record = (
        db.query(MicrosoftEmailToken)
        .filter(
            MicrosoftEmailToken.organization_id == org_id,
            MicrosoftEmailToken.is_active.is_(True),
        )
        .first()
    )

    if not record:
        return StatusResponse(connected=False)

    return StatusResponse(
        connected=True,
        email_address=record.email_address,
        connected_at=record.connected_at.isoformat() if record.connected_at else None,
    )


@router.post("/disconnect", response_model=DisconnectResponse)
async def microsoft_email_disconnect(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivate the Microsoft email connection for this organization."""
    org_id = _get_org_id(user)

    records = (
        db.query(MicrosoftEmailToken)
        .filter(
            MicrosoftEmailToken.organization_id == org_id,
            MicrosoftEmailToken.is_active.is_(True),
        )
        .all()
    )

    if not records:
        raise HTTPException(status_code=404, detail="No active Microsoft email connection found")

    for record in records:
        record.is_active = False
        record.updated_at = datetime.now(timezone.utc)

    db.commit()
    logger.info("Microsoft email disconnected for org %d by user %d", org_id, user.id)
    return DisconnectResponse(success=True, message="Microsoft email disconnected successfully")


@router.post("/test", response_model=TestEmailResponse)
async def microsoft_email_test(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a test email to the current user via Microsoft Graph.

    Uses the stored tokens for the org to send a brief test message.
    """
    org_id = _get_org_id(user)
    user_email = getattr(user, "email", None)
    if not user_email:
        raise HTTPException(status_code=400, detail="User has no email address on file")

    # Get a valid access token (auto-refreshes if needed)
    try:
        access_token, from_email = MicrosoftGraphEmailService.get_valid_access_token(db, org_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = MicrosoftGraphEmailService.send_email(
        access_token=access_token,
        to_email=user_email,
        subject="Perennia AI — Microsoft Email Test",
        html_content=(
            "<h2>Email Integration Active</h2>"
            "<p>This test message confirms that your Microsoft 365 email "
            "integration with Perennia AI is working correctly.</p>"
            "<p style='color:#888;font-size:12px;'>Sent via Microsoft Graph API</p>"
        ),
        from_email=from_email,
    )

    if result.get("success"):
        return TestEmailResponse(success=True, message=f"Test email sent to {user_email}")

    return TestEmailResponse(
        success=False,
        message="Failed to send test email",
        error=result.get("error", "Unknown error"),
    )


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


def _mask(email: str) -> str:
    """Mask email for logging: 'user@example.com' -> 'u***@example.com'."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_microsoft_email_routes(app):
    """Register the Microsoft email router with the FastAPI application."""
    app.include_router(router)
