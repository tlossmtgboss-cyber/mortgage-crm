"""
API Rate Limiting Middleware — Per-User and Per-IP Sliding Window

Enterprise-grade API rate limiting using a sliding window algorithm.
Applies globally to all API requests with per-prefix overrides for
expensive or high-frequency endpoints.

Architecture:
    - Per-user rate limiting for authenticated requests (user ID from JWT)
    - Per-IP rate limiting for unauthenticated requests
    - Redis-backed sliding window when available; in-memory fallback
    - Per-prefix limit overrides (AI endpoints lower, dashboard polling higher)
    - Standard rate limit response headers on every response
    - Exempt paths for health checks, CSRF, and public webhooks

This middleware complements (does not replace) the existing rate limiters:
    - security_middleware.RateLimitMiddleware — role-based tiers, burst protection
    - middleware/tenant_rate_limiter.py — per-organization quotas
    - middleware/mobile_rate_limit.py — mobile-specific limits
    - middleware/rate_limiter.py — per-endpoint decorator

This layer enforces a hard per-identity ceiling with prefix-specific tuning,
independent of user role or tenant.  It is the final safety net before the
application layer.

Middleware ordering:
    Add AFTER TenantContextMiddleware (so request.state.user is available)
    and BEFORE the response-level middleware (CORS, PII filter).

Environment variables:
    API_RL_ENABLED              Enable/disable (default: true)
    API_RL_AUTH_RPM              Authenticated default req/min (default: 60)
    API_RL_UNAUTH_RPM            Unauthenticated default req/min (default: 20)
    API_RL_AI_RPM                /api/v1/ai/ req/min (default: 30)
    API_RL_SECURITY_RPM          /api/v1/security/ req/min (default: 100)
    API_RL_PIPELINE_RPM          /api/v1/pipeline/ req/min (default: 120)
    API_RL_MAX_KEYS              Max tracked keys before eviction (default: 50000)
    API_RL_REDIS_PREFIX          Redis key prefix (default: "apirl:")
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
# Environment helpers
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
        logger.warning("Invalid integer for %s=%r, using default %d", name, val, default)
        return default


# ---------------------------------------------------------------------------
# Configuration — all tuneable via environment variables
# ---------------------------------------------------------------------------

ENABLED = _env_bool("API_RL_ENABLED", True)
AUTH_RPM = _env_int("API_RL_AUTH_RPM", 300)
UNAUTH_RPM = _env_int("API_RL_UNAUTH_RPM", 30)
AI_RPM = _env_int("API_RL_AI_RPM", 120)
SECURITY_RPM = _env_int("API_RL_SECURITY_RPM", 100)
PIPELINE_RPM = _env_int("API_RL_PIPELINE_RPM", 120)
MAX_KEYS = _env_int("API_RL_MAX_KEYS", 50_000)
REDIS_PREFIX = os.getenv("API_RL_REDIS_PREFIX", "apirl:")

WINDOW_SECONDS = 60  # 1-minute sliding window

# Paths exempt from rate limiting entirely
EXEMPT_PATHS = frozenset({
    "/health",
    "/health/live",
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/metrics",
    "/csrf-token",
    "/api/v1/csrf-token",
})

# Auth endpoints have their own dedicated rate limiting (mobile_rate_limit.py)
EXEMPT_PREFIXES_AUTH = (
    "/api/v1/account/start",
    "/api/v1/auth/login",
    "/token",
)

# Exempt prefixes — webhooks, public endpoints, and internal server-to-server
# calls are rate-limited elsewhere or self-authenticated
EXEMPT_PREFIXES = (
    "/api/v1/webhook/",
    "/api/v1/public/",
    "/api/vapi/",
    "/api/v1/telephony/",
    "/internal/",
)

# Prefix-specific rate limits.  Evaluated in order; first match wins.
# Uses env-var values so operators can tune without code changes.
PREFIX_LIMITS: List[Tuple[str, int]] = [
    ("/api/v1/ai/", AI_RPM),
    ("/api/v1/chat/", AI_RPM),
    ("/api/v1/agents/", AI_RPM),
    ("/api/v1/security/", SECURITY_RPM),
    ("/api/v1/audit/", SECURITY_RPM),
    ("/api/v1/pipeline/", PIPELINE_RPM),
    ("/api/v1/dashboard/", PIPELINE_RPM),
]


def _get_limit_for_request(path: str, is_authenticated: bool) -> int:
    """Return the per-minute limit for a given path and auth state."""
    path_lower = path.lower()
    for prefix, limit in PREFIX_LIMITS:
        if path_lower.startswith(prefix):
            return limit
    return AUTH_RPM if is_authenticated else UNAUTH_RPM


# ---------------------------------------------------------------------------
# In-Memory Sliding Window Store
# ---------------------------------------------------------------------------


class _SlidingWindowStore:
    """Thread-safe in-memory sliding window counter.

    Each key gets a deque of monotonic timestamps.  The deque is pruned on
    every check to discard entries outside the window.  Periodic cleanup
    removes fully-stale keys to bound memory.
    """

    def __init__(self, cleanup_interval: int = 120, max_keys: int = MAX_KEYS) -> None:
        self._buckets: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = cleanup_interval
        self._max_keys = max_keys

    def check(
        self,
        key: str,
        limit: int,
        window: int = WINDOW_SECONDS,
    ) -> Tuple[bool, int, int]:
        """Check whether the request is allowed.

        Returns:
            (allowed, remaining, reset_seconds)
            - allowed: True if under limit
            - remaining: requests left in window
            - reset_seconds: seconds until oldest entry expires (0 if allowed)
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
                reset_seconds = max(1, int((oldest + window) - now))
                return False, 0, reset_seconds

            bucket.append(now)
            remaining = limit - current_count - 1
            return True, remaining, 0

    def _maybe_cleanup(self, now: float) -> None:
        """Remove fully-stale buckets and evict oldest if over capacity."""
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now

        stale_keys = [
            key for key, bucket in self._buckets.items()
            if not bucket or bucket[-1] < now - 3600
        ]
        for key in stale_keys:
            del self._buckets[key]

        if len(self._buckets) > self._max_keys:
            sorted_keys = sorted(
                self._buckets.keys(),
                key=lambda k: self._buckets[k][-1] if self._buckets[k] else 0,
            )
            evict_count = len(self._buckets) - self._max_keys
            for key in sorted_keys[:evict_count]:
                del self._buckets[key]
            logger.warning(
                "API rate limiter emergency eviction: removed %d stale keys "
                "(total was %d, max %d)",
                evict_count,
                evict_count + self._max_keys,
                self._max_keys,
            )

        if stale_keys:
            logger.debug("API rate limiter cleanup: removed %d stale keys", len(stale_keys))


