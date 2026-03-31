"""
CSRF Protection Middleware

Provides Cross-Site Request Forgery protection for state-changing requests.
Uses the double-submit cookie pattern for stateless CSRF protection.

Usage:
    1. Add middleware to FastAPI app
    2. Frontend must include X-CSRF-Token header on state-changing requests
    3. Token is obtained from /api/v1/csrf-token endpoint or cookie
"""

import secrets
import logging
from typing import Optional, Set
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection using double-submit cookie pattern.

    How it works:
    1. Server sets a CSRF token in a cookie (readable by JavaScript)
    2. Client includes the same token in X-CSRF-Token header
    3. Server validates cookie value matches header value
    4. If mismatch, request is rejected

    This is secure because:
    - Attacker can't read the cookie from another domain (Same-Origin Policy)
    - Attacker can't set custom headers in cross-origin requests without CORS
    """

    # HTTP methods that modify state and require CSRF protection
    PROTECTED_METHODS: Set[str] = {"POST", "PUT", "PATCH", "DELETE"}

    # Paths that are exempt from CSRF (webhooks, public APIs, etc.)
    # API endpoints use JWT auth which provides sufficient protection
    EXEMPT_PATHS: Set[str] = {
        "/token",  # Login endpoint - can't have CSRF token before auth
        "/api/v1/token",  # Login endpoint alt path
        "/api/v1/auth",  # Auth endpoints
        "/api/v1/salesforce",  # Salesforce sync - uses JWT auth
        "/api/v1/integrations",  # Integration endpoints - uses JWT auth
        "/api/v1/migrations",  # Admin migrations - uses admin key auth
        "/api/v1/webhook",
        "/api/v1/webhooks",
        "/api/v1/voicemail/webhook",  # RVM provider delivery callbacks
        "/api/v1/zapier",
        "/api/v1/borrower",  # Borrower portal uses JWT auth
        "/api/v1/csrf-token",  # Token endpoint itself
        "/api/v1/public",  # Public endpoints (migrations, etc.)
        "/api/v1/scheduler/public",  # Public booking endpoints (unauthenticated POST)
        "/api/v1/admin/unlock-account",  # Admin unlock - uses admin key auth
        "/api/v1/admin-onboarding",  # Subscription onboarding - uses invite token auth, no session
        "/api/v1/invitations/activate",  # Public account activation from invite
        "/api/invite",  # Public invite acceptance (no auth context)
        "/api/integrations",  # New integration routes
        "/api/v1/app",  # Mobile app compatibility/health (unauthenticated, pre-login)
        "/health",
        "/api/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    }

    def __init__(
        self,
        app,
        cookie_name: str = "csrf_token",
        header_name: str = "X-CSRF-Token",
        cookie_secure: bool = True,
        cookie_samesite: str = "Lax",
        token_length: int = 32,
        enabled: bool = True,
    ):
        super().__init__(app)
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.cookie_secure = cookie_secure
        self.cookie_samesite = cookie_samesite
        self.token_length = token_length
        self.enabled = enabled

    def _generate_token(self) -> str:
        """Generate a cryptographically secure CSRF token."""
        return secrets.token_hex(self.token_length)

    def _is_exempt(self, request: Request) -> bool:
        """Check if request path is exempt from CSRF protection."""
        path = request.url.path

        # Check exact matches
        if path in self.EXEMPT_PATHS:
            return True

        # Check prefix matches
        for exempt in self.EXEMPT_PATHS:
            if path.startswith(exempt):
                return True

        return False

    def _validate_token(self, request: Request) -> bool:
        """Validate CSRF token from cookie matches header."""
        cookie_token = request.cookies.get(self.cookie_name)
        header_token = request.headers.get(self.header_name)

        if not cookie_token or not header_token:
            return False

        # Constant-time comparison to prevent timing attacks
        return secrets.compare_digest(cookie_token, header_token)

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request with CSRF protection."""

        # Skip if disabled
        if not self.enabled:
            return await call_next(request)

        # Skip safe methods (GET, HEAD, OPTIONS)
        if request.method not in self.PROTECTED_METHODS:
            response = await call_next(request)
            # Ensure CSRF cookie is set on all responses
            self._ensure_csrf_cookie(request, response)
            return response

        # Skip exempt paths
        if self._is_exempt(request):
            return await call_next(request)

        # Skip if request uses JWT Bearer auth (inherently CSRF-safe since
        # the token is in localStorage, not auto-sent by the browser like cookies)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and self._is_jwt_token(auth_header[7:]):
            return await call_next(request)

        # Skip if request has valid API key (machine-to-machine)
        api_key = request.headers.get("X-API-Key") or auth_header.replace("Bearer ", "")
        if api_key and self._is_api_key_auth(api_key):
            return await call_next(request)

        # Validate CSRF token
        if not self._validate_token(request):
            logger.warning(
                f"CSRF validation failed: {request.method} {request.url.path} "
                f"from {request.client.host if request.client else 'unknown'}"
            )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "CSRF token missing or invalid",
                    "code": "CSRF_VALIDATION_FAILED",
                }
            )

        # Process request
        response = await call_next(request)
        return response

    def _ensure_csrf_cookie(self, request: Request, response: Response):
        """Ensure CSRF cookie is set on response."""
        if self.cookie_name not in request.cookies:
            token = self._generate_token()
            response.set_cookie(
                key=self.cookie_name,
                value=token,
                httponly=False,  # Must be readable by JavaScript
                secure=self.cookie_secure,
                samesite=self.cookie_samesite,
                max_age=86400,  # 1 day
                path="/",
            )

    def _is_jwt_token(self, token: str) -> bool:
        """Check if token is a JWT (three base64 segments separated by dots)."""
        return len(token) >= 50 and token.count(".") == 2

    def _is_api_key_auth(self, token: str) -> bool:
        """Check if token looks like an API key (not a user JWT)."""
        # API keys are typically shorter and have a specific format
        # JWTs are longer and have three base64 parts
        if len(token) < 50:
            return True  # Likely an API key

        # Check for JWT format (xxx.xxx.xxx)
        if token.count(".") == 2:
            return False  # Likely a JWT

        return True


def get_csrf_token(request: Request) -> str:
    """
    Get or generate CSRF token for the current request.

    Use this in routes to get the token value for the frontend.
    """
    token = request.cookies.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
    return token


# FastAPI route for getting CSRF token
def create_csrf_routes():
    """Create CSRF token routes for FastAPI."""
    from fastapi import APIRouter

    router = APIRouter(tags=["Security"])

    @router.get("/csrf-token")
    async def get_csrf_token_route(request: Request):
        """
        Get a CSRF token for use in subsequent requests.

        The token is also set as a cookie. Include this token
        in the X-CSRF-Token header for POST/PUT/PATCH/DELETE requests.
        """
        token = get_csrf_token(request)
        response = JSONResponse(content={"csrf_token": token})
        response.set_cookie(
            key="csrf_token",
            value=token,
            httponly=False,
            secure=True,
            samesite="Lax",
            max_age=86400,
            path="/",
        )
        return response

    return router
