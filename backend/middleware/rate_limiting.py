"""
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
DEPRECATED — DO NOT USE — Scheduled for removal
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

Adaptive Rate Limiting & DDoS Protection  [DEPRECATED 2026-04-30]

STATUS: DEAD CODE.  This middleware is NOT registered in main.py and never was.
It is only imported by chat_system_bootstrap.py (which is itself unused).

DO NOT import this module in new code.  All active rate limiting is handled by:
  - middleware/api_rate_limit.py  (APIRateLimitMiddleware) — primary per-user/IP
  - middleware/tenant_rate_limiter.py (TenantRateLimitMiddleware) — per-org
  - middleware/mobile_rate_limit.py  (MobileRateLimitMiddleware) — mobile
  - middleware/rate_limiter.py — decorator-based per-endpoint

This file is retained only to avoid breaking the (unused) chat_system_bootstrap
import.  It will be deleted when chat_system_bootstrap.py is removed.

Original purpose (no longer active):
- Per-tenant rate limiting with tier-based quotas (PERF-004)
- Tiered rate limiting by route category
- Suspicious activity detection
- Automatic stricter limits for bad actors
- Client identification via visitor_id, IP, or fingerprint
- In-memory token bucket fallback when Redis is unavailable
"""

import logging
import hashlib
import time
import threading
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import redis

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Thread-safe in-memory token bucket rate limiter.

    Used as a fallback when Redis is unavailable. Applies conservative limits
    (50% of Redis-backed limits) since state is per-instance, not shared across
    workers.

    Memory-bounded: evicts oldest entries when exceeding MAX_ENTRIES.
    Stale entries (older than STALE_SECONDS) are cleaned up periodically.
    """

    MAX_ENTRIES = 10_000
    STALE_SECONDS = 300  # 5 minutes
    CLEANUP_INTERVAL = 60  # Run cleanup at most once per minute
    CONSERVATIVE_FACTOR = 0.5  # 50% of normal limits

    # Log fallback activation at most once per minute
    _LOG_INTERVAL = 60

    def __init__(self):
        self._buckets: Dict[str, Tuple[float, float, float]] = {}
        # Each value: (tokens_remaining, last_refill_time, max_tokens)
        self._lock = threading.Lock()
        self._last_cleanup = 0.0
        self._last_fallback_log = 0.0

    def log_fallback(self) -> None:
        """Log that we are falling back to in-memory limiter, throttled to once/min."""
        now = time.monotonic()
        if now - self._last_fallback_log >= self._LOG_INTERVAL:
            self._last_fallback_log = now
            logger.warning(
                "Redis unavailable — rate limiter falling back to in-memory token bucket"
            )

    def check(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """Check if a request is allowed under the token bucket.

        Args:
            key: Unique identifier for the rate limit bucket.
            max_requests: The normal (Redis-backed) limit. Will be halved internally.
            window_seconds: Time window in seconds for the limit.

        Returns:
            (allowed, remaining) matching the Redis path return signature.
            ``remaining`` is the estimated tokens left; when denied it is 0.
        """
        now = time.monotonic()
        conservative_max = max(1, int(max_requests * self.CONSERVATIVE_FACTOR))
        refill_rate = conservative_max / max(window_seconds, 1)  # tokens per second

        with self._lock:
            self._maybe_cleanup(now)

            if key in self._buckets:
                tokens, last_refill, _ = self._buckets[key]
                elapsed = now - last_refill
                tokens = min(conservative_max, tokens + elapsed * refill_rate)
            else:
                tokens = float(conservative_max)

            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[key] = (tokens, now, float(conservative_max))
                return True, int(tokens)
            else:
                # Denied — record the attempt time but don't deduct
                self._buckets[key] = (tokens, now, float(conservative_max))
                return False, 0

    def _maybe_cleanup(self, now: float) -> None:
        """Remove stale entries and evict oldest if over capacity.

        Must be called while holding self._lock.
        """
        if now - self._last_cleanup < self.CLEANUP_INTERVAL:
            return
        self._last_cleanup = now

        # Remove entries older than STALE_SECONDS
        stale_cutoff = now - self.STALE_SECONDS
        stale_keys = [
            k for k, (_, last_refill, _) in self._buckets.items()
            if last_refill < stale_cutoff
        ]
        for k in stale_keys:
            del self._buckets[k]

        # If still over capacity, evict oldest entries
        if len(self._buckets) > self.MAX_ENTRIES:
            sorted_keys = sorted(
                self._buckets.keys(),
                key=lambda k: self._buckets[k][1]  # sort by last_refill time
            )
            evict_count = len(self._buckets) - self.MAX_ENTRIES
            for k in sorted_keys[:evict_count]:
                del self._buckets[k]

# Per-tenant rate limit quotas by subscription tier (PERF-004)
# These define the TOTAL requests/min allowed for an entire organization
TENANT_TIER_LIMITS = {
    'lead_management': {'requests_per_min': 200, 'ai_per_min': 60, 'burst_multiplier': 1.5},
    'lead_and_active': {'requests_per_min': 500, 'ai_per_min': 120, 'burst_multiplier': 1.5},
    'full_pipeline': {'requests_per_min': 2000, 'ai_per_min': 200, 'burst_multiplier': 2.0},
    # Fallback for orgs without a recognized tier
    'default': {'requests_per_min': 200, 'ai_per_min': 60, 'burst_multiplier': 1.0},
}


class AdaptiveRateLimiter(BaseHTTPMiddleware):
    """
    Adaptive rate limiting that distinguishes between:
    - Per-tenant org-level limits (prevents noisy neighbor)
    - Per-client individual limits
    - Suspicious activity
    - Bot traffic
    """

    def __init__(self, app, redis_client: redis.Redis):
        super().__init__(app)
        self.redis = redis_client
        self._memory_limiter = InMemoryRateLimiter()

        # Per-client rate limit tiers by route category
        self.LIMITS = {
            'chat_message': {'requests': 60, 'window': 60},      # 60 msg/min
            'session_create': {'requests': 10, 'window': 3600},  # 10 sessions/hour
            'call_initiate': {'requests': 3, 'window': 3600},    # 3 calls/hour
            'analytics': {'requests': 100, 'window': 60},        # 100 req/min
            'public_booking': {'requests': 20, 'window': 60},      # 20 req/min per IP
            'default': {'requests': 120, 'window': 60},          # 120 req/min default
            # API key rate limits (Enterprise Check 11.5)
            'api_key': {'requests': 1000, 'window': 60},         # 1000 req/min for API keys
        }

        # Suspicious activity thresholds
        self.SUSPICIOUS_PATTERNS = {
            'rapid_session_creation': 5,   # 5 sessions in 5 minutes
            'identical_messages': 3,       # Same message 3 times in window
            'fast_typing': 10,             # Messages < 2 seconds apart
        }

        # Blocked clients (in-memory cache, also stored in Redis)
        self.blocked_clients: set = set()

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ['/health', '/api/health', '/metrics']:
            return await call_next(request)

        # Identify client
        client_id = self._get_client_identifier(request)

        # Check if blocked
        if await self._is_blocked(client_id):
            return JSONResponse(
                status_code=403,
                content={"error": "Access denied", "reason": "Too many violations"}
            )

        # Track rate limit info for headers on successful responses
        rl_info: Optional[Dict[str, Any]] = None

        # --- Per-tenant rate limit check (PERF-004) ---
        org_id = getattr(getattr(request, 'state', None), 'organization_id', None)
        if org_id:
            tenant_result = await self._check_tenant_rate_limit(
                org_id, request.url.path
            )
            if not tenant_result['allowed']:
                logger.warning(f"Tenant rate limit exceeded for org_id={org_id}")
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Organization rate limit exceeded",
                        "retry_after": tenant_result['retry_after'],
                        "scope": "tenant"
                    },
                    headers={
                        "Retry-After": str(tenant_result['retry_after']),
                        "X-RateLimit-Limit": str(tenant_result['limit']),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(tenant_result['reset']),
                    }
                )

        # --- Per-client rate limit check ---
        # Get route category (now includes client_id for API key detection)
        route_category = self._categorize_route(request.url.path, request.method, client_id)

        if route_category:
            # Check rate limit
            rl_result = await self._check_rate_limit(
                client_id,
                route_category
            )

            if not rl_result['allowed']:
                logger.warning(f"Rate limit exceeded for {client_id} on {route_category}")
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "retry_after": rl_result['retry_after'],
                        "category": route_category
                    },
                    headers={
                        "Retry-After": str(rl_result['retry_after']),
                        "X-RateLimit-Limit": str(rl_result['limit']),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(rl_result['reset']),
                    }
                )

            # Save info for adding headers to successful response
            rl_info = rl_result

            # Check for suspicious patterns (async, non-blocking)
            if route_category == 'chat_message':
                await self._track_activity(client_id, request)

        response = await call_next(request)

        # Attach rate limit headers to successful responses
        if rl_info is not None:
            response.headers["X-RateLimit-Limit"] = str(rl_info['limit'])
            response.headers["X-RateLimit-Remaining"] = str(rl_info['remaining'])
            response.headers["X-RateLimit-Reset"] = str(rl_info['reset'])

        return response

    def _get_client_identifier(self, request: Request) -> str:
        """
        Get unique client identifier with multiple fallback strategies.

        Enterprise Check 11.5: Per-Client Rate Limiting (HIGH - 10pts)

        Priority order:
        1. API Key (X-API-Key header) - for authenticated API access
        2. Visitor ID (X-Visitor-ID header) - for frontend tracking
        3. Session ID (from URL path) - for chat/session endpoints
        4. IP address (with X-Forwarded-For support) - fallback
        """
        # Priority 1: API Key from header (for programmatic access)
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # Hash the key for privacy in Redis
            import hashlib
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            return f"apikey:{key_hash}"

        # Priority 2: Visitor ID from header (set by frontend)
        visitor_id = request.headers.get("X-Visitor-ID")
        if visitor_id:
            return f"visitor:{visitor_id}"

        # Priority 3: Session ID from path (for message endpoints)
        path_parts = request.url.path.split('/')
        if 'sessions' in path_parts:
            try:
                session_idx = path_parts.index('sessions') + 1
                if session_idx < len(path_parts):
                    session_id = path_parts[session_idx]
                    return f"session:{session_id}"
            except (ValueError, IndexError):
                pass

        # Priority 4: IP address (with X-Forwarded-For support)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"

    def _categorize_route(self, path: str, method: str, client_id: str) -> str:
        """
        Categorize route for rate limiting.

        Enterprise Check 11.5: Per-Client Rate Limiting (HIGH - 10pts)
        API keys get higher rate limits than regular clients.
        """
        path_lower = path.lower()

        # API key requests get special higher limits
        if client_id.startswith('apikey:'):
            return 'api_key'

        # Public booking endpoints (unauthenticated, tighter limits)
        if '/public/book' in path_lower or '/public/available-slots' in path_lower or '/public/book-demo' in path_lower:
            return 'public_booking'

        if '/messages' in path_lower and method == 'POST':
            return 'chat_message'
        elif '/sessions' in path_lower and method == 'POST':
            return 'session_create'
        elif '/call-request' in path_lower or '/click-to-call' in path_lower:
            return 'call_initiate'
        elif '/analytics' in path_lower:
            return 'analytics'

        return 'default'

    async def _check_tenant_rate_limit(
        self,
        org_id: int,
        path: str,
    ) -> Dict[str, Any]:
        """Check per-tenant (organization-level) rate limit (PERF-004).

        This prevents noisy-neighbor problems where one org consumes all API capacity.
        Limits are determined by the org's subscription tier.

        Returns a dict with keys:
            allowed (bool): Whether the request is permitted.
            retry_after (int): Seconds until the window resets (meaningful when denied).
            limit (int): Maximum requests allowed in the window.
            remaining (int): Requests remaining in the current window.
            reset (int): Unix timestamp when the current window expires.
        """
        window = 60  # 1 minute sliding window
        limit = 0
        key = ""
        try:
            tier = await self._get_tenant_tier(org_id)
            tier_config = TENANT_TIER_LIMITS.get(tier, TENANT_TIER_LIMITS['default'])

            # Determine which bucket: AI endpoints get a separate, smaller quota
            is_ai = '/ai/' in path or '/chat/' in path or '/agents/' in path or '/messages' in path
            if is_ai:
                limit = tier_config['ai_per_min']
                key = f"tenant_rl:ai:{org_id}"
            else:
                limit = tier_config['requests_per_min']
                key = f"tenant_rl:api:{org_id}"

            current = self.redis.get(key)
            if current is None:
                self.redis.setex(key, window, 1)
                reset_at = int(time.time()) + window
                return {
                    'allowed': True,
                    'retry_after': 0,
                    'limit': limit,
                    'remaining': limit - 1,
                    'reset': reset_at,
                }

            current = int(current)
            ttl = self.redis.ttl(key)
            if ttl < 0:
                ttl = window
            reset_at = int(time.time()) + ttl

            if current >= limit:
                return {
                    'allowed': False,
                    'retry_after': max(ttl, 1),
                    'limit': limit,
                    'remaining': 0,
                    'reset': reset_at,
                }

            self.redis.incr(key)
            return {
                'allowed': True,
                'retry_after': 0,
                'limit': limit,
                'remaining': max(0, limit - current - 1),
                'reset': reset_at,
            }

        except redis.RedisError as e:
            logger.error(f"Redis error in tenant rate limiter: {e}")
            # Fall back to in-memory limiter instead of failing open
            self._memory_limiter.log_fallback()
            allowed, remaining = self._memory_limiter.check(
                key, limit, window
            )
            reset_at = int(time.time()) + window
            return {
                'allowed': allowed,
                'retry_after': 0 if allowed else window,
                'limit': limit,
                'remaining': remaining,
                'reset': reset_at,
            }

    async def _get_tenant_tier(self, org_id: int) -> str:
        """Look up an org's subscription tier from cache or DB.

        Caches the result in Redis for 5 minutes to avoid DB lookups on every request.
        """
        cache_key = f"tenant_tier:{org_id}"
        try:
            cached = self.redis.get(cache_key)
            if cached:
                return cached

            # Lazy import to avoid circular dependency
            from db import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                row = db.execute(
                    text("SELECT tier FROM organization_subscriptions WHERE organization_id = :org_id AND status = 'active' LIMIT 1"),
                    {"org_id": org_id}
                ).fetchone()
                tier = row[0] if row else 'default'
            finally:
                db.close()

            self.redis.setex(cache_key, 300, tier)  # Cache for 5 min
            return tier

        except Exception as e:
            logger.warning(f"Failed to get tenant tier for org {org_id}: {e}")
            return 'default'

    async def _check_rate_limit(
        self,
        client_id: str,
        category: str
    ) -> Dict[str, Any]:
        """Check if request is within rate limit.

        Returns a dict with keys:
            allowed (bool): Whether the request is permitted.
            retry_after (int): Seconds until the window resets (meaningful when denied).
            limit (int): Maximum requests allowed in the window.
            remaining (int): Requests remaining in the current window.
            reset (int): Unix timestamp when the current window expires.
        """
        limit_config = self.LIMITS.get(category, self.LIMITS['default'])
        max_requests = limit_config['requests']
        window = limit_config['window']
        key = f"ratelimit:{category}:{client_id}"

        try:
            current = self.redis.get(key)

            if current is None:
                # First request in window
                self.redis.setex(key, window, 1)
                reset_at = int(time.time()) + window
                return {
                    'allowed': True,
                    'retry_after': 0,
                    'limit': max_requests,
                    'remaining': max_requests - 1,
                    'reset': reset_at,
                }

            current = int(current)
            ttl = self.redis.ttl(key)
            # ttl can be -1 (no expiry) or -2 (key gone); treat as full window
            if ttl < 0:
                ttl = window
            reset_at = int(time.time()) + ttl

            if current >= max_requests:
                # Exceeded limit
                return {
                    'allowed': False,
                    'retry_after': max(ttl, 1),
                    'limit': max_requests,
                    'remaining': 0,
                    'reset': reset_at,
                }

            # Increment counter
            self.redis.incr(key)
            return {
                'allowed': True,
                'retry_after': 0,
                'limit': max_requests,
                'remaining': max(0, max_requests - current - 1),
                'reset': reset_at,
            }

        except redis.RedisError as e:
            logger.error(f"Redis error in rate limiter: {e}")
            # Fall back to in-memory limiter instead of failing open
            self._memory_limiter.log_fallback()
            fallback_key = f"ratelimit:{category}:{client_id}"
            allowed, remaining = self._memory_limiter.check(
                fallback_key,
                max_requests,
                window,
            )
            reset_at = int(time.time()) + window
            return {
                'allowed': allowed,
                'retry_after': 0 if allowed else window,
                'limit': max_requests,
                'remaining': remaining,
                'reset': reset_at,
            }

    async def _track_activity(self, client_id: str, request: Request):
        """Track activity for suspicious pattern detection"""
        now = datetime.now(timezone.utc).timestamp()

        try:
            # Track message timestamps
            msg_key = f"activity:messages:{client_id}"
            self.redis.zadd(msg_key, {str(now): now})
            self.redis.expire(msg_key, 300)  # Keep 5 minutes of history

            # Clean old entries
            self.redis.zremrangebyscore(msg_key, 0, now - 300)

            # Check for fast typing (>10 messages in 20 seconds)
            recent_count = self.redis.zcount(msg_key, now - 20, now)
            if recent_count >= self.SUSPICIOUS_PATTERNS['fast_typing']:
                await self._flag_suspicious(client_id, 'fast_typing')

        except redis.RedisError as e:
            logger.error(f"Redis error tracking activity: {e}")

    async def _flag_suspicious(self, client_id: str, reason: str):
        """Flag client as suspicious and apply stricter limits"""
        logger.warning(f"Suspicious activity detected: {client_id} - {reason}")

        try:
            # Increment violation counter
            violation_key = f"violations:{client_id}"
            violations = self.redis.incr(violation_key)
            self.redis.expire(violation_key, 3600)  # Reset after 1 hour

            # Block after 3 violations
            if violations >= 3:
                await self._block_client(client_id)
            else:
                # Apply 50% stricter limits
                for category in self.LIMITS:
                    key = f"ratelimit:{category}:{client_id}"
                    current = self.redis.get(key)
                    if current:
                        # Artificially increase count
                        new_count = int(int(current) * 1.5)
                        ttl = self.redis.ttl(key)
                        if ttl > 0:
                            self.redis.setex(key, ttl, new_count)

        except redis.RedisError as e:
            logger.error(f"Redis error flagging suspicious: {e}")

    async def _block_client(self, client_id: str):
        """Block a client temporarily"""
        logger.warning(f"Blocking client: {client_id}")

        try:
            block_key = f"blocked:{client_id}"
            self.redis.setex(block_key, 3600, "1")  # Block for 1 hour
            self.blocked_clients.add(client_id)

        except redis.RedisError as e:
            logger.error(f"Redis error blocking client: {e}")

    async def _is_blocked(self, client_id: str) -> bool:
        """Check if client is blocked"""
        if client_id in self.blocked_clients:
            return True

        try:
            block_key = f"blocked:{client_id}"
            return self.redis.exists(block_key) > 0

        except redis.RedisError:
            return False

    def get_rate_limit_status(self, client_id: str, category: str) -> Dict[str, Any]:
        """Get current rate limit status for a client"""
        limit_config = self.LIMITS.get(category, self.LIMITS['default'])
        key = f"ratelimit:{category}:{client_id}"

        try:
            current = int(self.redis.get(key) or 0)
            ttl = self.redis.ttl(key)

            return {
                'limit': limit_config['requests'],
                'remaining': max(0, limit_config['requests'] - current),
                'reset_in': max(0, ttl),
                'window': limit_config['window']
            }

        except redis.RedisError:
            return {
                'limit': limit_config['requests'],
                'remaining': limit_config['requests'],
                'reset_in': limit_config['window'],
                'window': limit_config['window']
            }


def create_rate_limiter(redis_url: str):
    """Factory function to create rate limiter with Redis connection"""
    redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
    return lambda app: AdaptiveRateLimiter(app, redis_client)


def setup_rate_limiting(app, redis_client):
    """DEPRECATED stub — retained only for chat_system_bootstrap.py import compat.

    This function is a no-op.  Active rate limiting is handled by
    APIRateLimitMiddleware registered in main.py.
    """
    logger.warning(
        "setup_rate_limiting() called but is deprecated and a no-op. "
        "Rate limiting is handled by APIRateLimitMiddleware."
    )
