# 🚨 RAILWAY FIX - DO THIS NOW

## ⚡ Quick Fix Guide - Copy & Paste Ready

**Estimated Time:** 10-15 minutes

---

## Step 1: Check Current Railway Status

### Open Railway Dashboard
1. Go to: https://railway.app/dashboard
2. Click on your **"mortgage-crm"** project
3. You should see two services:
   - **PostgreSQL** (database)
   - **backend** (your FastAPI app)

### Check if PostgreSQL is Running
- Click on the **PostgreSQL** service
- Status should show: **"Active"** ✅
- If not active, that's your problem - the database isn't running

### Check Backend Status
- Click on the **backend** service
- Click **"Deployments"** tab
- Latest deployment status:
  - 🔴 **Failed** or **Crashed** = Environment variable issue
  - 🟡 **Building** = Wait for it to complete
  - 🟢 **Active** but 502 errors = Port/startup issue

---

## Step 2: View Error Logs (IMPORTANT)

Before adding variables, let's see what the actual error is:

1. In **backend** service → **Deployments** tab
2. Click on the **latest deployment**
3. Click **"View Logs"** button
4. Scroll to find error messages (usually at the bottom)

**Copy the error message** - We'll need it if the fix below doesn't work.

**Common errors you might see:**
- `KeyError: 'DATABASE_URL'` → Missing DATABASE_URL
- `KeyError: 'SECRET_KEY'` → Missing SECRET_KEY
- `could not connect to server` → Database not linked
- `ModuleNotFoundError` → Build dependency issue (unlikely)
- `relation "users" does not exist` → Normal on first run

---

## Step 3: Add Environment Variables

### Go to Variables Tab
1. In **backend** service, click **"Variables"** tab
2. You'll see a list of current variables (if any)

### Add These Variables (Copy-Paste)

Click **"+ New Variable"** for each one:

#### Variable 1: DATABASE_URL
```
Name: DATABASE_URL
Value: ${{Postgres.DATABASE_URL}}
```
**Important:**
- Click **"Variable Reference"** instead of "Raw Editor"
- Select your **Postgres** service from dropdown
- Select **DATABASE_URL** from the list
- This creates a reference to your database

#### Variable 2: SECRET_KEY
```
Name: SECRET_KEY
Value: <SEE GENERATED VALUE BELOW>
```

**Your Generated SECRET_KEY:**
```
d29e43b5059126da6dda9a061609a329c827a638eb43947cff69f115f4fbdd0a
```
**Copy the line above ↑**

#### Variable 3: OPENAI_API_KEY
```
Name: OPENAI_API_KEY
Value:
```
**Note:** Leave empty for now (app will run without AI features)

If you have an OpenAI API key:
```
Value: sk-proj-...your-key...
```

#### Variable 4: ENVIRONMENT
```
Name: ENVIRONMENT
Value: production
```

---

## Step 4: Verify Database is Linked

### Check PostgreSQL Service
1. Go back to project overview (click project name at top)
2. Click on **PostgreSQL** service
3. Click **"Variables"** tab
4. You should see variables like:
   - `PGHOST`
   - `PGPORT`
   - `PGDATABASE`
   - `PGUSER`
   - `PGPASSWORD`
   - `DATABASE_URL`

### Ensure Backend Can See Database
1. Go back to **backend** service
2. Click **"Settings"** tab
3. Scroll to **"Service Connections"**
4. You should see your **Postgres** service listed
5. If not, click **"+ New Connection"** and select Postgres

---

## Step 5: Trigger Redeploy

After adding all variables:

### Option A: Automatic Redeploy
Railway usually redeploys automatically when you add/change variables.
- Watch the **Deployments** tab
- A new deployment should start within 30 seconds
- Wait 3-5 minutes for it to complete

### Option B: Manual Redeploy (if automatic doesn't start)
1. Go to **Deployments** tab
2. Click on the latest deployment
3. Click **"Redeploy"** button at top right

### Option C: Push Empty Commit (from your local machine)
```bash
git commit --allow-empty -m "🚀 Trigger Railway redeploy"
git push origin main
```

---

## Step 6: Monitor Deployment

### Watch the Logs
1. **Deployments** tab → Click latest deployment → **"View Logs"**
2. Watch for these messages:

**✅ Success Messages:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**🔴 Error Messages:**
```
sqlalchemy.exc.OperationalError → Database connection failed
KeyError: 'DATABASE_URL' → Variable not set correctly
ModuleNotFoundError → Missing dependency
```

### Deployment Timeline
- **0-30 seconds:** Starting build
- **1-2 minutes:** Installing dependencies
- **2-3 minutes:** Building application
- **3-4 minutes:** Deploying
- **4-5 minutes:** Should be live!

