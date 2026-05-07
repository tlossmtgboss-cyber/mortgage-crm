"""
Centralized RBAC Enforcement Middleware — granular route-to-permission mapping.

Extends rbac_enforcement.py (which provides a baseline admin/manager floor)
with finer-grained per-prefix and per-method permission checks.

rbac_enforcement.py catches broad categories (admin-only, manager-only).
This middleware adds:
  - Org settings routes -> org_admin+
  - Reports routes -> manager+
  - User write operations -> org_admin+
  - Compliance routes -> manager+
  - Method-aware gating (read vs. write on the same prefix)

Permission hierarchy (highest to lowest):
  platform_admin > site_admin > org_admin > leadership > management > sales > processing > operations > readonly

The hierarchy is intentionally a superset of the existing permission_role
values on User.permission_role (admin, site_admin, leadership, management,
sales, processing, operations) plus the task-requested levels
(platform_admin, org_admin, readonly) mapped onto existing role values.

Mapping from task-requested names to actual permission_role values:
  platform_admin -> admin, platform_admin, super_admin
  site_admin     -> site_admin
  org_admin      -> site_admin, admin (org-level admin)
  manager        -> management, leadership, branch_manager, manager, team_lead
  loan_officer   -> sales, loan_officer
  processor      -> processing, processor
  assistant      -> operations, assistant
  readonly       -> readonly, viewer

Must be registered AFTER TenantContextMiddleware (Starlette LIFO: add BEFORE).
Must be registered AFTER rbac_enforcement.py so both layers run.
"""

import logging
import time
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Permission hierarchy — ordered from most to least privileged.
# Each level includes all privileges of levels below it.
# ---------------------------------------------------------------------------

PERMISSION_LEVELS: List[str] = [
    "platform_admin",
    "site_admin",
    "org_admin",
    "leadership",
    "management",
    "sales",
    "processing",
    "operations",
    "readonly",
]

# Build a set of levels at-or-above a given level for fast lookup.
# e.g. _LEVEL_SETS["management"] = {"platform_admin", "site_admin", "org_admin", "leadership", "management"}
_LEVEL_SETS: Dict[str, FrozenSet[str]] = {}
for _i, _level in enumerate(PERMISSION_LEVELS):
    _LEVEL_SETS[_level] = frozenset(PERMISSION_LEVELS[: _i + 1])

# ---------------------------------------------------------------------------
# Alias mapping: normalize various role strings from User.permission_role,
# User.role, and User.current_role into canonical permission levels.
# ---------------------------------------------------------------------------

ROLE_ALIASES: Dict[str, str] = {
    # platform_admin aliases
    "admin": "platform_admin",
    "platform_admin": "platform_admin",
    "super_admin": "platform_admin",
    # site_admin aliases
    "site_admin": "site_admin",
    # org_admin — in practice site_admin doubles as org_admin
    "org_admin": "org_admin",
    # leadership aliases
    "leadership": "leadership",
    "director": "leadership",
    "vp": "leadership",
    # management aliases
    "management": "management",
    "manager": "management",
    "branch_manager": "management",
    "team_lead": "management",
    "regional_manager": "management",
    # sales/loan_officer aliases
    "sales": "sales",
    "loan_officer": "sales",
    # processing aliases
    "processing": "processing",
    "processor": "processing",
    # operations aliases
    "operations": "operations",
    "assistant": "operations",
    # readonly aliases
    "readonly": "readonly",
    "viewer": "readonly",
}

# ---------------------------------------------------------------------------
# Route -> minimum permission level mapping.
#
# Each entry is (url_prefix, http_methods_or_None, min_level).
#   - http_methods=None means ALL methods require min_level.
#   - http_methods={"POST","PUT","PATCH","DELETE"} means only write methods
#     require min_level; reads pass through to route-level auth.
#
# Order matters: first match wins. Put more specific prefixes first.
# ---------------------------------------------------------------------------

WRITE_METHODS: FrozenSet[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

ROUTE_PERMISSION_MAP: List[Tuple[str, Optional[FrozenSet[str]], str]] = [
    # Admin routes (belt-and-suspenders — rbac_enforcement.py also blocks these)
    ("/api/v1/admin/", None, "platform_admin"),
    ("/api/admin/", None, "platform_admin"),
    ("/api/v1/platform-contracts", None, "platform_admin"),
    ("/api/v1/scim/", None, "platform_admin"),

    # Organization settings — org_admin+ for any method
    ("/api/v1/org/settings/", None, "org_admin"),
    ("/api/v1/organizations/", WRITE_METHODS, "org_admin"),

    # User management — reads are open to authenticated users,
    # writes (create/update/delete) require org_admin+
    ("/api/v1/users/", WRITE_METHODS, "org_admin"),
    ("/api/v1/user-roles/", WRITE_METHODS, "org_admin"),

    # Reports — manager+ for all methods
    ("/api/v1/reports/", None, "management"),

    # Compliance — manager+ for all methods
    ("/api/v1/compliance/", None, "management"),

    # Team management — manager+
    ("/api/v1/team/", None, "management"),
    ("/api/v1/teams/", None, "management"),
]

# Paths that are always exempt from RBAC checks (public, webhooks, etc.).
# Reuse the same list as rbac_enforcement.py to stay in sync.
EXEMPT_PREFIXES: Tuple[str, ...] = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/static/",
    "/api/v1/auth/",
    "/api/v1/account/start",
    "/api/v1/account/recover",
    "/token",
    "/api/v1/portal/",
    "/api/v1/borrower-portal/",
    "/api/v1/borrower/",
    "/api/v1/portal-assistant/",
    "/api/v1/portal-video/",
    "/api/v1/gdpr/data-subject-request",
    "/api/v1/onboarding/",
    "/api/smart-docs/eclosing/webhooks",
    "/api/v1/telnyx/",
    "/api/v1/telnyx-retell/",
    "/api/vapi/",
    "/api/v1/vapi/",
    "/api/v1/slybroadcast/",
    "/api/v1/webhooks/",
    "/api/v1/los/webhooks",
)


