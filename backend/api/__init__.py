"""
API Module

Contains all API route definitions organized by version and domain.

Structure:
    api/
    ├── health.py          # Health check endpoints
    ├── versioning.py      # API versioning infrastructure
    ├── cache_routes.py    # Cache management
    ├── monitoring.py      # Monitoring endpoints
    ├── webhooks.py        # Webhook handlers
    └── v1/                # API version 1
        └── routes/        # Domain-specific routes
"""

from .versioning import (
    APIVersion,
    VersionedAPIRouter,
    APIVersionMiddleware,
    get_version_info,
    version_router,
    CURRENT_VERSION,
)

__all__ = [
    "APIVersion",
    "VersionedAPIRouter",
    "APIVersionMiddleware",
    "get_version_info",
    "version_router",
    "CURRENT_VERSION",
]
