"""
Module Subscription Routes

API endpoints for managing subscription modules.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

# Import from main app
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.module_service import ModuleService

router = APIRouter(prefix="/api/v1/modules", tags=["modules"])


# Pydantic models for request/response
class ModuleResponse(BaseModel):
    id: int
    module_key: str
    module_name: str
    description: Optional[str]
    category: str
    icon: str
    monthly_price: float
    annual_price: float
    included_features: List[str]
    gated_routes: List[str]
    is_enabled: Optional[bool] = None
    is_trial: Optional[bool] = None
    trial_ends_at: Optional[str] = None


class EnableModuleRequest(BaseModel):
    module_key: str
    is_trial: bool = False
    trial_days: int = 14


class ModuleCheckResponse(BaseModel):
    has_access: bool
    module_key: str
    module_name: Optional[str] = None
    monthly_price: Optional[float] = None


class PricingSummaryResponse(BaseModel):
    base_price: float
    modules_price: float
    total_monthly: float
    total_annual: float
    enabled_modules: List[str]
    premium_modules_count: int


class NavigationAccessResponse(BaseModel):
    enabled_modules: List[str]
    route_access: dict


# Database and user dependencies - injected from main app
_get_db = None
_get_current_user = None


def set_dependencies(get_db_func, get_current_user_func):
    """Set the database and user dependencies from main app."""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


def get_db():
    """Get database session."""
    if _get_db is None:
        raise RuntimeError("Database dependency not configured. Call set_dependencies first.")
    return _get_db()


def get_current_user():
    """Get current user."""
    if _get_current_user is None:
        raise RuntimeError("User dependency not configured. Call set_dependencies first.")
    return _get_current_user()


@router.get("/available", response_model=List[ModuleResponse])
async def get_available_modules(db: Session = Depends(get_db)):
    """Get all available subscription modules with pricing."""
    modules = ModuleService.get_all_modules(db)
    return modules


@router.get("/my-modules")
async def get_my_modules(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get current user's organization modules with enabled status."""
    org_id = current_user.get('organization_id')
    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    modules = ModuleService.get_organization_modules_detailed(db, org_id)
    pricing = ModuleService.get_pricing_summary(db, org_id)

    return {
        'modules': modules,
        'pricing': pricing
    }


@router.get("/check/{module_key}")
async def check_module_access(
    module_key: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Check if current user's organization has access to a specific module."""
    org_id = current_user.get('organization_id')
    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    has_access = ModuleService.has_module(db, org_id, module_key)
    module = ModuleService.get_module_by_key(db, module_key)

    return {
        'has_access': has_access,
        'module_key': module_key,
        'module_name': module['module_name'] if module else None,
        'monthly_price': module['monthly_price'] if module else None
    }


@router.get("/check-feature/{feature_key}")
async def check_feature_access(
    feature_key: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Check if current user's organization has access to a specific feature."""
    org_id = current_user.get('organization_id')
    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    has_access = ModuleService.has_feature(db, org_id, feature_key)

    return {
        'has_access': has_access,
        'feature_key': feature_key
    }


@router.get("/check-route")
async def check_route_access(
    route: str = Query(..., description="Route path to check"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Check if a route is accessible based on organization's modules."""
    org_id = current_user.get('organization_id')
    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    access = ModuleService.is_route_accessible(db, org_id, route)

    return access


@router.get("/navigation")
async def get_navigation_access(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get navigation items with lock status based on modules."""
    org_id = current_user.get('organization_id')
    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    return ModuleService.get_navigation_with_access(db, org_id)


@router.get("/pricing")
async def get_pricing_summary(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get pricing summary for current organization's modules."""
    org_id = current_user.get('organization_id')
    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    return ModuleService.get_pricing_summary(db, org_id)


@router.post("/enable")
async def enable_module(
    request: EnableModuleRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Enable a module for the current organization."""
    org_id = current_user.get('organization_id')
    user_id = current_user.get('id')

    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    # Check if user has admin permissions
    role = current_user.get('role') or current_user.get('permission_role')
    if role not in ['admin', 'owner', 'leadership']:
        raise HTTPException(status_code=403, detail="Only admins can enable modules")

    try:
        result = ModuleService.enable_module(
            db=db,
            organization_id=org_id,
            module_key=request.module_key,
            enabled_by=user_id,
            is_trial=request.is_trial,
            trial_days=request.trial_days
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/disable")
async def disable_module(
    module_key: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Disable a module for the current organization."""
    org_id = current_user.get('organization_id')

    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    # Check if user has admin permissions
    role = current_user.get('role') or current_user.get('permission_role')
    if role not in ['admin', 'owner', 'leadership']:
        raise HTTPException(status_code=403, detail="Only admins can disable modules")

    try:
        result = ModuleService.disable_module(db, org_id, module_key)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Admin endpoints for managing modules across organizations
@router.get("/admin/organization/{organization_id}")
async def admin_get_org_modules(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Admin: Get modules for a specific organization."""
    # Check admin permission
    role = current_user.get('role') or current_user.get('permission_role')
    if role != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")

    modules = ModuleService.get_organization_modules_detailed(db, organization_id)
    pricing = ModuleService.get_pricing_summary(db, organization_id)

    return {
        'organization_id': organization_id,
        'modules': modules,
        'pricing': pricing
    }


@router.post("/admin/organization/{organization_id}/enable")
async def admin_enable_module(
    organization_id: int,
    request: EnableModuleRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Admin: Enable a module for a specific organization."""
    # Check admin permission
    role = current_user.get('role') or current_user.get('permission_role')
    if role != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")

    user_id = current_user.get('id')

    try:
        result = ModuleService.enable_module(
            db=db,
            organization_id=organization_id,
            module_key=request.module_key,
            enabled_by=user_id,
            is_trial=request.is_trial,
            trial_days=request.trial_days
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Public endpoint for module info (no auth required)
@router.get("/public/list")
async def get_public_modules(db: Session = Depends(get_db)):
    """Get public module list for marketing/signup pages."""
    modules = ModuleService.get_all_modules(db)

    # Return simplified version for public display
    return [
        {
            'module_key': m['module_key'],
            'module_name': m['module_name'],
            'description': m['description'],
            'category': m['category'],
            'icon': m['icon'],
            'monthly_price': m['monthly_price'],
            'annual_price': m['annual_price'],
            'included_features': m['included_features']
        }
        for m in modules
    ]


# Admin endpoint for running migration (no auth, uses admin key)
@router.post("/admin/run-migration")
async def run_module_migration(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db),
):
    """
    Run the subscription modules migration.
    Creates tables and seeds module definitions.
    """
    # Simple admin key check
    if admin_key != "perennia-admin-2024":
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from migrations.add_subscription_modules import run_migration

        # Get the engine from the session's bind
        engine = db.get_bind()
        success = run_migration(engine)

        if success:
            return {
                "success": True,
                "message": "Subscription modules migration completed successfully",
            }
        else:
            raise HTTPException(status_code=500, detail="Migration failed")
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Migration import failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")
