"""
Module Subscription Routes

API endpoints for managing subscription modules.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

# Import from main app
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.module_service import ModuleService
from sqlalchemy.exc import SQLAlchemyError

_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

router = APIRouter(prefix="/api/v1/modules", tags=["modules"])

# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


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
# These are stored as the actual dependency functions from main.py
_get_db = None
_get_current_user = None


def set_dependencies(get_db_func, get_current_user_func):
    """Set the database and user dependencies from main app."""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


def get_db():
    """
    Wrapper for database dependency.
    Yields from the underlying generator.
    """
    if _get_db is None:
        raise RuntimeError("Database dependency not configured. Call set_dependencies first.")
    # Yield from the generator
    yield from _get_db()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Async wrapper for current user dependency.
    Calls the injected dependency function with proper parameters.
    """
    if _get_current_user is None:
        raise RuntimeError("User dependency not configured. Call set_dependencies first.")
    # Call the stored async function and await it
    return await _get_current_user(token=token, request=request, db=db)


@router.get("/available", response_model=List[ModuleResponse])
async def get_available_modules(db: Session = Depends(get_db)):
    """Get all available subscription modules with pricing."""
    modules = ModuleService.get_all_modules(db)
    return modules


@router.get("/my-modules")
async def get_my_modules(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get current user's organization modules with enabled status."""
    # Default response when modules system is unavailable
    default_response = {
        'modules': [
            {
                "module_key": "base",
                "module_name": "Base Package",
                "description": "Core CRM features",
                "category": "base",
                "icon": "home",
                "monthly_price": 99.0,
                "annual_price": 990.0,
                "included_features": ["Dashboard", "Leads", "Loans", "Tasks", "Calendar"],
                "gated_routes": [],
                "is_enabled": True,
                "enabled_at": None,
                "is_trial": False,
                "trial_ends_at": None,
            }
        ],
        'pricing': {
            "base_price": 99.0,
            "modules_price": 0,
            "total_monthly": 99.0,
            "total_annual": 990.0,
            "enabled_modules": ["base"],
            "premium_modules_count": 0,
        }
    }

    # Handle case where current_user might be None or invalid
    if current_user is None:
        logger.warning("get_my_modules: current_user is None, returning defaults")
        return default_response

    try:
        org_id = getattr(current_user, 'organization_id', None)
        user_id = getattr(current_user, 'id', None)
        user_email = getattr(current_user, 'email', None)
        user_role = getattr(current_user, 'role', None) or getattr(current_user, 'permission_role', None)

        # Default to org 1 if user doesn't have an org (single-tenant fallback)
        if not org_id:
            # For admins or if no org set, default to org 1
            org_id = 1
            logger.info(f"User {user_id} ({user_email}) has no organization_id, defaulting to org 1")

        modules = ModuleService.get_organization_modules_detailed(db, org_id)
        pricing = ModuleService.get_pricing_summary(db, org_id)

        # If no modules returned (table might not exist), return default
        if not modules:
            logger.warning("No modules returned from ModuleService, using defaults")
            return default_response

        return {
            'modules': modules,
            'pricing': pricing
        }
    except Exception as e:
        logger.error(f"Error fetching user modules: {e}")
        return default_response


@router.get("/check/{module_key}")
async def check_module_access(
    module_key: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Check if current user's organization has access to a specific module."""
    org_id = getattr(current_user, 'organization_id', None)
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
    current_user = Depends(get_current_user)
):
    """Check if current user's organization has access to a specific feature."""
    org_id = getattr(current_user, 'organization_id', None)
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
    current_user = Depends(get_current_user)
):
    """Check if a route is accessible based on organization's modules."""
    org_id = getattr(current_user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    access = ModuleService.is_route_accessible(db, org_id, route)

    return access


@router.get("/navigation")
async def get_navigation_access(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get navigation items with lock status based on modules."""
    org_id = getattr(current_user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    return ModuleService.get_navigation_with_access(db, org_id)


@router.get("/pricing")
async def get_pricing_summary(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get pricing summary for current organization's modules."""
    org_id = getattr(current_user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    return ModuleService.get_pricing_summary(db, org_id)


@router.post("/enable")
async def enable_module(
    request: EnableModuleRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Enable a module for the current organization."""
    org_id = getattr(current_user, 'organization_id', None)
    user_id = getattr(current_user, 'id', None)

    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    # Check if user has admin permissions
    role = getattr(current_user, 'role', None) or getattr(current_user, 'permission_role', None)
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
        raise HTTPException(status_code=400, detail="Bad request")


@router.post("/disable")
async def disable_module(
    module_key: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Disable a module for the current organization."""
    org_id = getattr(current_user, 'organization_id', None)

    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    # Check if user has admin permissions
    role = getattr(current_user, 'role', None) or getattr(current_user, 'permission_role', None)
    if role not in ['admin', 'owner', 'leadership']:
        raise HTTPException(status_code=403, detail="Only admins can disable modules")

    try:
        result = ModuleService.disable_module(db, org_id, module_key)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")


# Admin endpoints for managing modules across organizations
@router.get("/admin/organization/{organization_id}")
async def admin_get_org_modules(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Admin: Get modules for a specific organization."""
    # Check admin permission
    role = getattr(current_user, 'role', None) or getattr(current_user, 'permission_role', None)
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
    current_user = Depends(get_current_user)
):
    """Admin: Enable a module for a specific organization."""
    # Check admin permission
    role = getattr(current_user, 'role', None) or getattr(current_user, 'permission_role', None)
    if role != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")

    user_id = getattr(current_user, 'id', None)

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
        raise HTTPException(status_code=400, detail="Bad request")


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
):
    """
    Run the subscription modules migration.
    Creates tables and seeds module definitions.
    """
    # Simple admin key check
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from migrations.add_subscription_modules import run_migration
        from database import engine

        success = run_migration(engine)

        if success:
            return {
                "success": True,
                "message": "Subscription modules migration completed successfully",
            }
        else:
            raise HTTPException(status_code=500, detail="Migration failed")
    except ImportError as e:
        raise HTTPException(status_code=500, detail="Migration import failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Migration failed")


@router.get("/admin/check-users")
async def check_users_debug(
    admin_key: str = Query(..., description="Admin API key"),
    org_id: int = Query(1, description="Organization ID"),
):
    """Debug endpoint to check users and their organization associations."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from database import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            # Get all users with their org info
            result = conn.execute(text("""
                SELECT id, email, role, permission_role, organization_id
                FROM users
                ORDER BY id
                LIMIT 20
            """))
            users = [
                {
                    "id": row[0],
                    "email": row[1],
                    "role": row[2],
                    "permission_role": row[3],
                    "organization_id": row[4]
                }
                for row in result.fetchall()
            ]

            # Get org modules for specified org
            org_result = conn.execute(text("""
                SELECT module_key, is_enabled FROM organization_modules
                WHERE organization_id = :org_id
            """), {"org_id": org_id})
            org_modules = [{"key": r[0], "enabled": r[1]} for r in org_result.fetchall()]

            return {
                "users": users,
                "org_modules": org_modules
            }
    except SQLAlchemyError as e:
        return {"error": "Internal server error"}


@router.get("/admin/debug")
async def debug_modules(
    admin_key: str = Query(..., description="Admin API key"),
    enable_all: bool = Query(False, description="Enable all modules for org 1"),
    org_id: int = Query(1, description="Organization ID"),
    set_admin_user: int = Query(None, description="User ID to set as admin"),
    check_user: int = Query(None, description="Check user info by ID"),
):
    """Debug endpoint to check module data and optionally enable all modules."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from database import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            results = {}

            # Check user info if requested
            if check_user:
                user_result = conn.execute(text("""
                    SELECT id, email, role, permission_role, organization_id
                    FROM users WHERE id = :user_id
                """), {"user_id": check_user})
                user_row = user_result.fetchone()
                if user_row:
                    results["user_info"] = {
                        "id": user_row[0],
                        "email": user_row[1],
                        "role": user_row[2],
                        "permission_role": user_row[3],
                        "organization_id": user_row[4]
                    }
                    # Also check enabled modules for user's org
                    if user_row[4]:
                        org_modules = conn.execute(text("""
                            SELECT module_key, is_enabled FROM organization_modules
                            WHERE organization_id = :org_id
                        """), {"org_id": user_row[4]})
                        results["user_org_modules"] = [
                            {"key": r[0], "enabled": r[1]} for r in org_modules.fetchall()
                        ]

            # Enable all modules if requested
            if enable_all:
                premium_modules = [
                    'ai_assistant', 'partner_portals', 'video_os', 'voice_os',
                    'recruiting_suite', 'conversation_intelligence',
                    'advanced_analytics', 'integrations'
                ]
                enabled = []
                for module_key in premium_modules:
                    try:
                        conn.execute(text("""
                            INSERT INTO organization_modules
                            (organization_id, module_key, is_enabled, enabled_at, is_trial, created_at, updated_at)
                            VALUES (:org_id, :module_key, true, NOW(), false, NOW(), NOW())
                            ON CONFLICT (organization_id, module_key)
                            DO UPDATE SET is_enabled = true, enabled_at = NOW(), is_trial = false, disabled_at = NULL, updated_at = NOW()
                        """), {"org_id": org_id, "module_key": module_key})
                        enabled.append(module_key)
                    except SQLAlchemyError as e:
                        pass
                conn.commit()
                results["enabled_modules"] = enabled
                results["enable_message"] = f"Enabled {len(enabled)} modules for org {org_id}"

            # Set user as admin if requested
            if set_admin_user:
                try:
                    # Update user role
                    conn.execute(text("""
                        UPDATE users SET permission_role = 'admin', role = 'admin' WHERE id = :user_id
                    """), {"user_id": set_admin_user})
                    conn.commit()  # Commit immediately so role update is saved
                    results["admin_set"] = f"User {set_admin_user} set as admin"

                    # Try to grant admin permissions in user_permission_overrides table
                    admin_perms = ['admin.view', 'admin.manage', 'system.admin', 'permissions.view_all', 'team.manage_permissions']
                    for perm in admin_perms:
                        try:
                            conn.execute(text("""
                                INSERT INTO user_permission_overrides
                                (user_id, permission_key, granted, is_temporary, granted_by, granted_at)
                                VALUES (:user_id, :perm_key, true, false, :user_id, NOW())
                                ON CONFLICT (user_id, permission_key)
                                DO UPDATE SET granted = true, granted_at = NOW()
                            """), {"user_id": set_admin_user, "perm_key": perm})
                            conn.commit()
                        except Exception as inner_e:
                            try:
                                conn.rollback()  # Rollback failed permission insert
                            except Exception:
                                pass
                            results.setdefault("perm_errors", []).append(f"{perm}: {str(inner_e)[:50]}")

                except SQLAlchemyError as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    results["admin_error"] = str(e)

            # Check if table exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'subscription_modules'
                )
            """))
            table_exists = result.scalar()

            if not table_exists:
                return {"table_exists": False, "modules": [], "count": 0, **results}

            # Get count
            result = conn.execute(text("SELECT COUNT(*) FROM subscription_modules"))
            count = result.scalar()

            # Get modules
            result = conn.execute(text("SELECT module_key, module_name, is_active FROM subscription_modules"))
            modules = [{"key": row[0], "name": row[1], "active": row[2]} for row in result.fetchall()]

            return {
                "table_exists": table_exists,
                "count": count,
                "modules": modules,
                **results
            }
    except SQLAlchemyError as e:
        return {"error": "Internal server error"}


@router.post("/admin/enable-all")
async def enable_all_modules(
    organization_id: int = Query(None, description="Organization ID (defaults to 1)"),
    admin_key: str = Query(..., description="Admin API key"),
):
    """
    Enable all premium modules for an organization.
    Removes all UPGRADE badges by enabling every module.
    """
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    org_id = organization_id or 1

    try:
        from database import engine
        from sqlalchemy import text
        from datetime import datetime

        # All premium module keys
        premium_modules = [
            'ai_assistant',
            'partner_portals',
            'video_os',
            'voice_os',
            'recruiting_suite',
            'conversation_intelligence',
            'advanced_analytics',
            'integrations'
        ]

        enabled = []
        errors = []

        with engine.connect() as conn:
            for module_key in premium_modules:
                try:
                    # Upsert the module for the organization
                    conn.execute(text("""
                        INSERT INTO organization_modules
                        (organization_id, module_key, is_enabled, enabled_at, is_trial, created_at, updated_at)
                        VALUES (:org_id, :module_key, true, NOW(), false, NOW(), NOW())
                        ON CONFLICT (organization_id, module_key)
                        DO UPDATE SET
                            is_enabled = true,
                            enabled_at = NOW(),
                            is_trial = false,
                            disabled_at = NULL,
                            updated_at = NOW()
                    """), {"org_id": org_id, "module_key": module_key})
                    enabled.append(module_key)
                except SQLAlchemyError as e:
                    errors.append({"module": module_key, "error": "Internal server error"})

            conn.commit()

        return {
            "success": True,
            "organization_id": org_id,
            "enabled_modules": enabled,
            "errors": errors if errors else None,
            "message": f"All {len(enabled)} premium modules enabled for organization {org_id}"
        }
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Failed to enable modules")


@router.get("/admin/check-integrations")
async def check_integrations_config(
    admin_key: str = Query(..., description="Admin API key"),
):
    """Check if integration credentials are configured."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    import os

    integrations_status = {
        "salesforce": {
            "client_id_set": bool(os.getenv("SALESFORCE_CLIENT_ID")),
            "client_secret_set": bool(os.getenv("SALESFORCE_CLIENT_SECRET")),
            "redirect_uri": os.getenv("SALESFORCE_REDIRECT_URI", "not set"),
        },
        "hubspot": {
            "client_id_set": bool(os.getenv("HUBSPOT_CLIENT_ID")),
            "client_secret_set": bool(os.getenv("HUBSPOT_CLIENT_SECRET")),
        },
        "google_calendar": {
            "client_id_set": bool(os.getenv("GOOGLE_CLIENT_ID")),
            "client_secret_set": bool(os.getenv("GOOGLE_CLIENT_SECRET")),
        },
        "slack": {
            "client_id_set": bool(os.getenv("SLACK_CLIENT_ID")),
            "client_secret_set": bool(os.getenv("SLACK_CLIENT_SECRET")),
        },
        "openai": {
            "api_key_set": bool(os.getenv("OPENAI_API_KEY")),
        },
        "anthropic": {
            "api_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        },
    }

    return {
        "integrations": integrations_status,
        "frontend_url": os.getenv("FRONTEND_URL", "not set"),
        "base_url": os.getenv("BASE_URL", "not set"),
    }


@router.post("/admin/clear-demo-data")
async def clear_demo_data(
    admin_key: str = Query(..., description="Admin API key"),
    confirm: bool = Query(False, description="Must be true to confirm deletion"),
):
    """
    Clear all demo/sample data from the CRM.
    Removes leads, loans, tasks, MUM data, reconciliation tasks, smart docs, etc.
    Preserves system users and settings.
    """
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    if not confirm:
        return {
            "success": False,
            "message": "Add confirm=true to actually delete data. This will remove all leads, loans, tasks, etc.",
            "warning": "This action cannot be undone!"
        }

    try:
        from database import engine
        from sqlalchemy import text

        deleted = {}
        errors = []

        with engine.connect() as conn:
            # List of tables to clear (order matters due to foreign keys)
            # Using TRUNCATE with CASCADE for faster deletion and to handle FK constraints
            tables_to_truncate = [
                # Child tables first (for safety, though CASCADE should handle it)
                "task_comments",
                "task_attachments",
                "loan_notes",
                "loan_documents",
                "loan_conditions",
                "loan_milestones",
                "loan_portal_configs",
                "loan_close_schedules",
                "loan_property_baselines",
                "loan_property_costs",
                "loan_lifecycle_history",
                "loan_risk_flags",
                "loan_heartbeat_activities",
                "reconciliation_tasks",
                "reconciliation_items",
                "smart_doc_extractions",
                "smart_documents",
                "lead_activities",
                "lead_notes",
                "borrower_portal_accesses",
                "partner_portal_accesses",
                "mum_portfolio_entries",
                "client_communications",
                "email_threads",
                "email_messages",
            ]

            # First try TRUNCATE with CASCADE on main tables
            main_tables = ["tasks", "loans", "leads"]

            for table_name in main_tables:
                try:
                    # Get count before truncate
                    count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    count = count_result.scalar()

                    # Use TRUNCATE with CASCADE to handle FK constraints
                    conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
                    conn.commit()
                    deleted[table_name] = count
                except SQLAlchemyError as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    error_str = str(e).lower()
                    if "does not exist" in error_str or "undefined table" in error_str:
                        deleted[table_name] = "table not found"
                    else:
                        errors.append(f"{table_name}: {str(e)[:100]}")

            # Then clear child tables (many might already be empty due to CASCADE)
            for table_name in tables_to_truncate:
                try:
                    count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    count = count_result.scalar()
                    if count > 0:
                        conn.execute(text(f"TRUNCATE TABLE {table_name} CASCADE"))
                        conn.commit()
                        deleted[table_name] = count
                except SQLAlchemyError as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    error_str = str(e).lower()
                    if "does not exist" not in error_str and "undefined table" not in error_str:
                        # Don't log if table doesn't exist
                        pass

            # Also clear activity logs for deleted entities
            try:
                result = conn.execute(text(
                    "DELETE FROM activity_logs WHERE entity_type IN ('lead', 'loan', 'task')"
                ))
                conn.commit()
                deleted["activity_logs"] = result.rowcount
            except Exception:
                pass

        total_deleted = sum(v for v in deleted.values() if isinstance(v, int))

        return {
            "success": True,
            "total_records_deleted": total_deleted,
            "details": deleted,
            "errors": errors if errors else None,
            "message": f"Cleared {total_deleted} records from the CRM"
        }
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail="Failed to clear demo data")
