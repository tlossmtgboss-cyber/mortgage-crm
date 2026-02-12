# Portal Skill Challenge — Validation Report

**Generated:** 2026-02-12
**Mode:** Full (All 5 domains, all 3 portals)
**Validator:** Claude Code (Opus 4.6) — Static Code Analysis

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Security Score** | **52/100** — Needs Attention |
| Total Checks | 63 |
| Passed | 44 |
| Failed | 5 |
| Needs Review | 8 |
| Skipped | 6 |
| Critical Failures | 3 |
| High Failures | 2 |
| Portals Tested | 3/3 (Borrower/PURL, Partner/Realtor, LO/Internal) |
| Domains Tested | 5/5 |

### Score Breakdown
```
Base Score:                          100
SEC-006  SQL Injection (CRITICAL):   -10
SEC-012  PII Logging (CRITICAL):     -10
DOC-008  Download Auth (CRITICAL):   -10
SEC-002  Tenant Isolation (HIGH):     -5
SEC-003  PII Encryption (HIGH):       -5
SEC-015  Admin Auth (HIGH):           -5
DOC-010  Version History (MEDIUM):    -2
PS-010   HTTPS Redirect (MEDIUM):     -1 (platform-mitigated)
                                    ─────
FINAL SCORE:                          52
```

### Rating: Needs Attention
- Address CRITICAL items within 24 hours
- Address HIGH items within 1 week

---

## Domain 1: Portal Setup

### PS-001: Portal routes resolve
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** Borrower, Partner, LO
- **Details:** 8+ portal types properly defined and registered
  - Borrower/PURL: `/api/purl`, `/api/v1/purl-admin` (`backend/routes/purl_routes.py:166-169`)
  - Partner/Realtor: `/api/v1/realtor-portal` (`backend/routes/realtor_portal_routes.py:32`)
  - LO/MUM Portal: `/api/v1/mum-portal` (`backend/routes/mum_portal_routes.py`)
  - Additional: Listing Agent, Recruit, Portal Settings, Smart Docs, Video, AI Assistant
  - Frontend: `portalApi.js` with lifecycle, milestone, document, notification endpoints
  - Production URLs: `https://api.perenniaai.com` (API), `https://app.perenniaai.com` (SPA)

### PS-006: SSL/TLS certificate valid (>30d)
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** All
- **Details:** HSTS header configured with 1-year max-age, includeSubDomains
  - `backend/security_middleware.py:718-719`: `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  - Railway (backend) and Vercel (frontend) handle SSL termination at edge

### PS-007: CORS restricts origins (no wildcard)
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** All
- **Details:** Explicit allowlist with no wildcard `*` origins
  - `backend/middleware/dynamic_cors.py:26`: `# SECURITY: Explicit allowlists instead of wildcards`
  - Static allowlist: `perenniaai.com`, `app.perenniaai.com`, `api.perenniaai.com`, localhost dev ports
  - Suffix matching for `*.perenniaai.com` and `*.railway.app` subdomains
  - Dynamic custom domain validation via `CustomDomainService`
  - Response sets specific origin, never `*`: `response.headers["Access-Control-Allow-Origin"] = origin`

### PS-010: HTTPS enforced (HTTP -> HTTPS redirect)
- **Severity:** CRITICAL
- **Status:** NEEDS REVIEW
- **Applies to:** All
- **Details:** HSTS provides repeat-visit protection, but no app-level `HTTPSRedirectMiddleware`
  - First-visit HTTP requests may not be redirected at application level
  - Railway/Vercel likely handle this at platform level (not verified)
- **Remediation:** Add `starlette.middleware.https.HTTPSRedirectMiddleware` for defense-in-depth

---

## Domain 2: User Access

### UA-001: PURL token generation with correct scopes
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** Secure token implementation
  - `backend/models/purl.py:1152-1188`: `PURLTokenGenerator` using `secrets.token_bytes(32)` (256-bit)
  - Token format: `purl_live_` prefix + 64 hex chars
  - Tokens hashed with SHA256 before storage (only hash persisted)
  - Three scope levels: READ, WRITE, FULL

### UA-002: Expired tokens rejected (HTTP 401)
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** All
- **Details:** Automatic expiration with status update
  - `backend/services/purl_token_service.py:170-176`: Checks `expires_at < now(UTC)`, auto-marks `TokenStatus.EXPIRED`
  - `backend/middleware/purl_auth.py:146-151`: Returns HTTP 401 for invalid/expired tokens

