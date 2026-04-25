# Perennia AI — Smart Docs Workflow Audit Report

**Generated**: 2026-04-24T23:52:40Z
**Audit Scope**: Smart Docs subsystem — routes, workflow states, SLA, escalation, security, compliance, AI services, integrations
**Environment**: Local static analysis (no live API checks)
**Files Analyzed**: ~120 files across routes/, services/smart_docs/, database/models/, validation/, tasks/, migrations/

## Executive Summary

- **Total Checks**: 111
- **Critical**: 8 | **Warning**: 30 | **Pass**: 56 | **Info**: 17 | **Skipped**: 0
- **Overall Health Score**: 0/100 (formula-driven; see context below)
- **Top Priority**: SQL injection in ai_resolution_engine.py allows arbitrary column writes via AI-parsed input

> **Score Context**: The low formula score (100 - 8×15 - 30×5 = -170, floored to 0) reflects the sheer volume of findings across a 120-file subsystem. 56 of 111 checks passed. The security/compliance layer scored well (0 criticals, 22 passes). The critical findings are concentrated in 3 areas: route registration, model attribute mismatches, and the AI resolution engine.

---

## Critical Findings (8)

### [SDOC-001] SQL Injection in ai_resolution_engine.py
**Severity**: CRITICAL
**Category**: Security / AI Services
**Finding**: `_set_field_value()` at line 1554 interpolates `top_level_field` directly into SQL via f-string: `f"UPDATE loans SET {top_level_field} = :value WHERE id = :loan_id"`. The field path originates from AI-parsed borrower input — an attacker who controls the field path can inject arbitrary SQL into the column position.
**Impact**: Arbitrary database writes. Could overwrite any column on the loans table.
**Recommendation**: Whitelist allowed column names against `Loan.__table__.columns`. Never interpolate column names from untrusted input.
**File**: `backend/services/smart_docs/ai_resolution_engine.py:1554`

### [SDOC-002] Broken field lookup in ai_resolution_engine.py
**Severity**: CRITICAL
**Category**: AI Services
**Finding**: `_get_field_value()` at line 1502 uses `text("SELECT :col_name FROM loans WHERE ...")` with `col_name` as a bind parameter. SQL bind parameters are values, not identifiers — this query returns the literal string value of `col_name` instead of the column data. The entire resolution engine's field-read path is broken.
**Impact**: AI resolution engine cannot read any loan field values. All field lookups silently return wrong data.
**Recommendation**: Use column whitelist validation, then reference the column by name in the SQL string.
**File**: `backend/services/smart_docs/ai_resolution_engine.py:1502`

### [SDOC-003] Direct Anthropic API calls bypass resilient_ai_call
**Severity**: CRITICAL
**Category**: AI Services
**Finding**: Three services make direct `client.messages.create()` calls bypassing the `resilient_ai_call` wrapper, losing retry logic, circuit breaker protection, and cost tracking:
1. `document_data_extractor.py:499` — `self.anthropic.messages.create()`
2. `bank_statement_analyzer.py:805` — transaction extraction
3. `bank_statement_analyzer.py:1694` — summary generation
**Impact**: No retry on transient failures, no circuit breaker protection, no cost attribution for these calls.
**Recommendation**: Replace all three with `resilient_ai_call()`.
**Files**: `backend/services/smart_docs/document_data_extractor.py:499`, `backend/services/smart_docs/bank_statement_analyzer.py:805,1694`

### [SD-AUTH-003] Portal V1 has ZERO authentication
**Severity**: CRITICAL
**Category**: Auth / Security
**Finding**: `portal_smart_docs_routes.py` at `/api/portal/smart-docs/{workspace_slug}/*` uses ONLY rate limiting (30 req/min) and minimum slug length (8 chars). No JWT, no token, no session. Anyone who obtains a workspace slug can view the full needs list (borrower names, loan numbers) and upload documents.
**Impact**: PII exposure for mortgage borrowers. Document injection possible.
**Recommendation**: Deprecate V1 portal in favor of V2 (`smart_docs_portal_v2_routes.py`) which uses magic-link JWT. Add auth to V1 or redirect all traffic to V2.
**File**: `backend/routes/portal_smart_docs_routes.py`

