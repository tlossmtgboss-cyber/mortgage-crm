"""
Permission Roles — Single source of truth.

Import from here instead of hardcoding role strings in route files.

Usage:
    from utils.roles import ALLOWED_ROLES, ADMIN_ROLES, INVITE_GRANTING_ROLES, validate_role
"""

from enum import Enum
from typing import Set


class PermissionRole(str, Enum):
    """All valid permission roles in the system."""
    ADMIN = "admin"
    SITE_ADMIN = "site_admin"
    LEADERSHIP = "leadership"
    MANAGEMENT = "management"
    SALES = "sales"
    PROCESSING = "processing"
    OPERATIONS = "operations"


# Role metadata for UI rendering and display
ROLE_METADATA = {
    PermissionRole.ADMIN: {"label": "Admin", "description": "Full system access"},
    PermissionRole.SITE_ADMIN: {"label": "Site Admin", "description": "Site-level administration"},
    PermissionRole.LEADERSHIP: {"label": "Leadership", "description": "Company leadership with broad access"},
    PermissionRole.MANAGEMENT: {"label": "Management", "description": "Team management capabilities"},
    PermissionRole.SALES: {"label": "Sales", "description": "Loan officer / sales role"},
    PermissionRole.PROCESSING: {"label": "Processing", "description": "Loan processing role"},
    PermissionRole.OPERATIONS: {"label": "Operations", "description": "Operations and support"},
}

# All roles that can be assigned to employees
ALLOWED_ROLES: Set[str] = {r.value for r in PermissionRole}

# Roles that have admin-level privileges
ADMIN_ROLES: Set[str] = {"admin", "site_admin"}

# Roles that can create invitations
INVITE_GRANTING_ROLES: Set[str] = {"admin", "site_admin", "leadership", "management"}


def validate_role(role: str) -> str:
    """Validate and normalize a role string. Returns the role value or raises ValueError."""
    normalized = (role or "").lower().strip()
    if normalized not in ALLOWED_ROLES:
        raise ValueError(f"Invalid role '{role}'. Must be one of: {', '.join(sorted(ALLOWED_ROLES))}")
    return normalized


def is_admin_role(role: str) -> bool:
    """Check if a role has admin-level privileges."""
    return (role or "").lower().strip() in ADMIN_ROLES


def can_grant_invites(role: str) -> bool:
    """Check if a role can create employee invitations."""
    return (role or "").lower().strip() in INVITE_GRANTING_ROLES
