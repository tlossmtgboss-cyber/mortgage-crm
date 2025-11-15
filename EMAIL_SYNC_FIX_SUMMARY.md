# 🔧 Email Sync Issue - Quick Fix

## 📋 The Problem

You haven't seen any emails in the CRM because **Microsoft 365 hasn't been connected yet**.

---

## ✅ The Solution (3 Steps)

### Step 1: Connect Microsoft 365
1. Login to: https://mortgage-crm-nine.vercel.app/login
2. Go to **Settings** (⚙️ in top navigation)
3. Click **"Integrations"** in the sidebar
4. Find **"Outlook Email"** card
5. Click to connect
6. Sign in with your Microsoft 365 account
7. Grant email permissions

### Step 2: Verify Connection
After connecting, you should see:
- ✅ "Microsoft 365 Connected" status
- Your email address displayed
- "Sync Now" button available

### Step 3: Trigger First Sync
- Click **"Sync Now"** button, OR
- Wait 5 minutes for auto-sync

---

## 🔍 Check If It's Working

### Method 1: Browser Console (Recommended)

1. **Open browser console**: Press **F12**
2. **Paste and run this**:

```javascript
fetch('https://mortgage-crm-production-7a9a.up.railway.app/api/v1/microsoft/sync-diagnostics', {
  headers: {'Authorization': 'Bearer ' + localStorage.getItem('token')}
})
.then(r => r.json())
.then(data => {
  console.log('=== EMAIL SYNC STATUS ===');
  console.log('Connected:', data.connection.connected);
  console.log('Email:', data.connection.email_address);
  console.log('Sync Enabled:', data.connection.sync_enabled);
  console.log('Recent Emails:', data.recent_emails.count);
  console.log('\n=== RECOMMENDATIONS ===');
  data.recommendations.forEach(r => console.log(`${r.type}: ${r.message}\nAction: ${r.action}\n`));
});
```

This will show you:
- ✅ Connection status
- ✅ Number of synced emails
- ✅ Specific recommendations

---

### Method 2: Force Immediate Sync

If connected, you can force a sync right now:

```javascript
fetch('https://mortgage-crm-production-7a9a.up.railway.app/api/v1/microsoft/force-sync', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer ' + localStorage.getItem('token'),
    'Content-Type': 'application/json'
  }
})
.then(r => r.json())
.then(data => console.log('Synced:', data.new_emails, 'new emails'));
```

---

## 📧 Where to See Emails

After syncing, emails appear in:

1. **Reconciliation Tab**
   - Go to **Reconciliation** in navigation
   - Check **"Pending Duplicates"** tab
   - Check **"Completed Tasks"** tab

2. **What You'll See**:
   - Loan status updates
   - Date changes
   - Amount updates
   - Document notices
   - Borrower information updates

---

## 🚨 Common Issues

### Issue 1: "Microsoft 365 not connected"
**Fix**: Follow Step 1 above to connect

### Issue 2: Connected but no emails
**Possible Causes**:
- Inbox is empty (send yourself a test email)
- First sync hasn't run yet (click "Sync Now" or wait 5 min)
- All emails already processed (check Reconciliation → Completed Tasks)

### Issue 3: Sync errors
**Fix**: Reconnect Microsoft 365 (disconnect, then connect again)

---

## 📊 How Auto-Sync Works

Once connected:
```
Every 5 Minutes:
  ↓
Checks Microsoft 365 Inbox
  ↓
Fetches new emails (last 50)
  ↓
AI processes each email
  ↓
Extracts loan data
  ↓
Creates reconciliation items
  ↓
Appears in Reconciliation tab
```

---

## 🎯 Expected Results

After connecting and syncing:

**Diagnostics should show**:
```json
{
  "connection": {
    "connected": true,
    "email_address": "your@email.com",
    "sync_enabled": true
  },
  "recent_emails": {
    "count": 10
  },
  "recommendations": [{
    "type": "success",
    "message": "System is working! 10 emails synced"
  }]
}
```

**Reconciliation tab should show**:
- Pending items from emails
- Or completed items if auto-approved (>95% confidence)

---

## 📚 Full Documentation

For detailed instructions:
- **Connection Guide**: `MICROSOFT_365_CONNECTION_GUIDE.md`
- **Troubleshooting**: `EMAIL_SYNC_TROUBLESHOOTING.md`

---

## ✅ Next Steps

1. **Connect Microsoft 365** (if not already connected)
2. **Run diagnostics** (paste command in browser console)
3. **Click "Sync Now"** or wait 5 minutes
4. **Check Reconciliation tab** for emails
5. **Share diagnostic output** if still not working

---

**The system is ready** - it just needs you to connect your Microsoft 365 account!