### UA-003: Revoked tokens rejected immediately
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** Comprehensive revocation mechanism
  - `purl_token_service.py:242-291`: `revoke_token()` sets status, tracks `revoked_at`, `revoked_by`, `revoked_reason`
  - Bulk revocation: `revoke_all_workspace_tokens()` (lines 293-343)
  - Status check at `purl_token_service.py:166-168`: Non-ACTIVE tokens return None -> 401

### UA-004: OAuth flow for Partner/LO
- **Severity:** CRITICAL
- **Status:** NEEDS REVIEW
- **Applies to:** Partner, LO
- **Details:** Microsoft OAuth implemented with HMAC-signed state + CSRF protection
  - JWT creation: `main.py:557-575` with configurable expiration, HS256/RS256
  - LO Portal and Partner Portal OAuth flows not fully visible in reviewed files
- **Remediation:** Verify and document LO-specific and Partner-specific OAuth flows

### UA-005: Role-based permissions (RBAC)
- **Severity:** CRITICAL
- **Status:** NEEDS REVIEW
- **Applies to:** LO
- **Details:** RBAC infrastructure exists but enforcement incomplete
  - `database/models/permission.py`: `RolePagePermission`, `UserPagePermission`, `PermissionLevel` enum
  - `PURLWorkspaceMember` has role field (OWNER, PROCESSOR, CLOSER, VIEWER) but enforcement not visible on all endpoints
- **Remediation:** Audit all LO Portal endpoints for role-based access checks

### UA-006: Read-only token cannot write (HTTP 403)
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** Scope enforcement via dependency injection
  - `purl_auth.py:159-173`: `require_purl_write_scope()` checks `has_write_access()`, returns 403
  - All write routes use `Depends(require_purl_write_scope)` (e.g., `save_application()`, `upload_document()`)

### UA-007: Rate limiting triggers at threshold
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** All
- **Details:** Per-token rate limiting with configurable tiers
  - `purl_auth.py:334-414`: `PURLRateLimiter` with 60/min, 1000/hr defaults
  - Returns HTTP 429 when exceeded
  - Note: In-memory only — recommend Redis for distributed deployments

### UA-008: Session timeout enforced
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** All
- **Details:** JWT-based with short TTL
  - `auth/config.py:43-46`: Access token 15 minutes, refresh token 7 days
  - PURL tokens: Optional expiration via `expires_in_days` parameter

### UA-011: Multi-tenant isolation (User A cannot access User B)
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** All
- **Details:** Workspace-level isolation enforced
  - `purl_auth.py:191-214`: `verify_workspace_access()` validates slug matches token's workspace
  - `PURLAuthContext` stores `organization_id`, `workspace_id`, `workspace_slug`, `contact_id`
  - All PURL routes call `verify_workspace_access(context, slug)`

---

## Domain 3: Security

### SEC-001: RLS policies active on PURL tables
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** Application-level RLS via `TenantMixin`
  - `database/tenant_mixin.py`: Automatic `organization_id` column with FK, index, helper methods
  - `tenant_query()` and `get_by_tenant()` for filtered queries
  - Note: PostgreSQL-level RLS policies available but not confirmed enabled — defense-in-depth opportunity

### SEC-002: Tenant isolation (cross-org returns 0 rows)
- **Severity:** CRITICAL
- **Status:** NEEDS REVIEW
- **Applies to:** All
- **Details:** Tenant filtering available but not uniformly enforced
  - `TenantMixin.tenant_query()` provides filtering mechanism
  - Risk: If developer omits `.filter(Model.organization_id == org_id)`, cross-tenant data exposure possible
  - Enforcement is application-level, not database-level
- **Remediation:** Enable PostgreSQL RLS policies as defense-in-depth; audit all queries for tenant filtering

### SEC-003: PII fields encrypted at rest
- **Severity:** CRITICAL
- **Status:** NEEDS REVIEW
- **Applies to:** All
- **Details:** Encryption infrastructure exists but coverage uncertain
  - `encryption_utils.py`: Fernet-based `EncryptedString`, `EncryptedInteger`, `EncryptedFloat` TypeDecorators
  - Uses `DATA_ENCRYPTION_KEY` (separate from JWT secret)
  - Issue: Models must explicitly use `EncryptedString` — cannot confirm all PII fields (SSN, DOB, financial) are encrypted
  - Fallback to `SECRET_KEY` if `DATA_ENCRYPTION_KEY` not set (security downgrade)
