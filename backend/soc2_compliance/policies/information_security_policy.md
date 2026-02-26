# Information Security Policy

**SOC 2 Criteria:** CC1 (Control Environment), CC5 (Control Activities)
**Last Reviewed:** 2026-02-25
**Next Review:** 2026-08-25
**Owner:** Security Team

## 1. Purpose

Establish the framework for protecting the confidentiality, integrity, and availability of all information assets within the Perennia AI platform.

## 2. Scope

This policy applies to all employees, contractors, and third-party service providers who access, process, or store information within Perennia AI systems.

## 3. Policy Statements

### 3.1 Information Protection
- All sensitive data (PII, financial records, loan data) must be classified per the Data Classification Policy.
- Data at rest must be encrypted using AES-256 or equivalent (Fernet field-level encryption for PII columns).
- Data in transit must use TLS 1.2 or higher.

### 3.2 Access Management
- Access follows the principle of least privilege.
- All access is authenticated (JWT RS256 tokens) and authorized (role-based access control).
- Multi-factor authentication is required for all administrative access.

### 3.3 Security Monitoring
- All API requests are logged via the SOC 2 audit middleware.
- High-severity events trigger automated alerts via DataDog/SIEM integration.
- Compliance scans run daily at 02:15 UTC.

### 3.4 Vulnerability Management
- Dependencies are pinned in `requirements.lock` and reviewed monthly.
- Security patches for critical vulnerabilities must be applied within 72 hours.

## 4. Procedures

1. New employee onboarding includes security awareness training.
2. Quarterly access reviews verify least-privilege compliance.
3. Annual penetration testing conducted by qualified third party.
4. Security incidents follow the Incident Response Policy.

## 5. Review Schedule

| Review Type | Frequency | Responsible Party |
|---|---|---|
| Policy review | Semi-annual | Security Team |
| Access audit | Quarterly | Platform Admin |
| Penetration test | Annual | External vendor |
| Compliance scan | Daily (automated) | SOC 2 Scheduler |
