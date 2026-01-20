# 🔐 Azure AD Setup - Step-by-Step Guide

## 📋 What You'll Need

- Microsoft 365 account (Work or School account)
- Admin access to Azure Portal
- 30 minutes of time

---

## 🎯 Step 1: Access Azure Portal

### 1.1 Open Azure Portal
- Go to: **https://portal.azure.com**
- Sign in with your Microsoft 365 account
- If you don't have an Azure account, you'll be prompted to create one (free)

### 1.2 Navigate to Azure Active Directory
1. In the Azure Portal home page
2. Look for **"Azure Active Directory"** in the left menu
3. Or use the search bar at top: type "Azure Active Directory"
4. Click on it

---

## 📝 Step 2: Register Your Application

### 2.1 Go to App Registrations
1. In Azure Active Directory, look at the left menu
2. Find and click **"App registrations"**
3. Click **"+ New registration"** button at the top

### 2.2 Fill Out Registration Form

**Name:**
```
Mortgage CRM Teams Integration
```

**Supported account types:**
- Select: **"Accounts in this organizational directory only (Single tenant)"**
- This means only your organization can use it

**Redirect URI:**
- Platform: **Web** (select from dropdown)
- URL:
```
https://api.perenniaai.com/auth/microsoft/callback
```

### 2.3 Register
1. Click **"Register"** button at bottom
2. Wait a few seconds for the app to be created

---

## 🆔 Step 3: Copy Application IDs

You'll now see your app's overview page. **COPY THESE VALUES:**

### 3.1 Application (client) ID
- Look for **"Application (client) ID"**
- It looks like: `12345678-1234-1234-1234-123456789012`
- Click the **copy icon** 📋 next to it
- **Paste it in a notepad** - you'll need this later

### 3.2 Directory (tenant) ID
- Look for **"Directory (tenant) ID"**
- It looks like: `87654321-4321-4321-4321-210987654321`
- Click the **copy icon** 📋 next to it
- **Paste it in your notepad** next to the Client ID

**Your notepad should now have:**
```
Client ID: 12345678-1234-1234-1234-123456789012
Tenant ID: 87654321-4321-4321-4321-210987654321
```

---

## 🔑 Step 4: Create Client Secret

### 4.1 Navigate to Certificates & Secrets
1. In your app's left menu
2. Click **"Certificates & secrets"**
3. You'll see tabs for Certificates and Client secrets

### 4.2 Create New Secret
1. Click the **"Client secrets"** tab
2. Click **"+ New client secret"** button

### 4.3 Configure Secret
**Description:**
```
CRM Teams Integration Secret
```

**Expires:**
- Select: **24 months** (or longest option available)
- Or **Custom** if you want a specific date

### 4.4 Add and Copy Secret
1. Click **"Add"** button
2. **IMMEDIATELY** copy the **Value** (not the Secret ID)
3. The value looks like: `ABC123xyz789~AbC123XyZ.789_aBc`
4. **⚠️ IMPORTANT:** You can ONLY see this once! Copy it NOW!
5. **Paste it in your notepad**

**Your notepad should now have:**
```
Client ID: 12345678-1234-1234-1234-123456789012
Tenant ID: 87654321-4321-4321-4321-210987654321
Client Secret: ABC123xyz789~AbC123XyZ.789_aBc
```

---

## 🔐 Step 5: Set API Permissions

### 5.1 Navigate to API Permissions
1. In your app's left menu
2. Click **"API permissions"**
3. You'll see a list of current permissions

### 5.2 Add Microsoft Graph Permissions
1. Click **"+ Add a permission"** button
2. A panel will slide out from the right

### 5.3 Select Microsoft Graph
1. Click **"Microsoft Graph"** (the first big tile)
2. You'll see two options:
   - Delegated permissions
   - Application permissions
3. Click **"Application permissions"** (this is important!)

### 5.4 Add Calendar Permission
1. In the search box, type: `Calendars`
2. Expand **"Calendars"** section
3. Check the box for: **`Calendars.ReadWrite`**

### 5.5 Add OnlineMeetings Permission
1. In the search box, type: `OnlineMeetings`
2. Expand **"OnlineMeetings"** section
3. Check the box for: **`OnlineMeetings.ReadWrite.All`**

### 5.6 Add User Permission
1. In the search box, type: `User`
2. Expand **"User"** section
3. Check the box for: **`User.Read.All`**

### 5.7 Add Permissions
1. Click **"Add permissions"** button at bottom
2. You'll be back to the permissions list

### 5.8 Grant Admin Consent
**This is CRITICAL - don't skip this step!**

1. You'll see your 3 new permissions listed
2. They'll show "Not granted for [Your Organization]" in the Status column
3. Click the **"Grant admin consent for [Your Organization]"** button
4. A popup will ask: "Grant admin consent for the requested permissions?"
5. Click **"Yes"**
6. Wait a moment
7. The Status column should now show **green checkmarks** ✅ with "Granted for [Your Organization]"

**If you don't see "Grant admin consent" button:**
- You need admin privileges
- Contact your IT administrator
- Or sign in with an admin account

---

## ✅ Step 6: Verify Configuration

Your app is now configured! Let's verify:

