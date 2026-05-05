"""
Permission System Core Routes

This module contains the core permission system functions and endpoints for the mortgage CRM.

Includes:
- Permission checking functions (has_permission, require_permission_or_403)
- Resource access checking (check_resource_access)
- Permission filter functions for leads, clients, loans, and MUM clients
- Role template application
- User permission management endpoints

These functions enforce multi-tenant isolation and role-based access control.
"""

import json
import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text, or_
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["permissions"])


# =============================================================================
# RUNTIME IMPORTS - Avoid circular imports
# =============================================================================

def _get_user_model():
    from database.models import User
    return User

def _get_lead_model():
    from database.models import Lead
    return Lead

def _get_loan_model():
    from database.models import Loan
    return Loan

def _get_mum_client_model():
    from database.models import MUMClient
    return MUMClient

def _get_audit_log_model():
    from database.models import AuditLog
    return AuditLog

def _get_current_user():
    from auth.dependencies import get_current_user
    return get_current_user


async def _current_user_dep(request: Request, db: Session = Depends(get_db)):
    """Proper FastAPI dependency that resolves to the actual user object."""
    from auth.dependencies import get_current_user
    return await get_current_user(request, db)


# =============================================================================
# CORE PERMISSION FUNCTIONS
# =============================================================================

def has_permission(user_id: int, permission_key: str, db: Session) -> bool:
    """
    Check if a user has a specific permission

    Args:
        user_id: ID of the user to check
        permission_key: Permission key (e.g., 'leads.view_all', 'clients.edit_own')
        db: Database session

    Returns:
        True if user has the permission, False otherwise
    """
    try:
        # First check explicit user_permissions table
        result = db.execute(text("""
            SELECT granted FROM user_permissions
            WHERE user_id = :user_id
              AND permission_key = :permission_key
              AND granted = TRUE
            LIMIT 1
        """), {'user_id': user_id, 'permission_key': permission_key})

        permission = result.fetchone()
        if permission is not None:
            return True

        # Fallback: Check role-based default permissions
        # Get user's permission_role and check against role defaults
        user_result = db.execute(text("""
            SELECT permission_role FROM users WHERE id = :user_id
        """), {'user_id': user_id})
        user_row = user_result.fetchone()

        if user_row and user_row[0]:
            role = user_row[0].lower()

            # Define role-based default permissions
            role_defaults = {
                'admin': True,  # Admin has all permissions
                'site_admin': True,  # Site admin has all permissions
                'leadership': {
                    'leads.view_all': True, 'leads.create': True, 'leads.edit_all': True,
                    'clients.view_all': True, 'loans.view_all': True, 'team.view_all': True,
                },
                'management': {
                    'leads.view_team': True, 'leads.create': True, 'leads.edit_own': True,
                    'clients.view_team': True, 'loans.view_team': True, 'team.view_team': True,
                },
                'sales': {
                    'leads.view_assigned': True, 'leads.edit_own': True, 'leads.create': True,
                    'clients.view_assigned': True, 'loans.view_assigned': True,
                },
                'processing': {
                    'loans.view_all': True, 'loans.process': True, 'loans.edit_documents': True,
                    'clients.view_all': True,
                },
                'operations': {
                    'leads.view_all': True, 'clients.view_all': True, 'loans.view_all': True,
                    'loans.process': True,
                },
            }

            if role in ['admin', 'site_admin']:
                return True  # Full access

            if role in role_defaults and isinstance(role_defaults[role], dict):
                return role_defaults[role].get(permission_key, False)

        return False

    except Exception as e:
        logger.error(f"Permission check error for user {user_id}, key {permission_key}: {e}")
        db.rollback()  # Rollback to recover from SQL errors
        return False


