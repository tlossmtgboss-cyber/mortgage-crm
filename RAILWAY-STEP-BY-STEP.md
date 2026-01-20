# 🎯 Railway Setup - Exact Clicks Step-by-Step

## Follow these instructions exactly - I'll guide you through every click!

---

## STEP 1: Open Railway Dashboard

1. **Open your browser**
2. **Go to:** https://railway.app/dashboard
3. **Log in** if you're not already

You should see a page with your projects.

**✋ STOP HERE** - Do you see your "mortgage-crm" project?
- ✅ YES → Continue to Step 2
- ❌ NO → Let me know and we'll troubleshoot

---

## STEP 2: Open Your Project

1. **Click** on the **"mortgage-crm"** project (or whatever your project is named)

You should now see:
- A PostgreSQL service (database icon)
- A backend service (your FastAPI app)
- Maybe other services

**✋ STOP HERE** - Do you see these two services?
- ✅ YES → Continue to Step 3
- ❌ NO → Take a screenshot and let me know what you see

---

## STEP 3: Check PostgreSQL Database

1. **Click** on the **PostgreSQL** service (the database one)
2. Look at the top - it should say **"Active"** with a green dot

**✋ STOP HERE** - Is PostgreSQL showing "Active"?
- ✅ YES → Click the **← back arrow** at top left, then continue to Step 4
- ❌ NO (says "Crashed" or "Failed") → This is the problem! Let me know.

---

## STEP 4: Open Backend Service Variables

1. **Click** on the **backend** service (your FastAPI app)
2. You'll see several tabs at the top:
   - Deployments
   - Metrics
   - **Variables** ← Click this one
   - Settings
   - etc.
3. **Click** the **"Variables"** tab

You should now see a page that shows environment variables.

**✋ STOP HERE** - Describe what you see:
- Do you see any variables already listed?
- Is there a **"+ New Variable"** or **"Add Variable"** button?

---

## STEP 5: Add DATABASE_URL (Special Method)

**This one is SPECIAL - we use a reference, not a raw value!**

### Click "+ New Variable"

You should see a dialog with tabs:
- **Variable** (Raw Editor)
- **Variable Reference** ← Select this tab!

### Select "Variable Reference" Tab

1. **Click** on the **"Variable Reference"** tab (NOT "Variable")

You should now see:
- A dropdown to select a service
- A dropdown to select a variable

### Select the Reference

1. **Service dropdown:** Select **"Postgres"** (or whatever your PostgreSQL service is named)
2. **Variable dropdown:** Select **"DATABASE_URL"**
3. **Click** the **"Add"** button

**✋ STOP HERE** - Did it add successfully?
- ✅ YES → You should see `DATABASE_URL` in the list with a value like `${{Postgres.DATABASE_URL}}`
- ❌ NO → What error did you get?

---

## STEP 6: Add SECRET_KEY

### Click "+ New Variable" again

Now we'll use the normal method:

1. **Click** the **"Variable"** tab (Raw Editor - this is the default)

You should see two fields:
- **Variable Name**
- **Variable Value**

### Enter the Values

**Variable Name:**
```
SECRET_KEY
```

**Variable Value** (copy this ENTIRE line):
```
d29e43b5059126da6dda9a061609a329c827a638eb43947cff69f115f4fbdd0a
```

### Add It

1. **Click** the **"Add"** button

**✋ STOP HERE** - Did it add successfully?
- ✅ YES → You should see `SECRET_KEY` in the list with value starting "d29e43b5..."
- ❌ NO → What happened?

---

## STEP 7: Add OPENAI_API_KEY

### Click "+ New Variable" again

**Variable Name:**
```
OPENAI_API_KEY
```

**Variable Value:**
```
(leave this completely empty - just blank)
```

OR if you have an OpenAI API key:
```
sk-proj-your-actual-key-here
```

### Add It

1. **Click** the **"Add"** button

**✋ STOP HERE** - Added?
- ✅ YES → Continue to Step 8
- ❌ NO → Let me know the issue

---

## STEP 8: Add ENVIRONMENT

### Click "+ New Variable" again

**Variable Name:**
```
ENVIRONMENT
```

**Variable Value:**
```
production
```

### Add It

1. **Click** the **"Add"** button

**✋ STOP HERE** - Added?
- ✅ YES → Continue to Step 9
- ❌ NO → Let me know

---

## STEP 9: Verify All Variables

You should now see **4 variables** in the list:

1. **DATABASE_URL** = `${{Postgres.DATABASE_URL}}` (or shows as reference)
2. **SECRET_KEY** = `d29e43b5...` (shows first few characters, rest is hidden)
3. **OPENAI_API_KEY** = (empty or your key)
4. **ENVIRONMENT** = `production`

**✋ STOP HERE** - Do you see all 4?
- ✅ YES → Continue to Step 10
- ❌ NO → Which ones are missing?

---

## STEP 10: Watch for Auto-Redeploy

**Railway automatically redeploys when you add/change variables!**

### Go to Deployments Tab

1. **Click** the **"Deployments"** tab at the top

You should see:
- A new deployment starting (might say "Building" or "Deploying")
- Or it might already be deploying

### What You'll See

The status will change like this:
1. **🟡 Queued** → Waiting to start
2. **🟡 Building** → Installing dependencies
3. **🟡 Deploying** → Starting the app
4. **🟢 Active** → Running! ← This is what we want
   OR
5. **🔴 Failed** → Something went wrong ← Let me know if you see this

**This takes 3-5 minutes.** ⏱️

**✋ STOP HERE and WAIT** - Watch the deployment status
- After 3-5 minutes, what status do you see?

---

## STEP 11: Check the Logs

### While Deployment is Running (or after)

1. **Click** on the latest deployment (the top one in the list)
2. You'll see a **"View Logs"** button
3. **Click** "View Logs"

### What to Look For

**✅ GOOD SIGNS (Success!):**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**🔴 BAD SIGNS (Errors):**
```
KeyError: 'DATABASE_URL'
sqlalchemy.exc.OperationalError
ModuleNotFoundError
```

**✋ STOP HERE** - What do you see in the logs?
- Copy the last 10-20 lines and share them with me

---

## STEP 12: Test the Backend

### Get Your Railway URL

1. In the backend service, look for your **public domain**
2. It should be something like: `api.perenniaai.com`
3. Copy this URL

### Test in Terminal

Open your terminal and run:

```bash
curl https://api.perenniaai.com/health
```

**Expected response:**
```json
{"status":"healthy"}
```
or
```json
{"status":"ok"}
```
or similar

**✋ STOP HERE** - What did you get?
- ✅ 200 OK with JSON response → **SUCCESS! 🎉**
- ❌ 502 Bad Gateway → Still not working, check logs
- ❌ Other error → Tell me what you got

### Test in Browser

Open your browser and go to:
```
https://api.perenniaai.com/docs
```

**Expected:** You should see the FastAPI Swagger UI documentation page

**✋ STOP HERE** - What do you see?
- ✅ API documentation page → **SUCCESS! 🎉**
- ❌ 502 error → Not working yet
- ❌ Other → Describe what you see

---

## 🎉 SUCCESS CHECKLIST

If everything worked, you should have:

- [✓] All 4 environment variables added to Railway
- [✓] Deployment status shows "Active" (green)
- [✓] Logs show "Application startup complete"
- [✓] Health endpoint returns 200 OK
- [✓] API docs page loads in browser

---

## 🚨 IF SOMETHING WENT WRONG

### Common Issues:

**1. Deployment shows "Failed"**
- Go to logs and copy the error message
- Share it with me

**2. Still getting 502 error**
- Check: Did DATABASE_URL get added as a **reference** (not raw text)?
- Check: Is PostgreSQL service "Active"?
- Try: Manual redeploy (click redeploy button)

**3. "Could not connect to database" error**
- Check: PostgreSQL service is running
- Check: DATABASE_URL is `${{Postgres.DATABASE_URL}}` (with double braces)
- Try: Remove and re-add DATABASE_URL variable

**4. Deployment stuck at "Building"**
- Wait 10 minutes (first deployment can take longer)
- If still stuck, try: Settings → General → Restart

---

## 📞 NEXT STEPS AFTER SUCCESS

Once the backend is working:

1. **Test Frontend Connection**
   - Go to: https://mortgage-crm-nine.vercel.app
   - Try to login with: `demo@test.com` / `demo123`

2. **Verify Vercel Environment Variable**
   - Go to: https://vercel.com/dashboard
   - Check `REACT_APP_API_URL` is set

3. **(Optional) Setup Microsoft Integration**
   - Run: `./update-microsoft-integration.sh`

---

## 💬 TELL ME WHERE YOU ARE

At which step are you stuck? Share:
1. The step number you're on
2. What you see on the screen
3. Any error messages

I'll help you troubleshoot from there! 🚀