# ---------------------------------------------------------------------------
# Redis Sliding Window Store
# ---------------------------------------------------------------------------


class _RedisSlidingWindowStore:
    """Redis-backed sliding window using sorted sets.

    Each key is a Redis sorted set where members are unique request IDs
    and scores are timestamps.  ZREMRANGEBYSCORE prunes old entries,
    ZCARD counts current entries, and ZADD adds the new request — all
    in a single pipeline for atomicity.
    """

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def check(
        self,
        key: str,
        limit: int,
        window: int = WINDOW_SECONDS,
    ) -> Tuple[bool, int, int]:
        """Check whether the request is allowed using Redis sorted sets.

        Returns:
            (allowed, remaining, reset_seconds)
        """
        now = time.time()
        redis_key = f"{REDIS_PREFIX}{key}"
        cutoff = now - window

        try:
            pipe = self._redis.pipeline()
            # Remove expired entries
            pipe.zremrangebyscore(redis_key, 0, cutoff)
            # Count current entries
            pipe.zcard(redis_key)
            # Add this request (use timestamp + counter as member for uniqueness)
            member = f"{now}:{id(pipe)}"
            pipe.zadd(redis_key, {member: now})
            # Set TTL to auto-expire the key after the window
            pipe.expire(redis_key, window + 10)
            results = pipe.execute()

            current_count = results[1]  # ZCARD result (before adding new entry)

            if current_count >= limit:
                # Over limit — remove the entry we just added
                self._redis.zrem(redis_key, member)
                # Get oldest entry to compute reset time
                oldest = self._redis.zrange(redis_key, 0, 0, withscores=True)
                if oldest:
                    oldest_ts = oldest[0][1]
                    reset_seconds = max(1, int((oldest_ts + window) - now))
                else:
                    reset_seconds = window
                return False, 0, reset_seconds

            remaining = limit - current_count - 1
            return True, remaining, 0

        except Exception as exc:
            # Any Redis error — caller should fall back to in-memory
            raise exc


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


