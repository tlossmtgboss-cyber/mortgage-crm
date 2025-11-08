# 🚨 Railway Deployment Diagnostics Guide

## Current Issue: 502 Bad Gateway Error

Your Railway backend is returning 502 errors, which means the application is not starting properly.

---

## 📋 Step 1: Check Railway Logs

### Access Logs in Railway Dashboard

1. **Go to Railway Dashboard**
   ```
   https://railway.app/dashboard
   ```

2. **Navigate to Your Project**
   - Click on "mortgage-crm" project
   - Click on the "backend" service

3. **View Deployment Logs**
   - Click "Deployments" tab
   - Click on the latest deployment
   - Click "View Logs"

### What to Look For in Logs

#### ✅ Good Signs (App Starting Successfully)
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

#### 🔴 Common Error Patterns

**Database Connection Errors:**
```
sqlalchemy.exc.OperationalError
could not connect to server
connection refused
FATAL: password authentication failed
```
**Solution**: Check DATABASE_URL is properly set and linked to Postgres service

**Missing Environment Variables:**
```
KeyError: 'DATABASE_URL'
KeyError: 'SECRET_KEY'
```
**Solution**: Add missing environment variables in Railway Variables tab

**Import Errors:**
```
ModuleNotFoundError: No module named 'X'
ImportError: cannot import name 'X'
```
**Solution**: Ensure requirements.txt includes all dependencies

**Circular Import Error:**
```
ImportError: cannot import name 'X' from partially initialized module
```
**Solution**: Already fixed in commit a1b5d80 - redeploy if needed

**Port Binding Issues:**
```
OSError: [Errno 98] Address already in use
```
**Solution**: Ensure using Railway's $PORT variable

**Database Schema Issues:**
```
sqlalchemy.exc.ProgrammingError
relation "users" does not exist
```
**Solution**: Database tables need to be created on first run

---

## 📋 Step 2: Check Railway Environment Variables

### Required Variables

Go to: Railway Dashboard → Your Project → backend service → **Variables** tab

Verify these are set:

```bash
# REQUIRED
DATABASE_URL = ${{Postgres.DATABASE_URL}}
SECRET_KEY = <64-character hex string>
OPENAI_API_KEY = sk-...

# RECOMMENDED
ENVIRONMENT = production
PORT = ${{PORT}}  # Usually auto-set by Railway
```

### How to Add DATABASE_URL Reference

1. Click "+ New Variable"
2. Click "Reference" tab
3. Select your Postgres database service
4. Select "DATABASE_URL"
5. Click "Add"

### Generate SECRET_KEY

Run this locally and copy the output:
```bash
openssl rand -hex 32
```

Then add it to Railway Variables:
```
SECRET_KEY = <paste-the-generated-key-here>
```

---

## 📋 Step 3: Check Database Service

### Verify PostgreSQL Database

1. In Railway Dashboard → Your Project
2. Verify you have a PostgreSQL database service
3. Click on the Postgres service
4. Check that it's showing "Active" status

### If No Database Exists

1. Click "+ New" in your project
2. Select "Database" → "Add PostgreSQL"
3. Wait for it to provision
4. Link it to your backend service (see Step 2)

---

## 📋 Step 4: Check Recent Deployments

### View Deployment History

1. Railway Dashboard → backend service → Deployments
2. Check recent deployments

### Common Issues

**Build Failed:**
- Red "Failed" status
- Check build logs for Python package errors
- Ensure requirements.txt is valid

**Build Succeeded but Crashed:**
- Green "Active" briefly, then crashes
- This is your current issue (502)
- Check runtime logs for startup errors

**Deployment Pending:**
- Orange "Building" or "Deploying" status
- Wait for it to complete
- Should take 2-5 minutes

---

## 📋 Step 5: Trigger Manual Redeploy

Sometimes Railway gets stuck. Try a manual redeploy:

### Option A: From Dashboard

1. Railway Dashboard → backend service → Deployments
2. Click on latest deployment
3. Click "Redeploy" button
4. Wait 3-5 minutes

### Option B: Push Empty Commit

From your local terminal:
```bash
git commit --allow-empty -m "Trigger Railway redeploy"
git push
```

---

## 🔍 Using Railway CLI (Advanced)

### Install Railway CLI

```bash
npm install -g @railway/cli
```

### Login and View Logs

