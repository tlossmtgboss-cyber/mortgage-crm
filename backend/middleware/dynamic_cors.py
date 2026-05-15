"""
Dynamic CORS Middleware

Custom CORS middleware that checks origins against database.
Supports both static and dynamically configured custom domains.

Environment-aware: localhost origins are only allowed in development mode.
Production mode is detected via ENVIRONMENT or RAILWAY_ENVIRONMENT env vars.
"""

import logging
import os
from typing import Callable, Optional, Set
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


def _is_production() -> bool:
    """Detect production environment from env vars."""
    env = os.getenv("ENVIRONMENT", os.getenv("RAILWAY_ENVIRONMENT", "development"))
    return env.lower() == "production"


def _get_railway_public_domain() -> Optional[str]:
    """Get this deployment's own Railway public domain (if any)."""
    return os.getenv("RAILWAY_PUBLIC_DOMAIN")


def _get_extra_railway_domains() -> Set[str]:
    """Parse RAILWAY_CORS_DOMAINS env var (comma-separated hostnames) into a set."""
    raw = os.getenv("RAILWAY_CORS_DOMAINS", "").strip()
    if not raw:
        return set()
    return {d.strip().lower() for d in raw.split(",") if d.strip()}


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """
    CORS middleware with dynamic origin checking.

    Uses CustomDomainService to check if origins are allowed,
    with caching for performance.

    Security properties:
    - Origins are checked against an explicit allowlist (never wildcard)
    - localhost origins are only permitted in non-production environments
    - railway.app subdomains are restricted to this deployment's own domain
    - Custom domains are validated via database lookup (CustomDomainService)
    - Wildcard values for methods/headers/expose_headers are rejected
    """

    # SECURITY: Explicit allowlists instead of wildcards
    DEFAULT_ALLOWED_METHODS = [
        "GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"
    ]
    DEFAULT_ALLOWED_HEADERS = [
        "Accept",
        "Accept-Language",
        "Authorization",
        "Content-Language",
        "Content-Type",
        "Origin",
        "X-Requested-With",
        "X-CSRF-Token",
        "X-Request-ID",
        "X-Visitor-ID",
        "X-API-Key",
        "X-Impersonation-Token",
        "X-Mask-PII",
    ]
    DEFAULT_EXPOSE_HEADERS = [
        "Content-Length",
        "Content-Type",
        "X-Request-ID",
        "X-Response-Time",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "X-RateLimit-Tier",
        "Retry-After",
    ]

    # Production origins (always allowed)
    _PRODUCTION_ORIGINS: Set[str] = {
        "https://perenniaai.com",
        "https://www.perenniaai.com",
        "https://app.perenniaai.com",
        "https://api.perenniaai.com",
        # Capacitor iOS/Android app origins (used in production builds)
        "capacitor://localhost",
        "ionic://localhost",
    }

    # Development-only origins (never allowed in production)
    _DEV_ORIGINS: Set[str] = {
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
    }

    def __init__(
        self,
        app: ASGIApp,
        allow_credentials: bool = True,
        allow_methods: list = None,
        allow_headers: list = None,
        expose_headers: list = None,
        max_age: int = 3600,
    ):
        super().__init__(app)
        self.allow_credentials = allow_credentials
        self.is_production = _is_production()
        self._railway_domain = _get_railway_public_domain()
        self._extra_railway_domains = _get_extra_railway_domains()

        # SECURITY: Reject wildcard values — force explicit allowlists
        if allow_methods == ["*"]:
            logger.warning(
                "CORS allow_methods=['*'] rejected — using explicit default list"
            )
            allow_methods = None
        if allow_headers == ["*"]:
            logger.warning(
                "CORS allow_headers=['*'] rejected — using explicit default list"
            )
            allow_headers = None
        if expose_headers == ["*"]:
            logger.warning(
                "CORS expose_headers=['*'] rejected — using explicit default list"
            )
            expose_headers = None

        self.allow_methods = allow_methods or self.DEFAULT_ALLOWED_METHODS
        self.allow_headers = allow_headers or self.DEFAULT_ALLOWED_HEADERS
        self.expose_headers = expose_headers or self.DEFAULT_EXPOSE_HEADERS
        self.max_age = max_age
        self._domain_service = None

        # Build static origin set once at startup
        self._static_origins: Set[str] = set(self._PRODUCTION_ORIGINS)
        if not self.is_production:
            self._static_origins.update(self._DEV_ORIGINS)
        if self._railway_domain:
            self._static_origins.add(f"https://{self._railway_domain}")
        for domain in self._extra_railway_domains:
            self._static_origins.add(f"https://{domain}")

        logger.info(
            "CORS middleware initialized: production=%s, static_origins=%d, max_age=%d",
            self.is_production,
            len(self._static_origins),
            self.max_age,
        )

    @property
    def domain_service(self):
        """Lazy-load domain service to avoid import issues."""
        if self._domain_service is None:
            try:
                from services.custom_domain_service import get_domain_service
                self._domain_service = get_domain_service()
            except Exception as e:
                logger.warning(f"Could not load domain service: {e}")
                # Return a fallback that allows static domains
                return None
        return self._domain_service

    def is_allowed_origin(self, origin: str) -> bool:
        """Check if origin is allowed.

        Order of checks:
        1. Static origin set (production domains + dev domains if non-prod)
        2. *.perenniaai.com subdomains (validated suffix match)
        3. This deployment's own Railway domain (exact match, not all *.railway.app)
        4. Custom domains via database lookup (CustomDomainService)
        """
        if not origin:
            return False

        # 1. Check static origin set (fast path)
        if origin in self._static_origins:
            return True

        # 2. Allow perenniaai.com subdomains (validated suffix match)
        from urllib.parse import urlparse
        try:
            parsed = urlparse(origin)
            hostname = parsed.hostname or ""
        except Exception as e:
            logger.exception(f"Failed to parse origin URL '{origin}': {e}")
            return False

        if hostname == "perenniaai.com" or hostname.endswith(".perenniaai.com"):
            return True

        # 3. Railway.app: only allow this deployment's own domain, not all subdomains.
        # In production, open *.railway.app is a security risk because any Railway
        # user could deploy an app that sends credentialed cross-origin requests.
        if hostname.endswith(".railway.app"):
            if self._railway_domain and hostname == self._railway_domain:
                return True
            if hostname in self._extra_railway_domains:
                return True
            logger.warning(
                "Rejected railway.app origin %s (not in allowed domains)",
                origin,
            )
            return False

        # 4. Use domain service for custom domains if available
        try:
            if self.domain_service:
                return self.domain_service.is_allowed_origin(origin)
        except Exception as e:
            logger.warning(f"Domain service check failed: {e}")

        return False

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        origin = request.headers.get("origin")

        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS":
            response = Response(status_code=204)
            if origin and self.is_allowed_origin(origin):
                self._add_cors_headers(response, origin)
            return response

        # Handle regular requests - wrap in try/except to ensure CORS headers
        # are added even when exceptions occur (otherwise browser blocks error responses)
        try:
            response = await call_next(request)
        except Exception as e:
            import traceback as _tb
            tb_str = _tb.format_exc()
            logger.error(
                "CORS middleware caught unhandled exception on %s %s: %s\n%s",
                request.method, request.url.path, e, tb_str,
            )
            try:
                from utils.error_handling import _record_error
                _record_error(request.method, request.url.path, type(e).__name__, str(e), tb_str)
            except Exception:
                pass
            from starlette.responses import JSONResponse
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "path": request.url.path}
            )

        # Always try to add CORS headers for allowed origins
        if origin and self.is_allowed_origin(origin):
            self._add_cors_headers(response, origin)

        return response

    def _add_cors_headers(self, response: Response, origin: str) -> None:
        """Add CORS headers to response.

        Always uses the specific origin (never wildcard) since we validate
        origins in is_allowed_origin() and allow_credentials=True requires
        a specific origin per the CORS spec.
        """
        response.headers["Access-Control-Allow-Origin"] = origin

        if self.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        if self.allow_methods:
            response.headers["Access-Control-Allow-Methods"] = ", ".join(
                self.allow_methods
            )

        if self.allow_headers:
            response.headers["Access-Control-Allow-Headers"] = ", ".join(
                self.allow_headers
            )

        if self.expose_headers:
            response.headers["Access-Control-Expose-Headers"] = ", ".join(
                self.expose_headers
            )

        response.headers["Access-Control-Max-Age"] = str(self.max_age)