def _build_key(request: Request) -> Tuple[str, bool]:
    """Build a rate limit key from the request.

    Returns:
        (key, is_authenticated)
    """
    user = getattr(getattr(request, "state", None), "user", None)
    user_id = getattr(user, "id", None) if user else None

    if user_id:
        return f"user:{user_id}", True

    # Fall back to IP
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    return f"ip:{ip}", False


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class APIRateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware enforcing per-identity API rate limits.

    Uses Redis sliding window when available, falls back to in-memory.
    Attaches X-RateLimit-* headers to all responses.
    Returns 429 Too Many Requests with Retry-After when exceeded.
    """

    def __init__(self, app, enabled: bool = ENABLED) -> None:
        super().__init__(app)
        self.enabled = enabled
        self._memory_store = _SlidingWindowStore()
        self._redis_store: Optional[_RedisSlidingWindowStore] = None
        self._redis_available = False

        # Deduplicated log tracking — avoid flooding logs for the same key
        self._logged_keys: set = set()
        self._logged_keys_lock = threading.Lock()
        self._last_log_clear = time.monotonic()

        # Try to connect to Redis
        self._connect_redis()

    def _connect_redis(self) -> None:
        """Attempt to connect to Redis for distributed rate limiting."""
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.info("APIRateLimitMiddleware: No REDIS_URL — using in-memory store")
            return

        try:
            import redis
            client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            self._redis_store = _RedisSlidingWindowStore(client)
            self._redis_available = True
            logger.info("APIRateLimitMiddleware: Redis connected — using Redis-backed sliding window")
        except Exception as exc:
            logger.warning(
                "APIRateLimitMiddleware: Redis unavailable (%s) — using in-memory store", exc
            )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        # Skip exempt paths
        if path in EXEMPT_PATHS:
            return await call_next(request)

        # Skip exempt prefixes
        if any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES):
            return await call_next(request)

        # Auth endpoints have dedicated rate limiting elsewhere
        if any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES_AUTH):
            return await call_next(request)

        # Skip OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Build identity key
        identity_key, is_authenticated = _build_key(request)

        # Determine limit for this path + auth state
        limit = _get_limit_for_request(path, is_authenticated)

        # Check rate limit — Redis first, fall back to in-memory
        allowed, remaining, reset_seconds = self._check(identity_key, limit)

        if not allowed:
            self._log_rate_limit_hit(identity_key, path, limit, reset_seconds)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests",
                    "detail": f"Rate limit of {limit} requests per minute exceeded. "
                              f"Retry after {reset_seconds} seconds.",
                    "retry_after": reset_seconds,
                },
                headers={
                    "Retry-After": str(reset_seconds),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_seconds),
                },
            )

        # Proceed with the request
        response = await call_next(request)

        # Attach rate limit headers to every response
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        if reset_seconds:
            response.headers["X-RateLimit-Reset"] = str(reset_seconds)

        return response

    def _check(
        self, key: str, limit: int
    ) -> Tuple[bool, int, int]:
        """Check rate limit using Redis or in-memory fallback."""
        if self._redis_available and self._redis_store is not None:
            try:
                return self._redis_store.check(key, limit, WINDOW_SECONDS)
            except Exception as exc:
                logger.warning(
                    "APIRateLimitMiddleware: Redis error (%s) — falling back to in-memory",
                    exc,
                )
                self._redis_available = False

        return self._memory_store.check(key, limit, WINDOW_SECONDS)

    def _log_rate_limit_hit(
        self,
        key: str,
        path: str,
        limit: int,
        reset_seconds: int,
    ) -> None:
        """Log rate limit hits without flooding — one log per key per 60s."""
        now = time.monotonic()
        with self._logged_keys_lock:
            if now - self._last_log_clear > 60:
                self._logged_keys.clear()
                self._last_log_clear = now
            if key in self._logged_keys:
                return
            self._logged_keys.add(key)

        logger.warning(
            "API rate limit exceeded: key=%s path=%s limit=%d/min retry_after=%ds",
            key,
            path,
            limit,
            reset_seconds,
        )
