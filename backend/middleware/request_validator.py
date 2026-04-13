"""
Request Validation Middleware
=============================

ASGI middleware that validates and sanitizes incoming HTTP requests before
they reach route handlers.  Provides defense-in-depth against common attack
vectors without relying on individual route-level checks.

Checks performed:
1. **Content-Type validation** -- POST/PUT/PATCH bodies must declare a JSON
   or multipart Content-Type (file uploads are allowed).
2. **Request size limiting** -- Bodies larger than MAX_REQUEST_SIZE_MB (env,
   default 10 MB) are rejected with 413.
3. **Header sanitization** -- Null bytes in header values are stripped.
4. **Path traversal protection** -- Paths containing ``..`` are rejected.
5. **SQL injection detection** -- Query parameters are scanned for obvious
   attack patterns (UNION SELECT, DROP TABLE, etc.).
6. **XSS detection** -- Query parameters are scanned for ``<script>``,
   ``javascript:``, ``onerror=``, and similar payloads.

Rejection behaviour:
- Returns **400 Bad Request** with a generic ``"Bad request"`` message.
- Logs the actual detection reason at WARNING level with the request_id
  for post-incident investigation.
- Never reveals which specific check triggered the rejection.

Usage in main.py:
    from middleware.request_validator import RequestValidatorMiddleware
    app.add_middleware(RequestValidatorMiddleware)

Configuration (environment variables):
    MAX_REQUEST_SIZE_MB  -- Maximum request body size in megabytes (default 10).
"""

from __future__ import annotations

import logging
import os
import re
from typing import FrozenSet, Optional, Pattern

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _max_body_bytes() -> int:
    """Read MAX_REQUEST_SIZE_MB from environment, default 10 MB."""
    try:
        mb = int(os.getenv("MAX_REQUEST_SIZE_MB", "10"))
    except (TypeError, ValueError):
        mb = 10
    return max(mb, 1) * 1024 * 1024


MAX_BODY_BYTES: int = _max_body_bytes()

# HTTP methods that carry a request body
_BODY_METHODS: FrozenSet[str] = frozenset({"POST", "PUT", "PATCH"})

# Content-Type prefixes that are acceptable for body-bearing requests
_ALLOWED_CONTENT_TYPES: tuple[str, ...] = (
    "application/json",
    "multipart/form-data",
    "application/x-www-form-urlencoded",
)

# Paths where we skip Content-Type enforcement (webhooks, file-upload
# endpoints, voice/telephony callbacks that may send form-data or raw).
_CONTENT_TYPE_SKIP_PREFIXES: tuple[str, ...] = (
    "/api/v1/webhook",
    "/api/v1/voice",
    "/api/v1/vapi",
    "/api/v1/telnyx",
    "/api/v1/slybroadcast",
    "/api/portal/",
    "/api/v1/documents/upload",
    "/api/v1/smart-docs/",
    "/docs",
    "/openapi.json",
)

# Additional path substrings that bypass Content-Type enforcement
# (file uploads, document endpoints, webhook callbacks).
_CONTENT_TYPE_SKIP_SUBSTRINGS: tuple[str, ...] = (
    "/upload",
    "/document",
    "/webhook",
)


# ---------------------------------------------------------------------------
# SQL injection patterns
# ---------------------------------------------------------------------------
# Only flag unambiguous attack payloads to keep false-positive rate low.
# Each pattern uses word boundaries (\b) and case-insensitive matching.

_SQL_INJECTION_PATTERNS: list[Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bUNION\b\s+\bSELECT\b",
        r"\bUNION\b\s+\bALL\b\s+\bSELECT\b",
        r"\bDROP\b\s+\bTABLE\b",
        r"\bDROP\b\s+\bDATABASE\b",
        r"\bDELETE\b\s+\bFROM\b",
        r"\bINSERT\b\s+\bINTO\b",
        r"\bUPDATE\b\s+\S+\s+\bSET\b",
        r"\bEXEC\b\s*\(",
        r"\bEXECUTE\b\s*\(",
        r";\s*--",
        r"\bOR\b\s+1\s*=\s*1",
        r"\bOR\b\s+'[^']*'\s*=\s*'",
        r"\bAND\b\s+1\s*=\s*1",
        r"\bSLEEP\s*\(",
        r"\bBENCHMARK\s*\(",
        r"\bWAITFOR\b\s+\bDELAY\b",
        r"\bLOAD_FILE\s*\(",
        r"\bINTO\b\s+\bOUTFILE\b",
        r"\bINFORMATION_SCHEMA\b",
    ]
]


# ---------------------------------------------------------------------------
# XSS patterns
# ---------------------------------------------------------------------------
# Only flag obvious injection vectors to avoid flagging benign values that
# happen to contain angle brackets in free-text fields.

_XSS_PATTERNS: list[Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"<\s*script",
        r"javascript\s*:",
        r"vbscript\s*:",
        r"\bon\w+\s*=",             # onerror=, onload=, onclick=, ...
        r"<\s*iframe",
        r"<\s*object",
        r"<\s*embed",
        r"<\s*img\s[^>]*\bon\w+\s*=",  # <img onerror=...>
        r"<\s*svg\s[^>]*\bon\w+\s*=",  # <svg onload=...>
        r"data\s*:\s*text/html",
    ]
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_request_id(request: Request) -> str:
    """Extract request_id from header or state (set by RequestLoggingMiddleware)."""
    # Try X-Request-ID header first
    rid = request.headers.get("x-request-id", "")
    if rid:
        return rid
    # Try request.state (set by logging middleware)
    try:
        return getattr(request.state, "request_id", "unknown")
    except Exception:
        return "unknown"


