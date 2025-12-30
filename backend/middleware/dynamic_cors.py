"""
Dynamic CORS Middleware

Custom CORS middleware that checks origins against database.
Supports both static and dynamically configured custom domains.
"""

import logging
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """
    CORS middleware with dynamic origin checking.

    Uses CustomDomainService to check if origins are allowed,
    with caching for performance.
    """

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
        self.allow_methods = allow_methods or ["*"]
        self.allow_headers = allow_headers or ["*"]
        self.expose_headers = expose_headers or ["*"]
        self.max_age = max_age
        self._domain_service = None

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
        """Check if origin is allowed."""
        if not origin:
            return False

        # Use domain service if available
        if self.domain_service:
            return self.domain_service.is_allowed_origin(origin)

        # Fallback: allow static domains only
        static_allowed = {
            "http://localhost:3000",
            "http://localhost:3001",
            "https://perenniaai.com",
            "https://www.perenniaai.com",
            "https://app.perenniaai.com",
            "https://api.perenniaai.com",
            # Railway production domains
            "https://mortgage-crm-production-7a9a.up.railway.app",
        }

        if origin in static_allowed:
            return True

        # Allow perenniaai.com subdomains
        if origin.endswith("perenniaai.com"):
            return True

        # Allow railway.app subdomains (production hosting)
        if origin.endswith(".railway.app"):
            return True

        return False

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        origin = request.headers.get("origin")

        # Handle preflight OPTIONS requests
        if request.method == "OPTIONS":
            if origin and self.is_allowed_origin(origin):
                response = Response(status_code=204)
                self._add_cors_headers(response, origin)
                return response
            else:
                # Still return 204 but without CORS headers
                return Response(status_code=204)

        # Handle regular requests - wrap in try/except to ensure CORS headers
        # are added even when exceptions occur (otherwise browser blocks error responses)
        try:
            response = await call_next(request)
        except Exception as e:
            # Log the error
            logger.error(f"Error in request to {request.url.path}: {str(e)}")
            # Create error response with CORS headers
            from starlette.responses import JSONResponse
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )

        if origin and self.is_allowed_origin(origin):
            self._add_cors_headers(response, origin)

        return response

    def _add_cors_headers(self, response: Response, origin: str) -> None:
        """Add CORS headers to response."""
        response.headers["Access-Control-Allow-Origin"] = origin

        if self.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        if self.allow_methods:
            methods = ", ".join(self.allow_methods) if self.allow_methods != ["*"] else "*"
            response.headers["Access-Control-Allow-Methods"] = methods

        if self.allow_headers:
            headers = ", ".join(self.allow_headers) if self.allow_headers != ["*"] else "*"
            response.headers["Access-Control-Allow-Headers"] = headers

        if self.expose_headers:
            expose = ", ".join(self.expose_headers) if self.expose_headers != ["*"] else "*"
            response.headers["Access-Control-Expose-Headers"] = expose

        response.headers["Access-Control-Max-Age"] = str(self.max_age)
