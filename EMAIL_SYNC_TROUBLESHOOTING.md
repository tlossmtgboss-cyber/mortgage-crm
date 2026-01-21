# 📧 Email Sync Troubleshooting Guide

**Issue**: No emails appearing in CRM

---

## 🔍 Quick Diagnosis

I've added diagnostic tools to help identify the issue. Let's check your email sync status:

### Option 1: Via Browser (Easiest)

1. **Login to your CRM**: https://mortgage-crm-nine.vercel.app/login
2. **Open your browser's console**: Press F12 or Right-click → Inspect
3. **Run this command in the Console tab**:

```javascript
fetch('https://app.perenniaai.com/api/v1/microsoft/sync-diagnostics', {
  headers: {
    'Authorization': 'Bearer ' + localStorage.getItem('token')
  }
})
.then(r => r.json())
.then(data => {
  console.log('=== EMAIL SYNC STATUS ===');
  console.log('Connected:', data.connection.connected);
  console.log('Email:', data.connection.email_address);
  console.log('Sync Enabled:', data.connection.sync_enabled);
  console.log('Last Sync:', data.connection.last_sync_at);
  console.log('Recent Emails:', data.recent_emails.count);
  console.log('\n=== RECOMMENDATIONS ===');
  data.recommendations.forEach(r => {
    console.log(`${r.type.toUpperCase()}: ${r.message}`);
    console.log(`Action: ${r.action}\n`);
  });
});
```

---

## 🎯 Most Common Issues & Fixes

### Issue 1: Microsoft 365 Not Connected
**Symptoms**: "Microsoft 365 not connected" in diagnostics

**Fix**:
1. Go to **Settings** page
2. Click **"Integrations"** (🔌 icon)
3. Find **"Outlook Email"** card
4. Click to connect
5. Sign in with your Microsoft 365 account
6. Grant permissions when prompted

**Guide**: See `MICROSOFT_365_CONNECTION_GUIDE.md` for step-by-step instructions

---

### Issue 2: Email Sync is Disabled
**Symptoms**: Connected but "sync_enabled: false"

**Fix**:
1. Go to **Settings → Integrations**
2. Find your connected Microsoft 365 account
3. Toggle **"Enable Auto-Sync"** to ON
4. Click **"Save Settings"**

---

### Issue 3: First Sync Not Triggered Yet
**Symptoms**: Connected and enabled, but "last_sync_at: null"

**Fix**:
Option A: **Manual Sync**
1. Go to **Settings → Integrations**
2. Click **"Sync Now"** button
3. Wait 10-30 seconds
4. Check if emails appear in Reconciliation tab

Option B: **Wait for Auto-Sync**
- System syncs automatically every 5 minutes
- Wait up to 5 minutes for first sync

---

### Issue 4: No Emails in Inbox
**Symptoms**: Sync works but "recent_emails: 0"

**Possible Causes**:
1. **Inbox is empty** - Check your Microsoft 365 inbox has emails
2. **Wrong folder** - Sync is looking at "Inbox" by default
3. **All emails already processed** - Check Reconciliation tab for existing items

**Fix**:
- Send yourself a test email
- Wait 5 minutes or click "Sync Now"
- Check Reconciliation tab

---

### Issue 5: Tokens Expired
**Symptoms**: Sync errors in logs, "Authentication failed"

**Fix**:
1. Go to **Settings → Integrations**
2. Click **"Disconnect"**
3. Click **"Connect"** again
4. Re-authorize with Microsoft 365

---

## 🚀 Force a Manual Sync

If you want to trigger an immediate sync (bypasses the 5-minute wait):

### Via Browser Console:
```javascript
fetch('https://app.perenniaai.com/api/v1/microsoft/force-sync', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer ' + localStorage.getItem('token'),
    'Content-Type': 'application/json'
  }
})
.then(r => r.json())
.then(data => {
  console.log('=== SYNC RESULT ===');
  console.log('Success:', data.success);
  console.log('Total Emails:', data.total_emails);
  console.log('New Emails:', data.new_emails);
  console.log('Message:', data.message);
});
```

---

## 📊 Understanding the Sync Process

```
┌─────────────────────┐
│ Microsoft 365 Inbox │
└──────────┬──────────┘
           │
           ↓ (Every 5 minutes)
┌─────────────────────┐
│   Auto-Sync Job     │ ← Checks all users with sync enabled
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  Fetch New Emails   │ ← Gets last 50 emails from inbox
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│ AI Email Processor  │ ← Extracts loan data, dates, status
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│ Reconciliation Tab  │ ← Items appear here for review
└─────────────────────┘
```

---

## 🔍 Check Logs for Errors

If you have Railway CLI:

```bash
railway logs | grep -i "sync\|email\|microsoft"
```

Look for:
- ✅ "Auto-sync: Checking X users for email sync" (should be > 0)
- ✅ "Auto-syncing emails for user..."
- ✅ "Auto-synced X/Y emails for user..."
- ❌ "Auto-sync error" (indicates a problem)

---

## 📝 What to Check

1. **Connection Status**
   - [ ] Microsoft 365 account connected?
   - [ ] Email address showing correctly?
   - [ ] "Connected" status = true?

2. **Sync Settings**
   - [ ] Sync enabled = true?
   - [ ] Sync frequency = 5 minutes?
   - [ ] Last sync timestamp exists?

3. **Email Inbox**
   - [ ] Microsoft 365 inbox has emails?
   - [ ] Looking at correct folder (Inbox)?
   - [ ] Test email sent to yourself?

4. **Reconciliation Tab**
   - [ ] Any items in pending review?
   - [ ] Check "Completed Tasks" tab too
   - [ ] Items might be auto-approved if confidence > 95%

---

## 🎯 Next Steps

Based on the diagnostic results:

**If Microsoft 365 not connected:**
→ Follow `MICROSOFT_365_CONNECTION_GUIDE.md`

**If connected but no sync:**
→ Click "Sync Now" in Settings

**If emails synced but not visible:**
→ Check Reconciliation tab (both Pending and Completed)

**If still not working:**
→ Run diagnostics and share the output:
- Connection status
- Recent emails count
- Recommendations shown
- Any error messages in console

---

## ✅ Success Indicators

You'll know it's working when:

1. **Diagnostics show**:
   ```json
   {
     "connection": {
       "connected": true,
       "sync_enabled": true,
       "last_sync_at": "2025-01-15T..."
     },
     "recent_emails": {
       "count": 10
     },
     "recommendations": [
       {
         "type": "success",
         "message": "System is working! 10 emails synced recently"
       }
     ]
   }
   ```

2. **Reconciliation tab** shows pending items

3. **Logs show**: "Auto-synced 5/10 emails for user X"

---

## 🆘 Still Need Help?

Run the diagnostic command and share:
1. Connection status output
2. Recommendations received
3. Recent emails count
4. Any error messages

This will help identify the exact issue!
