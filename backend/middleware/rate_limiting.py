"""
Adaptive Rate Limiting & DDoS Protection

This middleware provides:
- Tiered rate limiting by route category
- Suspicious activity detection
- Automatic stricter limits for bad actors
- Client identification via visitor_id, IP, or fingerprint
"""

import logging
import hashlib
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import redis

logger = logging.getLogger(__name__)


class AdaptiveRateLimiter(BaseHTTPMiddleware):
    """
    Adaptive rate limiting that distinguishes between:
    - Normal users
    - Suspicious activity
    - Bot traffic
    """

    def __init__(self, app, redis_client: redis.Redis):
        super().__init__(app)
        self.redis = redis_client

        # Rate limit tiers by route category
        self.LIMITS = {
            'chat_message': {'requests': 60, 'window': 60},      # 60 msg/min
            'session_create': {'requests': 10, 'window': 3600},  # 10 sessions/hour
            'call_initiate': {'requests': 3, 'window': 3600},    # 3 calls/hour
            'analytics': {'requests': 100, 'window': 60},        # 100 req/min
            'default': {'requests': 120, 'window': 60},          # 120 req/min default
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

        # Get route category
        route_category = self._categorize_route(request.url.path, request.method)

        if route_category:
            # Check rate limit
            is_allowed, retry_after = await self._check_rate_limit(
                client_id,
                route_category
            )

            if not is_allowed:
                logger.warning(f"Rate limit exceeded for {client_id} on {route_category}")
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "retry_after": retry_after,
                        "category": route_category
                    },
                    headers={"Retry-After": str(retry_after)}
                )

            # Check for suspicious patterns (async, non-blocking)
            if route_category == 'chat_message':
                await self._track_activity(client_id, request)

        response = await call_next(request)
        return response

    def _get_client_identifier(self, request: Request) -> str:
        """Get unique client identifier with multiple fallback strategies"""
        # Priority 1: Visitor ID from header (set by frontend)
        visitor_id = request.headers.get("X-Visitor-ID")
        if visitor_id:
            return f"visitor:{visitor_id}"

        # Priority 2: Session ID from path (for message endpoints)
        path_parts = request.url.path.split('/')
        if 'sessions' in path_parts:
            try:
                session_idx = path_parts.index('sessions') + 1
                if session_idx < len(path_parts):
                    session_id = path_parts[session_idx]
                    return f"session:{session_id}"
            except (ValueError, IndexError):
                pass

        # Priority 3: IP address (with X-Forwarded-For support)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"

    def _categorize_route(self, path: str, method: str) -> str:
        """Categorize route for rate limiting"""
        path_lower = path.lower()

        if '/messages' in path_lower and method == 'POST':
            return 'chat_message'
        elif '/sessions' in path_lower and method == 'POST':
            return 'session_create'
        elif '/call-request' in path_lower or '/click-to-call' in path_lower:
            return 'call_initiate'
        elif '/analytics' in path_lower:
            return 'analytics'

        return 'default'

    async def _check_rate_limit(
        self,
        client_id: str,
        category: str
    ) -> Tuple[bool, int]:
        """Check if request is within rate limit"""
        limit_config = self.LIMITS.get(category, self.LIMITS['default'])
        key = f"ratelimit:{category}:{client_id}"

        try:
            current = self.redis.get(key)

            if current is None:
                # First request in window
                self.redis.setex(key, limit_config['window'], 1)
                return True, 0

            current = int(current)

            if current >= limit_config['requests']:
                # Exceeded limit
                ttl = self.redis.ttl(key)
                return False, max(ttl, 1)

            # Increment counter
            self.redis.incr(key)
            return True, 0

        except redis.RedisError as e:
            logger.error(f"Redis error in rate limiter: {e}")
            # Fail open on Redis errors (allow request)
            return True, 0

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
