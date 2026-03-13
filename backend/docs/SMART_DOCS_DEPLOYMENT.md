# Smart Docs V2 -- Production Deployment Runbook

Last updated: 2026-03-12

Platform: Railway (auto-deploy from main branch)
Backend: FastAPI on `api.perenniaai.com`
Frontend: SPA on `app.perenniaai.com`

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Environment Variables Reference](#environment-variables-reference)
3. [Database Migration Steps](#database-migration-steps)
4. [Deployment Steps](#deployment-steps)
5. [Rollback Procedure](#rollback-procedure)
6. [Cron Tasks](#cron-tasks)
7. [Monitoring and Alerting](#monitoring-and-alerting)
8. [Troubleshooting Guide](#troubleshooting-guide)

---

## Pre-Deployment Checklist

Complete every item before merging to main. Unchecked items are blockers.

### Infrastructure

- [ ] `DATABASE_URL` configured and reachable from Railway
- [ ] Database backup taken (see [Database Migration Steps](#database-migration-steps))
- [ ] All 4 Smart Docs migrations tested on staging (V2, enterprise, tenant isolation, PII encryption)
- [ ] S3 bucket created with correct CORS policy (see [S3 Configuration](#s3-configuration))
- [ ] AWS IAM credentials scoped to Smart Docs bucket only

### Security

- [ ] `ESIGN_SIGNING_SECRET` generated and set -- persistent HMAC key, NOT ephemeral (see generation command below)
- [ ] `ESIGN_TOKEN_SECRET` generated and set -- JWT signing key for e-sign access tokens
- [ ] `PII_ENCRYPTION_KEY` generated and set -- AES key for PII-at-rest encryption
- [ ] `SECRET_KEY` is the production RS256 key (shared with main auth system)
- [ ] TCPA consent records table seeded (`smart_docs_consent_records`)
- [ ] Internal DNC entries table created (`internal_dnc_entries`)

### AI Services

- [ ] `ANTHROPIC_API_KEY` validated -- test with a classify call on staging
- [ ] AI circuit breaker defaults reviewed (5 failures to open, 60s recovery)
- [ ] Daily AI budget limit set via `SMART_DOCS_AI_BUDGET_DAILY` if cost controls needed

### Integrations (Optional -- skip if not using)

- [ ] Plaid: `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV` configured
- [ ] eClosing: `ECLOSING_PROVIDER`, `ECLOSING_API_URL`, `ECLOSING_API_KEY` configured
- [ ] AUS: `DU_API_URL`/`DU_API_KEY` and/or `LPA_API_URL`/`LPA_API_KEY` configured

### Business Configuration

- [ ] Business rules defaults seeded via `POST /api/smart-docs/config/rules/seed-defaults`
- [ ] Auto-review thresholds set (`SMART_DOCS_AUTO_APPROVE_THRESHOLD`, `SMART_DOCS_AUTO_REJECT_THRESHOLD`)
- [ ] Feature flags configured per org in the feature tier system (`smart_docs` = CORE tier)
- [ ] Document retention policies created in `document_retention_policies` table

### Monitoring

- [ ] Health check endpoint (`GET /api/smart-docs/monitoring/health`) reachable
- [ ] DataDog or equivalent alerting configured for Smart Docs error rates
- [ ] Log level set to INFO (not DEBUG) in production
- [ ] PII log redaction filter verified active

---

## Environment Variables Reference

### Required -- Deployment Will Fail Without These

| Variable | Description | Example / Generation |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:5432/perennia` |
| `ANTHROPIC_API_KEY` | Claude API key for document classification, OCR, income analysis, and call intel extraction | `sk-ant-api03-...` |
| `ESIGN_SIGNING_SECRET` | Persistent HMAC-SHA256 key for e-signature non-repudiation. MUST be set in production. Once set, NEVER rotate without re-signing all active envelopes. | Generate: `python -c 'import secrets; print(secrets.token_hex(32))'` |
| `ESIGN_TOKEN_SECRET` | JWT signing key for e-sign recipient access tokens (short-lived, safe to rotate) | Generate: `python -c 'import secrets; print(secrets.token_hex(32))'` |
| `SECRET_KEY` | Main application JWT signing key (shared with auth system). Used by portal auth service. | Already set in Railway |
| `PII_ENCRYPTION_KEY` | AES-256 key for encrypting PII fields (ocr_text, account numbers, IP addresses) in smart_documents table | Generate: `python -c 'import secrets; print(secrets.token_hex(32))'` |

### AWS / S3 Storage

| Variable | Description | Default |
|---|---|---|
| `SMART_DOCS_S3_BUCKET` | S3 bucket for Smart Docs document storage | Falls back to `PERENNIA_S3_BUCKET`, then `perennia-docs` |
| `AWS_ACCESS_KEY_ID` | AWS IAM access key | Required unless using IAM role |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM secret key | Required unless using IAM role |
| `AWS_REGION` | AWS region for S3 | `us-east-1` |

### AI / ML Configuration

| Variable | Description | Default |
|---|---|---|
| `ANTHROPIC_MODEL` | Default Claude model for AI operations | `claude-sonnet-4-20250514` |
| `ANTHROPIC_VISION_MODEL` | Claude model for vision/PDF analysis (e-sign field detection) | `claude-sonnet-4-20250514` |
| `SMART_DOCS_AI_MODEL` | Model override for document splitting service | `claude-sonnet-4-20250514` |
| `SMART_DOCS_AUTO_APPROVE_THRESHOLD` | AI confidence score (0-100) above which documents are auto-approved | `80` |
| `SMART_DOCS_AUTO_REJECT_THRESHOLD` | AI confidence score (0-100) below which documents are auto-rejected | `30` |

### Portal and Frontend URLs

| Variable | Description | Default |
|---|---|---|
| `APP_URL` | Frontend application base URL | `https://app.perenniaai.com` |
| `PORTAL_BASE_URL` | Borrower portal base URL | `https://app.perenniaai.com/portal` |
| `PORTAL_TOKEN_EXPIRY_HOURS` | Magic link / portal token expiry | `72` |
| `ESIGN_FRONTEND_URL` | E-sign signing page base URL | `https://app.perenniaai.com/esign` |

### E-Signature

| Variable | Description | Default |
|---|---|---|
| `ESIGN_ENABLE_AI_VISION` | Enable AI-powered signature field detection on uploaded PDFs | `false` |
| `ESIGN_MIN_FIELD_CONFIDENCE` | Minimum confidence (0-100) for AI-detected signature fields | `30` |

### Telephony (Follow-up SMS)

| Variable | Description | Default |
|---|---|---|
| `TELNYX_API_KEY` | Telnyx API key for SMS follow-ups | Required for SMS follow-ups |
| `TELNYX_FROM_NUMBER` | Telnyx sending phone number | `+18438838956` |
| `TELNYX_MESSAGING_PROFILE_ID` | Telnyx messaging profile | `40019bed-2fa1-4407-a0c6-fe4c6b222c93` |

### Plaid (Bank Verification -- Optional)

| Variable | Description | Default |
|---|---|---|
| `PLAID_CLIENT_ID` | Plaid API client ID | Empty (disabled) |
| `PLAID_SECRET` | Plaid API secret | Empty (disabled) |
| `PLAID_ENV` | Plaid environment: `sandbox`, `development`, or `production` | `sandbox` |
| `PLAID_WEBHOOK_URL` | Webhook URL for Plaid events | Empty |
| `PLAID_WEBHOOK_VERIFICATION_KEY` | Key for verifying Plaid webhook signatures | Empty |

### AUS Integration (Optional)

| Variable | Description | Default |
|---|---|---|
| `DU_API_URL` | Fannie Mae Desktop Underwriter API endpoint | Empty (mock mode) |
| `DU_API_KEY` | DU API key | Empty |
| `LPA_API_URL` | Freddie Mac Loan Product Advisor API endpoint | Empty (mock mode) |
| `LPA_API_KEY` | LPA API key | Empty |

### eClosing / RON (Optional)

| Variable | Description | Default |
|---|---|---|
| `ECLOSING_PROVIDER` | eClosing platform: `snapdocs`, `pavaso`, `notarycam`, or `internal` | `internal` |
| `ECLOSING_API_URL` | Provider API base URL | Empty |
| `ECLOSING_API_KEY` | Provider API key | Empty |

### Batch Operations

| Variable | Description | Default |
|---|---|---|
| `BATCH_MAX_CONCURRENT_PER_ORG` | Max concurrent batch jobs per organization | `3` |
| `BATCH_ITEM_RATE_LIMIT_SECONDS` | Delay between items in a batch job | `0.1` |
| `BATCH_MAX_ITEMS_PER_JOB` | Maximum items in a single batch job | `500` |
| `BATCH_MAX_ZIP_SIZE_BYTES` | Maximum ZIP download size | `209715200` (200 MB) |
| `BATCH_ASYNC_CONCURRENCY` | Async concurrency limit within a batch | `5` |

### Compliance and Retention

| Variable | Description | Default |
|---|---|---|
| `AUDIT_RETENTION_DAYS` | Minimum audit record retention period. Floor is 2555 (7 years) per IRS guidance. | `2555` |

### Branding

| Variable | Description | Default |
|---|---|---|
| `COMPANY_NAME` | Company name for PDF generation and white-label templates | `Perennia AI` |
| `COMPANY_LOGO_PATH` | File path to company logo for PDF headers | Empty |

---

## Database Migration Steps

Smart Docs V2 uses 4 sequential migrations, all idempotent (safe to re-run). All use `CREATE TABLE IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS`.

### 1. Backup Production Database

```bash
# Railway provides pg_dump via the CLI
railway run pg_dump -Fc > backup_$(date +%Y%m%d_%H%M%S).dump
```

### 2. Run Migrations

Migrations run automatically on app startup via `register_smart_docs_v2_routes()` in `smart_docs_v2_registration.py`. To run manually:

```bash
# Migration 1: Core V2 tables (21 tables)
# E-signature, income calculation, document intelligence, follow-up, security
python -m migrations.smart_docs_v2_migration

# Migration 2: Enterprise tables (10 tables)
# Plaid, AUS, eClosing, IRS transcripts, business rules, cache, audit, consent, DNC
python -m migrations.smart_docs_enterprise_migration

# Migration 3: Tenant isolation fixes (adds organization_id + NOT NULL + composite indexes)
# Fixes 3 tables missing tenant isolation: followup_events, integrity_checks, watermark_logs
python -m migrations.smart_docs_v2_tenant_isolation

# Migration 4: PII encryption columns (adds _encrypted shadow columns to smart_documents)
python -m migrations.smart_docs_pii_encryption
```

Additional table migrations run automatically during registration:
- `add_business_rules_table` -- business_rule_configs
- `add_eclosing_table` -- eclosing_sessions
- `add_aus_submission_table` -- aus_submissions
- `add_irs_transcript_table` -- irs_transcript_requests
- `add_ai_benchmark_tables` -- AI benchmarking tables

### 3. Verify Tables Created

After startup, check logs for:
```
Smart Docs V2: registered N route modules: esign, intelligence, income, ...
Smart Docs V2: database migration complete
Smart Docs Enterprise: N route modules, N middleware components
```

**Tables created by Migration 1 (V2 core -- 21 tables):**

| Group | Tables |
|---|---|
| E-Signature | `esignature_envelopes`, `esignature_recipients`, `esignature_fields`, `esignature_audit_events`, `esignature_templates` |
| Income | `income_calculations`, `income_sources`, `income_verification_tasks` |
| Intelligence | `ai_document_classifications`, `document_requirement_rules`, `pos_document_mappings`, `call_intel_document_needs` |
| Follow-up | `document_followup_campaigns`, `document_followup_events`, `document_appointments`, `document_followup_templates` |
| Security | `document_access_logs`, `document_encryption_records`, `document_integrity_checks`, `document_retention_policies`, `document_watermark_logs` |

**Tables created by Migration 2 (Enterprise -- 10 tables):**

`plaid_connections`, `aus_submissions`, `eclosing_sessions`, `irs_transcript_requests`, `business_rule_configs`, `document_processing_cache`, `decision_audit_logs`, `audit_retention_configs`, `smart_docs_consent_records`, `internal_dnc_entries`

### 4. Seed Business Rules Defaults

After tables are created:
```bash
curl -X POST https://api.perenniaai.com/api/smart-docs/config/rules/seed-defaults \
  -H "Authorization: Bearer <admin_token>" \
  -H "X-API-Key: <api_key>"
```

### 5. Run PII Encryption Backfill (if upgrading from V1)

Only needed if the `smart_documents` table has existing data with plaintext PII:
```bash
PII_ENCRYPTION_KEY=<your_key> python -m migrations.smart_docs_pii_encryption
```

---

## Deployment Steps

### 1. Merge to Main Branch

```bash
git checkout main
git merge <feature-branch>
git push origin main
```

Railway auto-deploys from main.

### 2. Monitor Deployment

Watch Railway deploy logs for:

```
# Route registration (expect ~20 modules)
Smart Docs V2: registered 20 route modules: esign, intelligence, income, followup, security, review, bank-analysis, analytics, portal, portal-v2, config, eclosing, plaid, aus, mismo, monitoring, transcript, benchmark

# Migration output
[SMART_DOCS_V2] Starting Smart Docs V2 migration...
[SMART_DOCS_V2] Smart Docs V2 migration completed successfully!
[SMART_DOCS_ENTERPRISE] Migration complete: 10 tables ensured.

# Middleware
Smart Docs Enterprise: 3 middleware components registered: pii_log_filter, metrics, trace_id
```

### 3. Verify Health Check

```bash
curl https://api.perenniaai.com/api/smart-docs/monitoring/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2026-03-12T...",
  "components": { ... }
}
```

Acceptable statuses: `healthy`, `degraded` (non-critical service down).
Failure status: `unhealthy` -- investigate immediately.

### 4. Run Smoke Tests

```bash
# Test AI classification
curl -X POST https://api.perenniaai.com/api/smart-docs/doc-intel/classify \
  -H "Authorization: Bearer <token>" \
  -F "file=@test_paystub.pdf"

# Test document upload
curl -X POST https://api.perenniaai.com/api/v1/smart-docs/documents/<loan_id>/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@test_document.pdf" \
  -F "doc_type=paystubs"

# Test e-signature envelope creation
curl -X POST https://api.perenniaai.com/api/v1/esign/envelopes \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test Envelope","document_storage_key":"test"}'

# Test monitoring dashboard (admin only)
curl https://api.perenniaai.com/api/smart-docs/monitoring/dashboard \
  -H "Authorization: Bearer <admin_token>"
```

### 5. Monitor Error Rates

Watch for 30 minutes after deploy:
- Railway logs: filter for `ERROR` and `WARNING` with `smart_docs` or `esign`
- DataDog: check Smart Docs route group error rate
- Monitoring endpoint: `GET /api/smart-docs/monitoring/errors?hours=1`

### 6. Verify Cron Tasks Registered

If using APScheduler, check logs for:
```
Smart Docs V2: registered 8 cron tasks
```

---

## Rollback Procedure

### Standard Rollback (Code Only)

1. Revert the merge commit on main:
   ```bash
   git revert <merge_commit_sha>
   git push origin main
   ```
2. Railway auto-redeploys the reverted code.
3. Database migrations are forward-only and additive (CREATE IF NOT EXISTS). No DB rollback needed -- unused tables cause no harm.

### Data Issue Rollback

If corrupted data is discovered:
1. Stop the Railway service immediately via the dashboard.
2. Restore from the pre-deployment backup:
   ```bash
   railway run pg_restore -d perennia backup_YYYYMMDD_HHMMSS.dump
   ```
3. Revert code and redeploy.
4. Investigate root cause before re-attempting deployment.

### Partial Rollback (Single Module)

Individual route modules can be disabled without a full rollback by setting the corresponding import to fail. Each module in `smart_docs_v2_registration.py` is wrapped in try/except -- a missing module is logged and skipped. To disable a module:
1. Rename or delete the route file (e.g., `smart_docs_esign_routes.py` to `smart_docs_esign_routes.py.disabled`).
2. Commit and push. The rest of Smart Docs continues to function.

---

## Cron Tasks

All cron tasks are tenant-isolated (process per-organization) and defined in `backend/tasks/smart_docs_cron_tasks.py`.

| Task | Schedule | Description |
|---|---|---|
| `process_document_followups` | Every 15 minutes | Execute pending follow-up campaign steps |
| `check_document_expirations` | Daily at 6:00 AM | Mark expired documents, create re-upload campaigns |
| `process_auto_renewals` | Daily at 7:00 AM | Create renewal requests for recurring documents (paystubs) |
| `send_esignature_reminders` | Every 4 hours | Send reminders for pending e-sign envelopes, expire stale ones |
| `verify_document_integrity` | Daily at 2:00 AM | Random-sample integrity check on approved documents in S3 |
| `process_call_intelligence_for_documents` | Every 30 minutes | Analyze call transcripts for document needs |
| `monitor_document_slas` | Every hour | Check document request SLA compliance, flag breaches |
| `cleanup_smart_docs` | Daily at 3:00 AM | Expire stale signing tokens, count archivable records |

Registration in `main.py`:
```python
from routes.smart_docs_v2_registration import register_smart_docs_cron_tasks
register_smart_docs_cron_tasks(scheduler)
```

---

## Monitoring and Alerting

### Health Check Endpoint

```
GET /api/smart-docs/monitoring/health
```
- No authentication required (suitable for load balancer probes)
- Returns `healthy`, `degraded`, or `unhealthy`

### Admin Monitoring Endpoints (require admin role)

| Endpoint | Description |
|---|---|
| `GET /monitoring/metrics?hours=24` | Processing counts, latency percentiles, success rates, AI costs |
| `GET /monitoring/sla?hours=24` | SLA compliance per operation type |
| `GET /monitoring/costs?days=30` | AI cost breakdown by operation, daily trend, projected monthly |
| `GET /monitoring/errors?hours=24` | Error counts by service, circuit breaker trip history |
| `GET /monitoring/dashboard?hours=24` | Combined health + SLA + metrics + errors in one call |

All endpoints are under `/api/smart-docs` prefix.

### SLA Targets

| Operation | Target |
|---|---|
| Document classification | < 30 seconds |
| Document review | < 2 minutes |
| Follow-up send | < 1 hour after trigger |
| Income calculation | < 5 minutes |

### Key Metrics to Monitor

| Metric | Warning Threshold | Critical Threshold |
|---|---|---|
| Error rate (5xx) | > 1% | > 5% |
| p95 latency (classification) | > 15 seconds | > 30 seconds |
| AI API daily spend | > 80% of budget | > 95% of budget |
| Circuit breaker state | HALF_OPEN | OPEN |
| S3 upload failures | > 3 in 15 min | > 10 in 15 min |
| Document integrity tamper detected | Any occurrence | -- |
| SLA breach count (hourly) | > 5 | > 20 |

### Alert Escalation

| Severity | Response Time | Contact |
|---|---|---|
| Critical (unhealthy, data integrity, circuit breaker OPEN) | 15 minutes | On-call engineer |
| Warning (degraded, SLA warnings, elevated error rate) | 1 hour | Engineering team |
| Info (high AI spend, expiring documents) | Next business day | Product team |

---

## Troubleshooting Guide

### AI Classification Not Working

**Symptoms:** Document uploads succeed but classification returns null or fallback types.

**Check:**
1. Verify `ANTHROPIC_API_KEY` is set and valid:
   ```bash
   curl https://api.anthropic.com/v1/messages \
     -H "x-api-key: $ANTHROPIC_API_KEY" \
     -H "anthropic-version: 2023-06-01" \
     -H "content-type: application/json" \
     -d '{"model":"claude-sonnet-4-20250514","max_tokens":10,"messages":[{"role":"user","content":"test"}]}'
   ```
2. Check circuit breaker status:
   ```bash
   curl https://api.perenniaai.com/api/smart-docs/monitoring/errors?hours=1 \
     -H "Authorization: Bearer <admin_token>"
   ```
   If circuit is OPEN: wait for `cb_recovery_timeout` (60s default) to reset to HALF_OPEN.
3. Check Railway logs for `ai_resilience` or `circuit_breaker` entries.
4. Verify the model name in `ANTHROPIC_MODEL` is valid and accessible.

**Resolution:** If API key is invalid, rotate in Railway env vars and redeploy. If circuit breaker is stuck, restart the Railway service to reset in-memory state.

### E-Signature Tokens Failing

**Symptoms:** Borrowers clicking signing links get 401/403 errors.

**Check:**
1. Verify `ESIGN_SIGNING_SECRET` matches what was used to create the envelope:
   ```bash
   # In Railway console, check the first 8 chars match what is expected
   echo $ESIGN_SIGNING_SECRET | head -c 8
   ```
2. Verify `ESIGN_TOKEN_SECRET` is set (used for short-lived JWT access tokens).
3. Check if the signing token has expired (tokens have `signing_token_expires_at`).
4. Check the esignature_audit_events table for the specific envelope.

**Resolution:** If secrets were rotated, all active envelopes signed with the old secret are invalidated. You must void and re-create affected envelopes. NEVER rotate `ESIGN_SIGNING_SECRET` without a planned migration.

### Upload Failures

**Symptoms:** Document uploads return 500 errors or timeouts.

**Check:**
1. S3 connectivity:
   ```bash
   # From Railway console
   python -c "import boto3; s3 = boto3.client('s3'); print(s3.list_buckets())"
   ```
2. Verify bucket name: `SMART_DOCS_S3_BUCKET` or `PERENNIA_S3_BUCKET`.
3. Check IAM permissions: the IAM user/role needs `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject` on the bucket.
4. Check file size: default max is controlled by FastAPI's request body limit and any nginx/Railway proxy limits.
5. Check Railway logs for `ClientError` or `NoCredentialsError` from boto3.

**Resolution:** Fix IAM permissions or credentials. If S3 is down, the service degrades gracefully -- uploads fail but the rest of Smart Docs continues to function.

### S3 CORS Configuration

The S3 bucket needs CORS configured for presigned URL downloads from the frontend:
```json
[
    {
        "AllowedHeaders": ["*"],
        "AllowedMethods": ["GET", "PUT"],
        "AllowedOrigins": [
            "https://app.perenniaai.com",
            "https://api.perenniaai.com"
        ],
        "ExposeHeaders": ["ETag"],
        "MaxAgeSeconds": 3600
    }
]
```

### Tenant Isolation Issues

**Symptoms:** Users seeing documents from other organizations, or "No organization context" errors.

**Check:**
1. Verify the tenant isolation migration ran:
   ```sql
   SELECT column_name FROM information_schema.columns
   WHERE table_name = 'document_followup_events' AND column_name = 'organization_id';
   ```
2. Check for rows with `organization_id = 0` (sentinel value for orphaned records):
   ```sql
   SELECT COUNT(*) FROM document_followup_events WHERE organization_id = 0;
   SELECT COUNT(*) FROM document_integrity_checks WHERE organization_id = 0;
   SELECT COUNT(*) FROM document_watermark_logs WHERE organization_id = 0;
   ```
3. Verify the user's JWT includes `organization_id`.

**Resolution:** If orphaned rows exist, run the backfill queries from `smart_docs_v2_tenant_isolation.py` manually. If the migration has not run, execute it:
```bash
python -m migrations.smart_docs_v2_tenant_isolation
```

### Performance Degradation

**Symptoms:** Slow response times, timeouts on classification or income calculation.

**Check:**
1. Database query performance:
   ```sql
   -- Check for missing indexes
   SELECT schemaname, tablename, indexname FROM pg_indexes
   WHERE tablename LIKE '%smart_doc%' OR tablename LIKE '%esign%';

   -- Check table sizes
   SELECT relname, n_live_tup FROM pg_stat_user_tables
   WHERE relname LIKE '%smart_doc%' OR relname LIKE '%esign%'
   ORDER BY n_live_tup DESC;
   ```
2. AI latency: check `/monitoring/metrics` for p95 latency by operation.
3. Document processing cache hit rate:
   ```sql
   SELECT processing_type, COUNT(*) as entries, SUM(hit_count) as total_hits
   FROM document_processing_cache GROUP BY processing_type;
   ```
4. Railway resource utilization (CPU, memory) via Railway dashboard.
5. Database connection pool: Railway has ~20 connection limit. Check for connection exhaustion.

**Resolution:**
- If AI is slow: check Anthropic status page. Consider increasing `timeout_seconds` in `AICallConfig`.
- If DB is slow: check for long-running queries (`pg_stat_activity`), consider adding indexes.
- If cache is cold: the cache populates over time. High cache miss rates are expected after fresh deployment.
- If connections exhausted: check `db.py` pool settings (pool_size=5, max_overflow=10).

### PII Encryption Issues

**Symptoms:** Encrypted columns contain null while plaintext columns have data, or decryption errors.

**Check:**
1. Verify `PII_ENCRYPTION_KEY` is set and matches what was used to encrypt:
   ```bash
   echo $PII_ENCRYPTION_KEY | head -c 8
   ```
2. Check `pii_encrypted_at` column for migration progress:
   ```sql
   SELECT
     COUNT(*) as total,
     COUNT(pii_encrypted_at) as encrypted,
     COUNT(*) - COUNT(pii_encrypted_at) as pending
   FROM smart_documents WHERE ocr_text IS NOT NULL;
   ```

**Resolution:** If encryption key was lost or rotated, encrypted data is unrecoverable. The plaintext columns are preserved during the transition period -- do not drop them until encryption is verified. Re-run the backfill with the correct key:
```bash
PII_ENCRYPTION_KEY=<correct_key> python -m migrations.smart_docs_pii_encryption
```

### Route Registration Failures

**Symptoms:** Specific Smart Docs endpoints return 404, but others work.

**Check:**
1. Search Railway startup logs for `Failed to register` warnings.
2. Each module is independently wrapped in try/except. A single module failure does not block others.
3. Common causes:
   - Missing Python dependency (e.g., `plaid-python` for Plaid routes)
   - Import error in a service file
   - Database model import failure

**Resolution:** Fix the underlying import error. The module will register on next restart. Missing optional dependencies (Plaid, AUS) can be safely ignored if those features are not in use.

---

## Architecture Quick Reference

### Route Modules (registered via `smart_docs_v2_registration.py`)

| Module | Prefix | Auth Required |
|---|---|---|
| E-Signature | `/api/v1/esign/*` | Yes (envelope mgmt) / Token-based (signing) |
| Document Intelligence | `/api/smart-docs/doc-intel/*` | Yes |
| Income Calculation | `/api/smart-docs/income/*` | Yes |
| Follow-up Automation | `/api/smart-docs/followup/*` | Yes |
| Document Security | `/api/smart-docs/doc-security/*` | Yes |
| Document Review | `/api/smart-docs/doc-review/*` | Yes |
| Bank Statement Analysis | `/api/smart-docs/bank-analysis/*` | Yes |
| Document Analytics | `/api/smart-docs/doc-analytics/*` | Yes |
| Borrower Portal | `/api/smart-docs/portal/*` | Token-based (magic link) |
| Borrower Portal V2 | `/api/smart-docs/portal/v2/*` | Token-based (magic link) |
| Business Rules Config | `/api/smart-docs/config/*` | Yes (admin for writes) |
| eClosing | `/api/smart-docs/eclosing/*` | Yes |
| Plaid | `/api/smart-docs/plaid/*` | Yes |
| AUS | `/api/smart-docs/aus/*` | Yes |
| MISMO | `/api/smart-docs/mismo/*` | Yes |
| Monitoring | `/api/smart-docs/monitoring/*` | No (health) / Yes (admin for others) |
| IRS Transcript | `/api/smart-docs/transcript/*` | Yes |
| AI Benchmark | `/api/smart-docs/benchmark/*` | Yes (admin) |

### Middleware Stack (in execution order)

1. **TraceIDMiddleware** -- propagates `X-Trace-ID` header across requests
2. **SmartDocsMetricsMiddleware** -- per-request latency + error counters for `/api/smart-docs/*`
3. **PII Log Filter** -- strips SSN, credit card, DOB patterns from all log output

### Key Service Files

| Service | Path | Purpose |
|---|---|---|
| AI Resilience | `services/smart_docs/ai_resilience.py` | Circuit breaker + retry for Anthropic API |
| S3 Storage | `services/smart_docs/s3_storage_service.py` | Document upload/download |
| E-Sign Crypto | `services/smart_docs/esignature_crypto_service.py` | HMAC signing + token generation |
| E-Sign Key Manager | `services/smart_docs/esignature_key_manager.py` | Key lifecycle management |
| PII Encryption | `services/smart_docs/pii_encryption_service.py` | AES encryption for PII fields |
| Monitoring | `services/smart_docs/monitoring_service.py` | Health, metrics, SLA, cost reporting |
| Malware Scanner | `services/smart_docs/malware_scanner_service.py` | ClamAV + signature-based file scanning |
| Follow-up Automation | `services/smart_docs/followup_automation_service.py` | Campaign execution engine |
| Business Rules | `services/smart_docs/business_rules_service.py` | Configurable threshold management |
