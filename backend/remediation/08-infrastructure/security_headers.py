"""
08-infrastructure/security_headers.py

Security response headers. Covers the baseline SOC 2 auditors and most
pen-test checklists look for.

Drop-in: backend/app/middleware/security_headers.py
Register in main.py:
    app.add_middleware(SecurityHeadersMiddleware)
"""

from __future__ import annotations

import os
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

IS_PROD = os.environ.get("ENV") == "production"

# Content Security Policy — start strict, relax per verified need.
# 'self' everywhere; explicit allowlist for CDN, Anthropic/OpenAI if called
# from browser (unlikely — those calls should be server-side), and analytics.
#
# If you later add Intercom, Segment, etc., add their origins here — don't
# weaken to unsafe-*.
CSP_DIRECTIVES = {
    "default-src": ["'self'"],
    "script-src": [
        "'self'",
        # Vite inline runtime uses nonces in prod; keep 'unsafe-inline' off
        "'strict-dynamic'",
    ],
    "style-src": [
        "'self'",
        "'unsafe-inline'",  # Tailwind + Radix need inline styles
        "https://fonts.googleapis.com",
    ],
    "font-src": ["'self'", "https://fonts.gstatic.com", "data:"],
    "img-src": ["'self'", "data:", "blob:", "https:"],
    "media-src": ["'self'", "blob:", "https:"],
    "connect-src": [
        "'self'",
        "https://api.anthropic.com",
        "wss://*.perennia.ai",  # WebSocket for live updates
    ],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "object-src": ["'none'"],
    "upgrade-insecure-requests": [],
}


def _build_csp() -> str:
    parts = []
    for directive, sources in CSP_DIRECTIVES.items():
        if not sources:
            parts.append(directive)
        else:
            parts.append(f"{directive} {' '.join(sources)}")
    return "; ".join(parts)


_CSP_HEADER = _build_csp()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # HSTS: tell browsers to always use HTTPS. Only in prod — don't break
        # local dev over http://localhost.
        if IS_PROD:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        # Clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Referrer policy — don't leak full URLs to external sites
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy — disable features we never use
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(self), payment=(), usb=()"
        )

        # CSP — skip for OpenAPI docs which need relaxed rules
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
            response.headers["Content-Security-Policy"] = _CSP_HEADER

        # Cross-origin isolation
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"

        # Don't leak server identity
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)

        return response