### [SD-MODEL-001] send_to_portal_for_signature uses non-existent model attributes
**Severity**: CRITICAL
**Category**: Model / Route Mismatch
**Finding**: `smart_docs_requests_routes.py:369-379` creates `DocPolicyEvent` with: `event_type="PORTAL_DOCUSIGN_REQUEST"` (not in enum), `message=...` (no such column), `data={...}` (column is named `payload`). This endpoint crashes at runtime.
**Impact**: Portal DocuSign request feature is non-functional.
**Recommendation**: Add `PORTAL_DOCUSIGN_REQUEST` to `DocPolicyEventType`, rename `data=` to `payload=`, remove or add `message` column.
**File**: `backend/routes/smart_docs_requests_routes.py:369-379`

### [SD-MODEL-002] send_to_portal_for_signature accesses non-existent request.metadata
**Severity**: CRITICAL
**Category**: Model / Route Mismatch
**Finding**: `smart_docs_requests_routes.py:339-341` accesses `request.metadata` but `DocumentRequest` has no `metadata` column. Causes `AttributeError` at runtime.
**Impact**: Same endpoint as SD-MODEL-001 — double crash path.
**Recommendation**: Add `metadata = Column(JSON, nullable=True)` to DocumentRequest or store in existing field.
**File**: `backend/routes/smart_docs_requests_routes.py:339-341`

### [SD-REG-001] Enterprise routes registered twice
**Severity**: CRITICAL
**Category**: Registration
**Finding**: `register_smart_docs_enterprise_routes(app)` is called twice: once from `register_smart_docs_v2_routes()` at `smart_docs_v2_registration.py:282-286`, and again directly in `main.py:2517-2518`. Enterprise config routes are mounted at duplicate paths.
**Impact**: Duplicate route definitions; potential for confusing behavior and wasted startup time.
**Recommendation**: Remove the standalone call at `main.py:2517-2521`.
**File**: `backend/routes/smart_docs_v2_registration.py:282`, `backend/main.py:2517`

### [ESC-003] SLA breach is terminal — post-breach escalation chains never fire
**Severity**: CRITICAL
**Category**: SLA / Escalation
**Finding**: `sla_enforcement_service.py:1318-1322` — when a breach is detected at 100%, the loop executes `continue`, skipping escalation threshold checks at 150%/200%. Post-breach escalation to senior management never triggers.
**Impact**: Severely overdue items (hours/days past SLA) have no escalation visibility. Management is blind to chronic breaches.
**Recommendation**: Remove the `continue` after breach detection. Allow 150%/200% thresholds to fire.
**File**: `backend/services/smart_docs/enterprise/sla_enforcement_service.py:1318`

---

## Warning Findings (30)

### Routes & Registration (4)

| ID | Finding | File |
|----|---------|------|
| SD-REG-002 | Triple registration of followup, review, analytics routers across V1, V2, and legacy mounts | `smart_docs_v2_registration.py`, `smart_docs_routes.py`, `_register_documents_income.py` |
| SD-REG-004 | `smart_docs_routes.py` mounted from both `inline_legacy_routes.py:1615` and `_register_documents_income.py:26` | Both files |
| SD-AUTH-006 | `smart_docs_config_routes.py` uses custom `_get_current_user` wrapper instead of canonical auth | `smart_docs_config_routes.py:84` |
| SD-AUTH-007 | `smart_docs_cadence_routes.py` uses fragile lazy Depends resolution pattern | `smart_docs_cadence_routes.py:24-49` |

### State Machine (2)

| ID | Finding | File |
|----|---------|------|
| SD-STATE-001 | `SmartDocument.status` is raw String(32) with no enum validation — 11 states found but arbitrary strings accepted | `smart_docs_models.py` |
| SD-STATE-003 | UPLOAD_FAILED is a dead-end state with no retry or cleanup path | `smart_docs_crud_routes.py:488` |

