"""
Shared FastAPI authentication dependencies for route files.

These are proper async dependencies that resolve to User objects.
Use instead of broken `Depends(lambda: get_current_user_dep())` pattern.

Usage:
    from routes.auth_deps import current_user_dep, current_user_flexible_dep

    @router.get("/example")
    async def example(current_user=Depends(current_user_dep)):
        ...
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from db import get_db


async def current_user_dep(request: Request, db: Session = Depends(get_db)):
    """Strict Bearer token auth — resolves to User object."""
    from main import get_current_user
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    return await get_current_user(token, request, db)


async def current_user_flexible_dep(request: Request, db: Session = Depends(get_db)):
    """Flexible auth (Bearer, API key, cookie) — resolves to User object."""
    from main import get_current_user_flexible
    return await get_current_user_flexible(request, db)
