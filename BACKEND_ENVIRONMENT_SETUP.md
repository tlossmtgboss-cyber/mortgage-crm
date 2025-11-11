# 🔐 Backend Environment Variables Setup Guide

## Current Deployment Status

✅ **All code is LIVE** - Frontend and backend are deployed!
✅ **Native phone integration works NOW** - No setup required!
✅ **Twilio integration ready** - Just add variables below

---

## 📱 Two Levels of Phone Integration

### Level 1: Native Phone Integration (Already Active!)
**Status:** ✅ **Working NOW - No backend setup needed**

**What works:**
- Click-to-call (tel: protocol)
- SMS/Text messaging (sms: protocol)
- Email links (mailto: protocol)

**How it works:**
- Uses your phone's native apps
- Works with ANY carrier (Verizon, AT&T, T-Mobile, etc.)
- No backend configuration required
- Already deployed and working!

**Test it now:**
1. Go to: `https://mortgage-crm-git-main-tim-loss-projects.vercel.app/verizon-test`
2. Click any phone number in your leads list
3. Your phone will open instantly!

---

### Level 2: Advanced Twilio Integration (Optional)
**Status:** ⚠️ **Requires backend environment variables**

**Additional features:**
- Send SMS directly from CRM (no phone needed)
- Bulk SMS campaigns
- SMS templates and automation
- Track delivery status
- SMS conversation history in CRM
- Port your Verizon number to Twilio

---

## 🔧 Backend Environment Variables Needed

### Required Variables for Twilio (Optional Advanced Features)

Add these to your **Railway backend** environment variables:

```bash
# Twilio Configuration (Optional - for advanced SMS features)
TWILIO_ACCOUNT_SID=your_account_sid_here
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1your_phone_number_here
```

### How to Get Twilio Credentials

#### Step 1: Sign Up for Twilio
1. Go to: https://www.twilio.com/try-twilio
2. Sign up for a free account ($15 credit included)
3. Verify your email and phone

#### Step 2: Get Your Credentials
1. Log in to Twilio Console: https://console.twilio.com
2. From the dashboard, copy:
   - **Account SID** (starts with AC...)
   - **Auth Token** (click to reveal)

#### Step 3: Get a Phone Number
1. In Twilio Console, go to: **Phone Numbers** → **Buy a Number**
2. Choose a number (search by area code if desired)
3. Purchase the number (uses your free credit)
4. Copy the phone number in E.164 format (e.g., +15551234567)

#### Step 4: Add to Railway Backend
1. Go to your Railway dashboard: https://railway.app
2. Select your backend service
3. Go to **Variables** tab
4. Add the three environment variables:
   ```
   TWILIO_ACCOUNT_SID = ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN = your_32_character_token
   TWILIO_PHONE_NUMBER = +15551234567
   ```
5. Click **Save**
6. Railway will automatically restart your backend

---

## 🎯 Current Backend Variables (Full List)

Here are ALL the environment variables your backend should have:

### Essential (Already Set)
```bash
# Database
DATABASE_URL=postgresql://...

# Security
SECRET_KEY=your_secret_key_here
JWT_SECRET_KEY=your_jwt_secret_here

# API Keys
API_KEY=your_api_key_here
```

### Optional Integrations
```bash
# Twilio (SMS - Optional)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+15551234567

# SendGrid (Email - Optional)
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxx
SENDGRID_FROM_EMAIL=noreply@yourdomain.com

# OpenAI (AI Features - Optional)
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx

# Anthropic Claude (AI Features - Optional)
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxx

# Microsoft Graph (Calendar/Email - Optional)
MICROSOFT_CLIENT_ID=your_client_id
MICROSOFT_CLIENT_SECRET=your_client_secret
MICROSOFT_TENANT_ID=your_tenant_id

# Stripe (Payments - Optional)
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxxxxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_live_xxxxxxxxxxxxxxxxxxxx

# Calendly (Scheduling - Optional)
CALENDLY_API_KEY=your_calendly_api_key
```

---

## 📋 Quick Setup Checklist

### For Native Phone Integration (Works Now!)
- [x] Code deployed to production
- [x] Frontend routes configured
- [x] Test page available at /verizon-test
- [ ] Test the features yourself

### For Twilio Integration (Optional)
- [ ] Sign up for Twilio account
- [ ] Get Account SID
- [ ] Get Auth Token
- [ ] Purchase/get phone number
- [ ] Add variables to Railway backend
- [ ] Restart backend service
- [ ] Test SMS sending from CRM

---

## 🚀 How to Add Variables to Railway

