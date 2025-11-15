# 🤖 Sample AI Diagnosis - Outlook Integration Issues

This document shows what the AI IT Helpdesk will output when you submit a ticket about Outlook/Calendar integration issues.

---

## 📝 Sample Ticket Submission

**Title**: Outlook Email and Calendar Sync Not Working

**Description**:
```
I'm having issues with the Outlook email and calendar integrations:

1. Email sync is not pulling emails from my Outlook inbox
2. Calendar events are not syncing properly
3. I see a 502 error when trying to sync
4. The connection status shows as disconnected even after I authorize

Error message: "Failed to sync emails: 502 Bad Gateway"

Please diagnose and provide steps to fix these integration issues.
```

**Category**: SaaS Configuration
**Urgency**: High
**System**: Microsoft 365
**Project**: mortgage-crm

---

## 🎯 AI Diagnosis Response

### Root Cause
```
Microsoft 365 OAuth token expired or connection not properly established
```

### Detailed Diagnosis
```
The 502 Bad Gateway error indicates that the backend is unable to successfully
communicate with Microsoft's Graph API. This typically occurs when:

1. The OAuth access token has expired (tokens expire after 1 hour)
2. The refresh token is invalid or expired
3. The Microsoft 365 account authorization was revoked
4. Network connectivity issues between Railway and Microsoft Graph API
5. Microsoft Graph API is experiencing service issues

The fact that connection status shows "disconnected" even after authorization
suggests the OAuth callback did not complete successfully or the token was
not properly stored in the database.
```

---

## 💡 Proposed Fix

**Risk Level**: LOW

### Steps:

1. **Disconnect and reconnect Microsoft 365 account**
   - Go to Settings → Integrations
   - Find "Outlook Email" integration
   - Click "Disconnect" to clear old credentials
   - Click "Connect" and authorize again with Microsoft 365
   - Grant all requested permissions

2. **Verify OAuth token is stored correctly**
   - After reconnecting, check connection status
   - Should show your email address
   - Status should be "Connected"

3. **Enable email sync**
   - Ensure "Enable Auto-Sync" toggle is ON
   - Set sync frequency (default: 5 minutes)
   - Select sync folder (default: Inbox)

4. **Trigger manual sync to test**
   - Click "Sync Now" button
   - Wait 10-30 seconds
   - Check Reconciliation tab for new emails

5. **Verify calendar integration**
   - Ensure calendar permissions were granted during OAuth
   - Check if calendar events are visible
   - Test creating a calendar event

---

### Commands to Run

#### Command 1: Check Microsoft 365 Connection Status
**Description**: Verify if Microsoft 365 is connected and sync is enabled

**Command**:
```javascript
fetch('https://mortgage-crm-production-7a9a.up.railway.app/api/v1/microsoft/sync-diagnostics', {
  headers: {'Authorization': 'Bearer ' + localStorage.getItem('token')}
})
.then(r => r.json())
.then(data => {
  console.log('Connection Status:', data.connection);
  console.log('Recent Emails:', data.recent_emails.count);
  console.log('Recommendations:', data.recommendations);
});
```

**Platform**: Browser Console (F12)

---

#### Command 2: Force Immediate Sync
**Description**: Trigger an immediate email sync (bypasses 5-minute wait)

**Command**:
```javascript
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

**Platform**: Browser Console (F12)

---

#### Command 3: Check Railway Backend Logs
**Description**: View recent backend logs to identify specific errors

**Command**:
```bash
railway logs | grep -i "microsoft\|sync\|email" | tail -30
```

**Platform**: Terminal (requires Railway CLI)

---

#### Command 4: Test Microsoft Graph API Connectivity
**Description**: Verify the backend can reach Microsoft's API

**Command**:
```bash
curl -I https://graph.microsoft.com/v1.0/me
```

**Platform**: Terminal

---

## 📊 Expected Results After Fix

### If Successful:

**Connection Diagnostics** should show:
```json
{
  "connection": {
    "connected": true,
    "email_address": "your@email.com",
    "sync_enabled": true,
    "last_sync_at": "2025-01-15T10:30:00Z"
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

**Reconciliation Tab** should show:
- Pending email-based loan updates
- OR completed items (if auto-approved at >95% confidence)

**Calendar Integration** should show:
- Connected status
- Recent calendar events visible
- Ability to create/sync events

---

## 🔍 Troubleshooting If Fix Doesn't Work

### Issue 1: Still seeing "disconnected" after reconnecting

**Possible Causes**:
- Browser cache preventing proper OAuth flow
- Popup blocker preventing authorization window

**Additional Steps**:
1. Clear browser cache and cookies
2. Try in incognito/private browsing mode
3. Disable popup blockers for mortgage-crm-nine.vercel.app
4. Check browser console for JavaScript errors

---

### Issue 2: Connected but sync shows 0 emails

**Possible Causes**:
- Inbox is actually empty
- Wrong folder selected for sync
- All emails already processed

**Additional Steps**:
1. Send yourself a test email to your Outlook account
2. Wait 5 minutes for auto-sync OR click "Sync Now"
3. Check Reconciliation → Completed Tasks (emails may be auto-processed)
4. Verify sync folder is set to "Inbox" not a subfolder

---

### Issue 3: 502 error persists

**Possible Causes**:
- Microsoft Graph API service issue
- Network firewall blocking Graph API
- OAuth permissions incomplete

**Additional Steps**:
1. Check Microsoft 365 service status: https://status.cloud.microsoft/
2. Verify all permissions granted during OAuth:
   - Mail.Read
   - Mail.ReadWrite
   - Calendars.Read
   - Calendars.ReadWrite
3. Contact support if Microsoft service is down
4. Check Railway backend logs for detailed error messages

---

## ✅ Success Indicators

You'll know the fix worked when:

1. ✅ Connection status shows "Connected: true"
2. ✅ Your email address is displayed
3. ✅ Recent emails count > 0
4. ✅ Recommendations show "success" type
5. ✅ No 502 errors in browser console
6. ✅ Reconciliation tab shows new email-based items
7. ✅ Calendar events visible in calendar integration

---

## 🎯 Prevention

To prevent this issue in the future:

1. **Don't revoke app permissions** in Microsoft 365 admin center
2. **Keep auto-sync enabled** to maintain active token
3. **Monitor diagnostics regularly** using the diagnostics endpoint
4. **Reconnect every 90 days** to refresh long-term tokens
5. **Check Railway logs** for early warning signs

---

## 📞 Need More Help?

If the above fix doesn't work:

1. **Submit a new IT Helpdesk ticket** with:
   - Results from running the diagnostic commands
   - Exact error messages from browser console
   - Screenshots of connection status page
   - Railway logs output

2. **Check existing documentation**:
   - `EMAIL_SYNC_FIX_SUMMARY.md` - Quick fix guide
   - `EMAIL_SYNC_TROUBLESHOOTING.md` - Detailed troubleshooting
   - `MICROSOFT_365_CONNECTION_GUIDE.md` - Step-by-step connection

3. **Use the diagnostics endpoint** to get AI recommendations:
   - The endpoint analyzes your specific situation
   - Provides customized recommendations
   - Includes actionable next steps

---

**This is a SAMPLE of what the AI will generate when you submit a real ticket!**

The AI diagnosis is generated in real-time based on your specific issue description, so the actual response may be more tailored to your exact problem.
