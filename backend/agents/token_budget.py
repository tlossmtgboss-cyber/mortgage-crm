"""
Token Budget & Rate Limiter for AI Orchestrator

Enforces per-org token budgets and per-tenant request rate limits
to prevent unbounded API costs and resource monopolization.

Redis-backed for multi-replica correctness (Railway numReplicas=2).
Falls back to in-memory with conservative limits in production if
Redis is unavailable, or full limits in development.
"""

import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Conservative fraction of budget when Redis is down in production.
# Each replica gets 1/4 of the budget — with 2 replicas that's 1/2 total,
# providing a safety margin against overspend.
_DEGRADED_BUDGET_FRACTION = 0.25


def _degraded_hard_cap() -> int:
    """Absolute per-replica token ceiling when Redis is unavailable in prod.

    Without Redis we cannot coordinate spend across an unknown number of
    replicas, so beyond the fraction-based degraded budget we also enforce an
    ABSOLUTE hard cap. Once a replica hits this ceiling it fails CLOSED (denies)
    regardless of the configured per-org budget — bounding worst-case multi-
    replica overspend during a Redis outage.

    Configurable via AI_DEGRADED_HARD_CAP_TOKENS (default 100k tokens/replica/period).
    """
    try:
        return max(0, int(os.getenv("AI_DEGRADED_HARD_CAP_TOKENS", "100000")))
    except (TypeError, ValueError):
        return 100_000


def _is_production() -> bool:
    """Check if running in production (Railway or ENVIRONMENT=production)."""
    return bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("ENVIRONMENT", "").lower() in ("production", "prod")
    )


def _get_redis_client():
    """
    Create a synchronous Redis client from REDIS_URL.

    Returns None if REDIS_URL is not set or connection fails.
    Uses the same pattern as auth/tokens.py and security_middleware.py.
    """
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        import redis
        client = redis.from_url(
            redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
        )
        client.ping()
        return client
    except Exception as e:
        if _is_production():
            logger.critical(
                f"[TOKEN_BUDGET] Redis connection FAILED in production: {e}. "
                "Token budgets and rate limits will use CONSERVATIVE in-memory fallback. "
                "Cross-replica enforcement is DISABLED."
            )
        else:
            logger.warning(
                f"[TOKEN_BUDGET] Redis unavailable ({e}). "
                "Using full in-memory fallback (development mode)."
            )
        return None


# =============================================================================
# Token Budget
# =============================================================================

@dataclass
class OrgUsage:
    """Token usage for a single organization in the current period."""
    tokens_used: int = 0
    requests: int = 0
    period_start: float = field(default_factory=time.time)


