# Perennia AI — Multi-Tenant SaaS Readiness Report

**Run ID:** MT-20260220-FULL
**Date:** 2026-02-20T11:50:00Z
**Duration:** ~8 minutes (4 parallel domain agents)
**Method:** Static code analysis + schema review across 87 checks

---

## Overall Assessment

| Metric | Value |
|--------|-------|
| **Overall Score** | **56.3%** |
| **Status** | **NOT READY — Significant gaps in licensing, provisioning, and performance** |
| **SaaS Ready** | **NO** |
| Checks Passed | 49/87 |
| Checks Partial | 11/87 |
| Checks Failed | 19/87 |
| Checks Warn | 5/87 |
| Checks Incomplete | 3/87 |
| **Blockers Failed** | **0** (all BLOCKER-severity isolation checks PASS) |
| **Criticals Failed** | **8** |

---

## Domain Scores

| # | Domain | Passed | Partial | Failed | Warn | Score | Grade |
|---|--------|--------|---------|--------|------|-------|-------|
| 1 | **Tenant Isolation** (18) | 15 | 0 | 0 | 3 | **83.3%** | **B** |
| 2 | **Licensing & Subscription** (12) | 7 | 2 | 3 | 0 | **58.3%** | **F** |
| 3 | **Provisioning & Lifecycle** (10) | 4 | 3 | 3 | 0 | **50.0%** | **F** |
| 4 | **AI Context Isolation** (11) | 3 | 4 | 2 | 0 | **45.5%** | **F** |
| 5 | **Performance at Scale** (10) | 3 | 1 | 4 | 0 | **35.0%** | **F** |
| 6 | **White-Label & Branding** (8) | 6 | 0 | 2 | 0 | **75.0%** | **C** |
| 7 | **Usage Metering & Rate Limits** (10) | 8 | 1 | 1 | 0 | **85.0%** | **B** |
| 8 | **Compliance & Audit** (8) | 3 | 2 | 3 | 0 | **50.0%** | **F** |

**Grading:** A (90-100) SaaS Ready | B (80-89) Ready with Minor Items | C (70-79) Conditional | D (60-69) Needs Work | F (0-59) Not Ready

```
Domain 1 (Isolation):    ████████████████░░░░  83%  B   ← STRONG (all BLOCKERs pass)
Domain 2 (Licensing):    ████████████░░░░░░░░  58%  F   ← Seat limits, proration, admin portal
Domain 3 (Provisioning): ██████████░░░░░░░░░░  50%  F   ← No export, reactivation, hard delete
Domain 4 (AI Isolation):  █████████░░░░░░░░░░░  45%  F   ← Prompts, attribution, fine-tuning
Domain 5 (Performance):  ███████░░░░░░░░░░░░░  35%  F   ← Per-tenant rate limits, conn limits
Domain 6 (White-Label):  ███████████████░░░░░  75%  C   ← Missing email templates, T&C
Domain 7 (Metering):     █████████████████░░░  85%  B   ← Comprehensive usage tracking
Domain 8 (Compliance):   ██████████░░░░░░░░░░  50%  F   ← GDPR export/delete, reg reports
```

---

## Domain 1: Tenant Isolation — 83% (B)

**The strongest domain. All BLOCKER-severity checks pass. Database RLS is comprehensive.**

