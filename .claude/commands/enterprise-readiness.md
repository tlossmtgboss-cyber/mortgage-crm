---
name: enterprise-readiness
description: >
  Comprehensive enterprise readiness skill for Perennia AI CRM. Covers all 12
  domains required to certify the platform for enterprise mortgage lender deployment:
  multi-tenant isolation, compliance & regulatory, data quality, security audit,
  onboarding & provisioning, migration & import, integration health, analytics &
  reporting, performance & load testing, API gateway, disaster recovery, and
  white-label theming. Use this skill for enterprise certification audits, pre-sale
  readiness checks, SOC 2 preparation, client onboarding validation, and ongoing
  production health monitoring. Each domain produces both a Markdown report and
  structured JSON for dashboard integration.
---

# Perennia AI — Enterprise Readiness Skill

> The difference between a product and a platform is whether an enterprise
> InfoSec team, compliance officer, and CTO can all say yes on the same day.

---

## Overview

This skill validates that Perennia AI is ready for enterprise deployment across
**12 critical domains**. Each domain contains specific checks, pass/fail criteria,
and remediation guidance. The skill can be run as a full audit (all 12 domains)
or targeted to specific domains.

**Reference files** in `reference/` contain detailed check specifications,
SQL queries, API test patterns, and scoring rubrics for each domain.

---

## Execution Modes

| Mode | Domains | Use Case |
|------|---------|----------|
| `full` | All 12 | Pre-sale enterprise certification |
| `security` | 1, 4, 8 | InfoSec review preparation |
| `compliance` | 2, 3 | Regulatory readiness check |
| `onboarding` | 5, 6, 10, 12 | New client deployment readiness |
| `integration` | 7, 11 | Integration health monitoring |
| `performance` | 9 | Load testing and capacity planning |
| `targeted` | Any combination | Ad-hoc validation |

---

## Scoring System

Each domain scores 0–100 using weighted checks:

| Check Severity | Weight | Failure Impact |
|---|---|---|
| **CRITICAL** | 20 points | Auto-fail entire domain (score capped at 49) |
| **HIGH** | 10 points | Major deduction |
| **MEDIUM** | 5 points | Moderate deduction |
| **LOW** | 2 points | Minor deduction |

**Domain Grades:**
- **A (90-100):** Enterprise ready
- **B (80-89):** Ready with minor items
- **C (70-79):** Conditional — requires remediation plan
- **D (60-69):** Not ready — significant gaps
- **F (0-59):** Blocked — critical failures

**Overall Platform Grade:** Weighted average of all 12 domains. Any domain
scoring F blocks overall certification regardless of average.

---

## The 12 Domains

### Domain Map

```
ENTERPRISE READINESS
├── SECURITY & ISOLATION
│   ├── Domain 1:  Multi-Tenant Isolation
│   ├── Domain 4:  Security Audit
│   └── Domain 8:  Disaster Recovery
├── COMPLIANCE & DATA
│   ├── Domain 2:  Compliance & Regulatory
│   ├── Domain 3:  Data Quality & Integrity
│   └── Domain 9:  Analytics & Reporting
├── INTEGRATION & PERFORMANCE
│   ├── Domain 7:  Integration Health
│   ├── Domain 6:  Performance & Load Testing
│   └── Domain 11: API Gateway & Developer Experience
└── CLIENT OPERATIONS
    ├── Domain 5:  Onboarding & Provisioning
    ├── Domain 10: Migration & Data Import
    └── Domain 12: White-Label & Theming
```

---

## DOMAIN 1: MULTI-TENANT ISOLATION

**Priority:** BLOCKER — No enterprise deal closes without this.
**Reference:** `reference/multi-tenant.md`

### Purpose

Verify that tenant data is completely isolated at every layer — database, API,
file storage, AI context, background workers, and caching. A single cross-tenant
data leak is a company-ending event for an enterprise mortgage platform.

### Checks (18 total)

#### Database Isolation (6 checks, all CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 1.1 | RLS policies exist on ALL tenant-scoped tables | Static: query pg_policies | Every table with org_id/tenant_id has active RLS policy |
| 1.2 | RLS policies are ENABLED (not just created) | Static: `SELECT relrowsecurity FROM pg_class` | `relrowsecurity = true` for all tenant tables |
| 1.3 | Cross-tenant SELECT returns zero rows | Live: Set role to tenant_A, SELECT from tenant_B | Zero rows returned across all tables |
| 1.4 | Cross-tenant INSERT is blocked | Live: Set role to tenant_A, INSERT with tenant_B org_id | INSERT rejected or org_id overridden |
| 1.5 | Cross-tenant UPDATE is blocked | Live: Attempt UPDATE on tenant_B record as tenant_A | Zero rows affected |
| 1.6 | Cross-tenant DELETE is blocked | Live: Attempt DELETE on tenant_B record as tenant_A | Zero rows affected |