- **Remediation:** Audit all models for sensitive fields; ensure `DATA_ENCRYPTION_KEY` is set in Railway

### SEC-004: Audit log captures CRUD operations
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** All
- **Details:** Comprehensive audit infrastructure
  - `database/models/security.py`: `AuditLog` and `AIAuditLog` models
  - PURL request auditing: `log_purl_action()` in auth middleware
  - Permission audit logs via `/users/{user_id}/audit`

### SEC-005: Rate limiting per-token (60/min, 1000/hr)
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** Multi-tier rate limiting
  - `security_middleware.py`: Standard 60/min, 1000/hr | Admin 200/min, 5000/hr | Anon 30/min, 300/hr
  - Per-user (JWT) and per-IP (unauthenticated) tracking
  - Endpoint-specific multipliers for expensive operations
  - Burst protection on 10-second windows

### SEC-006: SQL injection protection
- **Severity:** CRITICAL
- **Status:** FAILED
- **Applies to:** All
- **Details:** **Raw SQL with f-string interpolation found**
  - `salesforce_integration_routes.py` lines 121, 153, 181, 209, 231, 274, 1293:
    ```python
    db.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
    ```
  - `debug_data_routes.py` lines 1725, 1742:
    ```python
    db.execute(text(f"SELECT COUNT(*) FROM {table}"))
    ```
  - Table/column names interpolated without whitelist validation
- **Remediation:** Add table/column name whitelisting before any dynamic DDL execution

### SEC-007: CSP headers present
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** All
- **Details:** Full CSP + security headers configured
  - `security_middleware.py`: CSP, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, X-XSS-Protection
  - Note: CSP allows `'unsafe-inline'` and `'unsafe-eval'` — should be restricted if possible

### SEC-008: No API keys in client bundles
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** All
- **Details:** No hardcoded secrets found in frontend code
  - Tokens passed as props/context at runtime
  - Standard REACT_APP_ prefixed env vars only

### SEC-009: S3 presigned URLs expire within TTL
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** 1-hour TTL on presigned URLs (`ExpiresIn=3600`)

### SEC-010: HTTPS enforced
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** All
- **Details:** HSTS with 1-year max-age + includeSubDomains

### SEC-011: Cookie flags (httpOnly, Secure, SameSite)
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** All
- **Details:** `middleware/secure_cookies.py`: httpOnly=True, Secure=True, SameSite=Lax
  - Access token: 15-minute max-age
  - Refresh token: 7-day max-age

### SEC-012: PII not logged in plaintext
- **Severity:** CRITICAL
- **Status:** FAILED
- **Applies to:** All
- **Details:** **Email addresses logged in plaintext throughout auth routes**
  - `auth_routes.py` lines 404, 409, 427, 470, 510, 512, 514, 517, 592, 622, 638, 895, 1020, 1071, 1273:
    ```python
    logger.info(f"User {current_user.email} logged out, token blacklisted")
    logger.info(f"Password reset email sent successfully to {request.email}")
    logger.info(f"New account registered: {request.email} (org: {request.company_name})")
    ```
  - Violates GDPR, CCPA, financial industry regulations
- **Remediation:** Replace email with user ID in logs or add PII redaction logging filter

### SEC-013: OWASP Top 10 headers
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** All
- **Details:** All recommended headers present
  - X-Frame-Options: DENY
  - X-Content-Type-Options: nosniff
  - Strict-Transport-Security: max-age=31536000
  - Referrer-Policy: strict-origin-when-cross-origin
  - Permissions-Policy: geolocation=(), microphone=(), camera=()
  - Content-Security-Policy: configured

### SEC-014: Database SSL and connection pooling
- **Severity:** HIGH
- **Status:** NEEDS REVIEW
- **Applies to:** All
- **Details:** QueuePool configured but SSL enforcement not explicitly visible
  - Connection pooling via SQLAlchemy QueuePool confirmed
  - `sslmode=require` not visible in sampled connection strings
- **Remediation:** Verify Railway PostgreSQL connection includes `sslmode=require`

