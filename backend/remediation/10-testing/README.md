# 10 — Testing

**Findings addressed:**
- #8 (frontend test coverage <5%, 75 test files for 388 pages)
- Devil's advocate q#4 (can't spin up staging that matches prod)
- Devil's advocate q#10 (mobile test coverage essentially zero)

## Realistic Targets

Getting from <5% to 80% coverage in a single PR is unserious. What we actually ship:

| Tier | Target | What lives here |
|------|--------|-----------------|
| **Tier 1: Auth paths** | 95% line coverage | Everything in `03-auth/` — login, refresh, logout, CSRF, RBAC guards |
| **Tier 2: Critical flows** | 80% branch coverage | Loan stage changes, document upload, pipeline assignment, billing-adjacent paths |
| **Tier 3: Top-20 pages** | Playwright e2e | The 20 most-visited pages (measured via page-visits in usage stats) |
| **Tier 4: Regression fence** | Snapshot tests | Key UI surfaces — pipeline kanban, loan detail, Aria widget |
| **Tier 5: Everything else** | Track, don't block | Coverage reported but not enforced |

Post-merge trajectory: +5 percentage points per month for six months, tracked in a Grafana dashboard.

## What Ships In This PR

1. **`tests/auth/`** — full test suite for the new auth system (Tier 1)
2. **`tests/e2e/critical-paths.spec.ts`** — Playwright tests for login, loan creation, stage advance, document upload, logout (Tier 3 seed)
3. **`post-deploy-verification.sh`** — automated post-merge smoke test suite (also doubles as the runbook at the top of `REMEDIATION.md`)
4. **Coverage CI workflow** — reports coverage on every PR, fails if Tier 1/2 files drop below threshold
5. **Mobile device matrix config** — Playwright project running critical paths on iPhone 14, iPad Pro, iPhone SE viewports

## Execution

```bash
# Backend auth tests
cd backend
pytest tests/auth/ -v --cov=app.auth --cov-fail-under=95

# Frontend component + integration
cd frontend
npm test -- --coverage --run

# Playwright e2e
npx playwright install --with-deps
npx playwright test

# Mobile viewport run
npx playwright test --project=mobile-iphone --project=mobile-ipad
```