def _resolve_user_level(user) -> Optional[str]:
    """
    Extract the highest canonical permission level from a User object.

    Checks permission_role, role, and current_role attributes.
    Returns the highest (most privileged) canonical level found,
    or None if no recognized role is present.
    """
    best_index = len(PERMISSION_LEVELS)  # Start worse than any level
    found_any = False

    for attr in ("permission_role", "role", "current_role"):
        raw = getattr(user, attr, None)
        if not raw or not isinstance(raw, str):
            continue
        normalized = raw.strip().lower()
        canonical = ROLE_ALIASES.get(normalized)
        if canonical is None:
            continue
        idx = PERMISSION_LEVELS.index(canonical)
        if idx < best_index:
            best_index = idx
            found_any = True

    # Also honour is_admin boolean flag
    if getattr(user, "is_admin", False):
        admin_idx = PERMISSION_LEVELS.index("platform_admin")
        if admin_idx < best_index:
            best_index = admin_idx
            found_any = True

    return PERMISSION_LEVELS[best_index] if found_any else None


def _is_exempt(path: str) -> bool:
    """Return True if the path is exempt from RBAC checks."""
    return any(path.startswith(p) for p in EXEMPT_PREFIXES)


def _find_required_level(
    path: str, method: str
) -> Optional[str]:
    """
    Find the minimum permission level required for the given path + method.

    Returns the level string (e.g. "management") or None if no rule matches.
    """
    for prefix, methods, min_level in ROUTE_PERMISSION_MAP:
        if not path.startswith(prefix):
            continue
        # If methods is None, the rule applies to ALL methods.
        # If methods is a set, only those HTTP methods are gated.
        if methods is not None and method not in methods:
            continue
        return min_level
    return None


def _has_permission(user_level: str, required_level: str) -> bool:
    """
    Check if user_level meets or exceeds required_level in the hierarchy.

    Returns True if user_level is at or above required_level.
    """
    allowed_set = _LEVEL_SETS.get(required_level)
    if allowed_set is None:
        # Unknown required level — deny by default
        return False
    return user_level in allowed_set


class CentralizedRBACMiddleware(BaseHTTPMiddleware):
    """
    Granular route-to-permission enforcement middleware.

    Works alongside RBACEnforcementMiddleware from rbac_enforcement.py:
    - rbac_enforcement.py provides a broad admin/manager floor.
    - This middleware adds finer-grained per-prefix, per-method checks.

    Must be registered AFTER TenantContextMiddleware sets request.state.user.
    In Starlette LIFO order, add this BEFORE TenantContextMiddleware.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        # 1. Skip exempt paths, non-API paths, and OPTIONS preflight
        if _is_exempt(path) or not path.startswith("/api/") or method == "OPTIONS":
            return await call_next(request)

        # 2. Read user from request.state (set by TenantContextMiddleware)
        user = getattr(request.state, "user", None)
        if user is None:
            # No user set — let route-level Depends(get_current_user) handle 401.
            return await call_next(request)

        # 3. Check if this route + method has a permission requirement
        required_level = _find_required_level(path, method)
        if required_level is None:
            # No rule matches — allow through (route-level auth still applies)
            return await call_next(request)

        # 4. Resolve user's canonical permission level
        user_level = _resolve_user_level(user)
        user_id = getattr(user, "id", "?")

        if user_level is None:
            # User has no recognized role — deny access to gated routes
            logger.warning(
                "RBAC_CENTRAL denied: no recognized role for user %s "
                "accessing %s %s (required: %s)",
                user_id, method, path, required_level,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Insufficient permissions. {required_level} role or higher required.",
                },
            )

        # 5. Check if user's level meets the requirement
        if not _has_permission(user_level, required_level):
            logger.warning(
                "RBAC_CENTRAL denied: user %s (level=%s) blocked from %s %s "
                "(required: %s+)",
                user_id, user_level, method, path, required_level,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Insufficient permissions. {required_level} role or higher required.",
                },
            )

        # 6. Allowed — continue to route handler
        return await call_next(request)
