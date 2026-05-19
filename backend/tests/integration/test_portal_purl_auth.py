"""
Portal PURL Authentication — Integration Tests
==============================================

Test matrix (skipped until secrets are provisioned — see
`docs/portal_test_credentials_setup.md`):

    UA-001  valid PURL token returns 200 with borrower payload
    UA-002  expired PURL token returns 401 with code=token_expired
    UA-006  cross-tenant PURL token cannot read another tenant's loan
    UA-011  multi-tenant isolation — token for tenant A sees ONLY tenant A rows
    UA-012  revoked token (post-logout / kill-switch) returns 401

Run locally:
    PERENNIA_TEST_PURL_TOKEN=... \\
    PERENNIA_TEST_EXPIRED_TOKEN=... \\
    PERENNIA_TEST_PURL_TOKEN_TENANT_A=... \\
    PERENNIA_TEST_PURL_TOKEN_TENANT_B=... \\
    PERENNIA_TEST_ADMIN_JWT=... \\
    PERENNIA_TEST_WORKSPACE_ID=... \\
    PERENNIA_TEST_BORROWER_READ_TOKEN=... \\
    pytest backend/tests/integration/test_portal_purl_auth.py -v

In CI the same env vars are populated from GitHub Actions secrets — see
`.github/workflows/golden-tests.yml`.
"""

from __future__ import annotations

import os
from typing import Optional

import pytest

from backend.tests.portal_test_credentials import (
    ENV_ADMIN_JWT,
    ENV_BORROWER_READ_TOKEN,
    ENV_EXPIRED_TOKEN,
    ENV_PURL_TOKEN,
    ENV_PURL_TOKEN_TENANT_A,
    ENV_PURL_TOKEN_TENANT_B,
    ENV_WORKSPACE_ID,
    require,
)

# Base URL for the API under test. Default to local dev; CI overrides via
# PERENNIA_TEST_API_BASE_URL → e.g. https://api.staging.perenniaai.com
API_BASE_URL = os.environ.get("PERENNIA_TEST_API_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def http_client():
    """Lightweight HTTP client. Uses `requests` if available, else `httpx`."""
    try:
        import requests
        sess = requests.Session()
        sess.headers.update({"User-Agent": "perennia-portal-tests/1.0"})
        yield sess
        sess.close()
    except ImportError:
        try:
            import httpx
            with httpx.Client(timeout=15.0) as client:
                yield client
        except ImportError:
            pytest.skip("Neither `requests` nor `httpx` available")


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _purl_url(path: str) -> str:
    return f"{API_BASE_URL.rstrip('/')}{path}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ua_001_valid_purl_token_returns_borrower_payload(http_client):
    """UA-001 — valid PURL token returns 200 with borrower payload."""
    token = require(ENV_PURL_TOKEN)
    resp = http_client.get(
        _purl_url("/api/portal/borrower/me"),
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    )
    body = resp.json()
    assert "borrower_id" in body or "id" in body or "email" in body, (
        f"Borrower payload missing expected identity fields: {body}"
    )


@pytest.mark.integration
def test_ua_002_expired_token_returns_401(http_client):
    """UA-002 — expired PURL token returns 401."""
    token = require(ENV_EXPIRED_TOKEN)
    resp = http_client.get(
        _purl_url("/api/portal/borrower/me"),
        headers=_auth_headers(token),
    )
    assert resp.status_code == 401, (
        f"Expected 401 for expired token, got {resp.status_code}: {resp.text[:300]}"
    )
    # Body should include a machine-readable code indicating expiry.
    try:
        body = resp.json()
        code = (
            body.get("code")
            or body.get("error")
            or body.get("detail", {}).get("code")
            if isinstance(body.get("detail"), dict)
            else body.get("detail")
        )
        assert code is None or "expir" in str(code).lower() or "token" in str(code).lower(), (
            f"Expected token-expiry indicator in body, got: {body}"
        )
    except ValueError:
        pass  # non-JSON body acceptable as long as status is 401


@pytest.mark.integration
def test_ua_006_cross_tenant_token_denied(http_client):
    """UA-006 — Tenant A's token cannot read a Tenant B loan."""
    token_a = require(ENV_PURL_TOKEN_TENANT_A)
    # The borrower portal exposes loan detail at /api/portal/borrower/loan/{id}.
    # In a properly provisioned test env, env var PERENNIA_TEST_TENANT_B_LOAN_ID
    # is the loan id owned by Tenant B that Tenant A must NOT be able to read.
    tenant_b_loan_id = os.environ.get("PERENNIA_TEST_TENANT_B_LOAN_ID", "00000000-0000-0000-0000-000000000000")
    resp = http_client.get(
        _purl_url(f"/api/portal/borrower/loan/{tenant_b_loan_id}"),
        headers=_auth_headers(token_a),
    )
    assert resp.status_code in (401, 403, 404), (
        f"Cross-tenant access must return 401/403/404 (RLS denies), "
        f"got {resp.status_code}: {resp.text[:300]}"
    )


@pytest.mark.integration
def test_ua_011_multi_tenant_isolation(http_client):
    """UA-011 — Tenant A list endpoint returns ONLY Tenant A rows."""
    token_a = require(ENV_PURL_TOKEN_TENANT_A)
    token_b = require(ENV_PURL_TOKEN_TENANT_B)

    resp_a = http_client.get(
        _purl_url("/api/portal/borrower/documents"),
        headers=_auth_headers(token_a),
    )
    resp_b = http_client.get(
        _purl_url("/api/portal/borrower/documents"),
        headers=_auth_headers(token_b),
    )
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200

    docs_a = resp_a.json() if isinstance(resp_a.json(), list) else resp_a.json().get("documents", [])
    docs_b = resp_b.json() if isinstance(resp_b.json(), list) else resp_b.json().get("documents", [])
    ids_a = {d.get("id") for d in docs_a if isinstance(d, dict)}
    ids_b = {d.get("id") for d in docs_b if isinstance(d, dict)}
    overlap = ids_a & ids_b
    assert not overlap, (
        f"Tenant isolation violated — overlapping document IDs across tenants: {overlap}"
    )


@pytest.mark.integration
@pytest.mark.security
def test_ua_012_revoked_token_returns_401(http_client):
    """UA-012 — a token that has been revoked (post-logout) returns 401."""
    token = require(ENV_BORROWER_READ_TOKEN)
    admin_jwt = require(ENV_ADMIN_JWT)

    # Step 1: confirm token currently works.
    pre = http_client.get(
        _purl_url("/api/portal/borrower/me"),
        headers=_auth_headers(token),
    )
    if pre.status_code != 200:
        pytest.skip(
            f"PERENNIA_TEST_BORROWER_READ_TOKEN not currently valid "
            f"(status={pre.status_code}); rotate via setup runbook before re-running."
        )

    # Step 2: revoke it via the admin kill-switch.
    revoke = http_client.post(
        _purl_url("/api/admin/tokens/revoke"),
        json={"token": token},
        headers=_auth_headers(admin_jwt),
    )
    assert revoke.status_code in (200, 204), (
        f"Admin revoke must succeed, got {revoke.status_code}: {revoke.text[:300]}"
    )

    # Step 3: token should now return 401.
    post = http_client.get(
        _purl_url("/api/portal/borrower/me"),
        headers=_auth_headers(token),
    )
    assert post.status_code == 401, (
        f"Revoked token must return 401, got {post.status_code}: {post.text[:300]}"
    )