def require_permission_or_403(user_id: int, permission_key: str, db: Session) -> None:
    """
    PHASE 3: Check permission and raise 403 if not granted.

    Args:
        user_id: ID of the user to check
        permission_key: Permission key (e.g., 'leads.create', 'loans.delete')
        db: Database session

    Raises:
        HTTPException: 403 Forbidden if user lacks the permission
    """
    # Master admin (user ID 1) always has permission
    if user_id == 1:
        return

    # Check if user is an admin by permission_role - admins have full access
    try:
        result = db.execute(text("""
            SELECT permission_role FROM users WHERE id = :user_id
        """), {'user_id': user_id})
        user_row = result.fetchone()
        if user_row and user_row[0] and user_row[0].lower() == 'admin':
            return  # Admin users bypass all permission checks
    except Exception as e:
        logger.warning(f"Error checking admin status for user {user_id}: {e}")

    if not has_permission(user_id, permission_key, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission_key}"
        )


def check_resource_access(
    user_id: int,
    resource_owner_id: int,
    edit_all_permission: str,
    edit_own_permission: str,
    db: Session
) -> None:
    """
    PHASE 3: Check if user can access/modify a specific resource.

    Allows access if:
    1. User is master admin (ID 1)
    2. User has edit_all permission
    3. User has edit_own permission AND owns the resource

    Args:
        user_id: ID of the user trying to access
        resource_owner_id: ID of the user who owns the resource
        edit_all_permission: Permission key for editing all resources
        edit_own_permission: Permission key for editing own resources
        db: Database session

    Raises:
        HTTPException: 403 if user cannot access the resource
    """
    # Master admin always has access
    if user_id == 1:
        return

    # Check for edit_all permission
    if has_permission(user_id, edit_all_permission, db):
        return

    # Check for edit_own permission + ownership
    if has_permission(user_id, edit_own_permission, db):
        # Allow if user owns the resource OR if the resource has no owner (unassigned)
        if user_id == resource_owner_id or resource_owner_id is None:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only modify your own records"
        )

    raise HTTPException(status_code=403, detail="Insufficient permissions")


def get_user_permissions(user_id: int, db: Session) -> Dict[str, bool]:
    """
    Get all permissions for a user

    Returns a dictionary of permission_key -> granted
    """
    try:
        result = db.execute(text("""
            SELECT permission_key, granted
            FROM user_permissions
            WHERE user_id = :user_id
        """), {'user_id': user_id})

        permissions = {}
        for row in result:
            permissions[row[0]] = row[1]

        return permissions

    except Exception as e:
        logger.error(f"Get user permissions error for user {user_id}: {e}")
        try:
            db.rollback()  # Recover from SQL errors (e.g., missing table)
        except Exception as e:
            logger.error(f"Error during rollback in get_user_permissions: {e}")
        return {}


# =============================================================================
# PERMISSION FILTER FUNCTIONS
# =============================================================================

def filter_leads_by_permissions(query, user, db: Session):
    """
    Filter leads query based on user's permissions WITH ORGANIZATION ISOLATION.

    CRITICAL: Organization filter is ALWAYS applied first to ensure multi-tenant isolation.
    Permission filters then apply WITHIN the user's organization only.

    Returns filtered query based on:
    - Platform admin (permission_role='admin'): See all leads across all orgs
    - Master user (id=1): See all leads in their organization
    - leads.view_all: See all leads in their organization
    - leads.view_team: See team's leads in their organization
    - leads.view_assigned: See only assigned leads
    """
    Lead = _get_lead_model()

    try:
        # CRITICAL: Always start with organization filter for multi-tenant isolation
        # Platform admins can see all organizations
        is_platform_admin = getattr(user, 'permission_role', '') == 'admin'
        org_id = getattr(user, 'organization_id', None)

        if is_platform_admin:
            # Platform admin can see everything
            pass
        elif org_id:
            # Apply organization filter FIRST - this is the tenant boundary
            query = query.filter(Lead.organization_id == org_id)
        else:
            # User has no organization - can only see their own leads
            logger.warning(f"User {user.id} has no organization_id - filtering to owned leads only")
            return query.filter(Lead.owner_id == user.id)

        # Now apply permission-based filters WITHIN the organization

        # Master user can see all leads in their org (check both ID and email)
        if user.id == 1 or user.email == 'admin@perenniaai.com':
            return query

        if has_permission(user.id, 'leads.view_all', db):
            # Management: See all leads in their organization
            return query

        if has_permission(user.id, 'leads.view_team', db):
            # Team Lead: See team's leads within their organization
            team_id = getattr(user, 'team_id', None)
            if team_id:
                # Get all team member IDs in the same organization
                team_member_ids = db.execute(text("""
                    SELECT id FROM users
                    WHERE team_id = :team_id AND organization_id = :org_id
                """), {"team_id": team_id, "org_id": org_id}).fetchall()
                team_ids = [m[0] for m in team_member_ids]
                if team_ids:
                    return query.filter(Lead.owner_id.in_(team_ids))
            # If no team, fall back to own leads
            return query.filter(Lead.owner_id == user.id)

        if has_permission(user.id, 'leads.view_assigned', db):
            # Sales: See only their assigned leads
            return query.filter(Lead.owner_id == user.id)

        # Default: Show leads owned by the user (backwards compatibility)
        return query.filter(Lead.owner_id == user.id)
    except Exception as e:
        logger.error(f"Permission filter error: {e}")
        # Fallback: return leads owned by user
        return query.filter(Lead.owner_id == user.id)


