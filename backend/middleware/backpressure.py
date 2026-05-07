"""
Request Backpressure / Load Shedding Middleware

Tracks concurrent in-flight requests using an asyncio-safe atomic counter.
When concurrent requests exceed a configurable threshold, returns 503 Service
Unavailable with a Retry-After header so clients back off gracefully.

Health check endpoints are always exempt.

Configuration (environment variables):
    MAX_CONCURRENT_REQUESTS  — threshold before shedding (default: 100)
    BACKPRESSURE_RETRY_AFTER — Retry-After header value in seconds (default: 5)
"""

import asyncio
import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Configurable via env
MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "100"))
RETRY_AFTER_SECONDS = int(os.getenv("BACKPRESSURE_RETRY_AFTER", "5"))

# Paths exempt from backpressure (health checks must always respond)
_EXEMPT_PATHS = frozenset({
    "/health",
    "/api/health",
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
})


class BackpressureMiddleware(BaseHTTPMiddleware):
    """Sheds load when concurrent in-flight requests exceed a threshold.

    Uses a simple atomic counter (asyncio.Lock protects increment/decrement)
    rather than a semaphore so that the threshold can be changed at runtime
    without recreating the semaphore.
    """

    def __init__(self, app, max_concurrent: int = MAX_CONCURRENT_REQUESTS):
        super().__init__(app)
        self.max_concurrent = max_concurrent
        self._in_flight = 0
        self._lock = asyncio.Lock()
        self._shedding = False  # tracks whether we are currently in shedding state

    async def dispatch(self, request: Request, call_next):
        # Always allow health checks through
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        # Atomically check and increment in-flight counter
        async with self._lock:
            if self._in_flight >= self.max_concurrent:
                if not self._shedding:
                    self._shedding = True
                    logger.warning(
                        "Backpressure: load shedding STARTED — "
                        f"in_flight={self._in_flight} >= threshold={self.max_concurrent}"
                    )
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "Service temporarily unavailable",
                        "detail": "Server is under heavy load. Please retry shortly.",
                        "retry_after": RETRY_AFTER_SECONDS,
                    },
                    headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
                )
            self._in_flight += 1

        try:
            response = await call_next(request)
            return response
        finally:
            async with self._lock:
                self._in_flight -= 1
                if self._shedding and self._in_flight < self.max_concurrent:
                    self._shedding = False
                    logger.info(
                        "Backpressure: load shedding ENDED — "
                        f"in_flight={self._in_flight} < threshold={self.max_concurrent}"
                    )

    @property
    def current_in_flight(self) -> int:
        """Return current in-flight count (for health/debug endpoints)."""
        return self._in_flight
