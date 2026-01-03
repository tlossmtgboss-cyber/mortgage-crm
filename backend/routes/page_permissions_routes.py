"""
Page Permissions API Routes
Role-Based Access Control (RBAC) for page-level permissions
Perennia AI - TL Development LLC

Handles CRUD operations for role permissions and page access control.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import json

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/page-permissions", tags=["Page Permissions"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class PageInfo(BaseModel):
    """Information about a single page"""
    key: str
    name: str
    path: str
    category: str
    stage: str


class RoleInfo(BaseModel):
    """Information about a role"""
    key: str
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    hierarchy_level: int = 0
    permissions: List[str] = []
    enabled_count: int = 0
    total_pages: int = 0
    is_custom: bool = False


class RolePermissionsResponse(BaseModel):
    """Response for role permissions"""
    role: str
    role_name: str
    permissions: List[str]
    total_pages: int
    enabled_count: int
    last_modified: Optional[datetime] = None
    modified_by: Optional[str] = None


class UpdatePermissionsRequest(BaseModel):
    """Request to update permissions for a role"""
    permissions: List[str] = Field(..., description="List of page keys to enable")


class PermissionCheckRequest(BaseModel):
    """Request to check if user has access to a page"""
    page_key: str


class PermissionCheckResponse(BaseModel):
    """Response for permission check"""
    page_key: str
    has_access: bool
    page_info: Optional[PageInfo] = None


class BulkPermissionCheckRequest(BaseModel):
    """Request to check multiple pages at once"""
    page_keys: List[str]


class BulkPermissionCheckResponse(BaseModel):
    """Response for bulk permission check"""
    results: Dict[str, bool]


class AllRolesResponse(BaseModel):
    """Response containing all roles and their permissions"""
    roles: List[Dict[str, Any]]
    pages: List[PageInfo]
    categories: List[str]


class AuditLogEntry(BaseModel):
    """Audit log entry"""
    id: int
    timestamp: datetime
    user_id: int
    user_email: Optional[str]
    target_type: str
    target_name: Optional[str]
    action: str
    changes: Dict[str, Any]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_role_id(db: Session, role_key: str) -> Optional[int]:
    """Get role ID by role key"""
    result = db.execute(text(
        "SELECT id FROM permission_roles WHERE role_key = :role_key AND is_active = true"
    ), {"role_key": role_key})
    row = result.fetchone()
    return row[0] if row else None


def get_page_id(db: Session, page_key: str) -> Optional[int]:
    """Get page ID by page key"""
    result = db.execute(text(
        "SELECT id FROM pages WHERE page_key = :page_key AND is_active = true"
    ), {"page_key": page_key})
    row = result.fetchone()
    return row[0] if row else None


def get_role_permissions(db: Session, role_key: str) -> List[str]:
    """Get all page keys for a role"""
    result = db.execute(text("""
        SELECT p.page_key
        FROM role_page_permissions rpp
        JOIN permission_roles r ON r.id = rpp.role_id
        JOIN pages p ON p.id = rpp.page_id
        WHERE r.role_key = :role_key
        AND rpp.can_view = true
        AND r.is_active = true
        AND p.is_active = true
        ORDER BY p.display_order
    """), {"role_key": role_key})

    return [row[0] for row in result.fetchall()]


def log_permission_change(
    db: Session,
    user_id: int,
    user_email: str,
    target_type: str,
    target_id: int,
    target_name: str,
    action: str,
    changes: Dict[str, Any],
    request: Optional[Request] = None
):
    """Log permission changes for audit trail"""
    ip_address = None
    user_agent = None

    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

    try:
        db.execute(text("""
            INSERT INTO page_permission_audit_log
            (user_id, user_email, target_type, target_id, target_name, action, changes, ip_address, user_agent)
            VALUES (:user_id, :user_email, :target_type, :target_id, :target_name, :action, :changes::jsonb, :ip_address, :user_agent)
        """), {
            "user_id": user_id,
            "user_email": user_email,
            "target_type": target_type,
            "target_id": target_id,
            "target_name": target_name,
            "action": action,
            "changes": json.dumps(changes),
            "ip_address": ip_address,
            "user_agent": user_agent
        })
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log permission change: {e}")


# ============================================================================
# API ROUTES
# ============================================================================

@router.get("/pages", response_model=List[PageInfo])
async def get_all_pages(db: Session = Depends(get_db)):
    """
    Get all available pages in the system.
    Returns page metadata organized for the permissions UI.
    """
    result = db.execute(text("""
        SELECT page_key, name, path, category, stage
        FROM pages
        WHERE is_active = true
        ORDER BY display_order, name
    """))

    pages = []
    for row in result.fetchall():
        pages.append(PageInfo(
            key=row[0],
            name=row[1],
            path=row[2],
            category=row[3],
            stage=row[4]
        ))

    return pages


@router.get("/roles", response_model=AllRolesResponse)
async def get_all_roles(db: Session = Depends(get_db)):
    """
    Get all roles with their current permissions.
    Used to populate the permissions management UI.
    """
    # Get total page count
    total_result = db.execute(text("SELECT COUNT(*) FROM pages WHERE is_active = true"))
    total_pages = total_result.fetchone()[0]

    # Get all roles
    roles_result = db.execute(text("""
        SELECT role_key, name, description, color, icon, hierarchy_level, is_system_role
        FROM permission_roles
        WHERE is_active = true
        ORDER BY hierarchy_level
    """))

    roles = []
    for row in roles_result.fetchall():
        role_key = row[0]
        perms = get_role_permissions(db, role_key)

        roles.append({
            "key": role_key,
            "name": row[1],
            "description": row[2],
            "color": row[3],
            "icon": row[4],
            "hierarchy_level": row[5],
            "is_system_role": row[6],
            "permissions": perms,
            "enabled_count": len(perms),
            "total_pages": total_pages,
            "is_custom": False  # Could track if role has custom overrides
        })

    # Get all pages
    pages_result = db.execute(text("""
        SELECT page_key, name, path, category, stage
        FROM pages
        WHERE is_active = true
        ORDER BY display_order, name
    """))

    pages = []
    for row in pages_result.fetchall():
        pages.append(PageInfo(
            key=row[0],
            name=row[1],
            path=row[2],
            category=row[3],
            stage=row[4]
        ))

    # Get unique categories
    categories_result = db.execute(text("""
        SELECT DISTINCT category FROM pages WHERE is_active = true ORDER BY category
    """))
    categories = [row[0] for row in categories_result.fetchall()]

    return AllRolesResponse(roles=roles, pages=pages, categories=categories)


@router.get("/role/{role_key}", response_model=RolePermissionsResponse)
async def get_role_permissions_endpoint(
    role_key: str,
    db: Session = Depends(get_db)
):
    """
    Get permissions for a specific role.
    """
    # Validate role exists
    role_id = get_role_id(db, role_key)
    if not role_id:
        raise HTTPException(status_code=404, detail=f"Role not found: {role_key}")

    # Get role info
    role_result = db.execute(text(
        "SELECT name FROM permission_roles WHERE role_key = :role_key"
    ), {"role_key": role_key})
    role_name = role_result.fetchone()[0]

    # Get total pages
    total_result = db.execute(text("SELECT COUNT(*) FROM pages WHERE is_active = true"))
    total_pages = total_result.fetchone()[0]

    # Get permissions
    perms = get_role_permissions(db, role_key)

    return RolePermissionsResponse(
        role=role_key,
        role_name=role_name,
        permissions=perms,
        total_pages=total_pages,
        enabled_count=len(perms)
    )


@router.put("/role/{role_key}", response_model=RolePermissionsResponse)
async def update_role_permissions(
    role_key: str,
    request_data: UpdatePermissionsRequest,
    request: Request,
    db: Session = Depends(get_db),
    # TODO: Add authentication dependency
    # current_user: User = Depends(get_current_user)
):
    """
    Update permissions for a specific role.
    Only administrators can update permissions.
    """
    # Validate role exists
    role_id = get_role_id(db, role_key)
    if not role_id:
        raise HTTPException(status_code=404, detail=f"Role not found: {role_key}")

    # Get role info
    role_result = db.execute(text(
        "SELECT name FROM permission_roles WHERE role_key = :role_key"
    ), {"role_key": role_key})
    role_name = role_result.fetchone()[0]

    # Get old permissions for audit
    old_perms = get_role_permissions(db, role_key)

    # Validate all page keys exist
    invalid_keys = []
    for page_key in request_data.permissions:
        if not get_page_id(db, page_key):
            invalid_keys.append(page_key)

    if invalid_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid page keys: {invalid_keys}"
        )

    # Clear existing permissions for this role
    db.execute(text(
        "DELETE FROM role_page_permissions WHERE role_id = :role_id"
    ), {"role_id": role_id})

    # Insert new permissions
    for page_key in request_data.permissions:
        page_id = get_page_id(db, page_key)
        if page_id:
            db.execute(text("""
                INSERT INTO role_page_permissions (role_id, page_id, can_view)
                VALUES (:role_id, :page_id, true)
            """), {"role_id": role_id, "page_id": page_id})

    db.commit()

    # Log the change
    added = set(request_data.permissions) - set(old_perms)
    removed = set(old_perms) - set(request_data.permissions)

    log_permission_change(
        db=db,
        user_id=1,  # TODO: Use actual user ID from auth
        user_email="admin@example.com",  # TODO: Use actual user email
        target_type="role",
        target_id=role_id,
        target_name=role_key,
        action="updated",
        changes={
            "added": list(added),
            "removed": list(removed),
            "old_count": len(old_perms),
            "new_count": len(request_data.permissions)
        },
        request=request
    )

    # Get total pages
    total_result = db.execute(text("SELECT COUNT(*) FROM pages WHERE is_active = true"))
    total_pages = total_result.fetchone()[0]

    return RolePermissionsResponse(
        role=role_key,
        role_name=role_name,
        permissions=request_data.permissions,
        total_pages=total_pages,
        enabled_count=len(request_data.permissions),
        last_modified=datetime.utcnow()
    )


@router.post("/role/{role_key}/reset", response_model=RolePermissionsResponse)
async def reset_role_to_default(
    role_key: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Reset a role's permissions to default.
    This re-runs the seeding logic for the specified role.
    """
    # Import the default permissions
    from migrations.add_page_permissions_system import get_default_permissions, get_all_pages

    # Validate role exists
    role_id = get_role_id(db, role_key)
    if not role_id:
        raise HTTPException(status_code=404, detail=f"Role not found: {role_key}")

    role_result = db.execute(text(
        "SELECT name FROM permission_roles WHERE role_key = :role_key"
    ), {"role_key": role_key})
    role_name = role_result.fetchone()[0]

    # Get old permissions
    old_perms = get_role_permissions(db, role_key)

    # Get default permissions
    default_permissions = get_default_permissions()
    if role_key == "administrator":
        default_perms = [p["page_key"] for p in get_all_pages()]
    else:
        default_perms = default_permissions.get(role_key, [])

    # Clear existing permissions
    db.execute(text(
        "DELETE FROM role_page_permissions WHERE role_id = :role_id"
    ), {"role_id": role_id})

    # Insert default permissions
    for page_key in default_perms:
        page_id = get_page_id(db, page_key)
        if page_id:
            db.execute(text("""
                INSERT INTO role_page_permissions (role_id, page_id, can_view)
                VALUES (:role_id, :page_id, true)
            """), {"role_id": role_id, "page_id": page_id})

    db.commit()

    # Log the change
    log_permission_change(
        db=db,
        user_id=1,  # TODO: Use actual user ID
        user_email="admin@example.com",
        target_type="role",
        target_id=role_id,
        target_name=role_key,
        action="reset_to_default",
        changes={
            "old_permissions": old_perms,
            "new_permissions": default_perms
        },
        request=request
    )

    # Get total pages
    total_result = db.execute(text("SELECT COUNT(*) FROM pages WHERE is_active = true"))
    total_pages = total_result.fetchone()[0]

    return RolePermissionsResponse(
        role=role_key,
        role_name=role_name,
        permissions=default_perms,
        total_pages=total_pages,
        enabled_count=len(default_perms),
        last_modified=datetime.utcnow()
    )