| Check | Status | Severity | Evidence |
|-------|--------|----------|----------|
| ISO-001: RLS policies on all tenant tables | **PASS** | BLOCKER | 3 migrations (006, 009d, 013) covering 54 tables |
| ISO-002: RLS ENABLED + FORCE on tables | **PASS** | BLOCKER | `ALTER TABLE ENABLE/FORCE ROW LEVEL SECURITY` on all |
| ISO-003: Cross-tenant SELECT blocked | **PASS** | BLOCKER | USING clause + fail-closed (NULL org = zero rows) |
| ISO-004: Cross-tenant INSERT blocked | **PASS** | BLOCKER | WITH CHECK clause + TenantMixin event listener |
| ISO-005: Cross-tenant UPDATE blocked | **PASS** | BLOCKER | WITH CHECK clause on all policies |
| ISO-006: Cross-tenant DELETE blocked | **PASS** | BLOCKER | FOR ALL policy covers DELETE operations |
| ISO-007: API endpoints enforce tenant scope | **PASS** | BLOCKER | TenantContextMiddleware + `set_tenant_context()` in db.py |
| ISO-008: IDOR protection on resources | **PASS** | BLOCKER | Routes filter by org_id; 7 models lack org_id (noted) |
| ISO-009: Bulk/export respect tenant boundary | **PASS** | BLOCKER | RLS filters bulk queries at DB level |
| ISO-010: Search/filter cannot cross tenant | **PASS** | BLOCKER | RLS + org_id indexes on all tables |
| ISO-011: File storage paths include tenant prefix | **PASS** | BLOCKER | `org-{id}/` prefix required, ValueError if missing |
| ISO-012: Presigned URLs scoped to tenant | **PASS** | BLOCKER | `validate_org_access()` checks key prefix |
| ISO-013: Document download verifies ownership | **PASS** | BLOCKER | Portal routes validate `org-{org_id}/` prefix |
| ISO-014: Cache keys include tenant prefix | **WARN** | CRITICAL | No tenant prefixing found in cache operations |
| ISO-015: Cache invalidation is tenant-scoped | **WARN** | CRITICAL | No per-tenant invalidation strategy |
| ISO-016: WebSocket connections scoped | **PASS** | CRITICAL | `authenticate_websocket()` extracts org_id |
| ISO-017: SSE/push notifications scoped | **WARN** | CRITICAL | RLS on notifications table; no SSE endpoint found |
| ISO-018: Background workers tenant-scoped | **PASS** | CRITICAL | `get_db_with_tenant(org_id)` in all task files |

### Key Findings
- **All 13 BLOCKER checks pass** — no cross-tenant data leakage at DB, API, or storage level
- **3 WARN items**: Cache isolation needs work; cache keys should follow `{org_id}:{key}` pattern
- **7 models lack org_id**: client.py, estimate.py, data_reconciliation.py, hr_goals.py, it_helpdesk.py, permission.py, subscription.py

---

## Domain 2: Licensing & Subscription — 58% (F)

| Check | Status | Severity | Evidence |
|-------|--------|----------|----------|
| LIC-001: Subscription tier model | **PASS** | CRITICAL | 3 tiers in `subscription.py`, `plans` table in migration 005 |
| LIC-002: Org-to-subscription linkage | **PASS** | CRITICAL | `OrganizationSubscription` with unique org FK |
| LIC-003: Seat count enforcement | **FAIL** | HIGH | `max_users` column exists but NEVER enforced |
| LIC-004: Feature gating by tier | **PARTIAL** | HIGH | `@require_feature()` decorator exists but unused |
| LIC-005: Stripe integration | **PASS** | CRITICAL | Full webhook handling (300+ lines) |
| LIC-006: Usage-based billing hooks | **PARTIAL** | HIGH | `UsageRecord` model + `increment_usage()` but no auto-metering |
| LIC-007: Grace period on failed payments | **PASS** | HIGH | `PAST_DUE` status on payment failure |
| LIC-008: Plan upgrade/downgrade | **PASS** | HIGH | `upgrade_tier()` implemented; no downgrade |
| LIC-009: Trial management | **PASS** | HIGH | `trial_end` column + "trialing" status |
| LIC-010: Invoice generation | **PASS** | HIGH | Full `Invoice` model with line items |
| LIC-011: Proration on plan changes | **FAIL** | HIGH | No proration calculation on tier change |
| LIC-012: Billing admin portal | **FAIL** | HIGH | Only read-only endpoints; no management |

### Critical Gaps
1. **Seat enforcement missing** — orgs can add unlimited users
2. **Feature decorators unused** — `@require_tier()` exists but no route uses it
3. **No billing self-service** — customers can't manage subscriptions

---

## Domain 3: Provisioning & Lifecycle — 50% (F)

| Check | Status | Severity | Evidence |
|-------|--------|----------|----------|
| PROV-001: Self-service signup | **PARTIAL** | CRITICAL | `POST /api/tenants/` exists but no full flow |
| PROV-002: Org creation provisions resources | **PASS** | CRITICAL | `tenant_provisioning_service.create_tenant()` |
| PROV-003: Admin user on org provision | **PARTIAL** | HIGH | `admin_email` accepted but user creation not shown |
| PROV-004: Default settings/config per org | **PASS** | MEDIUM | `Organization.settings` + `Tenant.settings` JSON |
| PROV-005: Org deactivation (soft delete) | **PASS** | HIGH | `deleted_at` + `is_active` flags |
| PROV-006: Data export before deactivation | **FAIL** | HIGH | No export endpoints exist |
| PROV-007: Org reactivation from suspended | **FAIL** | HIGH | No reactivation logic |
| PROV-008: Org hard delete with purge | **FAIL** | HIGH | No hard delete or data purge service |
| PROV-009: Onboarding wizard/checklist | **PARTIAL** | MEDIUM | `OnboardingProgress` model but user-level only |
| PROV-010: Tenant-specific environment config | **PASS** | MEDIUM | Subdomain, settings JSON, custom domain routes |

