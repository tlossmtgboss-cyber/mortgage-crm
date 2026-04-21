"""
Page Permissions API Routes

API endpoints for the page-level access control system.
Provides endpoints for:
- Getting user's accessible pages
- Checking page access
- Managing user page overrides (admin)
- Managing page permissions by role (admin)
- Pinning/unpinning pages
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List, Callable, Any
from pydantic import BaseModel
from datetime import datetime
import json

import logging
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/page-permissions", tags=["Page Permissions"])

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

from db import get_db

_get_current_user: Callable = None
_User: Any = None


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable, user_model: Any):
    """Set dependencies from main.py to avoid circular imports."""
    global _get_current_user, _User
    _get_current_user = get_current_user_func
    _User = user_model
    logger.info("Page permissions routes dependencies set")


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user dependency - wrapper for injected dependency."""
    if _get_current_user is None:
        raise RuntimeError("Page permissions routes not initialized. Call set_dependencies first.")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class PageCategory(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    display_order: int
    default_visible: bool


class PageInfo(BaseModel):
    id: int
    path: str
    name: str
    description: Optional[str] = None
    category: str
    icon: Optional[str] = None
    parent_path: Optional[str] = None
    display_order: int
    min_role: str
    can_view: bool = True
    can_edit: bool = False
    is_pinned: bool = False
    pin_order: Optional[int] = None


class PageAccessCheck(BaseModel):
    can_view: bool
    can_edit: bool
    is_nav_visible: bool
    access_source: str


class UserPageOverrideRequest(BaseModel):
    can_view: Optional[bool] = None
    can_edit: Optional[bool] = None
    is_nav_visible: Optional[bool] = None
    override_reason: Optional[str] = None
    expires_at: Optional[datetime] = None


class PinPageRequest(BaseModel):
    is_pinned: bool
    pin_order: Optional[int] = None


class RolePagePermissionRequest(BaseModel):
    can_view: bool
    can_edit: bool
    is_nav_visible: bool


class BulkPagePermissionRequest(BaseModel):
    page_ids: List[int]
    role: str
    can_view: bool
    can_edit: bool


# =============================================================================
# PUBLIC ENDPOINTS (for authenticated users)
# =============================================================================

@router.get("/categories")
async def get_page_categories(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all page categories."""
    try:
        result = db.execute(text("""
            SELECT id, code, name, description, icon, display_order, default_visible
            FROM page_categories
            ORDER BY display_order
        """))

        categories = [
            {
                "id": row[0],
                "code": row[1],
                "name": row[2],
                "description": row[3],
                "icon": row[4],
                "display_order": row[5],
                "default_visible": bool(row[6]),
            }
            for row in result.fetchall()
        ]

        return {"categories": categories}
    except Exception as e:
        logger.error(f"Error fetching page categories: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/my-pages")
async def get_my_accessible_pages(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all pages accessible by the current user."""
    try:
        user_id = current_user.id
        user_role = getattr(current_user, 'permission_role', 'sales') or 'sales'

        # Build query
        query = """
            SELECT
                p.id,
                p.path,
                p.name,
                p.description,
                p.category,
                p.icon,
                p.parent_path,
                p.display_order,
                p.min_role,
                COALESCE(upo.can_view, pp.can_view, 1) as can_view,
                COALESCE(upo.can_edit, pp.can_edit, 0) as can_edit,
                COALESCE(upo.is_pinned, 0) as is_pinned,
                upo.pin_order
            FROM pages p
            LEFT JOIN user_page_overrides upo ON upo.page_id = p.id
                AND upo.user_id = :user_id
                AND (upo.expires_at IS NULL OR upo.expires_at > CURRENT_TIMESTAMP)
            LEFT JOIN page_permissions pp ON pp.page_id = p.id
                AND pp.role = :role
            WHERE p.is_active = 1
                AND COALESCE(upo.is_nav_visible, pp.is_nav_visible, 1) = 1
        """

        params = {"user_id": user_id, "role": user_role}

        if category:
            query += " AND p.category = :category"
            params["category"] = category

        query += """
            ORDER BY
                COALESCE(upo.is_pinned, 0) DESC,
                upo.pin_order NULLS LAST,
                p.display_order
        """

        result = db.execute(text(query), params)

        pages = [
            {
                "id": row[0],
                "path": row[1],
                "name": row[2],
                "description": row[3],
                "category": row[4],
                "icon": row[5],
                "parent_path": row[6],
                "display_order": row[7],
                "min_role": row[8],
                "can_view": bool(row[9]),
                "can_edit": bool(row[10]),
                "is_pinned": bool(row[11]),
                "pin_order": row[12],
            }
            for row in result.fetchall()
        ]

        # Group by category
        by_category = {}
        for page in pages:
            cat = page["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(page)

        return {
            "pages": pages,
            "by_category": by_category,
            "total": len(pages),
        }
    except Exception as e:
        logger.error(f"Error fetching user pages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/check/{page_path:path}")
async def check_page_access(
    page_path: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Check if current user can access a specific page."""
    try:
        user_id = current_user.id
        user_role = getattr(current_user, 'permission_role', 'sales') or 'sales'

        # Normalize path
        if not page_path.startswith("/"):
            page_path = "/" + page_path

        # Check for exact match or pattern match (for paths with :id)
        result = db.execute(text("""
            SELECT id, path, min_role, is_active
            FROM pages
            WHERE path = :path OR path LIKE :pattern
            LIMIT 1
        """), {
            "path": page_path,
            "pattern": page_path.rsplit("/", 1)[0] + "/%"
        })

        page = result.fetchone()

        if not page:
            return {
                "can_view": False,
                "can_edit": False,
                "is_nav_visible": False,
                "access_source": "page_not_found",
            }

        page_id = page[0]

        # Check user override first
        override = db.execute(text("""
            SELECT can_view, can_edit, is_nav_visible
            FROM user_page_overrides
            WHERE user_id = :user_id AND page_id = :page_id
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        """), {"user_id": user_id, "page_id": page_id}).fetchone()

        if override:
            return {
                "can_view": bool(override[0]) if override[0] is not None else True,
                "can_edit": bool(override[1]) if override[1] is not None else False,
                "is_nav_visible": bool(override[2]) if override[2] is not None else True,
                "access_source": "user_override",
            }

        # Check role permission
        role_perm = db.execute(text("""
            SELECT can_view, can_edit, is_nav_visible
            FROM page_permissions
            WHERE page_id = :page_id AND role = :role
        """), {"page_id": page_id, "role": user_role}).fetchone()

        if role_perm:
            return {
                "can_view": bool(role_perm[0]),
                "can_edit": bool(role_perm[1]),
                "is_nav_visible": bool(role_perm[2]),
                "access_source": "role_permission",
            }

        # Default based on role hierarchy
        role_hierarchy = {"sales": 1, "operations": 2, "management": 3, "admin": 4}
        min_role = page[2] or "sales"
        user_level = role_hierarchy.get(user_role, 1)
        min_level = role_hierarchy.get(min_role, 1)

        can_view = user_level >= min_level

        return {
            "can_view": can_view,
            "can_edit": user_role == "management" or user_level > min_level,
            "is_nav_visible": can_view,
            "access_source": "default",
        }
    except Exception as e:
        logger.error(f"Error checking page access: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/pin/{page_id}")
async def pin_page(
    page_id: int,
    request: PinPageRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Pin or unpin a page for the current user."""
    try:
        user_id = current_user.id

        # Check if override exists
        existing = db.execute(text("""
            SELECT id FROM user_page_overrides
            WHERE user_id = :user_id AND page_id = :page_id
        """), {"user_id": user_id, "page_id": page_id}).fetchone()

        if existing:
            db.execute(text("""
                UPDATE user_page_overrides
                SET is_pinned = :is_pinned, pin_order = :pin_order, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND page_id = :page_id
            """), {
                "user_id": user_id,
                "page_id": page_id,
                "is_pinned": 1 if request.is_pinned else 0,
                "pin_order": request.pin_order,
            })
        else:
            db.execute(text("""
                INSERT INTO user_page_overrides (user_id, page_id, is_pinned, pin_order)
                VALUES (:user_id, :page_id, :is_pinned, :pin_order)
            """), {
                "user_id": user_id,
                "page_id": page_id,
                "is_pinned": 1 if request.is_pinned else 0,
                "pin_order": request.pin_order,
            })

        db.commit()

        return {
            "success": True,
            "page_id": page_id,
            "is_pinned": request.is_pinned,
            "pin_order": request.pin_order,
        }
    except SQLAlchemyError as e:
        logger.error(f"Error pinning page: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/pinned")
async def get_pinned_pages(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get user's pinned pages."""
    try:
        user_id = current_user.id

        result = db.execute(text("""
            SELECT
                p.id, p.path, p.name, p.icon, p.category,
                upo.pin_order
            FROM user_page_overrides upo
            JOIN pages p ON p.id = upo.page_id
            WHERE upo.user_id = :user_id
                AND upo.is_pinned = 1
                AND p.is_active = 1
            ORDER BY upo.pin_order NULLS LAST, p.name
        """), {"user_id": user_id})

        pinned = [
            {
                "id": row[0],
                "path": row[1],
                "name": row[2],
                "icon": row[3],
                "category": row[4],
                "pin_order": row[5],
            }
            for row in result.fetchall()
        ]

        return {"pinned_pages": pinned}
    except Exception as e:
        logger.error(f"Error fetching pinned pages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# ADMIN ENDPOINTS (for managing permissions)
# =============================================================================

@router.get("/admin/pages")
async def get_all_pages(
    category: Optional[str] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all pages (admin view)."""
    # Check admin permission
    user_role = getattr(current_user, 'permission_role', 'sales')
    if user_role != 'management':
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        query = """
            SELECT
                p.id, p.path, p.name, p.description, p.category,
                p.icon, p.parent_path, p.display_order, p.is_active,
                p.requires_auth, p.min_role, p.default_permissions,
                pc.name as category_name
            FROM pages p
            LEFT JOIN page_categories pc ON pc.code = p.category
            WHERE 1=1
        """
        params = {}

        if not include_inactive:
            query += " AND p.is_active = 1"

        if category:
            query += " AND p.category = :category"
            params["category"] = category

        query += " ORDER BY p.display_order"

        result = db.execute(text(query), params)

        pages = [
            {
                "id": row[0],
                "path": row[1],
                "name": row[2],
                "description": row[3],
                "category": row[4],
                "icon": row[5],
                "parent_path": row[6],
                "display_order": row[7],
                "is_active": bool(row[8]),
                "requires_auth": bool(row[9]),
                "min_role": row[10],
                "default_permissions": json.loads(row[11]) if row[11] else [],
                "category_name": row[12],
            }
            for row in result.fetchall()
        ]

        return {"pages": pages, "total": len(pages)}
    except Exception as e:
        logger.error(f"Error fetching all pages: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/pages/{page_id}/permissions")
async def get_page_permissions(
    page_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all permissions for a specific page."""
    user_role = getattr(current_user, 'permission_role', 'sales')
    if user_role != 'management':
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # Get page info
        page = db.execute(text("""
            SELECT id, path, name, min_role FROM pages WHERE id = :page_id
        """), {"page_id": page_id}).fetchone()

        if not page:
            raise HTTPException(status_code=404, detail="Page not found")

        # Get role permissions
        role_perms = db.execute(text("""
            SELECT role, can_view, can_edit, is_nav_visible
            FROM page_permissions
            WHERE page_id = :page_id
        """), {"page_id": page_id}).fetchall()

        # Get user overrides
        user_overrides = db.execute(text("""
            SELECT
                upo.id, u.id as user_id, u.email, u.full_name,
                upo.can_view, upo.can_edit, upo.is_nav_visible,
                upo.override_reason, upo.expires_at
            FROM user_page_overrides upo
            JOIN users u ON u.id = upo.user_id
            WHERE upo.page_id = :page_id
        """), {"page_id": page_id}).fetchall()

        return {
            "page": {
                "id": page[0],
                "path": page[1],
                "name": page[2],
                "min_role": page[3],
            },
            "role_permissions": [
                {
                    "role": r[0],
                    "can_view": bool(r[1]),
                    "can_edit": bool(r[2]),
                    "is_nav_visible": bool(r[3]),
                }
                for r in role_perms
            ],
            "user_overrides": [
                {
                    "id": o[0],
                    "user_id": o[1],
                    "email": o[2],
                    "name": o[3],
                    "can_view": bool(o[4]) if o[4] is not None else None,
                    "can_edit": bool(o[5]) if o[5] is not None else None,
                    "is_nav_visible": bool(o[6]) if o[6] is not None else None,
                    "override_reason": o[7],
                    "expires_at": o[8].isoformat() if o[8] else None,
                }
                for o in user_overrides
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching page permissions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/admin/pages/{page_id}/role/{role}")
async def update_role_permission(
    page_id: int,
    role: str,
    request: RolePagePermissionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update role-based permission for a page."""
    user_role = getattr(current_user, 'permission_role', 'sales')
    if user_role != 'management':
        raise HTTPException(status_code=403, detail="Admin access required")

    if role not in ['sales', 'operations', 'management']:
        raise HTTPException(status_code=400, detail="Invalid role")

    try:
        # Check if exists
        existing = db.execute(text("""
            SELECT id FROM page_permissions WHERE page_id = :page_id AND role = :role
        """), {"page_id": page_id, "role": role}).fetchone()

        if existing:
            db.execute(text("""
                UPDATE page_permissions
                SET can_view = :can_view, can_edit = :can_edit,
                    is_nav_visible = :is_nav_visible, updated_at = CURRENT_TIMESTAMP
                WHERE page_id = :page_id AND role = :role
            """), {
                "page_id": page_id,
                "role": role,
                "can_view": 1 if request.can_view else 0,
                "can_edit": 1 if request.can_edit else 0,
                "is_nav_visible": 1 if request.is_nav_visible else 0,
            })
        else:
            db.execute(text("""
                INSERT INTO page_permissions (page_id, role, can_view, can_edit, is_nav_visible)
                VALUES (:page_id, :role, :can_view, :can_edit, :is_nav_visible)
            """), {
                "page_id": page_id,
                "role": role,
                "can_view": 1 if request.can_view else 0,
                "can_edit": 1 if request.can_edit else 0,
                "is_nav_visible": 1 if request.is_nav_visible else 0,
            })

        db.commit()

        # Log the change
        logger.info(f"User {current_user.id} updated page {page_id} permissions for role {role}")

        return {
            "success": True,
            "page_id": page_id,
            "role": role,
            "permissions": {
                "can_view": request.can_view,
                "can_edit": request.can_edit,
                "is_nav_visible": request.is_nav_visible,
            },
        }
    except SQLAlchemyError as e:
        logger.error(f"Error updating role permission: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/users/{user_id}/pages/{page_id}/override")
async def create_user_page_override(
    user_id: int,
    page_id: int,
    request: UserPageOverrideRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create or update a user-specific page override."""
    admin_role = getattr(current_user, 'permission_role', 'sales')
    if admin_role != 'management':
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # Check if override exists
        existing = db.execute(text("""
            SELECT id FROM user_page_overrides WHERE user_id = :user_id AND page_id = :page_id
        """), {"user_id": user_id, "page_id": page_id}).fetchone()

        if existing:
            db.execute(text("""
                UPDATE user_page_overrides
                SET can_view = :can_view, can_edit = :can_edit, is_nav_visible = :is_nav_visible,
                    override_reason = :reason, expires_at = :expires_at,
                    granted_by = :granted_by, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND page_id = :page_id
            """), {
                "user_id": user_id,
                "page_id": page_id,
                "can_view": 1 if request.can_view else 0 if request.can_view is not None else None,
                "can_edit": 1 if request.can_edit else 0 if request.can_edit is not None else None,
                "is_nav_visible": 1 if request.is_nav_visible else 0 if request.is_nav_visible is not None else None,
                "reason": request.override_reason,
                "expires_at": request.expires_at,
                "granted_by": current_user.id,
            })
        else:
            db.execute(text("""
                INSERT INTO user_page_overrides
                    (user_id, page_id, can_view, can_edit, is_nav_visible, override_reason, expires_at, granted_by)
                VALUES
                    (:user_id, :page_id, :can_view, :can_edit, :is_nav_visible, :reason, :expires_at, :granted_by)
            """), {
                "user_id": user_id,
                "page_id": page_id,
                "can_view": 1 if request.can_view else 0 if request.can_view is not None else None,
                "can_edit": 1 if request.can_edit else 0 if request.can_edit is not None else None,
                "is_nav_visible": 1 if request.is_nav_visible else 0 if request.is_nav_visible is not None else None,
                "reason": request.override_reason,
                "expires_at": request.expires_at,
                "granted_by": current_user.id,
            })

        db.commit()

        logger.info(f"User {current_user.id} created page override for user {user_id} on page {page_id}")

        return {
            "success": True,
            "user_id": user_id,
            "page_id": page_id,
            "override": {
                "can_view": request.can_view,
                "can_edit": request.can_edit,
                "is_nav_visible": request.is_nav_visible,
                "expires_at": request.expires_at.isoformat() if request.expires_at else None,
            },
        }
    except SQLAlchemyError as e:
        logger.error(f"Error creating user page override: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/admin/users/{user_id}/pages/{page_id}/override")
async def delete_user_page_override(
    user_id: int,
    page_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete a user-specific page override."""
    admin_role = getattr(current_user, 'permission_role', 'sales')
    if admin_role != 'management':
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        result = db.execute(text("""
            DELETE FROM user_page_overrides WHERE user_id = :user_id AND page_id = :page_id
        """), {"user_id": user_id, "page_id": page_id})

        db.commit()

        return {"success": True, "deleted": result.rowcount > 0}
    except SQLAlchemyError as e:
        logger.error(f"Error deleting user page override: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/users/{user_id}/overrides")
async def get_user_overrides(
    user_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all page overrides for a specific user."""
    admin_role = getattr(current_user, 'permission_role', 'sales')
    if admin_role != 'management':
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        result = db.execute(text("""
            SELECT
                upo.id, p.id as page_id, p.path, p.name,
                upo.can_view, upo.can_edit, upo.is_nav_visible,
                upo.is_pinned, upo.override_reason, upo.expires_at,
                g.full_name as granted_by_name
            FROM user_page_overrides upo
            JOIN pages p ON p.id = upo.page_id
            LEFT JOIN users g ON g.id = upo.granted_by
            WHERE upo.user_id = :user_id
            ORDER BY p.display_order
        """), {"user_id": user_id})

        overrides = [
            {
                "id": row[0],
                "page_id": row[1],
                "path": row[2],
                "name": row[3],
                "can_view": bool(row[4]) if row[4] is not None else None,
                "can_edit": bool(row[5]) if row[5] is not None else None,
                "is_nav_visible": bool(row[6]) if row[6] is not None else None,
                "is_pinned": bool(row[7]),
                "override_reason": row[8],
                "expires_at": row[9].isoformat() if row[9] else None,
                "granted_by": row[10],
            }
            for row in result.fetchall()
        ]

        return {"user_id": user_id, "overrides": overrides}
    except Exception as e:
        logger.error(f"Error fetching user overrides: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/bulk-update")
async def bulk_update_permissions(
    request: BulkPagePermissionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Bulk update permissions for multiple pages."""
    admin_role = getattr(current_user, 'permission_role', 'sales')
    if admin_role != 'management':
        raise HTTPException(status_code=403, detail="Admin access required")

    if request.role not in ['sales', 'operations', 'management']:
        raise HTTPException(status_code=400, detail="Invalid role")

    try:
        updated = 0
        for page_id in request.page_ids:
            # Check if exists
            existing = db.execute(text("""
                SELECT id FROM page_permissions WHERE page_id = :page_id AND role = :role
            """), {"page_id": page_id, "role": request.role}).fetchone()

            if existing:
                db.execute(text("""
                    UPDATE page_permissions
                    SET can_view = :can_view, can_edit = :can_edit, updated_at = CURRENT_TIMESTAMP
                    WHERE page_id = :page_id AND role = :role
                """), {
                    "page_id": page_id,
                    "role": request.role,
                    "can_view": 1 if request.can_view else 0,
                    "can_edit": 1 if request.can_edit else 0,
                })
            else:
                db.execute(text("""
                    INSERT INTO page_permissions (page_id, role, can_view, can_edit, is_nav_visible)
                    VALUES (:page_id, :role, :can_view, :can_edit, :can_view)
                """), {
                    "page_id": page_id,
                    "role": request.role,
                    "can_view": 1 if request.can_view else 0,
                    "can_edit": 1 if request.can_edit else 0,
                })
            updated += 1

        db.commit()

        return {"success": True, "updated_count": updated}
    except SQLAlchemyError as e:
        logger.error(f"Error bulk updating permissions: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# ACCESS LOGGING
# =============================================================================

@router.post("/log-access")
async def log_page_access(
    page_path: str,
    access_granted: bool,
    denial_reason: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Log a page access attempt."""
    try:
        # Get page ID
        page = db.execute(text("""
            SELECT id FROM pages WHERE path = :path
        """), {"path": page_path}).fetchone()

        page_id = page[0] if page else None

        db.execute(text("""
            INSERT INTO page_access_log
                (user_id, page_id, page_path, access_type, access_granted, denial_reason, ip_address, user_agent)
            VALUES
                (:user_id, :page_id, :page_path, :access_type, :access_granted, :denial_reason, :ip, :ua)
        """), {
            "user_id": current_user.id,
            "page_id": page_id,
            "page_path": page_path,
            "access_type": "view" if access_granted else "denied",
            "access_granted": 1 if access_granted else 0,
            "denial_reason": denial_reason,
            "ip": request.client.host if request else None,
            "ua": request.headers.get("User-Agent") if request else None,
        })

        db.commit()

        return {"logged": True}
    except SQLAlchemyError as e:
        logger.error(f"Error logging page access: {e}")
        # Don't fail the request if logging fails
        return {"logged": False, "error": "Internal server error"}


@router.get("/admin/access-log")
async def get_access_log(
    user_id: Optional[int] = None,
    page_id: Optional[int] = None,
    denied_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get page access logs (admin only)."""
    admin_role = getattr(current_user, 'permission_role', 'sales')
    if admin_role != 'management':
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        query = """
            SELECT
                pal.id, pal.user_id, u.email, u.full_name,
                pal.page_id, p.path, p.name,
                pal.access_type, pal.access_granted, pal.denial_reason,
                pal.ip_address, pal.accessed_at
            FROM page_access_log pal
            LEFT JOIN users u ON u.id = pal.user_id
            LEFT JOIN pages p ON p.id = pal.page_id
            WHERE 1=1
        """
        params = {"limit": limit, "offset": offset}

        if user_id:
            query += " AND pal.user_id = :user_id"
            params["user_id"] = user_id

        if page_id:
            query += " AND pal.page_id = :page_id"
            params["page_id"] = page_id

        if denied_only:
            query += " AND pal.access_granted = 0"

        query += " ORDER BY pal.accessed_at DESC LIMIT :limit OFFSET :offset"

        result = db.execute(text(query), params)

        logs = [
            {
                "id": row[0],
                "user_id": row[1],
                "email": row[2],
                "user_name": row[3],
                "page_id": row[4],
                "page_path": row[5],
                "page_name": row[6],
                "access_type": row[7],
                "access_granted": bool(row[8]),
                "denial_reason": row[9],
                "ip_address": row[10],
                "accessed_at": row[11].isoformat() if row[11] else None,
            }
            for row in result.fetchall()
        ]

        return {"logs": logs, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"Error fetching access logs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# MIGRATION ENDPOINT
# ============================================================================

@router.post("/admin/run-migration")
async def run_page_permissions_migration(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin key for migration"),
    db: Session = Depends(get_db),
):
    """
    Run the page permissions migration on the production database.
    Requires admin_key for authorization.
    """
    import os
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        results = {"tables_created": [], "data_seeded": [], "errors": []}

        # Create page_categories table
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS page_categories (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    display_name VARCHAR(200) NOT NULL,
                    description TEXT,
                    icon VARCHAR(50),
                    display_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            results["tables_created"].append("page_categories")
        except SQLAlchemyError as e:
            if "already exists" not in str(e).lower():
                logger.error(f"page_categories creation failed: {e}")
                results["errors"].append("page_categories: creation failed")

        # Create pages table
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS pages (
                    id SERIAL PRIMARY KEY,
                    category_id INTEGER REFERENCES page_categories(id),
                    name VARCHAR(200) NOT NULL,
                    path VARCHAR(500) NOT NULL UNIQUE,
                    description TEXT,
                    icon VARCHAR(50),
                    display_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    requires_feature_flag VARCHAR(100),
                    parent_page_id INTEGER REFERENCES pages(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            results["tables_created"].append("pages")
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.error(f"pages table creation failed: {e}")
                results["errors"].append("pages: creation failed")

        # Create page_permissions table
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS page_permissions (
                    id SERIAL PRIMARY KEY,
                    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
                    role VARCHAR(50) NOT NULL,
                    can_view BOOLEAN DEFAULT FALSE,
                    can_edit BOOLEAN DEFAULT FALSE,
                    can_delete BOOLEAN DEFAULT FALSE,
                    can_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(page_id, role)
                )
            """))
            results["tables_created"].append("page_permissions")
        except SQLAlchemyError as e:
            if "already exists" not in str(e).lower():
                logger.error(f"page_permissions table creation failed: {e}")
                results["errors"].append("page_permissions: creation failed")

        # Create user_page_overrides table
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS user_page_overrides (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
                    can_view BOOLEAN,
                    can_edit BOOLEAN,
                    can_delete BOOLEAN,
                    can_admin BOOLEAN,
                    override_reason TEXT,
                    granted_by INTEGER,
                    expires_at TIMESTAMP,
                    is_pinned BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, page_id)
                )
            """))
            results["tables_created"].append("user_page_overrides")
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.error(f"user_page_overrides table creation failed: {e}")
                results["errors"].append("user_page_overrides: creation failed")

        # Create page_access_log table
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS page_access_log (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    page_id INTEGER REFERENCES pages(id),
                    page_path VARCHAR(500),
                    access_type VARCHAR(50) DEFAULT 'view',
                    access_granted BOOLEAN NOT NULL,
                    denial_reason TEXT,
                    ip_address VARCHAR(45),
                    user_agent TEXT,
                    session_id VARCHAR(100),
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            results["tables_created"].append("page_access_log")
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.error(f"page_access_log table creation failed: {e}")
                results["errors"].append("page_access_log: creation failed")

        db.commit()

        # Check if categories exist before seeding
        category_count = db.execute(text("SELECT COUNT(*) FROM page_categories")).scalar()

        if category_count == 0:
            # Seed categories
            categories = [
                ("dashboard", "Dashboard", "Main dashboard and overview pages", "dashboard", 1),
                ("crm", "CRM", "Customer relationship management", "users", 2),
                ("pipeline", "Pipeline", "Loan pipeline management", "trending-up", 3),
                ("documents", "Documents", "Document management", "file-text", 4),
                ("communications", "Communications", "Email, SMS, and calls", "message-circle", 5),
                ("settings", "Settings", "System settings and configuration", "settings", 6),
                ("admin", "Administration", "Admin-only features", "shield", 7),
                ("reports", "Reports", "Analytics and reporting", "bar-chart", 8),
                ("marketing", "Marketing", "Marketing tools", "megaphone", 9),
                ("integrations", "Integrations", "Third-party integrations", "link", 10),
                ("team", "Team", "Team management", "users", 11),
                ("ai", "AI Tools", "AI-powered features", "cpu", 12),
            ]

            for name, display_name, description, icon, order in categories:
                try:
                    db.execute(text("""
                        INSERT INTO page_categories (name, display_name, description, icon, display_order)
                        VALUES (:name, :display_name, :description, :icon, :order)
                        ON CONFLICT (name) DO NOTHING
                    """), {"name": name, "display_name": display_name, "description": description, "icon": icon, "order": order})
                except Exception as e:
                    logger.error(f"Error seeding category {name}: {e}")

            results["data_seeded"].append(f"categories: {len(categories)}")
            db.commit()

        # Check if pages exist before seeding
        page_count = db.execute(text("SELECT COUNT(*) FROM pages")).scalar()

        if page_count == 0:
            # Get category IDs
            cat_result = db.execute(text("SELECT id, name FROM page_categories"))
            category_map = {row[1]: row[0] for row in cat_result.fetchall()}

            # Seed core pages
            pages = [
                (category_map.get("dashboard"), "Dashboard", "/dashboard", "Main dashboard", "home", 1),
                (category_map.get("crm"), "Leads", "/leads", "Lead management", "user-plus", 1),
                (category_map.get("crm"), "Clients", "/clients", "Client management", "users", 2),
                (category_map.get("pipeline"), "Pipeline", "/pipeline", "Loan pipeline", "git-branch", 1),
                (category_map.get("pipeline"), "Loans", "/loans", "Active loans", "briefcase", 2),
                (category_map.get("documents"), "Smart Docs", "/smart-docs", "Document management", "file-text", 1),
                (category_map.get("communications"), "Email", "/email", "Email inbox", "mail", 1),
                (category_map.get("communications"), "SMS", "/sms", "SMS messaging", "message-square", 2),
                (category_map.get("settings"), "Settings", "/settings", "User settings", "settings", 1),
                (category_map.get("admin"), "Users", "/admin/users", "User management", "users", 1),
                (category_map.get("admin"), "Roles", "/admin/roles", "Role management", "shield", 2),
                (category_map.get("reports"), "Analytics", "/reports/analytics", "Analytics dashboard", "bar-chart-2", 1),
                (category_map.get("ai"), "AI Assistant", "/ai-assistant", "AI-powered assistant", "cpu", 1),
            ]

            for cat_id, name, path, description, icon, order in pages:
                if cat_id:
                    try:
                        db.execute(text("""
                            INSERT INTO pages (category_id, name, path, description, icon, display_order)
                            VALUES (:cat_id, :name, :path, :description, :icon, :order)
                            ON CONFLICT (path) DO NOTHING
                        """), {"cat_id": cat_id, "name": name, "path": path, "description": description, "icon": icon, "order": order})
                    except Exception as e:
                        logger.error(f"Error seeding page {name}: {e}")

            results["data_seeded"].append(f"pages: {len(pages)}")
            db.commit()

            # Seed default permissions for admin role
            page_result = db.execute(text("SELECT id FROM pages"))
            page_ids = [row[0] for row in page_result.fetchall()]

            for page_id in page_ids:
                try:
                    db.execute(text("""
                        INSERT INTO page_permissions (page_id, role, can_view, can_edit, can_delete, can_admin)
                        VALUES (:page_id, 'admin', TRUE, TRUE, TRUE, TRUE)
                        ON CONFLICT (page_id, role) DO NOTHING
                    """), {"page_id": page_id})
                except Exception as e:
                    logger.error(f"Error seeding admin permission for page {page_id}: {e}")

            results["data_seeded"].append(f"permissions: {len(page_ids)} pages x admin role")
            db.commit()

        # Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_pages_category ON pages(category_id)",
            "CREATE INDEX IF NOT EXISTS idx_pages_path ON pages(path)",
            "CREATE INDEX IF NOT EXISTS idx_page_permissions_page ON page_permissions(page_id)",
            "CREATE INDEX IF NOT EXISTS idx_page_permissions_role ON page_permissions(role)",
            "CREATE INDEX IF NOT EXISTS idx_user_page_overrides_user ON user_page_overrides(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_page_access_log_user ON page_access_log(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_page_access_log_accessed ON page_access_log(accessed_at)",
        ]

        for idx_sql in indexes:
            try:
                db.execute(text(idx_sql))
            except Exception as e:
                logger.error(f"Error creating index: {e}")

        db.commit()
        results["indexes_created"] = len(indexes)

        return {
            "success": len(results["errors"]) == 0,
            "message": "Page permissions migration completed",
            "results": results
        }

    except SQLAlchemyError as e:
        logger.error(f"Migration error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
