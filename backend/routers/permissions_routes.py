"""
Perennia AI - Stage-Based Permissions API Routes

This module provides API endpoints for the stage-based permission system including:
- Stage access management (Lead, Active Loan, Portfolio)
- Permission template operations
- Individual permission checks and overrides
- Permission request workflows
- Subscription management
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import json

from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/api/v1/permissions", tags=["permissions"])


def _authorize_user_access(current_user: dict, target_user_id: int, db: Session) -> None:
    """Verify current_user can access target_user_id's permission data.

    Allows self-access or users with team.manage_permissions.
    """
    if current_user.get("id") == target_user_id:
        return
    has_perm = db.execute(text(
        "SELECT user_has_permission(:actor_id, 'team.manage_permissions')"
    ), {"actor_id": current_user["id"]}).scalar()
    if not has_perm:
        raise HTTPException(status_code=403, detail="Not authorized to view other users' permissions")

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class LoanStageResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str]
    display_order: int
    icon: Optional[str]
    color: Optional[str]
    is_active: bool

class PermissionDefinitionResponse(BaseModel):
    id: int
    key: str
    stage_code: Optional[str]
    category: str
    name: str
    description: Optional[str]
    requires_subscription: bool
    risk_level: str
    display_order: int
    group_name: Optional[str]
    is_active: bool

class PermissionTemplateResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str]
    stage_code: Optional[str]
    role_type: str
    permissions: Dict[str, bool]
    default_scope: str
    is_system_default: bool
    is_active: bool
    display_order: int

class UserStageAccessResponse(BaseModel):
    id: int
    user_id: int
    stage_code: str
    access_type: str
    template_id: Optional[int]
    template: Optional[PermissionTemplateResponse]
    data_scope: str
    is_active: bool
    granted_at: datetime
    granted_by: Optional[int]
    expires_at: Optional[datetime]

class PermissionOverrideResponse(BaseModel):
    id: int
    user_id: int
    permission_key: str
    granted: bool
    scope_override: Optional[str]
    is_temporary: bool
    expires_at: Optional[datetime]
    reason: Optional[str]
    granted_by: int
    granted_at: datetime

class UserPermissionProfileResponse(BaseModel):
    user_id: int
    email: str
    stage_access: List[UserStageAccessResponse]
    enabled_stages: List[str]
    permissions: Dict[str, bool]
    permission_count: int
    overrides: List[PermissionOverrideResponse]

class GrantStageAccessRequest(BaseModel):
    stage_code: str = Field(..., max_length=50)
    template_code: Optional[str] = Field(None, max_length=50)
    data_scope: Optional[str] = Field("assigned", max_length=50)
    expires_at: Optional[datetime] = None
    reason: Optional[str] = Field(None, max_length=2000)

class ApplyTemplateRequest(BaseModel):
    template_code: str

class UpdateDataScopeRequest(BaseModel):
    data_scope: str

class AddOverrideRequest(BaseModel):
    permission_key: str = Field(..., max_length=100)
    granted: bool
    scope_override: Optional[str] = Field(None, max_length=50)
    is_temporary: bool = False
    expires_at: Optional[datetime] = None
    reason: Optional[str] = Field(None, max_length=2000)

class PermissionRequestCreate(BaseModel):
    request_type: str = Field(..., max_length=50)  # 'stage_access', 'permission', 'template_change', 'scope_upgrade'
    stage_code: Optional[str] = Field(None, max_length=50)
    permission_key: Optional[str] = Field(None, max_length=100)
    template_id: Optional[int] = None
    requested_scope: Optional[str] = Field(None, max_length=50)
    justification: str = Field(..., min_length=50, max_length=5000)
    urgency: str = Field("medium", max_length=20)
    is_temporary: bool = False
    duration_days: Optional[int] = None

class PermissionRequestResponse(BaseModel):
    id: int
    user_id: int
    request_type: str
    stage_code: Optional[str]
    permission_key: Optional[str]
    template_id: Optional[int]
    requested_scope: Optional[str]
    justification: str
    urgency: str
    is_temporary: bool
    duration_days: Optional[int]
    status: str
    reviewed_by: Optional[int]
    reviewed_at: Optional[datetime]
    review_notes: Optional[str]
    created_at: datetime
    updated_at: datetime

class ApproveRequestPayload(BaseModel):
    notes: Optional[str] = Field(None, max_length=2000)

class DenyRequestPayload(BaseModel):
    reason: str = Field(..., max_length=2000)

class MoreInfoRequestPayload(BaseModel):
    questions: str = Field(..., max_length=5000)

# ============================================================================
# STAGE MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/stages", response_model=Dict[str, List[LoanStageResponse]])
async def get_stages(db: Session = Depends(get_db)):
    """Get all available loan stages."""
    result = db.execute(text("""
        SELECT id, code, name, description, display_order, icon, color, is_active
        FROM loan_stages
        WHERE is_active = TRUE
        ORDER BY display_order
    """))

    stages = []
    for row in result:
        stages.append(LoanStageResponse(
            id=row.id,
            code=row.code,
            name=row.name,
            description=row.description,
            display_order=row.display_order,
            icon=row.icon,
            color=row.color,
            is_active=row.is_active
        ))

    return {"stages": stages}


@router.get("/stages/enabled")
async def get_enabled_stages(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get stages enabled for the current organization's subscription."""
    # Get organization subscription
    result = db.execute(text("""
        SELECT os.enabled_stages, st.stages as tier_stages
        FROM organization_subscriptions os
        LEFT JOIN subscription_tiers st ON st.id = os.subscription_tier_id
        WHERE os.organization_id = :org_id AND os.status = 'active'
    """), {"org_id": current_user.get("organization_id", 1)})

    row = result.fetchone()
    if row:
        # Use custom enabled_stages if set, otherwise use tier default
        enabled_stages = row.enabled_stages if row.enabled_stages else row.tier_stages
        return {"enabled_stages": enabled_stages or []}

    # Default to all stages if no subscription found
    return {"enabled_stages": ["lead", "active_loan", "portfolio"]}