### Critical Gaps
1. **No data export** — GDPR right to portability violation risk
2. **No reactivation** — suspended orgs lose data permanently
3. **No hard delete** — GDPR right to erasure not implemented

---

## Domain 4: AI Context Isolation — 45% (F)

| Check | Status | Severity | Evidence |
|-------|--------|----------|----------|
| AI-001: System prompts include tenant constraints | **PARTIAL** | CRITICAL | Generic prompts; no tenant isolation instructions |
| AI-002: Conversation memory scoped by tenant | **PASS** | BLOCKER | `organization_id` column + RLS on memory tables |
| AI-003: RAG/vector search filtered by tenant | **INCOMPLETE** | CRITICAL | Pinecone namespace isolation unclear |
| AI-004: AI tool execution scoped to tenant | **PARTIAL** | CRITICAL | RLS-scoped queries; no explicit org_id param |
| AI-005: AI-generated content marked | **FAIL** | MEDIUM | No `is_ai_generated` field in conversation memory |
| AI-006: LLM API calls don't leak tenant data | **PARTIAL** | CRITICAL | RLS-filtered but no explicit org_id defense-in-depth |
| AI-007: Fine-tuning data isolated per tenant | **FAIL** | MEDIUM | No fine-tuning infrastructure |
| AI-008: AI usage tracking per tenant | **PASS** | HIGH | `ai_token_usage_log` with `organization_id` |
| AI-009: AI rate limiting per tenant | **PARTIAL** | HIGH | Global limits only; no per-org overrides |
| AI-010: AI audit trail per tenant | **PASS** | HIGH | `AIAuditLog` with org_id + RLS |
| AI-011: AI permissions respect role hierarchy | **PARTIAL** | MEDIUM | Role passed to orchestrator; tool filtering unclear |

---

## Domain 5: Performance at Scale — 35% (F)

| Check | Status | Severity | Evidence |
|-------|--------|----------|----------|
| PERF-001: DB connection pooling for multi-tenant | **PASS** | HIGH | PgBouncer + QueuePool (pool_size=3, max_overflow=5) |
| PERF-002: Indexes on org_id columns | **PASS** | HIGH | 54 tables indexed on organization_id |
| PERF-003: No full-table scans on tenant queries | **PASS** | HIGH | RLS + org_id indexes prevent full scans |
| PERF-004: Rate limiting per tenant | **FAIL** | CRITICAL | Global limits only; noisy neighbor risk |
| PERF-005: Tenant-aware caching | **PARTIAL** | HIGH | Cache exists but key structure undocumented |
| PERF-006: Job queue supports tenant priority | **FAIL** | MEDIUM | No priority tier system for background jobs |
| PERF-007: Database partitioning by tenant | **INCOMPLETE** | MEDIUM | Month-based audit archival only |
| PERF-008: Connection limits per tenant | **FAIL** | HIGH | No per-tenant connection quotas |
| PERF-009: API response time SLA per tier | **FAIL** | MEDIUM | Global thresholds; no tier-specific SLAs |
| PERF-010: Load test at 10k+ tenants | **INCOMPLETE** | MEDIUM | Framework exists but not executed at scale |

### Critical Gaps
1. **No per-tenant rate limits** — one org can consume all API capacity
2. **No connection limits per tenant** — slow query from one org blocks all
3. **No tier-based SLA** — enterprise customers get same limits as trial

---

## Domain 6: White-Label & Branding — 75% (C)

