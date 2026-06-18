"""
Canonical auth dependencies for FastAPI route files.

All route files should import auth dependencies from here instead of
redefining their own get_current_user / get_current_user_flexible.

Usage:
    from auth.dependencies import get_current_user, get_current_user_flexible, oauth2_scheme

    @router.get("/my-endpoint")
    async def my_endpoint(user = Depends(get_current_user)):
        ...

The real function bodies live here; main.py re-exports them for back-compat.
"""
import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import jwt
from jwt.exceptions import InvalidTokenError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from db import get_db

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)

# oauth2_scheme — canonical instance used by get_current_user and re-exported to main.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# ---------------------------------------------------------------------------
# Secure-token helpers — imported from auth.tokens at module load time.
# If auth.tokens is unavailable we fall back to raw HS256.
# ---------------------------------------------------------------------------
try:
    from auth.tokens import (
        verify_token as _verify_secure_token,
        token_blacklist,
        TokenType,
        is_token_blacklisted,
    )
    _USE_SECURE_TOKENS = True
except ImportError:
    _USE_SECURE_TOKENS = False
    _verify_secure_token = None  # type: ignore[assignment]
    token_blacklist = None       # type: ignore[assignment]
    TokenType = None             # type: ignore[assignment]
    is_token_blacklisted = None  # type: ignore[assignment]

# Legacy HS256 constants (only used when _USE_SECURE_TOKENS is False)
_SECRET_KEY = os.getenv("SECRET_KEY", "")
_ALGORITHM = os.getenv("AUTH_ALGORITHM", "HS256")


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


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Get current user with impersonation support."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    actual_user = None

    # Lazy model import to avoid circular imports at module load time.
    from database.models import User, ApiKey

    # Check if token is an API key
    if token.startswith('sk_') or token.startswith('pk_live_'):
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        api_key = db.query(ApiKey).filter(
            ApiKey.key_hash == token_hash,
            ApiKey.is_active == True
        ).first()

        if not api_key:
            api_key = db.query(ApiKey).filter(
                ApiKey.key == token,
                ApiKey.is_active == True
            ).first()
            if api_key:
                api_key = db.query(ApiKey).filter(
                    ApiKey.id == api_key.id
                ).with_for_update().first()
                if api_key and api_key.key is not None:
                    api_key.key_hash = token_hash
                    api_key.key_prefix = token[:8]
                    api_key.key = None
                    db.commit()

        if api_key is None:
            raise credentials_exception

        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        api_key.last_used_at = datetime.now(timezone.utc)
        db.commit()

        actual_user = db.query(User).filter(User.id == api_key.user_id).first()
        if actual_user is None:
            raise credentials_exception

        if request:
            request.state._api_key_obj = api_key

        if request and api_key.scopes:
            try:
                from auth.scope_enforcement import check_endpoint_scopes
                if not check_endpoint_scopes(request, api_key.scopes):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="API key lacks required scope for this endpoint",
                    )
            except ImportError:
                pass
            except HTTPException:
                raise

    else:
        if _USE_SECURE_TOKENS:
            token_data = _verify_secure_token(token, expected_type=TokenType.ACCESS)
            if not token_data:
                raise credentials_exception
            email = token_data.sub
        else:
            try:
                _jwt_aud = os.getenv("JWT_AUDIENCE", "perennia-crm")
                payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM], audience=_jwt_aud, options={"verify_aud": True})
                _expected_issuer = os.getenv("JWT_ISSUER", "perennia-api")
                _token_issuer = payload.get("iss")
                if _token_issuer and _token_issuer != _expected_issuer:
                    logger.warning(f"JWT issuer mismatch: expected={_expected_issuer}, got={_token_issuer}")
                    raise credentials_exception
                email: str = payload.get("sub")
                if email is None:
                    raise credentials_exception
                token_scope = payload.get("scope")
                if token_scope in ("mfa_verify", "mfa_setup"):
                    logger.warning(f"Rejected MFA scoped token ({token_scope}) used as access token for {email}")
                    raise credentials_exception
                jti = payload.get("jti")
                if jti:
                    try:
                        from auth.tokens import is_token_blacklisted as _is_bl
                        if _is_bl(jti):
                            raise credentials_exception
                    except ImportError:
                        pass
            except InvalidTokenError:
                raise credentials_exception

        actual_user = db.query(User).filter(User.email == email).first()
        if actual_user is None:
            raise credentials_exception

        if not getattr(actual_user, "is_active", True):
            raise HTTPException(status_code=401, detail="Account deactivated")
        if getattr(actual_user, "locked_until", None) and actual_user.locked_until > datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Account temporarily locked")

    # Check for impersonation
    actual_user = resolve_impersonation(request, actual_user, db)

    # Update last_activity_at (throttled to every 5 minutes)
    try:
        now = datetime.now(timezone.utc)
        if actual_user.last_activity_at is None or (now - actual_user.last_activity_at).total_seconds() > 300:
            actual_user.last_activity_at = now
            db.commit()
    except Exception as e:
        logger.debug(f"Failed to update last_activity_at: {e}")
        db.rollback()

    return actual_user


