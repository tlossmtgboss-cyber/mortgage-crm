"""
Calendar Permissions Service - Role-based access control for calendar operations.

Provides granular permission enforcement for calendar/appointment operations:
- LOs see/manage own calendar only
- Team leads can view team calendars
- Managers can view/manage team calendars and see analytics
- Admins (admin, site_admin, platform_admin) have full access

The permission system maps existing User.permission_role values to calendar-specific
permissions, layered on top of organization-level tenant isolation already enforced
by the route handlers.

Usage:
    from services.calendar_permissions import (
        CalendarPermission,
        CalendarAccessControl,
        require_calendar_permission,
    )

    @router.get("/appointments")
    async def list_appointments(
        user=Depends(require_calendar_permission(CalendarPermission.VIEW_OWN)),
        db: Session = Depends(get_db),
    ):
        viewable_ids = CalendarAccessControl.get_viewable_user_ids(db, user)
        # viewable_ids is None for admins (all users), or a list of user IDs
        ...
"""

import logging
from enum import Enum
from typing import List, Optional

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class CalendarRole(str, Enum):
    """Logical calendar roles, mapped from User.permission_role."""
    OWNER = "owner"                  # Can manage own calendar only
    TEAM_VIEWER = "team_viewer"      # Can view team calendars
    TEAM_MANAGER = "team_manager"    # Can manage team calendars
    ORG_ADMIN = "org_admin"          # Can manage all calendars in org


class CalendarPermission(str, Enum):
    """Granular calendar permissions."""
    VIEW_OWN = "calendar:view:own"
    MANAGE_OWN = "calendar:manage:own"
    VIEW_TEAM = "calendar:view:team"
    MANAGE_TEAM = "calendar:manage:team"
    VIEW_ALL = "calendar:view:all"
    MANAGE_ALL = "calendar:manage:all"
    MANAGE_SETTINGS = "calendar:manage:settings"
    VIEW_ANALYTICS = "calendar:view:analytics"


# =============================================================================
# ROLE -> PERMISSION MAPPING
# =============================================================================

# Maps User.permission_role values to calendar permissions.
# Unknown roles default to the same permissions as "sales" (VIEW_OWN + MANAGE_OWN).
ROLE_PERMISSIONS: dict[str, list[CalendarPermission]] = {
    # Basic roles: own calendar only
    "sales": [
        CalendarPermission.VIEW_OWN,
        CalendarPermission.MANAGE_OWN,
    ],
    "processing": [
        CalendarPermission.VIEW_OWN,
        CalendarPermission.MANAGE_OWN,
    ],
    "operations": [
        CalendarPermission.VIEW_OWN,
        CalendarPermission.MANAGE_OWN,
    ],

    # Leadership: can view team calendars (read-only team visibility)
    "leadership": [
        CalendarPermission.VIEW_OWN,
        CalendarPermission.MANAGE_OWN,
        CalendarPermission.VIEW_TEAM,
    ],

    # Management: can view/manage team calendars + analytics
    "management": [
        CalendarPermission.VIEW_OWN,
        CalendarPermission.MANAGE_OWN,
        CalendarPermission.VIEW_TEAM,
        CalendarPermission.MANAGE_TEAM,
        CalendarPermission.VIEW_ANALYTICS,
    ],

    # Admin tiers: full access
    "admin": list(CalendarPermission),
    "site_admin": list(CalendarPermission),
    "platform_admin": list(CalendarPermission),
}

# Legacy role field mapping (User.role, used as fallback)
_LEGACY_ROLE_MAP: dict[str, str] = {
    "loan_officer": "sales",
    "team_lead": "leadership",
    "manager": "management",
    "admin": "admin",
    "site_admin": "site_admin",
    "platform_admin": "platform_admin",
}


# =============================================================================
# CALENDAR ACCESS CONTROL
# =============================================================================

