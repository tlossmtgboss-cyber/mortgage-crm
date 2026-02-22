"""
Rate Limit Middleware — Request rate limiting and abuse detection.
SOC 2 Criteria: CC5 (Control Activities), A1 (Availability)

Implements token bucket rate limiting per IP and per user to prevent
abuse and ensure service availability.
"""
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Dict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..config import SOC2Config

logger = logging.getLogger("soc2.middleware.rate_limit")


@dataclass
class TokenBucket:
    """Simple token bucket for rate limiting."""
    tokens: float
    max_tokens: int
    refill_rate: float  # tokens per second
    last_refill: float = field(default_factory=time.time)

    def consume(self) -> bool:
        """Try to consume a token. Returns True if allowed."""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware with per-IP and per-user limits.
    
    Add to FastAPI:
        app.add_middleware(RateLimitMiddleware)
    
    Rate limit headers returned:
        X-RateLimit-Limit: Maximum requests per window
        X-RateLimit-Remaining: Remaining requests
        X-RateLimit-Reset: Seconds until bucket refills
    """

    def __init__(self, app, config: SOC2Config = None):
        super().__init__(app)
        self.config = config or SOC2Config.from_env()
        self._buckets: Dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(
                tokens=self.config.rate_limit_burst,
                max_tokens=self.config.rate_limit_burst,
                refill_rate=self.config.rate_limit_requests_per_minute / 60.0,
            )
        )
        self._login_buckets: Dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(
                tokens=self.config.rate_limit_login_per_minute,
                max_tokens=self.config.rate_limit_login_per_minute,
                refill_rate=self.config.rate_limit_login_per_minute / 60.0,
            )
        )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        user_id = getattr(request.state, "user_id", None)

        # Determine the rate limit key
        rate_key = str(user_id) if user_id else client_ip

        # Use stricter limits for auth endpoints
        is_auth_endpoint = any(
            p in request.url.path for p in ["/login", "/auth", "/token", "/register"]
        )

        if is_auth_endpoint:
            bucket = self._login_buckets[client_ip]
        else:
            bucket = self._buckets[rate_key]

        if not bucket.consume():
            logger.warning(
                "rate_limit_exceeded",
                extra={
                    "ip": client_ip,
                    "user_id": str(user_id) if user_id else None,
                    "path": request.url.path,
                    "is_auth": is_auth_endpoint,
                }
            )

            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after_seconds": int(1 / bucket.refill_rate),
                },
                headers={
                    "Retry-After": str(int(1 / bucket.refill_rate)),
                    "X-RateLimit-Limit": str(bucket.max_tokens),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(bucket.max_tokens)
        response.headers["X-RateLimit-Remaining"] = str(int(bucket.tokens))

        return response
