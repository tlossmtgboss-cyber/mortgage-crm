"""
API Versioning Middleware

Adds versioning headers to all API responses:
- API-Version: The version of the API serving the response
- Deprecation: (RFC 8594) Date when endpoint was deprecated
- Sunset: (RFC 8594) Date when endpoint will be removed

This middleware works in conjunction with:
- api/versioning.py: VersionedAPIRouter for new versioned routes
- Existing routes: Adds headers to legacy routes for forward compatibility

Usage:
    from middleware.api_versioning import APIVersioningMiddleware

    app.add_middleware(
        APIVersioningMiddleware,
        current_version="1.0",
        deprecated_endpoints={
            "/old-endpoint": {
                "deprecation_date": "2024-06-01",
                "sunset_date": "2024-12-01",
                "replacement": "/api/v1/new-endpoint"
            }
        }
    )
"""

import logging
from datetime import date, datetime
from typing import Dict, Any, Optional, Set
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)


# Default API version for unversioned endpoints
CURRENT_API_VERSION = "1.0"

# V1 blanket deprecation — all /api/v1/ endpoints are deprecated
# in favor of /api/v2/ equivalents.
V1_DEPRECATION_DATE = "2026-05-01"
V1_SUNSET_DATE = "2027-01-01T00:00:00Z"

# V1 -> V2 successor mappings for Link header
V1_SUCCESSOR_MAP: Dict[str, str] = {
    "/api/v1/leads": "/api/v2/leads",
    "/api/v1/loans": "/api/v2/loans",
    "/api/v1/scheduler": "/api/v2/scheduler",
}

# Deprecated endpoints configuration
# Format: path -> {deprecation_date, sunset_date, replacement}
DEPRECATED_ENDPOINTS: Dict[str, Dict[str, Any]] = {
    # Example:
    # "/api/old-endpoint": {
    #     "deprecation_date": date(2024, 6, 1),
    #     "sunset_date": date(2024, 12, 1),
    #     "replacement": "/api/v1/new-endpoint",
    # },
}

# Sunset endpoints - return 410 Gone
SUNSET_ENDPOINTS: Set[str] = set()


class APIVersioningMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds API versioning headers to all responses.

    Headers added:
    - API-Version: Current API version (e.g., "1.0")
    - Deprecation: RFC 8594 date if endpoint is deprecated
    - Sunset: RFC 8594 date if endpoint has a sunset date
    - Link: Points to replacement endpoint if available

    Also handles sunset endpoints by returning 410 Gone.
    """

    def __init__(
        self,
        app,
        current_version: str = CURRENT_API_VERSION,
        deprecated_endpoints: Dict[str, Dict[str, Any]] = None,
        sunset_endpoints: Set[str] = None,
    ):
        super().__init__(app)
        self.current_version = current_version
        self.deprecated_endpoints = deprecated_endpoints or DEPRECATED_ENDPOINTS
        self.sunset_endpoints = sunset_endpoints or SUNSET_ENDPOINTS

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Check for sunset endpoints first
        if self._is_sunset_endpoint(path):
            return self._create_gone_response(path)

        # Process the request
        response = await call_next(request)

        # Add versioning headers
        self._add_version_headers(response, path)

        # Add deprecation headers if applicable
        self._add_deprecation_headers(response, path)

        return response

    def _is_sunset_endpoint(self, path: str) -> bool:
        """Check if the endpoint is sunset (410 Gone)."""
        # Check exact match
        if path in self.sunset_endpoints:
            return True

        # Check prefix match for versioned paths
        for sunset_path in self.sunset_endpoints:
            if path.startswith(sunset_path):
                return True

        return False

    def _create_gone_response(self, path: str) -> JSONResponse:
        """Create a 410 Gone response for sunset endpoints."""
        deprecation_info = self.deprecated_endpoints.get(path, {})
        replacement = deprecation_info.get("replacement", "/api/v1")

        return JSONResponse(
            status_code=410,
            content={
                "detail": "This API endpoint has been sunset and is no longer available.",
                "code": "ENDPOINT_SUNSET",
                "replacement": replacement,
                "documentation": "/docs",
            },
            headers={
                "API-Version": self.current_version,
                "Content-Type": "application/json",
            },
        )

    def _add_version_headers(self, response: Response, path: str) -> None:
        """Add API-Version header to response."""
        # Don't override if already set by VersionedAPIRouter
        if "API-Version" not in response.headers:
            # Detect version from path
            if "/api/v2" in path:
                response.headers["API-Version"] = "2.0"
            elif "/api/v1" in path:
                response.headers["API-Version"] = "1.0"
            else:
                # Default version for non-versioned endpoints
                response.headers["API-Version"] = self.current_version

    def _add_deprecation_headers(self, response: Response, path: str) -> None:
        """Add Deprecation and Sunset headers for deprecated endpoints.

        All /api/v1/ endpoints automatically receive deprecation headers
        pointing to their /api/v2/ successors (if mapped).  Individually
        registered deprecations take priority.
        """
        deprecation_info = self._get_deprecation_info(path)

        # Blanket V1 deprecation: any /api/v1/ path gets headers
        if not deprecation_info and "/api/v1" in path:
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = V1_SUNSET_DATE

            # Find the best successor-version link
            successor = None
            for v1_prefix, v2_replacement in V1_SUCCESSOR_MAP.items():
                if path.startswith(v1_prefix):
                    successor = v2_replacement
                    break
            if successor:
                response.headers["Link"] = f'<{successor}>; rel="successor-version"'
            return

        if not deprecation_info:
            return

        # RFC 8594 Deprecation header
        deprecation_date = deprecation_info.get("deprecation_date")
        if deprecation_date:
            if isinstance(deprecation_date, str):
                response.headers["Deprecation"] = deprecation_date
            elif isinstance(deprecation_date, (date, datetime)):
                # RFC 7231 date format for Deprecation header
                response.headers["Deprecation"] = deprecation_date.strftime("%a, %d %b %Y 00:00:00 GMT")

        # RFC 8594 Sunset header
        sunset_date = deprecation_info.get("sunset_date")
        if sunset_date:
            if isinstance(sunset_date, str):
                response.headers["Sunset"] = sunset_date
            elif isinstance(sunset_date, (date, datetime)):
                # RFC 7231 date format for Sunset header
                response.headers["Sunset"] = sunset_date.strftime("%a, %d %b %Y 00:00:00 GMT")

        # Link header pointing to replacement
        replacement = deprecation_info.get("replacement")
        if replacement:
            response.headers["Link"] = f'<{replacement}>; rel="successor-version"'

        # Log deprecation warning (once per request path)
        logger.debug(f"Deprecated endpoint accessed: {path}")

    def _get_deprecation_info(self, path: str) -> Optional[Dict[str, Any]]:
        """Get deprecation info for a path."""
        # Exact match
        if path in self.deprecated_endpoints:
            return self.deprecated_endpoints[path]

        # Prefix match (for endpoints with path parameters)
        for deprecated_path, info in self.deprecated_endpoints.items():
            if path.startswith(deprecated_path.rstrip("/")):
                return info

        return None


def deprecate_endpoint(
    path: str,
    deprecation_date: date = None,
    sunset_date: date = None,
    replacement: str = None,
) -> None:
    """
    Mark an endpoint as deprecated.

    Args:
        path: The endpoint path to deprecate
        deprecation_date: When deprecation starts (defaults to today)
        sunset_date: When endpoint will be removed (defaults to 6 months)
        replacement: URL of the replacement endpoint
    """
    if deprecation_date is None:
        deprecation_date = date.today()

    if sunset_date is None:
        # Default to 6 months from deprecation
        month = deprecation_date.month + 6
        year = deprecation_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(deprecation_date.day, 28)  # Safe day for all months
        sunset_date = date(year, month, day)

    DEPRECATED_ENDPOINTS[path] = {
        "deprecation_date": deprecation_date,
        "sunset_date": sunset_date,
        "replacement": replacement,
    }

    logger.info(
        f"Endpoint {path} marked as deprecated. "
        f"Sunset: {sunset_date.isoformat()}"
    )


def sunset_endpoint(path: str) -> None:
    """
    Mark an endpoint as sunset (will return 410 Gone).

    Args:
        path: The endpoint path to sunset
    """
    SUNSET_ENDPOINTS.add(path)
    logger.info(f"Endpoint {path} has been sunset (410 Gone)")