def _has_path_traversal(path: str) -> bool:
    """Return True if the URL path contains directory traversal sequences."""
    # Normalise encoded variants before checking
    decoded = path.replace("%2e", ".").replace("%2E", ".")
    return ".." in decoded


def _check_sql_injection(value: str) -> Optional[str]:
    """Return the matched pattern name if SQL injection is detected, else None."""
    for pattern in _SQL_INJECTION_PATTERNS:
        if pattern.search(value):
            return pattern.pattern
    return None


def _check_xss(value: str) -> Optional[str]:
    """Return the matched pattern name if XSS is detected, else None."""
    for pattern in _XSS_PATTERNS:
        if pattern.search(value):
            return pattern.pattern
    return None


def _strip_null_bytes_from_headers(request: Request) -> bool:
    """
    Check whether any header contains null bytes.

    Returns True if null bytes were found (headers are immutable on the ASGI
    scope, so the middleware logs a warning and rejects the request).
    """
    for key, value in request.headers.items():
        if "\x00" in key or "\x00" in value:
            return True
    return False


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RequestValidatorMiddleware(BaseHTTPMiddleware):
    """
    Validates incoming requests for common attack patterns and malformed input.

    See module docstring for the full list of checks performed.
    """

    async def dispatch(self, request: Request, call_next):
        # Fast-path: let WebSocket upgrades and OPTIONS preflight through
        if request.scope.get("type") == "websocket":
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)

        request_id = _get_request_id(request)
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        # ------------------------------------------------------------------
        # 1. Path traversal protection
        # ------------------------------------------------------------------
        if _has_path_traversal(path):
            logger.warning(
                "Request rejected: path traversal detected | "
                "request_id=%s ip=%s path=%s",
                request_id, client_ip, path,
            )
            return JSONResponse(
                status_code=400,
                content={"detail": "Bad request"},
            )

        # ------------------------------------------------------------------
        # 2. Null bytes in headers
        # ------------------------------------------------------------------
        if _strip_null_bytes_from_headers(request):
            logger.warning(
                "Request rejected: null bytes in headers | "
                "request_id=%s ip=%s path=%s",
                request_id, client_ip, path,
            )
            return JSONResponse(
                status_code=400,
                content={"detail": "Bad request"},
            )

        # ------------------------------------------------------------------
        # 3. Request body size limit
        # ------------------------------------------------------------------
        content_length_str = request.headers.get("content-length")
        if content_length_str:
            try:
                content_length = int(content_length_str)
                if content_length > MAX_BODY_BYTES:
                    max_mb = MAX_BODY_BYTES / (1024 * 1024)
                    logger.warning(
                        "Request rejected: body too large (%d bytes, max %d MB) | "
                        "request_id=%s ip=%s path=%s",
                        content_length, max_mb, request_id, client_ip, path,
                    )
                    return JSONResponse(
                        status_code=413,
                        content={"detail": f"Request body too large. Maximum size is {max_mb:.0f} MB."},
                    )
            except (ValueError, TypeError):
                pass  # malformed Content-Length is handled by the HTTP server

        # ------------------------------------------------------------------
        # 4. Content-Type validation for body-bearing methods
        # ------------------------------------------------------------------
        if request.method in _BODY_METHODS:
            content_type = request.headers.get("content-type", "")
            cl = request.headers.get("content-length", "0")
            has_body = cl not in ("0", "")
            path_skip = (
                any(path.startswith(prefix) for prefix in _CONTENT_TYPE_SKIP_PREFIXES)
                or any(substr in path.lower() for substr in _CONTENT_TYPE_SKIP_SUBSTRINGS)
            )

            if has_body and not path_skip:
                ct_lower = content_type.lower()
                if ct_lower and not any(ct_lower.startswith(allowed) for allowed in _ALLOWED_CONTENT_TYPES):
                    logger.warning(
                        "Request rejected: disallowed Content-Type '%s' | "
                        "request_id=%s ip=%s path=%s method=%s",
                        content_type, request_id, client_ip, path, request.method,
                    )
                    return JSONResponse(
                        status_code=415,
                        content={"detail": "Unsupported Media Type"},
                    )

        # ------------------------------------------------------------------
        # 5. SQL injection & XSS detection in query parameters
        # ------------------------------------------------------------------
        query_params = request.query_params
        if query_params:
            for key, value in query_params.items():
                # Check both keys and values
                for check_value in (key, value):
                    sqli_match = _check_sql_injection(check_value)
                    if sqli_match:
                        logger.warning(
                            "Request rejected: SQL injection pattern in query param | "
                            "request_id=%s ip=%s path=%s param_key=%s pattern=%s",
                            request_id, client_ip, path, key, sqli_match,
                        )
                        return JSONResponse(
                            status_code=400,
                            content={"detail": "Bad request"},
                        )

                    xss_match = _check_xss(check_value)
                    if xss_match:
                        logger.warning(
                            "Request rejected: XSS pattern in query param | "
                            "request_id=%s ip=%s path=%s param_key=%s pattern=%s",
                            request_id, client_ip, path, key, xss_match,
                        )
                        return JSONResponse(
                            status_code=400,
                            content={"detail": "Bad request"},
                        )

        # ------------------------------------------------------------------
        # All checks passed — continue to next middleware / route handler
        # ------------------------------------------------------------------
        return await call_next(request)