#### API Isolation (4 checks, all CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 1.7 | API endpoints enforce tenant scope | Live: Auth as tenant_A, request tenant_B resources | 403 or empty result on every endpoint |
| 1.8 | IDOR protection on all resource endpoints | Live: Enumerate IDs across tenant boundary | No resource leakage |
| 1.9 | Bulk endpoints respect tenant filter | Live: Bulk export as tenant_A | Only tenant_A data in export |
| 1.10 | Search/filter cannot cross tenant boundary | Live: Search with no tenant filter | Results scoped to authenticated tenant |

#### File Storage Isolation (3 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 1.11 | S3/storage paths include tenant prefix | Static: Review upload/download code | All paths include `/{tenant_id}/` |
| 1.12 | Presigned URLs scoped to tenant | Live: Generate URL as tenant_A, access as tenant_B | Access denied |
| 1.13 | Document downloads verify tenant ownership | Live: Request tenant_B document as tenant_A | 403 Forbidden |

#### AI Context Isolation (3 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 1.14 | Agent system prompts don't contain cross-tenant data | Static: Review prompt construction | Prompts only inject current tenant context |
| 1.15 | RAG/retrieval scoped to tenant | Live: Query knowledge base as tenant_A | Only tenant_A documents returned |
| 1.16 | Conversation history isolated | Live: Request chat history as tenant_A | Only tenant_A conversations returned |

#### Background Worker Isolation (2 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 1.17 | Sync workers process within tenant scope | Static: Review worker code | All queries include tenant filter |
| 1.18 | Scheduled jobs don't leak tenant context | Static: Review cron/scheduler | Each job execution scoped to single tenant |

---

## DOMAIN 2: COMPLIANCE & REGULATORY

**Priority:** BLOCKER — Mortgage-specific regulatory requirements.
**Reference:** `reference/compliance.md`

### Purpose

Verify the platform enforces mortgage regulatory requirements automatically,
not through human checklists. Enterprise lenders need the system to PREVENT
compliance violations, not just report them.

### Checks (22 total)

#### TRID Compliance (6 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 2.1 | LE delivery deadline tracked (3 business days from app) | Static + Live: Review SLA engine | Auto-calculated from application_date, business day calendar applied |
| 2.2 | CD delivery deadline tracked (3 business days before closing) | Static + Live: Review SLA engine | Auto-calculated from closing_date, countdown with alerts |
| 2.3 | Changed circumstance triggers re-disclosure | Static: Review event handlers | Rate change, loan amount change, program change trigger CD regeneration |
| 2.4 | Tolerance cure tracking | Static: Review fee comparison logic | Zero-tolerance, 10% bucket, and unlimited categories properly classified |
| 2.5 | Waiting period enforcement | Live: Attempt to schedule closing < 3 business days from CD | System prevents or warns |
| 2.6 | TRID audit trail complete | Live: Pull audit log for sample loan | Every disclosure event timestamped with delivery method |

#### ECOA / Fair Lending (4 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 2.7 | Adverse action notice deadline (30 days) | Static: Review denial workflow | Auto-triggered within 30 days of denial decision |
| 2.8 | Adverse action reason codes | Static: Review denial templates | Specific, accurate reason codes (not generic) |
| 2.9 | Fair lending data collection (demographics) | Static: Review application form | GMI data collected per regulation, stored separately from decisioning |
| 2.10 | AI decisioning bias monitoring | Static: Review agent decision logs | No protected-class correlation in AI recommendations |

#### TCPA Compliance (4 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 2.11 | Consent captured before outbound calls/texts | Static + Live: Review telephony workflow | Consent record exists with timestamp, method, and scope |
| 2.12 | DNC list checking | Live: Submit known DNC number | System blocks outbound contact |
| 2.13 | Time-of-day calling restrictions | Live: Attempt call outside 8am-9pm local | System blocks or queues for appropriate time |
| 2.14 | Opt-out processing (immediate) | Live: Submit opt-out | All outbound communication stops within 10 minutes |

#### HMDA Data (3 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 2.15 | HMDA-reportable fields captured | Static: Review loan schema | All LAR fields present and populated |
| 2.16 | HMDA data validation | Live: Submit incomplete HMDA record | Validation errors returned for missing required fields |
| 2.17 | HMDA export capability | Live: Generate HMDA LAR file | Valid pipe-delimited file matching CFPB spec |

