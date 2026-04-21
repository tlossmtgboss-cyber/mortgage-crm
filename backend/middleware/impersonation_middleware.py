"""
Impersonation Enforcement Middleware

This middleware enforces read-only mode during impersonation sessions.
When a manager is impersonating an employee in read-only mode, all write
operations (POST, PUT, PATCH, DELETE) are blocked with a 403 Forbidden response.

Phase 3 Permission Enforcement - Part 1
"""

import logging
from datetime import datetime, timezone
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Set, Optional
from sqlalchemy import text

logger = logging.getLogger(__name__)

# HTTP methods that modify data
WRITE_METHODS: Set[str] = {"POST", "PUT", "PATCH", "DELETE"}

# Paths exempt from read-only enforcement
# These endpoints need to work even in read-only mode
EXEMPT_PATHS: Set[str] = {
    "/api/v1/impersonation/end",
    "/api/v1/impersonation/current",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
    "/api/v1/auth/token",
    "/api/v1/account/signoff",  # WAF-safe alias for logout
    "/api/v1/account/renew",  # WAF-safe alias for token refresh
    "/docs",
    "/openapi.json",
    "/health",
    "/health-check",
    "/api/v1/health-check",
}

# Path prefixes that are exempt (for paths with dynamic segments)
EXEMPT_PATH_PREFIXES: tuple = (
    "/api/v1/impersonation/",
    "/api/v1/public/",
    "/api/portal/",  # Public portal endpoints
    "/api/v1/auth/",  # Auth endpoints always allowed
)


def get_impersonation_mode_from_token(token: str, db_session) -> Optional[str]:
    """
    Query the database to get the impersonation mode for a given token.

    Returns:
        'read_only', 'full_access', or None if session not found/invalid
    """
    try:
        result = db_session.execute(text("""
            SELECT mode FROM impersonation_sessions
            WHERE session_token = :token
              AND is_active = TRUE
              AND expires_at > :now
            LIMIT 1
        """), {
            'token': token,
            'now': datetime.now(timezone.utc)
        })

        row = result.fetchone()
        if row:
            return row[0]
        return None

    except Exception as e:
        logger.error(f"Error checking impersonation mode: {e}")
        return None


class ImpersonationEnforcementMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce read-only mode during impersonation.

    Checks the X-Impersonation-Token header and queries the database
    to determine if the session is in read-only mode. If so, all write
    operations are blocked with a 403 response.
    """

    def __init__(self, app, db_session_factory=None):
        super().__init__(app)
        self.db_session_factory = db_session_factory

    async def dispatch(self, request: Request, call_next):
        # Only check write methods
        if request.method not in WRITE_METHODS:
            return await call_next(request)

        # Check for exempt paths (exact match)
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # Check for exempt path prefixes
        if request.url.path.startswith(EXEMPT_PATH_PREFIXES):
            return await call_next(request)

        # Check for impersonation token in header
        impersonation_token = request.headers.get("X-Impersonation-Token")

        if not impersonation_token:
            # No impersonation, allow request
            return await call_next(request)

        # Check impersonation mode in database
        impersonation_mode = None

        if self.db_session_factory:
            db = self.db_session_factory()
            try:
                impersonation_mode = get_impersonation_mode_from_token(impersonation_token, db)
            finally:
                db.close()

        # Also store on request.state for use by route handlers
        if impersonation_mode:
            request.state.impersonation_mode = impersonation_mode

        if impersonation_mode == 'read_only':
            logger.warning(
                f"Blocked write operation in read-only impersonation mode: "
                f"{request.method} {request.url.path}"
            )

            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Read-only impersonation mode - write operations are disabled",
                    "error_code": "IMPERSONATION_READ_ONLY",
                    "hint": "End impersonation or switch to full-access mode to make changes"
                }
            )

        return await call_next(request)


def is_impersonation_read_only(request: Request) -> bool:
    """
    Helper function to check if current request is in read-only impersonation mode.

    Can be used in endpoint handlers for additional checks or UI hints.
    """
    return getattr(request.state, 'impersonation_mode', None) == 'read_only'


def revoke_manager_impersonation_sessions(manager_id: int, db_session) -> int:
    """Revoke all active impersonation sessions for a manager (e.g., on logout)."""
    from database.models.core import ImpersonationSession
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    count = db_session.query(ImpersonationSession).filter(
        ImpersonationSession.manager_id == manager_id,
        ImpersonationSession.is_active == True,
    ).update({"is_active": False, "ended_at": now})
    db_session.commit()
    if count:
        logger.info("Revoked %d impersonation session(s) for manager_id=%s on logout", count, manager_id)
    return count


def get_impersonation_info(request: Request) -> dict:
    """
    Get impersonation info from request state.

    Returns:
        dict with keys: is_impersonating, mode, actual_user_id, impersonated_user_id
    """
    session = getattr(request.state, 'impersonation_session', None)

    if not session:
        return {
            'is_impersonating': False,
            'mode': getattr(request.state, 'impersonation_mode', None),
            'actual_user_id': None,
            'impersonated_user_id': None
        }

    return {
        'is_impersonating': True,
        'mode': session.mode,
        'actual_user_id': session.manager_id,
        'impersonated_user_id': session.impersonated_user_id
    }
