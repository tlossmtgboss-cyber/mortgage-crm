"""
Authentication and Authorization Utilities
Provides role checking and permission verification for FastAPI endpoints.
"""
from typing import Optional, List
from fastapi import HTTPException, Depends
from functools import wraps

# Admin-level roles for user management operations
ADMIN_PERMISSION_ROLES = ['admin', 'leadership', 'management']
ADMIN_LEGACY_ROLES = ['admin', 'manager']

# Power user roles for elevated access
POWER_USER_PERMISSION_ROLES = ['admin', 'leadership', 'management', 'sales']
POWER_USER_LEGACY_ROLES = ['admin', 'manager', 'senior_loan_officer']


def check_admin_permission(user) -> bool:
    """
    Check if user has admin-level permissions.

    Checks Phase 2 permission_role first, then falls back to legacy role.

    Args:
        user: User object with role and/or permission_role attributes

    Returns:
        True if user has admin permissions, False otherwise
    """
    # Check Phase 2 permission_role first
    permission_role = getattr(user, 'permission_role', None)
    if permission_role and permission_role.lower() in [r.lower() for r in ADMIN_PERMISSION_ROLES]:
        return True

    # Check is_admin flag
    if getattr(user, 'is_admin', False):
        return True

    # Fallback to legacy role
    legacy_role = getattr(user, 'role', None)
    if legacy_role and legacy_role.lower() in [r.lower() for r in ADMIN_LEGACY_ROLES]:
        return True

    return False


def check_power_user_permission(user) -> bool:
    """
    Check if user has power user (elevated) permissions.

    Power users include admins, managers, and senior staff.

    Args:
        user: User object with role and/or permission_role attributes

    Returns:
        True if user has power user permissions, False otherwise
    """
    # Check Phase 2 permission_role first
    permission_role = getattr(user, 'permission_role', None)
    if permission_role and permission_role.lower() in [r.lower() for r in POWER_USER_PERMISSION_ROLES]:
        return True

    # Check is_admin flag
    if getattr(user, 'is_admin', False):
        return True

    # Fallback to legacy role
    legacy_role = getattr(user, 'role', None)
    if legacy_role and legacy_role.lower() in [r.lower() for r in POWER_USER_LEGACY_ROLES]:
        return True

    return False


def check_has_role(user, allowed_roles: List[str]) -> bool:
    """
    Check if user has any of the specified roles.

    Args:
        user: User object with role and/or permission_role attributes
        allowed_roles: List of role names that are allowed

    Returns:
        True if user has any of the allowed roles
    """
    allowed_lower = [r.lower() for r in allowed_roles]

    # Check permission_role
    permission_role = getattr(user, 'permission_role', None)
    if permission_role and permission_role.lower() in allowed_lower:
        return True

    # Check legacy role
    legacy_role = getattr(user, 'role', None)
    if legacy_role and legacy_role.lower() in allowed_lower:
        return True

    return False


def require_admin(current_user) -> None:
    """
    Verify current user has admin permissions. Raises HTTPException if not.

    Usage in FastAPI endpoint:
        @app.get("/admin/endpoint")
        async def admin_endpoint(current_user: User = Depends(get_current_user)):
            require_admin(current_user)
            # ... rest of endpoint

    Args:
        current_user: The authenticated user object

    Raises:
        HTTPException: 403 Forbidden if user is not an admin
    """
    if not check_admin_permission(current_user):
        raise HTTPException(
            status_code=403,
            detail="Admin access required. You do not have permission to perform this action."
        )


def require_power_user(current_user) -> None:
    """
    Verify current user has power user (elevated) permissions. Raises HTTPException if not.

    Args:
        current_user: The authenticated user object

    Raises:
        HTTPException: 403 Forbidden if user is not a power user
    """
    if not check_power_user_permission(current_user):
        raise HTTPException(
            status_code=403,
            detail="Elevated access required. You do not have permission to perform this action."
        )


def require_roles(current_user, allowed_roles: List[str]) -> None:
    """
    Verify current user has one of the specified roles. Raises HTTPException if not.

    Args:
        current_user: The authenticated user object
        allowed_roles: List of role names that are allowed

    Raises:
        HTTPException: 403 Forbidden if user doesn't have any of the allowed roles
    """
    if not check_has_role(current_user, allowed_roles):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied. Required role: {', '.join(allowed_roles)}"
        )


def get_user_role_tier(user) -> str:
    """
    Get the user's role tier for rate limiting and feature access.

    Returns:
        'admin' | 'power_user' | 'standard' | 'anonymous'
    """
    if check_admin_permission(user):
        return 'admin'
    if check_power_user_permission(user):
        return 'power_user'
    return 'standard'