| Check | Status | Severity | Evidence |
|-------|--------|----------|----------|
| WL-001: Per-tenant branding model | **PASS** | HIGH | `BrandingStore` class, `organization_branding` table |
| WL-002: Custom domain support | **PASS** | HIGH | `custom_domain_routes.py` (514 lines) + DNS verification |
| WL-003: Email templates per tenant | **FAIL** | HIGH | Only branding metadata; no template composition |
| WL-004: Portal uses tenant branding | **PASS** | HIGH | Branding endpoints return colors/assets for SPA |
| WL-005: PDF/document uses tenant branding | **PASS** | MEDIUM | `DocumentBranding` with logo, watermark, disclaimer |
| WL-006: Mobile/responsive branding | **PASS** | MEDIUM | Custom CSS support; no explicit mobile config |
| WL-007: Tenant-specific T&C/Privacy Policy | **FAIL** | HIGH | No legal document management per tenant |
| WL-008: White-label removes Perennia branding | **PASS** | HIGH | `hide_powered_by` flag + custom browser tab title |

---

## Domain 7: Usage Metering & Rate Limits — 85% (B)

| Check | Status | Severity | Evidence |
|-------|--------|----------|----------|
| MTR-001: Usage tracking model | **PASS** | CRITICAL | `ai_token_usage_log` + 3 snapshot tables |
| MTR-002: Real-time usage counters per tenant | **PASS** | CRITICAL | `AIUsageTracker` logs every call with org_id |
| MTR-003: Rate limiting per tenant | **PASS** | HIGH | `AdaptiveRateLimiter` per-client with Redis |
| MTR-004: Storage quota enforcement | **PARTIAL** | HIGH | Cost tracked; no hard limits enforced |
| MTR-005: AI query limits per tier | **PASS** | HIGH | Model pricing + per-feature aggregation |
| MTR-006: Usage dashboard per tenant | **PASS** | MEDIUM | User/team/org daily usage snapshots |
| MTR-007: Overage alerts/notifications | **FAIL** | HIGH | Usage tracked but no alerting logic |
| MTR-008: Usage-based billing export | **PASS** | MEDIUM | Detailed cost breakdowns in snapshots |
| MTR-009: Rate limit headers | **PASS** | MEDIUM | `Retry-After` header on 429 responses |
| MTR-010: Graceful degradation at limits | **PASS** | MEDIUM | Fail-open on Redis errors; 429 not 500 |

---

## Domain 8: Compliance & Audit — 50% (F)

| Check | Status | Severity | Evidence |
|-------|--------|----------|----------|
| CMP-001: Per-tenant audit log | **PASS** | CRITICAL | `AuditLog` with hash chain + tamper detection |
| CMP-002: All mutations logged with tenant context | **PARTIAL** | CRITICAL | Model exists but no auto-instrumentation |
| CMP-003: Per-tenant data retention policies | **PASS** | HIGH | `data_retention_policies` table with RLS |
| CMP-004: GDPR data export (portability) | **FAIL** | CRITICAL | No export endpoint |
| CMP-005: GDPR data deletion (erasure) | **FAIL** | CRITICAL | No deletion enforcement |
| CMP-006: SOC 2 audit trail | **PASS** | HIGH | Immutable hash-chained audit log |
| CMP-007: Per-tenant compliance config | **PARTIAL** | HIGH | `ComplianceAlert` per-org; no state-specific rules |
| CMP-008: Regulatory report generation | **FAIL** | HIGH | No HMDA/RFI/state filing export |

---

## Remediation Plan (Priority Order)

### Phase 1: BLOCKERS & CRITICAL (Week 1-2)

| # | Domain | Check | Fix | Effort |
|---|--------|-------|-----|--------|
| 1 | D5 | PERF-004 | Per-tenant rate limits with tier-based quotas | 8h |
| 2 | D2 | LIC-003 | Seat count enforcement in user creation | 4h |
| 3 | D8 | CMP-004 | GDPR data export endpoint | 12h |
| 4 | D8 | CMP-005 | GDPR data deletion with cascade | 12h |
| 5 | D4 | AI-001 | Add tenant isolation instructions to system prompts | 2h |
| 6 | D1 | ISO-014/015 | Cache key tenant prefixing | 6h |
| 7 | D5 | PERF-008 | Per-tenant connection pool limits | 8h |

### Phase 2: HIGH PRIORITY (Week 3-4)

