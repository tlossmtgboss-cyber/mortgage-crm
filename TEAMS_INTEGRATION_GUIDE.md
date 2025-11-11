# 📅 Microsoft Teams Integration Guide

## ✅ What's Been Implemented

Your CRM now has Microsoft Teams integration built in! Here's what's ready:

### 🎯 **Frontend Components (COMPLETE)**

✅ **Teams Meeting Modal**
- Beautiful Microsoft Teams-branded interface
- Create meetings directly from lead profiles
- Auto-populated fields based on lead info
- Meeting type templates (Consultation, Follow-Up, etc.)
- Date, time, and duration picker
- Add additional attendees
- Include meeting notes/agenda

✅ **Lead Detail Integration**
- "Teams Meeting" button in Quick Actions
- Purple gradient Teams branding
- One-click meeting creation
- Responsive mobile design

### 📱 **How It Works Now**

**User Experience:**
1. Open any lead's profile
2. Click "👥 Teams Meeting" in Quick Actions
3. Teams modal opens with:
   - Auto-filled subject line
   - Meeting type selector
   - Date/time picker
   - Duration options (15-480 minutes)
   - Attendee email input
   - Notes section
4. Click "Create Meeting"
5. Meeting link generated (when backend configured)

---

## 🔧 **Backend Setup Required**

To enable full functionality, you need to configure Microsoft Graph API access. This allows the CRM to actually create Teams meetings.

### **What's Needed:**

1. **Microsoft 365 Account** (Work or School account with Teams)
2. **Azure AD App Registration** (for API access)
3. **Microsoft Graph API Permissions**
4. **Backend Environment Variables**

---

## 📋 **Complete Backend Setup Steps**

### **Step 1: Register App in Azure AD**

1. Go to: **https://portal.azure.com**
2. Log in with your Microsoft 365 account
3. Navigate to: **Azure Active Directory** → **App registrations**
4. Click **"+ New registration"**

**App Details:**
```
Name: Mortgage CRM - Teams Integration
Supported account types: Single tenant (your organization only)
Redirect URI: https://mortgage-crm-production-7a9a.up.railway.app/auth/microsoft/callback
```

5. Click **"Register"**

### **Step 2: Get Application (client) ID**

After registration, you'll see:
- **Application (client) ID** - Copy this (looks like: `12345678-1234-1234-1234-123456789012`)
- **Directory (tenant) ID** - Copy this too

### **Step 3: Create Client Secret**

