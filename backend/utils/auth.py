"""
Authentication and Authorization Utilities
Provides role checking, permission verification, and password validation
for FastAPI endpoints.

Role Hierarchy:
- admin: Platform Administrator (developer/engineer) - full access across all organizations
- site_admin: Site Administrator (licensee) - full access within their organization only
- leadership: Organization leadership (VP, Director level)
- management: Department/team management
- sales: Sales team members
- processing: Loan processors
- operations: General operations staff
"""
import re
import logging
from typing import Optional, List
from fastapi import HTTPException, Depends
from functools import wraps

logger = logging.getLogger(__name__)

# =============================================================================
# PASSWORD COMPLEXITY CONSTANTS
# =============================================================================

PASSWORD_MIN_LENGTH = 12
PASSWORD_SPECIAL_CHARS = r'!@#$%^&*()\-_+=\[\]{}|;:,.<>?/~`'

# =============================================================================
# PASSWORD STRENGTH VALIDATION (Enterprise Security - Domain 4)
# =============================================================================

def validate_password_strength(password: str) -> List[str]:
    """
    Validate password meets enterprise complexity requirements.

    Requirements:
    - Minimum 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character (!@#$%^&*()-_+=)

    Args:
        password: The password string to validate

    Returns:
        List of violation messages. Empty list means the password is valid.
    """
    violations = []

    if len(password) < PASSWORD_MIN_LENGTH:
        violations.append(
            f"Password must be at least {PASSWORD_MIN_LENGTH} characters long "
            f"(currently {len(password)})"
        )

    if not re.search(r'[A-Z]', password):
        violations.append("Password must contain at least one uppercase letter")

    if not re.search(r'[a-z]', password):
        violations.append("Password must contain at least one lowercase letter")

    if not re.search(r'[0-9]', password):
        violations.append("Password must contain at least one digit")

    if not re.search(r'[!@#$%^&*()\-_+=\[\]{}|;:,.<>?/~`]', password):
        violations.append(
            "Password must contain at least one special character "
            "(!@#$%^&*()-_+=)"
        )

    return violations


def require_strong_password(password: str) -> None:
    """
    Validate password strength and raise HTTPException if requirements are not met.

    Convenience wrapper around validate_password_strength() for use in route handlers.

    Args:
        password: The password string to validate

    Raises:
        HTTPException: 400 Bad Request with list of violations if password is weak
    """
    violations = validate_password_strength(password)
    if violations:
        raise HTTPException(
            status_code=400,
            detail=f"Password does not meet security requirements: {'; '.join(violations)}"
        )


# =============================================================================
# MFA ENFORCEMENT FOR ADMIN ACCOUNTS (Enterprise Security - Domain 4)
# =============================================================================

# Admin-level roles that MUST have MFA enabled to access sensitive endpoints
ADMIN_ROLES_REQUIRING_MFA = ['admin', 'site_admin']


def require_admin_mfa(current_user) -> None:
    """
    Enforce MFA for admin-level users accessing sensitive endpoints.

    If the user has an admin or site_admin role/permission_role, they MUST
    have MFA enabled. Non-admin users are allowed through without MFA.

    Args:
        current_user: The authenticated user object

    Raises:
        HTTPException: 403 Forbidden if admin user has not enabled MFA
    """
    permission_role = getattr(current_user, 'permission_role', None) or ''
    legacy_role = getattr(current_user, 'role', None) or ''

    is_admin_user = (
        permission_role.lower() in [r.lower() for r in ADMIN_ROLES_REQUIRING_MFA]
        or legacy_role.lower() in [r.lower() for r in ADMIN_ROLES_REQUIRING_MFA]
    )

    if not is_admin_user:
        return  # Non-admin users are not required to have MFA

    mfa_enabled = getattr(current_user, 'mfa_enabled', False) or False

    if not mfa_enabled:
        logger.warning(
            f"Admin MFA enforcement: user {getattr(current_user, 'email', '?')} "
            f"(role={legacy_role}, permission_role={permission_role}) "
            f"blocked from sensitive endpoint - MFA not enabled"
        )
        raise HTTPException(
            status_code=403,
            detail=(
                "Multi-factor authentication (MFA) is required for admin accounts. "
                "Please enable MFA at /api/v1/auth/mfa/setup before accessing "
                "this resource."
            ),
        )