@router.get("/users/{user_id}/stages/{stage_code}/access")
async def check_stage_access(
    user_id: int,
    stage_code: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if user has access to a specific stage."""
    result = db.execute(text("""
        SELECT id FROM user_stage_access
        WHERE user_id = :user_id
        AND stage_code = :stage_code
        AND is_active = TRUE
        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
    """), {"user_id": user_id, "stage_code": stage_code})

    return {"has_access": result.fetchone() is not None}


# ============================================================================
# PERMISSION DEFINITIONS
# ============================================================================

@router.get("/definitions")
async def get_permission_definitions(
    stage_code: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all permission definitions, optionally filtered by stage or category."""
    query = """
        SELECT id, key, stage_code, category, name, description,
               requires_subscription, risk_level, display_order, group_name, is_active
        FROM permission_definitions
        WHERE is_active = TRUE
    """
    params = {}

    if stage_code:
        query += " AND (stage_code = :stage_code OR stage_code IS NULL)"
        params["stage_code"] = stage_code

    if category:
        query += " AND category = :category"
        params["category"] = category

    query += " ORDER BY stage_code NULLS LAST, display_order"

    result = db.execute(text(query), params)

    permissions = []
    for row in result:
        permissions.append({
            "id": row.id,
            "key": row.key,
            "stage_code": row.stage_code,
            "category": row.category,
            "name": row.name,
            "description": row.description,
            "requires_subscription": row.requires_subscription,
            "risk_level": row.risk_level,
            "display_order": row.display_order,
            "group_name": row.group_name,
            "is_active": row.is_active
        })

    return {"permissions": permissions}


@router.get("/definitions/grouped")
async def get_grouped_permissions(db: Session = Depends(get_db)):
    """Get permission definitions grouped by stage and category."""
    # Get stages
    stages_result = db.execute(text("""
        SELECT id, code, name, description, display_order, icon, color, is_active
        FROM loan_stages WHERE is_active = TRUE
        ORDER BY display_order
    """))
    stages = {row.code: dict(row._mapping) for row in stages_result}

    # Get permissions
    perms_result = db.execute(text("""
        SELECT id, key, stage_code, category, name, description,
               requires_subscription, risk_level, display_order, group_name, is_active
        FROM permission_definitions
        WHERE is_active = TRUE
        ORDER BY stage_code NULLS LAST, category, display_order
    """))

    # Group by stage, then by category
    groups = {}
    for row in perms_result:
        stage_key = row.stage_code or "global"
        if stage_key not in groups:
            groups[stage_key] = {
                "stage": stages.get(row.stage_code) if row.stage_code else None,
                "categories": {}
            }

        if row.category not in groups[stage_key]["categories"]:
            groups[stage_key]["categories"][row.category] = []

        groups[stage_key]["categories"][row.category].append({
            "id": row.id,
            "key": row.key,
            "name": row.name,
            "description": row.description,
            "risk_level": row.risk_level
        })

    # Convert to list format
    result = []
    for stage_key in ["lead", "active_loan", "portfolio", "global"]:
        if stage_key in groups:
            group = groups[stage_key]
            result.append({
                "stage": group["stage"],
                "categories": [
                    {"name": cat, "permissions": perms}
                    for cat, perms in group["categories"].items()
                ]
            })

    return {"groups": result}


# ============================================================================
# PERMISSION TEMPLATES
# ============================================================================

@router.get("/templates")
async def get_templates(
    stage_code: Optional[str] = None,
    role_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get permission templates, optionally filtered by stage or role type."""
    query = """
        SELECT id, code, name, description, stage_code, role_type,
               permissions, default_scope, is_system_default, is_active, display_order
        FROM stage_permission_templates
        WHERE is_active = TRUE
    """
    params = {}

    if stage_code:
        query += " AND stage_code = :stage_code"
        params["stage_code"] = stage_code

    if role_type:
        query += " AND role_type = :role_type"
        params["role_type"] = role_type

    query += " ORDER BY stage_code, display_order"

    result = db.execute(text(query), params)

    templates = []
    for row in result:
        templates.append({
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "description": row.description,
            "stage_code": row.stage_code,
            "role_type": row.role_type,
            "permissions": row.permissions,
            "default_scope": row.default_scope,
            "is_system_default": row.is_system_default,
            "is_active": row.is_active,
            "display_order": row.display_order
        })

    return {"templates": templates}


@router.get("/templates/stage/{stage_code}")
async def get_stage_templates(stage_code: str, db: Session = Depends(get_db)):
    """Get templates for a specific stage."""
    result = db.execute(text("""
        SELECT id, code, name, description, stage_code, role_type,
               permissions, default_scope, is_system_default, is_active, display_order
        FROM stage_permission_templates
        WHERE stage_code = :stage_code AND is_active = TRUE
        ORDER BY display_order
    """), {"stage_code": stage_code})

    templates = [dict(row._mapping) for row in result]
    return {"templates": templates}


@router.get("/templates/{code}")
async def get_template_by_code(code: str, db: Session = Depends(get_db)):
    """Get a specific template by code."""
    result = db.execute(text("""
        SELECT id, code, name, description, stage_code, role_type,
               permissions, default_scope, is_system_default, is_active, display_order
        FROM stage_permission_templates
        WHERE code = :code
    """), {"code": code})

    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")

    return {"template": dict(row._mapping)}


# ============================================================================
# USER PERMISSIONS
# ============================================================================

@router.get("/users/{user_id}/profile")
async def get_user_permission_profile(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's complete permission profile."""
    # Check authorization
    if current_user["id"] != user_id:
        # Check if current user has permission to view others' permissions
        has_perm = db.execute(text("""
            SELECT user_has_permission(:actor_id, 'team.manage_permissions')
        """), {"actor_id": current_user["id"]}).scalar()
        if not has_perm:
            raise HTTPException(status_code=403, detail="Not authorized to view this user's permissions")

    # Get user info
    user_result = db.execute(text("""
        SELECT id, email FROM users WHERE id = :user_id
    """), {"user_id": user_id})
    user = user_result.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get stage access
    stage_access_result = db.execute(text("""
        SELECT usa.id, usa.user_id, usa.stage_code, usa.access_type,
               usa.template_id, usa.data_scope, usa.is_active,
               usa.granted_at, usa.granted_by, usa.expires_at,
               spt.code as template_code, spt.name as template_name,
               spt.permissions as template_permissions
        FROM user_stage_access usa
        LEFT JOIN stage_permission_templates spt ON spt.id = usa.template_id
        WHERE usa.user_id = :user_id AND usa.is_active = TRUE
        AND (usa.expires_at IS NULL OR usa.expires_at > CURRENT_TIMESTAMP)
    """), {"user_id": user_id})

    stage_access = []
    enabled_stages = []
    all_permissions = {}

    for row in stage_access_result:
        stage_access.append({
            "id": row.id,
            "user_id": row.user_id,
            "stage_code": row.stage_code,
            "access_type": row.access_type,
            "template_id": row.template_id,
            "template": {
                "code": row.template_code,
                "name": row.template_name
            } if row.template_id else None,
            "data_scope": row.data_scope,
            "is_active": row.is_active,
            "granted_at": row.granted_at.isoformat() if row.granted_at else None,
            "granted_by": row.granted_by,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None
        })
        enabled_stages.append(row.stage_code)

        # Merge template permissions
        if row.template_permissions:
            all_permissions.update(row.template_permissions)

    # Get overrides
    overrides_result = db.execute(text("""
        SELECT id, user_id, permission_key, granted, scope_override,
               is_temporary, expires_at, reason, granted_by, granted_at
        FROM user_permission_overrides
        WHERE user_id = :user_id
        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
    """), {"user_id": user_id})

    overrides = []
    for row in overrides_result:
        overrides.append({
            "id": row.id,
            "user_id": row.user_id,
            "permission_key": row.permission_key,
            "granted": row.granted,
            "scope_override": row.scope_override,
            "is_temporary": row.is_temporary,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "reason": row.reason,
            "granted_by": row.granted_by,
            "granted_at": row.granted_at.isoformat() if row.granted_at else None
        })
        # Apply override to permissions
        all_permissions[row.permission_key] = row.granted

    return {
        "user_id": user.id,
        "email": user.email,
        "stage_access": stage_access,
        "enabled_stages": enabled_stages,
        "permissions": all_permissions,
        "permission_count": sum(1 for v in all_permissions.values() if v),
        "overrides": overrides
    }


@router.get("/users/{user_id}/stages")
async def get_user_stage_access(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's stage access records."""
    _authorize_user_access(current_user, user_id, db)
    result = db.execute(text("""
        SELECT usa.*, spt.code as template_code, spt.name as template_name
        FROM user_stage_access usa
        LEFT JOIN stage_permission_templates spt ON spt.id = usa.template_id
        WHERE usa.user_id = :user_id
        ORDER BY usa.stage_code
    """), {"user_id": user_id})

    stage_access = [dict(row._mapping) for row in result]
    return {"stage_access": stage_access}


@router.post("/users/{user_id}/stages")
async def grant_stage_access(
    user_id: int,
    request: GrantStageAccessRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Grant stage access to a user."""
    # Check authorization
    has_perm = db.execute(text("""
        SELECT user_has_permission(:actor_id, 'team.manage_permissions')
    """), {"actor_id": current_user["id"]}).scalar()
    if not has_perm:
        raise HTTPException(status_code=403, detail="Not authorized to manage permissions")

    # Get template ID if code provided
    template_id = None
    if request.template_code:
        template_result = db.execute(text("""
            SELECT id FROM stage_permission_templates WHERE code = :code
        """), {"code": request.template_code})
        template_row = template_result.fetchone()
        if template_row:
            template_id = template_row.id

    # Insert or update stage access
    result = db.execute(text("""
        INSERT INTO user_stage_access
            (user_id, stage_code, access_type, template_id, data_scope,
             is_active, granted_by, expires_at)
        VALUES
            (:user_id, :stage_code, 'granted', :template_id, :data_scope,
             TRUE, :granted_by, :expires_at)
        ON CONFLICT (user_id, stage_code)
        DO UPDATE SET
            template_id = EXCLUDED.template_id,
            data_scope = EXCLUDED.data_scope,
            is_active = TRUE,
            granted_by = EXCLUDED.granted_by,
            expires_at = EXCLUDED.expires_at,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
    """), {
        "user_id": user_id,
        "stage_code": request.stage_code,
        "template_id": template_id,
        "data_scope": request.data_scope,
        "granted_by": current_user["id"],
        "expires_at": request.expires_at
    })

    db.commit()
    row = result.fetchone()

    return {"stage_access": dict(row._mapping), "message": "Stage access granted"}


@router.delete("/users/{user_id}/stages/{stage_code}")
async def revoke_stage_access(
    user_id: int,
    stage_code: str,
    reason: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Revoke stage access from a user."""
    # Check authorization
    has_perm = db.execute(text("""
        SELECT user_has_permission(:actor_id, 'team.manage_permissions')
    """), {"actor_id": current_user["id"]}).scalar()
    if not has_perm:
        raise HTTPException(status_code=403, detail="Not authorized to manage permissions")

    db.execute(text("""
        UPDATE user_stage_access
        SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id AND stage_code = :stage_code
    """), {"user_id": user_id, "stage_code": stage_code})

    db.commit()

    return {"message": "Stage access revoked"}


@router.post("/users/{user_id}/stages/{stage_code}/apply-template")
async def apply_template_to_stage(
    user_id: int,
    stage_code: str,
    request: ApplyTemplateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Apply a template to user's stage access."""
    # Check authorization
    has_perm = db.execute(text("""
        SELECT user_has_permission(:actor_id, 'team.manage_permissions')
    """), {"actor_id": current_user["id"]}).scalar()
    if not has_perm:
        raise HTTPException(status_code=403, detail="Not authorized to manage permissions")

    # Get the new template
    template_result = db.execute(text("""
        SELECT id, permissions, default_scope FROM stage_permission_templates
        WHERE code = :code AND stage_code = :stage_code
    """), {"code": request.template_code, "stage_code": stage_code})

    template = template_result.fetchone()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found for this stage")

    # Get current permissions for diff
    current_result = db.execute(text("""
        SELECT spt.permissions
        FROM user_stage_access usa
        JOIN stage_permission_templates spt ON spt.id = usa.template_id
        WHERE usa.user_id = :user_id AND usa.stage_code = :stage_code
    """), {"user_id": user_id, "stage_code": stage_code})

    current_row = current_result.fetchone()
    current_permissions = current_row.permissions if current_row else {}

    # Calculate changes
    changes = []
    new_permissions = template.permissions
    all_keys = set(current_permissions.keys()) | set(new_permissions.keys())
    for key in all_keys:
        old_val = current_permissions.get(key, False)
        new_val = new_permissions.get(key, False)
        if old_val != new_val:
            changes.append({"key": key, "old_value": old_val, "new_value": new_val})

    # Update stage access with new template
    db.execute(text("""
        UPDATE user_stage_access
        SET template_id = :template_id,
            data_scope = :data_scope,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id AND stage_code = :stage_code
    """), {
        "template_id": template.id,
        "data_scope": template.default_scope,
        "user_id": user_id,
        "stage_code": stage_code
    })

    db.commit()

    # Get updated record
    updated_result = db.execute(text("""
        SELECT usa.*, spt.code as template_code, spt.name as template_name
        FROM user_stage_access usa
        LEFT JOIN stage_permission_templates spt ON spt.id = usa.template_id
        WHERE usa.user_id = :user_id AND usa.stage_code = :stage_code
    """), {"user_id": user_id, "stage_code": stage_code})

    updated = updated_result.fetchone()

    return {
        "stage_access": dict(updated._mapping) if updated else None,
        "changes_applied": changes
    }


# ============================================================================
# PERMISSION OVERRIDES
# ============================================================================

@router.get("/users/{user_id}/overrides")
async def get_user_overrides(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's permission overrides."""
    _authorize_user_access(current_user, user_id, db)
    result = db.execute(text("""
        SELECT * FROM user_permission_overrides
        WHERE user_id = :user_id
        ORDER BY granted_at DESC
    """), {"user_id": user_id})

    overrides = [dict(row._mapping) for row in result]
    return {"overrides": overrides}


@router.post("/users/{user_id}/overrides")
async def add_override(
    user_id: int,
    request: AddOverrideRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a permission override for a user."""
    # Check authorization
    has_perm = db.execute(text("""
        SELECT user_has_permission(:actor_id, 'team.manage_permissions')
    """), {"actor_id": current_user["id"]}).scalar()
    if not has_perm:
        raise HTTPException(status_code=403, detail="Not authorized to manage permissions")

    result = db.execute(text("""
        INSERT INTO user_permission_overrides
            (user_id, permission_key, granted, scope_override,
             is_temporary, expires_at, reason, granted_by)
        VALUES
            (:user_id, :permission_key, :granted, :scope_override,
             :is_temporary, :expires_at, :reason, :granted_by)
        ON CONFLICT (user_id, permission_key)
        DO UPDATE SET
            granted = EXCLUDED.granted,
            scope_override = EXCLUDED.scope_override,
            is_temporary = EXCLUDED.is_temporary,
            expires_at = EXCLUDED.expires_at,
            reason = EXCLUDED.reason,
            granted_by = EXCLUDED.granted_by,
            granted_at = CURRENT_TIMESTAMP
        RETURNING *
    """), {
        "user_id": user_id,
        "permission_key": request.permission_key,
        "granted": request.granted,
        "scope_override": request.scope_override,
        "is_temporary": request.is_temporary,
        "expires_at": request.expires_at,
        "reason": request.reason,
        "granted_by": current_user["id"]
    })

    db.commit()
    row = result.fetchone()

    return {"override": dict(row._mapping)}


@router.delete("/users/{user_id}/overrides/{permission_key:path}")
async def remove_override(
    user_id: int,
    permission_key: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a permission override."""
    # Check authorization
    has_perm = db.execute(text("""
        SELECT user_has_permission(:actor_id, 'team.manage_permissions')
    """), {"actor_id": current_user["id"]}).scalar()
    if not has_perm:
        raise HTTPException(status_code=403, detail="Not authorized to manage permissions")

    db.execute(text("""
        DELETE FROM user_permission_overrides
        WHERE user_id = :user_id AND permission_key = :permission_key
    """), {"user_id": user_id, "permission_key": permission_key})

    db.commit()

    return {"message": "Override removed"}


# ============================================================================
# PERMISSION CHECKS
# ============================================================================

@router.get("/users/{user_id}/check/{permission_key:path}")
async def check_permission(
    user_id: int,
    permission_key: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if user has a specific permission."""
    _authorize_user_access(current_user, user_id, db)
    result = db.execute(text("""
        SELECT user_has_permission(:user_id, :permission_key) as has_permission
    """), {"user_id": user_id, "permission_key": permission_key})

    has_perm = result.scalar()

    # Get scope if applicable
    scope_result = db.execute(text("""
        SELECT pd.stage_code, usa.data_scope, upo.scope_override
        FROM permission_definitions pd
        LEFT JOIN user_stage_access usa ON usa.user_id = :user_id AND usa.stage_code = pd.stage_code
        LEFT JOIN user_permission_overrides upo ON upo.user_id = :user_id AND upo.permission_key = :permission_key
        WHERE pd.key = :permission_key
    """), {"user_id": user_id, "permission_key": permission_key})

    scope_row = scope_result.fetchone()
    scope = None
    if scope_row:
        scope = scope_row.scope_override or scope_row.data_scope

    return {
        "has_permission": has_perm,
        "scope": scope,
        "reason": None if has_perm else "Permission not granted"
    }


@router.post("/users/{user_id}/check-any")
async def check_any_permission(
    user_id: int,
    permission_keys: List[str],
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if user has any of the specified permissions."""
    _authorize_user_access(current_user, user_id, db)
    for key in permission_keys:
        result = db.execute(text("""
            SELECT user_has_permission(:user_id, :permission_key)
        """), {"user_id": user_id, "permission_key": key})
        if result.scalar():
            return {"has_permission": True, "matched_key": key}

    return {"has_permission": False}


@router.post("/users/{user_id}/check-all")
async def check_all_permissions(
    user_id: int,
    permission_keys: List[str],
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if user has all of the specified permissions."""
    _authorize_user_access(current_user, user_id, db)
    missing = []
    for key in permission_keys:
        result = db.execute(text("""
            SELECT user_has_permission(:user_id, :permission_key)
        """), {"user_id": user_id, "permission_key": key})
        if not result.scalar():
            missing.append(key)

    return {
        "has_permission": len(missing) == 0,
        "missing_keys": missing
    }


@router.get("/users/{user_id}/effective")
async def get_effective_permissions(
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all permissions the user currently has."""
    _authorize_user_access(current_user, user_id, db)
    # Get all template permissions from user's stage access
    template_result = db.execute(text("""
        SELECT spt.permissions
        FROM user_stage_access usa
        JOIN stage_permission_templates spt ON spt.id = usa.template_id
        WHERE usa.user_id = :user_id AND usa.is_active = TRUE
        AND (usa.expires_at IS NULL OR usa.expires_at > CURRENT_TIMESTAMP)
    """), {"user_id": user_id})

    permissions = {}
    for row in template_result:
        if row.permissions:
            permissions.update(row.permissions)

    # Apply overrides
    override_result = db.execute(text("""
        SELECT permission_key, granted
        FROM user_permission_overrides
        WHERE user_id = :user_id
        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
    """), {"user_id": user_id})

    for row in override_result:
        permissions[row.permission_key] = row.granted

    return {"permissions": permissions}


# ============================================================================
# PERMISSION REQUESTS
# ============================================================================

@router.post("/requests")
async def create_permission_request(
    request: PermissionRequestCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a permission request."""
    # Check for existing pending request
    existing = db.execute(text("""
        SELECT id FROM stage_permission_requests
        WHERE user_id = :user_id
        AND request_type = :request_type
        AND COALESCE(stage_code, '') = COALESCE(:stage_code, '')
        AND COALESCE(permission_key, '') = COALESCE(:permission_key, '')
        AND status = 'pending'
    """), {
        "user_id": current_user["id"],
        "request_type": request.request_type,
        "stage_code": request.stage_code,
        "permission_key": request.permission_key
    })

    if existing.fetchone():
        raise HTTPException(status_code=400, detail="A pending request already exists")

    result = db.execute(text("""
        INSERT INTO stage_permission_requests
            (user_id, request_type, stage_code, permission_key, template_id,
             requested_scope, justification, urgency, is_temporary, duration_days)
        VALUES
            (:user_id, :request_type, :stage_code, :permission_key, :template_id,
             :requested_scope, :justification, :urgency, :is_temporary, :duration_days)
        RETURNING *
    """), {
        "user_id": current_user["id"],
        "request_type": request.request_type,
        "stage_code": request.stage_code,
        "permission_key": request.permission_key,
        "template_id": request.template_id,
        "requested_scope": request.requested_scope,
        "justification": request.justification,
        "urgency": request.urgency,
        "is_temporary": request.is_temporary,
        "duration_days": request.duration_days
    })

    db.commit()
    row = result.fetchone()

    return {"request": dict(row._mapping)}


@router.get("/requests/my")
async def get_my_requests(
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's permission requests."""
    query = """
        SELECT * FROM stage_permission_requests
        WHERE user_id = :user_id
    """
    params = {"user_id": current_user["id"]}

    if status:
        query += " AND status = :status"
        params["status"] = status

    query += " ORDER BY created_at DESC"

    result = db.execute(text(query), params)
    requests = [dict(row._mapping) for row in result]

    return {"requests": requests}


@router.get("/requests/pending")
async def get_pending_requests(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get pending requests for review (for managers)."""
    # Check authorization
    has_perm = db.execute(text("""
        SELECT user_has_permission(:actor_id, 'team.manage_permissions')
    """), {"actor_id": current_user["id"]}).scalar()
    if not has_perm:
        raise HTTPException(status_code=403, detail="Not authorized to review requests")

    result = db.execute(text("""
        SELECT spr.*, u.email as requester_email, u.full_name as requester_name
        FROM stage_permission_requests spr
        JOIN users u ON u.id = spr.user_id
        WHERE spr.status = 'pending'
        ORDER BY
            CASE spr.urgency
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                ELSE 4
            END,
            spr.created_at
    """))

    requests = [dict(row._mapping) for row in result]
    return {"requests": requests}


@router.post("/requests/{request_id}/approve")
async def approve_request(
    request_id: int,
    payload: ApproveRequestPayload,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Approve a permission request."""
    # Check authorization
    has_perm = db.execute(text("""
        SELECT user_has_permission(:actor_id, 'team.manage_permissions')
    """), {"actor_id": current_user["id"]}).scalar()
    if not has_perm:
        raise HTTPException(status_code=403, detail="Not authorized to approve requests")

    # Get request
    req_result = db.execute(text("""
        SELECT * FROM stage_permission_requests WHERE id = :id AND status = 'pending'
    """), {"id": request_id})
    req = req_result.fetchone()

    if not req:
        raise HTTPException(status_code=404, detail="Request not found or already processed")

    # Process the request based on type
    expires_at = None
    if req.is_temporary and req.duration_days:
        expires_at = datetime.now() + timedelta(days=req.duration_days)

    if req.request_type == 'stage_access':
        # Grant stage access
        db.execute(text("""
            INSERT INTO user_stage_access
                (user_id, stage_code, access_type, template_id, is_active,
                 granted_by, expires_at)
            VALUES
                (:user_id, :stage_code, 'granted', :template_id, TRUE,
                 :granted_by, :expires_at)
            ON CONFLICT (user_id, stage_code)
            DO UPDATE SET is_active = TRUE, granted_by = EXCLUDED.granted_by,
                expires_at = EXCLUDED.expires_at, updated_at = CURRENT_TIMESTAMP
        """), {
            "user_id": req.user_id,
            "stage_code": req.stage_code,
            "template_id": req.template_id,
            "granted_by": current_user["id"],
            "expires_at": expires_at
        })

    elif req.request_type == 'permission':
        # Add permission override
        db.execute(text("""
            INSERT INTO user_permission_overrides
                (user_id, permission_key, granted, is_temporary, expires_at,
                 reason, granted_by)
            VALUES
                (:user_id, :permission_key, TRUE, :is_temporary, :expires_at,
                 :reason, :granted_by)
            ON CONFLICT (user_id, permission_key)
            DO UPDATE SET granted = TRUE, is_temporary = EXCLUDED.is_temporary,
                expires_at = EXCLUDED.expires_at, granted_by = EXCLUDED.granted_by,
                granted_at = CURRENT_TIMESTAMP
        """), {
            "user_id": req.user_id,
            "permission_key": req.permission_key,
            "is_temporary": req.is_temporary,
            "expires_at": expires_at,
            "reason": f"Approved request #{request_id}",
            "granted_by": current_user["id"]
        })

    elif req.request_type == 'scope_upgrade':
        # Update data scope
        db.execute(text("""
            UPDATE user_stage_access
            SET data_scope = :scope, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id AND stage_code = :stage_code
        """), {
            "user_id": req.user_id,
            "stage_code": req.stage_code,
            "scope": req.requested_scope
        })

    # Update request status
    result = db.execute(text("""
        UPDATE stage_permission_requests
        SET status = 'approved', reviewed_by = :reviewed_by,
            reviewed_at = CURRENT_TIMESTAMP, review_notes = :notes,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        RETURNING *
    """), {
        "id": request_id,
        "reviewed_by": current_user["id"],
        "notes": payload.notes
    })

    db.commit()
    row = result.fetchone()

    return {"request": dict(row._mapping)}


@router.post("/requests/{request_id}/deny")
async def deny_request(
    request_id: int,
    payload: DenyRequestPayload,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deny a permission request."""
    # Check authorization
    has_perm = db.execute(text("""
        SELECT user_has_permission(:actor_id, 'team.manage_permissions')
    """), {"actor_id": current_user["id"]}).scalar()
    if not has_perm:
        raise HTTPException(status_code=403, detail="Not authorized to deny requests")

    result = db.execute(text("""
        UPDATE stage_permission_requests
        SET status = 'denied', reviewed_by = :reviewed_by,
            reviewed_at = CURRENT_TIMESTAMP, review_notes = :reason,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id AND status = 'pending'
        RETURNING *
    """), {
        "id": request_id,
        "reviewed_by": current_user["id"],
        "reason": payload.reason
    })

    db.commit()
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Request not found or already processed")

    return {"request": dict(row._mapping)}


@router.post("/requests/{request_id}/more-info")
async def request_more_info(
    request_id: int,
    payload: MoreInfoRequestPayload,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Request more information for a permission request."""
    result = db.execute(text("""
        UPDATE stage_permission_requests
        SET status = 'more_info', reviewed_by = :reviewed_by,
            review_notes = :questions, updated_at = CURRENT_TIMESTAMP
        WHERE id = :id AND status = 'pending'
        RETURNING *
    """), {
        "id": request_id,
        "reviewed_by": current_user["id"],
        "questions": payload.questions
    })

    db.commit()
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Request not found or already processed")

    return {"request": dict(row._mapping)}


@router.post("/requests/{request_id}/cancel")
async def cancel_request(
    request_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a pending request (by requester)."""
    result = db.execute(text("""
        UPDATE stage_permission_requests
        SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
        WHERE id = :id AND user_id = :user_id AND status = 'pending'
        RETURNING id
    """), {"id": request_id, "user_id": current_user["id"]})

    db.commit()

    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Request not found or cannot be cancelled")

    return {"message": "Request cancelled"}


# ============================================================================
# AUDIT LOG
# ============================================================================

@router.get("/users/{user_id}/audit")
async def get_permission_audit_log(
    user_id: int,
    limit: int = Query(50, le=500),
    offset: int = 0,
    action: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get permission audit log for a user."""
    query = """
        SELECT pal.*, u.email as actor_email
        FROM permission_audit_log pal
        LEFT JOIN users u ON u.id = pal.actor_id
        WHERE pal.user_id = :user_id
    """
    params = {"user_id": user_id}

    if action:
        query += " AND pal.action = :action"
        params["action"] = action

    if start_date:
        query += " AND pal.timestamp >= :start_date"
        params["start_date"] = start_date

    if end_date:
        query += " AND pal.timestamp <= :end_date"
        params["end_date"] = end_date

    # SAFETY: 'query' is built entirely from hardcoded SQL string literals above
    # (the base SELECT and conditional WHERE clauses like "AND pal.action = :action").
    # All user-supplied values use :param bind syntax — never interpolated.
    count_result = db.execute(text(f"SELECT COUNT(*) FROM ({query}) sub"), params)
    total = count_result.scalar()

    # Get paginated results
    query += " ORDER BY pal.timestamp DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    result = db.execute(text(query), params)
    logs = [dict(row._mapping) for row in result]

    return {"logs": logs, "total": total}
