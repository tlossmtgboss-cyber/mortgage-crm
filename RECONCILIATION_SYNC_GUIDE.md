# 📧 Reconciliation Center - Email Sync Features

## What's New

Your Reconciliation Center now includes:

### 1. **Manual "Sync Emails Now" Button**
- Located in the header of the Reconciliation Center
- Beautiful gradient purple button with sync icon (⟳)
- Click to instantly pull in emails from Microsoft 365
- Shows real-time status during sync

### 2. **Automatic Email Sync Every 5 Minutes**
- Runs silently in the background
- No user interaction needed
- Keeps reconciliation queue up-to-date automatically
- Starts as soon as you open the Reconciliation Center

---

## How to Use

### Manual Sync

1. **Navigate to Reconciliation Center**
   - Go to your CRM dashboard
   - Click "Reconciliation" in the navigation

2. **Click "Sync Emails Now"**
   - Button is in the top-right area of the header
   - Shows spinning animation during sync
   - Displays success message when complete

3. **View Results**
   - Success: "✓ Synced X emails successfully" (green)
   - Error: "⚠ Sync failed - please try again" (red)
   - Messages auto-dismiss after 3 seconds

### Automatic Sync

**No action needed!** The system automatically:
- Syncs emails every 5 minutes
- Runs in the background (silent)
- Updates the last sync time
- Refreshes your reconciliation queue

---

## Visual Features

### Button States

**Normal State:**
```
⟳ Sync Emails Now
```
- Purple gradient button
- Hover effect: lifts slightly
- Click to sync

**Syncing State:**
```
[spinner] Syncing...
```
- Lighter purple shade
- Animated spinner
- Button disabled during sync

### Status Messages

**Success (Green):**
```
✓ Synced 12 emails successfully
```

**Error (Red):**
```
⚠ Sync failed - please try again
```

**Last Sync Time:**
```
Last synced: 2:45:30 PM
```
- Shows when sync was last completed
- Updates automatically
- Displayed when no active status message

---

## How It Works Behind the Scenes

### When You Click "Sync Emails Now"

```
1. Button shows "Syncing..." with spinner
   ↓
2. API calls Microsoft 365 to fetch last 50 emails
   ↓
3. Each email is processed through DRE (Data Reconciliation Engine)
   ↓
4. AI Email Processor Agent reviews each email
   ↓
5. Extracted data appears in reconciliation queue
   ↓
6. Status message shows "✓ Synced X emails successfully"
   ↓
7. Pending items count updates automatically
```

### Automatic Background Sync (Every 5 Minutes)

```
Timer triggers every 5 minutes
   ↓
Silent sync runs (no UI changes)
   ↓
New emails processed automatically
   ↓
Reconciliation queue updated
   ↓
Last sync time updated quietly
```

---

## What Gets Synced

When emails are synced, the system:

1. **Fetches emails** from your Microsoft 365 inbox
2. **Classifies content** (loan update, status change, document notice, etc.)
3. **Extracts data** (loan numbers, amounts, dates, statuses)
4. **Matches to loans** in your CRM
5. **Creates reconciliation items** if confidence < 95%
6. **Auto-applies updates** if confidence ≥ 95%
7. **Triggers AI agents** to enhance and complete data

---

## Reconciliation Queue Updates

After sync, you'll see new items for:

- **Loan status updates** from lender emails
- **Closing date changes** from title company
- **Appraisal results** from appraisal companies
- **Condition updates** from underwriter emails
- **Document requests** from processors

Each item shows:
- Confidence score (High/Medium/Low)
- Category (Status Update, Date Change, etc.)
- Source email subject and sender
- Extracted fields with current vs. new values

---

## Configuration

### Sync Frequency
Currently set to: **5 minutes**

To change frequency, edit `ReconciliationCenter.js` line 22:
```javascript
}, 5 * 60 * 1000); // Change 5 to desired minutes
```

**Recommended ranges:**
- **5 minutes**: High-volume offices (default)
- **10 minutes**: Medium-volume offices
- **15 minutes**: Low-volume offices

**Note:** Syncing too frequently (< 5 min) may hit Microsoft API rate limits.

### Auto-Sync On/Off

To disable auto-sync (manual only), comment out lines 19-24:
```javascript
// Auto-sync emails every 5 minutes
// const syncInterval = setInterval(() => {
//   syncEmails(true); // silent sync
// }, 5 * 60 * 1000);
```

---

## Troubleshooting

### "Sync failed" Error

**Possible Causes:**
1. Microsoft 365 not connected
2. Auth token expired
3. Network connection issue

**Solutions:**
1. Check Settings → Integrations → Microsoft 365
2. Reconnect if needed (click "Connect Email")
3. Ensure sync is enabled in Microsoft settings

### No New Items After Sync

**This is normal if:**
- No new emails since last sync
- All emails already processed
- Emails don't contain loan-related content

**Check:**
- Last sync time (should update even if no emails)
- Email sync settings (folder, filters)
- Microsoft connection status

### Button Stuck in "Syncing..." State

**Rare edge case, usually resolves automatically**

**To fix:**
1. Refresh the page
2. Check browser console for errors
3. Verify Microsoft connection is active

---

## Technical Details

### API Endpoint Used
```
POST /api/v1/microsoft/sync-now
```

### Response Format
```json
{
  "status": "success",
  "fetched_count": 50,
  "processed_count": 12,
  "message": "Synced 12 emails successfully"
}
```

### Browser Storage
- Last sync time stored in component state
- Sync interval ID managed by React useEffect
- Clean-up on component unmount

---

## Benefits

✅ **Always Up-to-Date** - Automatic sync every 5 minutes
✅ **Manual Control** - Sync on-demand when you need it
✅ **Visual Feedback** - Clear status messages for all actions
✅ **Non-Intrusive** - Background syncing doesn't interrupt work
✅ **Error Handling** - Graceful failure with retry option
✅ **Performance** - Efficient syncing without page reload
✅ **AI Integration** - Synced emails processed by AI agents

---

## Next Steps

1. **Test Manual Sync**
   - Go to Reconciliation Center
   - Click "Sync Emails Now"
   - Watch status messages

2. **Verify Auto-Sync**
   - Leave Reconciliation page open
   - Check "Last synced" time updates every 5 min
   - New items appear automatically

3. **Review Reconciliation Items**
   - Approve high-confidence extractions
   - Correct and approve medium-confidence items
   - Reject incorrect extractions

4. **Monitor AI Agent Activity**
   - Check `/api/ai/executions?agent_id=email_processor`
   - See how Email Processor Agent enhances data

---

## Support

The email sync feature is now live and active in your CRM. If you need to:
- Adjust sync frequency
- Modify button styling
- Change sync behavior
- Add sync notifications

Edit the files:
- `/frontend/src/pages/ReconciliationCenter.js` (logic)
- `/frontend/src/pages/ReconciliationCenter.css` (styling)

---

**Your Reconciliation Center now keeps your loan data automatically synchronized with incoming emails!**