#### State Licensing (3 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 2.18 | LO NMLS verification | Static + Live: Review LO profile | NMLS # stored, active license verified |
| 2.19 | State-specific disclosure requirements | Static: Review disclosure engine | State-specific disclosures triggered by property state |
| 2.20 | Multi-state licensing enforcement | Live: Assign loan in unlicensed state | System warns or blocks |

#### Audit Trail (2 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 2.21 | All compliance events immutably logged | Static: Review audit logging | Append-only audit table, no UPDATE/DELETE allowed |
| 2.22 | Audit log tamper detection | Static: Review log integrity | Hash chain or equivalent tamper-evident mechanism |

---

## DOMAIN 3: DATA QUALITY & INTEGRITY

**Priority:** HIGH — Prevents "your CRM data is unreliable" churn.
**Reference:** `reference/data-quality.md`

### Purpose

Continuously validate that data across the platform is complete, consistent,
properly formatted, and referentially sound. Bad data kills CRM trust faster
than any other failure mode.

### Checks (20 total)

#### Record Completeness (5 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 3.1 | Required fields populated on contacts | Live: Query contacts with NULL required fields | < 2% null rate on required fields |
| 3.2 | Required fields populated on loans | Live: Query loans with NULL required fields | < 1% null rate on required fields |
| 3.3 | Required fields populated on tasks | Live: Query tasks missing assignee/due_date | < 1% orphaned tasks |
| 3.4 | SLA milestone dates populated on active loans | Live: Query active loans with missing milestone dates | < 5% missing expected milestones |
| 3.5 | Contact method validity (email/phone) | Live: Regex validation on all contacts | > 95% valid format |

#### Referential Integrity (5 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 3.6 | All loans have valid contact reference | Live: LEFT JOIN loans to contacts | Zero orphaned loans |
| 3.7 | All tasks have valid assignee reference | Live: LEFT JOIN tasks to users | Zero tasks with invalid assignee |
| 3.8 | All documents have valid loan reference | Live: LEFT JOIN documents to loans | Zero orphaned documents |
| 3.9 | All activities have valid entity reference | Live: Validate polymorphic references | Zero dangling activity references |
| 3.10 | FK constraints enforced at DB level | Static: Query pg_constraint | All relationships have FK constraints, not just app-level |

#### Duplicate Detection (3 checks, MEDIUM)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 3.11 | Duplicate contacts (same email) | Live: GROUP BY email HAVING COUNT > 1 | < 1% duplicate rate |
| 3.12 | Duplicate contacts (same phone) | Live: GROUP BY normalized_phone HAVING COUNT > 1 | < 2% duplicate rate |
| 3.13 | Duplicate loans (same borrower + property) | Live: Match on SSN + property address | Zero unresolved duplicates |

#### Data Freshness (4 checks, MEDIUM)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 3.14 | Stale leads (no activity in 30+ days) | Live: Query leads with last_activity > 30 days | Flagged, not blocking |
| 3.15 | Active loans with stale status | Live: Loans in "processing" for 60+ days | < 5% of active pipeline |
| 3.16 | Sync timestamps current | Live: Check last_sync on all integrations | All synced within configured interval |
| 3.17 | Rate data freshness | Live: Check rate cache timestamp | Updated within 15 minutes |

#### PII Protection (3 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 3.18 | SSN encrypted at rest | Static + Live: Check column encryption | SSN never stored in plaintext |
| 3.19 | SSN masked in API responses | Live: GET contact with SSN | Returns `***-**-1234` format |
| 3.20 | PII not present in logs | Static: Grep application logs | Zero SSN/DOB/full-account in log output |

---

## DOMAIN 4: SECURITY AUDIT

**Priority:** BLOCKER — Required for InfoSec review.
**Reference:** `reference/security.md`

### Purpose

Validate the platform's security posture across authentication, authorization,
input handling, encryption, and operational security.

### Checks (24 total)

#### Authentication (6 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 4.1 | JWT token expiration enforced | Live: Use expired token | 401 Unauthorized |
| 4.2 | Refresh token rotation | Live: Use refresh token | Old refresh token invalidated |
| 4.3 | Password complexity requirements | Live: Create user with weak password | Rejected with specific guidance |
| 4.4 | Account lockout after failed attempts | Live: 10 failed login attempts | Account locked, notification sent |
| 4.5 | SSO/SAML integration functional | Live: SAML assertion flow | Successful auth + user provisioning |
| 4.6 | MFA enforcement (enterprise tier) | Live: Login without MFA on MFA-required org | MFA challenge presented |

