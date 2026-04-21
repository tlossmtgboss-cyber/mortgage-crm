# Integration Checklist — Every Finding Mapped to Code

Every item in the original audit, mapped to the file(s) that resolve it. Check
each before considering the PR merge-ready.

## Critical Findings (audit items 1–3, #6 from HIGH)

- [ ] **#1 Hardcoded secrets in `.env.test` and `.env`**
  → `01-secrets/README.md` (rotation checklist)
  → `01-secrets/scan-leaks.sh`, `scrub-history.sh`
  → `01-secrets/.pre-commit-config.yaml`, `.gitleaks.toml` (prevention)

- [ ] **#2 JWT in localStorage**
  → `03-auth/backend/routes.py` (httpOnly cookies on login)
  → `03-auth/frontend/authClient.ts` (cookie-based authFetch)
  → `03-auth/frontend/remove-localstorage-jwt.sh` (codemod)
  → `ci/ci.yml` (forbidden-patterns job blocks regression)

- [ ] **#3 22 npm vulnerabilities**
  → `07-dependencies/README.md` (remediation commands)
  → `07-dependencies/dependabot.yml` (ongoing)
  → `07-dependencies/security-scan.yml` (CI gate)

- [ ] **#6 PII encryption plaintext fallback**
  → `02-encryption/pii_encryption.py` (hard-fail module)
  → `02-encryption/startup.py` (refuses to boot if key missing)
  → `02-encryption/migrate_plaintext_pii.py` (backfill any existing leaks)

## High Findings (audit items 4, 5, 7, 8)

- [ ] **#4 No migration framework**
  → `04-migrations/README.md` (baseline-not-backfill strategy)
  → `04-migrations/env.py`, `alembic.ini`, `script.py.mako`
  → `ci/ci.yml` (migration-check job detects drift)

- [ ] **#5 Sync DB queries in async auth**
  → `03-auth/backend/dependencies.py` (async `get_current_user`)
  → `08-infrastructure/db.py` (async session factory)
  → `ci/ci.yml` forbidden-patterns blocks `session.query` in auth

- [ ] **#7 45MB frontend bundle**
  → `06-frontend/vite.config.ts` (manual chunks)
  → `06-frontend/App.tsx` + `routes/manifest.tsx` (lazy routes)
  → `06-frontend/size-check.mjs` (CI budget gate)

- [ ] **#8 Frontend test coverage <5%**
  → `10-testing/README.md` (tiered targets)
  → `10-testing/critical-paths.spec.ts` (Tier 3 seed)
  → `10-testing/playwright.config.ts` (mobile viewports)
  → `ci/ci.yml` (coverage reporting + Tier 1 95% gate on auth)

## Questionable Decisions

- [ ] **Dual auth systems (RS256 + legacy + SF HS256)**
  → `03-auth/backend/tokens.py` (single source of truth, RS256 everywhere)

- [ ] **Context API only, no state management**
  → `06-frontend/stores/authStore.ts`, `pipelineStore.ts`, `notificationsStore.ts`, `uiStore.ts`

- [ ] **4,843-line App.jsx**
  → `06-frontend/App.tsx` (~60 lines)
  → `06-frontend/routes/manifest.tsx` (data-driven routes)

- [ ] **No PgBouncer**
  → `08-infrastructure/README.md` (Supavisor decision)
  → `08-infrastructure/db.py` (pooled URL handling)

- [ ] **CSRF bypass with unvalidated Bearer**
  → `03-auth/backend/dependencies.py` `verify_csrf` (double-submit cookie)
  → Cookie auth eliminates Bearer path entirely

## Missing for Enterprise (gaps)

- [ ] **No MFA for admin**
  → `03-auth/backend/routes.py` has MFA hook — full MFA module is separate work, flagged
  → `05-audit-logs/service.py` MFA event types ready

- [ ] **No refresh token rotation**
  → `03-auth/backend/refresh_store.py` (rotation + family revoke on theft)

- [ ] **No rate limiting on auth**
  → `08-infrastructure/rate_limit.py`
  → `03-auth/backend/routes.py` `@limiter.limit(AUTH_LOGIN)` etc.

- [ ] **No audit log persistence**
  → `05-audit-logs/model.py`, `service.py`, `middleware.py`
  → `05-audit-logs/0002_create_audit_events.py`

- [ ] **No automated dependency scanning**
  → `07-dependencies/dependabot.yml`, `security-scan.yml`

- [ ] **No database backup verification**
  → `08-infrastructure/backup-verify.yml` (weekly automated restore test)

## Over-Engineering Observations

- [ ] **255 AI tools context bloat**
  → `09-tools/registry.py`, `router.py` (role-scoped loading, 15–40 per call)
  → `09-tools/CONSOLIDATION_NOTES.md` (framework for future deletion)

- [ ] **13 call intelligence agent files / aspirational features**
  → Not addressed in this PR. That's a product decision, not a code fix.

## Post-Deploy Verification

Run `10-testing/post-deploy-verification.sh` after merge. Every check must pass.