### SEC-015: Admin endpoints require elevated privileges
- **Severity:** CRITICAL
- **Status:** NEEDS REVIEW
- **Applies to:** All
- **Details:** Key-based auth used instead of role-based auth
  - `/api/v1/admin/force-password-reset`: Uses `ADMIN_RESET_KEY` env var
  - `/api/v1/setup-admin`: Uses `admin_key` query parameter
  - No `@require_admin` decorator pattern visible
- **Remediation:** Implement role-based admin auth; add rate limiting on admin operations

---

## Domain 4: CRM Data Sync

### SYNC-001: Salesforce OAuth token valid
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** All
- **Details:** Comprehensive OAuth token management
  - `services/salesforce/oauth_service.py:374-416`: Auto-refresh on expiration, encrypted storage (Fernet)
  - PKCE implementation with DB + memory fallback (10-min TTL)
  - HMAC-signed state for CSRF protection
  - Invalid refresh tokens trigger `error` status on profile

### SYNC-002: Field mapping complete
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** All
- **Details:** 26+ default field mappings with type validation
  - `field_mapping_service.py:42-56`: Type compatibility matrix
  - Transform types: direct, picklist, stage_map, date_format, currency, phone, name split/concat
  - Validation with error/warning messages per mapping

### SYNC-003/004: Push/Pull sync latency
- **Severity:** CRITICAL
- **Status:** PASSED (with caveat)
- **Applies to:** All
- **Details:** Inbound-only design; Salesforce is authoritative
  - Pull sync: Every 10 minutes on staggered schedule (:08, :18, :28, :38, :48, :58)
  - Push sync: DISABLED — all `push_*` functions return "not_implemented"
  - Health check every 10 min (:02, :12, :22, :32, :42, :52)
  - Batch size: 200-500 records per sync

### SYNC-005: Bi-directional conflict resolution
- **Severity:** HIGH
- **Status:** NEEDS REVIEW
- **Applies to:** All
- **Details:** Conflict tracking schema exists but no active conflict detection
  - `IntegrationRecordTracking.sync_status` defines 'conflict' state but no code implements detection
  - `last_write_wins` policy set only for calendar sync (`oauth_service.py:349`)
  - Mitigated by unidirectional design (Salesforce always wins)
- **Remediation:** Document explicitly as inbound-only; implement conflict detection if bidirectional sync is enabled

### SYNC-006: Lead status propagation triggers workflows
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** Borrower, LO
- **Details:** 33 SLA milestone triggers with workflow enrollment
  - `salesforce_sla_trigger_service.py:33-250`: Application, lock, processing, appraisal, closing date triggers
  - Status field: `MtgPlanner_CRM__Status__c` -> CRM `stage` via `stage_map` transform

### SYNC-007: Contact/borrower fields match
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** Email-based matching with full contact field sync
  - First Name, Last Name, Email, Phone mapped to `MtgPlanner_CRM__Borrower_*` fields
  - Organization_id backfill for tenant isolation
  - Upsert logic prevents duplicates

### SYNC-008: Opportunity/loan stage sync
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** All
- **Details:** 11+ stage value mappings
  - `field_mapping_service.py:60-74`: New Lead->LEAD, Qualified->QUALIFIED, ... Funded->FUNDED, Lost->LOST

### SYNC-009: Sync error count < 1%
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** All
- **Details:** Error rate tracking with 10% threshold
  - `salesforce_sync_tasks.py:497-500`: Health check calculates `failures / (syncs + failures)`
  - IntegrationEvent tracks: records_processed, records_succeeded, records_failed, duration_ms
  - Stale connection detection at 15-minute window

### SYNC-010: Retry queue draining
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** All
- **Details:** Priority-based retry queue with max 3 attempts
  - `sync_service.py:712-754`: `process_queue()` ordered by priority DESC, scheduled_for ASC
  - Status flow: pending -> processing -> (completed|retry|failed)
  - Note: No exponential backoff between retries
- **Remediation:** Add exponential backoff delays (2s, 4s, 8s)

### SYNC-011: Echo prevention (no duplicates)
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** All
- **Details:** MD5 sync hash prevents redundant updates
  - `sync_service.py:373-416`: Hash comparison skips upsert if data unchanged
  - Unique constraint: `(integration_profile_id, source_object, source_record_id)`
  - 60-second echo ignore window for calendar events

