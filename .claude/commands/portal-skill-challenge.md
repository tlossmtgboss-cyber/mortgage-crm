---
name: portal-skill-challenge
description: Comprehensive validation skill for Perennia AI portal systems (Borrower/Client PURL portals, Partner/Realtor portals, LO portals). Validates portal setup, user access controls, security posture, CRM data synchronization, and document sync. Use when onboarding new users, deploying portal updates, running health checks, or auditing security and data integrity across all portal types.
---

# Portal Skill Challenge

## Overview

The Portal Skill Challenge validates that all Perennia AI portal systems are correctly configured, secure, and properly syncing data from the CRM (including Salesforce). It covers three portal types across five validation domains:

| Portal Type | Description | Auth Method |
|-------------|-------------|-------------|
| **Borrower/Client Portal** (PURL) | Personal URL workspaces for borrowers — application, documents, tasks, timeline, messages | Token-based (`purl_live_*`) |
| **Partner/Realtor Portal** | Co-branded microsites for referral partners — leads, co-marketing, shared pipeline | JWT + OAuth |
| **Loan Officer Portal** | Internal CRM dashboard — full pipeline, AI agents, workflows | JWT + RBAC |

| Validation Domain | What It Checks |
|-------------------|----------------|
| **Portal Setup** | Configuration, routing, modules enabled, branding, feature flags |
| **User Access** | Authentication flows, token validity, scope enforcement, session management |
| **Security** | RLS policies, tenant isolation, rate limiting, audit logging, PII protection |
| **CRM Data Sync** | Salesforce ↔ CRM field mapping, push/pull cycles, conflict resolution, SLA compliance |
| **Document Sync** | Document request propagation, upload/download integrity, S3 presigned URLs, version tracking |

---

## How to Use This Skill

### When to Trigger

- **New user onboarding**: Run full validation after provisioning a new org/user
- **Post-deployment**: Run after any portal or sync code changes
- **Scheduled health check**: Run daily or weekly as part of ops monitoring
- **Security audit**: Run security domain checks before compliance reviews
- **Incident response**: Run targeted checks when sync failures or access issues are reported

### Execution Modes

| Mode | Scope | Use When |
|------|-------|----------|
| `full` | All 5 domains, all 3 portals | New deployment, major release, audit |
| `portal-only` | Setup + Access only | Portal config changes, UI deploys |
| `sync-only` | CRM Sync + Document Sync only | Sync job changes, Salesforce updates |
| `security-only` | Security domain only | Pre-audit, post-incident |
| `targeted` | Single portal + single domain | Debugging a specific issue |

---

## Validation Architecture

```
┌─────────────────────────────────────────────────────┐
│                 PORTAL SKILL CHALLENGE               │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ Borrower │  │ Partner  │  │    LO    │  Portals  │
│  │  (PURL)  │  │ (Realtor)│  │ (Internal)│          │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘          │
│       │              │              │                │
│  ┌────▼──────────────▼──────────────▼─────┐         │
│  │         VALIDATION DOMAINS              │         │
│  │                                         │         │
│  │  1. Portal Setup       ✓ Config         │         │
│  │  2. User Access        ✓ Auth           │         │
│  │  3. Security           ✓ Isolation      │         │
│  │  4. CRM Data Sync      ✓ Salesforce     │         │
│  │  5. Document Sync      ✓ Files          │         │
│  └────────────┬────────────────────────────┘         │
│               │                                      │
│  ┌────────────▼────────────────────────────┐         │
│  │          REPORT GENERATOR               │         │
│  │  ✓ Pass/Fail per check                  │         │
│  │  ✓ SLA compliance metrics               │         │
│  │  ✓ Security score (0-100)               │         │
│  │  ✓ Remediation steps for failures       │         │
│  └─────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────┘
```

---

## Domain 1: Portal Setup Validation

Ensures each portal type is correctly configured and reachable.

### Checks

Read `reference/portal-setup-checks.md` for the full check definitions.

**Summary of checks:**