class TokenBudget:
    """
    Per-organization token budget enforcement.

    Tracks token usage per org and blocks requests when the budget is exhausted.
    Budget resets at the start of each period (default: 1 hour).

    When Redis is available, uses atomic INCRBY + EXPIRE for cross-replica
    accuracy. When Redis is unavailable:
    - Production: Uses conservative in-memory limits (25% of configured budget
      per replica) and logs CRITICAL.
    - Development: Uses full in-memory limits.

    Usage:
        budget = TokenBudget(max_tokens_per_org=500_000, period_seconds=3600)

        if not budget.check_budget(org_id):
            return "Budget exceeded"

        # ... run LLM ...

        budget.record_usage(org_id, tokens_used=1500)
    """

    # Redis key prefixes
    _KEY_TOKENS = "ai_budget:tokens"
    _KEY_REQUESTS = "ai_budget:requests"

    def __init__(
        self,
        max_tokens_per_org: int = 500_000,
        period_seconds: int = 3600,
        redis_client=None,
    ):
        self.max_tokens_per_org = max_tokens_per_org
        self.period_seconds = period_seconds

        # Redis client — set externally or auto-detected
        self._redis = redis_client
        self._redis_available = redis_client is not None

        # In-memory fallback
        self._usage: Dict[int, OrgUsage] = defaultdict(OrgUsage)
        self._lock = Lock()

        # Effective budget when in degraded (in-memory) mode.
        # In production without Redis, take the MIN of the fraction-based
        # budget and an absolute hard cap so worst-case multi-replica spend is
        # bounded and the limiter fails CLOSED once the cap is hit.
        if _is_production() and not self._redis_available:
            self._degraded_max = min(
                int(max_tokens_per_org * _DEGRADED_BUDGET_FRACTION),
                _degraded_hard_cap(),
            )
        else:
            self._degraded_max = max_tokens_per_org

    def _connect_redis(self) -> bool:
        """Lazily attempt Redis connection if not already connected."""
        if self._redis_available:
            return True
        client = _get_redis_client()
        if client:
            self._redis = client
            self._redis_available = True
            # Restore full budget now that Redis is available
            self._degraded_max = self.max_tokens_per_org
            logger.info("[TOKEN_BUDGET] Redis connection established — using Redis-backed counters")
            return True
        return False

    def _current_window(self) -> int:
        """Get the current time window index for key bucketing."""
        return int(time.time() // self.period_seconds)

    def _redis_key(self, org_id: int, metric: str) -> str:
        """Build a Redis key for the current window."""
        window = self._current_window()
        return f"{metric}:{org_id}:{window}"

    def _activate_fallback(self, operation: str, error: Exception) -> None:
        """Switch to in-memory fallback on Redis failure."""
        if self._redis_available:
            self._redis_available = False
            if _is_production():
                self._degraded_max = min(
                    int(self.max_tokens_per_org * _DEGRADED_BUDGET_FRACTION),
                    _degraded_hard_cap(),
                )
                logger.critical(
                    f"[TOKEN_BUDGET] Redis failed during {operation}: {error}. "
                    f"Switching to CONSERVATIVE in-memory fallback "
                    f"({self._degraded_max}/{self.max_tokens_per_org} tokens per replica, "
                    f"hard cap {_degraded_hard_cap()})."
                )
            else:
                self._degraded_max = self.max_tokens_per_org
                logger.warning(
                    f"[TOKEN_BUDGET] Redis failed during {operation}: {error}. "
                    "Using full in-memory fallback (development mode)."
                )

    # --- In-memory fallback methods (same as original) ---

    def _get_or_reset(self, org_id: int) -> OrgUsage:
        """Get usage for org, resetting if period has expired."""
        usage = self._usage[org_id]
        now = time.time()
        if now - usage.period_start >= self.period_seconds:
            usage.tokens_used = 0
            usage.requests = 0
            usage.period_start = now
        return usage

    def _memory_check_budget(self, org_id: int) -> bool:
        with self._lock:
            usage = self._get_or_reset(org_id)
            return usage.tokens_used < self._degraded_max

    def _memory_record_usage(self, org_id: int, tokens_used: int) -> None:
        with self._lock:
            usage = self._get_or_reset(org_id)
            usage.tokens_used += tokens_used
            usage.requests += 1

    def _memory_get_usage(self, org_id: int) -> Tuple[int, int, int]:
        with self._lock:
            usage = self._get_or_reset(org_id)
            remaining = max(0, self._degraded_max - usage.tokens_used)
            return usage.tokens_used, usage.requests, remaining

    def _memory_get_remaining(self, org_id: int) -> int:
        with self._lock:
            usage = self._get_or_reset(org_id)
            return max(0, self._degraded_max - usage.tokens_used)

    # --- Lua scripts for atomic reserve ---

    # Atomic check-and-reserve: reads current value, checks if adding the
    # increment would exceed the budget, and only increments if it fits.
    # Lua scripts execute atomically in Redis (single-threaded), so no other
    # command can interleave between the GET and INCRBY.
    #
    # KEYS[1] = token counter key
    # ARGV[1] = estimated tokens to reserve
    # ARGV[2] = max budget for the period
    # ARGV[3] = TTL in seconds for the key
    #
    # Returns: new total (>= 0) on success, -1 if budget would be exceeded
    _RESERVE_SCRIPT = """
local key = KEYS[1]
local increment = tonumber(ARGV[1])
local max_budget = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local current = tonumber(redis.call('GET', key) or '0')
if current + increment > max_budget then
    return -1
end
local new_total = redis.call('INCRBY', key, increment)
redis.call('EXPIRE', key, ttl)
return new_total
"""

    def __init_reserve_script(self):
        """Register the Lua reserve script with Redis (lazy, once)."""
        if not hasattr(self, '_reserve_sha'):
            self._reserve_sha = None
        if self._reserve_sha is None and self._redis_available:
            try:
                self._reserve_sha = self._redis.register_script(
                    self._RESERVE_SCRIPT
                )
            except Exception as e:
                logger.warning(f"[TOKEN_BUDGET] Failed to register Lua script: {e}")
                self._reserve_sha = None

    # --- In-memory fallback for reservations ---

    def _memory_reserve_budget(self, org_id: int, estimated_tokens: int) -> bool:
        """Atomic check-and-reserve using in-memory lock."""
        with self._lock:
            usage = self._get_or_reset(org_id)
            if usage.tokens_used + estimated_tokens > self._degraded_max:
                return False
            usage.tokens_used += estimated_tokens
            usage.requests += 1
            return True

    def _memory_adjust_reservation(
        self, org_id: int, estimated_tokens: int, actual_tokens: int
    ) -> None:
        """Correct reservation estimate with actual usage (in-memory)."""
        with self._lock:
            usage = self._get_or_reset(org_id)
            delta = actual_tokens - estimated_tokens
            usage.tokens_used = max(0, usage.tokens_used + delta)

    # --- Public API ---

    def reserve_budget(self, org_id: int, estimated_tokens: int) -> bool:
        """
        Atomically check and reserve tokens for an upcoming LLM call.

        This is the PREFERRED method over the check_budget() + record_usage()
        pattern. It eliminates the race condition where concurrent requests
        both pass check_budget() and overspend.

        Args:
            org_id: Organization ID.
            estimated_tokens: Estimated tokens for the upcoming LLM call.
                Use a conservative (high) estimate. After the call completes,
                call adjust_reservation() to correct the difference.

        Returns:
            True if the reservation succeeded (tokens were reserved).
            False if the budget would be exceeded (no tokens were reserved).
        """
        if self._redis_available:
            try:
                self.__init_reserve_script()
                if self._reserve_sha is not None:
                    key = self._redis_key(org_id, self._KEY_TOKENS)
                    ttl = self.period_seconds + 60
                    result = self._reserve_sha(
                        keys=[key],
                        args=[estimated_tokens, self.max_tokens_per_org, ttl],
                    )
                    result = int(result)
                    if result == -1:
                        logger.warning(
                            f"[BUDGET] Org {org_id} reservation denied: "
                            f"adding {estimated_tokens} would exceed "
                            f"{self.max_tokens_per_org} budget"
                        )
                        return False
                    # Reservation succeeded — also bump request counter
                    try:
                        req_key = self._redis_key(org_id, self._KEY_REQUESTS)
                        pipe = self._redis.pipeline()
                        pipe.incr(req_key)
                        pipe.expire(req_key, self.period_seconds + 60)
                        pipe.execute()
                    except Exception:
                        pass  # Request counter is best-effort
                    logger.debug(
                        f"[BUDGET] Org {org_id}: reserved {estimated_tokens} tokens, "
                        f"new total {result}/{self.max_tokens_per_org}"
                    )
                    return True
                else:
                    # Lua script not available — fall through to in-memory
                    logger.warning(
                        "[TOKEN_BUDGET] Lua script unavailable, using in-memory fallback"
                    )
            except Exception as e:
                self._activate_fallback("reserve_budget", e)

        # In-memory fallback
        allowed = self._memory_reserve_budget(org_id, estimated_tokens)
        if not allowed:
            with self._lock:
                usage = self._get_or_reset(org_id)
                logger.warning(
                    f"[BUDGET] Org {org_id} reservation denied (in-memory): "
                    f"{usage.tokens_used} + {estimated_tokens} would exceed "
                    f"{self._degraded_max} budget"
                )
        return allowed

    def adjust_reservation(
        self, org_id: int, estimated_tokens: int, actual_tokens: int
    ) -> None:
        """
        Correct a previous reservation after the LLM call completes.

        Call this after reserve_budget() once you know the actual token count.
        If actual < estimated, the difference is released back to the budget.
        If actual > estimated, the additional usage is recorded.

        Args:
            org_id: Organization ID.
            estimated_tokens: The estimate originally passed to reserve_budget().
            actual_tokens: The actual tokens consumed by the LLM call.
        """
        delta = actual_tokens - estimated_tokens
        if delta == 0:
            return  # Estimate was exact, nothing to adjust

        if self._redis_available:
            try:
                key = self._redis_key(org_id, self._KEY_TOKENS)
                ttl = self.period_seconds + 60
                if delta > 0:
                    # Underestimated — add the difference
                    pipe = self._redis.pipeline()
                    pipe.incrby(key, delta)
                    pipe.expire(key, ttl)
                    results = pipe.execute()
                    new_total = int(results[0])
                else:
                    # Overestimated — release the difference (DECRBY)
                    pipe = self._redis.pipeline()
                    pipe.decrby(key, abs(delta))
                    pipe.expire(key, ttl)
                    results = pipe.execute()
                    new_total = int(results[0])
                    # Guard against going negative (shouldn't happen, but be safe)
                    if new_total < 0:
                        self._redis.set(key, 0)
                        self._redis.expire(key, ttl)
                        new_total = 0
                logger.debug(
                    f"[BUDGET] Org {org_id}: adjusted reservation "
                    f"(estimated={estimated_tokens}, actual={actual_tokens}, "
                    f"delta={delta:+d}), new total={new_total}"
                )
                return
            except Exception as e:
                self._activate_fallback("adjust_reservation", e)

        # In-memory fallback
        self._memory_adjust_reservation(org_id, estimated_tokens, actual_tokens)
        logger.debug(
            f"[BUDGET] Org {org_id}: adjusted reservation (in-memory) "
            f"(estimated={estimated_tokens}, actual={actual_tokens}, "
            f"delta={delta:+d})"
        )

    def check_budget(self, org_id: int) -> bool:
        """
        Check if an organization has remaining token budget.

        Returns True if the request should be allowed.
        """
        if self._redis_available:
            try:
                key = self._redis_key(org_id, self._KEY_TOKENS)
                current = self._redis.get(key)
                tokens_used = int(current) if current else 0
                allowed = tokens_used < self.max_tokens_per_org
                if not allowed:
                    req_key = self._redis_key(org_id, self._KEY_REQUESTS)
                    req_count = self._redis.get(req_key)
                    logger.warning(
                        f"[BUDGET] Org {org_id} exceeded token budget: "
                        f"{tokens_used}/{self.max_tokens_per_org} tokens used "
                        f"in {int(req_count) if req_count else 0} requests"
                    )
                return allowed
            except Exception as e:
                self._activate_fallback("check_budget", e)

        # In-memory fallback
        allowed = self._memory_check_budget(org_id)
        if not allowed:
            with self._lock:
                usage = self._get_or_reset(org_id)
                logger.warning(
                    f"[BUDGET] Org {org_id} exceeded token budget (in-memory): "
                    f"{usage.tokens_used}/{self._degraded_max} tokens used "
                    f"in {usage.requests} requests"
                )
        return allowed

    def record_usage(self, org_id: int, tokens_used: int) -> None:
        """Record token usage for an organization."""
        if self._redis_available:
            try:
                token_key = self._redis_key(org_id, self._KEY_TOKENS)
                req_key = self._redis_key(org_id, self._KEY_REQUESTS)
                ttl = self.period_seconds + 60  # Extra 60s margin for clock skew

                pipe = self._redis.pipeline()
                pipe.incrby(token_key, tokens_used)
                pipe.expire(token_key, ttl)
                pipe.incr(req_key)
                pipe.expire(req_key, ttl)
                results = pipe.execute()

                new_total = int(results[0])
                new_requests = int(results[2])
                logger.debug(
                    f"[BUDGET] Org {org_id}: {new_total}/{self.max_tokens_per_org} "
                    f"tokens ({new_requests} requests)"
                )
                return
            except Exception as e:
                self._activate_fallback("record_usage", e)

        # In-memory fallback
        self._memory_record_usage(org_id, tokens_used)
        with self._lock:
            usage = self._get_or_reset(org_id)
            logger.debug(
                f"[BUDGET] Org {org_id}: {usage.tokens_used}/{self._degraded_max} "
                f"tokens ({usage.requests} requests) [in-memory]"
            )

    def get_remaining(self, org_id: int) -> int:
        """Get remaining tokens for an organization."""
        if self._redis_available:
            try:
                key = self._redis_key(org_id, self._KEY_TOKENS)
                current = self._redis.get(key)
                tokens_used = int(current) if current else 0
                return max(0, self.max_tokens_per_org - tokens_used)
            except Exception as e:
                self._activate_fallback("get_remaining", e)

        return self._memory_get_remaining(org_id)

    def get_usage(self, org_id: int) -> Tuple[int, int, int]:
        """Get (tokens_used, requests, remaining) for an org."""
        if self._redis_available:
            try:
                token_key = self._redis_key(org_id, self._KEY_TOKENS)
                req_key = self._redis_key(org_id, self._KEY_REQUESTS)

                pipe = self._redis.pipeline()
                pipe.get(token_key)
                pipe.get(req_key)
                results = pipe.execute()

                tokens_used = int(results[0]) if results[0] else 0
                requests = int(results[1]) if results[1] else 0
                remaining = max(0, self.max_tokens_per_org - tokens_used)
                return tokens_used, requests, remaining
            except Exception as e:
                self._activate_fallback("get_usage", e)

        return self._memory_get_usage(org_id)


# =============================================================================
# Rate Limiter (Sliding Window Counter via Redis, Token Bucket in-memory)
# =============================================================================

@dataclass
class _Bucket:
    """Token bucket state for a single tenant (in-memory fallback)."""
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.time)


