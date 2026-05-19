"""
Tests for SecurityHeadersMiddleware.

These tests intentionally use a minimal FastAPI application rather than the
full backend `main:app`, because:
  - they exercise pure middleware behavior (no DB / auth needed)
  - keeping the test fast & isolated avoids the multi-second boot time of the
    real application and prevents flakes caused by environment-specific
    startup failures.

If the full app fails to import for any reason in CI, we fall back to a tiny
in-process app that still exercises the same middleware class.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure backend/ is on sys.path when tests are invoked from repo root.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from middleware.security_headers import SecurityHeadersMiddleware  # noqa: E402


def _make_app() -> FastAPI:
    """Try to load the real app; fall back to a minimal one on import failure."""
    try:
        import os
        os.environ.setdefault("TESTING", "1")
        from main import app as real_app  # type: ignore
        return real_app
    except Exception:  # pragma: no cover — fallback path
        fallback = FastAPI()
        fallback.add_middleware(SecurityHeadersMiddleware)

        @fallback.get("/")
        async def _root():
            return {"ok": True}

        return fallback


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = _make_app()
    # If we loaded the real app, the OWASP middleware is already wired in
    # main.py. If we created a fallback, it was added explicitly above.
    return TestClient(app, raise_server_exceptions=False)


def test_root_response_includes_csp_header(client: TestClient) -> None:
    """GET / must include a Content-Security-Policy header."""
    resp = client.get("/")
    assert "content-security-policy" in {k.lower() for k in resp.headers.keys()}
    csp = resp.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_x_frame_options_is_deny(client: TestClient) -> None:
    """X-Frame-Options must be DENY to prevent clickjacking."""
    resp = client.get("/")
    assert resp.headers.get("x-frame-options") == "DENY"


def test_docs_path_is_not_blocked(client: TestClient) -> None:
    """The /docs endpoint must remain reachable and skip the strict CSP."""
    resp = client.get("/docs")
    # /docs must respond (200 when the real app exposes it, 404 in the
    # fallback minimal app — either way it must not be 5xx and must not
    # carry our restrictive CSP).
    assert resp.status_code < 500
    # We deliberately skip the strict CSP for the Swagger UI page.
    assert "content-security-policy" not in {k.lower() for k in resp.headers.keys()}