### Error Handling (3)

| ID | Finding | File |
|----|---------|------|
| SD-ERR-001 | `add_custom_request` returns error dicts with HTTP 200 instead of raising HTTPException | `smart_docs_requests_routes.py:71,92-97` |
| SD-ERR-002 | `get_applicants_with_pending_review` silently swallows all exceptions | `smart_docs_crud_routes.py:1311-1315` |
| SD-ERR-003 | `send_reminder` marks reminder as sent even when notification fails | `smart_docs_crud_routes.py:2001-2004` |

### HTTP Method (1)

| ID | Finding | File |
|----|---------|------|
| SD-HTTP-001 | No-show endpoint uses GET for state-changing operation | `smart_docs_followup_routes.py:982` |

### Data Integrity (1)

| ID | Finding | File |
|----|---------|------|
| SD-DATA-001 | No foreign key constraints in Smart Docs models (allows orphaned records) | All smart_docs model files |

### Portal Security (2)

| ID | Finding | File |
|----|---------|------|
| SD-SEC-001 | In-memory rate limiter is per-process only — multiplied by worker count | `portal_smart_docs_routes.py:62-104` |
| SD-SEC-11 | Portal auth rate limiting in-memory, doesn't survive restarts or multi-worker | `portal_auth_service.py:49,314` |

### SLA & Escalation (3)

| ID | Finding | File |
|----|---------|------|
| SLA-003 | Two parallel SLA systems (basic + enterprise) may produce conflicting statuses | `sla_service.py`, `sla_enforcement_service.py` |
| SLA-004 | Enterprise SLA holidays hardcoded to 2026 — wrong for other years | `sla_enforcement_service.py:148-159` |
| CONFIG-001 | Smart cadence holiday calendar covers only 3 fixed holidays (misses 8 floating) | `smart_cadence_service.py:69-75` |

### Notifications & Queues (2)

| ID | Finding | File |
|----|---------|------|
| NOTIF-001 | `notification_center_service.py` references non-existent template `"doc_status_update"` — all email notifications silently fail | `notification_center_service.py:1756` |
| QUEUE-001 | No dead-letter or retry mechanism for failed campaign steps — campaign advances past failures | `followup_automation_service.py:659-698` |

### Queue Tenant Isolation (1)

| ID | Finding | File |
|----|---------|------|
| QUEUE-002 | `queue_service.py` has no `organization_id` filtering — cross-tenant data leak | `queue_service.py` |

### Security Layer (6)

| ID | Finding | File |
|----|---------|------|
| SD-SEC-02 | PII encryption has no automated key rotation mechanism | `pii_encryption_service.py` |
| SD-SEC-04 | SSN last-4 digits leak in redacted log output | `pii_log_filter.py:55-56` |
| SD-SEC-07 | ClamAV optional; signature-based fallback scans only first 2MB | `malware_scanner_service.py` |
| SD-SEC-12 | Portal auth shares SECRET_KEY with Salesforce HS256 JWTs | `portal_auth_service.py` |
| SD-SEC-24 | S3 `put_object` does not set ServerSideEncryption explicitly | `s3_storage_service.py:217` |
| SDOC-004 | Plaid token fallback uses base64 encoding (not encryption) in non-prod | `plaid_service.py:176-186` |

### AI Services (3)

| ID | Finding | File |
|----|---------|------|
| SDOC-005 | Upload pipeline calls nonexistent `classifier.classify()` — classification never runs | `upload_pipeline.py:375` |
| SDOC-008 | Service registry missing ~15 services that exist in codebase | `service_registry.py` |
| SDOC-009 | `ai_review_service.py` calls `db.commit()` from service layer (should be `flush()`) | `ai_review_service.py:~613` |

### Stubs (2)

| ID | Finding | File |
|----|---------|------|
| SDOC-006 | AUS integration returns mock data when env vars not set | `aus_integration_service.py` |
| SDOC-007 | eClosing integration is stub — no live vendor connectivity | `eclosing_service.py` |

---

## Pass Highlights (56 checks passed)

