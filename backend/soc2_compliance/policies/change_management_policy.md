# Change Management Policy

**SOC 2 Criteria:** CC8 (Change Management)
**Last Reviewed:** 2026-02-25
**Next Review:** 2026-08-25
**Owner:** Engineering Team

## 1. Purpose

Ensure all changes to the Perennia AI platform are authorized, tested, and documented to maintain system integrity and availability.

## 2. Scope

All changes to application code, configuration, database schema, infrastructure, and third-party integrations.

## 3. Policy Statements

### 3.1 Change Types
- **Deployment**: Application code releases via Railway CI/CD.
- **Configuration**: Environment variable or feature flag changes.
- **Database Migration**: Schema changes or data migrations.
- **Infrastructure**: Railway service configuration, scaling, networking.
- **Security Patch**: Urgent fixes for security vulnerabilities.

### 3.2 Change Process
1. **Request**: Change documented in pull request or change record.
2. **Review**: Code review required; high-risk changes need two approvers.
3. **Test**: All changes must pass CI tests before deployment.
4. **Approve**: Approval recorded (PR merge = implicit approval).
5. **Implement**: Deployment via Railway with automatic rollback capability.
6. **Verify**: Post-deployment health checks confirm success.

### 3.3 Emergency Changes
- Security patches may bypass standard review for critical vulnerabilities.
- Emergency changes must be documented retroactively within 24 hours.
- Post-implementation review required within 48 hours.

### 3.4 Automated Recording
- Application startup records deployment events with Railway metadata (commit SHA, branch, deployment ID).
- All change records stored in `soc2_change_record` table via `ChangeManagementService`.

### 3.5 Rollback
- All deployments must have a rollback plan.
- Railway provides instant rollback to previous deployment.
- Database migrations must be reversible.

## 4. Procedures

1. Create pull request with description of changes and testing evidence.
2. Obtain code review approval.
3. Merge triggers CI/CD pipeline.
4. Post-deployment: verify health endpoint and audit log activity.
5. If issues detected: initiate rollback and create incident.

## 5. Review Schedule

| Review Type | Frequency | Responsible Party |
|---|---|---|
| Policy review | Semi-annual | Engineering Lead |
| Change audit | Monthly | Security Team |
| Unapproved change review | Daily (automated) | Compliance Scanner |
