"""
03-auth/backend/routes.py

Auth endpoints:
  POST /auth/login     — credentials in, cookies out
  POST /auth/refresh   — rotates refresh token, issues new access
  POST /auth/logout    — clears cookies + revokes session
  POST /auth/logout-all — revokes every session for user

Rate limiting: slowapi on all auth endpoints (finding gap: no rate limiting on
auth). Tighter limits on login than refresh.

Drop-in: backend/app/auth/routes.py
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    ACCESS_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    get_current_user,
)
from app.auth.password import verify_password
from app.auth.refresh_store import RefreshStore
from app.auth.tokens import (
    ACCESS_TOKEN_TTL,
    REFRESH_TOKEN_TTL,
    mint_access_token,
    mint_refresh_token,
)
from app.core.db import get_async_session
from app.core.redis import get_redis
from app.models.user import User
from app.services.audit import audit_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Shared limiter — register once in main.py and import here.
limiter = Limiter(key_func=get_remote_address)

COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", "")  # e.g. ".perennia.ai"
IS_PROD = os.environ.get("ENV") == "production"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class LoginResponse(BaseModel):
    user_id: str
    role: str
    org_id: str
    expires_in: int  # seconds until access token expiry


def _set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
) -> None:
    common = {
        "domain": COOKIE_DOMAIN or None,
        "secure": IS_PROD,
        "httponly": True,
        "samesite": "strict" if IS_PROD else "lax",
        "path": "/",
    }

    response.set_cookie(
        ACCESS_COOKIE_NAME,
        access_token,
        max_age=int(ACCESS_TOKEN_TTL.total_seconds()),
        **common,
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
        # Refresh cookie scoped to /auth so it isn't sent on every request
        **{**common, "path": "/auth"},
    )
    # CSRF cookie is READABLE by JS — frontend mirrors it in X-CSRF-Token header
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
        domain=COOKIE_DOMAIN or None,
        secure=IS_PROD,
        httponly=False,  # intentional — JS reads it
        samesite="strict" if IS_PROD else "lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    for name, path in [
        (ACCESS_COOKIE_NAME, "/"),
        (REFRESH_COOKIE_NAME, "/auth"),
        (CSRF_COOKIE_NAME, "/"),
    ]:
        response.delete_cookie(
            name,
            domain=COOKIE_DOMAIN or None,
            path=path,
        )


def _device_fingerprint(request: Request) -> str:
    """
    Weak binding — not a replacement for actual device attestation, but raises
    the cost of stolen refresh token replay from a different network.
    """
    ua = request.headers.get("user-agent", "")
    accept_lang = request.headers.get("accept-language", "")
    return hashlib.sha256(f"{ua}|{accept_lang}".encode()).hexdigest()


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute;20/hour")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    redis=Depends(get_redis),
) -> LoginResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Constant-time failure — run a dummy password check even if user is None
    # so response timing doesn't leak account existence.
    if user is None:
        verify_password(body.password, "$2b$12$" + "x" * 53)
        await audit_event(
            db, event_type="LOGIN_FAILED_NO_USER", actor_email=body.email, ip=request.client.host
        )
        raise HTTPException(status_code=401, detail="invalid_credentials")

    if not verify_password(body.password, user.password_hash):
        await audit_event(
            db, event_type="LOGIN_FAILED_BAD_PASSWORD", actor_id=user.id, ip=request.client.host
        )
        raise HTTPException(status_code=401, detail="invalid_credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="account_disabled")

    # MFA check — if enrolled, require a second factor endpoint call
    if user.mfa_enabled and not body.password:
        # In practice: return a partial-auth token, require /auth/mfa/verify next.
        # Stub here — full MFA flow is its own module.
        raise HTTPException(status_code=428, detail="mfa_required")

    session_id = secrets.token_urlsafe(16)
    access_token, claims = mint_access_token(
        user_id=str(user.id),
        role=user.role,
        org_id=str(user.org_id),
        session_id=session_id,
    )
    refresh_record = mint_refresh_token(
        user_id=str(user.id),
        session_id=session_id,
        device_fingerprint=_device_fingerprint(request),
    )
    await RefreshStore(redis).store(refresh_record)

    csrf_token = secrets.token_urlsafe(32)
    _set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=refresh_record.token,
        csrf_token=csrf_token,
    )

    await audit_event(
        db,
        event_type="USER_LOGIN",
        actor_id=user.id,
        ip=request.client.host,
        metadata={"session_id": session_id},
    )

    return LoginResponse(
        user_id=str(user.id),
        role=user.role,
        org_id=str(user.org_id),
        expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
    )


@router.post("/refresh")
@limiter.limit("30/minute")
async def refresh(
    request: Request,
    response: Response,
    redis=Depends(get_redis),
    db: Annotated[AsyncSession, Depends(get_async_session)] = None,
):
    presented = request.cookies.get(REFRESH_COOKIE_NAME)
    if not presented:
        raise HTTPException(status_code=401, detail="missing_refresh_token")

    store = RefreshStore(redis)
    new_record = await store.rotate(
        presented,
        device_fingerprint=_device_fingerprint(request),
    )
    if new_record is None:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="refresh_failed")

    # Load user to get current role (could have changed since last login)
    result = await db.execute(select(User).where(User.id == new_record.user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        await store.revoke_session(new_record.session_id)
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="user_invalid")

    access_token, _ = mint_access_token(
        user_id=str(user.id),
        role=user.role,
        org_id=str(user.org_id),
        session_id=new_record.session_id,
    )
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME) or secrets.token_urlsafe(32)

    _set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=new_record.token,
        csrf_token=csrf_token,
    )

    return {"expires_in": int(ACCESS_TOKEN_TTL.total_seconds())}


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    redis=Depends(get_redis),
    db: Annotated[AsyncSession, Depends(get_async_session)] = None,
):
    claims = getattr(user, "_access_claims", None)
    if claims:
        store = RefreshStore(redis)
        await store.revoke_session(claims.session_id)

        # Also delete the current refresh token if present
        refresh = request.cookies.get(REFRESH_COOKIE_NAME)
        if refresh:
            await redis.delete(f"refresh:{refresh}")

        await audit_event(
            db,
            event_type="USER_LOGOUT",
            actor_id=user.id,
            ip=request.client.host,
            metadata={"session_id": claims.session_id},
        )

    _clear_auth_cookies(response)
    return Response(status_code=204)


@router.post("/logout-all", status_code=204)
async def logout_all(
    request: Request,
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    redis=Depends(get_redis),
    db: Annotated[AsyncSession, Depends(get_async_session)] = None,
):
    store = RefreshStore(redis)
    await store.revoke_all_user_sessions(str(user.id))
    await audit_event(
        db,
        event_type="USER_LOGOUT_ALL",
        actor_id=user.id,
        ip=request.client.host,
    )
    _clear_auth_cookies(response)
    return Response(status_code=204)