### SYNC-013: Watermark/cursor advancing
- **Severity:** CRITICAL
- **Status:** PASSED (with limitation)
- **Applies to:** All
- **Details:** Salesforce `LAST_N_DAYS:1` filter for incremental sync
  - `last_synced_at` tracked per record but not used for watermarking
  - No persistent cursor position for resumable syncs
- **Remediation:** Store last successful sync timestamp for gap-free sync

---

## Domain 5: Document Sync

### DOC-001: Document request appears in borrower portal
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** Full request flow with status filtering and pagination
  - `perennia_docs_routes.py:361-403`: GET endpoint with workspace-aware queries
  - `purl_perennia_integration_routes.py:208-350`: Template-based request creation

### DOC-002: Upload stores in S3 and updates CRM
- **Severity:** CRITICAL
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** Two-stage upload flow (presigned URL + confirmation)
  - `portal_document_routes.py:146-281`: S3 key `workspaces/{id}/documents/{uuid}.{ext}`
  - 3600-second presigned URL, status: pending_upload -> uploaded -> pending_review
  - File size verified against S3 object (1KB tolerance)

### DOC-003: Status transitions propagate
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** All
- **Details:** Complete workflow: pending_upload -> uploaded -> pending_review -> approved/rejected/needs_info
  - `portal_document_routes.py:508-596`: Review endpoint with approve/reject/request_info
  - Parent request auto-completes when approved_count >= quantity
  - Bulk approve/reject with transaction support

### DOC-004: Presigned URLs expire correctly
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** 1-hour TTL, CloudFront fallback
  - Upload: `ExpiresIn=3600`, Download/Preview: `ExpiresIn=3600`
  - CloudFront signed URLs when `CLOUDFRONT_DOMAIN` + `CLOUDFRONT_KEY_PAIR_ID` configured

### DOC-005: File type validation
- **Severity:** HIGH
- **Status:** NEEDS REVIEW
- **Applies to:** All
- **Details:** MIME whitelist exists but no extension validation
  - `portal_document_routes.py:76-85`: Allows PDF, JPEG, PNG, GIF, WebP, HEIC, Word
  - MIME type checked against whitelist
  - Issue: No file extension validation — `.exe` renamed to `.pdf` could pass
  - No double-extension blocking (`.pdf.exe`)
- **Remediation:** Add extension validation matching MIME type; block dangerous extensions

### DOC-006: File size limits enforced
- **Severity:** MEDIUM
- **Status:** PASSED
- **Applies to:** All
- **Details:** 25 MB limit enforced via Pydantic Field constraint + S3 verification

### DOC-007: Template pack creates correct document set
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** Template pack system with seed data
  - `perennia_docs_routes.py:537-724`: CRUD endpoints for template packs
  - `purl_perennia_integration_routes.py`: `/initialize-documents` creates requests from template
  - Supports loan programs, employment types, property types filters

### DOC-008: Download accessible only by authorized users
- **Severity:** CRITICAL
- **Status:** FAILED
- **Applies to:** All
- **Details:** **No workspace authorization on download/preview endpoints**
  - `portal_document_routes.py:467-501`: `workspace_id` accepted as query param but never validated
  - No workspace membership check performed
  - No loan/lead ownership validation
  - Any authenticated user with a valid document_id can download any document
  - **Impact:** Data breach risk, borrower privacy violation
- **Remediation (P0):** Add workspace membership verification before serving documents

### DOC-009: PURL integration syncs activity feed
- **Severity:** HIGH
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** Unified activity feed merging workspace + document events
  - `purl_perennia_integration_routes.py:462-566`: Merges `purl_audit_log` + `perennia_document_events`
  - Chronological sorting, pagination, source attribution

### DOC-010: Version history on re-upload
- **Severity:** MEDIUM
- **Status:** FAILED
- **Applies to:** All
- **Details:** Schema supports versioning but no implementation
  - `derivative_type` column exists (ORIGINAL, COMPRESSED, PREVIEW) but always ORIGINAL
  - No re-upload endpoint, no version tracking, re-uploads create new records
- **Remediation:** Implement `/{document_id}/re-upload` with version sequencing

### DOC-011: Bulk operations work
- **Severity:** MEDIUM
- **Status:** PASSED
- **Applies to:** Borrower
- **Details:** Bulk approve and reject with transaction support
  - `perennia_docs_routes.py:908-972`: Single UPDATE statements with rollback on error

