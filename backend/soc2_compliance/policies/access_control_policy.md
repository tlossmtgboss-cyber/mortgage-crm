# Access Control Policy

**SOC 2 Criteria:** CC6 (Logical and Physical Access Controls)
**Last Reviewed:** 2026-02-25
**Next Review:** 2026-08-25
**Owner:** Security Team

## 1. Purpose

Define requirements for managing logical access to the Perennia AI platform to prevent unauthorized access to systems and data.

## 2. Scope

All user accounts, API keys, service accounts, and third-party integrations accessing Perennia AI systems.

## 3. Policy Statements

### 3.1 Authentication
- All users must authenticate via password + MFA (when enabled).
- Passwords must be at least 12 characters with uppercase, lowercase, digit, and special character.
- Password expiry: 90 days. Cannot reuse last 12 passwords.
- Account lockout after 5 failed login attempts (30-minute lockout window).

### 3.2 Session Management
- Session timeout: 30 minutes of inactivity (configurable via `SOC2_SESSION_TIMEOUT_MINUTES`).
- Sessions tracked in `soc2_active_session` table.
- Forced session termination available for compromised accounts.

### 3.3 API Key Management
- API keys registered in `soc2_api_key_registry` with hash-only storage.
- Keys must have defined scopes and expiration dates.
- Revoked keys logged with reason and revoking user.

### 3.4 Anomaly Detection
- New IP addresses and devices trigger risk scoring.
- Risk scores >= 40 flag login as anomalous.
- Risk scores >= 60 auto-create security incidents.
- Risk scores >= 80 classified as high-severity incidents.

### 3.5 Role-Based Access Control
- Users assigned roles: Platform Admin, Site Admin, Loan Officer, Processor, etc.
- Row-Level Security (RLS) enforces tenant isolation at the database level.
- Administrative actions require Platform Admin or Site Admin role.

## 4. Procedures

1. User provisioning: Account created by admin, initial password set, MFA enrollment required.
2. Access review: Quarterly review of all active accounts and permissions.
3. Offboarding: Account disabled, all sessions terminated, API keys revoked.
4. Privilege escalation: Requires approval from existing Platform Admin.

## 5. Review Schedule

| Review Type | Frequency | Responsible Party |
|---|---|---|
| Policy review | Semi-annual | Security Team |
| Access review | Quarterly | Platform Admin |
| API key audit | Quarterly | Security Team |
| Anomaly review | Weekly | Security Team |
