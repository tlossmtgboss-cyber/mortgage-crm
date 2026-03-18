"""
Per-Tenant Rate Limiting Middleware (In-Memory, No Redis Required)

Provides organization-level rate limiting using an in-memory sliding window
algorithm. Designed for single-instance deployment on Railway.

Unlike the Redis-based AdaptiveRateLimiter in rate_limiting.py, this middleware
requires no external dependencies. It extracts the tenant (organization_id) from
request.state (set by TenantContextMiddleware) and enforces per-organization
request quotas.

Features:
    - Per-organization sliding window rate limiting
    - Path-specific limit overrides (higher for CRM reads, lower for AI/booking)
    - Configurable via environment variables
    - Skips unauthenticated and health-check requests
    - Returns 429 with Retry-After header on limit breach
    - Thread-safe with threading.Lock
    - Periodic cleanup of stale tenant entries

Middleware ordering:
    This middleware MUST be added AFTER TenantContextMiddleware in the stack
    (i.e., added BEFORE it in app.add_middleware calls, since Starlette is LIFO).
    TenantContextMiddleware sets request.state.organization_id which this
    middleware reads.

Environment variables:
    TENANT_RL_DEFAULT_RPM        Default requests/minute per tenant (default: 100)
    TENANT_RL_CRM_RPM            Limit for /api/v1/leads, /api/v1/loans (default: 200)
    TENANT_RL_AI_RPM             Limit for /api/v1/ai/* paths (default: 20)
    TENANT_RL_BOOKING_RPM        Limit for /api/scheduler/public/book (default: 10)
    TENANT_RL_ENABLED            Enable/disable the middleware (default: true)
    TENANT_RL_MAX_TENANTS        Max tracked tenants before forced cleanup (default: 5000)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, List, Optional, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read once at import time, override via env vars)
# ---------------------------------------------------------------------------

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        logger.warning(
            "Invalid integer for %s=%r, using default %d", name, val, default
        )
        return default


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in _TRUE_VALUES


# Defaults
DEFAULT_RPM = _env_int("TENANT_RL_DEFAULT_RPM", 100)
CRM_RPM = _env_int("TENANT_RL_CRM_RPM", 200)
AI_RPM = _env_int("TENANT_RL_AI_RPM", 20)
BOOKING_RPM = _env_int("TENANT_RL_BOOKING_RPM", 10)
ENABLED = _env_bool("TENANT_RL_ENABLED", True)
MAX_TENANTS = _env_int("TENANT_RL_MAX_TENANTS", 5000)

# Sliding window size in seconds (always 60s = 1 minute)
WINDOW_SECONDS = 60

# Paths that bypass rate limiting entirely
SKIP_PATHS = frozenset({
    "/health",
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/metrics",
})

# Path prefix rules: (prefix, limit_per_minute)
# Evaluated in order; first match wins.
# Built from env-var values so operators can tune without code changes.
PATH_RULES: List[Tuple[str, int]] = [
    # Low-limit (expensive) paths first
    ("/api/scheduler/public/book", BOOKING_RPM),
    ("/api/v1/ai/", AI_RPM),
    ("/api/v1/agents/", AI_RPM),
    ("/api/v1/chat/", AI_RPM),
    # Higher-limit CRM paths
    ("/api/v1/leads", CRM_RPM),
    ("/api/v1/loans", CRM_RPM),
    ("/api/v1/pipeline", CRM_RPM),
    ("/api/v1/dashboard", CRM_RPM),
]

# ---------------------------------------------------------------------------
# Sliding Window Store
# ---------------------------------------------------------------------------


class _TenantSlidingWindow:
    """Thread-safe in-memory sliding window counter for per-tenant rate limiting.

    Each tenant+path-category gets a deque of monotonic timestamps. The deque
    is pruned on each check to remove entries outside the window.
    """

    def __init__(self, cleanup_interval: int = 60, max_tenants: int = MAX_TENANTS):
        # {bucket_key: deque[float]}
        # bucket_key = f"{org_id}:{category}"
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = cleanup_interval
        self._max_tenants = max_tenants

    def check(self, key: str, limit: int, window: int = WINDOW_SECONDS) -> Tuple[bool, int, int]:
        """Check whether the request is allowed.

        Returns:
            (allowed, remaining, retry_after_seconds)
        """
        now = time.monotonic()

        with self._lock:
            self._maybe_cleanup(now)

            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = deque()
                self._buckets[key] = bucket

            # Prune entries outside the window
            cutoff = now - window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            current_count = len(bucket)

            if current_count >= limit:
                # Calculate retry_after: time until the oldest in-window entry
                # expires (i.e., falls outside the window)
                oldest_in_window = bucket[0] if bucket else now
                retry_after = max(1, int((oldest_in_window + window) - now))
                remaining = 0
                return False, remaining, retry_after

            # Allowed - record this request
            bucket.append(now)
            remaining = limit - current_count - 1
            return True, remaining, 0

    def _maybe_cleanup(self, now: float) -> None:
        """Periodically remove fully-stale buckets to bound memory."""
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now

        stale_keys = []
        for key, bucket in self._buckets.items():
            if not bucket or bucket[-1] < now - 3600:
                stale_keys.append(key)

        for key in stale_keys:
            del self._buckets[key]

        # Emergency eviction if we have too many tracked tenants
        if len(self._buckets) > self._max_tenants:
            # Remove oldest-accessed buckets
            sorted_keys = sorted(
                self._buckets.keys(),
                key=lambda k: self._buckets[k][-1] if self._buckets[k] else 0,
            )
            evict_count = len(self._buckets) - self._max_tenants
            for key in sorted_keys[:evict_count]:
                del self._buckets[key]
            logger.warning(
                "Tenant rate limiter emergency eviction: removed %d stale buckets "
                "(total was %d, max %d)",
                evict_count,
                evict_count + self._max_tenants,
                self._max_tenants,
            )

        if stale_keys:
            logger.debug(
                "Tenant rate limiter cleanup: removed %d stale buckets", len(stale_keys)
            )


# Module-level singleton
_store = _TenantSlidingWindow()


def get_tenant_rate_limit_store() -> _TenantSlidingWindow:
    """Return the module-level sliding window store (useful for testing)."""
    return _store


# ---------------------------------------------------------------------------
# Path categorization
# ---------------------------------------------------------------------------


def _get_limit_for_path(path: str) -> int:
    """Return the per-minute limit for a request path.

    Checks PATH_RULES in order; first matching prefix wins.
    Falls back to DEFAULT_RPM.
    """
    path_lower = path.lower()
    for prefix, limit in PATH_RULES:
        if path_lower.startswith(prefix):
            return limit
    return DEFAULT_RPM


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class TenantRateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces per-tenant (organization) rate limits.

    Reads ``request.state.organization_id`` (set by TenantContextMiddleware)
    and applies a sliding-window counter per organization + path category.

    Unauthenticated requests (no organization_id) are passed through without
    rate limiting -- they are already handled by the per-IP RateLimitMiddleware
    in security_middleware.py.
    """

    def __init__(self, app, enabled: bool = ENABLED):
        super().__init__(app)
        self.enabled = enabled
        self.store = _store

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        # Skip health/docs/static paths
        if path in SKIP_PATHS or any(path.startswith(sp) for sp in SKIP_PATHS):
            return await call_next(request)

        # Extract tenant from request.state (set by TenantContextMiddleware)
        org_id: Optional[int] = getattr(
            getattr(request, "state", None), "organization_id", None
        )

        if org_id is None:
            # Unauthenticated or no tenant context -- skip tenant rate limiting.
            # Per-IP limiting is handled by RateLimitMiddleware in security_middleware.
            return await call_next(request)

        # Determine the limit for this path
        limit = _get_limit_for_path(path)

        # Build the bucket key: org + path category
        # We group by limit value so that e.g. all AI paths share one bucket
        # and all CRM paths share another, rather than per-exact-path.
        bucket_key = f"tenant:{org_id}:rpm{limit}"

        allowed, remaining, retry_after = self.store.check(
            bucket_key, limit=limit, window=WINDOW_SECONDS
        )

        if not allowed:
            logger.warning(
                "Tenant rate limit exceeded: org_id=%s path=%s limit=%d/min retry_after=%ds",
                org_id,
                path,
                limit,
                retry_after,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Organization rate limit of {limit} requests/minute exceeded",
                    "retry_after": retry_after,
                    "scope": "tenant",
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after),
                },
            )

        # Request allowed -- proceed and attach rate limit headers
        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response