1. In your app, go to **"Certificates & secrets"**
2. Click **"+ New client secret"**
3. Add description: `CRM Teams Integration`
4. Choose expiration: `24 months` (or longer)
5. Click **"Add"**
6. **IMPORTANT:** Copy the **Value** immediately (you won't see it again!)

### **Step 4: Set API Permissions**

1. Go to **"API permissions"**
2. Click **"+ Add a permission"**
3. Select **"Microsoft Graph"**
4. Choose **"Application permissions"** (not Delegated)

**Required Permissions:**
```
Calendars.ReadWrite     - Create and manage calendar events
OnlineMeetings.ReadWrite.All - Create Teams meetings
User.Read.All           - Read user information
```

5. Click **"Add permissions"**
6. Click **"Grant admin consent for [Your Organization]"**
7. Click **"Yes"** to confirm

### **Step 5: Add Environment Variables to Railway**

1. Go to: https://railway.app/dashboard
2. Select your **backend** service
3. Go to **"Variables"** tab
4. Add these variables:

```bash
# Microsoft Teams Integration
MICROSOFT_CLIENT_ID=your_application_client_id_here
MICROSOFT_CLIENT_SECRET=your_client_secret_here
MICROSOFT_TENANT_ID=your_directory_tenant_id_here

# Microsoft Graph API Endpoint
MICROSOFT_GRAPH_ENDPOINT=https://graph.microsoft.com/v1.0
```

5. Click **"Save"**
6. Backend will restart automatically

---

## 🎨 **What's Already Working**

### **Frontend (100% Complete)**

✅ **User Interface**
- Teams meeting modal
- Form validation
- Date/time picker
- Meeting type templates
- Attendee management
- Notes section
- Success/error feedback
- Meeting link display

✅ **Integration Points**
- Lead Detail page button
- Modal state management
- API endpoint calls
- Error handling
- Loading states

### **What's Pending Backend**

⏳ **Backend API Endpoint** (`/api/v1/teams/create-meeting`)
- Needs Microsoft Graph SDK integration
- OAuth2 authentication flow
- Meeting creation logic
- Calendar event creation
- Teams meeting link generation

---

## 💻 **Backend Implementation (For Developer)**

Here's what needs to be added to `backend/main.py`:

```python
# Required imports
from msal import ConfidentialClientApplication
import requests
from datetime import datetime, timedelta

# Microsoft Graph configuration
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
MICROSOFT_TENANT_ID = os.getenv("MICROSOFT_TENANT_ID")
MICROSOFT_AUTHORITY = f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}"
MICROSOFT_SCOPE = ["https://graph.microsoft.com/.default"]

# Initialize MSAL client
msal_app = ConfidentialClientApplication(
    MICROSOFT_CLIENT_ID,
    authority=MICROSOFT_AUTHORITY,
    client_credential=MICROSOFT_CLIENT_SECRET,
)

# Endpoint to create Teams meeting
@app.post("/api/v1/teams/create-meeting")
async def create_teams_meeting(
    subject: str,
    start_time: str,  # ISO 8601 format
    duration_minutes: int,
    attendees: List[str] = [],
    lead_id: Optional[int] = None,
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a Microsoft Teams meeting"""

    # Get access token
    result = msal_app.acquire_token_silent(MICROSOFT_SCOPE, account=None)
    if not result:
        result = msal_app.acquire_token_for_client(scopes=MICROSOFT_SCOPE)

    if "access_token" not in result:
        raise HTTPException(status_code=503, detail="Failed to authenticate with Microsoft")

    access_token = result["access_token"]

    # Calculate end time
    start_dt = datetime.fromisoformat(start_time)
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    # Build meeting request
    meeting_data = {
        "subject": subject,
        "startDateTime": start_dt.isoformat(),
        "endDateTime": end_dt.isoformat(),
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
        "attendees": [
            {
                "emailAddress": {"address": email},
                "type": "required"
            }
            for email in attendees
        ],
        "body": {
            "contentType": "HTML",
            "content": notes or ""
        }
    }

    # Create calendar event with Teams meeting
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        "https://graph.microsoft.com/v1.0/me/events",
        json=meeting_data,
        headers=headers
    )

    if response.status_code != 201:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to create meeting: {response.text}"
        )

    meeting_result = response.json()

    # Save to database (optional)
    # ... add code to save meeting record ...

    return {
        "id": meeting_result["id"],
        "subject": meeting_result["subject"],
        "start_time": meeting_result["start"]["dateTime"],
        "end_time": meeting_result["end"]["dateTime"],
        "join_url": meeting_result.get("onlineMeeting", {}).get("joinUrl"),
        "web_link": meeting_result["webLink"]
    }
```

### **Required Python Packages**

Add to `requirements.txt`:
```
msal==1.24.0
```

Install:
```bash
pip install msal
```

---

## 🚀 **Testing the Integration**

### **Step 1: Verify Environment Variables**

```bash
# Check Railway variables are set
railway variables

# Should show:
# MICROSOFT_CLIENT_ID
# MICROSOFT_CLIENT_SECRET
# MICROSOFT_TENANT_ID
```

### **Step 2: Test in CRM**

1. Go to: https://mortgage-crm-git-main-tim-loss-projects.vercel.app
2. Open any lead's profile
3. Click **"👥 Teams Meeting"**
4. Fill in:
   - Meeting Type: Initial Consultation
   - Date: Tomorrow
   - Time: 10:00 AM
   - Duration: 30 minutes
   - Attendees: your@email.com
5. Click **"Create Meeting"**

**Expected Result:**
- ✅ Success message
- 🔗 Teams meeting link displayed
- 📅 Meeting appears in your Microsoft Teams calendar

---

## 📊 **Features Breakdown**

| Feature | Status | Notes |
|---------|--------|-------|
| **Frontend Modal** | ✅ Complete | Fully functional UI |
| **Lead Integration** | ✅ Complete | Button in Quick Actions |
| **Form Validation** | ✅ Complete | Date, time, subject required |
| **Meeting Templates** | ✅ Complete | 5 preset types |
| **Attendee Management** | ✅ Complete | Multi-email support |
| **Notes/Agenda** | ✅ Complete | Rich text area |
| **Backend Endpoint** | ⏳ Pending | Needs Microsoft Graph setup |
| **OAuth Flow** | ⏳ Pending | Needs Azure AD setup |
| **Meeting Creation** | ⏳ Pending | Needs Graph API integration |

---

## 💡 **Benefits of Teams Integration**

✅ **Seamless Scheduling**
- Create meetings without leaving CRM
- Auto-populated lead information
- Quick meeting type selection

✅ **Professional Communication**
- Microsoft Teams branded meetings
- Calendar invitations sent automatically
- Meeting reminders via Teams

✅ **Better Organization**
- All meetings linked to leads
- Meeting history tracked
- Easy rescheduling

✅ **Time Savings**
- No manual calendar switching
- Pre-built templates
- One-click creation

---

## 🆘 **Troubleshooting**

### "Failed to authenticate with Microsoft"

**Solution:**
- Check environment variables are set correctly
- Verify Client ID and Secret are valid
- Check Tenant ID is correct
- Ensure client secret hasn't expired

### "Insufficient permissions"

**Solution:**
- Go to Azure AD → App registrations → Your app
- Check API permissions include:
  - Calendars.ReadWrite
  - OnlineMeetings.ReadWrite.All
- Click "Grant admin consent"

### "Meeting created but no Teams link"

**Solution:**
- Ensure `onlineMeetingProvider` is set to "teamsForBusiness"
- Check user has Teams license
- Verify `isOnlineMeeting` is true in request

---

## 📚 **Additional Resources**

**Microsoft Documentation:**
- Microsoft Graph API: https://docs.microsoft.com/en-us/graph/
- Create Teams Meeting: https://docs.microsoft.com/en-us/graph/api/application-post-onlinemeetings
- Azure AD App Registration: https://docs.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app

**MSAL Python:**
- Documentation: https://msal-python.readthedocs.io/
- Examples: https://github.com/AzureAD/microsoft-authentication-library-for-python

---

## 🎉 **Summary**

✅ **Frontend:** 100% complete and deployed
⏳ **Backend:** Needs Azure AD setup and Graph API integration
📅 **Ready to use:** Once backend is configured

**Time to full functionality:** ~30 minutes (Azure AD setup)
**Complexity:** Medium (requires Azure account)
**Value:** High (seamless Teams integration)

---

Once you complete the Azure AD setup and add the backend endpoint, your team will be able to create Microsoft Teams meetings directly from lead profiles with just a few clicks! 🚀
