"""
08-infrastructure/rate_limit.py

slowapi Limiter wired to Redis (works across replicas). Different limits for
different route classes: tight on auth, looser on read endpoints, special
handling for AI endpoints (expensive per call).

Drop-in: backend/app/core/rate_limit.py
"""

from __future__ import annotations

import os

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse


def _client_key(request: Request) -> str:
    """
    Rate-limit key strategy:
      - Authenticated users: keyed by user_id (won't punish NAT'd offices)
      - Anonymous: keyed by IP (from X-Forwarded-For if behind proxy)
    """
    user = getattr(request.state, "user", None)
    if user and getattr(user, "id", None):
        return f"user:{user.id}"

    xff = request.headers.get("x-forwarded-for")
    if xff:
        return f"ip:{xff.split(',')[0].strip()}"

    return f"ip:{get_remote_address(request)}"


REDIS_URL = os.environ.get("REDIS_URL", "memory://")

# Global limiter — import this from routes
limiter = Limiter(
    key_func=_client_key,
    storage_uri=REDIS_URL,
    strategy="fixed-window-elastic-expiry",
    default_limits=["1000/hour", "100/minute"],
    headers_enabled=True,  # X-RateLimit-* headers in responses
)


# --- Preset limits for common route classes ---------------------------------
# Used as @limiter.limit(AUTH_LOGIN) on routes.

AUTH_LOGIN = "5/minute;20/hour"
AUTH_REFRESH = "30/minute"
AUTH_PASSWORD_RESET = "3/hour"
AUTH_MFA = "10/minute"

# AI endpoints are expensive per call (LLM cost + latency)
AI_AGENT = "30/minute;500/hour"
AI_VOICE_CALL = "10/minute;100/hour"
AI_GUIDELINE_QUERY = "60/minute"

# Integration sync endpoints
INTEGRATION_SYNC = "5/minute"

# Bulk export / reporting
EXPORT_HEAVY = "10/hour"

# Webhook ingestion — high volume, keyed by source
WEBHOOK_INGEST = "300/minute"


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Consistent 429 response body across the API."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "rate_limit_exceeded",
            "retry_after_seconds": int(exc.detail.split()[-1]) if exc.detail else 60,
            "limit": str(exc.detail),
        },
        headers={"Retry-After": "60"},
    )
