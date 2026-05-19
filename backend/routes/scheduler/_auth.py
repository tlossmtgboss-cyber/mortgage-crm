"""
Scheduler auth helpers — user authentication and authorization.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from db import get_db
from db import get_async_db
from routes.scheduler._core import get_current_user_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_current_user(request: Request, db: AsyncSession = Depends(get_async_db)):
    """Authenticate the current user from the Authorization header."""
    func = get_current_user_func()
    if func is None:
        raise RuntimeError("Dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    user = await func(token=token, request=request, db=db)
    if hasattr(user, 'is_active') and not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")
    return user


def _get_org_id(user) -> int:
    """Get organization_id from user, raise 403 if missing."""
    org_id = getattr(user, 'organization_id', None)
    if org_id is None:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


def _is_scheduler_admin(user) -> bool:
    """
    Standardized admin check for scheduler endpoints.
    Uses permission_role (primary) with role fallback.
    Only true security roles qualify -- 'leadership' and 'management' are display titles, not admin grants.
    """
    role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
    return role.lower() in ('admin', 'site_admin', 'platform_admin')