#### Authorization (5 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 4.7 | RBAC enforced on all endpoints | Live: Access admin endpoint as basic user | 403 Forbidden |
| 4.8 | Role escalation prevention | Live: Attempt self-role-upgrade | Rejected |
| 4.9 | Permission template enforcement | Live: Verify all 10 roles have correct permissions | Matches permission matrix |
| 4.10 | Subscription tier feature gating | Live: Access paid feature on free tier | Feature blocked with upgrade prompt |
| 4.11 | API key scope enforcement | Live: Use read-only key for write operation | 403 Forbidden |

#### Input Security (5 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 4.12 | SQL injection prevention | Live: Submit SQL payloads on all input fields | All sanitized, no execution |
| 4.13 | XSS prevention | Live: Submit script tags in all text fields | Sanitized or escaped in output |
| 4.14 | CSRF protection | Live: Submit state-changing request without CSRF token | Rejected |
| 4.15 | File upload validation | Live: Upload executable disguised as PDF | Rejected by type checking |
| 4.16 | Request size limits | Live: Submit oversized payload | 413 Payload Too Large |

#### Encryption & Transport (4 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 4.17 | TLS 1.2+ enforced | Live: Attempt TLS 1.0/1.1 connection | Connection refused |
| 4.18 | HSTS headers present | Live: Check response headers | `Strict-Transport-Security` with long max-age |
| 4.19 | Encryption at rest for sensitive data | Static: Review DB encryption config | AES-256 or equivalent on PII columns |
| 4.20 | API keys/secrets not in source code | Static: Scan codebase | Zero hardcoded secrets |

#### Operational Security (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 4.21 | Security headers complete | Live: Check all response headers | CSP, X-Frame-Options, X-Content-Type-Options present |
| 4.22 | Rate limiting on auth endpoints | Live: Rapid-fire login attempts | 429 Too Many Requests after threshold |
| 4.23 | Admin endpoints IP-restricted (optional) | Static: Review admin route middleware | IP allowlist capability exists |
| 4.24 | Dependency vulnerability scan | Static: Run `pip audit` / `npm audit` | Zero critical/high CVEs |

---

## DOMAIN 5: ONBOARDING & PROVISIONING

**Priority:** HIGH — Required to actually land enterprise clients.
**Reference:** `reference/onboarding.md`

### Purpose

Validate the platform can onboard enterprise clients (50-500+ users) efficiently
with proper configuration, role assignment, and go-live validation.

### Checks (16 total)

#### Bulk User Provisioning (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 5.1 | CSV bulk user import | Live: Import 100-user CSV | All users created with correct roles |
| 5.2 | SCIM provisioning endpoint | Live: SCIM CREATE/UPDATE/DELETE | Users sync from IdP automatically |
| 5.3 | Role template bulk assignment | Live: Apply "LO" template to 50 users | All permissions correctly applied |
| 5.4 | Welcome email / credential delivery | Live: Bulk create users | Each receives onboarding email with secure credential setup |

#### Organization Configuration (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 5.5 | Org hierarchy setup (branches, regions) | Live: Create multi-branch org | Hierarchy reflects correctly in permissions |
| 5.6 | Subscription tier feature activation | Live: Enable enterprise features | Only paid features accessible |
| 5.7 | Integration credential setup | Live: Configure Salesforce/BytePro/Encompass | Connection verified, initial sync successful |
| 5.8 | Agent configuration per org | Live: Enable/disable specific AI agents | Only enabled agents available |

#### SSO / Identity (4 checks, CRITICAL for enterprise)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 5.9 | SAML SSO configuration | Live: Configure SAML IdP | Login via SSO works, user auto-provisioned |
| 5.10 | OIDC configuration | Live: Configure OIDC provider | Login via OIDC works |
| 5.11 | JIT user provisioning | Live: First SSO login for new user | User created with default role |
| 5.12 | SSO-enforced login (disable password) | Live: Set org to SSO-only | Password login disabled |

#### Go-Live Readiness (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 5.13 | Onboarding checklist completion | Live: Review org setup checklist | All required items completed |
| 5.14 | Sample data cleanup | Live: Verify no test/demo data in production | Zero test records |
| 5.15 | Admin user designated | Live: Verify org has admin user(s) | At least 1 admin with MFA enabled |
| 5.16 | Training materials accessible | Live: Verify help docs/videos available | Role-specific training content accessible |

---

## DOMAIN 6: PERFORMANCE & LOAD TESTING

**Priority:** HIGH — Required before enterprise go-live.
**Reference:** `reference/performance.md`

### Purpose

