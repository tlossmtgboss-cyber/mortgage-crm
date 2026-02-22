"""
Security Headers Middleware — Enforce security response headers.
SOC 2 Criteria: CC5 (Control Activities), CC6 (Access Controls)

Adds required security headers to all responses to prevent common
web vulnerabilities (XSS, clickjacking, MIME sniffing, etc.).
"""
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from ..config import SOC2Config


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.
    
    Add to FastAPI:
        app.add_middleware(SecurityHeadersMiddleware)
    """

    def __init__(self, app, config: SOC2Config = None):
        super().__init__(app)
        self.config = config or SOC2Config.from_env()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        # Prevent XSS
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Force HTTPS
        response.headers["Strict-Transport-Security"] = (
            f"max-age={self.config.hsts_max_age}; includeSubDomains; preload"
        )

        # Content Security Policy
        response.headers["Content-Security-Policy"] = self.config.content_security_policy

        # Prevent referrer leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy (disable unnecessary browser features)
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), "
            "payment=(), usb=(), magnetometer=()"
        )

        # Cache control for sensitive data
        if "/api/" in request.url.path:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        return response