| Check ID | Check | Applies To | Severity |
|----------|-------|------------|----------|
| PS-001 | Portal route resolves (HTTP 200/302) | All | CRITICAL |
| PS-002 | PURL workspace exists and status is valid | Borrower | CRITICAL |
| PS-003 | Portal modules enabled match subscription tier | All | HIGH |
| PS-004 | Branding assets (logo, colors, favicon) load | All | MEDIUM |
| PS-005 | Feature flags match org configuration | All | HIGH |
| PS-006 | SSL/TLS certificate valid and not expiring < 30d | All | CRITICAL |
| PS-007 | CORS configuration allows expected origins only | All | HIGH |
| PS-008 | Custom domain DNS resolves correctly | Partner/LO | MEDIUM |
| PS-009 | Portal modules render without JS errors | All | HIGH |
| PS-010 | Mobile responsive breakpoints functional | All | MEDIUM |

---

## Domain 2: User Access Validation

Ensures authentication and authorization work correctly for each portal type.

### Checks

Read `reference/user-access-checks.md` for the full check definitions.

| Check ID | Check | Applies To | Severity |
|----------|-------|------------|----------|
| UA-001 | Token generation returns valid token with correct scopes | Borrower | CRITICAL |
| UA-002 | Expired tokens are rejected (HTTP 401) | All | CRITICAL |
| UA-003 | Revoked tokens are rejected immediately | Borrower | CRITICAL |
| UA-004 | OAuth flow completes and returns valid JWT | Partner/LO | CRITICAL |
| UA-005 | Role-based permissions enforce correct access | LO | CRITICAL |
| UA-006 | Scope enforcement: read-only token cannot write | Borrower | CRITICAL |
| UA-007 | Rate limiting triggers at configured threshold | All | HIGH |
| UA-008 | Session timeout enforced after inactivity period | All | HIGH |
| UA-009 | Concurrent session policy enforced | LO | MEDIUM |
| UA-010 | Password reset / token refresh flow works | All | HIGH |
| UA-011 | Multi-tenant: User A cannot access User B's portal | All | CRITICAL |
| UA-012 | Subscription tier gates features correctly | All | HIGH |

---

## Domain 3: Security Validation

Ensures data isolation, PII protection, and compliance controls.

### Checks

Read `reference/security-checks.md` for the full check definitions.

| Check ID | Check | Applies To | Severity |
|----------|-------|------------|----------|
| SEC-001 | RLS policies active on all PURL tables (15 tables) | Borrower | CRITICAL |
| SEC-002 | Tenant isolation: cross-org query returns 0 rows | All | CRITICAL |
| SEC-003 | PII fields encrypted at rest (SSN, DOB, financial) | All | CRITICAL |
| SEC-004 | Audit log captures all portal CRUD operations | All | HIGH |
| SEC-005 | Rate limiting per-token: 60/min, 1000/hr enforced | Borrower | HIGH |
| SEC-006 | SQL injection protection on all user inputs | All | CRITICAL |
| SEC-007 | XSS prevention: CSP headers present and strict | All | HIGH |
| SEC-008 | API keys/secrets not exposed in client bundles | All | CRITICAL |
| SEC-009 | S3 presigned URLs expire within configured TTL | Borrower | HIGH |
| SEC-010 | HTTPS enforced (HTTP redirects to HTTPS) | All | CRITICAL |
| SEC-011 | Auth tokens use httpOnly, Secure, SameSite flags | All | HIGH |
| SEC-012 | Sensitive data masked in logs (no PII in plaintext) | All | CRITICAL |
| SEC-013 | OWASP Top 10 header checks (X-Frame, X-Content-Type, etc.) | All | HIGH |
| SEC-014 | Database connection uses SSL and connection pooling | All | HIGH |
| SEC-015 | Admin endpoints require elevated privileges | All | CRITICAL |

---

## Domain 4: CRM Data Sync Validation

Ensures Salesforce ↔ Perennia CRM sync is operational, accurate, and within SLA.

### Checks

Read `reference/crm-sync-checks.md` for the full check definitions.

