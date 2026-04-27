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
import hmac
import logging
import os
from typing import Optional

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


# ---------------------------------------------------------------------------
# Service-to-service auth: accepts JWT OR CRM_API_KEY / INTERNAL_API_KEY
# ---------------------------------------------------------------------------

class _SystemUser:
    """
    Synthetic user object returned when a service authenticates via API key
    instead of a JWT.  Provides the same interface (.id, .organization_id,
    .email, .role) that route handlers expect from get_current_user.
    """

    def __init__(self, organization_id: Optional[int] = None):
        self.id = None  # No real user row
        self.email = "system@perenniaai.com"
        self.role = "system"
        self.organization_id = organization_id
        self.is_active = True

    def __repr__(self):
        return f"<_SystemUser org={self.organization_id}>"


def _is_valid_api_key(candidate: str) -> bool:
    """
    Check *candidate* against CRM_API_KEY and INTERNAL_API_KEY env vars.
    Uses constant-time comparison to avoid timing side-channels.
    Returns True if it matches either key.
    """
    for env_name in ("CRM_API_KEY", "INTERNAL_API_KEY"):
        expected = os.environ.get(env_name, "").strip()
        if expected and hmac.compare_digest(candidate, expected):
            return True
    return False


async def get_current_user_or_api_key(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    FastAPI dependency that accepts **either** a valid JWT Bearer token
    (normal user auth) **or** a bare API key in the Authorization header /
    X-API-Key header (service-to-service auth).

    On API-key match, returns a ``_SystemUser`` whose ``organization_id``
    is pulled from the request JSON body (if present).  This lets the URLA
    voice agent call CRM endpoints using its CRM_API_KEY without needing
    a real JWT.

    Usage:
        @router.post("/my-service-endpoint")
        async def handler(user=Depends(get_current_user_or_api_key)):
            ...
    """
    # --- 1. Try JWT auth (existing path) ---
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        # If token looks like a JWT (3 dot-separated segments, > 50 chars),
        # try the normal user resolution.
        if token.count(".") == 2 and len(token) > 50:
            try:
                gcu, _, _ = _get_main_auth()
                user = await gcu(token, request, db)
                if user:
                    return user
            except Exception:
                # JWT decode failed — fall through to API key check below.
                pass

        # Bearer value is not a JWT — treat it as an API key candidate.
        if _is_valid_api_key(token):
            org_id = await _extract_org_id_from_body(request)
            logger.info("Service auth via Bearer API key (org=%s)", org_id)
            return _SystemUser(organization_id=org_id)

    # --- 2. Check X-API-Key header ---
    api_key = request.headers.get("X-API-Key", "")
    if api_key and _is_valid_api_key(api_key):
        org_id = await _extract_org_id_from_body(request)
        logger.info("Service auth via X-API-Key header (org=%s)", org_id)
        return _SystemUser(organization_id=org_id)

    # --- 3. Check X-Internal-API-Key header (Aria pattern) ---
    internal_key = request.headers.get("X-Internal-API-Key", "")
    if internal_key and _is_valid_api_key(internal_key):
        org_id = await _extract_org_id_from_body(request)
        logger.info("Service auth via X-Internal-API-Key header (org=%s)", org_id)
        return _SystemUser(organization_id=org_id)

    raise HTTPException(status_code=401, detail="Not authenticated")


async def _extract_org_id_from_body(request: Request) -> Optional[int]:
    """
    Best-effort extraction of ``organization_id`` from a JSON request body.
    Returns None if the body cannot be parsed or the field is absent.
    """
    try:
        body = await request.json()
        org_id = body.get("organization_id")
        return int(org_id) if org_id is not None else None
    except Exception:
        return None


__all__ = [
    'require_auth',
    'get_current_user',
    'get_current_user_flexible',
    'get_current_user_or_api_key',
    'get_oauth2_scheme',
    'current_user_dep',
    'current_user_flexible_dep',
    'oauth2_scheme',
]
