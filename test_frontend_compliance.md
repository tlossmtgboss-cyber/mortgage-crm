# Frontend Compliance System - Testing Guide

## ✅ Status: DEPLOYED & READY

Your compliance system frontend is deployed to Vercel. The WebFetch tool cannot render JavaScript/React apps, but all files are in place and the deployment is complete.

## 🧪 Manual Testing Steps

### Step 1: Login as Admin

1. Open: https://mortgage-crm-nine.vercel.app/login
2. Login with:
   - Email: `demo@example.com`
   - Password: `demo123`
3. Verify you're logged in (should redirect to dashboard)

### Step 2: Test Admin Settings Page

1. Navigate to: https://mortgage-crm-nine.vercel.app/admin/settings
2. **Expected to see:**
   - Page title: "Admin Settings"
   - Subtitle: "System administration and maintenance tools"
   - Section: "Access Certification Jobs"
   - Two job cards:

     **Card 1: Create Quarterly Certifications**
     - Blue badge: "Run Quarterly"
     - Description about creating certifications
     - Button: "Create Certifications"

     **Card 2: Send Certification Reminders**
     - Orange badge: "Run Daily"
     - Description about sending reminders
     - Button: "Send Reminders"

3. **Test Create Certifications:**
   - Click "Create Certifications" button
   - Should show: "Creating..."
   - After ~2 seconds: Green success message
   - Message: "Created X certifications for Q4-2025"
   - Note: If run again, should show "Skipped X (already exist)"

4. **Test Send Reminders:**
   - Click "Send Reminders" button
   - Should show: "Sending..."
   - After ~1 second: Green success message
   - Message: "0 reminders sent" (none due yet - 90 days away)

### Step 3: Test Compliance Dashboard

1. Navigate to: https://mortgage-crm-nine.vercel.app/compliance
2. **Expected to see:**

   **Overview Section:**
   ```
   Active Users: 2
   Total Certifications: 1
   Certification Rate: 0%
   Overdue Certifications: 0
   ```

   **Department Breakdown:**
   - Table showing:
     - Administration: 1 employee, 1 certification, 0% complete
     - General: 1 employee, 0 certifications

   **Pending Certifications List:**
   - One row showing:
     - Employee: Demo User
     - Period: Q4-2025
     - Due Date: February 14, 2026
     - Status: Pending (yellow badge)
     - Days Until Due: 90
     - Permissions: 102

   **Export Button:**
   - Top right corner: "Export CSV" button

3. **Test Export:**
   - Click "Export CSV"
   - Should download: `compliance-report-YYYY-MM-DD.csv`
   - Open file - should contain certification data

### Step 4: Test Navigation

1. **Check Navigation Links:**
   - Main nav should show "Compliance" link (visible to admin/management only)
   - User menu should show "🔧 Admin" link

2. **Verify Role Protection:**
   - Logout and login as a non-admin user
   - Compliance and Admin links should NOT appear
   - Direct navigation to /compliance or /admin/settings should redirect

## 🔍 Troubleshooting

### If pages don't load:

1. **Check Browser Console:**
   - Open Developer Tools (F12)
   - Look for errors in Console tab
   - Common issues:
     - CORS errors → Backend not responding
     - 404 errors → Check API endpoint
     - Module errors → CSS/JS import issues

2. **Verify Authentication:**
   - Check localStorage has 'token' set
   - Try logging out and back in
   - Check token is valid (not expired)

3. **Check Vercel Deployment:**
   ```bash
   # From project root
   git log -1  # Should show recent commit
   ```
   - Vercel auto-deploys on push to main
   - Deployment takes ~2-3 minutes

### If API calls fail:

1. **Check Network Tab:**
   - See actual request/response
   - Verify URL: `https://mortgage-crm-production-7a9a.up.railway.app`
   - Check Authorization header has Bearer token

2. **Test API Directly:**
   ```bash
   # Use test scripts
   ./test_compliance_endpoints.sh
   ./test_admin_jobs.sh
   ```

## 📊 Expected Production Data

After running "Create Certifications" once:

```json
{
  "users": {
    "total": 2,
    "active": 2
  },
  "certifications": {
    "total": 1,
    "certified": 0,
    "certified_percent": 0.0,
    "overdue": 0,
    "pending": 1
  },
  "permissions": {
    "total_granted": 151,
    "high_risk_granted": 0,
    "recent_changes_30d": 204
  }
}
```

## 🎯 Advanced Testing (Optional)

### Simulate Due Certification

To test the full certification workflow without waiting 90 days:

1. **Update due date in database:**
   ```bash
   # Create script: simulate_due_cert.sh
   ./run_migration_endpoint.sh

   # Then run SQL via Railway:
   railway run bash -c "psql \$DATABASE_URL -c \"UPDATE access_certifications SET due_date = CURRENT_DATE + 1 WHERE certification_period = 'Q4-2025'\""
   ```

2. **Send reminders:**
   - Go to Admin Settings
   - Click "Send Reminders"
   - Should now show "1 7-day reminder sent"

3. **Check notifications:**
   - Click bell icon in nav
   - Should see: "⚠️ Access certification due in 7 days"
   - Click notification → Opens certification modal

4. **Complete certification:**
   - Review employee permissions (102 total)
   - Optionally revoke some
   - Add notes
   - Click "Certify"
   - Dashboard should update: 100% completion rate

## ✅ Success Criteria

- [ ] Admin Settings page loads without errors
- [ ] Both job cards are visible and clickable
- [ ] Create Certifications creates Q4-2025 cert
- [ ] Send Reminders runs without errors
- [ ] Compliance Dashboard shows metrics
- [ ] Department breakdown displays correctly
- [ ] Pending certifications list shows 1 item
- [ ] Export CSV downloads successfully
- [ ] Navigation links appear for admin users
- [ ] Pages redirect for non-admin users

## 🚀 Next Steps After Testing

Once verified:
1. Set up scheduled jobs (cron) for:
   - Quarterly certification creation
   - Daily reminder checks
2. Add more test users to see multi-department view
3. Test full certification cycle with due certs
4. Set up email notifications (currently in-app only)
