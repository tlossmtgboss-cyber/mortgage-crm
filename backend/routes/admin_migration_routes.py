"""
Admin Migration Routes
Temporary migration endpoints for database updates and admin bootstrapping
"""
import hmac
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import subprocess
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter()

# Migration secret from env — fail closed if not set
ADMIN_MIGRATION_SECRET = os.getenv("ADMIN_MIGRATION_SECRET", "")


def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
    }


def get_db_dep():
    """Get database dependency at runtime"""
    from db import get_db
    return get_db


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user


def get_apply_role_template():
    """Get role template function"""
    import main
    return main.apply_role_template_to_user


@router.post("/admin/run-ai-migration")
async def run_ai_migration_endpoint(request: dict):
    """
    Temporary endpoint to run AI migration remotely.
    Usage: POST /admin/run-ai-migration with body: {"secret": "<ADMIN_MIGRATION_SECRET>"}
    """
    if not ADMIN_MIGRATION_SECRET:
        raise HTTPException(status_code=503, detail="Migration endpoint not configured")
    if not request.get("secret") or not hmac.compare_digest(request.get("secret", ""), ADMIN_MIGRATION_SECRET):
        raise HTTPException(status_code=403, detail="Invalid secret")

    try:
        result = subprocess.run(
            ["python3", "run_ai_migration.py"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app"
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Migration timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.get("/api/v1/migrations/check-phase2-permissions", response_model=None)
async def check_phase2_permission_migration(
    db: Session = Depends(lambda: get_db_dep()),
    current_user=Depends(current_user_dep)
):
    """
    Check if Phase 2 Permission System Migration has completed
    Returns status of tables and templates
    """
    if getattr(current_user, 'role', None) != 'admin' and getattr(current_user, 'permission_role', None) != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        results = {
            "permission_role_column_exists": False,
            "permission_templates_table_exists": False,
            "user_permissions_table_exists": False,
            "template_count": 0,
            "templates": []
        }

        try:
            db.execute(text("SELECT permission_role FROM users LIMIT 1"))
            results["permission_role_column_exists"] = True
        except Exception as e:
            logger.debug(f"permission_role column check failed: {e}")

        try:
            result = db.execute(text("SELECT COUNT(*) FROM permission_templates"))
            results["permission_templates_table_exists"] = True
            results["template_count"] = result.fetchone()[0]

            templates = db.execute(text("SELECT id, name, category FROM permission_templates"))
            results["templates"] = [{"id": t[0], "name": t[1], "category": t[2]} for t in templates]
        except Exception as e:
            logger.debug(f"permission_templates table check failed: {e}")

        try:
            db.execute(text("SELECT COUNT(*) FROM user_permissions LIMIT 1"))
            results["user_permissions_table_exists"] = True
        except Exception as e:
            logger.debug(f"user_permissions table check failed: {e}")

        results["migration_complete"] = (
            results["permission_role_column_exists"] and
            results["permission_templates_table_exists"] and
            results["user_permissions_table_exists"] and
            results["template_count"] >= 3
        )

        return results

    except Exception as e:
        logger.error(f"Check migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/v1/migrations/bootstrap-admin-user", response_model=None)
async def bootstrap_admin_user(
    user_id: int = 1,
    bootstrap_key: str = "",
    db: Session = Depends(lambda: get_db_dep())
):
    """
    Bootstrap an admin user with management permissions
    """
    models = get_models()
    User = models['User']
    apply_role_template = get_apply_role_template()

    try:
        if not ADMIN_MIGRATION_SECRET:
            raise HTTPException(status_code=503, detail="Bootstrap endpoint not configured")
        if not bootstrap_key or not hmac.compare_digest(bootstrap_key, ADMIN_MIGRATION_SECRET):
            raise HTTPException(status_code=403, detail="Invalid bootstrap key")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")

        success = apply_role_template(user_id, "management", user_id, db)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to apply management template")

        return {
            "success": True,
            "message": f"Successfully bootstrapped user {user.email} with management permissions",
            "user_id": user_id,
            "email": user.email,
            "role": "management"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bootstrap error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")



def set_dependencies(get_db_func, get_current_user_func):
    """Set dependencies for this router"""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func
