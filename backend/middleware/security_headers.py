"""
OWASP Security Headers Middleware.

Adds a strict set of security response headers to every HTTP response,
mitigating common attack vectors such as XSS, clickjacking, MIME sniffing,
and insecure embedding.

Headers applied:
  - Content-Security-Policy
  - X-Frame-Options
  - X-Content-Type-Options
  - Referrer-Policy
  - Permissions-Policy
  - Strict-Transport-Security (HTTPS requests only)

Skipped paths (documentation UIs require inline scripts/styles):
  - /docs
  - /redoc
  - /openapi.json
"""
from __future__ import annotations

import logging
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


# Paths that must remain free of strict CSP for FastAPI docs UIs.
_SKIP_PATHS: frozenset[str] = frozenset({"/docs", "/openapi.json", "/redoc"})


_CSP_VALUE = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https: wss:; "
    "frame-ancestors 'none'"
)

_BASE_HEADERS: dict[str, str] = {
    "Content-Security-Policy": _CSP_VALUE,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(self), camera=(self), payment=()",
}

_HSTS_HEADER = ("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")


def _should_skip(path: str, skip_paths: Iterable[str] = _SKIP_PATHS) -> bool:
    """Return True for FastAPI documentation paths that must keep relaxed headers."""
    if path in skip_paths:
        return True
    # /docs/oauth2-redirect etc.
    for sk in skip_paths:
        if path.startswith(sk + "/"):
            return True
    return False


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply OWASP-recommended security headers on every response.

    Usage:
        from middleware.security_headers import SecurityHeadersMiddleware
        app.add_middleware(SecurityHeadersMiddleware)
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        try:
            path = request.url.path
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            path = ""

        if _should_skip(path):
            return response

        for header, value in _BASE_HEADERS.items():
            # Do not clobber a header already set by an upstream handler.
            response.headers.setdefault(header, value)

        # Only emit HSTS for HTTPS responses (browsers ignore it on http anyway,
        # but emitting it can confuse local dev tooling).
        scheme = ""
        try:
            scheme = request.url.scheme or ""
            # Honor reverse-proxy forwarded scheme when present.
            fwd_proto = request.headers.get("x-forwarded-proto", "")
            if fwd_proto:
                scheme = fwd_proto.split(",")[0].strip().lower()
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            scheme = ""

        if scheme == "https":
            response.headers.setdefault(_HSTS_HEADER[0], _HSTS_HEADER[1])

        return response


__all__ = ["SecurityHeadersMiddleware"]
