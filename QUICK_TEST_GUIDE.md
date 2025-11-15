# ⚡ Quick Test Guide - IT Helpdesk & Outlook Integration

**5-Minute Quick Start**

---

## 🚀 Option 1: Test via Frontend (Easiest)

### Step 1: Login
Go to: https://mortgage-crm-nine.vercel.app

### Step 2: Navigate to IT Helpdesk
1. Click **Settings** (⚙️ icon in top navigation)
2. Click **IT Helpdesk** (🛠️ icon in sidebar)

### Step 3: Submit a Test Ticket
Copy and paste this into the form:

**Title**:
```
Outlook Email Sync Not Working
```

**Description**:
```
I'm having issues with the Outlook email integration:
- Email sync is not pulling emails from my inbox
- I see connection errors
- Calendar events are not syncing

Please diagnose and provide steps to fix.
```

**Settings**:
- Category: **SaaS Configuration**
- Urgency: **High**
- System: **Microsoft 365**
- Project: **mortgage-crm**

### Step 4: Click "Submit Issue →"

The AI will analyze your issue and provide:
- 🎯 Root cause diagnosis
- 💡 Step-by-step fix instructions
- 📋 Commands to run (with copy buttons)
- ⚠️ Risk level assessment

### Step 5: Review AI Response
You'll see:
- Root Cause: "Microsoft 365 OAuth token expired..."
- Diagnosis: Detailed explanation
- Proposed Fix: 5 steps to resolve
- Commands: JavaScript and bash commands to run
- Risk: Low

### Step 6: Test Workflow
1. Click **"Approve Fix"** button
2. Copy and run the commands
3. Enter resolution notes
4. Click **"Mark as Resolved"**

---

## 🧪 Option 2: Run Automated Tests

### Quick Test (30 seconds)
```bash
./test_it_helpdesk_automated.sh
```

**Tests**:
- ✅ Backend health
- ✅ IT Helpdesk endpoints
- ✅ Microsoft 365 diagnostics endpoints
- ✅ Frontend deployment

### Full Test (5 minutes - requires login)
```bash
python3 test_it_helpdesk_and_integrations.py
```

**Tests**:
- ✅ Submit ticket via API
- ✅ Get AI diagnosis
- ✅ Approve ticket
- ✅ Resolve ticket
- ✅ Check Microsoft 365 sync status
- ✅ Verify integration status

---

## 🔍 Option 3: Test Outlook Diagnostics

### Via Browser Console

1. Login to CRM
2. Press **F12** (open DevTools)
3. Go to **Console** tab
4. Paste and run:

```javascript
// Test 1: Check Email Sync Status
fetch('https://mortgage-crm-production-7a9a.up.railway.app/api/v1/microsoft/sync-diagnostics', {
  headers: {'Authorization': 'Bearer ' + localStorage.getItem('token')}
})
.then(r => r.json())
.then(data => {
  console.log('=== EMAIL SYNC STATUS ===');
  console.log('Connected:', data.connection.connected);
  console.log('Email:', data.connection.email_address);
  console.log('Recent Emails:', data.recent_emails.count);
  console.log('Recommendations:', data.recommendations);
});
```

```javascript
// Test 2: Force Immediate Sync
fetch('https://mortgage-crm-production-7a9a.up.railway.app/api/v1/microsoft/force-sync', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer ' + localStorage.getItem('token'),
    'Content-Type': 'application/json'
  }
})
.then(r => r.json())
.then(data => console.log('Sync Result:', data));
```

---

## 📊 What to Expect

### IT Helpdesk AI Diagnosis
- ⚡ **Response Time**: 5-10 seconds
- 🎯 **Root Cause**: Specific problem identified
- 💡 **Fix Steps**: 3-7 actionable steps
- 📋 **Commands**: Copy-paste ready
- ⚠️ **Risk Level**: Low/Medium/High

### Outlook Integration Diagnostics
- 🔌 **Connection Status**: Connected/Disconnected
- 📧 **Email Count**: Number of recent emails synced
- 📅 **Last Sync**: Timestamp of last sync
- 💬 **Recommendations**: AI-generated next steps

---

## ✅ Success Checklist

After testing, you should see:

### IT Helpdesk
- [x] Ticket submitted successfully
- [x] AI diagnosis displayed (root cause + fix)
- [x] Commands provided with copy buttons
- [x] Ticket appears in ticket list
- [x] Can approve and resolve tickets

### Outlook Integration
- [ ] Connection status = true (if you've connected Microsoft 365)
- [ ] Email address displayed
- [ ] Recent emails count > 0 (if emails exist)
- [ ] Recommendations provided
- [ ] No 502 errors

---

## 🐛 Troubleshooting

### If IT Helpdesk doesn't work:
1. Check backend: https://mortgage-crm-production-7a9a.up.railway.app/health
2. Check browser console for errors (F12)
3. Try refreshing the page
4. Check Railway logs: `railway logs | grep helpdesk`

### If Outlook sync shows 0 emails:
1. **Connect Microsoft 365 first**:
   - Go to Settings → Integrations
   - Click on "Outlook Email"
   - Authorize with Microsoft 365
2. Click "Sync Now" or wait 5 minutes
3. Check Reconciliation tab
4. See: `EMAIL_SYNC_FIX_SUMMARY.md`

---

## 📚 Full Documentation

- **IT_HELPDESK_TEST_RESULTS.md** - Complete test results
- **SAMPLE_AI_DIAGNOSIS.md** - Example AI response
- **AI_IT_HELPDESK_IMPLEMENTATION.md** - Technical details
- **EMAIL_SYNC_TROUBLESHOOTING.md** - Outlook troubleshooting

---

## 🎯 Next Steps

1. **Test IT Helpdesk** (Option 1 above - 2 minutes)
2. **Check Outlook sync** (Option 3 above - 1 minute)
3. **Run automated tests** (Optional - Option 2)
4. **Submit real issues** and let AI diagnose them!

---

**Everything is deployed and ready to test!** 🚀