| Check ID | Check | Applies To | Severity |
|----------|-------|------------|----------|
| SYNC-001 | Salesforce OAuth token is valid (not expired/revoked) | All | CRITICAL |
| SYNC-002 | Field mapping configuration is complete (no unmapped required fields) | All | CRITICAL |
| SYNC-003 | Push sync: CRM create → Salesforce record appears < 60s | All | CRITICAL |
| SYNC-004 | Pull sync: Salesforce update → CRM reflects change < 60s | All | CRITICAL |
| SYNC-005 | Bi-directional conflict resolution applies configured policy | All | HIGH |
| SYNC-006 | Lead status changes propagate and trigger correct workflows | Borrower/LO | CRITICAL |
| SYNC-007 | Contact/borrower profile fields match between systems | Borrower | HIGH |
| SYNC-008 | Opportunity/loan stage sync matches milestone definitions | All | HIGH |
| SYNC-009 | Sync error count < 1% of total records in last 24h | All | HIGH |
| SYNC-010 | Retry queue is draining (no stuck records > 1h) | All | HIGH |
| SYNC-011 | Echo prevention: no duplicate records from sync loops | All | CRITICAL |
| SYNC-012 | Custom object sync (Mortgage_App__c etc.) operational | All | HIGH |
| SYNC-013 | Watermark/cursor advancing (sync not stalled) | All | CRITICAL |
| SYNC-014 | SLA dashboard metrics within targets | All | HIGH |

### SLA Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Push latency | < 5 seconds (immediate) | Time from CRM save to Salesforce API call |
| Pull latency | < 60 seconds | Time from Salesforce change to CRM update |
| Echo prevention accuracy | > 99.9% | Duplicate records / total synced |
| Sync success rate | > 99.5% | Successful syncs / total attempts |
| Retry success rate | > 95% | Retries that eventually succeed |

---

## Domain 5: Document Sync Validation

Ensures document requests, uploads, and status sync correctly across portals.

### Checks

Read `reference/document-sync-checks.md` for the full check definitions.

| Check ID | Check | Applies To | Severity |
|----------|-------|------------|----------|
| DOC-001 | Document request created in CRM appears in borrower portal | Borrower | CRITICAL |
| DOC-002 | Document upload from portal stores in S3 and updates CRM record | Borrower | CRITICAL |
| DOC-003 | Document status transitions propagate (requested → uploaded → reviewed → approved) | All | HIGH |
| DOC-004 | Presigned URL generation works and URLs expire correctly | Borrower | HIGH |
| DOC-005 | File type validation enforced (reject disallowed extensions) | All | HIGH |
| DOC-006 | File size limits enforced (configurable per org) | All | MEDIUM |
| DOC-007 | Template pack application creates correct document set | Borrower | HIGH |
| DOC-008 | Document download accessible only by authorized users | All | CRITICAL |
| DOC-009 | Perennia Docs ↔ PURL integration syncs activity feed | Borrower | HIGH |
| DOC-010 | Document version history maintained on re-upload | All | MEDIUM |
| DOC-011 | Bulk document operations (multi-upload) work correctly | Borrower | MEDIUM |
| DOC-012 | Document notifications sent on status change | All | HIGH |

---

## Running the Validation

### Prerequisites

Before running, ensure:

1. **Environment variables** are set (see `reference/environment-config.md`)
2. **Database access** is available (read-only is sufficient for most checks)
3. **Salesforce connected app** credentials are available for sync checks
4. **Test user tokens** are available for each portal type
5. **S3 bucket** access for document sync checks

### Execution Script

The primary entry point is `scripts/portal_validator.py`. See the script for usage:

```bash
# Full validation - all domains, all portals
python scripts/portal_validator.py --mode full

# Portal setup and access only
python scripts/portal_validator.py --mode portal-only

# CRM and document sync only
python scripts/portal_validator.py --mode sync-only

# Security audit
python scripts/portal_validator.py --mode security-only

# Targeted: single portal, single domain
python scripts/portal_validator.py --mode targeted --portal borrower --domain security

# Output formats
python scripts/portal_validator.py --mode full --output json     # Machine-readable
python scripts/portal_validator.py --mode full --output report   # Human-readable markdown
python scripts/portal_validator.py --mode full --output both     # Both
```

### Output

The validator produces:

1. **Validation Report** (`portal_validation_report.md`) — Human-readable summary with pass/fail, severity, remediation steps
2. **Validation Results** (`portal_validation_results.json`) — Machine-readable results for CI/CD integration
3. **Security Score** — Weighted score from 0–100 based on severity of passed/failed checks
4. **SLA Compliance Dashboard** — Sync latency metrics vs targets

