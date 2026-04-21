"""
03-auth/backend/tokens.py

Single source of truth for auth tokens. Replaces:
  - backend/app/auth/tokens.py (RS256 current)
  - backend/app/main.py legacy auth
  - backend/app/salesforce/*.py HS256 JWT

All token minting and verification goes through this module. RS256 everywhere.
Refresh tokens are opaque random strings stored in Redis, not JWTs.

Drop-in: backend/app/auth/tokens.py
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from cryptography.hazmat.primitives import serialization

# --- Key material loaded once at startup --------------------------------------

_PRIVATE_KEY_PEM = os.environ.get("JWT_PRIVATE_KEY", "").encode()
_PUBLIC_KEY_PEM = os.environ.get("JWT_PUBLIC_KEY", "").encode()

if not _PRIVATE_KEY_PEM or not _PUBLIC_KEY_PEM:
    # Startup validation (02-encryption/startup.py) will catch this too, but
    # fail at import so import errors surface in tests.
    raise RuntimeError("JWT_PRIVATE_KEY and JWT_PUBLIC_KEY must be set (PEM-encoded RSA)")

_PRIVATE_KEY = serialization.load_pem_private_key(_PRIVATE_KEY_PEM, password=None)
_PUBLIC_KEY = serialization.load_pem_public_key(_PUBLIC_KEY_PEM)

_ALGO = "RS256"
_ISSUER = "perennia-ai"
_AUDIENCE = "perennia-api"


# --- Token shapes -------------------------------------------------------------

@dataclass(frozen=True)
class AccessTokenClaims:
    sub: str  # user_id
    role: str  # RBAC role
    org_id: str
    session_id: str  # ties to refresh token family
    jti: str  # for revocation
    iat: int
    exp: int
    token_type: Literal["access"] = "access"


@dataclass(frozen=True)
class RefreshTokenRecord:
    token: str  # opaque, urlsafe
    user_id: str
    session_id: str
    family_id: str  # rotation family — compromise detection
    issued_at: int
    expires_at: int
    device_fingerprint: str | None


# --- Durations ----------------------------------------------------------------

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=7)
# Sliding: each use extends by this amount, capped at absolute TTL.
REFRESH_ABSOLUTE_MAX = timedelta(days=30)


# --- Minting ------------------------------------------------------------------

def mint_access_token(
    *,
    user_id: str,
    role: str,
    org_id: str,
    session_id: str,
) -> tuple[str, AccessTokenClaims]:
    now = datetime.now(timezone.utc)
    claims = AccessTokenClaims(
        sub=user_id,
        role=role,
        org_id=org_id,
        session_id=session_id,
        jti=secrets.token_urlsafe(16),
        iat=int(now.timestamp()),
        exp=int((now + ACCESS_TOKEN_TTL).timestamp()),
    )
    encoded = jwt.encode(
        {
            "sub": claims.sub,
            "role": claims.role,
            "org_id": claims.org_id,
            "session_id": claims.session_id,
            "jti": claims.jti,
            "iat": claims.iat,
            "exp": claims.exp,
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "token_type": "access",
        },
        _PRIVATE_KEY,
        algorithm=_ALGO,
    )
    return encoded, claims


def mint_refresh_token(
    *,
    user_id: str,
    session_id: str,
    family_id: str | None = None,
    device_fingerprint: str | None = None,
) -> RefreshTokenRecord:
    """
    Mint an opaque refresh token. NOT a JWT — stored in Redis, revocable.
    family_id groups a rotation chain so we can detect token theft.
    """
    now = int(time.time())
    return RefreshTokenRecord(
        token=secrets.token_urlsafe(48),
        user_id=user_id,
        session_id=session_id,
        family_id=family_id or secrets.token_urlsafe(16),
        issued_at=now,
        expires_at=now + int(REFRESH_TOKEN_TTL.total_seconds()),
        device_fingerprint=device_fingerprint,
    )


# --- Verification -------------------------------------------------------------

class TokenError(Exception):
    """Base for all token validation errors."""


class TokenExpired(TokenError):
    pass


class TokenInvalid(TokenError):
    pass


def verify_access_token(encoded: str) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            encoded,
            _PUBLIC_KEY,
            algorithms=[_ALGO],
            issuer=_ISSUER,
            audience=_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "jti", "session_id"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise TokenExpired("Access token expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenInvalid(f"Access token invalid: {e}") from e

    if payload.get("token_type") != "access":
        raise TokenInvalid("Not an access token")

    return AccessTokenClaims(
        sub=payload["sub"],
        role=payload["role"],
        org_id=payload["org_id"],
        session_id=payload["session_id"],
        jti=payload["jti"],
        iat=payload["iat"],
        exp=payload["exp"],
    )
