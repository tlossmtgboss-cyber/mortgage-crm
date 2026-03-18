"""
Request Context Middleware

ASGI middleware that establishes a correlation ID for every HTTP request,
making it available throughout the request lifecycle via contextvars.

Responsibilities:
- Generates a unique request_id (UUID4 hex) for each incoming request
- Accepts an incoming X-Request-ID header if present (distributed tracing)
- Stores request_id in a ContextVar for access by any downstream code
- Adds X-Request-ID to every response header
- Logs request start and completion with duration_ms
- Extracts user_id / org_id from request.state (set by auth middleware)
- Skips logging for health-check and static asset paths

This should be the outermost application middleware (added last in the
FastAPI middleware stack) so that every piece of inner middleware and
every route handler has access to the correlation ID.

Usage in main.py:
    from middleware.request_context import RequestContextMiddleware
    app.add_middleware(RequestContextMiddleware)
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("perennia.request_context")

# ---------------------------------------------------------------------------
# Context variables -- accessible anywhere during the request lifecycle
# ---------------------------------------------------------------------------

_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_user_id_var: ContextVar[Optional[str]] = ContextVar("ctx_user_id", default=None)
_org_id_var: ContextVar[Optional[str]] = ContextVar("ctx_org_id", default=None)
_method_var: ContextVar[Optional[str]] = ContextVar("ctx_method", default=None)
_path_var: ContextVar[Optional[str]] = ContextVar("ctx_path", default=None)

REQUEST_ID_HEADER = "X-Request-ID"


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------

def get_request_id() -> Optional[str]:
    """Return the current request's correlation ID, or None outside a request."""
    return _request_id_var.get()


def get_user_id() -> Optional[str]:
    """Return the authenticated user ID for the current request, if available."""
    return _user_id_var.get()


def get_org_id() -> Optional[str]:
    """Return the tenant org ID for the current request, if available."""
    return _org_id_var.get()


def get_request_method() -> Optional[str]:
    """Return the HTTP method for the current request."""
    return _method_var.get()


def get_request_path() -> Optional[str]:
    """Return the path for the current request."""
    return _path_var.get()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Paths that generate high volume and don't need per-request logging
_SKIP_LOG_PATHS = frozenset({
    "/health",
    "/api/health",
    "/api/v1/health",
    "/metrics",
    "/favicon.ico",
    "/robots.txt",
})


def _extract_user_org(request: Request) -> tuple:
    """
    Extract user_id and org_id from request.state.

    Auth middleware (TenantContextMiddleware, get_current_user) typically
    sets request.state.user before route handlers execute.
    """
    user_id = None
    org_id = None

    user = getattr(request.state, "user", None)
    if user is not None:
        uid = getattr(user, "id", None)
        if uid is not None:
            user_id = str(uid)
        oid = getattr(user, "organization_id", None)
        if oid is not None:
            org_id = str(oid)

    return user_id, org_id


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Outermost middleware that assigns a correlation ID to every request.

    1. Reads X-Request-ID from the incoming request (for distributed tracing)
       or generates a new UUID4 hex string.
    2. Stores request_id, method, and path in contextvars so that any logger
       using RequestContextFilter (from utils.logging_config) automatically
       includes them.
    3. Adds X-Request-ID to the response headers.
    4. Logs request start and completion with duration_ms.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Generate or propagate correlation ID
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        path = request.url.path
        method = request.method

        # 2. Store in contextvars
        rid_token = _request_id_var.set(request_id)
        method_token = _method_var.set(method)
        path_token = _path_var.set(path)

        # Extract user/org context if auth middleware has already run
        user_id, org_id = _extract_user_org(request)
        uid_token = _user_id_var.set(user_id)
        oid_token = _org_id_var.set(org_id)

        skip_log = path in _SKIP_LOG_PATHS

        if not skip_log:
            logger.info(
                "Request started",
                extra={
                    "event_type": "request_start",
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "client_ip": request.client.host if request.client else None,
                    "user_agent": (request.headers.get("user-agent") or "")[:200],
                },
            )

        start = time.monotonic()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            if not skip_log:
                # Re-check user/org in case auth ran during the request
                user_id_late, org_id_late = _extract_user_org(request)
                logger.error(
                    "Request failed with unhandled exception",
                    extra={
                        "event_type": "request_error",
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "duration_ms": duration_ms,
                        "user_id": user_id_late or user_id,
                        "org_id": org_id_late or org_id,
                    },
                    exc_info=True,
                )
            raise
        finally:
            # Reset context vars to avoid leaking into other requests
            _request_id_var.reset(rid_token)
            _method_var.reset(method_token)
            _path_var.reset(path_token)
            _user_id_var.reset(uid_token)
            _org_id_var.reset(oid_token)

        duration_ms = round((time.monotonic() - start) * 1000, 2)

        # 3. Add correlation ID to response
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

        if not skip_log:
            # Re-check user/org in case auth ran during the request
            user_id_late, org_id_late = _extract_user_org(request)

            log_level = logging.WARNING if status_code >= 400 else logging.INFO
            logger.log(
                log_level,
                "Request completed",
                extra={
                    "event_type": "request_complete",
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "user_id": user_id_late or user_id,
                    "org_id": org_id_late or org_id,
                    "response_size": response.headers.get("content-length"),
                },
            )

        return response
