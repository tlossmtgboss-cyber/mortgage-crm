# Portal Test Credentials — Setup Runbook

Owner: Platform team
Last updated: 2026-05-19
Audience: Repo owner / SRE provisioning CI secrets

This document explains every secret consumed by the portal integration test
suite (`backend/tests/integration/test_portal_purl_auth.py`), how to mint each
one safely, and which specific test it unblocks.

Until these secrets are provisioned, the affected tests will `pytest.skip(...)`
with a clear message — they will NOT fail the pipeline. Provisioning unlocks
real coverage and removes the D6 ("portal auth unverified") penalty from the
master challenge report.

---

## Where to Set the Secrets

| Environment    | Mechanism                                                   |
|----------------|-------------------------------------------------------------|
| Local dev      | Shell exports or `.env.test` (gitignored)                   |
| GitHub Actions | Repo → Settings → Secrets and variables → Actions → Secrets |
| Staging CI     | Railway service env vars on the test workspace              |

The accessor module is `backend/tests/portal_test_credentials.py` — it is the
single source of truth for env-var names and the `require()` skip behavior.

---

## Secret Inventory

### 1. `PERENNIA_TEST_API_BASE_URL`
- **What:** Base URL of the API under test (no trailing slash).
- **Example:** `https://api.staging.perenniaai.com`
- **How to provision:** Use the staging API host. NEVER point at production.
- **Unblocks:** all five tests (used as the request target).

### 2. `PERENNIA_TEST_PURL_TOKEN`
- **What:** A valid borrower PURL token in the test workspace.
- **How to mint:**
  1. Log in to the staging app as a test LO.
  2. Create a synthetic borrower (`test-borrower@perennia.test`).
  3. Trigger the "Send PURL" action, intercept the magic-link URL, decode the
     `?token=` query param.
- **Rotation:** Every 30 days (PURL tokens default to 90-day expiry).
- **Unblocks:** **UA-001** (valid token returns borrower payload).

### 3. `PERENNIA_TEST_EXPIRED_TOKEN`
- **What:** A pre-minted PURL token whose `exp` claim is in the past.
- **How to mint:** Use the `scripts/mint_test_purl_token.py` helper with
  `--ttl -3600` (forces a token that expired one hour ago). The token is
  signed with the same RS256 key as production-test, so the signature is
  valid but the time check fails.
- **Rotation:** Never expires — it's already expired by design.
- **Unblocks:** **UA-002** (expired token returns 401).

### 4. `PERENNIA_TEST_PURL_TOKEN_TENANT_A`
- **What:** PURL token bound to test workspace **A**.
- **How to mint:** Same as `PERENNIA_TEST_PURL_TOKEN`, but inside the dedicated
  Tenant A test workspace (UUID: see `PERENNIA_TEST_WORKSPACE_ID` for primary;
  Tenant A may be a separate ID — record both).
- **Rotation:** 30 days.
- **Unblocks:** **UA-006** (cross-tenant denial) and **UA-011** (isolation).

### 5. `PERENNIA_TEST_PURL_TOKEN_TENANT_B`
- **What:** PURL token bound to a *different* test workspace **B**.
- **How to mint:** Create a second test workspace (`perennia-test-tenant-b`),
  add a synthetic borrower, mint a PURL token there.
- **Rotation:** 30 days.
- **Unblocks:** **UA-011** (multi-tenant isolation paired with Tenant A).

### 6. `PERENNIA_TEST_TENANT_B_LOAN_ID`
- **What:** UUID of a loan owned by Tenant B that Tenant A must NOT see.
- **How to provision:** Pick any loan ID from the Tenant B workspace seed data.
- **Rotation:** Static — only rotate if the seed loan is deleted.
- **Unblocks:** **UA-006** (cross-tenant denial).

### 7. `PERENNIA_TEST_ADMIN_JWT`
- **What:** RS256 JWT for an admin user in the test workspace, valid for at
  least 24 hours.
- **How to mint:**
  1. Log in via the standard `/api/auth/login` endpoint as
     `admin@perennia.test`.
  2. Copy the `access_token` from the response.
- **Rotation:** Daily (access tokens expire in 15 min in prod — for tests we
  use a longer-lived test-only key). Better: have CI mint a fresh one in a
  pre-step using stored username/password (more secure than storing the JWT).
- **Unblocks:** **UA-012** (token revocation via admin endpoint).

### 8. `PERENNIA_TEST_WORKSPACE_ID`
- **What:** UUID of the primary test workspace.
- **How to provision:** Read from the `workspaces` table after creating the
  test workspace via the onboarding flow.
- **Rotation:** Never (static identifier).
- **Unblocks:** Helper context for several tests (referenced in fixtures).

### 9. `PERENNIA_TEST_BORROWER_READ_TOKEN`
- **What:** Read-only borrower portal token (no write/upload scopes).
- **How to mint:** Same as `PERENNIA_TEST_PURL_TOKEN`, but generated against
  a borrower whose role only has `borrower:read` scope.
- **Rotation:** 30 days.
- **Unblocks:** **UA-012** (token revocation test — needs a sacrificial token
  that gets revoked mid-test).

---

## Local Quickstart

```bash
export PERENNIA_TEST_API_BASE_URL="https://api.staging.perenniaai.com"
export PERENNIA_TEST_PURL_TOKEN="eyJ..."
export PERENNIA_TEST_EXPIRED_TOKEN="eyJ..."
export PERENNIA_TEST_PURL_TOKEN_TENANT_A="eyJ..."
export PERENNIA_TEST_PURL_TOKEN_TENANT_B="eyJ..."
export PERENNIA_TEST_ADMIN_JWT="eyJ..."
export PERENNIA_TEST_WORKSPACE_ID="00000000-0000-0000-0000-000000000001"
export PERENNIA_TEST_BORROWER_READ_TOKEN="eyJ..."
export PERENNIA_TEST_TENANT_B_LOAN_ID="00000000-0000-0000-0000-0000000000B1"

pytest backend/tests/integration/test_portal_purl_auth.py -v
```

---

## CI Wiring

The wiring is already in place in `.github/workflows/golden-tests.yml` —
look for the `Run golden + integration tests` step. Every secret above is
mapped via `${{ secrets.<NAME> }}` into the job's environment. When the repo
owner adds the secret in GitHub, the next CI run picks it up automatically.

No code changes required to flip a test from "skipped" to "running".

---

## Security Notes

- Tokens are sensitive — never log them, never paste them into Slack/issues.
- Rotate every 30 days at minimum.
- Use dedicated test workspaces. NEVER mint test tokens against production tenants.
- Admin JWT should be short-lived (≤24h). Prefer a CI pre-step that mints
  a fresh JWT from username/password stored as secrets, rather than storing
  the JWT itself.
- All test tokens must be revocable via `/api/admin/tokens/revoke` — that's
  the same endpoint UA-012 exercises.

---

## Failure Modes

| Symptom | Likely cause |
|---------|--------------|
| All five tests SKIPPED | Secrets not provisioned. Follow this runbook. |
| UA-001 SKIPPED but UA-002 runs | Partial provisioning. Mint `PERENNIA_TEST_PURL_TOKEN`. |
| UA-001 fails with 401 | `PERENNIA_TEST_PURL_TOKEN` has expired or rotated. Re-mint. |
| UA-012 fails at step 1 (pre-revoke 200) | `PERENNIA_TEST_BORROWER_READ_TOKEN` has expired. Re-mint. |
| UA-006 returns 200 instead of 401/403/404 | **Bug** — cross-tenant RLS leak. File a P0. |
| UA-011 overlap detected | **Bug** — multi-tenant isolation broken. File a P0. |
