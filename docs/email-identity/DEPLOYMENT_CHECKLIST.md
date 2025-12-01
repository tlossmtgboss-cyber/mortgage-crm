# Email Identity Resolution - Production Deployment Checklist

## Pre-Deployment Checklist

### Database Prerequisites
- [ ] PostgreSQL 12+ running
- [ ] Database backup completed
- [ ] Sufficient disk space for new tables/indexes (~100MB)
- [ ] `email_reconciliation_queue` table exists
- [ ] `users`, `contacts`, `leads`, `loans` tables exist with proper FKs

### Code Prerequisites
- [ ] `email_identity_resolver.py` in `backend/services/`
- [ ] `add_email_identity_resolution.sql` in `backend/migrations/`
- [ ] `run_email_identity_migration.py` in `backend/`
- [ ] Updated `email_intelligence_routes.py` deployed

### Environment
- [ ] Test environment validated
- [ ] Staging deployment successful (if applicable)
- [ ] Rollback procedure documented and tested

---

## Phase 1: Database Migration (15 min)

### Step 1.1: Backup Database
```bash
# Create backup before migration
pg_dump $DATABASE_URL > backup_pre_email_identity_$(date +%Y%m%d_%H%M%S).sql

# Verify backup
ls -la backup_pre_email_identity_*.sql
```
- [ ] Backup created
- [ ] Backup file size > 0

### Step 1.2: Run Migration
```bash
cd backend

# Option A: Python script (recommended)
python run_email_identity_migration.py

# Option B: Direct SQL
psql $DATABASE_URL -f migrations/add_email_identity_resolution.sql
```
- [ ] Migration completed without errors

### Step 1.3: Verify Migration
```sql
-- Check new tables
SELECT COUNT(*) FROM known_client_emails;  -- Should return 0
SELECT COUNT(*) FROM email_identity_resolution_log;  -- Should return 0

-- Check new columns on email_reconciliation_queue
SELECT column_name FROM information_schema.columns
WHERE table_name = 'email_reconciliation_queue'
AND column_name IN ('match_evidence', 'match_client_name', 'match_loan_number', 'is_priority');
-- Should return 4 rows

-- Check coborrower_email on loans
SELECT column_name FROM information_schema.columns
WHERE table_name = 'loans' AND column_name = 'coborrower_email';
-- Should return 1 row

-- Check indexes created
SELECT indexname FROM pg_indexes
WHERE indexname LIKE 'idx_email%' OR indexname LIKE 'idx_known%' OR indexname LIKE 'idx_loans%';
-- Should return 10+ indexes

-- Check views
SELECT * FROM v_priority_emails LIMIT 1;  -- Should not error
SELECT * FROM v_email_match_stats LIMIT 1;  -- Should not error

-- Check functions
SELECT sync_entity_emails(1, 'lead', 1);  -- Should not error (returns 0 or 1)
```
- [ ] All 4 new columns exist on email_reconciliation_queue
- [ ] coborrower_email column exists on loans
- [ ] known_client_emails table created
- [ ] email_identity_resolution_log table created
- [ ] All indexes created
- [ ] Views accessible
- [ ] Functions working

---

## Phase 2: Backend Deployment (10 min)

### Step 2.1: Deploy Code
```bash
# Railway
git add .
git commit -m "Deploy email identity resolution system"
git push origin main
railway up

# Or your deployment method
```
- [ ] Code deployed successfully
- [ ] No deployment errors

### Step 2.2: Verify Backend Health
```bash
# Health check
curl https://your-api/health

# Check logs for startup
railway logs | grep -i "email"
```
- [ ] Backend responding
- [ ] No startup errors related to email identity

### Step 2.3: Verify Routes Available
```bash
TOKEN="your-auth-token"

# Check stats endpoint
curl -s "https://your-api/api/v1/email-intelligence/stats" \
  -H "Authorization: Bearer $TOKEN" | jq '.identity_resolution'

# Should see identity_resolution section in response
```
- [ ] Stats endpoint returns identity_resolution data

---

## Phase 3: Data Initialization (10 min)

### Step 3.1: Sync Known Clients
```bash
TOKEN="your-auth-token"

curl -X POST "https://your-api/api/v1/email-intelligence/sync-known-clients" \
  -H "Authorization: Bearer $TOKEN"
```

**Expected response:**
```json
{
  "status": "success",
  "emails_synced": 150
}
```
- [ ] Sync completed
- [ ] Record count > 0

### Step 3.2: Verify Known Clients Table
```sql
-- Check record count
SELECT COUNT(*) FROM known_client_emails;

-- Check distribution by source
SELECT source_type, COUNT(*)
FROM known_client_emails
GROUP BY source_type;

-- Sample records
SELECT email_address, client_name, source_type
FROM known_client_emails
LIMIT 5;
```
- [ ] Records populated from leads
- [ ] Records populated from loans
- [ ] Records populated from contacts (if applicable)

### Step 3.3: Update Existing Queue (Optional)
If you have existing unmatched emails, re-process them:
```sql
-- Count unmatched emails
SELECT COUNT(*) FROM email_reconciliation_queue
WHERE match_method IS NULL;

-- Option: Mark for reprocessing (if you have a reprocess mechanism)
UPDATE email_reconciliation_queue
SET status = 'pending_rematch'
WHERE match_method IS NULL AND status = 'pending';
```
- [ ] Decision made on existing emails

---

## Phase 4: Validation (15 min)

### Step 4.1: Test Known Client Match
```bash
# Get a known email from your database
KNOWN_EMAIL=$(psql $DATABASE_URL -t -c "SELECT email_address FROM known_client_emails LIMIT 1" | tr -d ' ')

# Test import
curl -X POST "https://your-api/api/v1/email-intelligence/import-email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"from_email\": \"$KNOWN_EMAIL\", \"subject\": \"Test\"}"
```

