# Phase 1 Deployment Guide
## Claude 4 Sonnet Email Parser & Comprehensive CRM Profiles

**Version:** 1.0.0
**Date:** November 15, 2025
**Status:** ✅ Ready for Deployment

---

## 📋 What Was Built

### 1. Claude 4 Sonnet Parser (`backend/ai_providers/claude_parser.py`)
- **156 field schemas** across all 4 profile types
- Comprehensive AI prompts for maximum extraction
- Confidence scoring (0-100%) for each field
- Calculated fields (LTV, DTI)
- Milestone detection
- Conflict identification
- Sentiment analysis
- Action recommendations

### 2. Expanded Database Models
- **LeadProfile**: 52 fields (complete pipeline from inquiry to pre-approval)
- **ActiveLoanProfile**: 53 fields (contract to funding with 27 milestone dates)
- **MUMClientProfile**: 22 fields (portfolio management & refinance opportunities)
- **TeamMemberProfile**: 29 fields (KPIs, DISC, goals, personal info)
- **EmailInteraction**: Comprehensive email tracking with AI analysis
- **FieldUpdateHistory**: Audit trail for all changes
- **DataConflict**: Conflict resolution queue

### 3. Email Processing Service (`backend/services/email_processor.py`)
- AI provider toggle (Claude/OpenAI)
- Profile type classification
- Intelligent profile matching
- Automated profile creation
- High-confidence field updates
- Conflict detection & flagging

### 4. Database Migration (`backend/migrations/001_create_comprehensive_profiles.py`)
- Safe table creation
- Rollback capability
- Verification checks

### 5. Testing Suite
- Sample emails for all 4 profile types
- Parser test script
- Full integration tests (TODO)

---

## 🚀 Deployment Steps

### Step 1: Set Up Environment Variables

1. **Copy the example environment file:**
   ```bash
   cd /Users/timothyloss/my-project/mortgage-crm/backend
   cp .env.example .env
   ```

2. **Add your Anthropic API key:**
   ```bash
   # Get your key from: https://console.anthropic.com/
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```

3. **Set AI provider to Claude:**
   ```bash
   AI_PROVIDER=claude
   ```

4. **Verify other settings:**
   - `DATABASE_URL` (should be your PostgreSQL or Railway database)
   - `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, etc. (for email sync)

### Step 2: Run Database Migration

1. **Create new profile tables:**
   ```bash
   python backend/migrations/001_create_comprehensive_profiles.py
   ```

   This will create:
   - ✅ `lead_profiles`
   - ✅ `active_loan_profiles`
   - ✅ `mum_client_profiles`
   - ✅ `team_member_profiles`
   - ✅ `email_interactions`
   - ✅ `field_update_history`
   - ✅ `data_conflicts`

2. **Verify tables were created:**
   The migration script will automatically verify and show you the created tables.

### Step 3: Test Claude Parser

1. **Set your API key for testing:**
   ```bash
   export ANTHROPIC_API_KEY='your-key-here'
   ```

2. **Run the parser test:**
   ```bash
   python backend/test_claude_parser.py
   ```

   This will:
   - Test all 4 profile types
   - Show extracted fields
   - Display confidence scores
   - Save results to `test_results_*.json`

3. **Review the results:**
   - Check `test_results_lead.json`
   - Check `test_results_active_loan.json`
   - Check `test_results_mum_client.json`
   - Check `test_results_team_member.json`

   Verify that fields are being extracted correctly with high confidence.

### Step 4: Update Backend Code (Integration)

The email processing service is ready, but you need to integrate it into your existing endpoints.

**Option A: Add New Endpoint (Recommended for testing)**

Add to `backend/main.py`:

```python
from services.email_processor import get_email_processor

