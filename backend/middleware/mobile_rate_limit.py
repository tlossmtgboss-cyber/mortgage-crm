"""
Mobile-Specific Rate Limiting Middleware (In-Memory, No Redis Required)

Provides rate limiting tailored to mobile app traffic patterns. Mobile apps
(Capacitor/iOS/Android) can generate excessive API calls from background
refresh, rapid navigation, and offline queue flush.

This middleware runs ONLY for requests identified as originating from the
mobile app (via User-Agent or X-Mobile-App header) and applies per-endpoint
rate limits tuned for mobile access patterns.

Features:
    - Per-endpoint configurable rate limits for mobile-specific paths
    - Sliding window counter (in-memory, single-process safe for Railway)
    - Key by user_id + endpoint (authenticated) or IP + endpoint (unauthenticated)
    - 2x burst allowance for offline sync endpoints
    - Standard rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining,
      X-RateLimit-Reset, Retry-After)
    - Periodic cleanup of expired entries to bound memory
    - Lightweight mobile detection via User-Agent and custom header

Middleware ordering:
    Add AFTER TenantContextMiddleware and auth middleware so that
    request.state.user is available for keying by user_id.

Environment variables:
    MOBILE_RL_ENABLED       Enable/disable this middleware (default: true)
    MOBILE_RL_MAX_KEYS      Max tracked keys before forced cleanup (default: 10000)
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in _TRUE_VALUES


def _env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


ENABLED = _env_bool("MOBILE_RL_ENABLED", True)
MAX_KEYS = _env_int("MOBILE_RL_MAX_KEYS", 10000)

# ---------------------------------------------------------------------------
# Per-Endpoint Rate Limits
# ---------------------------------------------------------------------------

# {path_prefix: {"requests": max_requests, "window": window_seconds}}
# Matched in order; first prefix match wins.
MOBILE_RATE_LIMITS = {
    # Unauthenticated endpoints (stricter)
    "/api/v1/app/compatibility": {"requests": 10, "window": 60},
    "/api/v1/app/health": {"requests": 30, "window": 60},

    # Auth endpoints
    "/api/v1/auth/login": {"requests": 5, "window": 300},
    "/api/v1/account/start": {"requests": 5, "window": 300},  # WAF-safe login alias
    "/token": {"requests": 5, "window": 300},
    "/api/v1/auth/sso": {"requests": 10, "window": 300},

    # Mobile dashboard (frequent polling)
    "/api/v1/mobile/dashboard": {"requests": 30, "window": 60},
    "/api/v1/mobile/notifications": {"requests": 60, "window": 60},

    # Push registration (infrequent)
    "/api/v1/push/register": {"requests": 5, "window": 300},

    # Offline queue flush (burst allowed -- see BURST_PATHS below)
    "/api/v1/mobile/sync": {"requests": 100, "window": 60},

    # Analytics (batch, low priority)
    "/api/v1/analytics/mobile": {"requests": 5, "window": 60},
    "/api/v1/analytics/performance": {"requests": 5, "window": 60},

    # Audit events (batch)
    "/api/v1/audit/mobile-events": {"requests": 5, "window": 60},

    # LiveKit token provisioning (expensive — limit to prevent abuse)
    "/api/v1/livekit/token": {"requests": 10, "window": 60},

    # Voice session save (infrequent — one per voice session)
    "/api/v1/mobile-voice/sessions/save": {"requests": 10, "window": 60},
}

# Default limits applied to any mobile request that does not match a specific path.
# Authenticated users (identified by JWT user_id) get a higher ceiling.
DEFAULT_MOBILE_LIMIT_AUTH = {"requests": 100, "window": 60}
DEFAULT_MOBILE_LIMIT_UNAUTH = {"requests": 20, "window": 60}

# Paths that get 2x burst allowance (LOs reconnecting after being offline)
BURST_PATHS = frozenset({
    "/api/v1/mobile/sync",
})

# Burst multiplier for offline queue flush endpoints
BURST_MULTIPLIER = 2

# Paths to skip entirely (health checks, static assets, certificate pinning)
SKIP_PATHS = frozenset({
    "/health",
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
})

# Prefixes to skip entirely (certificate pinning must always be reachable)
SKIP_PREFIXES = (
    "/api/v1/security/certificate-pins",
)

# ---------------------------------------------------------------------------
# Mobile Detection
# ---------------------------------------------------------------------------

# Compiled once; matches Capacitor WebView, iOS Safari (in-app), or Android
# WebView User-Agent patterns, plus common mobile browser indicators.
_MOBILE_UA_PATTERN = re.compile(
    r"Capacitor|PerenniaAI|CFNetwork|Darwin|okhttp|"
    r"iPhone|iPad|iPod|Android|Mobile Safari",
    re.IGNORECASE,
)


def is_mobile_request(request: Request) -> bool:
    """Determine whether a request originates from the mobile app.

    Checks:
    1. X-Mobile-App header (set by the Capacitor HTTP plugin)
    2. User-Agent matching known mobile/Capacitor patterns
    """
    # Explicit header from the app is the most reliable signal
    if request.headers.get("x-mobile-app"):
        return True

    user_agent = request.headers.get("user-agent", "")
    if _MOBILE_UA_PATTERN.search(user_agent):
        return True

    return False


# ---------------------------------------------------------------------------
# Sliding Window Store
# ---------------------------------------------------------------------------


class _MobileSlidingWindow:
    """Thread-safe in-memory sliding window counter.

    Each (identity + endpoint) combination gets a deque of monotonic
    timestamps. The deque is pruned on every check call. A periodic cleanup
    sweep removes fully-stale keys to bound memory usage.
    """

    def __init__(
        self,
        cleanup_interval: int = 120,
        max_keys: int = MAX_KEYS,
    ) -> None:
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = cleanup_interval
        self._max_keys = max_keys

    def check(
        self,
        key: str,
        limit: int,
        window: int,
    ) -> Tuple[bool, int, int]:
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
                oldest = bucket[0] if bucket else now
                retry_after = max(1, int((oldest + window) - now))
                return False, 0, retry_after

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

        # Emergency eviction if we exceed max tracked keys
        if len(self._buckets) > self._max_keys:
            sorted_keys = sorted(
                self._buckets.keys(),
                key=lambda k: self._buckets[k][-1] if self._buckets[k] else 0,
            )
            evict_count = len(self._buckets) - self._max_keys
            for key in sorted_keys[:evict_count]:
                del self._buckets[key]
            logger.warning(
                "Mobile rate limiter emergency eviction: removed %d stale keys "
                "(total was %d, max %d)",
                evict_count,
                evict_count + self._max_keys,
                self._max_keys,
            )

        if stale_keys:
            logger.debug(
                "Mobile rate limiter cleanup: removed %d stale keys",
                len(stale_keys),
            )


# Module-level singleton
_store = _MobileSlidingWindow()


def get_mobile_rate_limit_store() -> _MobileSlidingWindow:
    """Return the module-level store (useful for testing / reset)."""
    return _store


# ---------------------------------------------------------------------------
# Key Generation
# ---------------------------------------------------------------------------


def _build_rate_limit_key(request: Request, path_category: str) -> str:
    """Build a rate limit key from request identity + endpoint path.

    Authenticated requests are keyed by user_id + path so that each user has
    independent limits per endpoint. Unauthenticated requests fall back to IP.
    """
    # Try user_id from auth middleware
    user = getattr(getattr(request, "state", None), "user", None)
    user_id = getattr(user, "id", None) if user else None

    if user_id:
        return f"mobile:user:{user_id}:{path_category}"

    # Fall back to IP
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return f"mobile:ip:{ip}:{path_category}"


# ---------------------------------------------------------------------------
# Path Matching
# ---------------------------------------------------------------------------


def _get_limit_for_path(path: str, is_authenticated: bool = False) -> Tuple[str, int, int, bool]:
    """Find the rate limit config for a given path.

    Args:
        path: The request URL path.
        is_authenticated: Whether the request has a resolved user_id.

    Returns:
        (path_category, requests_limit, window_seconds, is_burst_path)
    """
    path_lower = path.lower()

    for prefix, config in MOBILE_RATE_LIMITS.items():
        if path_lower.startswith(prefix):
            is_burst = prefix in BURST_PATHS
            effective_limit = config["requests"]
            if is_burst:
                effective_limit *= BURST_MULTIPLIER
            return prefix, effective_limit, config["window"], is_burst

    # No prefix match — use auth-aware default
    default = DEFAULT_MOBILE_LIMIT_AUTH if is_authenticated else DEFAULT_MOBILE_LIMIT_UNAUTH
    return "_default_mobile", default["requests"], default["window"], False


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class MobileRateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces mobile-specific rate limits.

    Only processes requests identified as mobile (via User-Agent or
    X-Mobile-App header). Non-mobile requests pass through untouched.

    Rate limit headers are always attached to mobile responses so the app
    can implement client-side backoff.
    """

    def __init__(self, app, enabled: bool = ENABLED) -> None:
        super().__init__(app)
        self.enabled = enabled
        self.store = _store
        # Track rate limit hits for monitoring without flooding logs.
        # Only log the first hit per key per cleanup cycle.
        self._logged_keys: set = set()
        self._logged_keys_lock = threading.Lock()
        self._last_log_clear = time.monotonic()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)

        # Only apply to mobile requests
        if not is_mobile_request(request):
            return await call_next(request)

        path = request.url.path

        # Skip health/docs/static/certificate-pins
        if path in SKIP_PATHS:
            return await call_next(request)
        if any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
            return await call_next(request)

        # Determine auth state for default limit selection
        user = getattr(getattr(request, "state", None), "user", None)
        is_authenticated = getattr(user, "id", None) is not None if user else False

        # Determine rate limit for this path
        path_category, limit, window, is_burst = _get_limit_for_path(path, is_authenticated)

        # Build the rate limit key
        rl_key = _build_rate_limit_key(request, path_category)

        # Check the rate limit
        allowed, remaining, retry_after = self.store.check(rl_key, limit, window)

        if not allowed:
            self._log_rate_limit_hit(rl_key, path, limit, window, retry_after)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Mobile rate limit of {limit} requests per {window}s exceeded",
                    "retry_after": retry_after,
                    "scope": "mobile",
                    "path": path_category,
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
        if retry_after:
            response.headers["X-RateLimit-Reset"] = str(retry_after)

        return response

    def _log_rate_limit_hit(
        self,
        key: str,
        path: str,
        limit: int,
        window: int,
        retry_after: int,
    ) -> None:
        """Log rate limit hits without flooding.

        Only logs the first occurrence of each key per 60-second window,
        preventing log spam from a single misbehaving client.
        """
        now = time.monotonic()
        with self._logged_keys_lock:
            # Clear the set periodically
            if now - self._last_log_clear > 60:
                self._logged_keys.clear()
                self._last_log_clear = now

            if key in self._logged_keys:
                return
            self._logged_keys.add(key)

        logger.warning(
            "Mobile rate limit exceeded: key=%s path=%s limit=%d/%ds retry_after=%ds",
            key,
            path,
            limit,
            window,
            retry_after,
        )
