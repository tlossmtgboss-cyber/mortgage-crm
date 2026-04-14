"""
Request Context Middleware

ASGI middleware that establishes a correlation ID for every HTTP request,
making it available throughout the request lifecycle via contextvars.

Responsibilities:
- Generates a unique request_id (UUID4) for each incoming request
- Accepts an incoming X-Request-ID header if present (distributed tracing)
- Stores request_id in contextvars AND request.state for downstream access
- Adds X-Request-ID to every response header
- Structured JSON logging: method, path, status_code, response_time_ms,
  user_id, organization_id, client_ip, user_agent
- Log levels: INFO for 2xx/3xx, WARNING for 4xx, ERROR for 5xx
- Skips health-check and static asset paths
- PII protection: never logs request bodies; redacts sensitive query params

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

# Paths that generate high volume and provide no diagnostic value
_SKIP_LOG_PATHS: frozenset[str] = frozenset({
    "/health",
    "/api/health",
    "/api/v1/health",
    "/metrics",
    "/favicon.ico",
    "/robots.txt",
})

# Static file extensions -- skip logging to reduce noise
_STATIC_EXTENSIONS: frozenset[str] = frozenset({
    ".css", ".js", ".map", ".png", ".jpg", ".jpeg", ".gif",
    ".svg", ".ico", ".woff", ".woff2", ".ttf", ".eot",
})

# Query param keys that must never appear in logs
_SENSITIVE_QUERY_KEYS: frozenset[str] = frozenset({
    "password", "token", "secret", "key",
    "access_token", "refresh_token", "api_key",
    "client_secret", "authorization",
})


def _is_static_path(path: str) -> bool:
    """Check if the path looks like a static file request."""
    dot_idx = path.rfind(".")
    if dot_idx == -1:
        return False
    return path[dot_idx:].lower() in _STATIC_EXTENSIONS


def _safe_query_string(query: str) -> Optional[str]:
    """
    Return query string with sensitive parameter values redacted.
    Returns None if query is empty.
    """
    if not query:
        return None
    parts = []
    for pair in query.split("&"):
        eq_idx = pair.find("=")
        if eq_idx == -1:
            parts.append(pair)
            continue
        key = pair[:eq_idx].lower()
        if key in _SENSITIVE_QUERY_KEYS:
            parts.append(f"{pair[:eq_idx]}=[REDACTED]")
        else:
            parts.append(pair)
    return "&".join(parts)


def _get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP, preferring X-Forwarded-For for proxied requests."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First IP in the chain is the original client
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


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


def _log_level_for_status(status_code: int) -> int:
    """INFO for 2xx/3xx, WARNING for 4xx, ERROR for 5xx."""
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Outermost middleware that assigns a correlation ID to every request
    and emits structured JSON logs for enterprise observability.

    1. Reads X-Request-ID from the incoming request (for distributed tracing)
       or generates a new UUID4.
    2. Stores request_id in contextvars (for log injection via
       RequestContextFilter) AND on request.state (for downstream handlers).
    3. Adds X-Request-ID to the response headers.
    4. Emits a single structured log line per request on completion.
    5. Skips health checks and static file requests.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method

        # Fast exit for health checks and static files -- no logging, no overhead
        if path in _SKIP_LOG_PATHS or _is_static_path(path):
            response = await call_next(request)
            return response

        # 1. Generate or propagate correlation ID
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex

        # 2. Store on request.state so downstream handlers can access it
        request.state.request_id = request_id

        # 3. Store in contextvars for automatic log injection
        rid_token = _request_id_var.set(request_id)
        method_token = _method_var.set(method)
        path_token = _path_var.set(path)

        # Extract user/org context if auth middleware has already run
        user_id, org_id = _extract_user_org(request)
        uid_token = _user_id_var.set(user_id)
        oid_token = _org_id_var.set(org_id)

        client_ip = _get_client_ip(request)
        user_agent = (request.headers.get("user-agent") or "")[:200]

        start = time.monotonic()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            # Re-check user/org in case auth ran during the request
            user_id_late, org_id_late = _extract_user_org(request)
            logger.error(
                "Request failed with unhandled exception",
                extra={
                    "event_type": "request_error",
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "response_time_ms": duration_ms,
                    "user_id": user_id_late or user_id,
                    "organization_id": org_id_late or org_id,
                    "client_ip": client_ip,
                    "user_agent": user_agent,
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

        # 4. Add correlation ID and timing to response
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

        # 4a. Drop Content-Length so h11 uses chunked transfer encoding.
        # Stacked BaseHTTPMiddleware re-streams the body but preserves the
        # original Content-Length, causing h11.LocalProtocolError when the
        # streamed bytes don't match.  Removing it is safe — uvicorn/h11
        # falls back to chunked encoding automatically.
        if "content-length" in response.headers:
            del response.headers["content-length"]

        # Re-check user/org in case auth ran during the request
        user_id_late, org_id_late = _extract_user_org(request)

        # 5. Single structured log line per completed request
        log_level = _log_level_for_status(status_code)
        logger.log(
            log_level,
            "%s %s %d %.0fms",
            method,
            path,
            status_code,
            duration_ms,
            extra={
                "event_type": "request_complete",
                "request_id": request_id,
                "method": method,
                "path": path,
                "query": _safe_query_string(request.url.query),
                "status_code": status_code,
                "response_time_ms": duration_ms,
                "user_id": user_id_late or user_id,
                "organization_id": org_id_late or org_id,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "response_size": response.headers.get("content-length"),
            },
        )

        return response