Establish capacity ceilings, identify bottlenecks, and verify the platform
handles enterprise-scale concurrent usage.

### Checks (14 total)

#### API Performance (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 6.1 | API response time (p95) under load | Live: 100 concurrent users, measure p95 | < 500ms for read, < 1000ms for write |
| 6.2 | API response time (p99) under load | Live: Same load test, measure p99 | < 2000ms |
| 6.3 | Error rate under load | Live: Track 5xx responses | < 0.1% error rate |
| 6.4 | API throughput ceiling | Live: Ramp to failure | Document max RPS per endpoint category |

#### Database Performance (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 6.5 | Query performance (slowest queries) | Live: `pg_stat_statements` analysis | No query > 1s at p95 |
| 6.6 | Connection pool saturation | Live: Monitor pool under load | Pool never fully exhausted |
| 6.7 | Index coverage on hot queries | Static: EXPLAIN ANALYZE on top 20 queries | All use index scans, no seq scans on large tables |
| 6.8 | Deadlock frequency | Live: Monitor `pg_stat_activity` under concurrent writes | Zero deadlocks |

#### Background Worker Performance (3 checks, MEDIUM)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 6.9 | Webhook processing throughput | Live: Fire 1000 webhooks in 60s | All processed within 5 minutes |
| 6.10 | Sync worker completion time | Live: Full sync on 10K-record org | Completes within configured interval |
| 6.11 | Queue depth under load | Live: Monitor job queues during peak | Queue depth returns to 0 within SLA |

#### AI Agent Performance (3 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 6.12 | Agent response latency | Live: Concurrent agent invocations | < 5s for standard queries |
| 6.13 | Agent token consumption | Live: Monitor token usage per query | Within configured budget (12-18K per query) |
| 6.14 | Agent concurrent capacity | Live: 50 simultaneous agent requests | All complete without timeout |

---

## DOMAIN 7: INTEGRATION HEALTH

**Priority:** HIGH — Required as clients connect existing tools.
**Reference:** `reference/integrations.md`

### Purpose

Validate that all external integrations (LOS, CRM, telephony, email, document)
are healthy, syncing correctly, and resilient to failure.

### Checks (18 total)

#### LOS Integration — BytePro / Encompass (6 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 7.1 | Auth credentials valid | Live: Test API connection | 200 OK with valid session |
| 7.2 | Field mapping completeness | Live: Score mapped vs available fields | > 80% of critical fields mapped |
| 7.3 | Bidirectional sync functional | Live: Push record, pull back, diff | < 2% field delta |
| 7.4 | Sync latency within SLA | Live: Measure push-to-confirm time | < 60 seconds |
| 7.5 | Conflict resolution working | Live: Modify same record in both systems | Conflict detected and logged, latest-write or merge applied |
| 7.6 | Webhook delivery reliable | Live: Check webhook delivery log | > 99% delivery rate, retries functional |

#### CRM Integration — Salesforce (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 7.7 | OAuth token refresh functional | Live: Force token expiry and refresh | New token obtained without user action |
| 7.8 | SOQL query performance | Live: Run field discovery query | < 2s response time |
| 7.9 | Bulk API usage within limits | Live: Check API call count vs limit | < 70% of daily limit consumed |
| 7.10 | Echo prevention (anti-bounce) | Live: Push record, verify no re-sync loop | Watermark advances, no duplicate sync events |

#### Telephony — Twilio / Retell (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 7.11 | Twilio account SID/auth valid | Live: API status check | 200 OK |
| 7.12 | Phone number provisioning functional | Live: Request number | Number provisioned and active |
| 7.13 | Call recording storage accessible | Live: Retrieve recent recording | Audio file accessible |
| 7.14 | Webhook delivery to call processing pipeline | Live: Trace recent call through pipeline | Call → transcript → AI agents → CRM update verified |

#### Email — Microsoft Graph / SMTP (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 7.15 | Email OAuth valid | Live: Check token status | Valid or auto-refreshed |
| 7.16 | Email send functional | Live: Send test email | Delivered within 30s |
| 7.17 | Email receive/sync functional | Live: Check inbox sync timestamp | Synced within 5 minutes |
| 7.18 | Email template rendering | Live: Render all templates | Zero rendering errors |

---

## DOMAIN 8: DISASTER RECOVERY

**Priority:** HIGH — Required for SOC 2 and enterprise compliance.
**Reference:** `reference/disaster-recovery.md`

### Purpose

Validate backup/restore procedures, failover mechanisms, and business
continuity capabilities.

### Checks (12 total)

