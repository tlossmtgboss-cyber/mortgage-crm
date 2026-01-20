# 🚀 Vapi Activation Steps - Get Calls Working in 5 Minutes

## Current Status

✅ **Vapi integration is ALREADY BUILT in your codebase!**

Your system has:
- ✅ Vapi webhook endpoint: `/api/vapi/webhook`
- ✅ Vapi routes included in FastAPI
- ✅ Sam assistant configuration ready
- ✅ CRM functions (create tasks, schedule appointments, submit pre-approvals)
- ✅ AI Receptionist Dashboard integration

---

## What You Need To Do

### Step 1: Get Your Vapi Assistant ID (3 minutes)

#### Option A: You may already have it
Check if you have a Vapi assistant ID saved somewhere. Look for:
- Assistant ID starting with `asst_`
- Or check your Vapi dashboard: https://dashboard.vapi.ai

#### Option B: Create New Assistant via Vapi Dashboard
1. Go to https://dashboard.vapi.ai
2. Sign in (or create account)
3. Click **"Assistants"**
4. Click **"Create Assistant"**
5. Click **"Import JSON"**
6. Upload this file: `/Users/timothyloss/my-project/mortgage-crm/backend/vapi_assistant_final.json`
7. Click **"Create"**
8. **Copy the Assistant ID** (starts with `asst_`)

---

### Step 2: Add Vapi API Key to Railway (1 minute)

```bash
# Get your Vapi API key from dashboard
# Then add it to Railway:

railway variables --set VAPI_API_KEY=your_vapi_api_key_here
```

Or via Railway Dashboard:
1. Go to https://railway.app
2. Select your project
3. Click **"Variables"**
4. Add new variable:
   - **Name:** `VAPI_API_KEY`
   - **Value:** Your Vapi API key

---

### Step 3: Update Twilio Webhook (1 minute)

1. Go to https://console.twilio.com/us1/develop/phone-numbers/manage/incoming
2. Click your number: **+1 (832) 648-2297**
3. Under **"Voice Configuration"**:
   - When a call comes in: **Webhook**
   - URL: `https://api.vapi.ai/call/twilio?assistantId=YOUR_ASSISTANT_ID`
   - HTTP Method: **POST**
4. **Status Callback URL** (IMPORTANT for logging to your dashboard):
   - URL: `https://api.perenniaai.com/api/vapi/webhook`
   - HTTP Method: **POST**
5. Click **"Save"**

**Replace `YOUR_ASSISTANT_ID` with your actual assistant ID from Step 1**

---

### Step 4: Configure Vapi Webhooks (1 minute)

1. In Vapi dashboard, go to **"Settings"** → **"Webhooks"**
2. Add webhook URL:
   ```
   https://api.perenniaai.com/api/vapi/webhook
   ```
3. Select events:
   - ✅ `call.started`
   - ✅ `call.ended`
   - ✅ `tool-calls.*`
   - ✅ `transcript.update`
4. Click **"Save"**

---

### Step 5: Test! (30 seconds)

**Call +1 (832) 648-2297**

You should hear:
- Sam answers immediately
- Natural conversation
- Can create tasks, schedule appointments, submit pre-approvals

Then verify:
1. **Vapi Dashboard** - See call in "Calls" section
2. **Your AI Receptionist Dashboard** - Call logged automatically
3. **CRM** - Tasks/appointments created if requested during call

---

## What Your Assistant Does

**Sam can:**
- ✅ Greet callers warmly
- ✅ Collect pre-approval applications over the phone
- ✅ Schedule appointments using your CRM's available time slots
- ✅ Create callback tasks with priority levels
- ✅ Answer mortgage product questions
- ✅ Provide Calendly links for discovery calls

**Functions integrated:**
1. `create_task` - Create callbacks in your CRM
2. `schedule_appointment` - Book phone appointments
3. `get_available_time_slots` - Check availability
4. `submit_preapproval_application` - Submit applications to CRM
5. `schedule_calendly_appointment` - Provide Calendly scheduling links

All calls are automatically logged to your **AI Receptionist Dashboard**.

---

## Quick Command Reference

### Check if Vapi API key is set:
```bash
railway variables | grep VAPI
```

### Set Vapi API key:
```bash
railway variables --set VAPI_API_KEY=your_key_here
```

### Trigger Railway redeploy (if needed):
```bash
railway redeploy --yes
```

### Test Vapi webhook:
```bash
curl -X POST https://api.perenniaai.com/api/vapi/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "type": "test",
      "call": {"id": "test123"}
    }
  }'
```

---

## Troubleshooting

### Issue: "Assistant not found"
- Make sure you copied the full assistant ID including `asst_` prefix
- Verify assistant exists in Vapi dashboard

### Issue: "Calls still drop"
- Check Twilio webhook URL is correct
- Verify it points to `api.vapi.ai`, not your Railway URL
- Make sure HTTP method is **POST**

### Issue: "Functions not working"
- Verify VAPI_API_KEY is set in Railway
- Check Railway logs: `railway logs | grep vapi`
- Ensure webhook URL is accessible publicly

### Issue: "Calls not appearing in dashboard"
- Verify Vapi webhook is configured (Step 4)
- Check webhook URL: `https://api.perenniaai.com/api/vapi/webhook`
- Check Railway logs for webhook events

---

## What Happens Next

Once configured:

### Immediate (Today):
✅ Calls work perfectly
✅ Sam answers with natural voice
✅ All CRM functions working
✅ Dashboard shows all calls

### Short-term (While you fix Voice OS):
✅ Use Vapi for all production calls
✅ Reliable, proven solution
✅ Keep building Voice OS in parallel

### Long-term (When Voice OS is ready):
✅ Deploy Voice OS to proper infrastructure (not Railway)
✅ Test Voice OS in parallel
✅ Gradually migrate traffic
✅ Keep Vapi as failover backup

---

## Your Configuration Summary

**Twilio Webhook:**
```
https://api.vapi.ai/call/twilio?assistantId=YOUR_ASSISTANT_ID
```

**Vapi → CRM Webhook:**
```
https://api.perenniaai.com/api/vapi/webhook
```

**CRM Function Endpoints:**
```
/api/vapi/functions/create-task
/api/vapi/functions/schedule-appointment
/api/vapi/functions/available-time-slots
/api/vapi/functions/submit-preapproval-application
/api/vapi/functions/schedule-calendly-appointment
```

**Dashboard:**
```
https://mortgage-crm-nine.vercel.app/ai-receptionist-dashboard
```

---

## 🎯 Next Steps

1. **Get Assistant ID** (from Vapi dashboard or create new)
2. **Add VAPI_API_KEY** to Railway
3. **Update Twilio webhook** to point to Vapi
4. **Configure Vapi webhooks** to point to your CRM
5. **Test call** +1 (832) 648-2297

**Total time: ~5 minutes**
**Result: Working AI receptionist immediately!**

---

Let me know when you have your Assistant ID and I'll help configure everything!