def filter_clients_by_permissions(query, user, db: Session):
    """
    Filter clients query based on user's permissions WITH ORGANIZATION ISOLATION.

    CRITICAL: Organization filter is ALWAYS applied first to ensure multi-tenant isolation.

    Returns filtered query based on:
    - Platform admin: See all clients across all orgs
    - clients.view_all: See all clients in their organization
    - clients.view_team: See team's clients in their organization
    - clients.view_assigned: See only assigned clients
    """
    User = _get_user_model()

    try:
        # CRITICAL: Always start with organization filter for multi-tenant isolation
        is_platform_admin = getattr(user, 'permission_role', '') == 'admin'
        org_id = getattr(user, 'organization_id', None)

        entity = query.column_descriptions[0]['entity'] if query.column_descriptions else None

        if is_platform_admin:
            # Platform admin can see everything
            pass
        elif org_id and entity and hasattr(entity, 'organization_id'):
            # Apply organization filter FIRST
            query = query.filter(entity.organization_id == org_id)
        elif org_id and entity and hasattr(entity, 'user_id'):
            # For MUMClient which uses user_id, filter by users in this org
            query = query.filter(entity.user_id.in_(
                db.query(User.id).filter(User.organization_id == org_id)
            ))

        if has_permission(user.id, 'clients.view_all', db):
            # Management/Operations: See all clients in their organization
            return query

        if has_permission(user.id, 'clients.view_team', db):
            # Team Lead: See team's clients (clients owned by team members)
            team_id = getattr(user, 'team_id', None)
            if team_id:
                team_member_ids = db.execute(text("""
                    SELECT id FROM users WHERE team_id = :team_id AND organization_id = :org_id
                """), {"team_id": team_id, "org_id": org_id}).fetchall()
                team_ids = [m[0] for m in team_member_ids]
                if team_ids and entity and hasattr(entity, 'owner_id'):
                    return query.filter(entity.owner_id.in_(team_ids))
            return query  # Fall back to all if no team filtering possible

        if has_permission(user.id, 'clients.view_assigned', db):
            # See only assigned clients
            if entity and hasattr(entity, 'owner_id'):
                return query.filter(entity.owner_id == user.id)
            elif entity and hasattr(entity, 'user_id'):
                return query.filter(entity.user_id == user.id)
            return query  # Fall back if no owner_id/user_id column

        # Default: Return all clients in organization (backwards compatibility)
        return query
    except Exception as e:
        logger.error(f"Client permission filter error: {e}")
        return query


