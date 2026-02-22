"""
Account Management Routes
Master Administrator account, user, subscription, and cost management

Thin router that includes sub-routers:
- account_admin_routes: KPIs, account CRUD, account actions, user management,
  impersonation, billing, audit logs
- account_invitations_routes: Invite, list, resend, revoke, reinstate
- account_migrations_routes: Schema migrations, data cleanup, emergency admin reset

Extracted modules:
- account_models.py: Pydantic schemas, SQL safety infrastructure, helper functions
"""

from fastapi import APIRouter
import logging

from routes.account_admin_routes import router as admin_router
from routes.account_admin_routes import set_dependencies as set_admin_deps

from routes.account_invitations_routes import router as invitations_router
from routes.account_invitations_routes import set_dependencies as set_invitations_deps

from routes.account_migrations_routes import router as migrations_router
from routes.account_migrations_routes import set_dependencies as set_migrations_deps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/account-management", tags=["Account Management"])


def set_dependencies(user_model, current_user_func):
    """Set dependencies for all sub-routers"""
    set_admin_deps(user_model, current_user_func)
    set_invitations_deps(user_model, current_user_func)
    set_migrations_deps(user_model, current_user_func)


# Include sub-routers (no prefix - parent router already has /api/v1/admin/account-management)
router.include_router(admin_router)
router.include_router(invitations_router)
router.include_router(migrations_router)