#### Backup & Restore (4 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 8.1 | Database backup schedule active | Static: Review backup config | Automated daily backups running |
| 8.2 | Backup restoration tested | Live: Restore backup to test environment | Data integrity verified, < 1 hour RTO |
| 8.3 | Point-in-time recovery (PITR) available | Static: Review WAL archiving | PITR enabled with configurable retention |
| 8.4 | Backup encryption | Static: Review backup storage | Backups encrypted at rest |

#### Failover & Resilience (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 8.5 | Database failover functional | Live: Simulate primary failure | Replica promoted within RPO/RTO targets |
| 8.6 | Queue persistence across restart | Live: Enqueue jobs, restart workers | All jobs processed after restart |
| 8.7 | Graceful degradation without AI provider | Live: Block AI API calls | Core CRM functions still work (read/write/search) |
| 8.8 | Graceful degradation without telephony | Live: Block Twilio API | Manual call logging still works, queue for retry |

#### Data Retention & Archival (4 checks, MEDIUM)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 8.9 | Data retention policy enforced | Static: Review retention config | Configurable per tenant, default 7 years |
| 8.10 | Archived data accessible for compliance | Live: Retrieve archived loan file | Full audit trail accessible |
| 8.11 | Data deletion capability (GDPR/CCPA) | Live: Request user data deletion | PII removed, audit record retained |
| 8.12 | RPO/RTO documented and tested | Static + Live: Review documentation | RPO < 1 hour, RTO < 4 hours documented and demonstrated |

---

## DOMAIN 9: ANALYTICS & REPORTING

**Priority:** HIGH — Required for ongoing value demonstration.
**Reference:** `reference/analytics.md`

### Purpose

Validate the platform produces enterprise-grade reports, dashboards, and
analytics with proper access controls and export capabilities.

### Checks (14 total)

#### Report Generation (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 9.1 | Pipeline report generation | Live: Generate pipeline report | Accurate data, correct filters, renders in < 10s |
| 9.2 | LO production scorecard | Live: Generate LO scorecard | Units, volume, conversion rates, comparison to org avg |
| 9.3 | SLA compliance report | Live: Generate SLA report | All milestones tracked, violations flagged |
| 9.4 | Compliance audit report | Live: Generate compliance report | All regulatory events included with timestamps |

#### Access Controls (3 checks, CRITICAL)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 9.5 | Branch manager sees only their branch | Live: Auth as branch mgr, pull report | Only branch data in results |
| 9.6 | LO sees only their pipeline | Live: Auth as LO, pull report | Only assigned loans visible |
| 9.7 | Admin sees entire org | Live: Auth as admin, pull report | All org data accessible |

#### Export & Delivery (4 checks, MEDIUM)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 9.8 | PDF export functional | Live: Export report as PDF | Renders correctly, includes date/time stamp |
| 9.9 | Excel export functional | Live: Export report as XLSX | Correct columns, formatting, formulas |
| 9.10 | CSV export functional | Live: Export as CSV | Proper escaping, UTF-8 encoding |
| 9.11 | Scheduled report delivery | Live: Schedule daily report email | Delivered on schedule |

#### Dashboard Performance (3 checks, MEDIUM)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 9.12 | Dashboard load time | Live: Measure dashboard render | < 3 seconds with full data |
| 9.13 | Real-time metrics accuracy | Live: Compare dashboard to raw query | < 5 minute data lag |
| 9.14 | Custom date range filtering | Live: Filter reports by custom range | Accurate results for any date range |

---

## DOMAIN 10: MIGRATION & DATA IMPORT

**Priority:** HIGH — Required to get clients off their current system.
**Reference:** `reference/migration.md`

### Purpose

Validate the platform can ingest data from common mortgage CRM/LOS sources
with proper mapping, cleansing, validation, and rollback capability.

### Checks (14 total)

#### Import Capabilities (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 10.1 | CSV/Excel import functional | Live: Import 1000-row CSV | All records created, validation errors reported |
| 10.2 | Field mapping UI functional | Live: Map source fields to Perennia fields | Mapping saved, preview shows correct transformation |
| 10.3 | Data cleansing applied | Live: Import messy data (bad phones, mixed case) | Auto-cleaned per rules |
| 10.4 | Duplicate detection during import | Live: Import file with known duplicates | Duplicates flagged, merge/skip options presented |

#### Validation & Preview (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 10.5 | Dry-run preview | Live: Run import in preview mode | Shows what will be created/updated without committing |
| 10.6 | Required field validation | Live: Import with missing required fields | Validation errors with row numbers |
| 10.7 | Data type validation | Live: Import with wrong types (text in date field) | Type errors identified before commit |
| 10.8 | Referential validation | Live: Import loans without matching contacts | Unresolved references flagged |

