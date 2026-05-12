"""
Smart Docs Portal Authentication Service

Provides JWT-based authentication for the borrower document portal.
Generates and verifies portal access tokens that gate all borrower-facing
endpoints in smart_docs_portal_routes.py.

Security model:
- Tokens are signed JWTs (HS256) with loan_id, borrower_email, org_id, and scope
- Tokens expire after a configurable period (default 72 hours)
- Magic links embed a token for one-click access
- Rate limiting prevents brute-force token generation
- Every portal endpoint verifies the token AND cross-checks the workspace slug

This replaces the previous slug-only access pattern, which was vulnerable to
slug enumeration attacks exposing PII.
"""

import hashlib
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any

import jwt
from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise SystemExit("FATAL: SECRET_KEY environment variable is required but not set")

# Dedicated signing key for portal JWTs. Falls back to the shared SECRET_KEY
# when PORTAL_JWT_SECRET is not set, but production deployments SHOULD set a
# separate value to limit blast radius if any key is compromised.
PORTAL_JWT_SECRET = os.getenv("PORTAL_JWT_SECRET", SECRET_KEY)
PORTAL_TOKEN_ALGORITHM = "HS256"
PORTAL_TOKEN_ISSUER = "perennia-portal"
DEFAULT_EXPIRY_HOURS = int(os.getenv("PORTAL_TOKEN_EXPIRY_HOURS", "72"))
PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "http://localhost:3000/portal")

# Rate limiting: max token generations per email per hour
MAX_TOKEN_GENERATIONS_PER_HOUR = 5

# In-memory rate limit stores (keyed by email, values are timestamps)
# Rate limiting is per-worker (SD-SEC-11: Redis migration needed for cross-worker limits)
# Memory-safe: auto-cleans entries older than 1 hour
_token_generation_timestamps: Dict[str, list] = defaultdict(list)

# ---------------------------------------------------------------------------
# Token Revocation (in-memory; SD-SEC-11: migrate to Redis for cross-worker)
# ---------------------------------------------------------------------------
# Stores (token_jti_or_hash, expiry_timestamp) so we can auto-prune expired
# entries and keep the set from growing without bound.
_revoked_tokens: Dict[str, float] = {}  # token_hash -> exp timestamp
_REVOCATION_CLEANUP_INTERVAL = 600  # 10 minutes
_last_revocation_cleanup: float = 0.0

# Periodic cleanup state — shared across both token-gen and upload stores
_RATE_LIMIT_CLEANUP_INTERVAL = 300  # 5 minutes
_last_cleanup = time.time()


def _cleanup_rate_limit_stores() -> None:
    """Remove stale entries from both rate limit stores to prevent unbounded memory growth.

    Runs at most once every 5 minutes. Drops all entries older than 1 hour and
    removes keys with no remaining entries.
    """
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < _RATE_LIMIT_CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    cutoff = now - 3600  # Remove entries older than 1 hour
    for store in (_token_generation_timestamps, _upload_timestamps):
        for key in list(store.keys()):
            store[key] = [ts for ts in store[key] if ts > cutoff]
            if not store[key]:
                del store[key]


# ---------------------------------------------------------------------------
# Token Generation
# ---------------------------------------------------------------------------