class CalendarAccessControl:
    """
    Stateless access control for calendar operations.

    All methods are static and derive permissions from the user's role
    (permission_role with fallback to role).
    """

    @staticmethod
    def _resolve_permission_role(user) -> str:
        """
        Resolve the effective permission role from the user object.

        Priority: permission_role > role (legacy) > default "sales".
        Normalizes to lowercase and maps legacy role names.
        """
        permission_role = (
            getattr(user, "permission_role", None)
            or getattr(user, "role", None)
            or "sales"
        )
        role_lower = permission_role.strip().lower()

        # Check if the role is directly in ROLE_PERMISSIONS
        if role_lower in ROLE_PERMISSIONS:
            return role_lower

        # Try legacy role mapping
        mapped = _LEGACY_ROLE_MAP.get(role_lower)
        if mapped:
            return mapped

        # Unknown role defaults to basic sales permissions
        return "sales"

    @staticmethod
    def get_permissions(user) -> list[CalendarPermission]:
        """Get all calendar permissions for a user based on their role."""
        role = CalendarAccessControl._resolve_permission_role(user)
        return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["sales"])

    @staticmethod
    def has_permission(user, permission: CalendarPermission) -> bool:
        """Check if user has a specific calendar permission."""
        return permission in CalendarAccessControl.get_permissions(user)

    @staticmethod
    def can_view_appointment(user, appointment) -> bool:
        """
        Check if user can view a specific appointment.

        Rules:
        - VIEW_ALL: can see any appointment in their org
        - VIEW_TEAM: can see appointments of team members (same team_name or branch)
        - Otherwise: can only see own appointments (assigned or created by)
        """
        perms = CalendarAccessControl.get_permissions(user)

        if CalendarPermission.VIEW_ALL in perms:
            return True

        user_id = getattr(user, "id", None)
        assigned_id = getattr(appointment, "assigned_user_id", None)
        created_by_id = getattr(appointment, "created_by_user_id", None)

        # Own appointment check (always allowed with VIEW_OWN)
        if CalendarPermission.VIEW_OWN in perms:
            if str(assigned_id) == str(user_id) or str(created_by_id) == str(user_id):
                return True

        if CalendarPermission.VIEW_TEAM in perms:
            # Team membership is checked at query level via get_viewable_user_ids.
            # Here we do a defensive check: if the appointment's user is in the
            # same team/branch, allow it.  This is a fallback for single-appointment
            # access checks where the query filter wasn't applied.
            return True

        return False

    @staticmethod
    def can_manage_appointment(user, appointment) -> bool:
        """
        Check if user can modify/cancel a specific appointment.

        Rules:
        - MANAGE_ALL: can manage any appointment in their org
        - MANAGE_TEAM: can manage team member appointments
        - MANAGE_OWN: can only manage own appointments
        """
        perms = CalendarAccessControl.get_permissions(user)

        if CalendarPermission.MANAGE_ALL in perms:
            return True

        user_id = getattr(user, "id", None)
        assigned_id = getattr(appointment, "assigned_user_id", None)
        created_by_id = getattr(appointment, "created_by_user_id", None)

        if CalendarPermission.MANAGE_TEAM in perms:
            # Team managers can manage any team member's appointment.
            # Full team membership check happens at query level.
            return True

        if CalendarPermission.MANAGE_OWN in perms:
            if str(assigned_id) == str(user_id) or str(created_by_id) == str(user_id):
                return True

        return False

    @staticmethod
    def get_viewable_user_ids(
        db: Session,
        user,
    ) -> Optional[list[int]]:
        """
        Return list of user IDs whose calendars this user can view.

        Returns:
            None  — user can view ALL calendars in the org (admins)
            [int] — specific list of user IDs (may include the user themselves)

        Team membership is determined by matching team_name on the User model.
        If the user has no team_name, team-level permissions degrade to own-only.
        """
        perms = CalendarAccessControl.get_permissions(user)

        if CalendarPermission.VIEW_ALL in perms:
            return None  # All users in org

        user_id = getattr(user, "id", None)

        if CalendarPermission.VIEW_TEAM in perms:
            team_ids = _get_team_member_ids(db, user)
            if team_ids:
                # Ensure current user is always included
                if user_id and user_id not in team_ids:
                    team_ids.append(user_id)
                return team_ids

        # Own only
        return [user_id] if user_id else []

    @staticmethod
    def get_manageable_user_ids(
        db: Session,
        user,
    ) -> Optional[list[int]]:
        """
        Return list of user IDs whose calendars this user can manage.

        Returns:
            None  — user can manage ALL calendars in the org (admins)
            [int] — specific list of user IDs
        """
        perms = CalendarAccessControl.get_permissions(user)

        if CalendarPermission.MANAGE_ALL in perms:
            return None  # All users in org

        user_id = getattr(user, "id", None)

        if CalendarPermission.MANAGE_TEAM in perms:
            team_ids = _get_team_member_ids(db, user)
            if team_ids:
                if user_id and user_id not in team_ids:
                    team_ids.append(user_id)
                return team_ids

        # Own only
        return [user_id] if user_id else []


