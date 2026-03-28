# Disaster Recovery Plan (DRP)

## Perennia AI Platform

---

## 1. Document Control

| Field | Value |
|---|---|
| **Document Title** | Disaster Recovery Plan |
| **Version** | 1.0 |
| **Effective Date** | 2026-03-27 |
| **Last Reviewed** | 2026-03-27 |
| **Next Review** | 2026-09-27 |
| **Document Owner** | Engineering Lead |
| **Approved By** | _See Section 14 - Approval & Signatures_ |
| **Classification** | Internal - Confidential |
| **SOC 2 Criteria** | A1 (Availability), A1.2 (Recovery), A1.3 (Testing) |

**Review Schedule:** This document must be reviewed and updated:
- Semi-annually (every 6 months) under normal conditions
- After any Severity 1 or Severity 2 incident
- After any significant infrastructure change (provider migration, new region, architecture shift)
- After each DR test exercise

**Change History:**

| Version | Date | Author | Description |
|---|---|---|---|
| 1.0 | 2026-03-27 | Engineering Team | Initial formal DRP |

---

## 2. Purpose & Scope

### 2.1 Purpose

This Disaster Recovery Plan (DRP) defines the procedures, responsibilities, and resources required to recover the Perennia AI platform following a service disruption, data loss event, or infrastructure failure. It operationalizes the objectives stated in the [Disaster Recovery Policy](disaster_recovery_policy.md) and provides step-by-step runbooks for each failure scenario.

This document satisfies SOC 2 Trust Services Criteria:
- **A1.2** -- Environmental protections, data backups, and recovery infrastructure are authorized, designed, developed, implemented, operated, approved, maintained, and monitored to meet the entity's availability commitments and system requirements.
- **A1.3** -- Recovery plan procedures supporting system recovery are tested to help meet the entity's availability commitments.

### 2.2 Scope

This plan covers all production systems comprising the Perennia AI platform:

- Backend API application (FastAPI on Railway)
- PostgreSQL database (Railway-hosted)
- Redis instance (task queue broker, caching layer)
- AWS S3 buckets (document storage, file assets)
- Frontend application (Vercel-hosted SPA)
- Marketing site (Vercel-hosted)
- Celery worker processes (background task execution)
- Third-party integrations (Telnyx telephony, Twilio/Vapi voice AI, Anthropic/OpenAI/Mistral LLM providers, Salesforce, Encompass LOS, Deepgram, DataDog)

**Out of Scope:** End-user devices, third-party SaaS provider internal DR (covered by vendor management policy), and development/staging environments.

---

## 3. Recovery Objectives

### 3.1 Recovery Point Objective (RPO)

| Component | RPO Target | Mechanism |
|---|---|---|
| PostgreSQL database | **1 hour** | WAL archiving with continuous streaming; Railway PITR |
| Redis (task queue) | **4 hours** | RDB snapshots + AOF persistence; tasks are idempotent and replay-safe |
| AWS S3 (documents) | **24 hours** | Cross-region replication; versioning enabled |
| Application code | **0 (zero loss)** | Git repository on GitHub; every deployment is a tagged commit |
| Environment configuration | **0 (zero loss)** | Railway encrypted variable storage; documented in secure vault |

### 3.2 Recovery Time Objective (RTO)

| Scenario | RTO Target | Notes |
|---|---|---|
| Single component failure | **1 hour** | Automated failover or rapid manual intervention |
| Multi-component failure | **2 hours** | Parallel recovery procedures |
| Full infrastructure failure | **4 hours** | Complete rebuild from backups and IaC |
| Security breach (containment + recovery) | **4 hours** recovery after containment | Containment is immediate; forensics may extend total timeline |

### 3.3 Service Level Tiers

The platform operates in four degradation levels as defined by the `GracefulDegradation` service:

| Level | Definition | User Impact |
|---|---|---|
| **Full** | All services operational | None |
| **Degraded** | AI features limited, core CRM functional | AI chat/voice unavailable; CRUD operations work |
| **Minimal** | Database + auth only | Read-only pipeline view; no integrations |
| **Maintenance** | All services offline | Full outage; status page active |

---

## 4. Infrastructure Overview

### 4.1 Architecture Diagram (Logical)

```
                    +-----------------+
                    |   Vercel CDN    |
                    | (Frontend SPA)  |
                    +--------+--------+
                             |
                    +--------v--------+
                    |  Railway LB     |
                    | (Load Balancer) |
                    +--------+--------+
                             |
              +--------------+--------------+
              |                             |
     +--------v--------+          +--------v--------+
     | Railway App      |          | Celery Workers   |
     | (FastAPI)        |          | (Background)     |
     +--------+---------+          +--------+---------+
              |                             |
     +--------v---------+         +--------v---------+
     | Railway PostgreSQL|         | Redis             |
     | (Primary DB)      |         | (Broker + Cache)  |
     +-------------------+         +-------------------+
              |
     +--------v---------+
     | AWS S3            |
     | (Document Store)  |
     +-------------------+
```