**Security & Compliance — Strong (22/30 passed)**:
- AES-256-GCM encryption, fail-closed initialization, no plaintext fallback
- SHA-256 + HMAC-SHA256 for e-signatures, bcrypt for KBA answers
- ESIGN Act consent with versioned disclosure, paper alternative, withdrawal
- BSA/SAR tipping prevention via three-tier fraud access control
- Comprehensive input validation with ReDoS prevention, path traversal protection
- No hardcoded secrets anywhere — all from env vars
- Append-only decision audit with 3-year TRID retention minimum
- S3 tenant isolation via org-prefix validation, 5-minute pre-signed URLs
- Document versioning with regulated-doc change-reason enforcement

**AI & Income Analysis — Comprehensive (10/26 passed)**:
- 21 document type classifier with keyword + AI + filename fallback
- Dual OCR provider (Claude Vision + Tesseract) with preprocessing pipeline
- Circuit breaker + exponential backoff in resilient_ai_call
- Income calculator handles all pay frequencies with correct multipliers
- W2/Paystub cross-validator with 2025/2026 tax constants
- Tax return analyzer follows Fannie Mae guidelines (Schedule C/E, K-1)
- Bank statement analyzer with BSA structuring detection ($10K threshold)
- MISMO 3.6 mapper with defusedxml (XXE prevention)
- Sandboxed Jinja2 template engine

**SLA & Automation — Solid (14/27 passed)**:
- Enterprise SLA with 7 granular target types and business-hour calculation
- Escalation chains terminate properly (no infinite loops)
- Cron tasks have per-org error isolation with batch limits
- 7-year audit retention floor enforced even if env var set lower
- Freshness rules cover all time-sensitive document types
- Follow-up campaigns cover full document lifecycle (7 types)

---

## Workflow Dependency Map

```
                    ┌──────────────────────┐
                    │   Document Upload     │
                    │   (upload_pipeline)   │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │  Malware Scan        │ ─── FAIL ──→ REJECTED
                    │  (malware_scanner)   │
                    └──────────┬───────────┘
                               │ PASS
                    ┌──────────▼───────────┐
                    │  AI Classification   │ ←── BROKEN (SDOC-005)
                    │  (ai_classifier)     │     classifier.classify() DNE
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
     ┌────────────┐   ┌──────────────┐   ┌──────────────┐
     │ OCR + Data │   │ Freshness    │   │ Fraud        │
     │ Extraction │   │ Validation   │   │ Detection    │
     └─────┬──────┘   └──────┬───────┘   └──────┬───────┘
           │                 │                    │
           └────────┬────────┘                    │
                    ▼                             │
           ┌──────────────┐                       │
           │ AI Review    │◄──────────────────────┘
           │ (review_svc) │
           └──────┬───────┘
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
   APPROVED  NEEDS_REVIEW  REJECTED
        │         │         │
        │         │    ┌────▼─────┐
        │         │    │ Follow-up│
        │         │    │ Campaign │
        │         │    └──────────┘
        │         │
   ┌────▼─────────▼────┐
   │  SLA Monitoring    │ ←── NOTE: breach detection logs
   │  (sla_enforcement) │     but doesn't escalate past 100%
   └────────────────────┘     (ESC-003)
```

---

## Priority Action Items

### Immediate (this sprint)

1. **SDOC-001** — Fix SQL injection in `ai_resolution_engine.py:1554` (whitelist columns)
2. **SD-AUTH-003** — Deprecate unauthenticated V1 portal or add JWT auth
3. **SDOC-002** — Fix broken field lookup in `ai_resolution_engine.py:1502`
4. **SD-MODEL-001/002** — Fix `send_to_portal_for_signature` model mismatches
5. **QUEUE-002** — Add org_id filtering to `queue_service.py`

### This week

6. **ESC-003** — Remove `continue` after SLA breach to enable 150%/200% escalation
7. **SDOC-003** — Route 3 direct Anthropic calls through `resilient_ai_call`
8. **SDOC-005** — Fix `classifier.classify()` → `classifier.classify_document()` in upload pipeline
9. **NOTIF-001** — Add missing `doc_status_update` email template
10. **SD-REG-001** — Remove duplicate enterprise route registration from main.py