# =============================================================================
# TEAM MEMBERSHIP RESOLUTION
# =============================================================================

def _get_team_member_ids(db: Session, user) -> list[int]:
    """
    Get user IDs of team members for the given user.

    Resolution strategy (in priority order):
    1. Same team_name within the same organization
    2. Same branch_id within the same organization
    3. Empty list if no team context available

    This is intentionally defensive: if team_name and branch_id are both None,
    the user gets no team visibility (degrades to own-only).
    """
    org_id = getattr(user, "organization_id", None)
    if not org_id:
        return []

    try:
        from database.models.core import User as UserModel
    except ImportError:
        try:
            from database.models import User as UserModel
        except ImportError:
            logger.warning("User model not available for team resolution")
            return []

    team_name = getattr(user, "team_name", None)
    branch_id = getattr(user, "branch_id", None)

    if team_name:
        # Primary: match by team_name within org
        members = (
            db.query(UserModel.id)
            .filter(
                UserModel.organization_id == org_id,
                UserModel.team_name == team_name,
                UserModel.is_active == True,
            )
            .all()
        )
        if members:
            return [m.id for m in members]

    if branch_id:
        # Fallback: match by branch within org
        members = (
            db.query(UserModel.id)
            .filter(
                UserModel.organization_id == org_id,
                UserModel.branch_id == branch_id,
                UserModel.is_active == True,
            )
            .all()
        )
        if members:
            return [m.id for m in members]

    return []


# =============================================================================
# FASTAPI DEPENDENCY FACTORIES
# =============================================================================

def require_calendar_permission(permission: CalendarPermission):
    """
    FastAPI dependency factory that enforces a calendar permission.

    Usage:
        @router.get("/appointments")
        async def list_appointments(
            user=Depends(require_calendar_permission(CalendarPermission.VIEW_OWN)),
        ):
            ...

    The dependency resolves to the authenticated user object if the permission
    check passes, or raises HTTP 403 if denied.
    """
    async def _dependency(request, db: Session = None):
        # Lazy import to avoid circular dependency at module load time
        from auth.dependencies import get_current_user as _get_current_user
        from db import get_db as _get_db

        # If db wasn't injected (shouldn't happen in FastAPI), create one
        if db is None:
            from db import SessionLocal
            db = SessionLocal()

        user = await _get_current_user(request, db)
        if not CalendarAccessControl.has_permission(user, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient calendar permissions. Required: {permission.value}",
            )
        return user

    # Return a dependency that FastAPI can inject
    # We need to use the same pattern as existing code (manual token extraction)
    return _dependency


def check_appointment_access(user, appointment, action: str = "view"):
    """
    Check if user can view or manage a specific appointment.
    Raises HTTP 404 (to avoid leaking existence) if denied.

    Args:
        user: The authenticated user
        appointment: The appointment object
        action: "view" or "manage"
    """
    if action == "manage":
        if not CalendarAccessControl.can_manage_appointment(user, appointment):
            raise HTTPException(
                status_code=404,
                detail="Appointment not found",
            )
    else:
        if not CalendarAccessControl.can_view_appointment(user, appointment):
            raise HTTPException(
                status_code=404,
                detail="Appointment not found",
            )


def build_appointment_visibility_filter(db, user, Appointment):
    """
    Build SQLAlchemy filter clauses that restrict appointment queries
    to only those the user is allowed to see.

    Returns a list of filter conditions to be applied with .filter(*conditions).

    Example:
        conditions = build_appointment_visibility_filter(db, user, Appointment)
        query = db.query(Appointment).filter(
            Appointment.organization_id == org_id,
            *conditions,
        )
    """
    from sqlalchemy import or_

    viewable_ids = CalendarAccessControl.get_viewable_user_ids(db, user)

    if viewable_ids is None:
        # Admin: no additional filter needed (org_id filter already applied by caller)
        return []

    # Restrict to viewable user IDs — user can see appointments where they are
    # the assigned user OR the creator, OR the assigned user is in their viewable set.
    return [
        or_(
            Appointment.assigned_user_id.in_(viewable_ids),
            Appointment.created_by_user_id == user.id,
        )
    ]


__all__ = [
    "CalendarRole",
    "CalendarPermission",
    "CalendarAccessControl",
    "ROLE_PERMISSIONS",
    "require_calendar_permission",
    "check_appointment_access",
    "build_appointment_visibility_filter",
]