def filter_loans_by_permissions(query, user, db: Session):
    """
    Filter loans query based on user's permissions WITH ORGANIZATION ISOLATION.

    CRITICAL: Organization filter is ALWAYS applied first to ensure multi-tenant isolation.

    Returns filtered query based on:
    - Platform admin: See all loans across all orgs
    - loans.view_all: See all loans in their organization
    - loans.view_team: See team's loans in their organization
    - loans.view_assigned: See only assigned loans (where user is loan_officer)

    Default behavior (no permissions set): Show assigned loans + unassigned loans in org
    """
    Loan = _get_loan_model()

    try:
        # CRITICAL: Always start with organization filter for multi-tenant isolation
        is_platform_admin = getattr(user, 'permission_role', '') == 'admin'
        org_id = getattr(user, 'organization_id', None)

        if is_platform_admin:
            # Platform admin can see everything
            pass
        elif org_id:
            # Apply organization filter FIRST - this is the tenant boundary
            query = query.filter(Loan.organization_id == org_id)
        else:
            # User has no organization - can only see their own loans
            logger.warning(f"User {user.id} has no organization_id - filtering to assigned loans only")
            return query.filter(Loan.loan_officer_id == user.id)

        if has_permission(user.id, 'loans.view_all', db):
            # Management/Operations: See all loans in their organization
            return query

        if has_permission(user.id, 'loans.view_team', db):
            # Team Lead: See team's loans + unassigned loans within organization
            team_id = getattr(user, 'team_id', None)
            if team_id:
                team_member_ids = db.execute(text("""
                    SELECT id FROM users WHERE team_id = :team_id AND organization_id = :org_id
                """), {"team_id": team_id, "org_id": org_id}).fetchall()
                team_ids = [m[0] for m in team_member_ids]
                if team_ids:
                    return query.filter(or_(
                        Loan.loan_officer_id.in_(team_ids),
                        Loan.loan_officer_id.is_(None)  # Include unassigned loans in org
                    ))
            return query.filter(or_(
                Loan.loan_officer_id == user.id,
                Loan.loan_officer_id.is_(None)  # Include unassigned loans in org
            ))

        # Default: Show loans where user is the loan officer OR unassigned (in their org)
        return query.filter(or_(
            Loan.loan_officer_id == user.id,
            Loan.loan_officer_id.is_(None)  # Include unassigned loans in org
        ))
    except Exception as e:
        logger.error(f"Loan permission filter error: {e}")
        return query.filter(or_(
            Loan.loan_officer_id == user.id,
            Loan.loan_officer_id.is_(None)
        ))


def filter_mum_clients_by_permissions(query, user, db: Session):
    """
    PHASE 3: Filter MUM clients query based on user's permissions WITH ORGANIZATION ISOLATION.

    MUM Clients use 'user_id' field for ownership (not 'owner_id').

    CRITICAL: Organization filter is ALWAYS applied first to ensure multi-tenant isolation.

    Returns filtered query based on:
    - Platform admin: See all clients across all orgs
    - Master user (id=1): See all clients in their organization
    - clients.view_all: See all clients in their organization
    - clients.view_team: See team's clients in their organization
    - Default: See only own clients (user_id == current user)
    """
    MUMClient = _get_mum_client_model()

    try:
        # CRITICAL: Always start with organization filter for multi-tenant isolation
        is_platform_admin = getattr(user, 'permission_role', '') == 'admin'
        org_id = getattr(user, 'organization_id', None)

        if is_platform_admin:
            # Platform admin can see everything
            pass
        elif org_id:
            # Apply organization filter FIRST - this is the tenant boundary
            query = query.filter(MUMClient.organization_id == org_id)
        else:
            # User has no organization - can only see their own clients
            logger.warning(f"User {user.id} has no organization_id - filtering to owned clients only")
            return query.filter(MUMClient.user_id == user.id)

        # Master user can see all in their org
        if user.id == 1:
            return query

        if has_permission(user.id, 'clients.view_all', db):
            return query

        if has_permission(user.id, 'clients.view_team', db):
            team_id = getattr(user, 'team_id', None)
            if team_id:
                team_member_ids = db.execute(text("""
                    SELECT id FROM users WHERE team_id = :team_id AND organization_id = :org_id
                """), {"team_id": team_id, "org_id": org_id}).fetchall()
                team_ids = [m[0] for m in team_member_ids]
                if team_ids:
                    return query.filter(MUMClient.user_id.in_(team_ids))
            return query.filter(MUMClient.user_id == user.id)

        # Default: Show only clients owned by the user
        return query.filter(MUMClient.user_id == user.id)
    except Exception as e:
        logger.error(f"MUM client permission filter error: {e}")
        return query.filter(MUMClient.user_id == user.id)


