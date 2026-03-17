"""
API Deprecation Tracking Service - Perennia AI

Provides:
- ``@deprecated_endpoint(sunset_date, replacement)`` decorator that adds
  Sunset and Deprecation headers (RFC 8594) and logs usage.
- In-memory deprecation registry with endpoint-level hit counters.
- ``GET /api/v1/deprecation-notices`` route to list all deprecated endpoints.

Usage:
    from services.api_deprecation import deprecated_endpoint, deprecation_router

    @router.get("/old-thing")
    @deprecated_endpoint(
        sunset_date="2026-09-01",
        replacement="/api/v2/new-thing",
    )
    async def old_thing():
        ...

    # Mount the notices endpoint:
    app.include_router(deprecation_router)
"""

from __future__ import annotations

import functools
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Response

logger = logging.getLogger(__name__)


# =============================================================================
# DEPRECATION REGISTRY
# =============================================================================

@dataclass
class DeprecationNotice:
    """Metadata for a single deprecated endpoint."""
    path: str
    method: str
    deprecation_date: str  # ISO 8601 date string
    sunset_date: str       # ISO 8601 date string
    replacement: Optional[str] = None
    message: Optional[str] = None
    hit_count: int = 0


# Global registry: key = "METHOD:path"
_registry: Dict[str, DeprecationNotice] = {}

# Counter: "METHOD:path" -> count
_hit_counts: Dict[str, int] = defaultdict(int)


def get_deprecation_notices() -> List[Dict[str, Any]]:
    """Return all registered deprecation notices as dicts."""
    notices = []
    for key, notice in sorted(_registry.items()):
        notices.append({
            "path": notice.path,
            "method": notice.method,
            "deprecation_date": notice.deprecation_date,
            "sunset_date": notice.sunset_date,
            "replacement": notice.replacement,
            "message": notice.message,
            "hit_count": notice.hit_count + _hit_counts.get(key, 0),
        })
    return notices


def register_deprecation(
    path: str,
    method: str,
    deprecation_date: str,
    sunset_date: str,
    replacement: Optional[str] = None,
    message: Optional[str] = None,
) -> None:
    """Programmatically register a deprecation notice."""
    key = f"{method.upper()}:{path}"
    _registry[key] = DeprecationNotice(
        path=path,
        method=method.upper(),
        deprecation_date=deprecation_date,
        sunset_date=sunset_date,
        replacement=replacement,
        message=message,
    )


def clear_deprecation_registry() -> None:
    """Clear all deprecation notices (for testing)."""
    _registry.clear()
    _hit_counts.clear()


# =============================================================================
# DECORATOR
# =============================================================================

def deprecated_endpoint(
    sunset_date: str,
    replacement: Optional[str] = None,
    deprecation_date: Optional[str] = None,
    message: Optional[str] = None,
) -> Callable:
    """Decorator that marks a FastAPI endpoint as deprecated.

    Adds RFC 8594 ``Sunset`` and ``Deprecation`` headers to every
    response and logs a warning each time the endpoint is called.

    Args:
        sunset_date: ISO 8601 date when the endpoint will be removed
            (e.g. ``"2026-09-01"``).
        replacement: URL of the replacement endpoint (optional).
        deprecation_date: ISO 8601 date when deprecation started
            (defaults to today).
        message: Custom deprecation message for logs.
    """
    dep_date = deprecation_date or date.today().isoformat()

    def decorator(func: Callable) -> Callable:
        # Infer path and method from the route if we can; otherwise
        # fall back to function name.  These will be overridden by
        # register_deprecation if called manually.
        func_name = func.__name__

        @functools.wraps(func)
        async def wrapper(*args, response: Response = None, **kwargs):
            # Find the Response object in kwargs or positional args
            resp = response
            if resp is None:
                for arg in args:
                    if isinstance(arg, Response):
                        resp = arg
                        break

            result = await func(*args, **kwargs)

            # Add headers to the response if available
            if resp is not None:
                _set_deprecation_headers(resp, dep_date, sunset_date, replacement)

            # Track usage
            log_key = f"deprecated:{func_name}"
            _hit_counts[log_key] += 1
            logger.warning(
                "Deprecated endpoint called: %s (sunset=%s, replacement=%s, hits=%d)",
                func_name,
                sunset_date,
                replacement,
                _hit_counts[log_key],
            )

            return result

        # Store deprecation metadata on the function for introspection
        wrapper._deprecation_info = {
            "sunset_date": sunset_date,
            "deprecation_date": dep_date,
            "replacement": replacement,
            "message": message,
        }

        return wrapper
    return decorator


def _set_deprecation_headers(
    response: Response,
    deprecation_date: str,
    sunset_date: str,
    replacement: Optional[str],
) -> None:
    """Set RFC 8594 deprecation headers on a response."""
    try:
        dep_dt = datetime.fromisoformat(deprecation_date)
        response.headers["Deprecation"] = dep_dt.strftime(
            "%a, %d %b %Y 00:00:00 GMT"
        )
    except (ValueError, TypeError):
        response.headers["Deprecation"] = deprecation_date

    try:
        sun_dt = datetime.fromisoformat(sunset_date)
        response.headers["Sunset"] = sun_dt.strftime(
            "%a, %d %b %Y 00:00:00 GMT"
        )
    except (ValueError, TypeError):
        response.headers["Sunset"] = sunset_date

    if replacement:
        response.headers["Link"] = f'<{replacement}>; rel="successor-version"'


# =============================================================================
# ROUTER: GET /api/v1/deprecation-notices
# =============================================================================

deprecation_router = APIRouter(tags=["API Deprecation"])


@deprecation_router.get(
    "/api/v1/deprecation-notices",
    summary="List deprecated endpoints and sunset dates",
    response_description="List of all deprecated endpoints with their sunset dates and replacement URLs",
)
async def list_deprecation_notices():
    """Return all registered deprecation notices.

    This endpoint is useful for API consumers to discover which
    endpoints are deprecated and when they will be removed.

    Version Negotiation
    -------------------
    This endpoint is always served under ``/api/v1`` because it
    describes the deprecation state of v1 endpoints.
    """
    notices = get_deprecation_notices()
    return {
        "deprecation_notices": notices,
        "total": len(notices),
        "api_version": "1.0",
    }
