# Portal Consolidation — Follow-up Plan (Tasks 4 & 5)

> Continuation of `2026-05-29-portal-consolidation.md`. Phases 0/1/3 are complete and committed. Tasks 4 and 5 were found to be **architecturally blocked** during execution — they are NOT frontend-only changes. This plan scopes the real (backend-led) work each requires. **Do not attempt either as a simple redirect/delete — both premises in the original plan were verified false.**

**Tech Stack:** FastAPI/SQLAlchemy/PostgreSQL backend, React/Vite frontend. Same legacy↔PURL split that forced the Phase 1 IDOR fix is the root cause of both blockers here.

---

## Background: why these are blocked (verified 2026-05-30)

There are two parallel borrower-portal backends that were never unified:
- **Legacy:** `portal_routes.py` + `PortalLoan`/`portal_loans` + `portal_lifecycle_service` + a separate **access-token** system (`/portal/access/{token}`, `/borrower-portal/{token}` links).
- **PURL (live):** `purl_routes.py` + `PURLLoan`/`purl_loans` + `purl_workspace_service`, **slug-keyed**, PURL-access-token auth. The live portal stack (`PortalContainer` → stage portals) runs on this.

Tasks 4 and 5 both assumed these were closer than they are.

---

## Task 4 — Fold `BorrowerPortal` into the canonical stack

**Original (locked) plan:** redirect `/borrower-portal/:token` → `/portal/:slug`, retire `BorrowerPortal`.

**Why it's blocked (verified):**
- `/portal/access/{token}` (legacy) returns **no workspace slug** and **no redirect_url** — there is nothing for a frontend redirect to target.
- **No PURL endpoint maps an access token → a workspace slug** (confirmed: 0 same-line `token…slug` resolvers in `purl_routes.py`; the only token/access endpoints are legacy `/access/{token}` and `/partner/{access_token}`).
- The backend **still emits `/borrower-portal/{token}` links** (`portal_routes.py:1961,1997`) as an auth redirect fallback. A blind frontend redirect would break live borrower access for anyone arriving on those links.

**What it actually requires (backend-first):**

- [ ] **Step 1 — Bridge endpoint.** Add a PURL (or legacy) endpoint that, given a borrower access token, resolves the borrower's `PURLWorkspace` and returns its `slug` (scoped/authorized to that token). Decide whether the legacy access token can be exchanged for a PURL context, or whether a borrower needs a PURL token minted.
- [ ] **Step 2 — Decide the canonical token story.** Either (a) migrate `/borrower-portal/{token}` link generation to emit `/portal/{slug}?token=…` PURL links, or (b) keep the legacy link but have it server-redirect to the resolved slug. Pick one; document it.
- [ ] **Step 3 — Frontend redirect.** Only after Step 1 exists: `/borrower-portal/:token` resolves token→slug via the new endpoint and `Navigate`s into `/portal/:slug`. Map every datum `BorrowerPortal` rendered to its `PortalContainer`-stack equivalent first (the API-surface check from the original plan still applies).
- [ ] **Step 4 — Retire `BorrowerPortal.jsx`** once the redirect is verified end-to-end with a real token, and update/retire the backend `/borrower-portal/{token}` link emission.

**Risk:** auth + tenant isolation (same class as the Phase 1 IDOR). Route through Security review.

---

## Task 5 — Consolidate the API clients

**Original (locked) plan:** delete `lib/api/client.js` (assumed 0 imports), migrate 2 stragglers off `utils/api/client.js`, standardize on `services/api/client.js`.

**Why the premise is false (verified):** `lib/api` is **not** dead — it has **7 live importers**, including the entire live portal stack (`PortalContainer`, `ActiveLoanPortal`, `MUMPortal`), `PURLPortal.js`, `AdminDocumentReviewQueue.js`, and the Phase-1 `usePortalRealtime` hook + its test. Phase 1 also **added** `getBorrowerDashboard` to it. There is no dead client to delete.

**What it actually is:** three *actively-used* clients with different auth models —
- `services/api/client.js` (12 importers): axios, CSRF + LO-token refresh, offline cache. The LO/main-app client.
- `lib/api/client.js` (7 importers): `PerenniaAPI` class, `setAuthToken` holds the **PURL token** in instance memory. The borrower/portal client.
- `utils/api/client.js` (2 importers): thin axios wrapper.

These are not redundant copies — `services/api` is LO-authed and `lib/api` is PURL-authed. Merging them risks cross-contaminating LO and borrower tokens (the exact hazard behind the Phase 1 work).

**Revised scope (separate, lower-priority refactor):**
- [ ] **Step 1 — Retire only `utils/api/client.js`.** Migrate its 2 importers (`CreateTaskModal`, `esignApi`) to `services/api/client.js`. This is the only safe, clear consolidation.
- [ ] **Step 2 — Document, don't merge, the LO vs PURL split.** Add a header comment to each client stating its auth model and intended consumers, so the "3 clients" looks intentional rather than accidental.
- [ ] **Step 3 — (Optional, large)** If a true single client is desired later, it must explicitly model two auth contexts (LO token vs PURL token) — a dedicated design with Security review, not a delete.

**Do NOT delete `lib/api/client.js`.** It is the borrower portal's data layer.

---

## Sequencing

Task 4 is the higher-value, higher-risk item (real borrower-facing feature + auth). Task 5 Step 1 is a small safe cleanup that can happen anytime. Both are independent of the committed Phases 0/1/3.