**Expected**: Match with method `known_client_email`, confidence `1.0`, `is_priority: true`
- [ ] Known client matching works

### Step 4.2: Test Loan Number Extraction
```bash
# Get a loan number from your database
LOAN_NUM=$(psql $DATABASE_URL -t -c "SELECT loan_number FROM loans WHERE loan_number IS NOT NULL LIMIT 1" | tr -d ' ')

curl -X POST "https://your-api/api/v1/email-intelligence/import-email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"from_email\": \"unknown@test.com\", \"subject\": \"RE: Loan #$LOAN_NUM documents\"}"
```

**Expected**: Match with method `loan_number_subject`, confidence `0.8`
- [ ] Loan number extraction works

### Step 4.3: Test Vendor Domain Match
```bash
curl -X POST "https://your-api/api/v1/email-intelligence/import-email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"from_email": "appraiser@fanniemae.com", "subject": "Appraisal Complete"}'
```

**Expected**: Match with method `domain_vendor_match`, confidence `0.95`
- [ ] Vendor domain matching works

### Step 4.4: Test Thread Continuity
```bash
# Create first email in thread
RESULT=$(curl -s -X POST "https://your-api/api/v1/email-intelligence/import-email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"from_email": "known@client.com", "subject": "Question", "thread_id": "test-thread-123"}')

# Create second email in same thread from unknown sender
curl -X POST "https://your-api/api/v1/email-intelligence/import-email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"from_email": "unknown@different.com", "subject": "RE: Question", "thread_id": "test-thread-123"}'
```

**Expected**: Second email inherits match from first via thread_continuity
- [ ] Thread continuity works

### Step 4.5: Check Stats
```bash
curl -s "https://your-api/api/v1/email-intelligence/stats?days=1" \
  -H "Authorization: Bearer $TOKEN" | jq '.identity_resolution'
```

**Expected**:
```json
{
  "total_emails": 4,
  "matched": 4,
  "match_rate": 100.0,
  "by_method": {
    "known_client_email": 1,
    "loan_number_subject": 1,
    "domain_vendor_match": 1,
    "thread_continuity": 1
  }
}
```
- [ ] Stats showing correct data

---

## Post-Deployment Tasks

### Monitoring Setup
- [ ] Set up alert for match_rate < 50%
- [ ] Set up alert for known_client_emails sync failures
- [ ] Add identity_resolution to existing dashboards

### Documentation
- [ ] Update API documentation with new response fields
- [ ] Update internal wiki/runbooks
- [ ] Notify team of new feature

### Cleanup (After 1 Week)
- [ ] Remove test emails created during validation
- [ ] Review and archive old backups
- [ ] Verify no performance degradation

---

## Rollback Procedure

If issues are found, rollback in reverse order:

### Step 1: Revert Code
```bash
git revert HEAD
git push origin main
railway up
```

### Step 2: Revert Database (if needed)
```sql
-- Run the rollback script from the migration file
BEGIN;

DROP VIEW IF EXISTS v_priority_emails;
DROP VIEW IF EXISTS v_email_match_stats;
DROP FUNCTION IF EXISTS get_client_emails(INTEGER, INTEGER, INTEGER, INTEGER);
DROP FUNCTION IF EXISTS sync_entity_emails(INTEGER, VARCHAR, INTEGER);
DROP TABLE IF EXISTS email_identity_resolution_log;

ALTER TABLE email_reconciliation_queue
DROP COLUMN IF EXISTS match_evidence,
DROP COLUMN IF EXISTS match_client_name,
DROP COLUMN IF EXISTS match_loan_number;

-- Keep known_client_emails if it has valuable data
-- DROP TABLE IF EXISTS known_client_emails;

COMMIT;
```

### Step 3: Restore from Backup (nuclear option)
```bash
psql $DATABASE_URL < backup_pre_email_identity_YYYYMMDD_HHMMSS.sql
```

---

## Performance Benchmarks

After deployment, verify these metrics:

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Single email resolution | <100ms | API response time |
| Stats endpoint | <500ms | API response time |
| Known client lookup | <5ms | Database query time |
| Sync known clients | <30s for 1000 records | Endpoint response time |

```sql
-- Check query performance
EXPLAIN ANALYZE SELECT * FROM known_client_emails
WHERE email_address = 'test@example.com' AND user_id = 1;
-- Should show Index Scan, <1ms execution
```

---

## Troubleshooting Guide

### "Migration failed: relation does not exist"
**Cause**: Required tables missing
**Fix**: Ensure email_reconciliation_queue and other base tables exist

### "No matches found for any emails"
**Cause**: known_client_emails empty
**Fix**: Run sync-known-clients endpoint

### "Slow performance after deployment"
**Cause**: Indexes not created
**Fix**: Re-run migration or manually create indexes

### "is_priority always false"
**Cause**: Only known_client_email matches set priority
**Fix**: This is expected behavior - verify known clients are synced

### "Thread continuity not working"
**Cause**: thread_id not being passed in email data
**Fix**: Ensure email sync includes thread_id/conversationId

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |
| DBA | | | |
| QA | | | |
| DevOps | | | |
| Product Owner | | | |

---

## Post-Deployment Monitoring Schedule

| Check | Frequency | Owner |
|-------|-----------|-------|
| Match rate | Daily (first week), Weekly (after) | |
| Error logs | Daily (first week), Weekly (after) | |
| Performance metrics | Daily (first week), Weekly (after) | |
| Known clients sync | Weekly | |
| Storage usage | Monthly | |

---

**Deployment Version**: 1.0
**Estimated Total Time**: 50-60 minutes
**Risk Level**: Low (additive changes only)
