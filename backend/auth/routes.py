"""
Authentication Routes

Provides endpoints for:
- Token refresh with rotation
- Logout (token invalidation)
- Token introspection (for debugging/admin)

These routes use the new secure token system with RS256 support.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Cookie
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .tokens import (
    create_access_token,
    create_refresh_token,
    verify_token,
    token_blacklist,
    TokenType,
    TokenData,
    get_token_jti,
)
from .config import get_auth_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()


# =============================================================================
# Request/Response Models
# =============================================================================

class TokenResponse(BaseModel):
    """Response containing access and refresh tokens."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    refresh_token: Optional[str] = None


class RefreshRequest(BaseModel):
    """Request to refresh access token."""
    refresh_token: str


class LogoutRequest(BaseModel):
    """Request to logout and invalidate tokens."""
    refresh_token: Optional[str] = None
    all_devices: bool = False


class TokenInfo(BaseModel):
    """Token introspection response."""
    active: bool
    sub: Optional[str] = None
    token_type: Optional[str] = None
    exp: Optional[int] = None
    iat: Optional[int] = None
    jti: Optional[str] = None
    iss: Optional[str] = None
    aud: Optional[str] = None


# =============================================================================
# Token Refresh Endpoint
# =============================================================================

@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    request: RefreshRequest,
    response: Response,
):
    """
    Refresh access token using a valid refresh token.

    This implements token rotation:
    - Old refresh token is invalidated
    - New access and refresh tokens are issued
    - This limits the damage if a refresh token is stolen

    Args:
        request: Contains the refresh token

    Returns:
        New access token and refresh token
    """
    settings = get_auth_settings()

    # Verify the refresh token
    token_data = verify_token(
        request.refresh_token,
        expected_type=TokenType.REFRESH,
        check_blacklist=True,
    )

    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Blacklist the old refresh token (rotation)
    if settings.token_blacklist_enabled:
        token_blacklist.add(request.refresh_token, reason="token_rotation")

    # Create new tokens with same claims
    token_payload = {
        "sub": token_data.sub,
        "user_id": token_data.user_id,
        "tenant_id": token_data.tenant_id,
        "roles": token_data.roles,
    }

    # Remove None values
    token_payload = {k: v for k, v in token_payload.items() if v is not None}

    new_access_token = create_access_token(data=token_payload)
    new_refresh_token = create_refresh_token(data=token_payload)

    # Set refresh token as HttpOnly cookie for web clients
    if settings.require_secure_cookies:
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=True,
            samesite=settings.same_site_policy,
            max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        )

    logger.info(f"Token refreshed for user: {token_data.sub}")

    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        refresh_token=new_refresh_token,
    )


# =============================================================================
# Logout Endpoint
# =============================================================================

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    request_body: Optional[LogoutRequest] = None,
):
    """
    Logout and invalidate tokens.

    Options:
    - Invalidate current access token
    - Invalidate refresh token if provided
    - Invalidate all tokens for user (all_devices=true)

    Args:
        credentials: Bearer token from Authorization header
        request_body: Optional logout options
    """
    settings = get_auth_settings()
    access_token = credentials.credentials

    # Verify the access token to get user info
    token_data = verify_token(access_token, check_blacklist=False)

    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        )

    if settings.token_blacklist_enabled:
        # Blacklist the access token
        token_blacklist.add(access_token, reason="logout")

        # Blacklist refresh token if provided
        if request_body and request_body.refresh_token:
            token_blacklist.add(request_body.refresh_token, reason="logout")

        # Revoke all tokens for user if requested
        if request_body and request_body.all_devices and token_data.user_id:
            token_blacklist.revoke_all_for_user(token_data.user_id)
            logger.info(f"All tokens revoked for user {token_data.user_id}")

    # Clear refresh token cookie
    response.delete_cookie("refresh_token")

    logger.info(f"User logged out: {token_data.sub}")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Token Introspection (Admin/Debug)
# =============================================================================

@router.post("/introspect", response_model=TokenInfo)
async def introspect_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    token: Optional[str] = None,
):
    """
    Introspect a token to see its claims and validity.

    Can introspect:
    - The access token from Authorization header (default)
    - A specific token passed in request body

    This is useful for debugging and admin purposes.
    """
    token_to_check = token or credentials.credentials

    # Verify token
    token_data = verify_token(token_to_check, check_blacklist=True)

    if not token_data:
        return TokenInfo(active=False)

    return TokenInfo(
        active=True,
        sub=token_data.sub,
        token_type=token_data.token_type.value,
        exp=int(token_data.exp.timestamp()) if token_data.exp else None,
        iat=int(token_data.iat.timestamp()) if token_data.iat else None,
        jti=token_data.jti,
        iss=token_data.iss,
        aud=token_data.aud,
    )


# =============================================================================
# Token from Cookie (for web clients)
# =============================================================================

@router.post("/refresh-from-cookie", response_model=TokenResponse)
async def refresh_from_cookie(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
):
    """
    Refresh access token using refresh token from HttpOnly cookie.

    This is the preferred method for web applications as it:
    - Keeps the refresh token in an HttpOnly cookie (not accessible to JS)
    - Automatically includes the token on requests
    - Provides better protection against XSS attacks
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token cookie found",
        )

    # Reuse the main refresh logic
    return await refresh_tokens(
        RefreshRequest(refresh_token=refresh_token),
        response,
    )