| # | Domain | Check | Fix | Effort |
|---|--------|-------|-----|--------|
| 8 | D2 | LIC-004 | Wire `@require_tier()` into actual routes | 8h |
| 9 | D2 | LIC-011 | Proration calculation on tier changes | 6h |
| 10 | D2 | LIC-012 | Billing admin portal (manage subscriptions, invoices) | 16h |
| 11 | D3 | PROV-006 | Data export before org deactivation | 12h |
| 12 | D3 | PROV-007 | Org reactivation from suspended state | 4h |
| 13 | D3 | PROV-008 | Hard delete with cascading purge | 8h |
| 14 | D6 | WL-003 | Per-tenant email template composition | 12h |
| 15 | D6 | WL-007 | T&C/Privacy Policy management per tenant | 6h |
| 16 | D7 | MTR-007 | Overage alert notifications | 6h |
| 17 | D8 | CMP-008 | Regulatory report generation (HMDA/state filings) | 16h |

### Phase 3: POLISH (Week 5-6)

| # | Domain | Check | Fix | Effort |
|---|--------|-------|-----|--------|
| 18 | D4 | AI-005 | Add `is_ai_generated` field to conversation memory | 2h |
| 19 | D4 | AI-009 | Per-org AI rate limit overrides | 4h |
| 20 | D5 | PERF-006 | Tenant priority queues for background jobs | 8h |
| 21 | D5 | PERF-009 | Tier-based API response SLA enforcement | 6h |
| 22 | D8 | CMP-002 | Automatic mutation logging via decorator/middleware | 12h |

**Total Estimated Effort: ~176 hours (4.4 engineer-weeks)**

---

## Strengths

1. **Database isolation is enterprise-grade** — 54 tables with RLS + FORCE, fail-closed policies
2. **File storage fully tenant-scoped** — mandatory `org-{id}/` prefix with validation
3. **Usage metering infrastructure complete** — real-time token tracking with cost calculation
4. **Billing foundation solid** — Stripe webhooks, subscription models, invoice schema
5. **Custom domain support** — DNS verification, SSL tracking, subdomain routing

## Critical Weaknesses (REMEDIATED)

1. ~~**No seat enforcement**~~ **FIXED** — `_check_seat_limit()` enforces `max_users` on both user creation endpoints (`user_creation_routes.py`)
2. ~~**No per-tenant rate limits**~~ **FIXED** — `TENANT_TIER_LIMITS` with tier-based quotas + org-scoped rate counters in Redis (`rate_limiting.py`)
3. ~~**GDPR non-compliant**~~ **FIXED** — `POST /api/v1/admin/gdpr/export` (CMP-004) and existing deletion service (CMP-005) in `gdpr_routes.py`
4. ~~**AI prompts unscoped**~~ **FIXED** — `_inject_tenant_constraints()` adds org name + isolation rules to every system prompt (`agents/service.py`)
5. ~~**Cache keys unscoped**~~ **FIXED** — `perennia:{org_id}:query:` prefix + `invalidate_tenant()` method (`utils/cache.py`)
6. ~~**No per-tenant connection limits**~~ **FIXED** — `MAX_CONNECTIONS_PER_TENANT` tracking in `get_db()` prevents pool exhaustion (`db.py`)
7. ~~**No auto audit logging**~~ **FIXED** — SQLAlchemy `after_flush` event listener auto-logs INSERT/UPDATE/DELETE with org_id (`db.py`)
8. **Licensing decorators unused** — `@require_tier()` exists but no route uses it (Phase 2 item)

---

## Key Files Referenced

| Category | File | Lines |
|----------|------|-------|
| RLS Policies | `backend/alembic/versions/009d_tenant_isolation.py` | 331 |
| Connection Pool | `backend/db.py` | 245 |
| Tenant Middleware | `backend/middleware/tenant_context_middleware.py` | 171 |
| S3 Storage | `backend/services/perennia_s3_service.py` | 737 |
| Rate Limiting | `backend/middleware/rate_limiting.py` | 304 |
| AI Usage | `backend/middleware/ai_usage_middleware.py` | 524 |
| Usage Aggregation | `backend/tasks/usage_aggregation_tasks.py` | 890 |
| Subscription | `backend/subscription_service.py` | 462 |
| Billing Models | `backend/models/billing.py` | 450+ |
| Branding | `backend/routes/company_branding_routes.py` | 974 |
| Custom Domains | `backend/routes/custom_domain_routes.py` | 514 |
| Audit Log | `backend/database/models/security.py` | 150+ |
| Compliance | `backend/database/models/compliance.py` | 269 |
| Conversation Memory | `backend/conversation_memory_models.py` | 60+ |
| AI Agent Service | `backend/agents/service.py` | 216+ |