### Method 1: Railway Dashboard (Recommended)
1. Go to: https://railway.app/dashboard
2. Select your project: **mortgage-crm**
3. Click on your **backend service**
4. Click **Variables** tab
5. Click **+ New Variable**
6. Add variable name and value
7. Click **Add**
8. Railway auto-restarts the service

### Method 2: Railway CLI
```bash
# Install Railway CLI if you haven't
npm i -g @railway/cli

# Login to Railway
railway login

# Link to your project
railway link

# Set variables
railway variables set TWILIO_ACCOUNT_SID="ACxxxxx..."
railway variables set TWILIO_AUTH_TOKEN="your_token"
railway variables set TWILIO_PHONE_NUMBER="+15551234567"
```

### Method 3: Environment File (Local Development)
1. In your backend folder, create `.env` file
2. Add variables:
   ```bash
   TWILIO_ACCOUNT_SID=ACxxxxx...
   TWILIO_AUTH_TOKEN=your_token
   TWILIO_PHONE_NUMBER=+15551234567
   ```
3. For production, use Railway dashboard (Method 1)

---

## 🔍 Verify Backend Variables

### Check if Twilio is configured:
```bash
# SSH into Railway backend or check logs
railway logs

# Look for this line in logs:
# "Twilio SMS initialized successfully"

# If you see:
# "Twilio SMS credentials not configured"
# Then variables are not set yet
```

### Test Twilio from CRM:
1. Add Twilio variables to Railway
2. Wait for backend to restart (30 seconds)
3. Go to your CRM: `/verizon-test`
4. Look at **Integration Status** section
5. **Twilio SMS API** should show "Active" ✅

---

## 💡 Which Variables Do You Need?

### Minimum to Get Started (Working Now!)
**Answer: NONE!** Native phone integration works immediately.

### To Enable Twilio SMS (Optional)
**Answer: 3 variables**
- TWILIO_ACCOUNT_SID
- TWILIO_AUTH_TOKEN
- TWILIO_PHONE_NUMBER

### To Enable All Integrations
**Answer:** Add variables as needed for each service you want to use.

---

## 🎯 Recommended Setup Order

### 1. Start with Native Integration (Today!)
✅ Already working - no setup needed!
- Test at: `/verizon-test`
- Use click-to-call and SMS buttons
- Works with your Verizon service

### 2. Add Twilio (When Ready)
- Sign up for Twilio
- Add 3 environment variables
- Get advanced SMS features

### 3. Add Other Services (As Needed)
- SendGrid for email campaigns
- OpenAI/Claude for AI features
- Microsoft Graph for calendar
- Stripe for payments

---

## 🆘 Troubleshooting

### "I added Twilio variables but it's not working"
1. **Check Railway logs** for startup errors
2. **Verify variables are correct** (no typos, spaces, or quotes)
3. **Wait 30 seconds** for backend to restart
4. **Check phone number format** (must be E.164: +15551234567)

### "Where do I add these variables?"
- **Production:** Railway dashboard → Variables tab
- **Local:** Create `.env` file in backend folder

### "Do I need Twilio to use phone features?"
**No!** Native phone integration works right now without Twilio.
Twilio is only for advanced features like bulk SMS and in-CRM messaging.

### "Can I use my existing Verizon number with Twilio?"
**Yes!** You can port your Verizon number to Twilio.
- Takes 7-10 business days
- Keeps your same number
- Contact Twilio support for assistance

---

## ✅ Current Status Summary

| Feature | Status | Requires Backend Setup? |
|---------|--------|------------------------|
| Click-to-Call | ✅ Live Now | ❌ No |
| SMS/Text | ✅ Live Now | ❌ No |
| Email Links | ✅ Live Now | ❌ No |
| Test Page | ✅ Live Now | ❌ No |
| Twilio SMS API | ⚠️ Needs Setup | ✅ Yes (3 variables) |
| Bulk SMS | ⚠️ Needs Setup | ✅ Yes (Twilio) |
| SMS Templates | ⚠️ Needs Setup | ✅ Yes (Twilio) |

---

## 🎉 You're Ready!

**Native phone integration is LIVE and working right now!**

Test it at: https://mortgage-crm-git-main-tim-loss-projects.vercel.app/verizon-test

**Want Twilio?** Just add the 3 variables above to Railway and you're set!

---

## 📞 Need Help?

- Check the test page: `/verizon-test`
- Review logs in Railway dashboard
- Verify environment variables are set correctly
- Make sure backend has restarted after adding variables

**Happy integrating!** 📱