---

## Report Structure

```
Portal Skill Challenge Report
├── Executive Summary
│   ├── Overall Score: 87/100
│   ├── Critical Failures: 2
│   ├── High Failures: 3
│   ├── Portals Tested: 3/3
│   └── Domains Tested: 5/5
│
├── Domain 1: Portal Setup
│   ├── ✅ PS-001: Borrower portal route resolves (200)
│   ├── ✅ PS-002: PURL workspace exists (status: active)
│   ├── ❌ PS-004: Partner branding logo returns 404
│   └── ...
│
├── Domain 2: User Access
│   ├── ✅ UA-001: Token generation valid
│   ├── ❌ UA-008: Session timeout not enforced (no expiry header)
│   └── ...
│
├── Domain 3: Security
│   ├── ✅ SEC-001: RLS active on 15/15 PURL tables
│   ├── ✅ SEC-002: Tenant isolation confirmed
│   └── ...
│
├── Domain 4: CRM Data Sync
│   ├── ✅ SYNC-001: Salesforce token valid
│   ├── ❌ SYNC-003: Push latency 4.2s (target < 5s) ✅ within SLA
│   ├── ❌ SYNC-010: 3 stuck records in retry queue > 1h
│   └── ...
│
├── Domain 5: Document Sync
│   ├── ✅ DOC-001: Doc request appears in portal
│   ├── ✅ DOC-002: Upload stores in S3 correctly
│   └── ...
│
├── SLA Compliance
│   ├── Push Latency:        4.2s avg (target < 5s)    ✅
│   ├── Pull Latency:       42s avg (target < 60s)     ✅
│   ├── Echo Prevention:    100% (target > 99.9%)       ✅
│   ├── Sync Success Rate:  99.7% (target > 99.5%)     ✅
│   └── Retry Success Rate: 96.1% (target > 95%)       ✅
│
└── Remediation Plan
    ├── CRITICAL: Fix [issue] — Steps: ...
    ├── HIGH: Fix [issue] — Steps: ...
    └── MEDIUM: Fix [issue] — Steps: ...
```

---

## Security Scoring

The security score is a weighted composite:

| Severity | Weight | Impact on Score |
|----------|--------|-----------------|
| CRITICAL | 10 | Failing = -10 points each |
| HIGH | 5 | Failing = -5 points each |
| MEDIUM | 2 | Failing = -2 points each |

**Score = 100 - sum(failed_check_weights)**

| Score Range | Rating | Action Required |
|-------------|--------|-----------------|
| 90–100 | 🟢 Excellent | No action needed |
| 75–89 | 🟡 Good | Address HIGH items within 1 week |
| 50–74 | 🟠 Needs Attention | Address CRITICAL items within 24h |
| 0–49 | 🔴 Critical | Stop deployment, fix immediately |

---

## CI/CD Integration

The validation script returns exit codes for pipeline integration:

| Exit Code | Meaning |
|-----------|---------|
| 0 | All checks passed |
| 1 | Medium/High failures only (warning) |
| 2 | Critical failures detected (block deploy) |

### GitHub Actions Example

```yaml
- name: Portal Skill Challenge
  run: |
    python scripts/portal_validator.py --mode full --output json
  continue-on-error: false

- name: Upload Validation Report
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: portal-validation-report
    path: portal_validation_report.md
```

---

## Extending the Skill

To add new checks:

1. Add check definition to the appropriate `reference/<domain>-checks.md` file
2. Implement the check function in `scripts/checks/<domain>.py`
3. Register the check in `scripts/portal_validator.py` check registry
4. Add to the summary table in this SKILL.md

Naming convention: `<DOMAIN_PREFIX>-<NNN>` (e.g., `SEC-016`, `DOC-013`)

---

## Key Principles

1. **Never skip security checks** — Even in `portal-only` mode, basic auth validation runs
2. **Read-only by default** — Validation reads state; it never modifies production data
3. **Test isolation** — Test users/tokens are separate from production users
4. **Fail-safe** — If a check cannot be executed (e.g., missing credentials), it reports `SKIPPED` not `PASSED`
5. **Idempotent** — Running the validator multiple times produces the same result
6. **Audit trail** — Every validation run is logged with timestamp, operator, and results
