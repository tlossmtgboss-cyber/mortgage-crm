# Perennia AI — Enterprise Remediation PR

**Scope:** All 15 findings from the critical platform audit, end-to-end.
**Strategy:** Single branch cutover. Full JWT migration. No dual-mode.
**Target:** SOC 2 Type II readiness, enterprise sales qualification.

---

## Pre-Flight (Run in Order, Do Not Skip)

This PR is destructive — it rotates credentials, rewrites git history, breaks all active sessions, and changes schema management. You cannot merge it during business hours on Friday.

1. **Tag current state.** `git tag pre-remediation-$(date +%Y%m%d)` so there's a rollback anchor.
2. **Verify full DB backup exists and is restorable.** See `00-preflight/backup-verify.sh`. Do not trust Railway's snapshot alone — run a restore into a scratch DB.
3. **Freeze production writes for the deploy window.** Maintenance page in frontend, reject non-read endpoints at the edge.
4. **Notify any active users** their sessions will terminate.
5. **Have the secrets vault open** (1Password / Doppler / Railway vars) — you'll paste new values during step 01.

---

## Execution Order

Each folder is an independent step. Run in numeric order. Each folder has its own README with commands.

| Step | Folder | Finding(s) Addressed | Breaking? |
|------|--------|---------------------|-----------|
| 00 | preflight | — | No |
| 01 | secrets | #1, #13 | Yes — all API keys rotate |
| 02 | encryption | #6 | Yes — app won't boot without key |
| 03 | auth | #2, #5, and consolidates 3 JWT systems + adds refresh rotation, rate limiting, CSRF fix | Yes — all sessions invalidated |
| 04 | migrations | #4 | No |
| 05 | audit-logs | Enterprise gap: audit persistence | No |
| 06 | frontend | #7, #8, Context-only state decision | No (backward compat) |
| 07 | dependencies | #3, enterprise gap: auto-scanning | No |
| 08 | infrastructure | Railway conn limit, PgBouncer decision | No |
| 09 | tools | Over-engineering: 255 → role-scoped loading | No |
| 10 | testing | Frontend test coverage finding | No |
| ci  | GitHub Actions | Ties everything together | No |

---

## Post-Deploy Verification

After merge and deploy:

1. **Secrets**: `gitleaks detect --source . --no-git` returns zero findings.
2. **Encryption**: Boot app with `PII_ENCRYPTION_KEY` unset — it must refuse to start.
3. **Auth**: Browser devtools shows no JWT in localStorage. Auth cookie has `HttpOnly; Secure; SameSite=Strict`. `/api/auth/refresh` issues new refresh token and old one is rejected.
4. **CSRF**: `curl -X POST /api/... -H "Authorization: Bearer fake"` returns 401, not 200.
5. **Rate limiting**: 10 failed logins from one IP returns 429.
6. **Migrations**: `alembic current` prints the baseline rev. New migration → `alembic upgrade head` runs clean in staging.
7. **Audit logs**: Log in, check `audit_events` table for `USER_LOGIN` row.
8. **Frontend**: Initial bundle under 12MB gzipped. Network tab shows route-based code splits.
9. **npm audit**: Zero criticals, zero highs.
10. **Connection pool**: `SELECT count(*) FROM pg_stat_activity` plateaus well below DB limit under load.

Each check has an automated version in `10-testing/post-deploy-verification.sh`.

---

## Rollback

If post-deploy checks fail:

1. Revert the merge commit.
2. Restore DB from pre-remediation snapshot (step 00).
3. Rotate secrets **again** — the rotated ones are in Railway, the old ones are dead. You cannot roll back secrets.
4. Re-deploy tagged `pre-remediation-*` version.

The one-way door is secrets rotation. Everything else is reversible.

---

## What This PR Does NOT Fix

- **Product scope questions** (255 tools, 388 pages — which drive value). That's a strategy call, not a code change. See `09-tools/CONSOLIDATION_NOTES.md` for a framework but no deletions.
- **Business logic bugs.** This is infrastructure and security hardening.
- **SOC 2 paperwork.** Code controls are here; policies, vendor reviews, and auditor engagement are separate.