### 4.2 Component Details

| Component | Provider | Region | Redundancy |
|---|---|---|---|
| **PostgreSQL Database** | Railway | US (Oregon) | WAL archiving, PITR, daily snapshots |
| **Application Server** | Railway | US (Oregon) | Stateless containers, instant rollback |
| **Celery Workers** | Railway | US (Oregon) | Multiple worker processes, task retry |
| **Redis** | Railway | US (Oregon) | RDB + AOF persistence |
| **Frontend SPA** | Vercel | Edge (global CDN) | Multi-region edge deployment |
| **Document Storage** | AWS S3 | us-east-1 (primary) | Versioning, cross-region replication |
| **DNS** | Cloudflare / Vercel | Global | Anycast DNS, automatic failover |
| **Monitoring** | DataDog | SaaS | Independent of application infrastructure |

### 4.3 Critical Dependencies

| Dependency | Impact if Unavailable | Fallback |
|---|---|---|
| Anthropic API | AI agent features disabled | Graceful degradation to non-AI CRM; circuit breaker pattern |
| Telnyx | Outbound calls/SMS disabled | Queue messages for retry; manual calling |
| Twilio/Vapi | Voice AI disabled | Telnyx direct dial fallback |
| Deepgram | Voice transcription unavailable | Buffer audio for later processing |
| Salesforce | Sync paused | Queue sync operations; manual export |
| Encompass LOS | Loan sync paused | Queue operations; manual LOS entry |

---

## 5. Disaster Classification

### Severity 1 -- Critical (Full Outage)

**Definition:** Complete loss of platform availability. No users can access any functionality.

**Examples:**
- Railway region-wide outage
- Database corruption affecting all tables
- Compromised credentials with active data exfiltration
- DNS hijacking or domain compromise
- Complete network partition

**Response Time:** Immediate (within 15 minutes of detection)
**Escalation:** Engineering Lead + CTO + all on-call engineers

### Severity 2 -- Major (Partial Outage, Core Affected)

**Definition:** Core CRM functionality (pipeline, leads, loans) is unavailable, but some services may still operate.

**Examples:**
- PostgreSQL failure (database unreachable)
- Authentication system failure (no user can log in)
- Data integrity issue affecting loan records
- Redis failure causing task queue loss and session issues

**Response Time:** Within 30 minutes of detection
**Escalation:** Engineering Lead + on-call engineer

### Severity 3 -- Moderate (Feature Degradation)

**Definition:** Non-core features unavailable; core CRM continues to function.

**Examples:**
- AI/LLM provider outage (Anthropic, OpenAI, Mistral)
- Telephony provider outage (Telnyx or Twilio)
- S3 access issues (document upload/download affected)
- Celery worker failure (background tasks delayed)
- Single third-party integration failure

**Response Time:** Within 1 hour of detection
**Escalation:** On-call engineer

### Severity 4 -- Minor (Cosmetic / Low Impact)

**Definition:** Minor service degradation with minimal user impact.

**Examples:**
- Elevated API response latency (but within timeouts)
- Non-critical background job failures
- Monitoring/alerting system partial failure
- CDN cache invalidation issues

**Response Time:** Within 4 hours (next business day if after hours)
**Escalation:** Engineering team via standard ticketing

---

## 6. Recovery Procedures

### 6a. Database Failure Recovery

**Severity:** 1-2 | **RTO:** 1-2 hours | **RPO:** 1 hour

**Detection:**
- DataDog alert: PostgreSQL connection failures
- Health endpoint (`/health`) returns database error
- `/api/v1/admin/dr/failover-readiness` reports DB check failure

**Automated Response:**
- Circuit breaker activates for database-dependent routes
- `GracefulDegradation` service transitions to "minimal" or "maintenance" level
- Health endpoint reflects degraded state

**Manual Recovery Steps:**

1. **Assess the failure**
   ```
   # Check Railway dashboard for PostgreSQL service status
   # Review DataDog PostgreSQL integration metrics
   # Check /api/v1/admin/dr/degradation-health for current service level
   ```

2. **Attempt connection recovery**
   ```
   # Railway will auto-restart crashed database containers
   # Wait up to 5 minutes for automatic recovery
   # Monitor Railway deployment logs for PostgreSQL restart events
   ```

