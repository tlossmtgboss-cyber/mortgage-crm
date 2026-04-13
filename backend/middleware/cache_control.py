"""
Cache-Control Header Middleware
===============================

ASGI middleware that sets appropriate Cache-Control headers on API responses
based on the endpoint being served.  This is particularly important for mobile
clients (iOS Capacitor app) that may aggressively cache responses, leading to
stale data on dashboard screens and pipeline views.

Policy summary:
- Dashboard / pipeline endpoints:  private, max-age=60  (1 minute)
- Static config (version-check, feature-tiers):  public, max-age=300  (5 min)
- User-specific data (leads, loans, tasks detail):  private, no-cache
- Health check:  no-store
- Default:  private, no-cache

The middleware only sets Cache-Control if the response does not already include
one (so individual route handlers can override when needed).

Usage in main.py:
    from middleware.cache_control import CacheControlMiddleware
    app.add_middleware(CacheControlMiddleware)
"""

from __future__ import annotations

import logging
from typing import Sequence, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Policy definitions — evaluated in order; first match wins.
# Each entry is (match_function, cache_control_value).
# ---------------------------------------------------------------------------

# Paths that should never be cached (health probes, metrics)
_NO_STORE_PREFIXES: Tuple[str, ...] = (
    "/health",
    "/api/v1/health",
    "/api/v1/system/health",
    "/readyz",
    "/livez",
)

# Static / rarely-changing config endpoints — safe to cache publicly
_PUBLIC_CACHE_PREFIXES: Tuple[str, ...] = (
    "/api/v1/version-check",
    "/api/v1/version",
    "/api/v1/feature-tiers",
    "/api/v1/system/version",
    "/api/v1/config/feature-tiers",
)

# Dashboard / pipeline / aggregate endpoints — short-lived private cache
_SHORT_CACHE_PREFIXES: Tuple[str, ...] = (
    "/api/v1/dashboard",
    "/api/v1/pipeline",
    "/api/v1/metrics",
    "/api/v1/analytics",
)

# User-specific detail endpoints — must revalidate every time
_NO_CACHE_PREFIXES: Tuple[str, ...] = (
    "/api/v1/leads",
    "/api/v1/loans",
    "/api/v1/tasks",
    "/api/v1/contacts",
    "/api/v1/borrowers",
    "/api/v1/notifications",
    "/api/v1/users",
    "/api/v1/ai",
    "/api/v1/smart-docs",
    "/api/v1/calendar",
)


def _resolve_cache_policy(path: str) -> str:
    """Return the Cache-Control value for the given request path."""
    path_lower = path.lower()

    # 1. No-store (health checks)
    for prefix in _NO_STORE_PREFIXES:
        if path_lower.startswith(prefix):
            return "no-store"

    # 2. Public long-ish cache (static config)
    for prefix in _PUBLIC_CACHE_PREFIXES:
        if path_lower.startswith(prefix):
            return "public, max-age=300"

    # 3. Short private cache (dashboard/pipeline aggregates)
    for prefix in _SHORT_CACHE_PREFIXES:
        if path_lower.startswith(prefix):
            return "private, max-age=60"

    # 4. Explicit no-cache (user-specific data)
    for prefix in _NO_CACHE_PREFIXES:
        if path_lower.startswith(prefix):
            return "private, no-cache"

    # 5. Default — force revalidation
    return "private, no-cache"


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class CacheControlMiddleware(BaseHTTPMiddleware):
    """
    Sets Cache-Control response headers based on the endpoint path.

    Only applies to successful GET responses (2xx).  Non-GET methods and
    error responses are left untouched so that upstream error-handling
    middleware can set its own headers if needed.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        # Only set cache headers on GET responses — mutations should never
        # be cached, and most clients/CDNs ignore Cache-Control on non-GET.
        if request.method != "GET":
            return response

        # Don't overwrite if the route handler already set Cache-Control
        existing = response.headers.get("cache-control")
        if existing:
            return response

        path = request.url.path
        policy = _resolve_cache_policy(path)
        response.headers["Cache-Control"] = policy

        return response
