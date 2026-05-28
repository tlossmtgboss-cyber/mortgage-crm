"""
Endpoint-Level Rate Limiter (In-Memory, No Redis Required)

DECORATOR-BASED RATE LIMITER — complements the middleware-level
APIRateLimitMiddleware (middleware/api_rate_limit.py).

Provides a decorator-based rate limiter for FastAPI route handlers using a
sliding window counter algorithm.  Designed for per-endpoint protection of
Smart Docs V2 and other sensitive routes.

This module is applied directly to individual route handlers via decorators,
making it easy to assign different limits to different endpoints without
middleware path matching.

Rate Limiting Architecture (consolidated 2026-05-14):
    ACTIVE modules (each serves a distinct purpose):
    - middleware/api_rate_limit.py  — primary per-user/IP middleware (ASGI layer)
    - middleware/rate_limiter.py    (THIS FILE) — decorator-based per-endpoint limits
    - middleware/tenant_rate_limiter.py — per-organization quotas
    - middleware/mobile_rate_limit.py   — mobile-specific limits

    REMOVED (2026-05-27):
    - middleware/rate_limiting.py   — dead code, deleted

Features:
    - Sliding window counter (no Redis — pure in-memory)
    - Thread-safe with threading.Lock
    - Automatic periodic cleanup of expired entries
    - Standard rate limit response headers (X-RateLimit-*)
    - Predefined profiles for common use cases
    - Configurable key function (user_id, IP, org_id, etc.)

Usage:
    from middleware.rate_limiter import rate_limit, UPLOAD_LIMIT, AI_LIMIT

    @router.post("/upload")
    @rate_limit(limit=10, window=60)
    async def upload_doc(request: Request, ...):
        ...

    # Or using a predefined profile:
    @router.post("/ai-review/{document_id}")
    @AI_LIMIT
    async def ai_review(request: Request, ...):
        ...
"""

from __future__ import annotations

import functools
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# =============================================================================
# Rate Limiter Core
# =============================================================================


class RateLimiter:
    """In-memory sliding window rate limiter.

    Stores a deque of Unix timestamps per key.  Each call to ``check_rate_limit``
    prunes entries outside the window, then checks whether the count is within
    the allowed limit.

    Parameters
    ----------
    default_limit : int
        Default number of requests allowed per window.
    default_window : int
        Default window size in seconds.
    cleanup_interval : int
        Seconds between automatic cleanup sweeps of stale keys.
    """

    _instance: Optional["RateLimiter"] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "RateLimiter":
        """Singleton — ensures one shared counter store across all decorators."""
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instance = instance
        return cls._instance

    def __init__(
        self,
        default_limit: int = 100,
        default_window: int = 60,
        cleanup_interval: int = 60,
    ) -> None:
        if self._initialized:
            return
        self.default_limit = default_limit
        self.default_window = default_window
        self.cleanup_interval = cleanup_interval

        # {key: deque[float]}  — timestamps of recent requests
        self._buckets: Dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()
        self._initialized = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_rate_limit(
        self,
        key: str,
        limit: Optional[int] = None,
        window: Optional[int] = None,
    ) -> bool:
        """Return ``True`` if the request is allowed, ``False`` otherwise.

        Adds the current timestamp to the key's deque when allowed.
        """
        limit = limit or self.default_limit
        window = window or self.default_window
        now = time.monotonic()

        with self._lock:
            self._maybe_cleanup(now)
            bucket = self._buckets[key]

            # Prune timestamps outside the window
            cutoff = now - window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                return False

            bucket.append(now)
            return True

    def get_remaining(
        self,
        key: str,
        limit: int,
        window: int,
    ) -> int:
        """Return the number of requests remaining in the current window."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return limit
            cutoff = now - window
            # Count only entries inside the window
            count = sum(1 for ts in bucket if ts > cutoff)
            return max(0, limit - count)

    def get_reset_time(
        self,
        key: str,
        window: int,
    ) -> int:
        """Return seconds until the oldest entry in the window expires."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if not bucket:
                return 0
            cutoff = now - window
            # Find oldest in-window entry
            for ts in bucket:
                if ts > cutoff:
                    return max(1, int((ts + window) - now))
            return 0

    def reset(self, key: Optional[str] = None) -> None:
        """Clear counters.  If *key* is given, clear only that key."""
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _maybe_cleanup(self, now: float) -> None:
        """Periodically remove keys whose deques are entirely expired."""
        if now - self._last_cleanup < self.cleanup_interval:
            return
        self._last_cleanup = now
        stale_keys = []
        for key, bucket in self._buckets.items():
            if not bucket:
                stale_keys.append(key)
                continue
            # If newest entry is older than the largest plausible window (1 hour),
            # remove the key entirely.
            if bucket[-1] < now - 3600:
                stale_keys.append(key)
        for key in stale_keys:
            del self._buckets[key]
        if stale_keys:
            logger.debug("Rate limiter cleanup: removed %d stale keys", len(stale_keys))