3. **If auto-recovery fails -- initiate PITR restore**
   ```
   # Navigate to Railway project > PostgreSQL service > Backups
   # Select most recent clean backup point (within RPO window)
   # Initiate Point-in-Time Recovery
   # Railway provisions new volume from WAL archive
   # Expected duration: 15-45 minutes depending on data volume
   ```

4. **Post-restore validation**
   ```
   # Run /api/v1/admin/dr/rto-benchmark to verify DB connectivity
   # Execute schema verification (pending migrations check)
   # Run data integrity checks via compliance scan
   # Verify row counts on critical tables: loans, leads, users, organizations
   ```

5. **Re-run pending migrations**
   ```
   # Review alembic migration history
   # Apply any migrations that were pending at time of failure
   ```

6. **Restore service**
   ```
   # Verify /health returns 200
   # Verify /api/v1/admin/dr/failover-readiness passes all checks
   # Monitor error rates for 30 minutes post-recovery
   ```

7. **Post-recovery audit**
   - Record incident in `soc2_security_incident` table
   - Verify audit logging resumed correctly
   - Check for any data inconsistencies in the RPO gap window

---

### 6b. Application Server Failure

**Severity:** 2-3 | **RTO:** 30 minutes | **RPO:** N/A (stateless)

**Detection:**
- DataDog alert: health endpoint unreachable
- Vercel frontend reports API connection failures
- Railway deployment status shows unhealthy containers

**Recovery Steps:**

1. **Check Railway deployment status**
   ```
   # Railway dashboard > App service > Deployments
   # Identify if current deployment is healthy or crashed
   ```

2. **If current deployment crashed -- rollback**
   ```
   # Railway dashboard > Deployments > Select last known-good deployment
   # Click "Rollback" to redeploy previous version
   # Railway handles zero-downtime rollback for stateless services
   ```

3. **If Railway infrastructure issue -- redeploy**
   ```
   # Trigger fresh deployment from main branch
   # git push origin main (or trigger via Railway CLI)
   ```

4. **Verify recovery**
   ```
   # Confirm /health returns 200
   # Confirm /api/v1/admin/dr/degradation-health shows "full" service level
   # Verify audit logging is active
   # Test authentication flow end-to-end
   ```

5. **Notify stakeholders**
   - If downtime exceeded 30 minutes, notify affected users per Communication Plan

---

### 6c. Redis / Queue Failure

**Severity:** 2-3 | **RTO:** 1 hour | **RPO:** 4 hours (task state)

**Detection:**
- DataDog alert: Redis connection refused
- `/api/v1/admin/dr/queue-persistence` reports failure
- Celery workers log broker connection errors
- Background tasks (email, SMS, sync) stop executing

**Recovery Steps:**

1. **Assess Redis availability**
   ```
   # Check Railway Redis service status
   # Review /api/v1/admin/dr/queue-persistence for configuration status
   ```

2. **If Redis crashed -- wait for auto-restart**
   ```
   # Railway auto-restarts crashed Redis containers
   # RDB snapshot + AOF log restore data to last persistence point
   # Wait up to 5 minutes for automatic recovery
   ```

3. **If persistent data loss -- rebuild**
   ```
   # Provision new Redis instance on Railway
   # Update REDIS_URL environment variable
   # Restart application and Celery workers
   ```

4. **Recover lost tasks**
   ```
   # Celery tasks configured with task_acks_late=True and reject_on_worker_lost=True
   # Unacknowledged tasks replay automatically on broker reconnection
   # For tasks that may have been lost:
   #   - Check pending email queue and resend
   #   - Check pending SMS queue and resend
   #   - Trigger manual Salesforce/Encompass sync if needed
   #   - Re-dispatch any failed retention cleanup tasks
   ```

5. **Verify recovery**
   ```
   # Confirm /api/v1/admin/dr/queue-persistence passes all checks
   # Verify Celery workers are processing tasks (check Flower dashboard if available)
   # Test a round-trip task (e.g., trigger a test notification)
   ```

---

### 6d. S3 / Storage Failure

**Severity:** 3 | **RTO:** 2 hours | **RPO:** 24 hours

**Detection:**
- DataDog alert: S3 API errors
- Document upload/download failures reported by users
- Application logs show S3 timeout or access denied errors

**Recovery Steps:**

1. **Assess S3 availability**
   ```
   # Check AWS Health Dashboard for S3 service status
   # Verify IAM credentials are valid and not rotated
   # Test S3 connectivity with aws s3 ls
   ```

2. **If regional S3 outage -- switch to replica region**
   ```
   # Update S3_BUCKET_NAME and AWS_REGION environment variables to replica region
   # Cross-region replication ensures data is available in secondary region
   # Restart application to pick up new configuration
   ```

