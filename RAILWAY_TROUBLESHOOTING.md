# Railway Deployment Troubleshooting

## Current Status

Production API: https://mortgage-crm-production-7a9a.up.railway.app

**Issue:** Application returning 502 errors

## What We Fixed

1. **Database Migrations** - Added automatic migrations for `is_admin` and `parent_user_id` columns
2. **PORT Configuration** - Updated railway.toml to use Railway's $PORT environment variable
3. **Code Pushed** - Latest commit: 9bdd7e7

## Next Steps to Diagnose

### 1. Check Railway Logs

Go to Railway dashboard and view the deployment logs:

```
https://railway.app/project/<your-project-id>/deployments
```

Look for:
- Python startup errors
- Database connection errors
- Missing environment variables
- Import errors

### 2. Verify Environment Variables

Required variables in Railway dashboard:

```bash
DATABASE_URL=postgresql://...  # Should be set automatically by Railway
SECRET_KEY=<your-secret-key>   # Optional, has default
```

Optional (for Microsoft Graph integration):
```bash
MICROSOFT_CLIENT_ID=<your-client-id>
MICROSOFT_CLIENT_SECRET=<your-client-secret>
MICROSOFT_TENANT_ID=<your-tenant-id>
MICROSOFT_FROM_EMAIL=<your-email>
MICROSOFT_REDIRECT_URI=https://mortgage-crm-production-7a9a.up.railway.app/auth/microsoft/callback
```

### 3. Manual Database Migration (if needed)

If the automatic migration at startup failed, you can run it manually via Railway CLI:

```bash
# First, link your project
railway link

# Then run the migration script
railway run python3 migrate_db_simple.py

# Or run SQL directly
railway run psql -c "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT TRUE;"
railway run psql -c "ALTER TABLE users ADD COLUMN IF NOT EXISTS parent_user_id INTEGER REFERENCES users(id);"
```

### 4. Check Database Connection

Verify PostgreSQL is running and accessible:

```bash
railway run pg_isready
```

### 5. Common Issues and Solutions

#### Issue: "Application failed to respond"

**Possible Causes:**
1. App crashed on startup due to missing dependencies
2. Database connection failed
3. Port misconfiguration (we fixed this)
4. Migration failed

**Solution:**
- Check Railway logs for the actual error
- Verify all dependencies are in requirements.txt (they should be)
- Ensure DATABASE_URL is set

#### Issue: "MSAL not installed"

**Possible Cause:** Missing dependency

**Solution:**
```bash
# Add to backend/requirements.txt (already there)
msal==1.24.1
msgraph-sdk==1.0.0
azure-identity==1.14.0
```

#### Issue: Circular Import Error

**Status:** Fixed in latest code

**Verification:**
```bash
# Test locally
cd backend
source ../venv/bin/activate
python3 -c "import main; print('Import successful')"
```

### 6. Force Redeploy

If Railway didn't pick up the latest changes:

```bash
# Push an empty commit to force redeploy
git commit --allow-empty -m "Force Railway redeploy"
git push
```

### 7. Check Railway Build Logs

In Railway dashboard:
1. Go to your project
2. Click on the backend service
3. Go to "Deployments" tab
4. Click on the latest deployment
5. View "Build Logs" and "Deploy Logs"

Look for:
- Python version mismatch
- Dependency installation failures
- Database connection errors
- Port binding issues

## Testing the Fix

Once deployed successfully, test these endpoints:

```bash
# Health check
curl https://mortgage-crm-production-7a9a.up.railway.app/api/v1/health

# Should return:
# {"status":"healthy","database":"connected"}
```

```bash
# API docs (should load in browser)
open https://mortgage-crm-production-7a9a.up.railway.app/docs
```

## Creating Production User

After deployment is healthy, create the production user:

```bash
cd /Users/timothyloss/my-project/mortgage-crm
python3 create_production_user.py
```

This will create:
- Email: tloss@cmgfi.com
- Password: Woodwindow00!

## Additional Resources

- Railway Docs: https://docs.railway.app
- Railway Status: https://status.railway.app
- Project Logs: railway logs (after running `railway link`)

## Contact Support

If issues persist:
1. Export Railway logs: `railway logs > railway_errors.log`
2. Share the log file to diagnose the issue
3. Check Railway status page for outages

---

## Quick Diagnosis Commands

```bash
# Check if deployment is running
curl -I https://mortgage-crm-production-7a9a.up.railway.app

# Check health endpoint
curl https://mortgage-crm-production-7a9a.up.railway.app/api/v1/health

# View recent logs (requires railway link)
railway logs

# Check environment variables
railway variables

# Restart the service
railway restart
```

## Most Likely Issue

Based on the 502 errors and the fact that the code works locally, the most likely issues are:

1. **Database migration failed at startup** - The app tries to query the database before migrations run
2. **DATABASE_URL not set or invalid** - Railway should set this automatically, but verify it exists
3. **Python version mismatch** - Railway might be using a different Python version
4. **Missing system dependencies** - Some Python packages require system libraries

Check Railway logs to confirm which issue it is!
