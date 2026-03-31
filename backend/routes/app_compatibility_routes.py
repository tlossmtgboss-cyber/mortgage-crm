"""
App Version Compatibility Routes
Perennia AI

Provides version compatibility checking and mobile health endpoints.
These endpoints are unauthenticated — they must work before login so the
mobile app can determine whether to prompt for an update or show a
maintenance screen.

Rate limiting note:
  These endpoints are unauthenticated and publicly accessible.  The global
  RateLimitMiddleware in security_middleware.py applies to all requests, but
  consider adding a tighter per-IP limit if abuse is observed (e.g., 60 req/min
  per IP for /api/v1/app/* paths).
"""

import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/app", tags=["App Compatibility"])


# ============================================================================
# SEMVER COMPARISON
# ============================================================================

def _parse_version(version_str: str) -> Tuple[int, int, int]:
    """Parse a semver string into (major, minor, patch).

    Accepts "1", "1.0", or "1.0.2".  Missing components default to 0.
    """
    parts = version_str.strip().split(".")
    try:
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
    except (ValueError, IndexError):
        raise ValueError(f"Invalid version string: {version_str}")
    return (major, minor, patch)


def compare_versions(client_version: str, target_version: str) -> int:
    """Compare two semver version strings.

    Returns:
        -1 if client_version < target_version
         0 if client_version == target_version
         1 if client_version > target_version
    """
    client = _parse_version(client_version)
    target = _parse_version(target_version)

    if client < target:
        return -1
    elif client > target:
        return 1
    return 0


# ============================================================================
# CONFIGURATION (env vars with sensible defaults)
# ============================================================================

def _get_app_config() -> Dict[str, Any]:
    """Build the live config from environment variables on each request.

    Reading env vars per-request (rather than at module load) allows
    hot-updating via Railway's env var editor without a redeploy.
    """
    return {
        "ios": {
            "minimum_version": os.getenv("IOS_MIN_VERSION", "1.0.0"),
            "recommended_version": os.getenv("IOS_REC_VERSION", "1.0.2"),
            "store_url": os.getenv(
                "IOS_STORE_URL",
                "https://apps.apple.com/app/perennia-ai/id6744313015",
            ),
        },
        "android": {
            "minimum_version": os.getenv("ANDROID_MIN_VERSION", "1.0.0"),
            "recommended_version": os.getenv("ANDROID_REC_VERSION", "1.0.0"),
            "store_url": os.getenv(
                "ANDROID_STORE_URL",
                "https://play.google.com/store/apps/details?id=com.perenniaai.crm",
            ),
        },
        "maintenance_mode": os.getenv("MAINTENANCE_MODE", "false").lower() == "true",
        "maintenance_message": os.getenv("MAINTENANCE_MESSAGE", ""),
        "maintenance_estimated_end": os.getenv("MAINTENANCE_ESTIMATED_END", ""),
        "feature_flags": {
            "offline_mode": os.getenv("FF_OFFLINE_MODE", "true").lower() == "true",
            "voice_assistant": os.getenv("FF_VOICE_ASSISTANT", "true").lower() == "true",
            "document_scanner": os.getenv("FF_DOCUMENT_SCANNER", "true").lower() == "true",
            "biometric_login": os.getenv("FF_BIOMETRIC_LOGIN", "true").lower() == "true",
        },
        "backend_version": os.getenv("BACKEND_VERSION", "1.0.0"),
    }


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class MaintenanceInfo(BaseModel):
    enabled: bool
    message: str
    estimated_end: Optional[str]


class CompatibilityResponse(BaseModel):
    status: str  # "ok" | "update_recommended" | "update_required" | "maintenance"
    current_version: str
    minimum_version: str
    recommended_version: str
    update_url: Dict[str, str]
    changelog: str
    maintenance: MaintenanceInfo
    feature_flags: Dict[str, bool]


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


# ============================================================================
# ROUTES
# ============================================================================

@router.get(
    "/compatibility",
    response_model=CompatibilityResponse,
    summary="Check app version compatibility",
    description=(
        "Returns the compatibility status for a given mobile client version. "
        "No authentication required — called before login."
    ),
)
async def check_compatibility(
    platform: str = Query(
        ...,
        description="Client platform",
        regex="^(ios|android)$",
    ),
    version: str = Query(
        ...,
        description="Client app version (semver, e.g. 1.0.2)",
        regex=r"^\d+(\.\d+){0,2}$",
    ),
    build: Optional[int] = Query(
        None,
        description="Client build number (informational)",
    ),
):
    config = _get_app_config()

    # Resolve platform-specific values
    platform_config = config.get(platform)
    if platform_config is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported platform: {platform}. Use 'ios' or 'android'.",
        )

    minimum_version = platform_config["minimum_version"]
    recommended_version = platform_config["recommended_version"]

    # Maintenance mode takes precedence over everything
    if config["maintenance_mode"]:
        status_value = "maintenance"
    elif compare_versions(version, minimum_version) < 0:
        status_value = "update_required"
    elif compare_versions(version, recommended_version) < 0:
        status_value = "update_recommended"
    else:
        status_value = "ok"

    changelog = os.getenv("APP_CHANGELOG", "Bug fixes and performance improvements")

    return CompatibilityResponse(
        status=status_value,
        current_version=version,
        minimum_version=minimum_version,
        recommended_version=recommended_version,
        update_url={
            "ios": config["ios"]["store_url"],
            "android": config["android"]["store_url"],
        },
        changelog=changelog,
        maintenance=MaintenanceInfo(
            enabled=config["maintenance_mode"],
            message=config["maintenance_message"],
            estimated_end=config["maintenance_estimated_end"] or None,
        ),
        feature_flags=config["feature_flags"],
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Mobile health check",
    description=(
        "Lightweight health check for mobile connectivity testing. "
        "No authentication required."
    ),
)
async def mobile_health():
    config = _get_app_config()
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version=config["backend_version"],
    )