3. **If credential issue -- rotate credentials**
   ```
   # Generate new IAM access key in AWS console
   # Update AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in Railway
   # Restart application
   ```

4. **Verify recovery**
   ```
   # Test document upload via API
   # Test document download for existing file
   # Verify document listing returns expected results
   ```

5. **Deferred action**
   - Once primary region recovers, revert configuration
   - Verify cross-region replication is current
   - Audit any documents uploaded during failover period

---

### 6e. Complete Infrastructure Failure

**Severity:** 1 | **RTO:** 4 hours | **RPO:** 1 hour (database), 24 hours (files)

**Trigger:** Total loss of Railway infrastructure, or coordinated multi-provider failure.

**Recovery Steps:**

1. **Activate incident command** (see Section 7 - Communication Plan)
   - Incident Commander assumes control
   - All engineers join emergency channel
   - Status page updated to "Major Outage"

2. **Provision new Railway project**
   ```
   # Create new Railway project from infrastructure-as-code templates
   # Or: provision equivalent infrastructure on backup provider
   ```

3. **Restore database**
   ```
   # Obtain latest PostgreSQL backup from Railway backup storage
   # (Railway retains backups even if project is deleted)
   # Restore to new PostgreSQL instance
   # Verify WAL replay completes successfully
   # Validate table counts and data integrity
   ```

4. **Configure environment**
   ```
   # Restore all environment variables from secure vault
   # Critical variables:
   #   DATABASE_URL, REDIS_URL, SECRET_KEY
   #   AWS credentials (S3 access)
   #   TELNYX_API_KEY, TWILIO_AUTH_TOKEN
   #   ANTHROPIC_API_KEY, OPENAI_API_KEY
   #   VAPI_API_KEY, DEEPGRAM_API_KEY
   #   DATADOG_API_KEY
   #   SALESFORCE_* credentials
   # Verify no trailing whitespace or newline characters in credentials
   ```

5. **Deploy application**
   ```
   # Connect new Railway project to GitHub repository (main branch)
   # Trigger deployment
   # Verify build completes and containers start
   ```

6. **Deploy Celery workers**
   ```
   # Configure worker service in Railway
   # Set REDIS_URL to new Redis instance
   # Verify workers connect and begin processing
   ```

7. **Provision Redis**
   ```
   # Create new Redis instance in Railway
   # Configure RDB + AOF persistence
   # Update REDIS_URL across all services
   ```

8. **Update DNS**
   ```
   # If Railway URL changed, update api.perenniaai.com DNS record
   # TTL is typically 300s; propagation within 5-10 minutes
   ```

9. **Run full validation**
   ```
   # /health endpoint returns 200
   # /api/v1/admin/dr/failover-readiness -- all checks pass
   # /api/v1/admin/dr/queue-persistence -- all checks pass
   # /api/v1/admin/dr/rto-benchmark -- within RTO target
   # /api/v1/admin/dr/degradation-health -- service level "full"
   # Test end-to-end: login, view pipeline, create lead, upload document
   ```

10. **Verify integrations**
    ```
    # Salesforce sync connectivity
    # Telnyx telephony (test outbound SMS)
    # Vapi voice AI (test call)
    # Encompass LOS sync (if configured)
    # Email delivery (test notification)
    ```

11. **Post-recovery**
    - Run compliance scan
    - Verify audit logging is active and recording
    - Reconcile any data in the RPO gap (check source systems)
    - Update status page to "Operational"
    - Notify all users of recovery

---

### 6f. Security Breach / Data Compromise

**Severity:** 1 | **RTO:** 4 hours (after containment) | **RPO:** Determined by forensics

**This procedure supplements the [Incident Response Policy](incident_response_policy.md).**

**Immediate Containment (within 15 minutes):**

1. **Isolate affected systems**
   ```
   # Revoke compromised credentials immediately
   # Rotate SECRET_KEY to invalidate all active sessions/JWTs
   # If DB compromised: restrict network access to Railway PostgreSQL
   # If S3 compromised: revoke IAM credentials, enable bucket policy deny-all
   ```

2. **Preserve forensic evidence**
   ```
   # Take database snapshot BEFORE any cleanup
   # Export Railway deployment logs
   # Export DataDog logs for affected timeframe
   # Capture current audit trail from soc2_security_incident table
   # Do NOT restart services until evidence is preserved
   ```

3. **Assess scope**
   ```
   # Determine what data was accessed/exfiltrated
   # Check audit logs for unauthorized access patterns
   # Review JWT blacklist for tokens that should have been revoked
   # Check for unauthorized API key usage
   ```

**Recovery (after containment confirmed):**

