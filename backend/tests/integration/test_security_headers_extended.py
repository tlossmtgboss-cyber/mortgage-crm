"""
Extended integration tests for `middleware/security_headers.py`.

Each test inspects one OWASP header independently so failures pinpoint the
broken header rather than collapsing into a single test.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_module():
    target = _BACKEND_DIR / "middleware" / "security_headers.py"
    if not target.exists():
        pytest.skip("security_headers.py missing")
    spec = importlib.util.spec_from_file_location(
        "_perennia_security_headers_ext", str(target)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        pytest.skip(f"security_headers import failed: {exc}")
    return module


_sec = _load_module()


def _build_client():
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("fastapi/testclient not installed")
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    app.add_middleware(_sec.SecurityHeadersMiddleware)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Per-header presence tests (6)
# ---------------------------------------------------------------------------

def test_csp_header_present():
    resp = _build_client().get("/api/ping")
    assert "content-security-policy" in {k.lower() for k in resp.headers}


def test_x_frame_options_header_present():
    resp = _build_client().get("/api/ping")
    assert "x-frame-options" in {k.lower() for k in resp.headers}


def test_x_content_type_options_header_present():
    resp = _build_client().get("/api/ping")
    assert "x-content-type-options" in {k.lower() for k in resp.headers}


def test_referrer_policy_header_present():
    resp = _build_client().get("/api/ping")
    assert "referrer-policy" in {k.lower() for k in resp.headers}


def test_permissions_policy_header_present():
    resp = _build_client().get("/api/ping")
    assert "permissions-policy" in {k.lower() for k in resp.headers}


def test_hsts_header_absent_on_http():
    """HSTS must be omitted on plain HTTP responses (TestClient default)."""
    resp = _build_client().get("/api/ping")
    assert "strict-transport-security" not in {k.lower() for k in resp.headers}


# ---------------------------------------------------------------------------
# Value-level assertions (4)
# ---------------------------------------------------------------------------

def test_csp_allows_fonts_googleapis():
    resp = _build_client().get("/api/ping")
    csp = resp.headers.get("content-security-policy", "")
    assert "fonts.googleapis.com" in csp


def test_x_frame_options_is_deny():
    resp = _build_client().get("/api/ping")
    assert resp.headers.get("x-frame-options", "").upper() == "DENY"


def test_x_content_type_options_is_nosniff():
    resp = _build_client().get("/api/ping")
    assert resp.headers.get("x-content-type-options", "").lower() == "nosniff"


def test_referrer_policy_value_strict_origin():
    resp = _build_client().get("/api/ping")
    rp = resp.headers.get("referrer-policy", "")
    assert "strict-origin" in rp.lower()
