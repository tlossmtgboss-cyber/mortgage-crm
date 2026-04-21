"""
03-auth/backend/dependencies.py

Async auth dependency for FastAPI. Reads access token from httpOnly cookie,
validates it, loads user via ASYNC SQLAlchemy (fixes finding #5).

Drop-in: backend/app/auth/dependencies.py
Replaces the synchronous get_current_user that was blocking the event loop.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.refresh_store import RefreshStore
from app.auth.tokens import (
    AccessTokenClaims,
    TokenError,
    TokenExpired,
    verify_access_token,
)
from app.core.db import get_async_session
from app.core.redis import get_redis
from app.models.user import User

logger = logging.getLogger(__name__)

ACCESS_COOKIE_NAME = "perennia_access"
REFRESH_COOKIE_NAME = "perennia_refresh"
CSRF_COOKIE_NAME = "perennia_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Cookie"},
    )


async def get_access_claims(
    access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE_NAME)] = None,
    redis=Depends(get_redis),
) -> AccessTokenClaims:
    """
    Validates access cookie. Checks session revocation in Redis.
    Raises 401 with distinct details so frontend can handle refresh flow.
    """
    if not access_token:
        raise _unauthorized("missing_access_token")

    try:
        claims = verify_access_token(access_token)
    except TokenExpired:
        raise _unauthorized("access_token_expired")
    except TokenError as e:
        logger.warning("Invalid access token: %s", e)
        raise _unauthorized("invalid_access_token")

    store = RefreshStore(redis)
    if await store.is_session_revoked(claims.session_id):
        raise _unauthorized("session_revoked")

    return claims


async def get_current_user(
    claims: Annotated[AccessTokenClaims, Depends(get_access_claims)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """Load the user. ASYNC — does not block the event loop."""
    result = await db.execute(select(User).where(User.id == claims.sub))
    user = result.scalar_one_or_none()

    if user is None:
        raise _unauthorized("user_not_found")

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="account_disabled",
        )

    # Attach claim context for downstream (e.g. RBAC checks)
    user._access_claims = claims  # type: ignore[attr-defined]
    return user


# --- RBAC helpers -------------------------------------------------------------

def require_roles(*allowed_roles: str):
    """
    Usage:
        @router.get("/admin/...")
        async def admin_route(user = Depends(require_roles("admin", "super_admin"))):
            ...
    """
    async def _check(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        claims = getattr(user, "_access_claims", None)
        role = claims.role if claims else getattr(user, "role", None)
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient_role",
            )
        return user

    return _check


# --- CSRF protection (proper, not bypassed) -----------------------------------

async def verify_csrf(request: Request) -> None:
    """
    Double-submit CSRF check. Runs on all state-changing routes.

    Finding fix: previously, any request with an Authorization: Bearer header
    bypassed CSRF entirely — without validating the bearer value. This version
    uses cookie auth, so there's no Bearer bypass. The CSRF token is:
      - Issued as a readable cookie at login
      - Submitted by the frontend in X-CSRF-Token header on mutating requests
      - Compared to the cookie value (constant-time)
    """
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return

    # Exemption for webhook endpoints (they use HMAC signature verification instead)
    if request.url.path.startswith("/webhooks/"):
        return

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)

    if not cookie_token or not header_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="csrf_missing",
        )

    import hmac
    if not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="csrf_mismatch",
        )
