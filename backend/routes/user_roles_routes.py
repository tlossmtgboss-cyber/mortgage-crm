"""
User Roles Routes
Perennia AI - Mortgage CRM

API endpoints for multi-role user system:
- Get assigned roles for current user
- Switch active role (view)
- Admin: Manage user role assignments
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Security setup
security = HTTPBearer(auto_error=False)


# User proxy class for auth
class UserProxy:
    """Proxy class for authenticated user."""
    def __init__(self, row):
        self.id = row[0]
        self.email = row[1]
        self.name = row[2]
        self.role = row[3] if len(row) > 3 else None


# Auth dependency
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current user from JWT token."""
    from auth.tokens import verify_access_token

    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        token = credentials.credentials
        payload = verify_access_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or revoked token")
        email = payload.get("sub")

        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get user with raw SQL
        result = db.execute(
            text("SELECT id, email, full_name, role FROM users WHERE email = :email"),
            {"email": email}
        )
        user_row = result.fetchone()

        if not user_row:
            raise HTTPException(status_code=404, detail="User not found")

        return UserProxy(user_row)

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")
    except Exception as e:
        logger.error(f"Auth error (likely JWT): {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

router = APIRouter(prefix="/api/v1/users", tags=["User Roles"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class RoleInfo(BaseModel):
    """Role information."""
    id: int
    name: str
    is_primary: bool = False
    assigned_at: Optional[datetime] = None


class UserRolesResponse(BaseModel):
    """Response containing user's roles and active role."""
    assigned_roles: List[RoleInfo]
    active_role: Optional[RoleInfo]
    can_switch_roles: bool


class SwitchRoleRequest(BaseModel):
    """Request to switch active role."""
    role_id: int = Field(..., description="ID of the role to switch to")


class AssignRolesRequest(BaseModel):
    """Request to assign roles to a user."""
    role_ids: List[int] = Field(..., description="List of role IDs to assign")
    primary_role_id: Optional[int] = Field(None, description="ID of the primary role")


class AssignRolesResponse(BaseModel):
    """Response from role assignment."""
    user_id: int
    assigned_roles: List[RoleInfo]
    message: str


# =============================================================================
# CURRENT USER ROLE ENDPOINTS
# =============================================================================

@router.get("/me/roles", response_model=UserRolesResponse)
async def get_my_roles(
    current_user: UserProxy = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get current user's assigned roles and active role.

    Returns all roles assigned to the user and which role is currently active
    for UI view purposes.
    """
    try:
        user_id = current_user.id

        # Get assigned roles
        assigned_result = db.execute(text("""
            SELECT
                uar.role_id,
                oer.name as role_name,
                uar.is_primary,
                uar.assigned_at
            FROM user_assigned_roles uar
            JOIN onboarding_roles oer ON oer.id = uar.role_id
            WHERE uar.user_id = :user_id
            ORDER BY uar.is_primary DESC, oer.name
        """), {"user_id": user_id})

        assigned_roles = []
        for row in assigned_result:
            assigned_roles.append(RoleInfo(
                id=row.role_id,
                name=row.role_name,
                is_primary=row.is_primary,
                assigned_at=row.assigned_at
            ))

        # Get active role
        active_result = db.execute(text("""
            SELECT
                uac.active_role_id,
                oer.name as role_name
            FROM user_active_role uac
            JOIN onboarding_roles oer ON oer.id = uac.active_role_id
            WHERE uac.user_id = :user_id
        """), {"user_id": user_id})

        active_row = active_result.fetchone()
        active_role = None
        if active_row:
            # Find if active role is primary
            is_primary = any(r.id == active_row.active_role_id and r.is_primary for r in assigned_roles)
            active_role = RoleInfo(
                id=active_row.active_role_id,
                name=active_row.role_name,
                is_primary=is_primary
            )
        elif assigned_roles:
            # If no active role set, use primary or first assigned
            active_role = assigned_roles[0]

        return UserRolesResponse(
            assigned_roles=assigned_roles,
            active_role=active_role,
            can_switch_roles=len(assigned_roles) > 1
        )
    except Exception as e:
        # Tables might not exist yet or other error - return empty response
        logger.warning(f"Error fetching user roles: {e}")
        return UserRolesResponse(
            assigned_roles=[],
            active_role=None,
            can_switch_roles=False
        )


@router.post("/me/roles/switch")
async def switch_active_role(
    request: SwitchRoleRequest,
    current_user: UserProxy = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Switch the current user's active role for UI view.

    This changes which navigation and dashboard the user sees,
    but does not affect their actual permissions (they retain
    the highest permissions from all assigned roles).

    Admins (is_admin=True or permission_role='admin'/'site_admin') can
    switch to any role for impersonation/preview purposes.
    """
    user_id = current_user.id
    role_id = request.role_id

    # Check if user is an admin (can impersonate any role)
    is_admin = getattr(current_user, 'is_admin', False)
    permission_role = getattr(current_user, 'permission_role', '')
    is_admin_role = permission_role in ['admin', 'site_admin', 'platform_admin']

    if not is_admin and not is_admin_role:
        # Non-admins can only switch to roles they have assigned
        check_result = db.execute(text("""
            SELECT 1 FROM user_assigned_roles
            WHERE user_id = :user_id AND role_id = :role_id
        """), {"user_id": user_id, "role_id": role_id})

        if not check_result.fetchone():
            raise HTTPException(
                status_code=403,
                detail="You do not have this role assigned"
            )

    # Verify the role exists
    role_exists = db.execute(text("""
        SELECT 1 FROM onboarding_roles WHERE id = :role_id
    """), {"role_id": role_id})

    if not role_exists.fetchone():
        raise HTTPException(
            status_code=404,
            detail="Role not found"
        )

    # Get role name for response
    role_result = db.execute(text("""
        SELECT name FROM onboarding_roles WHERE id = :role_id
    """), {"role_id": role_id})
    role_row = role_result.fetchone()
    role_name = role_row.name if role_row else "Unknown"

    # Upsert active role - use INSERT OR REPLACE for SQLite compatibility
    # First try PostgreSQL syntax, fall back to SQLite
    now = datetime.now(timezone.utc)
    try:
        db.execute(text("""
            INSERT INTO user_active_role (user_id, active_role_id, switched_at)
            VALUES (:user_id, :role_id, :now)
            ON CONFLICT (user_id)
            DO UPDATE SET active_role_id = :role_id, switched_at = :now
        """), {"user_id": user_id, "role_id": role_id, "now": now})
    except Exception as e:
        logger.debug(f"PostgreSQL upsert failed in switch_active_role, trying SQLite fallback: {e}")
        # SQLite fallback using INSERT OR REPLACE
        db.execute(text("""
            INSERT OR REPLACE INTO user_active_role (user_id, active_role_id, switched_at)
            VALUES (:user_id, :role_id, :now)
        """), {"user_id": user_id, "role_id": role_id, "now": now})
    db.commit()

    logger.info(f"User {user_id} switched active role to {role_id} ({role_name})")

    return {
        "status": "success",
        "active_role": {
            "id": role_id,
            "name": role_name
        },
        "message": f"Switched to {role_name} view"
    }


# =============================================================================
# ADMIN ROLE MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/{user_id}/roles", response_model=UserRolesResponse)
async def get_user_roles(
    user_id: int,
    current_user: UserProxy = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get a user's assigned roles (admin only).

    Returns all roles assigned to the specified user.
    """
    # Check if current user is admin
    if current_user.role not in ['admin', 'super_admin', 'site_admin']:
        # Also check if they have Site Administrator role via onboarding
        admin_check = db.execute(text("""
            SELECT 1 FROM user_assigned_roles uar
            JOIN onboarding_roles oer ON oer.id = uar.role_id
            WHERE uar.user_id = :user_id
            AND oer.name IN ('Site Administrator', 'Admin')
        """), {"user_id": current_user.id})

        if not admin_check.fetchone():
            raise HTTPException(
                status_code=403,
                detail="Admin access required"
            )

    # Verify target user exists
    user_check = db.execute(text("""
        SELECT id FROM users WHERE id = :user_id
    """), {"user_id": user_id})

    if not user_check.fetchone():
        raise HTTPException(status_code=404, detail="User not found")

    # Get assigned roles
    assigned_result = db.execute(text("""
        SELECT
            uar.role_id,
            oer.name as role_name,
            uar.is_primary,
            uar.assigned_at
        FROM user_assigned_roles uar
        JOIN onboarding_roles oer ON oer.id = uar.role_id
        WHERE uar.user_id = :user_id
        ORDER BY uar.is_primary DESC, oer.name
    """), {"user_id": user_id})

    assigned_roles = []
    for row in assigned_result:
        assigned_roles.append(RoleInfo(
            id=row.role_id,
            name=row.role_name,
            is_primary=row.is_primary,
            assigned_at=row.assigned_at
        ))

    # Get active role
    active_result = db.execute(text("""
        SELECT
            uac.active_role_id,
            oer.name as role_name
        FROM user_active_role uac
        JOIN onboarding_roles oer ON oer.id = uac.active_role_id
        WHERE uac.user_id = :user_id
    """), {"user_id": user_id})

    active_row = active_result.fetchone()
    active_role = None
    if active_row:
        is_primary = any(r.id == active_row.active_role_id and r.is_primary for r in assigned_roles)
        active_role = RoleInfo(
            id=active_row.active_role_id,
            name=active_row.role_name,
            is_primary=is_primary
        )
    elif assigned_roles:
        active_role = assigned_roles[0]

    return UserRolesResponse(
        assigned_roles=assigned_roles,
        active_role=active_role,
        can_switch_roles=len(assigned_roles) > 1
    )


@router.put("/{user_id}/roles", response_model=AssignRolesResponse)
async def assign_user_roles(
    user_id: int,
    request: AssignRolesRequest,
    current_user: UserProxy = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Assign roles to a user (admin only).

    Replaces all existing role assignments with the new list.
    One role should be marked as primary.
    """
    # Check if current user is admin
    if current_user.role not in ['admin', 'super_admin', 'site_admin']:
        admin_check = db.execute(text("""
            SELECT 1 FROM user_assigned_roles uar
            JOIN onboarding_roles oer ON oer.id = uar.role_id
            WHERE uar.user_id = :user_id
            AND oer.name IN ('Site Administrator', 'Admin')
        """), {"user_id": current_user.id})

        if not admin_check.fetchone():
            raise HTTPException(
                status_code=403,
                detail="Admin access required"
            )

    # Verify target user exists
    user_check = db.execute(text("""
        SELECT id FROM users WHERE id = :user_id
    """), {"user_id": user_id})

    if not user_check.fetchone():
        raise HTTPException(status_code=404, detail="User not found")

    if not request.role_ids:
        raise HTTPException(
            status_code=400,
            detail="At least one role must be assigned"
        )

    # Verify all role IDs exist - use IN clause for database compatibility
    # Build placeholders dynamically for IN clause
    placeholders = ", ".join([f":role_id_{i}" for i in range(len(request.role_ids))])
    params = {f"role_id_{i}": role_id for i, role_id in enumerate(request.role_ids)}

    role_check = db.execute(text(f"""
        SELECT id, name FROM onboarding_roles WHERE id IN ({placeholders})
    """), params)

    valid_roles = {row.id: row.name for row in role_check}
    invalid_ids = set(request.role_ids) - set(valid_roles.keys())

    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role IDs: {list(invalid_ids)}"
        )

    # Determine primary role
    primary_role_id = request.primary_role_id
    if primary_role_id and primary_role_id not in request.role_ids:
        raise HTTPException(
            status_code=400,
            detail="Primary role must be in the assigned roles list"
        )
    if not primary_role_id:
        primary_role_id = request.role_ids[0]

    # Delete existing assignments
    db.execute(text("""
        DELETE FROM user_assigned_roles WHERE user_id = :user_id
    """), {"user_id": user_id})

    # Insert new assignments
    now = datetime.now(timezone.utc)
    for role_id in request.role_ids:
        db.execute(text("""
            INSERT INTO user_assigned_roles (user_id, role_id, assigned_at, assigned_by, is_primary)
            VALUES (:user_id, :role_id, :now, :assigned_by, :is_primary)
        """), {
            "user_id": user_id,
            "role_id": role_id,
            "now": now,
            "assigned_by": current_user.id,
            "is_primary": role_id == primary_role_id
        })

    # Set active role to primary if not already set
    try:
        db.execute(text("""
            INSERT INTO user_active_role (user_id, active_role_id, switched_at)
            VALUES (:user_id, :role_id, :now)
            ON CONFLICT (user_id) DO NOTHING
        """), {"user_id": user_id, "role_id": primary_role_id, "now": now})
    except Exception as e:
        logger.debug(f"PostgreSQL upsert failed in assign_user_roles, trying SQLite fallback: {e}")
        # SQLite fallback - check if exists first
        existing = db.execute(text("""
            SELECT 1 FROM user_active_role WHERE user_id = :user_id
        """), {"user_id": user_id}).fetchone()
        if not existing:
            db.execute(text("""
                INSERT INTO user_active_role (user_id, active_role_id, switched_at)
                VALUES (:user_id, :role_id, :now)
            """), {"user_id": user_id, "role_id": primary_role_id, "now": now})

    db.commit()

    logger.info(f"Admin {current_user.id} assigned roles {request.role_ids} to user {user_id}")

    # Build response
    assigned_roles = []
    for role_id in request.role_ids:
        assigned_roles.append(RoleInfo(
            id=role_id,
            name=valid_roles[role_id],
            is_primary=role_id == primary_role_id
        ))

    return AssignRolesResponse(
        user_id=user_id,
        assigned_roles=assigned_roles,
        message=f"Assigned {len(request.role_ids)} role(s) to user"
    )


@router.delete("/{user_id}/roles/{role_id}")
async def remove_user_role(
    user_id: int,
    role_id: int,
    current_user: UserProxy = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Remove a role from a user (admin only).

    Cannot remove the last role - user must have at least one role.
    """
    # Check if current user is admin
    if current_user.role not in ['admin', 'super_admin', 'site_admin']:
        admin_check = db.execute(text("""
            SELECT 1 FROM user_assigned_roles uar
            JOIN onboarding_roles oer ON oer.id = uar.role_id
            WHERE uar.user_id = :user_id
            AND oer.name IN ('Site Administrator', 'Admin')
        """), {"user_id": current_user.id})

        if not admin_check.fetchone():
            raise HTTPException(
                status_code=403,
                detail="Admin access required"
            )

    # Verify target user exists
    user_check = db.execute(text("""
        SELECT id FROM users WHERE id = :user_id
    """), {"user_id": user_id})

    if not user_check.fetchone():
        raise HTTPException(status_code=404, detail="User not found")

    # Check current role count
    count_result = db.execute(text("""
        SELECT COUNT(*) as cnt FROM user_assigned_roles WHERE user_id = :user_id
    """), {"user_id": user_id})

    count = count_result.fetchone().cnt
    if count <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot remove the last role. User must have at least one role."
        )

    # Check if role is assigned to user
    assignment_check = db.execute(text("""
        SELECT is_primary FROM user_assigned_roles
        WHERE user_id = :user_id AND role_id = :role_id
    """), {"user_id": user_id, "role_id": role_id})

    assignment = assignment_check.fetchone()
    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="Role not assigned to this user"
        )

    was_primary = assignment.is_primary

    # Delete the role assignment
    db.execute(text("""
        DELETE FROM user_assigned_roles
        WHERE user_id = :user_id AND role_id = :role_id
    """), {"user_id": user_id, "role_id": role_id})

    # If removed role was primary, set new primary
    if was_primary:
        db.execute(text("""
            UPDATE user_assigned_roles
            SET is_primary = TRUE
            WHERE user_id = :user_id
            AND id = (
                SELECT id FROM user_assigned_roles
                WHERE user_id = :user_id
                ORDER BY assigned_at
                LIMIT 1
            )
        """), {"user_id": user_id})

    # If removed role was active, switch to another
    active_check = db.execute(text("""
        SELECT 1 FROM user_active_role
        WHERE user_id = :user_id AND active_role_id = :role_id
    """), {"user_id": user_id, "role_id": role_id})

    if active_check.fetchone():
        # Get a remaining role
        new_active = db.execute(text("""
            SELECT role_id FROM user_assigned_roles
            WHERE user_id = :user_id
            ORDER BY is_primary DESC, assigned_at
            LIMIT 1
        """), {"user_id": user_id})

        new_role = new_active.fetchone()
        if new_role:
            now = datetime.now(timezone.utc)
            db.execute(text("""
                UPDATE user_active_role
                SET active_role_id = :new_role_id, switched_at = :now
                WHERE user_id = :user_id
            """), {"user_id": user_id, "new_role_id": new_role.role_id, "now": now})

    db.commit()

    logger.info(f"Admin {current_user.id} removed role {role_id} from user {user_id}")

    return {
        "status": "success",
        "message": "Role removed from user"
    }


# =============================================================================
# AVAILABLE ROLES ENDPOINT
# =============================================================================

@router.get("/available-roles")
async def get_available_roles(
    current_user: UserProxy = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get all available roles that can be assigned.

    Returns the list of roles from onboarding_roles table.
    """
    result = db.execute(text("""
        SELECT id, name, description
        FROM onboarding_roles
        WHERE is_active = true OR is_active IS NULL
        ORDER BY name
    """))

    roles = []
    for row in result:
        roles.append({
            "id": row.id,
            "name": row.name,
            "description": row.description
        })

    return {"roles": roles}