4. **Credential rotation**
   ```
   # Rotate ALL secrets (not just compromised ones):
   #   SECRET_KEY, DATABASE_URL password, REDIS_URL password
   #   All API keys (Telnyx, Twilio, Vapi, Anthropic, OpenAI, Mistral, Deepgram)
   #   AWS IAM credentials
   #   Salesforce OAuth tokens
   #   Encompass client secret
   # Update all values in Railway environment variables
   ```

5. **Database recovery (if tampered)**
   ```
   # Restore database from last known-clean backup (pre-breach)
   # This may be before the 1-hour RPO if breach was undetected
   # Replay legitimate transactions from audit log if possible
   ```

6. **Force user password resets**
   ```
   # Invalidate all user sessions (SECRET_KEY rotation handles JWTs)
   # Flag all user accounts for password reset on next login
   # Notify users via out-of-band communication (email from separate system)
   ```

7. **Regulatory notification**
   - Assess if breach triggers state data breach notification laws
   - Mortgage data (NPI) falls under GLBA Safeguards Rule
   - California: CCPA notification within 72 hours if CA residents affected
   - Other states: per state breach notification statutes
   - Document all notification decisions and timestamps

8. **Post-breach hardening**
   - Review and tighten RBAC permissions
   - Enable additional monitoring/alerting rules
   - Conduct security review of the attack vector
   - Update this DRP with lessons learned

---

## 7. Communication Plan

### 7.1 Internal Escalation Matrix

| Severity | First Responder | Escalation (15 min) | Escalation (30 min) | Executive Notification |
|---|---|---|---|---|
| **Sev 1** | On-call engineer | Engineering Lead | CTO | Immediate |
| **Sev 2** | On-call engineer | Engineering Lead | CTO (if unresolved at 1 hr) | Within 1 hour |
| **Sev 3** | On-call engineer | Engineering Lead (if unresolved at 2 hrs) | -- | Daily summary |
| **Sev 4** | Engineering team | -- | -- | Weekly summary |

### 7.2 Incident Roles

| Role | Responsibility |
|---|---|
| **Incident Commander** | Coordinates response, makes decisions, owns communication |
| **Technical Lead** | Directs technical recovery, assigns tasks |
| **Communications Lead** | Updates status page, drafts customer notifications |
| **Scribe** | Documents timeline, actions, and decisions in real time |

### 7.3 External Communication

| Audience | Channel | Timing |
|---|---|---|
| All users | Status page (status.perenniaai.com) | Immediately upon Sev 1-2 detection |
| Affected users | In-app banner + email | Within 1 hour for outages > 30 minutes |
| All users | Email | Post-incident summary within 48 hours |
| Regulatory (if breach) | Formal written notice | Per applicable state/federal requirements |

### 7.4 Communication Templates

**Status Page -- Investigating:**
> We are currently investigating an issue affecting [component]. Some users may experience [impact]. We will provide updates every 30 minutes.

**Status Page -- Identified:**
> We have identified the cause of [issue] and are actively working on recovery. Estimated time to resolution: [ETA].

**Status Page -- Resolved:**
> The issue affecting [component] has been resolved. All services are operating normally. A full post-incident report will be published within 48 hours.

---

## 8. Backup Strategy

### 8.1 PostgreSQL Database

| Attribute | Value |
|---|---|
| **Provider** | Railway managed PostgreSQL |
| **Backup Method** | WAL (Write-Ahead Log) archiving + daily base backups |
| **Frequency** | Continuous WAL streaming; daily full snapshots |
| **Retention** | 7 days (Railway default); critical snapshots exported monthly |
| **RPO Capability** | Point-in-time recovery to any second within retention window |
| **Restore Method** | Railway console PITR or snapshot restore |
| **Encryption** | At rest (Railway volume encryption); in transit (TLS) |

**Validation:** The `/api/v1/admin/dr/failover-readiness` endpoint checks:
- WAL archiving is active (`archive_mode = on`)
- Replication slots are configured
- Database latency is within acceptable bounds

### 8.2 AWS S3 Document Storage

| Attribute | Value |
|---|---|
| **Bucket** | Production document bucket (us-east-1) |
| **Versioning** | Enabled (protects against accidental deletion/overwrite) |
| **Replication** | Cross-region replication to secondary region |
| **Retention** | Per document type; minimum 7 years for loan documents per GLBA/TRID |
| **Encryption** | SSE-S3 (server-side encryption at rest); TLS in transit |
| **Access Control** | IAM role with least-privilege; bucket policy restricts by IP/role |

### 8.3 Redis

