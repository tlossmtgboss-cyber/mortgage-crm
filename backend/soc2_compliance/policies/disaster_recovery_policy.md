# Disaster Recovery Policy

**SOC 2 Criteria:** A1 (Availability)
**Last Reviewed:** 2026-02-25
**Next Review:** 2026-08-25
**Owner:** Engineering Team

## 1. Purpose

Define procedures for recovering Perennia AI platform services in the event of a disaster, ensuring business continuity and data integrity.

## 2. Scope

All Perennia AI production systems including the application, database, and integrated services.

## 3. Policy Statements

### 3.1 Recovery Objectives

| Metric | Target | Description |
|---|---|---|
| **RTO** (Recovery Time Objective) | 4 hours | Maximum acceptable downtime |
| **RPO** (Recovery Point Objective) | 1 hour | Maximum acceptable data loss |

### 3.2 Infrastructure (Railway)
- **Database**: PostgreSQL on Railway with automated daily backups.
- **Application**: Stateless containers with instant rollback to previous deployment.
- **Region**: US-based hosting for mortgage data compliance.
- **Scaling**: Horizontal scaling available via Railway service configuration.

### 3.3 Backup Strategy
| Component | Method | Frequency | Retention |
|---|---|---|---|
| PostgreSQL database | Railway automated backup | Daily | 7 days |
| Application code | Git repository (GitHub) | Every commit | Indefinite |
| Environment variables | Railway encrypted storage | On change | Current |
| Audit logs | Database + SIEM forwarding | Real-time | 2 years |

### 3.4 Recovery Procedures

#### Database Recovery
1. Identify latest clean backup from Railway backup list.
2. Restore database from backup via Railway console.
3. Verify data integrity with compliance scan.
4. Re-run any pending migrations.

#### Application Recovery
1. Roll back to last known-good deployment via Railway.
2. Verify health endpoint responds.
3. Check audit logging is active.
4. Notify affected users if downtime exceeded 30 minutes.

#### Complete Infrastructure Recovery
1. Provision new Railway project from infrastructure-as-code.
2. Restore database from backup.
3. Configure environment variables.
4. Deploy latest application version.
5. Run full compliance scan.
6. Verify all integrations (Salesforce, telephony, email).

### 3.5 Communication
- Engineering team notified immediately via on-call rotation.
- Customer notification within 1 hour for outages exceeding 30 minutes.
- Post-incident report within 48 hours.

## 4. Procedures

1. **Detection**: Automated health checks and DataDog alerts.
2. **Assessment**: Determine scope and impact of the incident.
3. **Recovery**: Execute appropriate recovery procedure above.
4. **Verification**: Run compliance scan, verify audit logging.
5. **Documentation**: Record incident and recovery in `soc2_security_incident`.

## 5. Testing Schedule

| Test Type | Frequency | Responsible Party |
|---|---|---|
| Policy review | Semi-annual | Engineering Lead |
| Backup restoration test | Quarterly | Engineering Team |
| Failover drill | Semi-annual | Engineering Team |
| Full DR exercise | Annual | Engineering + Security |