async def get_current_user_flexible(
    request: Request,
    db: Session = Depends(get_db),
):
    """Flexible authentication supporting Bearer token and X-API-Key header."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = None

    # Lazy model import to avoid circular imports at module load time.
    from database.models import User, ApiKey

    # Check X-API-Key header first
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        header_hash = hashlib.sha256(api_key_header.encode()).hexdigest()
        api_key = db.query(ApiKey).filter(
            ApiKey.key_hash == header_hash,
            ApiKey.is_active == True
        ).first()

        if not api_key:
            api_key = db.query(ApiKey).filter(
                ApiKey.key == api_key_header,
                ApiKey.is_active == True
            ).first()
            if api_key:
                api_key = db.query(ApiKey).filter(
                    ApiKey.id == api_key.id
                ).with_for_update().first()
                if api_key and api_key.key is not None:
                    api_key.key_hash = header_hash
                    api_key.key_prefix = api_key_header[:8]
                    api_key.key = None
                    db.commit()

        if api_key:
            if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key has expired",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            api_key.last_used_at = datetime.now(timezone.utc)
            db.commit()

            if hasattr(request, 'state'):
                request.state._api_key_obj = api_key

            if api_key.scopes:
                try:
                    from auth.scope_enforcement import check_endpoint_scopes
                    if not check_endpoint_scopes(request, api_key.scopes):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="API key lacks required scope for this endpoint",
                        )
                except ImportError:
                    pass
                except HTTPException:
                    raise

            if api_key.organization_id:
                from database.tenant_mixin import set_tenant_context
                set_tenant_context(db, api_key.organization_id)
                logger.info(f"API key tenant context set to org {api_key.organization_id}")

            actual_user = db.query(User).filter(User.id == api_key.user_id).first()
            if actual_user:
                return resolve_impersonation(request, actual_user, db, auth_method="API key")

        raise credentials_exception

    # Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")

    if not token:
        raise credentials_exception

    # Check if token is an API key in Bearer header
    if token.startswith('sk_') or token.startswith('pk_live_'):
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        api_key = db.query(ApiKey).filter(
            ApiKey.key_hash == token_hash,
            ApiKey.is_active == True
        ).first()

        if not api_key:
            api_key = db.query(ApiKey).filter(
                ApiKey.key == token,
                ApiKey.is_active == True
            ).first()
            if api_key:
                api_key = db.query(ApiKey).filter(
                    ApiKey.id == api_key.id
                ).with_for_update().first()
                if api_key and api_key.key is not None:
                    api_key.key_hash = token_hash
                    api_key.key_prefix = token[:8]
                    api_key.key = None
                    db.commit()

        if api_key is None:
            raise credentials_exception

        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        api_key.last_used_at = datetime.now(timezone.utc)
        db.commit()

        if hasattr(request, 'state'):
            request.state._api_key_obj = api_key

        if api_key.scopes:
            try:
                from auth.scope_enforcement import check_endpoint_scopes
                if not check_endpoint_scopes(request, api_key.scopes):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="API key lacks required scope for this endpoint",
                    )
            except ImportError:
                pass
            except HTTPException:
                raise

        actual_user = db.query(User).filter(User.id == api_key.user_id).first()
        if actual_user is None:
            raise credentials_exception

        return resolve_impersonation(request, actual_user, db, auth_method="Bearer API key")

    # JWT token
    if _USE_SECURE_TOKENS:
        token_data = _verify_secure_token(token, expected_type=TokenType.ACCESS)
        if not token_data:
            raise credentials_exception
        email = token_data.sub
    else:
        try:
            _jwt_aud = os.getenv("JWT_AUDIENCE", "perennia-crm")
            payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM], audience=_jwt_aud, options={"verify_aud": True})
            _expected_issuer = os.getenv("JWT_ISSUER", "perennia-api")
            _token_issuer = payload.get("iss")
            if _token_issuer and _token_issuer != _expected_issuer:
                logger.warning(f"JWT issuer mismatch: expected={_expected_issuer}, got={_token_issuer}")
                raise credentials_exception
            email: str = payload.get("sub")
            if email is None:
                raise credentials_exception
            token_scope = payload.get("scope")
            if token_scope in ("mfa_verify", "mfa_setup"):
                logger.warning(f"Rejected MFA scoped token ({token_scope}) used as access token for {email}")
                raise credentials_exception
        except InvalidTokenError:
            raise credentials_exception

    actual_user = db.query(User).filter(User.email == email).first()
    if actual_user is None:
        raise credentials_exception

    if not getattr(actual_user, "is_active", True):
        raise HTTPException(status_code=401, detail="Account deactivated")
    if getattr(actual_user, "locked_until", None) and actual_user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Account temporarily locked")

    # Check for impersonation
    return resolve_impersonation(request, actual_user, db, auth_method="flexible")


def get_oauth2_scheme():
    """Return the canonical oauth2_scheme."""
    return oauth2_scheme


# Aliases for Depends() usage — these are the real functions now, no proxy needed.
current_user_dep = get_current_user
current_user_flexible_dep = get_current_user_flexible


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


def _get_api_key_org_id(candidate: str) -> Optional[int]:
    """Return the org_id bound to an API key via env config.

    Each API key has a corresponding _ORG_ID env var (e.g. CRM_API_KEY_ORG_ID).
    If the env var is not set, the key is treated as system-level (org_id=None)
    and will NOT inherit org_id from the request body — preventing callers from
    choosing arbitrary tenants.
    """
    for env_name in ("CRM_API_KEY", "INTERNAL_API_KEY"):
        expected = os.environ.get(env_name, "").strip()
        if expected and hmac.compare_digest(candidate, expected):
            org_str = os.environ.get(f"{env_name}_ORG_ID", "").strip()
            if org_str:
                try:
                    return int(org_str)
                except ValueError:
                    pass
            return None
    return None


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
                user = await get_current_user(token, request, db)
                if user:
                    return user
            except Exception:
                # JWT decode failed — fall through to API key check below.
                pass

        # Bearer value is not a JWT — treat it as an API key candidate.
        if _is_valid_api_key(token):
            org_id = _get_api_key_org_id(token)
            if org_id is None:
                raise HTTPException(status_code=403, detail="API key organization not configured")
            logger.info("Service auth via Bearer API key (org=%s)", org_id)
            return _SystemUser(organization_id=org_id)

    # --- 2. Check X-API-Key header ---
    api_key = request.headers.get("X-API-Key", "")
    if api_key and _is_valid_api_key(api_key):
        org_id = _get_api_key_org_id(api_key)
        if org_id is None:
            raise HTTPException(status_code=403, detail="API key organization not configured")
        logger.info("Service auth via X-API-Key header (org=%s)", org_id)
        return _SystemUser(organization_id=org_id)

    # --- 3. Check X-Internal-API-Key header (Aria pattern) ---
    internal_key = request.headers.get("X-Internal-API-Key", "")
    if internal_key and _is_valid_api_key(internal_key):
        org_id = _get_api_key_org_id(internal_key)
        if org_id is None:
            raise HTTPException(status_code=403, detail="API key organization not configured")
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


# ---------------------------------------------------------------------------
# Password hashing utilities (re-exported from main for canonical access)
# ---------------------------------------------------------------------------

def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt. Delegates to main.get_password_hash."""
    from main import get_password_hash as _gph
    return _gph(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    from main import verify_password as _vp
    return _vp(plain, hashed)


def resolve_impersonation(request: Request, authenticated_user, db: Session, auth_method: str = ""):
    """Check for impersonation header and return impersonated user if authorized.

    Centralises the impersonation lookup that was previously duplicated across
    every auth path in main.py.  If the ``X-Impersonation-Token`` header is
    present and maps to a valid, active session for *authenticated_user*, the
    impersonated user is returned along with request-state annotations.
    Otherwise *authenticated_user* is returned unchanged.

    Args:
        request: The incoming FastAPI request (used to read the header and
            annotate ``request.state``).
        authenticated_user: The already-verified user object.
        db: Active SQLAlchemy session.
        auth_method: Short label included in log messages so the auth path
            that triggered impersonation is identifiable (e.g. ``"API key"``,
            ``"Bearer API key"``, ``"flexible"``, or ``""`` for the default
            ``get_current_user`` JWT path).

    Returns:
        The impersonated ``User`` if a valid session exists, otherwise
        *authenticated_user*.
    """
    if request is None:
        return authenticated_user

    impersonation_token = request.headers.get("X-Impersonation-Token")
    if not impersonation_token:
        return authenticated_user

    from datetime import datetime, timezone as _tz

    # Lazy-import models to avoid circular imports at module load time.
    from database.models import ImpersonationSession, User

    session = db.query(ImpersonationSession).filter(
        ImpersonationSession.session_token == impersonation_token,
        ImpersonationSession.is_active == True,
        ImpersonationSession.expires_at > datetime.now(_tz.utc),
        ImpersonationSession.manager_id == authenticated_user.id,
    ).first()

    if not session:
        return authenticated_user

    impersonated_user = db.query(User).filter(
        User.id == session.impersonated_user_id,
    ).first()

    if not impersonated_user:
        return authenticated_user

    label = f" ({auth_method})" if auth_method else ""
    logger.info(
        f"Impersonation active{label}: user {authenticated_user.id} "
        f"-> user {impersonated_user.id} (mode: {session.mode})"
    )
    request.state.impersonation_session = session
    request.state.impersonation_mode = session.mode
    request.state.actual_user = authenticated_user
    return impersonated_user


__all__ = [
    'require_auth',
    'get_current_user',
    'get_current_user_flexible',
    'get_current_user_or_api_key',
    'get_oauth2_scheme',
    'current_user_dep',
    'current_user_flexible_dep',
    'oauth2_scheme',
    'get_password_hash',
    'verify_password',
    'resolve_impersonation',
]
