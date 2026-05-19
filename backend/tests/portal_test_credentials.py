"""
Portal Test Credentials Harness
================================

Centralized accessor for portal-related test secrets.

Real values are NEVER committed. Values are read from environment variables that
must be provisioned by the repo owner in:
  - Local dev: shell exports / `.env.test` (gitignored).
  - CI: GitHub Actions repository secrets (see `.github/workflows/golden-tests.yml`).
  - Staging: Railway environment variables on the test workspace.

If a required secret is missing, the helper returns `None` and the calling test
should `pytest.skip(...)` with a clear message — never silently pass.

See `docs/portal_test_credentials_setup.md` for the provisioning runbook.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Env var names — single source of truth
# ---------------------------------------------------------------------------

ENV_PURL_TOKEN = "PERENNIA_TEST_PURL_TOKEN"
ENV_PURL_TOKEN_TENANT_A = "PERENNIA_TEST_PURL_TOKEN_TENANT_A"
ENV_PURL_TOKEN_TENANT_B = "PERENNIA_TEST_PURL_TOKEN_TENANT_B"
ENV_ADMIN_JWT = "PERENNIA_TEST_ADMIN_JWT"
ENV_WORKSPACE_ID = "PERENNIA_TEST_WORKSPACE_ID"
ENV_BORROWER_READ_TOKEN = "PERENNIA_TEST_BORROWER_READ_TOKEN"
ENV_EXPIRED_TOKEN = "PERENNIA_TEST_EXPIRED_TOKEN"


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------

def _get(name: str) -> Optional[str]:
    val = os.environ.get(name)
    return val if val and val.strip() else None


def get_purl_token() -> Optional[str]:
    """Generic borrower PURL token (default tenant)."""
    return _get(ENV_PURL_TOKEN)


def get_purl_token_tenant_a() -> Optional[str]:
    """PURL token bound to Tenant A — used for cross-tenant isolation tests."""
    return _get(ENV_PURL_TOKEN_TENANT_A)


def get_purl_token_tenant_b() -> Optional[str]:
    """PURL token bound to Tenant B — paired with Tenant A for isolation tests."""
    return _get(ENV_PURL_TOKEN_TENANT_B)


def get_admin_jwt() -> Optional[str]:
    """RS256 JWT for an admin user in the test workspace."""
    return _get(ENV_ADMIN_JWT)


def get_workspace_id() -> Optional[str]:
    """UUID of the dedicated test workspace."""
    return _get(ENV_WORKSPACE_ID)


def get_borrower_read_token() -> Optional[str]:
    """Read-only borrower portal token (no write scopes)."""
    return _get(ENV_BORROWER_READ_TOKEN)


def get_expired_token() -> Optional[str]:
    """Pre-minted PURL token whose `exp` claim is in the past."""
    return _get(ENV_EXPIRED_TOKEN)


# ---------------------------------------------------------------------------
# Skip helpers — call from a test to require a secret
# ---------------------------------------------------------------------------

def require(env_var: str) -> str:
    """Return the secret or pytest.skip with a clear message."""
    val = _get(env_var)
    if val is None:
        pytest.skip(
            f"Skipping — {env_var} not provisioned. "
            f"See docs/portal_test_credentials_setup.md for setup instructions."
        )
    return val


@dataclass(frozen=True)
class PortalCreds:
    """Bundle of every secret needed for the full portal test matrix."""

    purl_token: Optional[str]
    purl_token_tenant_a: Optional[str]
    purl_token_tenant_b: Optional[str]
    admin_jwt: Optional[str]
    workspace_id: Optional[str]
    borrower_read_token: Optional[str]
    expired_token: Optional[str]

    @property
    def fully_provisioned(self) -> bool:
        return all(
            v is not None
            for v in (
                self.purl_token,
                self.purl_token_tenant_a,
                self.purl_token_tenant_b,
                self.admin_jwt,
                self.workspace_id,
                self.borrower_read_token,
                self.expired_token,
            )
        )


def load_creds() -> PortalCreds:
    return PortalCreds(
        purl_token=get_purl_token(),
        purl_token_tenant_a=get_purl_token_tenant_a(),
        purl_token_tenant_b=get_purl_token_tenant_b(),
        admin_jwt=get_admin_jwt(),
        workspace_id=get_workspace_id(),
        borrower_read_token=get_borrower_read_token(),
        expired_token=get_expired_token(),
    )