| Attribute | Value |
|---|---|
| **Persistence** | RDB snapshots (every 60 seconds if >= 1 key changed) + AOF (append-only file) |
| **Backup** | Railway-managed; RDB files retained on volume |
| **Data Classification** | Transient (cache, session, task queue); not source-of-truth |
| **Loss Impact** | Tasks replay via Celery retry; cache rebuilds automatically; sessions re-authenticate |

**Validation:** The `/api/v1/admin/dr/queue-persistence` endpoint checks:
- Celery `task_acks_late` is enabled
- Celery `reject_on_worker_lost` is enabled
- Redis RDB/AOF persistence configuration
- Current queue depths

### 8.4 Application Code

| Attribute | Value |
|---|---|
| **Repository** | GitHub (private) |
| **Branches** | `main` (production), feature branches |
| **Protection** | Branch protection on `main`; PR review required |
| **CI/CD** | GitHub Actions (test suite) + Railway auto-deploy on push to `main` |
| **Retention** | Full Git history; indefinite |

### 8.5 Configuration & Secrets

| Attribute | Value |
|---|---|
| **Storage** | Railway encrypted environment variables |
| **Backup** | Documented in secure credential vault (see Appendix B) |
| **Rotation Schedule** | API keys quarterly; passwords semi-annually; after any suspected compromise |

---

## 9. Failover Procedures

### 9.1 Database Failover

Railway PostgreSQL uses managed PITR (Point-in-Time Recovery). Failover is provider-managed for hardware failures. For logical corruption (bad migration, accidental deletion), manual PITR restore is required.

**Automated Failover (Hardware):**
- Railway detects container/volume failure
- New container provisioned with existing volume or PITR restore
- Connection string remains stable (Railway internal networking)
- Application reconnects via SQLAlchemy connection pool retry

**Manual Failover (Logical Corruption):**
1. Identify last known-good point in time from audit logs
2. Initiate PITR restore in Railway console
3. Validate restored data (see Section 11)
4. Update `DATABASE_URL` if new instance provisioned
5. Restart application services

### 9.2 Application Failover

Railway provides instant rollback to any previous deployment:

1. Navigate to Railway dashboard > Service > Deployments
2. Select last successful deployment
3. Click "Rollback"
4. Railway performs zero-downtime deployment swap
5. Verify health endpoint

### 9.3 Redis Failover

1. Railway auto-restarts crashed Redis containers
2. Data restored from RDB snapshot + AOF replay
3. If volume is unrecoverable:
   - Provision new Redis instance
   - Update `REDIS_URL` environment variable
   - Restart all application and worker services
   - Lost tasks will be retried by Celery's retry policy

### 9.4 Frontend Failover

Vercel provides automatic failover:
- Global edge CDN with automatic failover between edge nodes
- If build fails, previous deployment remains active
- Instant rollback via Vercel dashboard
- Static assets served from CDN even if origin is unavailable

### 9.5 AI Provider Failover

The platform implements circuit breaker pattern (`CircuitBreaker` service) for AI providers:

1. Circuit opens after 5 consecutive failures (configurable)
2. `GracefulDegradation` transitions to "degraded" service level
3. Core CRM functionality remains available without AI
4. Circuit half-opens after recovery timeout (30 seconds)
5. Single successful request closes circuit, restoring full service

Provider fallback chain: Anthropic -> OpenAI -> Mistral (for call intelligence)

---

## 10. DR Testing Schedule

### 10.1 Test Calendar

| Test Type | Frequency | Duration | Participants | Next Scheduled |
|---|---|---|---|---|
| **Backup Restoration Test** | Quarterly | 2-4 hours | Engineering Team | Q2 2026 (April) |
| **Failover Drill** | Semi-annually | 2-4 hours | Engineering Team | Q3 2026 (July) |
| **Full DR Exercise** | Annually | Full day | Engineering + Security | Q4 2026 (October) |
| **Tabletop Exercise** | Semi-annually | 1-2 hours | Engineering + Leadership | Q2 2026 (May) |
| **Policy Review** | Semi-annually | 1 hour | Engineering Lead | Q3 2026 (September) |

### 10.2 Backup Restoration Test Procedure

1. Select a recent Railway PostgreSQL backup
2. Restore to an isolated test environment (not production)
3. Verify table counts match production (within RPO tolerance)
4. Run application health checks against restored database
5. Execute sample queries for critical data (loans, leads, users)
6. Document results, time to restore, and any issues
7. File test report in SOC 2 evidence repository

### 10.3 Failover Drill Procedure

1. Simulate component failure (stop one Railway service)
2. Verify graceful degradation activates correctly
3. Execute recovery procedure from this document
4. Measure actual recovery time against RTO target
5. Verify all automated readiness checks pass post-recovery
6. Document gaps between plan and actual execution
7. Update this DRP with any needed corrections

