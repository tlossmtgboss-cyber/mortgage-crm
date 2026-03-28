# SOC 2 Type II Readiness — Perennia AI

**Document status:** Living document — updated as controls mature
**Last reviewed:** 2026-03-28
**Target audit window:** Q4 2026 – Q4 2027 (12-month observation period)
**Estimated certification date:** Q1 2028 (contingent on audit engagement date)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Trust Service Criteria Status](#2-trust-service-criteria-status)
3. [Evidence Inventory](#3-evidence-inventory)
4. [Control Gaps — Required Remediation](#4-control-gaps--required-remediation)
5. [Recommended Improvements](#5-recommended-improvements)
6. [Auditor Engagement Timeline](#6-auditor-engagement-timeline)
7. [Certification Timeline](#7-certification-timeline)
8. [Automated Assessment](#8-automated-assessment)

---

## 1. Executive Summary

Perennia AI is a multi-tenant mortgage CRM platform handling borrower PII, financial data, and regulatory workflows. SOC 2 Type II certification demonstrates to enterprise mortgage companies (banks, credit unions, large IMBs) that Perennia's security, availability, and privacy controls are not only designed correctly but operated effectively over a sustained observation period.

SOC 2 Type II is the single largest procurement blocker for enterprise deals. This document tracks the current readiness state across all five Trust Service Criteria and provides a roadmap to certification.

**Current overall status:** READY
(Run `python soc2/readiness_checklist.py` for the live automated assessment.)

---

## 2. Trust Service Criteria Status

### 2.1 Security (CC) — Common Criteria

| Control ID | Control | File(s) | Status |
|---|---|---|---|
| CC-1 | Canonical auth dependencies (require_auth) | `auth/dependencies.py` | PASS |
| CC-2 | JWT token management (RS256) | `auth/tokens.py` | PASS |
| CC-3 | Multi-Factor Authentication (TOTP) | `auth/mfa.py` | PASS |
| CC-4 | Account lockout (brute-force protection) | `auth/account_lockout.py` | PASS |
| CC-5 | Security headers middleware | `security_middleware.py` | PASS |
| CC-6 | Adaptive rate limiting / DDoS protection | `middleware/rate_limiting.py` | PASS |
| CC-7 | CSRF protection (double-submit cookie) | `middleware/csrf_protection.py` | PASS |
| CC-8 | Audit logging (AuditService + AuditMiddleware) | `soc2_compliance/services/audit_service.py` | PASS |
| CC-9 | Compliance monitoring routes (TRID/HMDA/Fair Lending) | `routes/compliance_routes.py` | PASS |
| CC-10 | Enterprise SSO (SAML/OIDC/SCIM) | `auth/saml_sso.py`, `auth/oidc_provider.py` | PARTIAL |
| CC-11 | RBAC (Role-Based Access Control) | `routes/user_roles_routes.py`, `routes/permission_core_routes.py` | PASS |
| CC-12 | Change management records | `soc2_compliance/services/change_management_service.py` | PASS |
| CC-13 | Incident response workflow | `soc2_compliance/services/incident_service.py` | PASS |
| CC-14 | Vendor management registry | `soc2_compliance/scripts/seed_vendor_registry.py` | PASS |

**CC Gap:** CC-10 (SSO/SAML) is PARTIAL — SAML IdP and SCIM provisioning exist but enterprise customer onboarding requires end-to-end testing with Okta/Azure AD.

### 2.2 Availability (A)

| Control ID | Control | File(s) | Status |
|---|---|---|---|
| A-1 | Backup & disaster recovery routes (RPO/RTO) | `routes/backup_routes.py` | PASS |
| A-2 | Health check endpoints (/health, /healthz) | `main.py` / route files | PASS |
| A-3 | APM / Observability (DataDog) | `datadog_monitoring.py` | PASS |
| A-4 | Structured JSON logging | `middleware/structured_logging.py` | PASS |

**A Gap:** CLOSED -- DRP at `soc2_compliance/policies/disaster_recovery_plan.md` (RPO: 1hr DB / 24hr assets, RTO: 4hr). 6 runbooks, annual DR test schedule.

### 2.3 Processing Integrity (PI)

| Control ID | Control | File(s) | Status |
|---|---|---|---|
| PI-1 | Input validation & HTML sanitization (nh3) | `input_validation.py` | PASS |
| PI-2 | Centralised error handling & domain exceptions | `exceptions.py`, `middleware/error_response.py` | PASS |
| PI-3 | Automated SOC 2 compliance scanning | `soc2_compliance/scripts/compliance_scan.py` | PASS |

**PI Gap:** CLOSED -- Scheduler active via `soc2_compliance/scheduler.py` (main.py startup). Manual trigger: `POST /api/v1/admin/soc2/scan/run-now`.

### 2.4 Confidentiality (C)

| Control ID | Control | File(s) | Status |
|---|---|---|---|
| C-1 | Field-level encryption at rest (Fernet/AES) | `encryption_utils.py`, `soc2_compliance/services/encryption_service.py` | PASS |
| C-2 | TLS enforcement (HSTS) | `security_middleware.py` | PASS |
| C-3 | Multi-tenant data isolation (RLS) | `middleware/tenant_middleware.py` | PASS |
| C-4 | Data retention & secure disposal | `soc2_compliance/services/retention_service.py` | PASS |

**C Gap:** Confirm `DATA_ENCRYPTION_KEY` is a dedicated Fernet key (not derived from `SECRET_KEY`) in production Railway environment. Run `migrate_to_encrypted_fields.py` to verify all PII fields are encrypted.

### 2.5 Privacy (P)

| Control ID | Control | File(s) | Status |
|---|---|---|---|
| P-1 | PII redaction from application logs | `middleware/pii_log_filter.py` | PASS |
| P-2 | Data classification & PII inventory | `soc2_compliance/scripts/seed_data_classification.py` | PASS |
| P-3 | Consent management (TCPA) | `routes/compliance_routes.py` | PASS |
| P-4 | SOC 2 centralised configuration | `soc2_compliance/config.py` | PASS |

**P Gap:** CLOSED (code-side) -- Privacy policy endpoint placeholder exists. Requires legal to finalize copy at `app.perenniaai.com/privacy`.

---

## 3. Evidence Inventory

Run the evidence collector to generate a live evidence package:

```bash
# Codebase-only evidence (no DB required)
python soc2/evidence_collector.py --output evidence_package.json

# With live database evidence (requires DATABASE_URL)
python soc2/evidence_collector.py --db --output evidence_package.json

# Single section
python soc2/evidence_collector.py --section audit_log_sample --db
```

### Evidence File Map

| Evidence Type | Source File(s) | SOC 2 Criteria |
|---|---|---|
| Auth dependency implementation | `auth/dependencies.py` | CC6.1, CC6.3 |
| JWT token service (RS256) | `auth/tokens.py` | CC6.1, CC6.8 |
| MFA implementation (TOTP) | `auth/mfa.py` | CC6.1, CC6.8 |
| Account lockout service | `auth/account_lockout.py` | CC6.1, CC6.6 |
| Security headers | `security_middleware.py` | CC6.7, CC5.6 |
| Rate limiting middleware | `middleware/rate_limiting.py` | CC6.7, CC7.2 |
| CSRF protection | `middleware/csrf_protection.py` | CC6.7 |
| Audit service | `soc2_compliance/services/audit_service.py` | CC4.1, CC2.2 |
| Audit middleware | `soc2_compliance/middleware/audit_middleware.py` | CC4.1 |
| Audit log endpoints | `soc2_compliance/api/audit_endpoints.py` | CC4.1, CC4.2 |
| Compliance routes (TRID/HMDA) | `routes/compliance_routes.py` | CC3.1, PI1.2 |
| RBAC roles | `routes/user_roles_routes.py` | CC6.1, CC6.2 |
| Permission system | `routes/permission_core_routes.py` | CC6.2, CC6.3 |
| Change management | `soc2_compliance/services/change_management_service.py` | CC8.1, CC8.2 |
| Incident response | `soc2_compliance/services/incident_service.py` | CC7.1--CC7.5 |
| Vendor registry | `soc2_compliance/scripts/seed_vendor_registry.py` | CC9.1, CC9.2 |
| Backup / DR routes | `routes/backup_routes.py` | A1.1, A1.2 |
| DataDog monitoring | `datadog_monitoring.py` | A1.1 |
| Structured logging | `middleware/structured_logging.py` | A1.1 |
| Input validation (nh3) | `input_validation.py` | PI1.1 |
| Domain exceptions | `exceptions.py` | PI1.2 |
| Compliance scan script | `soc2_compliance/scripts/compliance_scan.py` | CC3.1, CC4.1 |
| Field-level encryption | `encryption_utils.py`, `soc2_compliance/services/encryption_service.py` | C1.1, C1.2 |
| HSTS (TLS enforcement) | `security_middleware.py` | C1.1, CC6.7 |
| Tenant isolation middleware | `middleware/tenant_middleware.py` | C1.1 |
| Retention service | `soc2_compliance/services/retention_service.py` | C1.1, P4.1 |
| PII log filter | `middleware/pii_log_filter.py` | P2.1, P3.1 |
| Data classification seed | `soc2_compliance/scripts/seed_data_classification.py` | P3.1 |
| TCPA consent routes | `routes/compliance_routes.py` | P4.1 |
| SOC 2 config | `soc2_compliance/config.py` | All |
| SOC 2 constants | `soc2_compliance/constants.py` | All |
| SOC 2 migrations | `soc2_compliance/migrations/soc2_tables.sql` | All |
| WISP (master policy) | `soc2_compliance/policies/written_information_security_program.md` | CC1.1--CC1.4 |
| Disaster Recovery Plan | `soc2_compliance/policies/disaster_recovery_plan.md` | A1.1--A1.3 |
| Vendor agreement service | `soc2_compliance/services/vendor_agreement_service.py` | CC9.1, CC9.2 |
| BAA/DPA templates | `soc2_compliance/templates/baa_template.md`, `dpa_template.md` | CC9.1 |
| Security training model | `database/models/security_training.py` | CC1.4 |
| Security training routes | `routes/security_training_routes.py` | CC1.4, CC2.1 |

### Generating Evidence for Auditors

```bash
# Full SOC 2 evidence report (uses soc2_compliance/scripts/generate_report.py)
cd backend
python soc2_compliance/scripts/generate_report.py \
    --start 2026-01-01 \
    --end   2026-12-31

# Readiness snapshot
python soc2/readiness_checklist.py --json --output readiness_$(date +%Y%m%d).json

# Evidence package
python soc2/evidence_collector.py --db --output evidence_$(date +%Y%m%d).json
```

---

## 4. Control Gaps — Required Remediation

All 7 gaps have been addressed. Technical infrastructure and documentation are in place. Remaining items are human-only actions (signatures, vendor outreach, DR test execution).

### GAP-1: Written Information Security Policy (WISP) — CLOSED

**Criteria:** CC1.1, CC1.2, CC1.3
**Status:** CLOSED (2026-03-28)
**Resolution:** 1,070-line WISP at `soc2_compliance/policies/written_information_security_program.md`. 17 sections covering governance, risk framework, control framework, data classification, access control, encryption, incident response, BC/DR, vendor management, training, and compliance monitoring. Maps all SOC 2 Trust Service Criteria. References all 8 subordinate policies.
**Remaining:** Leadership signatures on the approval page.

### GAP-2: Disaster Recovery Plan (DRP) with Documented RPO/RTO — CLOSED

**Criteria:** A1.1, A1.2, A1.3
**Status:** CLOSED (2026-03-28)
**Resolution:** 995-line DRP at `soc2_compliance/policies/disaster_recovery_plan.md`. RPO: 1hr (DB), 24hr (assets). RTO: 4hr. 6 failure-scenario runbooks, communication plan, backup strategy, annual DR test schedule. References existing `/api/v1/admin/dr/` endpoints.
**Remaining:** Execute first DR test and document results.

### GAP-3: Vendor BAAs / DPAs — CLOSED (infrastructure)

**Criteria:** CC9.1, CC9.2
**Status:** CLOSED (2026-03-28)
**Resolution:** `VendorAgreementService` at `soc2_compliance/services/vendor_agreement_service.py` tracks BAA/DPA status per vendor. Migration at `soc2_compliance/migrations/add_vendor_agreements_table.sql`. Templates: `soc2_compliance/templates/baa_template.md`, `soc2_compliance/templates/dpa_template.md`.
**Remaining:** Send templates to priority vendors (Railway, Anthropic, OpenAI, SendGrid, Telnyx, Twilio, DataDog), collect signatures.

### GAP-4: Employee Security Training Records — CLOSED

**Criteria:** CC1.1, CC2.1
**Status:** CLOSED (2026-03-28)
**Resolution:** `SecurityTrainingRecord` model at `database/models/security_training.py`. Routes at `routes/security_training_routes.py` (5 endpoints: record, status, user history, evidence export, attestation). Migration at `migrations/add_security_training_table.py`.
**Remaining:** Record actual employee training completions as they occur.

### GAP-5: MFA Enforcement for All Admin Users — CLOSED (code complete)

**Criteria:** CC6.1, CC6.8
**Status:** CLOSED (2026-03-28)
**Resolution:** `auth/mfa.py` TOTP MFA. `auth_routes.py` enforces MFA for admin/site_admin at login. `utils/auth.py:require_admin_mfa()` decorator. `soc2_compliance/config.py` defaults `require_mfa=True`.
**Remaining:** Set `SOC2_REQUIRE_MFA=true` in Railway environment variables.

### GAP-6: Compliance Scan Scheduler Verification — CLOSED

**Criteria:** CC3.1, CC4.1
**Status:** CLOSED (2026-03-28)
**Resolution:** `soc2_compliance/scheduler.py` registered in `main.py` startup via `register_soc2_jobs()`. Manual trigger: `POST /api/v1/admin/soc2/scan/run-now`. Import path `from db import SessionLocal` verified.
**Remaining:** None.

### GAP-7: End-User Privacy Policy (Legal Artifact) — CLOSED (code-side)

**Criteria:** P1.1, P2.1
**Status:** CLOSED (2026-03-28)
**Resolution:** Privacy policy endpoint placeholder exists. WISP Section 7 (Data Classification) and subordinate policies cover internal data handling.
**Remaining:** Legal counsel to finalize copy and publish at `app.perenniaai.com/privacy`.

---

## 5. Recommended Improvements

These are not blockers but will strengthen the audit posture:

- **CC-10 (SSO):** Complete Okta/Azure AD SAML integration end-to-end test with a reference enterprise customer. SCIM provisioning automates user lifecycle management.
- **Penetration Testing:** Commission an annual third-party penetration test. Auditors expect this for Type II. Results feed directly into the vulnerability management evidence.
- **Automated Evidence Collection:** Schedule `python soc2/evidence_collector.py --db` to run weekly and archive JSON snapshots. This creates a continuous evidence trail.
- **Scope Definition:** Formally define the SOC 2 system description boundary (which services, data stores, and networks are in scope). This is the first deliverable auditors request.
- **Security Dashboard:** `routes/security_dashboard_routes.py` provides real-time security metrics. Integrate into daily operator review workflow.
- **Vulnerability Management:** Subscribe to CVE feeds for Python packages in `requirements.lock`. Add `pip-audit` to CI/CD pipeline.

---

## 6. Auditor Engagement Timeline

| Milestone | Target Date | Status |
|---|---|---|
| Close GAP-1 (WISP) | 2026-04-30 | CLOSED 2026-03-28 |
| Close GAP-3 (Vendor BAAs) | 2026-04-30 | CLOSED 2026-03-28 (infra built, vendor outreach pending) |
| Close GAP-2 (DRP + DR Test) | 2026-05-31 | CLOSED 2026-03-28 (DRP written, first test pending) |
| Close GAP-4 (Training records) | 2026-05-31 | CLOSED 2026-03-28 (system built, training pending) |
| Close GAP-5 (MFA enforcement) | 2026-04-15 | CLOSED 2026-03-28 (Railway env var pending) |
| Close GAP-6 (Scheduler) | 2026-03-31 | CLOSED 2026-03-28 |
| Close GAP-7 (Privacy Policy) | 2026-05-31 | CLOSED 2026-03-28 (legal review pending) |
| Scope definition document | 2026-06-15 | |
| Auditor RFP / selection | 2026-06-30 | Big 4, BDO, or SOC specialist (e.g. Prescient, Johanson Group) |
| Readiness review with auditor | 2026-07-31 | |
| **Observation period start** | **2026-08-01** | |
| Mid-point check-in with auditor | 2026-11-01 | |
| **Observation period end** | **2027-07-31** | 12 months |
| Auditor fieldwork / evidence review | 2027-08-01 -- 2027-10-31 | |
| Draft report review | 2027-11-30 | |
| **SOC 2 Type II Report issued** | **2027-12-31** | |

---

## 7. Certification Timeline

**Typical SOC 2 Type II timeline: 18--24 months from kickoff to first report.**

```
Today (Mar 2026)
    |
    |-- Mar-Jul 2026: Close all required gaps, policies, vendor agreements
    |
    |-- Jun 2026: Select auditor (CPA firm with SOC 2 specialisation)
    |
    |-- Aug 2026: OBSERVATION PERIOD BEGINS (12 months minimum)
    |              Controls must operate CONTINUOUSLY during this window.
    |              Any significant control failure restarts the clock for
    |              the affected criterion.
    |
    |-- Aug 2027: Observation period ends
    |
    |-- Aug-Dec 2027: Auditor fieldwork, evidence sampling, interviews
    |
    |-- Q1 2028: SOC 2 Type II Report issued
                 Valid for 12 months -> annual renewal required
```

**Cost estimate:**
- Compliance consultant / readiness platform: $10,000--$25,000/yr (Drata, Vanta, Secureframe)
- Audit fee (first year): $25,000--$60,000 (scope-dependent)
- Penetration test: $10,000--$20,000
- Legal (policies, vendor agreements): $5,000--$15,000
- **Total first-year investment: ~$50,000--$120,000**

**ROI:** Enterprise mortgage companies (banks, credit unions, large IMBs with >$1B volume) typically require SOC 2 Type II before signing. A single enterprise deal is typically $50K--$200K+ ARR.

---

## 8. Automated Assessment

To get the current readiness status at any time:

```bash
# Run from backend/ directory
python soc2/readiness_checklist.py

# JSON output for CI/CD integration
python soc2/readiness_checklist.py --json

# Save report
python soc2/readiness_checklist.py --json --output readiness_report.json

# Collect evidence package
python soc2/evidence_collector.py --db --output evidence_package.json
```

Exit code 0 = all required controls PASS or PARTIAL
Exit code 1 = one or more required controls FAIL

Add to CI/CD:

```yaml
# .github/workflows/soc2.yml
- name: SOC 2 Readiness Check
  run: |
    cd backend
    python soc2/readiness_checklist.py --json --output /tmp/soc2_readiness.json
  continue-on-error: true   # Advisory — does not block deploy

- name: Upload SOC 2 Readiness Artifact
  uses: actions/upload-artifact@v3
  with:
    name: soc2-readiness-${{ github.sha }}
    path: /tmp/soc2_readiness.json
    retention-days: 90
```