# =============================================================================
# ROLE DEFINITIONS
# =============================================================================

# Platform admin - developer/engineer with god-mode access across all organizations
PLATFORM_ADMIN_ROLES = ['admin']

# Site admin - licensee/organization owner with admin access within their org
SITE_ADMIN_ROLES = ['site_admin']

# Admin-level roles for user management operations (includes both platform and site admins)
ADMIN_PERMISSION_ROLES = ['admin', 'site_admin', 'leadership', 'management']
ADMIN_LEGACY_ROLES = ['admin', 'manager']

# Power user roles for elevated access
POWER_USER_PERMISSION_ROLES = ['admin', 'site_admin', 'leadership', 'management', 'sales']
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


def is_platform_admin(user) -> bool:
    """
    Check if user is a Platform Administrator (developer/engineer).

    Platform admins have god-mode access across all organizations.
    They typically don't have an organization_id set.

    Args:
        user: User object with permission_role and organization_id attributes

    Returns:
        True if user is a platform admin
    """
    permission_role = getattr(user, 'permission_role', None)
    if permission_role and permission_role.lower() in [r.lower() for r in PLATFORM_ADMIN_ROLES]:
        return True

    # Check legacy admin role without organization
    legacy_role = getattr(user, 'role', None)
    org_id = getattr(user, 'organization_id', None)
    if legacy_role and legacy_role.lower() == 'admin' and not org_id:
        return True

    return False


def is_site_admin(user) -> bool:
    """
    Check if user is a Site Administrator (licensee/organization owner).

    Site admins have admin access within their own organization only.
    They have an organization_id set.

    Args:
        user: User object with permission_role and organization_id attributes

    Returns:
        True if user is a site admin
    """
    permission_role = getattr(user, 'permission_role', None)
    if permission_role and permission_role.lower() in [r.lower() for r in SITE_ADMIN_ROLES]:
        return True

    return False


def check_org_scoped_admin(user, target_org_id: int = None) -> bool:
    """
    Check if user has admin access to a specific organization.

    - Platform admins have access to all organizations
    - Site admins only have access to their own organization

    Args:
        user: User object
        target_org_id: The organization ID to check access for

    Returns:
        True if user has admin access to the target organization
    """
    # Platform admins have access to everything
    if is_platform_admin(user):
        return True

    # Site admins can only access their own organization
    if is_site_admin(user):
        user_org_id = getattr(user, 'organization_id', None)
        if target_org_id is None:
            return True  # No specific org required
        return user_org_id == target_org_id

    # Other admin-level roles with org check
    if check_admin_permission(user):
        user_org_id = getattr(user, 'organization_id', None)
        if target_org_id is None:
            return True
        return user_org_id == target_org_id

    return False


def require_platform_admin(current_user) -> None:
    """
    Verify current user is a Platform Administrator. Raises HTTPException if not.

    Platform admins are developers/engineers with full system access.

    Args:
        current_user: The authenticated user object

    Raises:
        HTTPException: 403 Forbidden if user is not a platform admin
    """
    if not is_platform_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Platform Administrator access required. This action requires developer-level permissions."
        )


def require_site_admin(current_user) -> None:
    """
    Verify current user is at least a Site Administrator. Raises HTTPException if not.

    Allows both platform admins and site admins.

    Args:
        current_user: The authenticated user object

    Raises:
        HTTPException: 403 Forbidden if user is not an admin
    """
    if not (is_platform_admin(current_user) or is_site_admin(current_user)):
        raise HTTPException(
            status_code=403,
            detail="Site Administrator access required. You must be an organization administrator to perform this action."
        )