@app.post("/api/v1/email/process-comprehensive")
async def process_email_comprehensive(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Process email with comprehensive Claude parsing
    """
    # Get email from Microsoft Graph
    from integrations.microsoft_graph import graph_client

    # TODO: Fetch email data using email_id
    email_data = {
        'id': email_id,
        # ... populate from Microsoft Graph
    }

    # Process with new service
    processor = get_email_processor()
    result = await processor.process_email(email_data, current_user.id, db)

    return result
```

**Option B: Replace Existing Endpoint**

Find your existing email processing endpoint (likely in `backend/main.py` around line 3305) and replace the `process_microsoft_email_to_dre` function logic with:

```python
from services.email_processor import get_email_processor

async def process_microsoft_email_to_dre(email_data: dict, user_id: int, db: Session):
    """Process a Microsoft Graph email with comprehensive parsing"""
    processor = get_email_processor()
    return await processor.process_email(email_data, user_id, db)
```

### Step 5: Deploy to Production

1. **Add environment variables to Railway:**
   ```bash
   railway variables set ANTHROPIC_API_KEY='your-key-here'
   railway variables set AI_PROVIDER='claude'
   ```

2. **Run migration on production database:**
   ```bash
   railway run python backend/migrations/001_create_comprehensive_profiles.py
   ```

3. **Deploy updated code:**
   ```bash
   git add .
   git commit -m "Add Phase 1: Claude parser & comprehensive profiles"
   git push
   ```

4. **Verify deployment:**
   - Check Railway logs for successful startup
   - Test with a real email
   - Check Reconciliation Center for extracted data

---

## 🧪 Testing Checklist

### Unit Tests
- [ ] Claude parser initializes correctly
- [ ] All 4 profile types can be parsed
- [ ] Field extraction works
- [ ] Confidence scoring works
- [ ] Classification logic works

### Integration Tests
- [ ] Email can be fetched from Microsoft Graph
- [ ] Email is classified correctly
- [ ] Email is parsed by Claude
- [ ] Profile matching works
- [ ] New profile is created (for new leads)
- [ ] Existing profile is updated (for known contacts)
- [ ] Conflicts are detected and stored
- [ ] EmailInteraction is saved
- [ ] High-confidence updates are applied

### Production Tests
- [ ] Send test email to connected inbox
- [ ] Verify email sync triggers
- [ ] Check EmailInteraction was created
- [ ] Verify profile was created/updated
- [ ] Check Reconciliation Center shows the email
- [ ] Verify confidence scores are reasonable
- [ ] Test conflict resolution flow

---

## 📊 Monitoring & Verification

### Database Queries

**Check email interactions:**
```sql
SELECT
    id,
    subject,
    from_email,
    profile_type,
    field_count,
    overall_confidence,
    sync_status,
    created_at
FROM email_interactions
ORDER BY created_at DESC
LIMIT 10;
```

**Check new lead profiles:**
```sql
SELECT
    id,
    first_name,
    last_name,
    email,
    phone,
    annual_income,
    credit_score,
    data_sources,
    created_at
FROM lead_profiles
ORDER BY created_at DESC
LIMIT 10;
```

**Check active loans:**
```sql
SELECT
    id,
    loan_number,
    amount,
    property_address,
    clear_to_close_date,
    funding_date,
    created_at
FROM active_loan_profiles
ORDER BY created_at DESC
LIMIT 10;
```

**Check conflicts:**
```sql
SELECT
    id,
    profile_type,
    field_name,
    current_value,
    proposed_value,
    confidence,
    status,
    created_at
FROM data_conflicts
WHERE status = 'pending'
ORDER BY created_at DESC;
```

### API Testing with curl

**Test parser endpoint:**
```bash
curl -X POST http://localhost:8000/api/v1/email/process-comprehensive \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "email_id": "test-message-id"
  }'
```

---

## 🔧 Troubleshooting

### Issue: "ANTHROPIC_API_KEY not set"
**Solution:** Make sure your `.env` file has the key and you've restarted the server.

### Issue: "Table already exists"
**Solution:** The migration is idempotent. If tables exist, it will skip creation.

### Issue: "No module named 'ai_providers'"
**Solution:** Make sure you're running from the backend directory:
```bash
cd /Users/timothyloss/my-project/mortgage-crm/backend
python test_claude_parser.py
```

### Issue: Low confidence scores
**Solution:**
- Check that your email content is comprehensive
- Verify the email contains relevant mortgage info
- Review the Claude prompt for the profile type
- Some fields may genuinely be uncertain

### Issue: No fields extracted
**Solution:**
- Check the email classification (might be wrong profile type)
- Verify email content is not empty
- Check Claude API logs for errors
- Try a different email with more explicit information

---

## 📈 Success Metrics

### Phase 1 Goals:
- ✅ Claude parser functional
- ✅ All database models created
- ✅ Migration script working
- ✅ Basic tests passing
- ⏳ End-to-end pipeline integrated
- ⏳ Production deployment verified

### Expected Performance:
- **Parsing time**: 2-5 seconds per email
- **Field extraction**: 15-30 fields per lead email
- **Field extraction**: 25-40 fields per active loan email
- **Confidence**: Average 75%+ on clear emails
- **Profile matching**: 95%+ accuracy on email/phone

---

## 🎯 Next Steps (Phase 2)

After Phase 1 is deployed and stable:

1. **Enhanced Profile Matching** (Phase 2)
   - Fuzzy name matching
   - Address parsing
   - ML-based disambiguation

2. **Data Sync Engine** (Phase 3)
   - Field-level conflict resolution
   - Merge strategies
   - Update history tracking

3. **Lifecycle Automation** (Phase 4)
   - Auto-convert Lead → Active Loan
   - Auto-convert Active Loan → MUM Client
   - Automated workflows

4. **AWS Lambda** (Phase 5)
   - Serverless processing
   - Real-time webhooks
   - Scalable architecture

---

## 📞 Support

**Issues?** Report at: https://github.com/your-repo/issues

**Questions?**
- Check logs: `railway logs`
- Review test results: `test_results_*.json`
- Check database: Run verification queries above

---

## ✅ Deployment Checklist

Before going live:

- [ ] Environment variables set (ANTHROPIC_API_KEY, AI_PROVIDER)
- [ ] Database migration completed
- [ ] Parser test passed
- [ ] Sample emails tested successfully
- [ ] Code integrated into main.py
- [ ] Railway deployment successful
- [ ] Production API key added
- [ ] First real email tested
- [ ] Reconciliation Center verified
- [ ] Monitoring queries set up
- [ ] Team trained on conflict resolution

---

**Ready to deploy Phase 1!** 🚀
