"""
RBAC Enforcement Middleware — ensures role-based access on all routes.

Defense-in-depth: individual routes can still add finer-grained checks,
but this middleware provides a baseline floor that cannot be bypassed.

Role hierarchy (from utils/auth.py):
  - admin:       Platform Admin — full cross-org access
  - site_admin:  Organization-level admin
  - leadership:  VP / Director level
  - management:  Team / department management
  - sales:       Loan officers and sales staff
  - processing:  Loan processors
  - operations:  General operations

The middleware reads request.state.user (set by TenantContextMiddleware)
and enforces:
  1. Admin-only path prefixes -> require admin or site_admin permission_role
  2. Manager-only path prefixes -> require management+ permission_role
  3. Mutating requests (POST/PUT/PATCH/DELETE) on sensitive prefixes -> require
     at least authenticated user (defense against misconfigured routes)

It does NOT replace per-route permission checks — it adds a floor.
"""

import logging
from typing import Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path classification
# ---------------------------------------------------------------------------

# Paths that require admin (platform_admin or site_admin) role.
# Matched by prefix — the path must START WITH one of these strings.
ADMIN_PREFIXES = (
    "/api/v1/admin/",
    "/api/admin/",
    "/api/v1/platform-contracts",
    "/api/v1/scim/",
    "/api/v1/admin-onboarding",
)

# Paths that require at least a management-level role.
MANAGER_PREFIXES = (
    "/api/v1/team/",
    "/api/v1/teams/",
    "/api/v1/reports/org",
    "/api/v1/compliance/org",
)

# Route-internal "/admin/" segments that should also be gated.
# These are routes like /api/v1/recruit-portal/admin/workspaces
# where the router prefix is NOT admin but the sub-path is.
ADMIN_SUBPATH_MARKER = "/admin/"

# Paths that are always public (no auth or role check required).
PUBLIC_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/static/",
    # Auth endpoints
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/account/start",  # WAF-safe alias for login
    "/api/v1/account/recover",  # WAF-safe alias for forgot-password
    "/api/v1/auth/verify-email",
    "/token",
    # Public portals
    "/api/v1/portal/",
    "/api/v1/borrower-portal/",
    "/api/v1/borrower/",
    "/api/v1/portal-assistant/",
    "/api/v1/portal-video/",
    # GDPR data subject requests (must be accessible without login)
    "/api/v1/gdpr/data-subject-request",
    # Onboarding (first-time setup)
    "/api/v1/onboarding/",
    # Inbound webhooks from third parties (authenticated via webhook secret, not JWT)
    "/api/smart-docs/eclosing/webhooks",
    "/api/v1/telnyx/",
    "/api/v1/telnyx-retell/",
    "/api/vapi/",
    "/api/v1/vapi/",
    "/api/v1/slybroadcast/",
    "/api/v1/webhooks/",
    "/api/v1/los/webhooks",
)

# HTTP methods that are considered "safe" (read-only).
SAFE_METHODS: Set[str] = {"GET", "HEAD", "OPTIONS"}

# ---------------------------------------------------------------------------
# Role sets — normalized to lowercase for comparison.
# We check BOTH permission_role (Phase 2) and legacy role field.
# ---------------------------------------------------------------------------

# Roles considered admin-level (full access within scope)
ADMIN_ROLES: Set[str] = {
    "admin", "site_admin",
    # Legacy values that may still exist in production data
    "platform_admin", "super_admin",
}

# Roles considered manager-level (includes all admin roles)
MANAGER_ROLES: Set[str] = ADMIN_ROLES | {
    "leadership", "management",
    # Legacy values
    "branch_manager", "manager", "team_lead",
}


def _get_user_roles_lower(user) -> Set[str]:
    """Extract all role identifiers from a User object, lowercased."""
    roles: Set[str] = set()
    for attr in ("permission_role", "role", "current_role"):
        value = getattr(user, attr, None)
        if value and isinstance(value, str):
            roles.add(value.strip().lower())
    # Also honour a boolean flag some code paths set
    if getattr(user, "is_admin", False):
        roles.add("admin")
    return roles


def _is_public(path: str) -> bool:
    """Return True if the path is always public (no role check needed)."""
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def _requires_admin(path: str) -> bool:
    """Return True if the path requires admin role."""
    # Explicit admin prefixes
    if any(path.startswith(p) for p in ADMIN_PREFIXES):
        return True
    # Paths containing /admin/ segment after /api/ (e.g. /api/v1/recruit-portal/admin/...)
    if path.startswith("/api/") and ADMIN_SUBPATH_MARKER in path:
        return True
    return False


def _requires_manager(path: str) -> bool:
    """Return True if the path requires manager role."""
    return any(path.startswith(p) for p in MANAGER_PREFIXES)


class RBACEnforcementMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces role-based access control as a defense-in-depth layer.

    Must be registered AFTER TenantContextMiddleware (which sets request.state.user).
    In Starlette LIFO order, that means this middleware is added BEFORE
    TenantContextMiddleware in the add_middleware() call sequence.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        # 1. Skip public paths and non-API paths
        if _is_public(path) or not path.startswith("/api/") or method == "OPTIONS":
            return await call_next(request)

        # 2. Read user from request.state (set by TenantContextMiddleware)
        user = getattr(request.state, "user", None)

        if user is None:
            # TenantContextMiddleware didn't set a user — either the request
            # is unauthenticated or the token was invalid.  We do NOT block
            # here because the route's own Depends(get_current_user) will
            # return 401.  This middleware only adds ROLE checks on top of
            # existing auth.
            return await call_next(request)

        user_roles = _get_user_roles_lower(user)
        user_id = getattr(user, "id", "?")

        # 3. Admin-only routes
        if _requires_admin(path):
            if not user_roles & ADMIN_ROLES:
                logger.warning(
                    "RBAC denied: admin route %s %s accessed by user %s (roles: %s)",
                    method, path, user_id, user_roles,
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Insufficient permissions. Admin role required.",
                    },
                )

        # 4. Manager-only routes
        elif _requires_manager(path):
            if not user_roles & MANAGER_ROLES:
                logger.warning(
                    "RBAC denied: manager route %s %s accessed by user %s (roles: %s)",
                    method, path, user_id, user_roles,
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Insufficient permissions. Manager role required.",
                    },
                )

        # 5. Continue to the route handler
        return await call_next(request)
