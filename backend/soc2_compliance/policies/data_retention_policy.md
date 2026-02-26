# Data Retention Policy

**SOC 2 Criteria:** P4 (Privacy — Disposal)
**Last Reviewed:** 2026-02-25
**Next Review:** 2026-08-25
**Owner:** Security Team

## 1. Purpose

Define retention periods for all data categories and ensure secure disposal of data beyond its retention window.

## 2. Scope

All data stored in Perennia AI databases, including audit logs, access events, incidents, change records, and business data.

## 3. Policy Statements

### 3.1 Retention Periods

| Data Category | Retention | Regulatory Basis |
|---|---|---|
| Audit Logs | 2 years (730 days) | SOC 2 |
| Access Logs | 2 years (730 days) | SOC 2 |
| Security Incidents | 3 years (1,095 days) | SOC 2 / GLBA |
| Change Records | 2 years (730 days) | SOC 2 |
| Compliance Checks | 2 years (730 days) | SOC 2 |
| PII Data | 3 years (1,095 days) | CCPA / GLBA |
| Loan Data | 5 years (1,825 days) | TRID / RESPA |
| Financial Records | 7 years (2,555 days) | IRS / GLBA |

### 3.2 Retention Enforcement
- Automated daily enforcement at 03:00 UTC via `RetentionService`.
- Records archived to `soc2_retention_archive` before deletion.
- WORM (Write-Once Read-Many) triggers prevent ad-hoc deletion of audit trails.
- Retention bypass only available to the automated retention service.

### 3.3 Secure Disposal
- Records deleted in batches (10,000 per batch) to avoid lock contention.
- Deletion logged in the audit trail with counts and cutoff dates.
- Archived records retained for compliance verification.

### 3.4 Data Subject Requests
- CCPA/GDPR deletion requests processed within 30 days.
- Deletion of regulated data (loan records) may be deferred per regulatory requirements.

## 4. Procedures

1. Daily automated retention enforcement runs after compliance scan.
2. Preview available via `RetentionService.preview_retention_enforcement()`.
3. Manual enforcement available via admin endpoint.
4. Retention status monitored via `RetentionService.get_retention_status()`.

## 5. Review Schedule

| Review Type | Frequency | Responsible Party |
|---|---|---|
| Policy review | Semi-annual | Security Team |
| Retention enforcement | Daily (automated) | SOC 2 Scheduler |
| Retention status audit | Monthly | Platform Admin |
