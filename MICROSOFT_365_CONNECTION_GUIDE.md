# 📧 Microsoft 365 Connection Guide

## Quick Setup (3 Steps)

### Step 1: Navigate to Settings
```
https://mortgage-crm-production-7a9a.up.railway.app/settings
```

### Step 2: Connect Microsoft 365

1. **Click on "Integrations"** in the sidebar (🔌)
2. **Find "Outlook Email"** integration card
3. **Click on the card** to initiate connection
4. **Microsoft login popup will appear**
5. **Sign in** with your Microsoft 365 account
6. **Grant permissions** when prompted:
   - Mail.Read
   - Mail.ReadWrite
   - Mail.Send
   - User.Read
   - Contacts.Read
7. **Popup will close automatically** after successful authorization

### Step 3: Verify Connection

After connecting, you should see:
- ✅ "Microsoft 365 Connected" status panel
- Your email address displayed
- "Sync Now" button available
- Last sync timestamp

---

## Test Email Sync

### Manual Test (Reconciliation Center)

1. Navigate to **Reconciliation** page
2. Click **"Sync Emails Now"** button (purple gradient button)
3. Watch for status message:
   - ✓ "Synced X emails successfully" (green)
   - Or error message if something fails

### Automatic Sync

Once connected, emails will automatically sync **every 5 minutes**:
- Runs silently in background
- Updates reconciliation queue automatically
- No user action needed

---

## What Happens After Sync

### 1. Email Processing Flow
```
Microsoft Inbox
    ↓
Sync to CRM (every 5 min)
    ↓
AI Email Processor Agent
    ↓
Data Extraction (loan info, dates, status)
    ↓
Reconciliation Queue (if confidence < 95%)
    ↓
Bulk Approval (up to 20 items)
    ↓
Loan Files Updated
```

### 2. Reconciliation Items Created

You'll see pending items for:
- **Loan status updates** (approved, suspended, processing, funded)
- **Date changes** (closing date, appraisal date, condition due dates)
- **Amount changes** (loan amount, purchase price)
- **Document notices** (missing docs, received docs)
- **Borrower information** (name, email, phone updates)

### 3. AI Enhancements

Email Processor Agent automatically:
- ✅ Updates loan status based on keywords
- ✅ Tracks critical dates (closing, appraisal, conditions)
- ✅ Creates reconciliation tasks for low-confidence items
- ✅ Flags missing documents
- ✅ Maintains complete audit trail

---

## Troubleshooting

### Issue: "Microsoft 365 not connected"

**Cause:** OAuth connection not completed

**Solution:**
1. Go to Settings → Integrations
2. Click "Outlook Email" card
3. Complete OAuth flow in popup
4. Check for "Connected" status

### Issue: "Sync failed - please try again"

**Possible causes:**
- Microsoft token expired → Will auto-refresh
- Network issue → Try again
- Invalid permissions → Reconnect Microsoft 365

**Solution:**
1. Check Settings → Integrations → Microsoft 365 status
2. If showing "Connected", click "Sync Now" to retry
3. If not connected, reconnect via OAuth flow

### Issue: No items in reconciliation queue after sync

**This is normal if:**
- ✅ No new emails since last sync
- ✅ No loan-related content in emails
- ✅ All extractions had 95%+ confidence (auto-applied)

**Check:**
- Last sync timestamp updated?
- Email count in sync message
- Loan files for auto-applied updates (high confidence)

### Issue: Popup blocked

**Solution:**
1. Allow popups for mortgage-crm domain
2. Click "Outlook Email" card again
3. Popup should appear

---

## Current Connection Status

Run this to check your Microsoft 365 connection:

```bash
# Test with your auth token
curl https://mortgage-crm-production-7a9a.up.railway.app/api/v1/microsoft/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Expected response when connected:**
```json
{
  "connected": true,
  "email_address": "your@email.com",
  "sync_enabled": true,
  "last_sync_at": "2025-01-13T12:00:00Z"
}
```

**Expected response when NOT connected:**
```json
{
  "connected": false,
  "email_address": null,
  "sync_enabled": false,
  "last_sync_at": null
}
```

---

## OAuth Configuration Details

Your CRM is configured with:

| Setting | Value |
|---------|-------|
| **Client ID** | `185b7101-9435-44da-87ab-b7582c4e4607` |
| **Tenant** | `common` (multi-tenant) |
| **Redirect URI** | `https://mortgage-crm-production-7a9a.up.railway.app/api/v1/email/oauth/callback` |
| **Scopes** | Mail.Read, Mail.ReadWrite, Mail.Send, User.Read, Contacts.Read |

---

## Security & Privacy

### What Data is Accessed?
- **Emails:** Last 50 emails from Inbox (or since last sync)
- **Metadata:** Subject, sender, recipients, received time
- **Content:** Email body (text/HTML) for AI processing

### What Data is Stored?
- **Encrypted tokens:** Access & refresh tokens (encrypted at rest)
- **Extracted data:** Only loan-related information
- **Email metadata:** Subject, sender, timestamp
- **No full emails stored:** Only extracted fields saved

### Token Security
- Tokens encrypted using Fernet encryption
- Stored in secure database
- Auto-refresh before expiration
- Can be revoked anytime (Disconnect button)

---

## FAQ

**Q: How often do emails sync?**
A: Every 5 minutes automatically, plus manual "Sync Now" option

**Q: Which folder is synced?**
A: Inbox by default (configurable in future)

**Q: Are sent emails synced?**
A: Not currently (future feature)

**Q: Can I sync older emails?**
A: First sync gets last 7 days, subsequent syncs get new emails since last sync

**Q: What happens to emails with no loan data?**
A: Classified as "unrelated" and ignored (not stored)

**Q: Can I disconnect anytime?**
A: Yes! Click "Disconnect" in Settings → Integrations → Microsoft 365 panel

**Q: Does this work with Outlook.com (personal)?**
A: Yes, works with both Microsoft 365 (business) and Outlook.com (personal)

---

## Next Steps

1. ✅ **Database table created** (microsoft_oauth_tokens)
2. ⏳ **Connect Microsoft 365** (Settings → Integrations → Outlook Email)
3. ⏳ **Test manual sync** (Reconciliation → "Sync Emails Now")
4. ⏳ **Review reconciliation items**
5. ⏳ **Bulk approve updates** (Select up to 20, click "Approve Selected")

---

**Your email sync system is ready! Just needs the Microsoft 365 connection to start working.**
