"""
Shared FastAPI authentication dependencies for route files.

These are proper async dependencies that resolve to User objects.
Use instead of broken `Depends(lambda: get_current_user_dep())` pattern.

Usage (per-endpoint):
    from routes.auth_deps import current_user_dep

    @router.get("/example")
    async def example(current_user=Depends(current_user_dep)):
        ...

Usage (router-level — protects ALL endpoints on the router):
    from routes.auth_deps import require_auth

    router = APIRouter(
        prefix="/api/v1/example",
        dependencies=[Depends(require_auth)],
    )
"""

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from db import get_db

_security = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: Session = Depends(get_db),
):
    """Router-level auth dependency. Rejects unauthenticated requests."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from auth.dependencies import get_current_user_flexible
    user = await get_current_user_flexible(
        token=credentials.credentials, request=None, db=db
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


async def current_user_dep(request: Request, db: Session = Depends(get_db)):
    """Strict Bearer token auth — resolves to User object."""
    from auth.dependencies import get_current_user
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    return await get_current_user(token, request, db)


async def current_user_flexible_dep(request: Request, db: Session = Depends(get_db)):
    """Flexible auth (Bearer, API key, cookie) — resolves to User object."""
    from auth.dependencies import get_current_user_flexible
    return await get_current_user_flexible(request, db)