### 10.4 Full DR Exercise Procedure

1. Simulate complete infrastructure failure (theoretical or actual)
2. Execute full recovery from Section 6e
3. Measure total time from "disaster declared" to "fully operational"
4. Validate all integrations restored and functional
5. Run compliance scan and verify audit trail continuity
6. Conduct post-exercise debrief
7. Update all DR documentation with findings

### 10.5 Test Success Criteria

| Criteria | Target |
|---|---|
| Database restored within RTO | < 4 hours |
| Data loss within RPO | < 1 hour of transactions |
| All health checks pass post-recovery | 100% |
| Audit logging resumed | Verified |
| All automated DR endpoints return healthy | Verified |

### 10.6 SOC 2 Evidence (A1.3)

All DR test results must be documented and retained as evidence:
- Test date, participants, and scenario
- Actual RTO/RPO achieved
- Issues encountered and remediation
- Sign-off by Engineering Lead

---

## 11. Post-Recovery Validation Checklist

Execute this checklist after any recovery event. All items must pass before declaring "recovered."

### 11.1 Infrastructure Validation

- [ ] Railway dashboard shows all services healthy (green)
- [ ] `/health` endpoint returns HTTP 200 with all checks passing
- [ ] `/api/v1/admin/dr/failover-readiness` -- all checks passed
- [ ] `/api/v1/admin/dr/queue-persistence` -- all checks passed
- [ ] `/api/v1/admin/dr/rto-benchmark` -- recovery time within RTO target
- [ ] `/api/v1/admin/dr/degradation-health` -- service level is "full"
- [ ] DataDog monitoring is receiving metrics and logs

### 11.2 Database Validation

- [ ] All database migrations are current (no pending)
- [ ] Row counts on critical tables are within expected range:
  - `users` / `organizations`
  - `loans` / `leads`
  - `documents` / `activities`
  - `compliance_alerts` / `soc2_security_incident`
- [ ] Sample queries return expected data for recent records
- [ ] Foreign key constraints are intact (no orphaned records)
- [ ] Indexes are present and used (check `pg_stat_user_indexes`)

### 11.3 Application Validation

- [ ] User authentication works (login, JWT issuance, token refresh)
- [ ] Role-based access control is enforced (test admin vs. LO)
- [ ] Pipeline view loads with correct data
- [ ] Lead creation and update works
- [ ] Loan record CRUD operations succeed
- [ ] Document upload and download works (S3 connectivity)
- [ ] Search functionality returns results

### 11.4 Integration Validation

- [ ] Celery workers are processing tasks (check queue depth trending down)
- [ ] Email delivery functional (trigger test notification)
- [ ] SMS delivery functional (test via Telnyx)
- [ ] AI chat responds (Anthropic/OpenAI connectivity)
- [ ] Voice AI functional (Vapi connectivity if applicable)
- [ ] Salesforce sync operational (if configured for org)
- [ ] Encompass LOS sync operational (if configured for org)

### 11.5 Compliance Validation

- [ ] Audit logging is active and recording new events
- [ ] Tenant isolation (RLS) is enforced
- [ ] CSRF middleware is active
- [ ] Rate limiting is functional
- [ ] SOC 2 compliance scan passes
- [ ] No compliance alerts in "open" state from the incident itself are unaddressed

### 11.6 Documentation

- [ ] Incident recorded in `soc2_security_incident` table
- [ ] Timeline documented (detection, response, recovery, validation)
- [ ] Root cause identified (or investigation opened)
- [ ] Status page updated to "Operational"
- [ ] User notification sent (if outage exceeded 30 minutes)
- [ ] Post-incident report draft started (due within 48 hours)

---

## 12. Appendix A: Contact List

> **CLASSIFICATION: RESTRICTED** -- This section contains contact information. Maintain in secure document management system alongside this plan.

| Role | Name | Phone | Email | Backup Contact |
|---|---|---|---|---|
| Engineering Lead | _[NAME]_ | _[PHONE]_ | _[EMAIL]_ | _[BACKUP]_ |
| CTO | _[NAME]_ | _[PHONE]_ | _[EMAIL]_ | _[BACKUP]_ |
| On-Call Engineer (Primary) | _[NAME]_ | _[PHONE]_ | _[EMAIL]_ | _[BACKUP]_ |
| On-Call Engineer (Secondary) | _[NAME]_ | _[PHONE]_ | _[EMAIL]_ | _[BACKUP]_ |
| Security Officer | _[NAME]_ | _[PHONE]_ | _[EMAIL]_ | _[BACKUP]_ |

### External Contacts

