# Incident Response Policy

**SOC 2 Criteria:** CC7 (System Operations)
**Last Reviewed:** 2026-02-25
**Next Review:** 2026-08-25
**Owner:** Security Team

## 1. Purpose

Define the process for identifying, responding to, and recovering from security incidents to minimize impact and prevent recurrence.

## 2. Scope

All security events affecting the confidentiality, integrity, or availability of Perennia AI systems and data.

## 3. Policy Statements

### 3.1 Incident Categories
- Unauthorized Access
- Data Breach
- Malware / Phishing
- Insider Threat
- Denial of Service
- Data Loss
- Configuration Error
- Vulnerability Exploit
- Policy Violation

### 3.2 Severity Levels
| Level | Response Time | Escalation |
|---|---|---|
| Critical | 1 hour | Immediate exec notification |
| High | 4 hours | Security team + engineering lead |
| Medium | 24 hours | Security team |
| Low | 72 hours | Logged for review |

### 3.3 Incident Lifecycle
1. **Detection**: Automated (anomaly detection, compliance scan) or manual report.
2. **Triage**: Classify category and severity.
3. **Containment**: Isolate affected systems (session termination, IP blocking).
4. **Investigation**: Root cause analysis.
5. **Remediation**: Fix the vulnerability and restore normal operations.
6. **Recovery**: Verify systems are clean and operational.
7. **Post-mortem**: Document lessons learned and preventive measures.
8. **Closure**: Incident closed after post-mortem completion.

### 3.4 Automated Escalation
- Anomalous logins with risk score >= 60 auto-create incidents.
- Risk score >= 80 creates high-severity incidents.
- Overdue critical/high incidents flagged by daily compliance scan.

### 3.5 Notification Requirements
- Data breaches involving PII: notify affected individuals within 72 hours.
- Regulatory reporting as required by GLBA, state breach notification laws.

## 4. Procedures

1. Responder creates incident in `soc2_security_incident` table.
2. Update status through lifecycle stages (each transition logged in timeline).
3. Document root cause, remediation steps, and preventive measures.
4. Complete post-mortem within 5 business days of resolution.
5. Verify preventive measures are implemented.

## 5. Review Schedule

| Review Type | Frequency | Responsible Party |
|---|---|---|
| Policy review | Semi-annual | Security Team |
| Incident response drill | Quarterly | Security Team |
| Open incident review | Weekly | Security Team |
| Post-mortem compliance | Monthly | Engineering Lead |
