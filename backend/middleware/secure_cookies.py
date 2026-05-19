"""
Secure Cookie Authentication

Provides HttpOnly cookie-based authentication as a more secure alternative
to localStorage token storage. HttpOnly cookies are immune to XSS attacks.

Migration path:
1. Backend sets auth token in HttpOnly cookie on login
2. Backend also returns token in response body (for backward compatibility)
3. Frontend can gradually migrate to cookie-based auth
4. Eventually deprecate localStorage token storage
"""

import logging
from typing import Optional
from datetime import timedelta
from starlette.requests import Request
from starlette.responses import Response
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class SecureCookieConfig:
    """Configuration for secure cookie settings."""

    # Cookie names
    ACCESS_TOKEN_COOKIE = "access_token"
    REFRESH_TOKEN_COOKIE = "refresh_token"

    # Security settings (should be True in production)
    HTTPONLY = True  # Prevents JavaScript access (XSS protection)
    SECURE = True  # Only send over HTTPS
    SAMESITE = "Lax"  # Prevents CSRF in most cases

    # Expiration (matches token expiration)
    ACCESS_TOKEN_MAX_AGE = 15 * 60  # 15 minutes
    REFRESH_TOKEN_MAX_AGE = 7 * 24 * 60 * 60  # 7 days

    # Domain settings
    DOMAIN = None  # Set to your domain in production, None for same-origin
    PATH = "/"


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: Optional[str] = None,
    config: SecureCookieConfig = None,
):
    """
    Set authentication tokens in secure HttpOnly cookies.

    Args:
        response: FastAPI/Starlette response object
        access_token: JWT access token
        refresh_token: JWT refresh token (optional)
        config: Cookie configuration (uses defaults if not provided)
    """
    config = config or SecureCookieConfig()

    # Set access token cookie
    response.set_cookie(
        key=config.ACCESS_TOKEN_COOKIE,
        value=access_token,
        httponly=config.HTTPONLY,
        secure=config.SECURE,
        samesite=config.SAMESITE,
        max_age=config.ACCESS_TOKEN_MAX_AGE,
        domain=config.DOMAIN,
        path=config.PATH,
    )

    # Set refresh token cookie if provided
    if refresh_token:
        response.set_cookie(
            key=config.REFRESH_TOKEN_COOKIE,
            value=refresh_token,
            httponly=config.HTTPONLY,
            secure=config.SECURE,
            samesite=config.SAMESITE,
            max_age=config.REFRESH_TOKEN_MAX_AGE,
            domain=config.DOMAIN,
            path="/api/v1/auth/refresh",  # Only sent to refresh endpoint
        )

    logger.debug("Auth cookies set successfully")


def clear_auth_cookies(
    response: Response,
    config: SecureCookieConfig = None,
):
    """
    Clear authentication cookies (logout).

    Args:
        response: FastAPI/Starlette response object
        config: Cookie configuration
    """
    config = config or SecureCookieConfig()

    # Delete cookies by setting max_age to 0
    response.delete_cookie(
        key=config.ACCESS_TOKEN_COOKIE,
        path=config.PATH,
        domain=config.DOMAIN,
    )
    response.delete_cookie(
        key=config.REFRESH_TOKEN_COOKIE,
        path="/api/v1/auth/refresh",
        domain=config.DOMAIN,
    )

    logger.debug("Auth cookies cleared")


def get_token_from_request(
    request: Request,
    config: SecureCookieConfig = None,
) -> Optional[str]:
    """
    Extract authentication token from request.

    Checks in order:
    1. HttpOnly cookie (most secure)
    2. Authorization header (backward compatibility)

    Args:
        request: FastAPI/Starlette request object
        config: Cookie configuration

    Returns:
        JWT token string or None
    """
    config = config or SecureCookieConfig()

    # Try cookie first (most secure)
    token = request.cookies.get(config.ACCESS_TOKEN_COOKIE)
    if token:
        return token

    # Fall back to Authorization header (backward compatibility)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]  # Remove "Bearer " prefix

    return None


def get_refresh_token_from_request(
    request: Request,
    config: SecureCookieConfig = None,
) -> Optional[str]:
    """
    Extract refresh token from request.

    Args:
        request: FastAPI/Starlette request object
        config: Cookie configuration

    Returns:
        Refresh token string or None
    """
    config = config or SecureCookieConfig()

    # Try cookie first
    token = request.cookies.get(config.REFRESH_TOKEN_COOKIE)
    if token:
        return token

    # Fall back to request body (for backward compatibility)
    # This would need to be handled in the route itself

    return None


# Dependency for FastAPI routes
async def get_current_user_from_cookie(request: Request):
    """
    FastAPI dependency to get current user from secure cookie.

    Usage:
        @router.get("/protected")
        async def protected_route(user = Depends(get_current_user_from_cookie)):
            ...
    """
    from auth.tokens import verify_token

    token = get_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = verify_token(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    # This should be replaced with your actual user lookup
    from database import get_db
    from sqlalchemy.orm import Session

    db: Session = next(get_db())
    try:
        # Import here to avoid circular imports
        from models import User
        user = db.query(User).filter(User.id == token_data.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return user
    finally:
        db.close()


# Helper for login/logout responses
def create_login_response(
    content: dict,
    access_token: str,
    refresh_token: Optional[str] = None,
    status_code: int = 200,
) -> Response:
    """
    Create a login response with secure cookies set.

    Args:
        content: Response body content
        access_token: JWT access token
        refresh_token: JWT refresh token
        status_code: HTTP status code

    Returns:
        JSONResponse with cookies set
    """
    from fastapi.responses import JSONResponse
    import json

    response = JSONResponse(
        content=content,
        status_code=status_code,
    )
    set_auth_cookies(response, access_token, refresh_token)
    return response


def create_logout_response(
    content: dict = None,
    status_code: int = 200,
) -> Response:
    """
    Create a logout response with cookies cleared.

    Args:
        content: Response body content
        status_code: HTTP status code

    Returns:
        JSONResponse with cookies cleared
    """
    from fastapi.responses import JSONResponse

    response = JSONResponse(
        content=content or {"message": "Logged out successfully"},
        status_code=status_code,
    )
    clear_auth_cookies(response)
    return response