| Provider | Support Channel | Account ID | SLA |
|---|---|---|---|
| Railway | Dashboard support / Discord | _[ACCOUNT]_ | Best-effort (managed hosting) |
| AWS | AWS Support console | _[ACCOUNT]_ | Business support tier |
| Vercel | Dashboard support | _[ACCOUNT]_ | Pro plan support |
| DataDog | Support portal | _[ACCOUNT]_ | Standard support |
| Telnyx | Portal / support@telnyx.com | _[ACCOUNT]_ | Enterprise support |
| Twilio | Console / support | _[ACCOUNT]_ | Standard support |
| Anthropic | API support | _[ACCOUNT]_ | API tier support |

---

## 13. Appendix B: System Access Credentials Location

> **CLASSIFICATION: RESTRICTED** -- This section documents WHERE credentials are stored, not the credentials themselves.

| System | Credential Location | Access Method |
|---|---|---|
| Railway (all services) | Railway dashboard > Project > Variables | Railway account login (SSO) |
| AWS (S3, IAM) | AWS IAM console | Root account MFA + IAM role |
| GitHub (repository) | GitHub organization settings | GitHub SSO |
| Vercel (frontend) | Vercel dashboard > Project > Settings | Vercel account login |
| DataDog (monitoring) | DataDog organization settings | DataDog account login |
| Domain registrar (DNS) | Registrar account | Account login + MFA |
| Telnyx (telephony) | Telnyx Mission Control portal | Account login |
| Twilio (voice) | Twilio console | Account login |
| Anthropic (AI) | Anthropic console | Account login |

**Credential Backup:**
- All production environment variables are documented in the secure credential vault
- Vault location: _[VAULT_URL]_ (accessible to Engineering Lead and CTO only)
- Last vault sync: _[DATE]_
- Vault backup: _[BACKUP_LOCATION]_

**Emergency Access:**
- If primary credential holder is unavailable, secondary access is through _[PROCESS]_
- Break-glass procedure: _[DOCUMENTED_SEPARATELY]_

---

## 14. Approval & Signatures

This Disaster Recovery Plan has been reviewed and approved by the following parties:

| Role | Name | Signature | Date |
|---|---|---|---|
| Engineering Lead | __________________ | __________________ | ________ |
| CTO | __________________ | __________________ | ________ |
| Security Officer | __________________ | __________________ | ________ |

**Approval Criteria:**
- All recovery procedures have been validated in test environment
- RTO and RPO targets are achievable based on DR test results
- Contact list and credential locations are current
- Communication templates and escalation matrix are approved by leadership

---

## SOC 2 Criteria Mapping

| SOC 2 Criteria | DRP Section | Evidence |
|---|---|---|
| **A1** -- Availability commitments | Section 3 (Recovery Objectives) | RPO/RTO targets documented |
| **A1.2** -- Recovery infrastructure | Section 4 (Infrastructure), Section 8 (Backups) | Architecture, backup strategy, failover procedures |
| **A1.2** -- Recovery procedures | Section 6 (Recovery Procedures) | Step-by-step runbooks for each scenario |
| **A1.3** -- Recovery plan testing | Section 10 (DR Testing Schedule) | Test calendar, procedures, success criteria |
| **CC7.4** -- Incident response | Section 6f (Security Breach), Section 7 (Communication) | Breach response, escalation matrix |
| **CC7.5** -- Incident recovery | Section 11 (Post-Recovery Checklist) | Validation steps, compliance verification |
| **CC9.1** -- Risk mitigation | Section 5 (Disaster Classification) | Severity tiers, response times |

---

## Automated DR Readiness Endpoints

The following admin API endpoints support automated DR validation and should be executed regularly:

| Endpoint | Purpose | Frequency |
|---|---|---|
| `GET /api/v1/admin/dr/failover-readiness` | Validates WAL, replication, DB latency, Redis, connection recovery | Daily (automated) |
| `GET /api/v1/admin/dr/queue-persistence` | Verifies Celery config, Redis persistence, queue depths | Daily (automated) |
| `GET /api/v1/admin/dr/rto-benchmark` | Benchmarks recovery steps and projects achievable RTO | Weekly (automated) |
| `GET /api/v1/admin/dr/degradation-health` | Reports current service level and circuit breaker status | Continuous (monitoring) |
| `GET /api/v1/admin/dr/runbook` | Returns documented failover procedures via API | On-demand |
| `GET /api/v1/admin/dr/retention-policy` | Returns data retention configuration | Monthly review |
| `GET /api/v1/admin/data-retention/report` | Comprehensive retention status across CRM + SOC 2 tables | Monthly review |

All endpoints require admin-level authentication (`admin`, `site_admin`, or `platform_admin` role).

---

*End of Disaster Recovery Plan*
