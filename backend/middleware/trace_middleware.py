"""
Trace ID Middleware

FastAPI middleware that ensures every request carries a trace ID:
- Extracts X-Trace-ID from incoming request headers (if present)
- Generates a new trace ID if none is provided
- Stores the trace ID in contextvars for the request lifecycle
- Adds X-Trace-ID to every response header
- Logs request start/end with duration

Designed to work with the Smart Docs structured logging system
(services.smart_docs.logging_config) but usable by any component
that calls get_trace_id().

Usage in main.py:
    from middleware.trace_middleware import TraceIDMiddleware
    app.add_middleware(TraceIDMiddleware)
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from services.smart_docs.logging_config import (
    TRACE_ID_HEADER,
    generate_trace_id,
    get_trace_id,
    set_trace_id,
)

logger = logging.getLogger("smart_docs.trace_middleware")

# Paths that generate high volume and don't need per-request logging
_SKIP_LOG_PATHS = frozenset({
    "/health",
    "/api/health",
    "/metrics",
    "/favicon.ico",
})


class TraceIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that propagates or generates a trace ID for every request.

    The trace ID is:
    1. Read from the incoming ``X-Trace-ID`` header (trusted in internal traffic)
    2. Generated fresh if the header is absent
    3. Stored in a ``ContextVar`` accessible via ``get_trace_id()``
    4. Echoed back in the ``X-Trace-ID`` response header

    Request start and completion (with duration) are logged at INFO level,
    except for health-check paths.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract or generate trace ID
        trace_id = request.headers.get(TRACE_ID_HEADER) or generate_trace_id()
        set_trace_id(trace_id)

        skip_log = request.url.path in _SKIP_LOG_PATHS

        if not skip_log:
            logger.info(
                "Request started",
                extra={
                    "event_type": "request_start",
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": request.client.host if request.client else None,
                },
            )

        start = time.monotonic()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            if not skip_log:
                logger.error(
                    "Request failed",
                    extra={
                        "event_type": "request_end",
                        "trace_id": trace_id,
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": duration_ms,
                        "success": False,
                    },
                )
            raise

        duration_ms = round((time.monotonic() - start) * 1000, 2)

        # Attach trace ID to response
        response.headers[TRACE_ID_HEADER] = trace_id

        if not skip_log:
            logger.info(
                "Request completed",
                extra={
                    "event_type": "request_end",
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "success": response.status_code < 400,
                },
            )

        return response