### 6.1 Check Overview
1. Go back to **"Overview"** in left menu
2. Verify you see:
   - Application (client) ID ✅
   - Directory (tenant) ID ✅

### 6.2 Check Secrets
1. Go to **"Certificates & secrets"**
2. Verify you see:
   - Your client secret listed ✅
   - Expiration date shown ✅

### 6.3 Check Permissions
1. Go to **"API permissions"**
2. Verify you see all 3 permissions with **green checkmarks**:
   - ✅ Calendars.ReadWrite
   - ✅ OnlineMeetings.ReadWrite.All
   - ✅ User.Read.All
3. Status should say "Granted"

---

## 🚀 Step 7: Add to Railway

Now let's add these credentials to your Railway backend:

### 7.1 Open Railway Dashboard
1. Go to: **https://railway.app/dashboard**
2. Log in to Railway
3. Click your **mortgage-crm** project
4. Click your **backend** service

### 7.2 Go to Variables
1. Click the **"Variables"** tab at the top
2. You'll see your existing environment variables

### 7.3 Add Microsoft Variables
Click **"+ New Variable"** for each of these:

**Variable 1:**
```
Name: MICROSOFT_CLIENT_ID
Value: [paste your Application (client) ID from notepad]
```

**Variable 2:**
```
Name: MICROSOFT_CLIENT_SECRET
Value: [paste your Client Secret from notepad]
```

**Variable 3:**
```
Name: MICROSOFT_TENANT_ID
Value: [paste your Directory (tenant) ID from notepad]
```

### 7.4 Save
1. After adding all 3 variables
2. Railway will automatically restart your backend
3. **Wait 30-60 seconds** for restart to complete

---

## 🧪 Step 8: Test the Integration

### 8.1 Check Backend Logs
1. In Railway, click **"Deployments"** tab
2. Click the latest deployment (top one)
3. Click **"View Logs"**
4. Look for any errors related to Microsoft or Teams

### 8.2 Test in CRM
1. Go to: https://mortgage-crm-git-main-tim-loss-projects.vercel.app
2. Log in to your CRM
3. Open any lead's profile
4. Click **"👥 Teams Meeting"** button
5. Fill in the meeting details:
   - Meeting Type: Initial Consultation
   - Date: Tomorrow
   - Time: 10:00 AM
   - Duration: 30 minutes
   - Your email in attendees field
6. Click **"Create Meeting"**

**Expected Result:**
- ✅ Success message appears
- 🔗 Teams meeting link displayed
- 📅 Meeting appears in your calendar

**If it fails:**
- Check Railway logs for error messages
- Verify all 3 variables are set correctly
- Make sure admin consent was granted
- Check client secret hasn't expired

---

## 📋 Troubleshooting Checklist

### ❌ "Authentication failed"
- [ ] Check Client ID is correct
- [ ] Check Client Secret is correct (no extra spaces)
- [ ] Check Tenant ID is correct
- [ ] Verify secret hasn't expired

### ❌ "Insufficient permissions"
- [ ] Verify API permissions were added
- [ ] Check admin consent was granted (green checkmarks)
- [ ] Wait a few minutes and try again (propagation delay)

### ❌ "User not found"
- [ ] Make sure you're signed in with correct Microsoft account
- [ ] Verify account has Teams license
- [ ] Check account is in the same tenant

### ❌ "Cannot create meeting"
- [ ] Verify User.Read.All permission granted
- [ ] Check Calendars.ReadWrite permission granted
- [ ] Check OnlineMeetings.ReadWrite.All permission granted

---

## 📸 Visual Reference

### What You Should See:

**In Azure Portal:**
```
App registrations > Your App
├── Overview
│   ├── Application (client) ID: ✅
│   └── Directory (tenant) ID: ✅
├── Certificates & secrets
│   └── Client secrets: ✅ (1 active)
└── API permissions
    ├── Calendars.ReadWrite: ✅ Granted
    ├── OnlineMeetings.ReadWrite.All: ✅ Granted
    └── User.Read.All: ✅ Granted
```

**In Railway:**
```
Variables
├── MICROSOFT_CLIENT_ID: Set ✅
├── MICROSOFT_CLIENT_SECRET: Set ✅
└── MICROSOFT_TENANT_ID: Set ✅
```

---

## 🎉 Success!

Once you complete all these steps, your CRM will be able to:
- ✅ Create Microsoft Teams meetings
- ✅ Generate Teams meeting links
- ✅ Send calendar invitations
- ✅ Add meetings to your calendar
- ✅ Invite multiple attendees
- ✅ Include meeting notes

---

## 💾 Save Your Credentials

**Keep these safe:**
```
Application (client) ID: ____________________
Directory (tenant) ID: ____________________
Client Secret: ____________________
Secret Expires: ____________________
```

**⚠️ IMPORTANT:**
- Store these securely
- Don't share publicly
- Set calendar reminder to renew secret before expiration

---

## 📞 Need Help?

**Common Issues:**
- Not an admin? Contact your IT administrator
- No Microsoft 365? Sign up at: https://www.microsoft.com/en-us/microsoft-365/business
- Azure errors? Check: https://docs.microsoft.com/en-us/azure/active-directory/

**Ready to proceed?**
Let me know when you've completed these steps and I'll help you implement the backend code!
