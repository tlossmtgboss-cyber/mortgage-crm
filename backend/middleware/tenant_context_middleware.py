"""
Tenant Context Middleware
=========================
Sets tenant context on request.state for all authenticated requests.

This middleware extracts the authenticated user from the JWT token (if present)
and populates request.state with:
- request.state.user: The authenticated User object
- request.state.tenant_context: TenantContext for the user's organization

It also sets the structured logging context variables for correlation:
- user_id: For user-level log correlation
- tenant_id: For organization-level log correlation (organization_id)

This enables the tenant isolation system to work without modifying every route.
"""

import logging
from typing import Optional, Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from sqlalchemy.orm import Session

# Import auth.tokens for algorithm-agnostic JWT verification (RS256/HS256)
try:
    from auth.tokens import verify_token as _verify_secure_token
    _SECURE_AUTH_AVAILABLE = True
except ImportError:
    _SECURE_AUTH_AVAILABLE = False
    _verify_secure_token = None

# Fallback: raw jose decode for environments without auth.tokens
from jose import JWTError, jwt

# Import structured logging context setters
try:
    from core.logging import set_user_id, set_tenant_id
    STRUCTURED_LOGGING_AVAILABLE = True
except ImportError:
    STRUCTURED_LOGGING_AVAILABLE = False
    set_user_id = None
    set_tenant_id = None

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts tenant context from authenticated requests.

    This runs AFTER authentication and sets request.state for use by routes.
    It's non-blocking - if auth fails, the route's own auth dependency will handle it.
    """

    def __init__(
        self,
        app,
        secret_key: str,
        algorithm: str = "HS256",
        get_db: Callable = None,
        user_model = None,
    ):
        super().__init__(app)
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.get_db = get_db
        self.user_model = user_model

    def _set_tenant_state(self, request: Request, user) -> None:
        """Populate request.state with tenant context from a resolved user."""
        request.state.user = user
        request.state.organization_id = getattr(user, 'organization_id', None)

        from services.tenant_isolation import TenantContext

        user_role = getattr(user, 'permission_role', 'sales')
        is_platform_admin = user_role == 'admin'

        request.state.tenant_context = TenantContext(
            organization_id=request.state.organization_id,
            user_id=user.id,
            user_role=user_role,
            is_platform_admin=is_platform_admin
        )

        # Set structured logging context for correlation
        if STRUCTURED_LOGGING_AVAILABLE:
            set_user_id(user.id)
            if request.state.organization_id:
                set_tenant_id(str(request.state.organization_id))

        logger.debug(
            f"Tenant context set for user {user.id}, "
            f"org {request.state.organization_id}"
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and add tenant context if authenticated."""

        # Initialize empty state
        request.state.user = None
        request.state.tenant_context = None
        request.state.organization_id = None

        # Skip tenant context for certain paths
        skip_paths = [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/api/v1/login",
            "/api/v1/register",
            "/api/v1/onboarding/",
            "/static/",
        ]

        if any(request.url.path.startswith(path) for path in skip_paths):
            return await call_next(request)

        # Try to extract user from Authorization header
        auth_header = request.headers.get("Authorization")

        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix

            if token.startswith("sk_") or token.startswith("pk_live_"):
                # API key authentication - resolve user and set tenant context
                try:
                    if self.get_db and self.user_model:
                        db = next(self.get_db())
                        try:
                            import hashlib as _hashlib
                            from database.models.core import ApiKey
                            _token_hash = _hashlib.sha256(token.encode()).hexdigest()
                            api_key = db.query(ApiKey).filter(
                                ApiKey.key_hash == _token_hash,
                                ApiKey.is_active == True
                            ).first()
                            # Fallback to plaintext for unmigrated keys
                            if not api_key:
                                api_key = db.query(ApiKey).filter(
                                    ApiKey.key == token,
                                    ApiKey.is_active == True
                                ).first()
                            if api_key:
                                user = db.query(self.user_model).filter(
                                    self.user_model.id == api_key.user_id
                                ).first()
                                if user:
                                    self._set_tenant_state(request, user)
                        finally:
                            db.close()
                except Exception as e:
                    logger.debug(f"API key tenant context extraction failed: {e}")
            else:
                # JWT authentication — use auth.tokens.verify_token for correct
                # algorithm (RS256 in production, HS256 in dev) and blacklist checks
                try:
                    user_id = None

                    if _SECURE_AUTH_AVAILABLE:
                        token_data = _verify_secure_token(token, check_blacklist=True)
                        if token_data:
                            sub = token_data.sub
                            # sub may be user_id (int) or email (str)
                            user_id = token_data.user_id
                            if not user_id:
                                try:
                                    user_id = int(sub)
                                except (ValueError, TypeError):
                                    # sub is an email — resolve to user_id via DB lookup
                                    pass
                    else:
                        # Fallback to raw jwt.decode (dev environments without auth module)
                        payload = jwt.decode(
                            token,
                            self.secret_key,
                            algorithms=[self.algorithm],
                            options={"verify_aud": False}
                        )
                        sub = payload.get("sub")
                        try:
                            user_id = int(sub)
                        except (ValueError, TypeError):
                            pass

                    if self.get_db and self.user_model:
                        db = next(self.get_db())
                        try:
                            user = None
                            if user_id:
                                user = db.query(self.user_model).filter(
                                    self.user_model.id == user_id
                                ).first()
                            elif sub:
                                # Email-based sub: look up user by email
                                user = db.query(self.user_model).filter(
                                    self.user_model.email == sub
                                ).first()

                            if user:
                                self._set_tenant_state(request, user)
                        finally:
                            db.close()

                except JWTError as e:
                    # Token invalid - route auth will handle the error
                    logger.debug(f"JWT decode failed in middleware: {e}")
                except Exception as e:
                    # Don't fail the request - let route auth handle it
                    logger.debug(f"Tenant context extraction failed: {e}")

        return await call_next(request)


def create_tenant_middleware(app, secret_key: str, get_db: Callable, user_model):
    """
    Factory function to create and add tenant middleware to app.

    Usage in main.py:
        from middleware.tenant_context_middleware import create_tenant_middleware

        create_tenant_middleware(app, SECRET_KEY, get_db, User)

    Args:
        app: FastAPI application
        secret_key: JWT secret key
        get_db: Database session dependency function
        user_model: SQLAlchemy User model class
    """
    app.add_middleware(
        TenantContextMiddleware,
        secret_key=secret_key,
        get_db=get_db,
        user_model=user_model,
    )
    logger.info("Tenant context middleware initialized")