#### Migration from Common Sources (3 checks, MEDIUM)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 10.9 | Encompass export ingestion | Live: Import Encompass CSV export | Field mapping template available, > 80% auto-mapped |
| 10.10 | Velocify/LoanTek lead import | Live: Import Velocify lead export | Leads created with proper status mapping |
| 10.11 | Generic CRM import (BNTouch, Jungo, etc.) | Live: Import generic CSV | Custom field mapping works for any schema |

#### Rollback & Audit (3 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 10.12 | Import rollback capability | Live: Roll back completed import | All imported records removed cleanly |
| 10.13 | Import audit trail | Live: Review import history | Every import logged with count, user, timestamp, errors |
| 10.14 | Large file handling | Live: Import 50K-row file | Completes without timeout, progress tracking visible |

---

## DOMAIN 11: API GATEWAY & DEVELOPER EXPERIENCE

**Priority:** MEDIUM — Required for ecosystem partnerships.
**Reference:** `reference/api-gateway.md`

### Purpose

Validate the platform provides a production-grade API for third-party integrations
with proper documentation, authentication, versioning, and developer tooling.

### Checks (12 total)

#### API Documentation (3 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 11.1 | OpenAPI/Swagger spec auto-generated | Live: Hit /docs endpoint | Complete spec with all endpoints, models, auth |
| 11.2 | API documentation accuracy | Live: Compare spec to actual endpoints | Zero undocumented endpoints, zero phantom endpoints |
| 11.3 | Code examples available | Static: Review developer docs | Examples in Python, JavaScript, cURL for top 10 operations |

#### API Management (5 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 11.4 | API key provisioning | Live: Create API key via admin UI | Key created with configurable scopes |
| 11.5 | API rate limiting per client | Live: Exceed rate limit | 429 with Retry-After header |
| 11.6 | API versioning | Live: Call v1 and v2 endpoints | Both functional, v1 deprecated gracefully |
| 11.7 | Webhook event catalog | Static: Review webhook docs | All events documented with payload schemas |
| 11.8 | Webhook retry with exponential backoff | Live: Register failing webhook endpoint | Retries with increasing intervals, maxes out and alerts |

#### Developer Environment (4 checks, MEDIUM)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 11.9 | Sandbox environment available | Live: Access sandbox API | Separate from production, test data pre-loaded |
| 11.10 | API changelog maintained | Static: Review changelog | Every breaking change documented with migration guide |
| 11.11 | SDK availability | Static: Review published SDKs | At least Python + JavaScript SDKs |
| 11.12 | Postman/Insomnia collection | Static: Review collection | Importable collection with all endpoints and auth pre-configured |

---

## DOMAIN 12: WHITE-LABEL & THEMING

**Priority:** MEDIUM — Required for bank and large lender deals.
**Reference:** `reference/white-label.md`

### Purpose

Validate the platform supports complete brand customization per tenant with
no Perennia branding leaking through.

### Checks (12 total)

#### Brand Configuration (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 12.1 | Logo upload and display | Live: Upload custom logo | Logo appears in header, emails, reports, portal |
| 12.2 | Color scheme customization | Live: Set primary/secondary/accent colors | All UI elements reflect custom colors |
| 12.3 | Font customization | Live: Set custom font family | Applied across application |
| 12.4 | Favicon customization | Live: Upload custom favicon | Browser tab shows custom icon |

#### Communication Branding (4 checks, HIGH)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 12.5 | Email templates use tenant branding | Live: Send email from white-labeled org | Zero Perennia branding, all tenant branding |
| 12.6 | SMS sender ID customizable | Live: Send SMS from white-labeled org | Sender name/number matches tenant config |
| 12.7 | Portal branding complete | Live: Access borrower portal | Full tenant branding, zero Perennia references |
| 12.8 | Report/PDF branding | Live: Generate report from white-labeled org | Tenant logo, colors, name on all reports |

#### Domain & Infrastructure (4 checks, MEDIUM)

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| 12.9 | Custom domain support | Live: Configure custom domain | Portal accessible at custom domain with SSL |
| 12.10 | SSL provisioning for custom domain | Live: Check SSL cert | Valid cert, auto-renewed |
| 12.11 | Subdomain routing | Live: Access tenant.customdomain.com | Routes to correct tenant |
| 12.12 | Branding leak scan | Live: Full-text search for "Perennia" in white-labeled output | Zero occurrences in UI, emails, docs, portal |

---

## OUTPUT FORMAT

### Markdown Report Structure