# Module-level singleton — shared across the process
_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Return the process-wide RateLimiter singleton."""
    return _limiter


# =============================================================================
# Key Functions
# =============================================================================


def _default_key_func(request: Request) -> str:
    """Default key: authenticated user_id > IP address."""
    # Try to get user from resolved dependencies (set by Depends)
    if hasattr(request.state, "user"):
        user = request.state.user
        user_id = getattr(user, "id", None)
        if user_id:
            return f"user:{user_id}"

    # Fall back to IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


def user_or_ip_key(request: Request) -> str:
    """Key by user_id (if authenticated) or IP address."""
    return _default_key_func(request)


def org_key(request: Request) -> str:
    """Key by organization_id — useful for org-wide budget caps."""
    if hasattr(request.state, "user"):
        org_id = getattr(request.state.user, "organization_id", None)
        if org_id:
            return f"org:{org_id}"
    return _default_key_func(request)


def ip_key(request: Request) -> str:
    """Key strictly by IP (ignores user identity)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}"


# =============================================================================
# Decorator
# =============================================================================


def rate_limit(
    limit: int = 100,
    window: int = 60,
    key_func: Optional[Callable[[Request], str]] = None,
):
    """Decorator that rate-limits a FastAPI endpoint handler.

    Parameters
    ----------
    limit : int
        Maximum number of requests per *window* seconds.
    window : int
        Sliding window size in seconds.
    key_func : callable, optional
        ``(Request) -> str`` function to generate the rate-limit key.
        Defaults to user_id or IP address.

    When the limit is exceeded, a 429 Too Many Requests response is returned
    with ``Retry-After`` header and ``X-RateLimit-*`` headers.

    The decorator inspects handler signatures to find the ``request: Request``
    parameter.  It works with both ``async def`` and plain ``def`` handlers.
    """
    resolve_key = key_func or _default_key_func

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Locate the Request object
            request: Optional[Request] = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                # Cannot rate-limit without a Request — let the call through
                logger.warning(
                    "rate_limit decorator on %s: no Request found in args/kwargs",
                    func.__name__,
                )
                return await func(*args, **kwargs)

            # Build a namespaced key: "rl:<endpoint>:<identity>"
            endpoint_name = func.__name__
            identity = resolve_key(request)
            rl_key = f"rl:{endpoint_name}:{identity}"

            limiter = get_rate_limiter()
            allowed = limiter.check_rate_limit(rl_key, limit=limit, window=window)

            remaining = limiter.get_remaining(rl_key, limit, window)
            reset = limiter.get_reset_time(rl_key, window)

            if not allowed:
                logger.warning(
                    "Rate limit exceeded: endpoint=%s key=%s limit=%d/%ds",
                    endpoint_name,
                    identity,
                    limit,
                    window,
                )
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "limit": limit,
                        "window_seconds": window,
                        "retry_after": reset,
                    },
                    headers={
                        "Retry-After": str(reset),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset),
                    },
                )

            # Call the actual handler
            response = await func(*args, **kwargs)

            # Attach rate-limit headers if the response is a JSONResponse /
            # Response object.  For dict returns (auto-serialised by FastAPI),
            # we store the headers on the request state so middleware can pick
            # them up.  In practice, most callers just need the 429 protection.
            if hasattr(response, "headers"):
                response.headers["X-RateLimit-Limit"] = str(limit)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Reset"] = str(reset)
            else:
                # Store on request.state for middleware/hooks that want to add
                # headers to the final response.
                request.state.rate_limit_headers = {
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(reset),
                }

            return response

        return wrapper
    return decorator


# =============================================================================
# Predefined Rate Limit Profiles
# =============================================================================

# File uploads — generous but bounded
UPLOAD_LIMIT = rate_limit(limit=10, window=60)

# AI-powered operations (classification, review, extraction)
AI_LIMIT = rate_limit(limit=30, window=60)

# Read endpoints (listings, details, stats)
READ_LIMIT = rate_limit(limit=100, window=60)

# Write/mutation endpoints (create, update, delete)
WRITE_LIMIT = rate_limit(limit=50, window=60)

# Authentication / token generation — tight to prevent brute force
AUTH_LIMIT = rate_limit(limit=5, window=300)

# E-signature token generation — moderate, per-hour
ESIGN_TOKEN_LIMIT = rate_limit(limit=10, window=3600)
