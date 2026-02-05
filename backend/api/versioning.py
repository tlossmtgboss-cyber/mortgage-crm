"""
API Versioning Infrastructure

Provides versioned API routing with:
- API-Version response header on all responses
- Sunset header for deprecated versions
- 410 Gone for sunset (end-of-life) versions
- Version negotiation via Accept header or URL prefix

Version Strategy:
- Current: v1 (stable)
- Deprecated: None
- Sunset: None

Versioning Rules:
1. New versions are introduced for breaking changes
2. Deprecated versions receive 6-month sunset notice
3. Sunset versions return 410 Gone
4. Non-breaking changes are added to current version

Usage:
    from api.versioning import VersionedAPIRouter, APIVersion

    # Create versioned router
    router = VersionedAPIRouter(version=APIVersion.V1)

    @router.get("/users")
    async def get_users():
        return {"users": []}

    # In main app
    app.include_router(router)
"""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, Callable, List
import logging

from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class APIVersion(str, Enum):
    """Available API versions."""
    V1 = "v1"
    # V2 = "v2"  # Add when needed


# Version metadata
VERSION_INFO: Dict[APIVersion, Dict[str, Any]] = {
    APIVersion.V1: {
        "status": "stable",
        "release_date": date(2024, 1, 1),
        "sunset_date": None,  # No sunset planned
        "deprecated_date": None,
    },
    # APIVersion.V2: {
    #     "status": "stable",
    #     "release_date": date(2025, 1, 1),
    #     "sunset_date": None,
    #     "deprecated_date": None,
    # },
}

# Current stable version
CURRENT_VERSION = APIVersion.V1

# Sunset versions (return 410 Gone)
SUNSET_VERSIONS: List[str] = []


class VersionedRoute(APIRoute):
    """
    Custom route class that adds version headers to responses.
    """

    def __init__(self, *args, api_version: APIVersion = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_version = api_version or CURRENT_VERSION

    def get_route_handler(self) -> Callable:
        original_handler = super().get_route_handler()

        async def versioned_handler(request: Request) -> Response:
            response = await original_handler(request)

            # Add version header
            response.headers["API-Version"] = self.api_version.value

            # Add deprecation/sunset headers if applicable
            version_meta = VERSION_INFO.get(self.api_version, {})

            if version_meta.get("deprecated_date"):
                response.headers["Deprecation"] = version_meta["deprecated_date"].isoformat()

            if version_meta.get("sunset_date"):
                sunset = version_meta["sunset_date"]
                response.headers["Sunset"] = sunset.strftime("%a, %d %b %Y 00:00:00 GMT")

            return response

        return versioned_handler


class VersionedAPIRouter(APIRouter):
    """
    APIRouter with built-in versioning support.

    Automatically adds:
    - Version prefix to all routes
    - API-Version response header
    - Deprecation and Sunset headers for deprecated versions

    Usage:
        router = VersionedAPIRouter(version=APIVersion.V1)

        @router.get("/users")
        async def get_users():
            return {"users": []}
    """

    def __init__(
        self,
        version: APIVersion = CURRENT_VERSION,
        prefix: str = "",
        **kwargs,
    ):
        # Add version to prefix
        version_prefix = f"/api/{version.value}"
        full_prefix = f"{version_prefix}{prefix}" if prefix else version_prefix

        # Use versioned route class
        super().__init__(
            prefix=full_prefix,
            route_class=VersionedRoute,
            **kwargs,
        )
        self.api_version = version

        # Store version for route class
        self._api_version = version

    def add_api_route(self, path: str, endpoint: Callable, **kwargs) -> None:
        """Override to pass version to route."""
        # Inject api_version into route_class_kwargs
        route_class_kwargs = kwargs.pop("route_class_kwargs", {})
        route_class_kwargs["api_version"] = self.api_version
        kwargs["route_class_kwargs"] = route_class_kwargs
        super().add_api_route(path, endpoint, **kwargs)


class APIVersionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle API versioning:
    - Rejects requests to sunset versions with 410 Gone
    - Adds version headers to all responses
    - Logs deprecation warnings
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Check for sunset versions
        for sunset_version in SUNSET_VERSIONS:
            if path.startswith(f"/api/{sunset_version}"):
                return JSONResponse(
                    status_code=410,
                    content={
                        "detail": f"API version '{sunset_version}' has been sunset and is no longer available.",
                        "current_version": CURRENT_VERSION.value,
                        "documentation": "/docs",
                    },
                    headers={
                        "API-Version": sunset_version,
                        "Content-Type": "application/json",
                    },
                )

        # Process request
        response = await call_next(request)

        # Add current version header if not already set
        if "API-Version" not in response.headers:
            # Detect version from path
            for version in APIVersion:
                if path.startswith(f"/api/{version.value}"):
                    response.headers["API-Version"] = version.value
                    break
            else:
                # Default to current version for non-versioned endpoints
                response.headers["API-Version"] = CURRENT_VERSION.value

        return response


def get_version_info() -> Dict[str, Any]:
    """
    Get information about all API versions.

    Returns dict with version status, dates, and documentation.
    """
    versions = {}
    for version, meta in VERSION_INFO.items():
        versions[version.value] = {
            "status": meta["status"],
            "release_date": meta["release_date"].isoformat() if meta["release_date"] else None,
            "deprecated_date": meta["deprecated_date"].isoformat() if meta.get("deprecated_date") else None,
            "sunset_date": meta["sunset_date"].isoformat() if meta.get("sunset_date") else None,
            "is_current": version == CURRENT_VERSION,
        }

    return {
        "current_version": CURRENT_VERSION.value,
        "versions": versions,
        "sunset_versions": SUNSET_VERSIONS,
    }


def deprecate_version(
    version: APIVersion,
    deprecated_date: date = None,
    sunset_date: date = None,
) -> None:
    """
    Mark a version as deprecated.

    Args:
        version: The version to deprecate
        deprecated_date: When deprecation starts (defaults to today)
        sunset_date: When version will be sunset (defaults to 6 months from now)
    """
    if deprecated_date is None:
        deprecated_date = date.today()

    if sunset_date is None:
        # Default to 6 months from deprecation
        sunset_date = date(
            deprecated_date.year + (deprecated_date.month + 6 - 1) // 12,
            (deprecated_date.month + 6 - 1) % 12 + 1,
            deprecated_date.day,
        )

    if version in VERSION_INFO:
        VERSION_INFO[version]["status"] = "deprecated"
        VERSION_INFO[version]["deprecated_date"] = deprecated_date
        VERSION_INFO[version]["sunset_date"] = sunset_date

        logger.warning(
            f"API version {version.value} deprecated. "
            f"Sunset date: {sunset_date.isoformat()}"
        )


def sunset_version(version: APIVersion) -> None:
    """
    Mark a version as sunset (end-of-life).

    Requests to this version will receive 410 Gone.
    """
    if version in VERSION_INFO:
        VERSION_INFO[version]["status"] = "sunset"

    if version.value not in SUNSET_VERSIONS:
        SUNSET_VERSIONS.append(version.value)

    logger.info(f"API version {version.value} has been sunset")


# Version endpoint router
version_router = APIRouter(prefix="/api", tags=["API Version"])


@version_router.get("/version")
async def get_api_version():
    """
    Get API version information.

    Returns current version, all available versions, and their status.
    """
    return get_version_info()


@version_router.get("/versions")
async def list_api_versions():
    """
    List all API versions with their status.

    Status values:
    - stable: Active and supported
    - deprecated: Still available but will be sunset
    - sunset: No longer available (410 Gone)
    """
    return get_version_info()
