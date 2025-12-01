# Email Identity Resolution System - Quick Start Guide

**Time to deploy: ~15 minutes**

---

## Prerequisites

- PostgreSQL 12+
- Python 3.9+
- Access to your backend deployment

---

## Step 1: Run Database Migration (5 min)

```bash
cd backend

# Option A: Run the migration script
python run_email_identity_migration.py

# Option B: Run SQL directly
psql $DATABASE_URL -f migrations/add_email_identity_resolution.sql
```

**Verify migration succeeded:**
```sql
-- Check tables exist
SELECT COUNT(*) FROM known_client_emails;
SELECT COUNT(*) FROM email_identity_resolution_log;

-- Check new columns
SELECT match_evidence, match_client_name, is_priority
FROM email_reconciliation_queue LIMIT 1;
```

---

## Step 2: Deploy Backend (3 min)

```bash
# If using Railway
git add .
git commit -m "Add email identity resolution system"
git push origin main
railway up

# If using other platform, deploy as usual
```

---

## Step 3: Sync Known Clients (2 min)

Populate the lookup table from existing CRM data:

```bash
# Get a token first
TOKEN=$(curl -s -X POST "https://your-api/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your@email.com&password=yourpass" | jq -r '.access_token')

# Sync known clients
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

---

## Step 4: Verify It's Working (3 min)

### Test email resolution:
```bash
curl -X POST "https://your-api/api/v1/email-intelligence/import-email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "from_email": "john.smith@gmail.com",
    "subject": "Question about loan #12345678",
    "body_preview": "Hi, I have a question about my application..."
  }'
```

**Expected response (if matched):**
```json
{
  "status": "queued",
  "email_id": 123,
  "match": {
    "contact_id": null,
    "loan_id": 456,
    "lead_id": null,
    "client_name": "John Smith",
    "loan_number": "12345678",
    "method": "loan_number_subject",
    "confidence": 0.8,
    "is_priority": false
  }
}
```

### Check stats:
```bash
curl "https://your-api/api/v1/email-intelligence/stats?days=7" \
  -H "Authorization: Bearer $TOKEN"
```

**Look for `identity_resolution` in response:**
```json
{
  "identity_resolution": {
    "total_emails": 100,
    "matched": 75,
    "match_rate": 75.0,
    "by_method": {
      "known_client_email": 40,
      "lead_email_match": 20,
      "loan_email_match": 10,
      "thread_continuity": 5
    }
  }
}
```

---

## Step 5: Test Each Match Strategy (2 min)

### Known Client (1.0 confidence):
```bash
# Email from someone in known_client_emails table
curl -X POST "https://your-api/api/v1/email-intelligence/import-email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"from_email": "known.client@example.com", "subject": "Test"}'
```

### Loan Number in Subject (0.8 confidence):
```bash
curl -X POST "https://your-api/api/v1/email-intelligence/import-email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"from_email": "unknown@example.com", "subject": "RE: Loan #12345678 Documents"}'
```

### Vendor Domain (0.9-0.95 confidence):
```bash
curl -X POST "https://your-api/api/v1/email-intelligence/import-email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"from_email": "appraiser@fanniemae.com", "subject": "Appraisal Complete"}'
```

---

## Quick Command Reference

| Task | Command |
|------|---------|
| Run migration | `python run_email_identity_migration.py` |
| Sync known clients | `POST /api/v1/email-intelligence/sync-known-clients` |
| Import email | `POST /api/v1/email-intelligence/import-email` |
| Check stats | `GET /api/v1/email-intelligence/stats` |
| View priority emails | `SELECT * FROM v_priority_emails` |
| View match stats | `SELECT * FROM v_email_match_stats` |

---

## Common Issues & Fixes

### "known_client_emails table doesn't exist"
```bash
python run_email_identity_migration.py
```

### "No matches found for any emails"
```bash
# 1. Check known_client_emails has data
SELECT COUNT(*) FROM known_client_emails;

# 2. If empty, sync from CRM
POST /api/v1/email-intelligence/sync-known-clients

# 3. Check leads/loans have emails
SELECT COUNT(*) FROM leads WHERE email IS NOT NULL;
SELECT COUNT(*) FROM loans WHERE borrower_email IS NOT NULL;
```

### "Low match rate (<50%)"
1. Ensure known_client_emails is populated
2. Check that lead/loan emails match incoming sender addresses
3. Review unmatched emails for patterns

### "Migration failed"
```bash
# Check PostgreSQL logs
# Common fixes:
# - Ensure email_reconciliation_queue table exists
# - Check foreign key references (users, contacts, leads, loans)
```

---

## Success Metrics

After deployment, you should see:

| Metric | Target | How to Check |
|--------|--------|--------------|
| Migration complete | All tables exist | `\dt` in psql |
| Known clients synced | >0 records | `SELECT COUNT(*) FROM known_client_emails` |
| Match rate | >50% first day | `/api/v1/email-intelligence/stats` |
| Priority detection | Working | Check `is_priority` on matched emails |
| Response time | <100ms | Monitor API response times |

---

## Next Steps

1. **Monitor** match rates for first 24-48 hours
2. **Review** unmatched emails to identify patterns
3. **Add** missing domains to KNOWN_VENDOR_DOMAINS if needed
4. **Build** UI dashboard (see `EMAIL_IDENTITY_INTEGRATION.md`)
5. **Set up** alerts for low match rates (see `email_identity_analytics.py`)

---

## Need More Help?

- Full documentation: `README_EMAIL_IDENTITY.md`
- Integration guide: `EMAIL_IDENTITY_INTEGRATION.md`
- Production checklist: `DEPLOYMENT_CHECKLIST.md`
- System overview: `SYSTEM_SUMMARY.md`

---

**Total time: ~15 minutes**

You now have email identity resolution running!