```markdown
# Perennia AI Enterprise Readiness Report
**Generated:** {timestamp}
**Mode:** {mode}
**Overall Grade:** {grade} ({score}/100)

## Executive Summary
{pass_count} of {total_count} checks passed across {domain_count} domains.
{critical_failure_count} critical failures require immediate remediation.

## Domain Scores
| Domain | Score | Grade | Critical Failures |
|--------|-------|-------|-------------------|
| 1. Multi-Tenant Isolation | {score} | {grade} | {count} |
| ... | ... | ... | ... |

## Critical Failures (Immediate Action Required)
### {domain_name}: {check_id} — {check_name}
- **Severity:** CRITICAL
- **Expected:** {pass_criteria}
- **Actual:** {actual_result}
- **Remediation:** {remediation_steps}
- **Evidence:** {evidence}

## All Results by Domain
### Domain 1: Multi-Tenant Isolation ({score}/100 — {grade})
| # | Check | Severity | Result | Evidence |
|---|-------|----------|--------|----------|
| 1.1 | RLS policies exist | CRITICAL | PASS | 47/47 tables covered |
| ... | ... | ... | ... | ... |

## Remediation Plan
| Priority | Check | Domain | Estimated Effort | Owner |
|----------|-------|--------|-----------------|-------|
| 1 | {check} | {domain} | {effort} | {suggested_owner} |
```

### JSON Output Structure

```json
{
  "report_id": "uuid",
  "generated_at": "ISO-8601",
  "mode": "full",
  "overall_score": 87,
  "overall_grade": "B",
  "enterprise_ready": false,
  "blocking_failures": ["1.3", "2.1", "4.6"],
  "domains": [
    {
      "id": 1,
      "name": "Multi-Tenant Isolation",
      "score": 92,
      "grade": "A",
      "checks_total": 18,
      "checks_passed": 17,
      "checks_failed": 1,
      "critical_failures": [],
      "checks": [
        {
          "id": "1.1",
          "name": "RLS policies exist on all tenant-scoped tables",
          "severity": "CRITICAL",
          "method": "static",
          "result": "PASS",
          "evidence": "47/47 tables have active RLS policies",
          "remediation": null
        }
      ]
    }
  ],
  "remediation_plan": [
    {
      "priority": 1,
      "check_id": "2.1",
      "domain": "Compliance & Regulatory",
      "description": "LE delivery deadline not auto-calculated",
      "effort": "2-3 days",
      "suggested_owner": "backend"
    }
  ]
}
```

---

## Execution Cadence

| Audience | Frequency | Mode | Trigger |
|----------|-----------|------|---------|
| **Pre-sale / Enterprise deal** | On-demand | `full` | Sales team requests certification |
| **New client onboarding** | Once per client | `onboarding` | Client contract signed |
| **Production monitoring** | Weekly | `security` + `integration` | Automated schedule |
| **Regulatory review** | Monthly | `compliance` | Compliance team schedule |
| **Load testing** | Quarterly or pre-launch | `performance` | Capacity planning |
| **SOC 2 preparation** | Annually | `full` | Audit preparation |

---

## Summary

**196 total checks** across 12 domains:

| Domain | Checks | Critical | High | Medium | Low |
|--------|--------|----------|------|--------|-----|
| 1. Multi-Tenant Isolation | 18 | 15 | 2 | 1 | 0 |
| 2. Compliance & Regulatory | 22 | 14 | 6 | 2 | 0 |
| 3. Data Quality & Integrity | 20 | 8 | 7 | 5 | 0 |
| 4. Security Audit | 24 | 15 | 9 | 0 | 0 |
| 5. Onboarding & Provisioning | 16 | 4 | 12 | 0 | 0 |
| 6. Performance & Load Testing | 14 | 0 | 11 | 3 | 0 |
| 7. Integration Health | 18 | 6 | 12 | 0 | 0 |
| 8. Disaster Recovery | 12 | 4 | 4 | 4 | 0 |
| 9. Analytics & Reporting | 14 | 3 | 4 | 7 | 0 |
| 10. Migration & Data Import | 14 | 0 | 11 | 3 | 0 |
| 11. API Gateway & Dev Experience | 12 | 0 | 8 | 4 | 0 |
| 12. White-Label & Theming | 12 | 0 | 8 | 4 | 0 |
| **TOTAL** | **196** | **69** | **94** | **33** | **0** |

**69 critical checks** — any single failure blocks enterprise certification.
**94 high checks** — failures require remediation plan with timeline.
**33 medium checks** — tracked but don't block deployment.

An enterprise-ready platform passes all 69 critical checks and scores ≥ 80
across all 12 domains.