@router.post("/role/{role_key}/copy-from/{source_role}", response_model=RolePermissionsResponse)
async def copy_permissions_from_role(
    role_key: str,
    source_role: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Copy permissions from one role to another.
    """
    # Validate both roles exist
    role_id = get_role_id(db, role_key)
    source_role_id = get_role_id(db, source_role)

    if not role_id:
        raise HTTPException(status_code=404, detail=f"Target role not found: {role_key}")
    if not source_role_id:
        raise HTTPException(status_code=404, detail=f"Source role not found: {source_role}")

    role_result = db.execute(text(
        "SELECT name FROM permission_roles WHERE role_key = :role_key"
    ), {"role_key": role_key})
    role_name = role_result.fetchone()[0]

    # Get old permissions
    old_perms = get_role_permissions(db, role_key)

    # Get source permissions
    source_perms = get_role_permissions(db, source_role)

    # Clear existing permissions
    db.execute(text(
        "DELETE FROM role_page_permissions WHERE role_id = :role_id"
    ), {"role_id": role_id})

    # Copy source permissions
    for page_key in source_perms:
        page_id = get_page_id(db, page_key)
        if page_id:
            db.execute(text("""
                INSERT INTO role_page_permissions (role_id, page_id, can_view)
                VALUES (:role_id, :page_id, true)
            """), {"role_id": role_id, "page_id": page_id})

    db.commit()

    # Log the change
    log_permission_change(
        db=db,
        user_id=1,
        user_email="admin@example.com",
        target_type="role",
        target_id=role_id,
        target_name=role_key,
        action=f"copied_from_{source_role}",
        changes={
            "source_role": source_role,
            "old_permissions": old_perms,
            "new_permissions": source_perms
        },
        request=request
    )

    # Get total pages
    total_result = db.execute(text("SELECT COUNT(*) FROM pages WHERE is_active = true"))
    total_pages = total_result.fetchone()[0]

    return RolePermissionsResponse(
        role=role_key,
        role_name=role_name,
        permissions=source_perms,
        total_pages=total_pages,
        enabled_count=len(source_perms),
        last_modified=datetime.utcnow()
    )


@router.post("/check", response_model=PermissionCheckResponse)
async def check_permission(
    request_data: PermissionCheckRequest,
    user_role: str = Query(..., description="User's role key"),
    user_id: Optional[int] = Query(None, description="User ID for override checking"),
    db: Session = Depends(get_db)
):
    """
    Check if a user with a given role can access a specific page.
    Use this in your route guards and navigation rendering.
    """
    # Validate page exists
    page_result = db.execute(text("""
        SELECT id, page_key, name, path, category, stage
        FROM pages
        WHERE page_key = :page_key AND is_active = true
    """), {"page_key": request_data.page_key})

    page_row = page_result.fetchone()
    if not page_row:
        raise HTTPException(status_code=400, detail=f"Invalid page key: {request_data.page_key}")

    page_id = page_row[0]
    page_info = PageInfo(
        key=page_row[1],
        name=page_row[2],
        path=page_row[3],
        category=page_row[4],
        stage=page_row[5]
    )

    # Check for user-specific override first
    if user_id:
        override_result = db.execute(text("""
            SELECT can_view
            FROM user_page_overrides
            WHERE user_id = :user_id
            AND page_id = :page_id
            AND (expires_at IS NULL OR expires_at > NOW())
        """), {"user_id": user_id, "page_id": page_id})

        override_row = override_result.fetchone()
        if override_row and override_row[0] is not None:
            return PermissionCheckResponse(
                page_key=request_data.page_key,
                has_access=override_row[0],
                page_info=page_info if override_row[0] else None
            )

    # Check role permissions
    perms = get_role_permissions(db, user_role)
    has_access = request_data.page_key in perms

    return PermissionCheckResponse(
        page_key=request_data.page_key,
        has_access=has_access,
        page_info=page_info if has_access else None
    )


@router.post("/check-bulk", response_model=BulkPermissionCheckResponse)
async def check_permissions_bulk(
    request_data: BulkPermissionCheckRequest,
    user_role: str = Query(..., description="User's role key"),
    user_id: Optional[int] = Query(None, description="User ID for override checking"),
    db: Session = Depends(get_db)
):
    """
    Check multiple pages at once - useful for navigation rendering.
    """
    perms = get_role_permissions(db, user_role)

    # Check for user overrides if user_id provided
    overrides = {}
    if user_id:
        override_result = db.execute(text("""
            SELECT p.page_key, upo.can_view
            FROM user_page_overrides upo
            JOIN pages p ON p.id = upo.page_id
            WHERE upo.user_id = :user_id
            AND (upo.expires_at IS NULL OR upo.expires_at > NOW())
            AND upo.can_view IS NOT NULL
        """), {"user_id": user_id})

        for row in override_result.fetchall():
            overrides[row[0]] = row[1]

    results = {}
    for key in request_data.page_keys:
        if key in overrides:
            results[key] = overrides[key]
        else:
            results[key] = key in perms

    return BulkPermissionCheckResponse(results=results)


@router.get("/user/accessible-pages")
async def get_user_accessible_pages(
    user_role: str = Query(..., description="User's role key"),
    user_id: Optional[int] = Query(None, description="User ID for override checking"),
    db: Session = Depends(get_db)
):
    """
    Get all pages a user can access based on their role.
    Use this to build the navigation menu.
    """
    perms = get_role_permissions(db, user_role)

    # Get page details
    pages_result = db.execute(text("""
        SELECT page_key, name, path, category, stage
        FROM pages
        WHERE is_active = true
        ORDER BY display_order, name
    """))

    all_pages = []
    for row in pages_result.fetchall():
        all_pages.append({
            "key": row[0],
            "name": row[1],
            "path": row[2],
            "category": row[3],
            "stage": row[4]
        })

    # Get user overrides if provided
    overrides = {}
    if user_id:
        override_result = db.execute(text("""
            SELECT p.page_key, upo.can_view
            FROM user_page_overrides upo
            JOIN pages p ON p.id = upo.page_id
            WHERE upo.user_id = :user_id
            AND (upo.expires_at IS NULL OR upo.expires_at > NOW())
            AND upo.can_view IS NOT NULL
        """), {"user_id": user_id})

        for row in override_result.fetchall():
            overrides[row[0]] = row[1]

    # Filter accessible pages
    accessible_pages = []
    for page in all_pages:
        key = page["key"]
        if key in overrides:
            if overrides[key]:
                accessible_pages.append(page)
        elif key in perms:
            accessible_pages.append(page)

    # Group by category
    grouped = {}
    for page in accessible_pages:
        cat = page["category"]
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(page)

    return {
        "role": user_role,
        "pages": accessible_pages,
        "grouped": grouped,
        "total_accessible": len(accessible_pages)
    }


@router.get("/audit-log")
async def get_audit_log(
    role_key: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Get permission change audit log.
    Optionally filter by role.
    """
    params = {"limit": limit, "offset": offset}
    where_clause = ""

    if role_key:
        where_clause = "WHERE target_name = :role_key"
        params["role_key"] = role_key

    # Get total count
    count_result = db.execute(text(f"""
        SELECT COUNT(*) FROM page_permission_audit_log {where_clause}
    """), params)
    total = count_result.fetchone()[0]

    # Get entries
    result = db.execute(text(f"""
        SELECT id, timestamp, user_id, user_email, target_type, target_name, action, changes
        FROM page_permission_audit_log
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT :limit OFFSET :offset
    """), params)

    entries = []
    for row in result.fetchall():
        entries.append({
            "id": row[0],
            "timestamp": row[1].isoformat() if row[1] else None,
            "user_id": row[2],
            "user_email": row[3],
            "target_type": row[4],
            "target_name": row[5],
            "action": row[6],
            "changes": row[7] if row[7] else {}
        })

    return {
        "entries": entries,
        "total": total,
        "limit": limit,
        "offset": offset
    }


# ============================================================================
# USER OVERRIDE ROUTES
# ============================================================================

class UserOverrideRequest(BaseModel):
    """Request to set user-specific page permission override"""
    page_key: str
    can_view: Optional[bool] = None
    reason: Optional[str] = None
    expires_at: Optional[datetime] = None


@router.post("/user/{user_id}/override")
async def set_user_override(
    user_id: int,
    request_data: UserOverrideRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Set a user-specific permission override for a page.
    Can_view=True grants access, False denies, None removes the override.
    """
    page_id = get_page_id(db, request_data.page_key)
    if not page_id:
        raise HTTPException(status_code=400, detail=f"Invalid page key: {request_data.page_key}")

    if request_data.can_view is None:
        # Remove override
        db.execute(text("""
            DELETE FROM user_page_overrides
            WHERE user_id = :user_id AND page_id = :page_id
        """), {"user_id": user_id, "page_id": page_id})
        action = "removed_override"
    else:
        # Set or update override
        db.execute(text("""
            INSERT INTO user_page_overrides (user_id, page_id, can_view, reason, expires_at, granted_by)
            VALUES (:user_id, :page_id, :can_view, :reason, :expires_at, :granted_by)
            ON CONFLICT (user_id, page_id)
            DO UPDATE SET
                can_view = EXCLUDED.can_view,
                reason = EXCLUDED.reason,
                expires_at = EXCLUDED.expires_at,
                granted_by = EXCLUDED.granted_by,
                granted_at = NOW()
        """), {
            "user_id": user_id,
            "page_id": page_id,
            "can_view": request_data.can_view,
            "reason": request_data.reason,
            "expires_at": request_data.expires_at,
            "granted_by": 1  # TODO: Use actual admin user ID
        })
        action = "granted" if request_data.can_view else "denied"

    db.commit()

    # Log the change
    log_permission_change(
        db=db,
        user_id=1,
        user_email="admin@example.com",
        target_type="user",
        target_id=user_id,
        target_name=str(user_id),
        action=f"override_{action}",
        changes={
            "page_key": request_data.page_key,
            "can_view": request_data.can_view,
            "reason": request_data.reason
        },
        request=request
    )

    return {"status": "success", "action": action}


@router.get("/user/{user_id}/overrides")
async def get_user_overrides(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all permission overrides for a user.
    """
    result = db.execute(text("""
        SELECT p.page_key, p.name, upo.can_view, upo.reason, upo.expires_at, upo.granted_at
        FROM user_page_overrides upo
        JOIN pages p ON p.id = upo.page_id
        WHERE upo.user_id = :user_id
        ORDER BY p.display_order
    """), {"user_id": user_id})

    overrides = []
    for row in result.fetchall():
        overrides.append({
            "page_key": row[0],
            "page_name": row[1],
            "can_view": row[2],
            "reason": row[3],
            "expires_at": row[4].isoformat() if row[4] else None,
            "granted_at": row[5].isoformat() if row[5] else None
        })

    return {"user_id": user_id, "overrides": overrides}