---

## Step 7: Test the Deployment

### Test 1: Health Endpoint
```bash
curl https://mortgage-crm-production-7a9a.up.railway.app/health
```

**Expected response:**
```json
{"status": "healthy"}
```
or similar success message

**If you get 502:** Deployment isn't working - check logs again

### Test 2: API Documentation
Open in browser:
```
https://mortgage-crm-production-7a9a.up.railway.app/docs
```

**Expected:** FastAPI Swagger UI documentation page

### Test 3: Check Deployment Status
In Railway dashboard:
- Backend service should show: 🟢 **"Active"**
- Under Deployments: Latest should be 🟢 **"Active"**

---

## 🎯 Success Checklist

- [ ] PostgreSQL service is Active
- [ ] DATABASE_URL variable references Postgres service
- [ ] SECRET_KEY variable is set (64 characters)
- [ ] OPENAI_API_KEY variable exists (can be empty)
- [ ] ENVIRONMENT variable set to "production"
- [ ] New deployment triggered
- [ ] Deployment shows "Active" status
- [ ] Logs show "Application startup complete"
- [ ] Health endpoint returns 200 OK
- [ ] API docs page loads

---

## 🚨 If It Still Doesn't Work

### Scenario 1: Still Getting 502
**Check:**
1. Logs show "Application startup complete"?
   - YES → Port issue (check PORT variable)
   - NO → Startup failing (check error in logs)

2. Database connected?
   - Go to Postgres service → **"Data"** tab
   - Should show database is accessible

3. Try different Railway region?
   - Settings → General → Region
   - Try changing and redeploying

### Scenario 2: Database Connection Error
**Fix:**
```bash
# In Railway Variables, remove and re-add DATABASE_URL
1. Delete DATABASE_URL variable
2. Add it again as a Reference to Postgres
3. Wait for redeploy
```

### Scenario 3: Build Succeeds but App Crashes
**Check:**
1. **Dockerfile** exists in backend folder? ✅
2. **requirements.txt** is valid? ✅
3. PORT variable set? (Railway sets this automatically)
4. Check if you have custom START_COMMAND set (should be empty)

### Scenario 4: First Deployment Takes Forever
**Normal for first deploy:**
- Creates database tables
- Generates sample data
- Can take 5-10 minutes
- Subsequent deploys are faster (2-3 minutes)

---

## 📞 Quick Commands

### Test Backend
```bash
# Health check
curl https://mortgage-crm-production-7a9a.up.railway.app/health

# API docs (open in browser)
open https://mortgage-crm-production-7a9a.up.railway.app/docs
```

### Redeploy from Local
```bash
git commit --allow-empty -m "Redeploy"
git push
```

### Check Railway Logs (if CLI installed)
```bash
railway login
railway link
railway logs
```

---

## 🎊 After Railway is Fixed

Once you see ✅ **"Application startup complete"** in logs:

### Immediate Next Steps:
1. **Test Frontend Connection**
   - Go to: https://mortgage-crm-nine.vercel.app
   - Try login: `demo@test.com` / `demo123`
   - Should redirect to dashboard

2. **Verify Vercel Environment**
   - Go to: https://vercel.com/dashboard
   - Click project → Settings → Environment Variables
   - Ensure: `REACT_APP_API_URL = https://mortgage-crm-production-7a9a.up.railway.app`

3. **Test API Endpoints**
   - Go to: https://mortgage-crm-production-7a9a.up.railway.app/docs
   - Try the `/token` endpoint with demo credentials
   - Try the `/api/v1/dashboard` endpoint

### Optional Integrations:
After everything works, you can add:
- Microsoft Graph API (see `update-microsoft-integration.sh`)
- OpenAI API key for AI features
- Twilio for SMS
- Stripe for payments

---

## 💡 Pro Tips

1. **Watch the Logs in Real-Time**
   - Keep logs open while deploying
   - Errors appear immediately

2. **Railway Auto-Deploys on Git Push**
   - Every push to main triggers a deploy
   - Good for continuous deployment
   - Be careful with broken code!

3. **Environment Variable Changes Auto-Redeploy**
   - Adding/changing variables triggers redeploy
   - No need to manually trigger

4. **Database Persists Between Deploys**
   - Your data is safe
   - Database is separate from backend
   - Can reset backend without losing data

5. **Use Railway CLI for Faster Debugging**
   ```bash
   npm install -g @railway/cli
   railway login
   railway link
   railway logs --follow
   ```

---

**Last Updated:** November 7, 2025
**Status:** Ready to execute
**Time Required:** 10-15 minutes

---

🚀 **Ready? Go to Step 1 and start fixing Railway!**