```bash
# Login to Railway
railway login

# Link to your project
railway link

# View live logs
railway logs

# Check service status
railway status
```

---

## 📋 Step 6: Local Testing Script

We've created a script to help you test locally. Run this:

```bash
# From the mortgage-crm directory
cd backend
python verify_env.py
```

This will:
- ✓ Check all required environment variables
- ✓ Verify configuration settings
- ✓ Show which integrations are enabled
- ✓ Provide setup instructions

---

## 🐛 Common 502 Error Causes & Solutions

### 1. Missing DATABASE_URL
**Symptom**: App crashes immediately on startup
**Solution**:
```bash
# In Railway Variables tab
DATABASE_URL = ${{Postgres.DATABASE_URL}}
```

### 2. Database Not Connected
**Symptom**: "could not connect to server"
**Solution**:
- Ensure Postgres service is running
- Check DATABASE_URL reference is correct
- Verify Postgres service is in same project

### 3. Missing SECRET_KEY
**Symptom**: KeyError or validation error
**Solution**:
```bash
# Generate locally
openssl rand -hex 32
# Add to Railway Variables
SECRET_KEY = <generated-value>
```

### 4. Import/Circular Import Error
**Symptom**: "cannot import name" or "partially initialized module"
**Solution**: Already fixed in latest code (commit a1b5d80)
- Trigger redeploy to get latest code

### 5. Database Tables Don't Exist
**Symptom**: "relation does not exist"
**Solution**:
- Tables are created automatically on first startup
- Check logs to ensure startup completes
- May need to wait for initial migration

### 6. Port Configuration Issue
**Symptom**: App tries to bind to wrong port
**Solution**: Railway auto-sets PORT variable
- Don't override it unless necessary
- App should use: `os.getenv("PORT", "8000")`

---

## 📝 Diagnostic Checklist

Use this to systematically check everything:

- [ ] Railway dashboard shows backend service as "Active"
- [ ] PostgreSQL database service exists and is "Active"
- [ ] DATABASE_URL variable is set (references Postgres)
- [ ] SECRET_KEY variable is set (64+ character hex string)
- [ ] OPENAI_API_KEY variable is set
- [ ] Latest deployment build succeeded (green checkmark)
- [ ] Deployment logs show "Application startup complete"
- [ ] Health endpoint works: `curl https://your-app.up.railway.app/health`
- [ ] API docs accessible: `curl https://your-app.up.railway.app/docs`
- [ ] No error messages in deployment logs

---

## 🆘 If Still Not Working

### Get Full Diagnostic Report

1. **Export Railway logs**:
   - Railway Dashboard → Deployments → View Logs
   - Copy the full log output

2. **Check deployment settings**:
   - Railway Dashboard → backend service → Settings
   - Verify:
     - Build command: Auto-detected (Docker)
     - Start command: Auto-detected from Dockerfile
     - Root directory: `/backend` or blank

3. **Verify Dockerfile**:
   - Check `backend/Dockerfile` exists
   - Should use: `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]`

4. **Check Network Tab**:
   - Railway Dashboard → backend service → Settings → Networking
   - Public domain should be enabled

---

## 📞 Quick Commands Reference

```bash
# Local environment check
cd backend && python verify_env.py

# Test local startup
cd backend && uvicorn main:app --reload

# Railway CLI logs
railway logs

# Railway CLI redeploy
railway up

# Generate new SECRET_KEY
openssl rand -hex 32

# Check if backend is reachable
curl -I https://mortgage-crm-production-7a9a.up.railway.app/health

# Check API docs
curl https://mortgage-crm-production-7a9a.up.railway.app/docs
```

---

## ✅ Next Steps After Railway is Fixed

Once you see "Application startup complete" in Railway logs:

1. ✅ Test health endpoint
2. ✅ Test API docs
3. ✅ Update Vercel REACT_APP_API_URL (if needed)
4. ✅ Test login from frontend
5. ✅ Configure Microsoft integration URLs
6. ✅ Test end-to-end flow

---

## 📊 Expected Healthy Logs

When everything is working, you should see:

```
INFO:     Will watch for changes in these directories: ['/app']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [1] using StatReload
INFO:     Started server process [8]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

Then when accessed:
```
INFO:     123.456.789.0:12345 - "GET /health HTTP/1.1" 200 OK
INFO:     123.456.789.0:12345 - "GET /docs HTTP/1.1" 200 OK
```

---

**Good luck! 🚀**