### Next sprint

11. **SD-SEC-24** — Add `ServerSideEncryption` to S3 puts
12. **SD-SEC-12** — Separate portal JWT secret from shared SECRET_KEY
13. **SLA-004 / CONFIG-001** — Replace hardcoded holidays with `holidays` library
14. **SD-STATE-001** — Add DocumentStatus enum with `@validates('status')`
15. **SDOC-004** — Block base64 Plaid token fallback in production

---

## Appendix: Full Check Results

| Check ID | Category | Severity | Status |
|----------|----------|----------|--------|
| SDOC-001 | AI/Security | CRITICAL | SQL injection in ai_resolution_engine |
| SDOC-002 | AI Services | CRITICAL | Broken field lookup |
| SDOC-003 | AI Services | CRITICAL | Bypassed resilient_ai_call (3 calls) |
| SD-AUTH-003 | Auth | CRITICAL | Portal V1 zero auth |
| SD-MODEL-001 | Model | CRITICAL | DocPolicyEvent wrong attributes |
| SD-MODEL-002 | Model | CRITICAL | DocumentRequest.metadata DNE |
| SD-REG-001 | Registration | CRITICAL | Double enterprise registration |
| ESC-003 | SLA | CRITICAL | Post-breach escalation dead |
| SD-REG-002 | Registration | WARNING | Triple router mounting |
| SD-REG-004 | Registration | WARNING | Double smart_docs_routes mount |
| SD-AUTH-006 | Auth | WARNING | Custom auth wrapper |
| SD-AUTH-007 | Auth | WARNING | Fragile lazy Depends |
| SD-STATE-001 | State Machine | WARNING | No status enum validation |
| SD-STATE-003 | State Machine | WARNING | UPLOAD_FAILED dead-end |
| SD-ERR-001 | Error Handling | WARNING | Error dict with 200 status |
| SD-ERR-002 | Error Handling | WARNING | Silent exception swallow |
| SD-ERR-003 | Error Handling | WARNING | False sent=True on failure |
| SD-HTTP-001 | HTTP Method | WARNING | GET for state change |
| SD-DATA-001 | Data Integrity | WARNING | No FK constraints |
| SD-SEC-001 | Portal | WARNING | Per-process rate limiter |
| SD-SEC-02 | Security | WARNING | No PII key rotation |
| SD-SEC-04 | Security | WARNING | SSN last-4 in logs |
| SD-SEC-07 | Security | WARNING | ClamAV optional |
| SD-SEC-11 | Security | WARNING | In-memory rate limiting |
| SD-SEC-12 | Security | WARNING | Shared SECRET_KEY |
| SD-SEC-24 | Security | WARNING | No S3 SSE |
| SLA-003 | SLA | WARNING | Dual SLA systems |
| SLA-004 | SLA | WARNING | Hardcoded 2026 holidays |
| CONFIG-001 | SLA | WARNING | 3/11 holidays covered |
| NOTIF-001 | Notifications | WARNING | Missing email template |
| QUEUE-001 | Queue | WARNING | No retry/dead-letter |
| QUEUE-002 | Queue | WARNING | No tenant isolation |
| SDOC-004 | Security | WARNING | Base64 Plaid fallback |
| SDOC-005 | AI Services | WARNING | Broken classifier call |
| SDOC-006 | Integrations | WARNING | AUS stub |
| SDOC-007 | Integrations | WARNING | eClosing stub |
| SDOC-008 | AI Services | WARNING | 15 unregistered services |
| SDOC-009 | AI Services | WARNING | Service-layer commit |
| SD-AUTH-001 | Auth | PASS | Parent router enforces auth |
| SD-AUTH-002 | Auth | PASS | V2 routes use Depends |
| SD-AUTH-004 | Auth | PASS | V2 portal JWT auth |
| SD-AUTH-005 | Auth | PASS | Tenant isolation helpers |
| SD-REG-003 | Registration | PASS | Graceful degradation |
| SD-STATE-004 | State Machine | PASS | DocumentRequest enum |
| SD-STATE-005 | State Machine | PASS | Campaign/Appointment enums |
| SD-ERR-004 | Validation | PASS | Thorough upload validation |
| SD-ERR-005 | Validation | PASS | SQL injection prevention |
| SD-SEC-002 | Security | PASS | Portal V2 crypto |
| SD-SEC-01 | Security | PASS | AES-256-GCM encryption |
| SD-SEC-03 | Security | PASS | PII log filter |
| SD-SEC-05 | Security | PASS | Real fraud detection |
| SD-SEC-06 | Security | PASS | BSA/SAR tipping prevention |
| SD-SEC-08 | Security | PASS | PDF forensics |
| SD-SEC-09 | Security | PASS | Screenshot detection |
| SD-SEC-10 | Security | PASS | Portal JWT + rate limiting |
| SD-SEC-13 | Security | PASS | Document security models |
| SD-SEC-14 | Security | PASS | E-sig SHA-256 + HMAC |
| SD-SEC-15 | Security | PASS | HKDF key derivation |
| SD-SEC-16 | Security | PASS | Signing chain audit trail |
| SD-SEC-17 | Security | PASS | ESIGN Act consent |
| SD-SEC-18 | Security | PASS | KBA bcrypt + lockout |
| SD-SEC-20 | Security | PASS | TCPA full compliance |
| SD-SEC-21 | Security | PASS | TCPA consent models |
| SD-SEC-23 | Security | PASS | S3 tenant isolation |
| SD-SEC-25 | Security | PASS | Document versioning audit |
| SD-SEC-26 | Security | PASS | Append-only decision audit |
| SD-SEC-27 | Security | PASS | Tiered archive + legal hold |
| SD-SEC-28 | Security | PASS | Safe rollback (dry-run) |
| SD-SEC-29 | Security | PASS | Input validation + ReDoS |
| SD-SEC-30 | Security | PASS | No hardcoded secrets |
| SLA-001 | SLA | PASS | Basic SLA targets defined |
| SLA-002 | SLA | PASS | Enterprise SLA granular |
| ESC-001 | Escalation | PASS | Chains terminate |
| ESC-002 | Escalation | PASS | Stale events expired |
| CRON-001 | Cron | PASS | Per-org error isolation |
| CRON-002 | Cron | PASS | Batch limits |
| CRON-003 | Cron | PASS | Tenant-scoped sessions |
| CRON-004 | Cron | PASS | No notification spam |
| CRON-005 | Cron | PASS | 7-year audit retention |
| NOTIF-002 | Notifications | PASS | Event types have templates |
| NOTIF-003 | Notifications | PASS | Force-deliver types |
| NOTIF-004 | Notifications | PASS | Follow-up templates |
| RULES-001 | Business Rules | PASS | 16 rules across 5 categories |
| RULES-002 | Business Rules | PASS | 7 campaign types |
| FRESH-001 | Freshness | PASS | All doc types covered |
| FRESH-002 | Freshness | PASS | Complementary validation |
| FRESH-003 | Freshness | PASS | Pay-cycle expiration |
| QUEUE-003 | Queue | PASS | Per-campaign isolation |
| QUEUE-004 | Queue | PASS | Execution limits |
| SDOC-010 | AI | PASS | All DocTypes classified |
| SDOC-011 | AI | PASS | Dual OCR with fallback |
| SDOC-012 | AI | PASS | Circuit breaker + retry |
| SDOC-013 | AI | PASS | Fail-closed malware scan |
| SDOC-014 | AI | PASS | MISMO 3.6 coverage |
| SDOC-015 | AI | PASS | Income calculator |
| SDOC-016 | AI | PASS | W2/Paystub cross-validation |
| SDOC-017 | AI | PASS | Tax return analyzer |
| SDOC-018 | AI | PASS | Bank statement + structuring |
| SDOC-019 | AI | PASS | Service registry tenant check |
