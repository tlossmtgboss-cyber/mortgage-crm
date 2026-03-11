"""
Canonical auth dependencies for FastAPI route files.

All route files should import auth dependencies from here instead of
redefining their own get_current_user / get_current_user_flexible.

Usage:
    from auth.dependencies import get_current_user, get_current_user_flexible, oauth2_scheme

    @router.get("/my-endpoint")
    async def my_endpoint(user = Depends(get_current_user)):
        ...

NOTE: Uses lazy imports from main to avoid circular import at module load time.
The functions themselves are resolved at request time (FastAPI dependency injection).
"""
import logging

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from db import get_db

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Router-level auth dependency. Rejects unauthenticated requests.

    Usage (protects ALL endpoints on the router):
        from auth.dependencies import require_auth

        router = APIRouter(
            prefix="/api/v1/example",
            dependencies=[Depends(require_auth)],
        )
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await get_current_user_flexible(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def _get_main_auth():
    """Lazy import auth functions from main.py to avoid circular imports."""
    from main import (
        get_current_user,
        get_current_user_flexible,
        oauth2_scheme,
    )
    return get_current_user, get_current_user_flexible, oauth2_scheme


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Async FastAPI dependency — resolves to the authenticated User object.

    Extracts the Bearer token from the Authorization header and delegates
    to main.py's get_current_user for RS256 token verification.

    Usage:
        @router.get("/endpoint")
        async def handler(user = Depends(get_current_user)):
            ...
    """
    gcu, _, _ = _get_main_auth()
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await gcu(token, request, db)


async def get_current_user_flexible(request: Request, db: Session = Depends(get_db)):
    """Async FastAPI dependency — resolves to User via Bearer, API key, or cookie.

    Usage:
        @router.get("/endpoint")
        async def handler(user = Depends(get_current_user_flexible)):
            ...
    """
    _, gcuf, _ = _get_main_auth()
    return await gcuf(request, db)


def get_oauth2_scheme():
    """Return the canonical oauth2_scheme from main.py."""
    _, _, scheme = _get_main_auth()
    return scheme


# For direct Depends() usage without calling the function:
#   from auth.dependencies import current_user_dep
#   async def handler(user = Depends(current_user_dep)):
#
# These are properties that resolve at import time of the ROUTE module,
# but since routes are imported after main.py is loaded, this is safe.

class _LazyAuthProxy:
    """Proxy that lazily resolves auth dependencies on first access.

    This avoids circular imports while still allowing route files to do:
        from auth.dependencies import current_user_dep
        @router.get("/x")
        async def handler(user = Depends(current_user_dep)): ...
    """

    def __init__(self, attr_name):
        self._attr_name = attr_name
        self._resolved = None

    def _resolve(self):
        if self._resolved is None:
            gcu, gcuf, scheme = _get_main_auth()
            _resolved_map = {
                'get_current_user': gcu,
                'get_current_user_flexible': gcuf,
                'oauth2_scheme': scheme,
            }
            self._resolved = _resolved_map[self._attr_name]
        return self._resolved

    def __call__(self, *args, **kwargs):
        return self._resolve()(*args, **kwargs)

    def __repr__(self):
        return f"<LazyAuthProxy({self._attr_name})>"


# Lazy proxies that resolve on first call (compatible with Depends())
current_user_dep = _LazyAuthProxy('get_current_user')
current_user_flexible_dep = _LazyAuthProxy('get_current_user_flexible')
oauth2_scheme = _LazyAuthProxy('oauth2_scheme')


__all__ = [
    'require_auth',
    'get_current_user',
    'get_current_user_flexible',
    'get_oauth2_scheme',
    'current_user_dep',
    'current_user_flexible_dep',
    'oauth2_scheme',
]
