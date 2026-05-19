"""
Admin guard dependency.

Provides ``require_admin`` — a FastAPI dependency that authorizes the request
only if the current user holds an administrative role.

Usage:
    from middleware.admin_guard import require_admin

    @router.get("/admin/something", dependencies=[Depends(require_admin)])
    async def handler(...):
        ...

Or to receive the user object directly:

    @router.get("/admin/something")
    async def handler(user = Depends(require_admin)):
        ...
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException, status

from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)


# Canonical set of administrative roles allowed past this guard.
ADMIN_ROLES: frozenset[str] = frozenset({"admin", "owner", "super_admin"})


def _extract_role(user: Any) -> str:
    """Best-effort extraction of the user's role, normalized to lowercase."""
    if user is None:
        return ""
    role = getattr(user, "role", None)
    if role is None and isinstance(user, dict):
        role = user.get("role")
    if role is None:
        return ""
    try:
        # Support Enum members with a `.value` attribute.
        if hasattr(role, "value"):
            role = role.value
        return str(role).strip().lower()
    except Exception as _exc:  # noqa: BLE001
        return ""


async def require_admin(current_user: Any = Depends(get_current_user)) -> Any:
    """Return ``current_user`` if administrative; otherwise raise 403."""
    if current_user is None:
        # Should have been caught by get_current_user already, but be explicit.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    role = _extract_role(current_user)
    if role not in ADMIN_ROLES:
        logger.warning(
            "Admin guard rejected user id=%s role=%r",
            getattr(current_user, "id", None),
            role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )

    return current_user


__all__ = ["require_admin", "ADMIN_ROLES"]