class RateLimiter:
    """
    Per-tenant rate limiter.

    When Redis is available, uses a sliding window counter approach:
    - INCR + EXPIRE on per-minute window keys for atomic cross-replica counting.

    When Redis is unavailable, falls back to in-memory token bucket algorithm.
    In production, the in-memory burst limit is reduced to prevent per-replica
    multiplication.

    Usage:
        limiter = RateLimiter(requests_per_minute=30, max_burst=10)

        allowed, retry_after = limiter.check_rate_limit(org_id)
        if not allowed:
            return f"Rate limited. Retry after {retry_after:.1f}s"
    """

    _KEY_PREFIX = "ai_ratelimit"

    def __init__(
        self,
        requests_per_minute: int = 30,
        max_burst: int = 10,
        redis_client=None,
    ):
        self.requests_per_minute = requests_per_minute
        self.rate = requests_per_minute / 60.0  # tokens per second
        self.max_burst = max_burst

        # Redis client
        self._redis = redis_client
        self._redis_available = redis_client is not None

        # In-memory fallback (token bucket)
        self._degraded_burst = max_burst
        if _is_production() and not self._redis_available:
            # Conservative: each replica gets fewer burst tokens
            self._degraded_burst = max(1, int(max_burst * _DEGRADED_BUDGET_FRACTION))
            self._degraded_rpm = max(1, int(requests_per_minute * _DEGRADED_BUDGET_FRACTION))
        else:
            self._degraded_rpm = requests_per_minute

        self._buckets: Dict[int, _Bucket] = defaultdict(
            lambda: _Bucket(tokens=self._degraded_burst)
        )
        self._lock = Lock()

    def _connect_redis(self) -> bool:
        """Lazily attempt Redis connection if not already connected."""
        if self._redis_available:
            return True
        client = _get_redis_client()
        if client:
            self._redis = client
            self._redis_available = True
            self._degraded_burst = self.max_burst
            self._degraded_rpm = self.requests_per_minute
            logger.info("[RATE_LIMIT] Redis connection established — using Redis-backed counters")
            return True
        return False

    def _activate_fallback(self, operation: str, error: Exception) -> None:
        """Switch to in-memory fallback on Redis failure."""
        if self._redis_available:
            self._redis_available = False
            if _is_production():
                self._degraded_burst = max(1, int(self.max_burst * _DEGRADED_BUDGET_FRACTION))
                self._degraded_rpm = max(1, int(self.requests_per_minute * _DEGRADED_BUDGET_FRACTION))
                logger.critical(
                    f"[RATE_LIMIT] Redis failed during {operation}: {error}. "
                    f"Switching to CONSERVATIVE in-memory fallback "
                    f"({self._degraded_rpm} req/min, burst={self._degraded_burst} per replica)."
                )
            else:
                self._degraded_burst = self.max_burst
                self._degraded_rpm = self.requests_per_minute
                logger.warning(
                    f"[RATE_LIMIT] Redis failed during {operation}: {error}. "
                    "Using full in-memory fallback (development mode)."
                )

    # --- In-memory token bucket fallback ---

    def _refill(self, bucket: _Bucket) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - bucket.last_refill
        degraded_rate = self._degraded_rpm / 60.0
        bucket.tokens = min(
            self._degraded_burst,
            bucket.tokens + elapsed * degraded_rate
        )
        bucket.last_refill = now

    def _memory_check_rate_limit(self, org_id: int) -> Tuple[bool, float]:
        with self._lock:
            bucket = self._buckets[org_id]
            self._refill(bucket)

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0
            else:
                degraded_rate = self._degraded_rpm / 60.0
                deficit = 1.0 - bucket.tokens
                retry_after = deficit / degraded_rate if degraded_rate > 0 else 60.0
                return False, retry_after

    # --- Public API ---

    def check_rate_limit(self, org_id: int) -> Tuple[bool, float]:
        """
        Check if a request is allowed under the rate limit.

        Returns:
            (allowed, retry_after_seconds)
            - allowed: True if request should proceed
            - retry_after: Seconds to wait before retrying (0 if allowed)
        """
        if self._redis_available:
            try:
                now = time.time()
                # Use a 60-second sliding window
                window = int(now // 60)
                key = f"{self._KEY_PREFIX}:{org_id}:{window}"

                pipe = self._redis.pipeline()
                pipe.incr(key)
                pipe.expire(key, 120)  # 2-minute TTL for safety
                results = pipe.execute()

                current_count = int(results[0])

                if current_count <= self.requests_per_minute:
                    return True, 0.0
                else:
                    # Seconds until next window
                    seconds_into_window = now - (window * 60)
                    retry_after = max(0.5, 60.0 - seconds_into_window)
                    logger.warning(
                        f"[RATE_LIMIT] Org {org_id} rate limited: "
                        f"{current_count}/{self.requests_per_minute} requests in window. "
                        f"Retry after {retry_after:.1f}s"
                    )
                    return False, retry_after
            except Exception as e:
                self._activate_fallback("check_rate_limit", e)

        # In-memory token bucket fallback
        allowed, retry_after = self._memory_check_rate_limit(org_id)
        if not allowed:
            logger.warning(
                f"[RATE_LIMIT] Org {org_id} rate limited (in-memory). "
                f"Retry after {retry_after:.1f}s"
            )
        return allowed, retry_after


# =============================================================================
# Singleton instances (configured via env vars, Redis auto-detected)
# =============================================================================

_token_budget: Optional[TokenBudget] = None
_rate_limiter: Optional[RateLimiter] = None


def _init_redis_client():
    """
    Create a shared Redis client for both TokenBudget and RateLimiter singletons.

    Returns None if Redis is not configured or unavailable.
    """
    return _get_redis_client()


def get_token_budget() -> TokenBudget:
    """Get the singleton TokenBudget instance."""
    global _token_budget
    if _token_budget is None:
        max_tokens = int(os.getenv("AI_MAX_TOKENS_PER_ORG_HOUR", "500000"))
        period = int(os.getenv("AI_BUDGET_PERIOD_SECONDS", "3600"))
        redis_client = _init_redis_client()
        _token_budget = TokenBudget(
            max_tokens_per_org=max_tokens,
            period_seconds=period,
            redis_client=redis_client,
        )
        if redis_client:
            logger.info(
                f"[TOKEN_BUDGET] Initialized with Redis — "
                f"{max_tokens} tokens/org, {period}s period"
            )
        else:
            mode = "CONSERVATIVE" if _is_production() else "full"
            effective = int(max_tokens * _DEGRADED_BUDGET_FRACTION) if _is_production() else max_tokens
            logger.warning(
                f"[TOKEN_BUDGET] Initialized WITHOUT Redis — "
                f"{mode} in-memory fallback ({effective} tokens/org/replica)"
            )
    return _token_budget


def get_rate_limiter() -> RateLimiter:
    """Get the singleton RateLimiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        rpm = int(os.getenv("AI_REQUESTS_PER_MINUTE", "30"))
        burst = int(os.getenv("AI_MAX_BURST", "10"))
        redis_client = _init_redis_client()
        _rate_limiter = RateLimiter(
            requests_per_minute=rpm,
            max_burst=burst,
            redis_client=redis_client,
        )
        if redis_client:
            logger.info(
                f"[RATE_LIMIT] Initialized with Redis — "
                f"{rpm} req/min, burst={burst}"
            )
        else:
            mode = "CONSERVATIVE" if _is_production() else "full"
            effective_rpm = max(1, int(rpm * _DEGRADED_BUDGET_FRACTION)) if _is_production() else rpm
            effective_burst = max(1, int(burst * _DEGRADED_BUDGET_FRACTION)) if _is_production() else burst
            logger.warning(
                f"[RATE_LIMIT] Initialized WITHOUT Redis — "
                f"{mode} in-memory fallback ({effective_rpm} req/min, burst={effective_burst}/replica)"
            )
    return _rate_limiter
