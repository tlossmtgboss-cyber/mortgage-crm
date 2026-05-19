"""
Request Logging Middleware  [DEPRECATED 2026-04-30]

Superseded by middleware/request_context.py (RequestContextMiddleware), which is
registered as the outermost middleware in main.py.  Both generate X-Request-ID,
set contextvars, and produce structured JSON request logs.  This file is kept
because middleware/__init__.py re-exports RequestLoggingMiddleware and some test
code may reference it.  Do NOT register this middleware — it would duplicate
request_context's logging.

ASGI middleware that logs every HTTP request with structured JSON output.

For each request:
- Generates or extracts X-Request-ID
- Sets request context (request_id, user_id, org_id) in contextvars
- Logs request start: method, path, user_id, org_id
- Logs request complete: status_code, duration_ms, response_size
- Adds X-Request-ID to response headers
- Skips health check endpoints to reduce noise
- Redacts sensitive fields from logged request bodies

Works with logging_config.StructuredFormatter and RequestContextFilter to
produce machine-parseable JSON log lines.

Usage in main.py:
    from middleware.request_logging import RequestLoggingMiddleware
    app.add_middleware(RequestLoggingMiddleware)
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, FrozenSet, Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from logging_config import (
    clear_request_context,
    generate_request_id,
    set_request_context,
)

logger = logging.getLogger("perennia.http")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REQUEST_ID_HEADER = "X-Request-ID"

# Paths that generate high volume and provide no diagnostic value
_SKIP_PATHS: FrozenSet[str] = frozenset({
    "/health",
    "/api/health",
    "/api/v1/health",
    "/metrics",
    "/favicon.ico",
    "/robots.txt",
})

# Fields that must never appear in logged request bodies
_SENSITIVE_FIELDS: FrozenSet[str] = frozenset({
    "password",
    "new_password",
    "old_password",
    "confirm_password",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "secret",
    "client_secret",
    "ssn",
    "social_security",
    "social_security_number",
    "credit_card",
    "card_number",
    "cvv",
    "account_number",
    "routing_number",
})

# SSN / card patterns for value-level scrubbing
_SENSITIVE_PATTERNS = [
    re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),             # SSN
    re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),  # Credit card
]


def _redact_body(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a shallow copy of body with sensitive fields replaced by
    '[REDACTED]'. Also scrubs values matching SSN/card patterns.

    Only operates on the top level of the dict; nested objects are
    converted to str representation to avoid deep-walk cost.
    """
    redacted: Dict[str, Any] = {}
    for key, value in body.items():
        lower_key = key.lower()
        if lower_key in _SENSITIVE_FIELDS:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, str):
            scrubbed = value
            for pat in _SENSITIVE_PATTERNS:
                if pat.search(scrubbed):
                    scrubbed = "[REDACTED]"
                    break
            redacted[key] = scrubbed
        elif isinstance(value, dict):
            # Recurse one level for nested objects
            redacted[key] = _redact_body(value)
        else:
            redacted[key] = value
    return redacted


def _extract_user_org(request: Request) -> tuple:
    """
    Extract user_id and org_id from the request state.

    These are typically set by auth middleware (get_current_user) earlier
    in the middleware chain. Returns (None, None) if not available.
    """
    user_id = None
    org_id = None

    # FastAPI auth middleware often stores user on request.state
    user = getattr(request.state, "user", None)
    if user is not None:
        user_id = getattr(user, "id", None)
        org_id = getattr(user, "organization_id", None)

    return user_id, org_id


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    HTTP request/response logging middleware with structured JSON output.

    Features:
    - Auto-generates X-Request-ID if not present in request headers
    - Echoes X-Request-ID in response headers for client correlation
    - Logs request start and completion with timing
    - Extracts user_id/org_id from auth context when available
    - Skips noisy health check endpoints
    - Redacts sensitive fields from logged bodies

    This middleware should be added early in the stack so it wraps as
    much of the request lifecycle as possible, but after auth middleware
    so user context is available.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip health checks and static assets
        if path in _SKIP_PATHS:
            response = await call_next(request)
            return response

        # Generate or extract request ID
        request_id = request.headers.get(REQUEST_ID_HEADER) or generate_request_id()

        # Extract user/org context (may be None if auth hasn't run yet)
        user_id, org_id = _extract_user_org(request)

        # Set context variables for downstream log statements
        set_request_context(
            request_id=request_id,
            user_id=user_id,
            org_id=org_id,
            endpoint=path,
        )

        # Log request start
        logger.info(
            "Request started",
            extra={
                "event_type": "request_start",
                "request_id": request_id,
                "method": request.method,
                "path": path,
                "query": str(request.url.query) if request.url.query else None,
                "user_id": user_id,
                "org_id": org_id,
                "client_ip": request.client.host if request.client else None,
                "user_agent": (request.headers.get("user-agent") or "")[:200],
            },
        )

        start = time.monotonic()
        status_code = 500  # Default in case of unhandled exception

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.error(
                "Request failed with unhandled exception",
                extra={
                    "event_type": "request_error",
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "user_id": user_id,
                    "org_id": org_id,
                    "duration_ms": duration_ms,
                },
                exc_info=True,
            )
            raise
        finally:
            clear_request_context()

        duration_ms = round((time.monotonic() - start) * 1000, 2)

        # Attach request ID to response
        response.headers[REQUEST_ID_HEADER] = request_id

        # Determine response size from content-length header if available
        response_size = response.headers.get("content-length")
        response_size_int = int(response_size) if response_size else None

        # Re-extract user/org in case auth middleware set it during request
        if user_id is None:
            user_id, org_id = _extract_user_org(request)

        # Log request completion
        log_level = logging.WARNING if status_code >= 400 else logging.INFO
        logger.log(
            log_level,
            "Request completed",
            extra={
                "event_type": "request_complete",
                "request_id": request_id,
                "method": request.method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "response_size": response_size_int,
                "user_id": user_id,
                "org_id": org_id,
            },
        )

        return response