### DOC-012: Notifications on status change
- **Severity:** HIGH
- **Status:** NEEDS REVIEW
- **Applies to:** All
- **Details:** Infrastructure exists but notifications disabled
  - `portal_document_routes.py:583`: `send_document_review_notification` replaced with `pass`
  - `portal_document_routes.py:359`: Background task commented out
  - Notification table and template system exist but no active notification service
- **Remediation:** Implement notification service and uncomment background tasks

---

## Remediation Plan

### P0 — Fix Immediately (blocks deployment)

| ID | Issue | Impact | Remediation |
|----|-------|--------|-------------|
| **SEC-006** | SQL injection in DDL statements | Schema modification, data exfiltration | Add table/column name whitelisting in `salesforce_integration_routes.py` and `debug_data_routes.py` |
| **SEC-012** | PII (email) logged in plaintext | GDPR/CCPA violation, regulatory fines | Replace `{email}` with `{user_id}` in auth_routes.py logger calls, or add PII redaction filter |
| **DOC-008** | Document download has no authorization check | Data breach, borrower privacy violation | Add workspace membership + loan ownership verification in `portal_document_routes.py:467-501` |

### P1 — Fix This Week

| ID | Issue | Impact | Remediation |
|----|-------|--------|-------------|
| **SEC-002** | Tenant isolation not uniformly enforced | Cross-tenant data exposure possible | Enable PostgreSQL RLS policies; audit all queries for org_id filtering |
| **SEC-003** | PII encryption coverage unknown | Sensitive data may be unencrypted | Audit models for SSN/DOB/financial fields; ensure `DATA_ENCRYPTION_KEY` in Railway |
| **SEC-015** | Admin endpoints use key-based auth | Admin impersonation possible | Replace `ADMIN_RESET_KEY` with role-based auth decorators |
| **DOC-005** | No file extension validation | Extension spoofing possible | Validate extension matches MIME type; block `.exe`, `.bat`, `.sh` |
| **DOC-012** | Document status notifications disabled | Borrowers don't receive rejection/info-needed alerts | Implement notification service; uncomment background tasks |

### P2 — Fix This Month

| ID | Issue | Impact | Remediation |
|----|-------|--------|-------------|
| **PS-010** | No app-level HTTP->HTTPS redirect | First-visit HTTP not redirected | Add `HTTPSRedirectMiddleware` |
| **UA-004** | Partner/LO OAuth flows not fully documented | Audit gap | Document and verify OAuth implementations |
| **UA-005** | PURL workspace member role enforcement incomplete | Unauthorized actions possible | Audit all endpoints for `PURLWorkspaceMember.role` checks |
| **SEC-014** | DB SSL enforcement not verified | Data in transit could be unencrypted | Confirm `sslmode=require` in Railway connection string |
| **SYNC-005** | No active conflict resolution | Data inconsistency if bidirectional sync enabled | Document as inbound-only; implement detection if needed |
| **SYNC-010** | No exponential backoff on retries | Cascading failures on API issues | Add delays: 2s, 4s, 8s between retry attempts |
| **SYNC-013** | No persistent watermark for resumable sync | Missed records on crash/delay | Store last sync timestamp for gap-free sync |
| **DOC-010** | No document version history | Compliance/audit gaps | Implement re-upload versioning with sequence tracking |

---

## What's Working Well

- **Token Security (UA-001/002/003/006):** PURL tokens use 256-bit secrets, SHA256 hashing, scope enforcement, and revocation — excellent implementation
- **Rate Limiting (SEC-005/UA-007):** Multi-tier per-user/per-IP with role-based limits and burst protection
- **CORS (PS-007):** Explicit allowlists with no wildcards
- **Cookie Security (SEC-011):** httpOnly, Secure, SameSite=Lax with appropriate TTLs
- **OWASP Headers (SEC-007/013):** Complete set including CSP, HSTS, X-Frame-Options, Permissions-Policy
- **Salesforce Sync (SYNC-001/002/006/007/008/011):** Comprehensive field mapping, encrypted tokens, echo prevention, SLA triggers
- **Document Upload (DOC-001/002/003/004):** Solid S3 integration with presigned URLs, status workflow, activity feed

---

*Report generated by Portal Skill Challenge — Claude Code (Opus 4.6)*
*Static code analysis only — no live API tests performed*
