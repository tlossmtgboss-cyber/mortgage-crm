"""
Adaptive Rate Limiting & DDoS Protection

This middleware provides:
- Tiered rate limiting by route category
- Per-user rate limiting for authenticated requests (JWT)
- Suspicious activity detection
- Automatic stricter limits for bad actors
- Client identification via user_id, visitor_id, IP, or fingerprint
"""

import logging
import hashlib
import os
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import redis

# JWT imports for user extraction
try:
    from jose import jwt, JWTError
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

logger = logging.getLogger(__name__)

# JWT configuration (same as main.py)
ALGORITHM = "HS256"


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

        # Rate limit tiers by route category (for anonymous/IP-based)
        self.LIMITS = {
            'chat_message': {'requests': 60, 'window': 60},      # 60 msg/min
            'session_create': {'requests': 10, 'window': 3600},  # 10 sessions/hour
            'call_initiate': {'requests': 3, 'window': 3600},    # 3 calls/hour
            'analytics': {'requests': 100, 'window': 60},        # 100 req/min
            'default': {'requests': 120, 'window': 60},          # 120 req/min default
        }

        # Higher limits for authenticated users (per-user rate limiting)
        self.AUTHENTICATED_LIMITS = {
            'chat_message': {'requests': 120, 'window': 60},     # 2x for auth users
            'session_create': {'requests': 30, 'window': 3600},  # 3x for auth users
            'call_initiate': {'requests': 10, 'window': 3600},   # 3x for auth users
            'analytics': {'requests': 300, 'window': 60},        # 3x for auth users
            'default': {'requests': 300, 'window': 60},          # 2.5x for auth users
            'api_heavy': {'requests': 1000, 'window': 60},       # For bulk operations
        }

        # Get SECRET_KEY for JWT decoding
        self._secret_key = os.getenv("SECRET_KEY", "dev-only-09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")

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

        # Identify client (now returns tuple with auth status)
        client_id, is_authenticated = self._get_client_identifier(request)

        # Store auth status on request for potential use by routes
        request.state.rate_limit_authenticated = is_authenticated
        request.state.rate_limit_client_id = client_id

        # Check if blocked
        if await self._is_blocked(client_id):
            return JSONResponse(
                status_code=403,
                content={"error": "Access denied", "reason": "Too many violations"}
            )

        # Get route category
        route_category = self._categorize_route(request.url.path, request.method)

        if route_category:
            # Check rate limit with appropriate tier based on auth status
            is_allowed, retry_after = await self._check_rate_limit(
                client_id,
                route_category,
                is_authenticated
            )

            if not is_allowed:
                logger.warning(f"Rate limit exceeded for {client_id} (auth={is_authenticated}) on {route_category}")
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "retry_after": retry_after,
                        "category": route_category,
                        "authenticated": is_authenticated
                    },
                    headers={"Retry-After": str(retry_after)}
                )

            # Check for suspicious patterns (async, non-blocking)
            if route_category == 'chat_message':
                await self._track_activity(client_id, request)

        response = await call_next(request)

        # Add rate limit info headers for transparency
        if route_category:
            limits = self.AUTHENTICATED_LIMITS if is_authenticated else self.LIMITS
            limit_config = limits.get(route_category, limits['default'])
            response.headers["X-RateLimit-Limit"] = str(limit_config['requests'])
            response.headers["X-RateLimit-Window"] = str(limit_config['window'])

        return response

    def _get_client_identifier(self, request: Request) -> Tuple[str, bool]:
        """
        Get unique client identifier with multiple fallback strategies.
        Returns tuple of (client_id, is_authenticated).

        Priority:
        1. Authenticated user (JWT token) - gets higher rate limits
        2. Visitor ID from header
        3. Session ID from path
        4. IP address (fallback)
        """
        # Priority 1: Authenticated user from JWT token
        user_email = self._extract_user_from_jwt(request)
        if user_email:
            # Hash email to create a stable identifier
            user_hash = hashlib.sha256(user_email.encode()).hexdigest()[:16]
            return f"user:{user_hash}", True

        # Priority 2: Visitor ID from header (set by frontend)
        visitor_id = request.headers.get("X-Visitor-ID")
        if visitor_id:
            return f"visitor:{visitor_id}", False

        # Priority 3: Session ID from path (for message endpoints)
        path_parts = request.url.path.split('/')
        if 'sessions' in path_parts:
            try:
                session_idx = path_parts.index('sessions') + 1
                if session_idx < len(path_parts):
                    session_id = path_parts[session_idx]
                    return f"session:{session_id}", False
            except (ValueError, IndexError):
                pass

        # Priority 4: IP address (with X-Forwarded-For support)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}", False

    def _extract_user_from_jwt(self, request: Request) -> Optional[str]:
        """
        Extract user email from JWT token if present and valid.
        This is a lightweight check - full validation happens in route handlers.
        """
        if not JWT_AVAILABLE:
            return None

        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        # Extract token from "Bearer <token>" format
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        token = parts[1]

        # Skip if it looks like an API key (usually starts with specific prefix)
        if token.startswith("pk_") or token.startswith("sk_") or len(token) < 50:
            return None

        try:
            # Decode JWT to extract user email
            # We only verify signature, don't check expiration here (for rate limiting purposes)
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[ALGORITHM],
                options={"verify_exp": False}  # Don't fail on expired tokens for rate limiting
            )
            return payload.get("sub")  # sub contains the email
        except JWTError:
            # Invalid token, fall back to other identifiers
            return None
        except Exception as e:
            logger.debug(f"Error extracting user from JWT: {e}")
            return None

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
        category: str,
        is_authenticated: bool = False
    ) -> Tuple[bool, int]:
        """
        Check if request is within rate limit.
        Uses higher limits for authenticated users.
        """
        # Select appropriate limit tier based on authentication status
        if is_authenticated:
            limits = self.AUTHENTICATED_LIMITS
        else:
            limits = self.LIMITS

        limit_config = limits.get(category, limits['default'])
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

    def get_rate_limit_status(self, client_id: str, category: str, is_authenticated: bool = False) -> Dict[str, Any]:
        """Get current rate limit status for a client"""
        limits = self.AUTHENTICATED_LIMITS if is_authenticated else self.LIMITS
        limit_config = limits.get(category, limits['default'])
        key = f"ratelimit:{category}:{client_id}"

        try:
            current = int(self.redis.get(key) or 0)
            ttl = self.redis.ttl(key)

            return {
                'limit': limit_config['requests'],
                'remaining': max(0, limit_config['requests'] - current),
                'reset_in': max(0, ttl),
                'window': limit_config['window'],
                'authenticated': is_authenticated,
                'client_type': client_id.split(':')[0] if ':' in client_id else 'unknown'
            }

        except redis.RedisError:
            return {
                'limit': limit_config['requests'],
                'remaining': limit_config['requests'],
                'reset_in': limit_config['window'],
                'window': limit_config['window'],
                'authenticated': is_authenticated,
                'client_type': client_id.split(':')[0] if ':' in client_id else 'unknown'
            }


def create_rate_limiter(redis_url: str):
    """
    Factory function to create rate limiter with Redis connection.

    If Redis is unavailable, creates a rate limiter that fails open
    (allows all requests) to prevent service disruption.
    """
    try:
        redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        # Test connection
        redis_client.ping()
        logger.info("Rate limiter connected to Redis successfully")
        return lambda app: AdaptiveRateLimiter(app, redis_client)
    except redis.RedisError as e:
        logger.warning(f"Redis unavailable for rate limiting: {e}. Rate limiting disabled.")
        # Return a no-op middleware that allows all requests
        return lambda app: NoOpRateLimiter(app)


class NoOpRateLimiter(BaseHTTPMiddleware):
    """
    No-op rate limiter used when Redis is unavailable.
    Allows all requests to pass through without rate limiting.
    """

    async def dispatch(self, request: Request, call_next):
        # Set default state values for compatibility
        request.state.rate_limit_authenticated = False
        request.state.rate_limit_client_id = "noop"
        return await call_next(request)