# =============================================================================
# ROLE TEMPLATE FUNCTIONS
# =============================================================================

def apply_role_template_to_user(user_id: int, role_name: str, granted_by_id: int, db: Session) -> bool:
    """
    Apply a permission template to a user based on their role

    Args:
        user_id: User to apply template to
        role_name: 'management', 'sales', or 'operations'
        granted_by_id: ID of user granting the permissions
        db: Database session

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get template by category (role name)
        result = db.execute(text("""
            SELECT id, name, permissions
            FROM permission_templates
            WHERE category = :role_name
              AND is_system_default = TRUE
            LIMIT 1
        """), {'role_name': role_name})

        template = result.fetchone()
        if not template:
            logger.error(f"No template found for role: {role_name}")
            return False

        template_id, template_name, permissions_json = template
        permissions = json.loads(permissions_json) if isinstance(permissions_json, str) else permissions_json

        # Delete existing permissions for this user
        db.execute(text("""
            DELETE FROM user_permissions WHERE user_id = :user_id
        """), {'user_id': user_id})

        # Insert new permissions from template
        for perm_key, granted in permissions.items():
            db.execute(text("""
                INSERT INTO user_permissions
                (user_id, permission_key, granted, granted_by, inherited_from)
                VALUES (:user_id, :perm_key, :granted, :granted_by, 'template')
            """), {
                'user_id': user_id,
                'perm_key': perm_key,
                'granted': granted,
                'granted_by': granted_by_id
            })

        # Update user's permission_role
        db.execute(text("""
            UPDATE users
            SET permission_role = :role_name
            WHERE id = :user_id
        """), {'user_id': user_id, 'role_name': role_name})

        db.commit()
        logger.info(f"Applied {template_name} template to user {user_id} ({len(permissions)} permissions)")
        return True

    except Exception as e:
        logger.error(f"Apply template error: {e}")
        db.rollback()
        return False


# =============================================================================
# PERMISSION ENDPOINTS
# =============================================================================

@router.post("/users/{user_id}/assign-role")
async def assign_role_to_user(
    user_id: int,
    role: str,
    current_user = Depends(_current_user_dep),
    db: Session = Depends(get_db)
):
    """
    Assign a permission role to a user and apply the corresponding template

    Requires: team.manage_permissions or permissions.manage
    """
    User = _get_user_model()

    try:
        # Check if current user has permission to manage permissions
        if not has_permission(current_user.id, 'permissions.manage', db):
            if not has_permission(current_user.id, 'team.manage_permissions', db):
                raise HTTPException(status_code=403, detail="You don't have permission to manage user roles")

        # Validate role
        if role not in ['management', 'sales', 'operations']:
            raise HTTPException(status_code=400, detail="Invalid role. Must be: management, sales, or operations")

        # Check if user exists
        target_user = db.query(User).filter(User.id == user_id).first()
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Apply template
        success = apply_role_template_to_user(user_id, role, current_user.id, db)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to apply role template")

        return {
            "success": True,
            "message": f"Successfully assigned {role} role to {target_user.email}",
            "user_id": user_id,
            "role": role
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Assign role error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users/{user_id}/permissions")
async def get_user_permissions_endpoint(
    user_id: int,
    current_user = Depends(_current_user_dep),
    db: Session = Depends(get_db)
):
    """
    Get all permissions for a user

    Users can view their own permissions, or if they have permissions.view_all
    """
    User = _get_user_model()

    try:
        # Check if requesting own permissions or has permission to view all
        if user_id != current_user.id:
            if not has_permission(current_user.id, 'permissions.view_all', db):
                raise HTTPException(status_code=403, detail="You can only view your own permissions")

        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Auto-fix admin permission_role if user is admin but doesn't have correct permission_role
        # This handles: admin@perenniaai.com, users with is_admin=True, or role='admin'
        current_permission_role = getattr(user, 'permission_role', None)
        if current_permission_role not in ('admin', 'site_admin'):
            is_admin_user = (
                user.email == 'admin@perenniaai.com' or
                getattr(user, 'is_admin', False) or
                getattr(user, 'role', '') == 'admin'
            )
            if is_admin_user and hasattr(user, 'permission_role'):
                try:
                    user.permission_role = 'admin'
                    db.commit()
                    logger.info(f"Auto-fixed permission_role to 'admin' for user {user.email}")
                except Exception as e:
                    logger.warning(f"Could not auto-fix permission_role: {e}")
                    db.rollback()

        # Get permissions (handles missing table gracefully)
        permissions = get_user_permissions(user_id, db)

        # Safe access to permission_role (might not exist as column)
        permission_role = getattr(user, 'permission_role', None) or 'sales'

        return {
            "user_id": user_id,
            "email": user.email,
            "permission_role": permission_role,
            "permissions": permissions,
            "permission_count": len(permissions)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get permissions error: {e}")
        # Return empty permissions on error instead of 500
        return {
            "user_id": user_id,
            "email": current_user.email if current_user else "unknown",
            "permission_role": "sales",
            "permissions": {},
            "permission_count": 0,
            "error": "Could not fetch permissions"
        }


@router.get("/permissions/templates")
async def get_permission_templates(
    current_user = Depends(_current_user_dep),
    db: Session = Depends(get_db)
):
    """
    Get all available permission templates

    Requires: permissions.view_all or team.manage_permissions
    """
    try:
        # Check permission
        if not has_permission(current_user.id, 'permissions.view_all', db):
            if not has_permission(current_user.id, 'team.manage_permissions', db):
                raise HTTPException(status_code=403, detail="Access denied")

        # Get templates
        result = db.execute(text("""
            SELECT id, name, description, category, permissions, is_system_default
            FROM permission_templates
            ORDER BY is_system_default DESC, name
        """))

        templates = []
        for row in result:
            perms = json.loads(row[4]) if isinstance(row[4], str) else row[4]
            templates.append({
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "category": row[3],
                "permission_count": len(perms),
                "is_system_default": row[5]
            })

        return {
            "templates": templates,
            "count": len(templates)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get templates error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users/{user_id}/permissions/template")
async def get_user_permission_template(
    user_id: int,
    current_user = Depends(_current_user_dep),
    db: Session = Depends(get_db)
):
    """
    Get the current permission template assigned to a user

    Returns the template name/category currently assigned
    """
    User = _get_user_model()

    try:
        # Check permission
        if not has_permission(current_user.id, 'team.manage_permissions', db):
            raise HTTPException(status_code=403, detail="Access denied")

        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "user_id": user_id,
            "email": user.email,
            "template": user.permission_role,
            "template_display": user.permission_role.title() if user.permission_role else "None"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user template error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/permissions/available")
async def get_available_permissions(
    current_user = Depends(_current_user_dep),
    db: Session = Depends(get_db)
):
    """
    Get all available permissions with descriptions and categories

    Returns a structured list of all permissions in the system
    NOTE: This endpoint is accessible to all authenticated users so they can see what permissions exist
    """
    try:
        # Define all available permissions organized by category
        permissions = {
            "dashboard_widgets": {
                "name": "Dashboard Widgets",
                "permissions": {
                    "dashboard.view_all_widgets": "View all dashboard widgets",
                    "dashboard.view_production_tracker": "View production tracker widget",
                    "dashboard.view_efficiency_monitor": "View loan efficiency monitor widget",
                    "dashboard.view_referral_scoreboard": "View referral scoreboard widget",
                    "dashboard.view_team_performance": "View team performance metrics widget",
                    "dashboard.customize": "Customize dashboard layout",
                    "dashboard.export": "Export dashboard data"
                }
            },
            "navigation": {
                "name": "Navigation Tabs",
                "permissions": {
                    "reports.view_scorecard": "Access Scorecard tab",
                    "partners.view": "Access Partners tab",
                    "team.view_all": "Access Team Members tab",
                    "reports.view_all": "Access Reports tab"
                }
            },
            "leads": {
                "name": "Leads Management",
                "permissions": {
                    "leads.view_all": "View all leads",
                    "leads.view_team": "View team's leads",
                    "leads.view_assigned": "View only assigned leads",
                    "leads.create": "Create new leads",
                    "leads.edit_all": "Edit any lead",
                    "leads.edit_own": "Edit own leads only",
                    "leads.delete": "Delete leads",
                    "leads.assign": "Assign leads to others",
                    "leads.export": "Export lead data"
                }
            },
            "clients": {
                "name": "Client Management",
                "permissions": {
                    "clients.view_all": "View all clients",
                    "clients.view_assigned": "View assigned clients only",
                    "clients.create": "Create clients",
                    "clients.edit_all": "Edit any client",
                    "clients.edit_own": "Edit own clients only",
                    "clients.delete": "Delete clients",
                    "clients.export": "Export client data"
                }
            },
            "loans": {
                "name": "Loan Management",
                "permissions": {
                    "loans.view_all": "View all loans",
                    "loans.view_assigned": "View assigned loans only",
                    "loans.create": "Create loans",
                    "loans.edit_all": "Edit any loan",
                    "loans.edit_own": "Edit own loans only",
                    "loans.delete": "Delete loans",
                    "loans.process": "Process loans (operations)",
                    "loans.export": "Export loan data"
                }
            },
            "team": {
                "name": "Team Management",
                "permissions": {
                    "team.view_all": "View all team members",
                    "team.view_team": "View own team",
                    "team.edit_members": "Edit team member profiles",
                    "team.manage_permissions": "Manage team permissions",
                    "team.impersonate": "Impersonate team members",
                    "team.view_performance": "View team performance metrics"
                }
            },
            "reports": {
                "name": "Reports & Analytics",
                "permissions": {
                    "reports.view_all": "View all reports",
                    "reports.view_sales": "View sales reports",
                    "reports.view_operations": "View operations reports",
                    "reports.export": "Export report data",
                    "analytics.view_all": "View all analytics",
                    "analytics.export": "Export analytics data"
                }
            },
            "settings": {
                "name": "Settings & Administration",
                "permissions": {
                    "settings.view": "View settings",
                    "settings.edit": "Edit settings",
                    "permissions.view_all": "View all user permissions",
                    "permissions.manage": "Manage permissions and assign roles"
                }
            },
            "tasks": {
                "name": "Tasks & Workflows",
                "permissions": {
                    "tasks.view_all": "View all tasks",
                    "tasks.view_team": "View team tasks",
                    "tasks.view_assigned": "View assigned tasks",
                    "tasks.create": "Create tasks",
                    "tasks.edit_all": "Edit any task",
                    "tasks.delete": "Delete tasks"
                }
            }
        }

        # Flatten permissions for frontend compatibility
        # Frontend expects: { permissions: { key: { name, description, category } } }
        flattened_permissions = {}
        for category_key, category_data in permissions.items():
            category_name = category_data["name"]
            for perm_key, perm_description in category_data["permissions"].items():
                flattened_permissions[perm_key] = {
                    "name": perm_key.replace('.', ' ').replace('_', ' ').title(),
                    "description": perm_description,
                    "category": category_name
                }

        return {
            "permissions": flattened_permissions,
            "categories": permissions,  # Keep for backwards compatibility
            "total_permissions": sum(len(cat["permissions"]) for cat in permissions.values())
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get available permissions error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/users/{user_id}/permissions/apply-template")
async def apply_permission_template(
    user_id: int,
    template_data: dict,
    current_user = Depends(_current_user_dep),
    db: Session = Depends(get_db)
):
    """
    Apply a permission template to a user

    Body: { "template": "sales" | "operations" | "management" }
    Returns: Updated permissions and diff of changes
    """
    User = _get_user_model()
    AuditLog = _get_audit_log_model()

    try:
        # Check permission
        if not has_permission(current_user.id, 'team.manage_permissions', db):
            raise HTTPException(status_code=403, detail="Access denied")

        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        template_name = template_data.get("template")
        if not template_name:
            raise HTTPException(status_code=400, detail="Template name required")

        # Get current permissions before applying template
        old_permissions = get_user_permissions(user_id, db)

        # Apply template
        success = apply_role_template_to_user(user_id, template_name, current_user.id, db)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to apply template")

        # Get new permissions after applying template
        new_permissions = get_user_permissions(user_id, db)

        # Calculate diff
        added = {k: v for k, v in new_permissions.items() if k not in old_permissions or not old_permissions[k]}
        removed = {k: v for k, v in old_permissions.items() if k not in new_permissions or not new_permissions[k]}
        unchanged = {k: v for k, v in new_permissions.items() if k in old_permissions and old_permissions[k] == v}

        # Log to audit log
        audit_entry = AuditLog(
            user_id=user_id,
            changed_by_id=current_user.id,
            change_type="permission_template",
            entity_type="user_permissions",
            entity_id=user_id,
            before_state={"permissions": old_permissions},
            after_state={
                "permissions": new_permissions,
                "template_applied": template_name,
                "added": list(added.keys()),
                "removed": list(removed.keys())
            },
            reason=f"Applied {template_name} permission template"
        )
        db.add(audit_entry)
        db.commit()

        logger.info(f"Applied {template_name} template to user {user_id} by {current_user.email}")

        return {
            "success": True,
            "message": f"Successfully applied {template_name} template",
            "user_id": user_id,
            "template": template_name,
            "permissions": new_permissions,
            "diff": {
                "added": list(added.keys()),
                "removed": list(removed.keys()),
                "unchanged": list(unchanged.keys()),
                "added_count": len(added),
                "removed_count": len(removed)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Apply template error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: int,
    permission_data: dict,
    current_user = Depends(_current_user_dep),
    db: Session = Depends(get_db)
):
    """
    Update individual permissions for a user

    Body: { "permissions": { "leads.view_all": true, "leads.edit_all": false, ... } }
    """
    User = _get_user_model()
    AuditLog = _get_audit_log_model()

    try:
        # Check permission
        if not has_permission(current_user.id, 'team.manage_permissions', db):
            raise HTTPException(status_code=403, detail="Access denied")

        # Get user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        permissions = permission_data.get("permissions", {})
        if not permissions:
            raise HTTPException(status_code=400, detail="Permissions object required")

        # Get current permissions
        old_permissions = get_user_permissions(user_id, db)

        # Update each permission
        for permission_key, granted in permissions.items():
            # Insert or update permission
            db.execute(text("""
                INSERT INTO user_permissions (user_id, permission_key, granted, granted_by, granted_at, inherited_from)
                VALUES (:user_id, :permission_key, :granted, :granted_by, CURRENT_TIMESTAMP, 'manual')
                ON CONFLICT (user_id, permission_key) DO UPDATE
                SET granted = :granted, granted_by = :granted_by, granted_at = CURRENT_TIMESTAMP
            """), {
                'user_id': user_id,
                'permission_key': permission_key,
                'granted': granted,
                'granted_by': current_user.id
            })

        db.commit()

        # Get updated permissions
        new_permissions = get_user_permissions(user_id, db)

        # Calculate changes
        changes = []
        for key in set(list(old_permissions.keys()) + list(new_permissions.keys())):
            old_val = old_permissions.get(key, False)
            new_val = new_permissions.get(key, False)
            if old_val != new_val:
                changes.append({
                    "permission": key,
                    "old_value": old_val,
                    "new_value": new_val
                })

        # Log to audit log
        if changes:
            audit_entry = AuditLog(
                user_id=user_id,
                changed_by_id=current_user.id,
                change_type="permission_update",
                entity_type="user_permissions",
                entity_id=user_id,
                before_state={"permissions": old_permissions},
                after_state={"permissions": new_permissions, "changes": changes},
                reason=f"Updated {len(changes)} permissions"
            )
            db.add(audit_entry)
            db.commit()

        logger.info(f"Updated permissions for user {user_id} by {current_user.email}. Changes: {len(changes)}")

        return {
            "success": True,
            "message": f"Successfully updated {len(changes)} permissions",
            "user_id": user_id,
            "permissions": new_permissions,
            "changes": changes,
            "changes_count": len(changes)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update permissions error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