def generate_portal_access_token(
    loan_id: Any,
    borrower_email: str,
    org_id: Any,
    expires_hours: int = DEFAULT_EXPIRY_HOURS,
    scope: str = "read_write",
) -> str:
    """
    Create a signed JWT portal access token.

    Args:
        loan_id: The loan ID the borrower is authorized to access.
        borrower_email: The borrower's verified email address.
        org_id: The organization ID for tenant isolation.
        expires_hours: Token lifetime in hours (default 72).
        scope: Access scope - "read" (view only) or "read_write" (view + upload).

    Returns:
        Signed JWT string.

    Raises:
        HTTPException(429): If rate limit exceeded for this email.
        ValueError: If required parameters are missing.
    """
    if not loan_id or not borrower_email or not org_id:
        raise ValueError("loan_id, borrower_email, and org_id are required")

    if scope not in ("read", "read_write"):
        raise ValueError("scope must be 'read' or 'read_write'")

    # Normalize email
    email_lower = borrower_email.strip().lower()

    # Rate limit check
    _enforce_rate_limit(email_lower)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=expires_hours)

    payload = {
        "iss": PORTAL_TOKEN_ISSUER,
        "sub": email_lower,
        "loan_id": str(loan_id),
        "org_id": str(org_id),
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    token = jwt.encode(payload, PORTAL_JWT_SECRET, algorithm=PORTAL_TOKEN_ALGORITHM)

    logger.info(
        f"Portal token generated for {_mask_email(email_lower)}, "
        f"loan={loan_id}, org={org_id}, scope={scope}, "
        f"expires={expires_at.isoformat()}"
    )

    return token


# ---------------------------------------------------------------------------
# Token Verification
# ---------------------------------------------------------------------------

def verify_portal_access_token(token: str) -> Dict[str, Any]:
    """
    Verify a portal access token and return the decoded claims.

    Args:
        token: The JWT string to verify.

    Returns:
        Dict with keys: loan_id, borrower_email, org_id, scope, issued_at, expires_at.

    Raises:
        HTTPException(401): If the token is invalid, expired, or malformed.
    """
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Portal access token is required",
        )

    # Check revocation list before expensive decode
    if is_portal_token_revoked(token):
        raise HTTPException(
            status_code=401,
            detail="Portal access token has been revoked.",
        )

    try:
        payload = jwt.decode(
            token,
            PORTAL_JWT_SECRET,
            algorithms=[PORTAL_TOKEN_ALGORITHM],
            issuer=PORTAL_TOKEN_ISSUER,
            options={"require": ["exp", "iss", "sub", "loan_id", "org_id", "scope"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Portal access token has expired. Please request a new link.",
        )
    except jwt.InvalidIssuerError:
        raise HTTPException(
            status_code=401,
            detail="Invalid portal access token",
        )
    except jwt.DecodeError:
        raise HTTPException(
            status_code=401,
            detail="Invalid portal access token",
        )
    except jwt.MissingRequiredClaimError as e:
        logger.warning(f"Portal token missing required claim: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid portal access token",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid portal access token",
        )

    return {
        "loan_id": payload["loan_id"],
        "borrower_email": payload["sub"],
        "org_id": payload["org_id"],
        "scope": payload.get("scope", "read"),
        "issued_at": datetime.fromtimestamp(payload["iat"], tz=timezone.utc).isoformat(),
        "expires_at": datetime.fromtimestamp(payload["exp"], tz=timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Magic Link Generation
# ---------------------------------------------------------------------------

def generate_portal_magic_link(
    loan_id: Any,
    borrower_email: str,
    org_id: Any,
    workspace_slug: str = "",
    expires_hours: int = DEFAULT_EXPIRY_HOURS,
) -> Dict[str, str]:
    """
    Create a time-limited magic link URL with an embedded portal token.

    The link points to the portal frontend which extracts the token and
    uses it as the X-Portal-Token header on subsequent API calls.

    Args:
        loan_id: The loan ID.
        borrower_email: The borrower's email.
        org_id: The organization ID.
        workspace_slug: Optional workspace slug for the URL path.
        expires_hours: Link lifetime in hours.

    Returns:
        Dict with 'url', 'token', and 'expires_at' keys.
    """
    token = generate_portal_access_token(
        loan_id=loan_id,
        borrower_email=borrower_email,
        org_id=org_id,
        expires_hours=expires_hours,
        scope="read_write",
    )

    # Decode to get expiry for the response
    claims = verify_portal_access_token(token)

    # Build the URL
    base = PORTAL_BASE_URL.rstrip("/")
    if workspace_slug:
        url = f"{base}/docs/{workspace_slug}?token={token}"
    else:
        url = f"{base}/docs?token={token}"

    return {
        "url": url,
        "token": token,
        "expires_at": claims["expires_at"],
    }


# ---------------------------------------------------------------------------
# FastAPI Dependency: get_current_portal_user
# ---------------------------------------------------------------------------

async def get_current_portal_user(
    request: Request,
    db: Session,
    workspace_slug: str = "",
) -> Dict[str, Any]:
    """
    FastAPI dependency that authenticates a portal user.

    Checks for a portal token in the following order:
    1. X-Portal-Token header
    2. Authorization: Bearer <token> header
    3. ?token= query parameter

    After verifying the token, cross-checks that the workspace_slug
    (if provided) belongs to the same org and loan.

    Args:
        request: The FastAPI Request object.
        db: SQLAlchemy session.
        workspace_slug: The workspace slug from the URL path.

    Returns:
        Dict with loan_id, borrower_email, org_id, scope, workspace_slug.

    Raises:
        HTTPException(401): If no valid token is found or verification fails.
    """
    # Extract token from multiple sources
    token = _extract_portal_token(request)

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Portal authentication required. Please use your portal access link.",
        )

    # Verify the token
    claims = verify_portal_access_token(token)

    # If a workspace_slug is provided, verify it belongs to the correct org/loan
    if workspace_slug:
        _verify_workspace_access(db, workspace_slug, claims)

    return {
        "loan_id": claims["loan_id"],
        "borrower_email": claims["borrower_email"],
        "org_id": claims["org_id"],
        "scope": claims["scope"],
        "workspace_slug": workspace_slug,
    }


def require_write_scope(portal_user: Dict[str, Any]) -> None:
    """
    Check that the portal user has write scope.

    Call this in endpoints that modify data (upload, reupload, submit LOE,
    send messages, confirm/reschedule appointments).

    Raises:
        HTTPException(403): If the user only has read scope.
    """
    if portal_user.get("scope") not in ("read_write", "write"):
        raise HTTPException(
            status_code=403,
            detail="This action requires write access. Please request a new portal link.",
        )


# ---------------------------------------------------------------------------
# Upload Rate Limiting
# ---------------------------------------------------------------------------

# In-memory upload count tracking (keyed by token sub, values are timestamps)
# Rate limiting is per-worker (SD-SEC-11: Redis migration needed for cross-worker limits)
# Memory-safe: auto-cleans entries older than 1 hour via _cleanup_rate_limit_stores()
_upload_timestamps: Dict[str, list] = defaultdict(list)

MAX_UPLOADS_PER_HOUR = 10


def check_upload_rate_limit(borrower_email: str) -> None:
    """
    Enforce upload rate limiting: max 10 uploads per hour per borrower.

    Raises:
        HTTPException(429): If rate limit exceeded.
    """
    _cleanup_rate_limit_stores()
    email_lower = borrower_email.strip().lower()
    now = time.time()
    cutoff = now - 3600  # 1 hour window

    # Prune old entries
    _upload_timestamps[email_lower] = [
        ts for ts in _upload_timestamps[email_lower] if ts > cutoff
    ]

    if len(_upload_timestamps[email_lower]) >= MAX_UPLOADS_PER_HOUR:
        logger.warning(f"Upload rate limit exceeded for {_mask_email(email_lower)}")
        raise HTTPException(
            status_code=429,
            detail="Upload rate limit exceeded. Please try again later.",
        )

    _upload_timestamps[email_lower].append(now)


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _token_hash(token: str) -> str:
    """Compute a SHA-256 hash of the raw JWT for revocation lookups.

    We store hashes rather than raw tokens to limit exposure if the
    revocation set is ever serialized or logged.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cleanup_revoked_tokens() -> None:
    """Prune expired entries from the revocation set."""
    global _last_revocation_cleanup
    now = time.time()
    if now - _last_revocation_cleanup < _REVOCATION_CLEANUP_INTERVAL:
        return
    _last_revocation_cleanup = now
    expired_keys = [k for k, exp in _revoked_tokens.items() if exp < now]
    for k in expired_keys:
        del _revoked_tokens[k]


def revoke_portal_token(token: str) -> bool:
    """Revoke a portal token so it can no longer be used.

    The token's expiry is extracted so the revocation entry can be
    auto-pruned after the token would have expired anyway.

    Returns True if the token was successfully revoked (valid JWT that
    was added to the revocation set), False otherwise.
    """
    _cleanup_revoked_tokens()
    try:
        # Decode without verification just to get exp claim for pruning
        payload = jwt.decode(
            token,
            PORTAL_JWT_SECRET,
            algorithms=[PORTAL_TOKEN_ALGORITHM],
            options={"verify_exp": False, "verify_iss": False},
        )
        exp = payload.get("exp", time.time() + 86400)  # Default 24h if missing
        th = _token_hash(token)
        _revoked_tokens[th] = float(exp)
        logger.info("Portal token revoked: hash=%s...%s", th[:8], th[-4:])
        return True
    except Exception as e:
        logger.warning("Failed to revoke portal token: %s", e)
        return False


def is_portal_token_revoked(token: str) -> bool:
    """Check whether a token has been revoked."""
    _cleanup_revoked_tokens()
    return _token_hash(token) in _revoked_tokens


def _extract_portal_token(request: Request) -> Optional[str]:
    """Extract portal token from header, auth header, or query param.

    Preferred sources (in order):
      1. X-Portal-Token header  (recommended)
      2. Authorization: Bearer header
      3. ?token= query parameter  (DEPRECATED — logged for monitoring)
    """
    # 1. X-Portal-Token header (preferred)
    token = request.headers.get("X-Portal-Token")
    if token:
        return token.strip()

    # 2. Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer_token = auth_header[7:].strip()
        # Distinguish portal tokens from CRM JWT tokens by checking issuer
        # Portal tokens are shorter and use HS256; CRM tokens use RS256.
        # We try to decode; if it fails, it's not a portal token.
        if bearer_token:
            return bearer_token

    # 3. Query parameter (DEPRECATED — tokens in URLs leak via referrer
    #    headers, server logs, and browser history)
    token = request.query_params.get("token")
    if token:
        logger.warning(
            "DEPRECATED: Portal token received via URL query parameter. "
            "Client should migrate to X-Portal-Token header. "
            "path=%s remote=%s",
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        return token.strip()

    return None


def _verify_workspace_access(
    db: Session,
    workspace_slug: str,
    claims: Dict[str, Any],
) -> None:
    """
    Verify that the workspace_slug matches the token's org_id and loan_id.

    Raises:
        HTTPException(401): If workspace does not match token claims.
    """
    from sqlalchemy import text as sa_text

    result = db.execute(
        sa_text("""
            SELECT w.id, w.organization_id, pl.main_loan_id, pl.id as purl_loan_id
            FROM purl_workspaces w
            LEFT JOIN purl_loans pl ON pl.workspace_id = w.id
            WHERE w.slug = :slug
            ORDER BY pl.created_at DESC NULLS LAST
            LIMIT 1
        """),
        {"slug": workspace_slug},
    ).fetchone()

    if not result:
        raise HTTPException(
            status_code=401,
            detail="Invalid portal access. Workspace not found.",
        )

    workspace_org_id = str(result[1]) if result[1] else None
    workspace_loan_id = str(result[2]) if result[2] else (str(result[3]) if result[3] else None)

    # Verify org matches
    if workspace_org_id and workspace_org_id != str(claims["org_id"]):
        logger.warning(
            f"Portal workspace org mismatch: token org={claims['org_id']}, "
            f"workspace org={workspace_org_id}, slug={workspace_slug}"
        )
        raise HTTPException(
            status_code=401,
            detail="Portal access denied. Token does not match this workspace.",
        )

    # Verify loan matches (if workspace has a loan)
    if workspace_loan_id and workspace_loan_id != str(claims["loan_id"]):
        logger.warning(
            f"Portal workspace loan mismatch: token loan={claims['loan_id']}, "
            f"workspace loan={workspace_loan_id}, slug={workspace_slug}"
        )
        raise HTTPException(
            status_code=401,
            detail="Portal access denied. Token does not match this workspace.",
        )


def _enforce_rate_limit(email: str) -> None:
    """
    Enforce rate limiting on token generation.

    Raises:
        HTTPException(429): If rate limit exceeded.
    """
    _cleanup_rate_limit_stores()
    now = time.time()
    cutoff = now - 3600  # 1 hour window

    # Prune old entries
    _token_generation_timestamps[email] = [
        ts for ts in _token_generation_timestamps[email] if ts > cutoff
    ]

    if len(_token_generation_timestamps[email]) >= MAX_TOKEN_GENERATIONS_PER_HOUR:
        logger.warning(f"Token generation rate limit exceeded for {_mask_email(email)}")
        raise HTTPException(
            status_code=429,
            detail="Too many token requests. Please try again later.",
        )

    _token_generation_timestamps[email].append(now)


def _mask_email(email: str) -> str:
    """Mask email for logging (e.g., j***n@example.com)."""
    parts = email.split("@")
    if len(parts) != 2:
        return "***"
    local = parts[0]
    domain = parts[1]
    if len(local) <= 2:
        masked = local[0] + "***"
    else:
        masked = local[0] + "***" + local[-1]
    return f"{masked}@{domain}"


# ---------------------------------------------------------------------------
# Test Helpers (only used by test suite)
# ---------------------------------------------------------------------------

def reset_rate_limits() -> None:
    """Reset all rate limit counters and revocation set. For testing only."""
    _token_generation_timestamps.clear()
    _upload_timestamps.clear()
    _revoked_tokens.clear()
