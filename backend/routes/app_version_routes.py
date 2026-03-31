"""
App Version Check Routes

Provides version checking and forced update support for the Perennia AI
mobile app. No authentication required — this must work before login so
that outdated clients can be blocked at launch.

Endpoints:
  GET /api/v1/app/version-check  — compare client version against minimum/recommended
"""
import os
import logging
from typing import Optional, Tuple

from fastapi import Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# =============================================================================
# Version configuration
# =============================================================================
# Override any value via environment variables.  Defaults match the current
# production release (1.0.2 / build 21).

APP_VERSION_CONFIG = {
    "ios": {
        "minimum": os.getenv("IOS_MIN_VERSION", "1.0.0"),
        "recommended": os.getenv("IOS_RECOMMENDED_VERSION", "1.0.2"),
        "current": os.getenv("IOS_CURRENT_VERSION", "1.0.2"),
        "store_url": os.getenv(
            "IOS_STORE_URL",
            "https://apps.apple.com/app/perenniaai-crm-platform/id6743197498",
        ),
        "changelog": os.getenv("IOS_CHANGELOG", "Bug fixes and performance improvements."),
    },
    "android": {
        "minimum": os.getenv("ANDROID_MIN_VERSION", "1.0.0"),
        "recommended": os.getenv("ANDROID_RECOMMENDED_VERSION", "1.0.0"),
        "current": os.getenv("ANDROID_CURRENT_VERSION", "1.0.0"),
        "store_url": os.getenv(
            "ANDROID_STORE_URL",
            "https://play.google.com/store/apps/details?id=com.perenniaai.crm",
        ),
        "changelog": os.getenv("ANDROID_CHANGELOG", ""),
    },
}

# Global maintenance mode (set via env vars at deploy time)
MAINTENANCE_MODE = os.getenv("APP_MAINTENANCE_MODE", "false").lower() in ("true", "1", "yes")
MAINTENANCE_MESSAGE = os.getenv(
    "APP_MAINTENANCE_MESSAGE",
    "We're performing scheduled maintenance. Please try again shortly.",
)


# =============================================================================
# Semver helpers
# =============================================================================

def _parse_semver(version_str: str) -> Tuple[int, int, int]:
    """Parse a version string like '1.2.3' into a (major, minor, patch) tuple.

    Tolerates missing components: '1.2' -> (1, 2, 0), '1' -> (1, 0, 0).
    Non-numeric parts are treated as 0.
    """
    parts = version_str.strip().split(".")
    result = [0, 0, 0]
    for i in range(min(len(parts), 3)):
        try:
            result[i] = int(parts[i])
        except (ValueError, IndexError):
            result[i] = 0
    return (result[0], result[1], result[2])


def _version_lt(a: str, b: str) -> bool:
    """Return True if version *a* is strictly less than version *b*."""
    return _parse_semver(a) < _parse_semver(b)


# =============================================================================
# Route registration
# =============================================================================

def register_app_version_routes(app, **_kwargs):
    """Register the version-check endpoint.

    Accepts **kwargs so it can be called with the standard
    ``register_xxx_routes(app=app, get_db=get_db, ...)`` signature used
    throughout main.py even though this route doesn't need DB or auth.
    """

    @app.get("/api/v1/app/version-check")
    async def version_check(
        platform: str = Query("ios", description="Client platform (ios or android)"),
        version: str = Query("0.0.0", description="Client app version, e.g. 1.0.2"),
        build: Optional[str] = Query(None, description="Client build number, e.g. 21"),
    ):
        """Check whether the client's app version is acceptable.

        Returns version metadata plus ``force_update`` / ``update_available``
        flags so the client can decide whether to show a blocking modal, an
        optional banner, or nothing.

        **No authentication required** — this endpoint is called before login.
        """
        platform_key = platform.lower() if platform.lower() in APP_VERSION_CONFIG else "ios"
        config = APP_VERSION_CONFIG[platform_key]

        minimum_version = config["minimum"]
        recommended_version = config["recommended"]
        current_version = config["current"]
        store_url = config["store_url"]
        changelog = config["changelog"]

        # Determine update flags
        force_update = _version_lt(version, minimum_version)
        update_available = _version_lt(version, recommended_version)

        logger.info(
            "Version check: platform=%s client=%s build=%s min=%s rec=%s force=%s",
            platform_key,
            version,
            build,
            minimum_version,
            recommended_version,
            force_update,
        )

        return JSONResponse(
            content={
                "current_version": current_version,
                "minimum_version": minimum_version,
                "recommended_version": recommended_version,
                "force_update": force_update,
                "update_available": update_available,
                "update_url": store_url,
                "changelog": changelog,
                "maintenance_mode": MAINTENANCE_MODE,
                "maintenance_message": MAINTENANCE_MESSAGE if MAINTENANCE_MODE else "",
            },
            # Allow aggressive caching in CDN/client (5 min) so the endpoint
            # doesn't get hammered on every app foreground event.
            headers={"Cache-Control": "public, max-age=300"},
        )
