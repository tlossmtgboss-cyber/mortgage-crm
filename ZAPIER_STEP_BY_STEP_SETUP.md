# Zapier Setup Guide - Step-by-Step Instructions

Complete guide to setting up Zaps for your Mortgage CRM.

---

## Prerequisites

Before you begin:
- ✅ Zapier account (free or paid)
- ✅ API Key: `185b7101-9435-44da-87ab-b7582c4e4607`
- ✅ API URL: `https://mortgage-crm-production-7a9a.up.railway.app`

---

# Setup 1: Form Submission → Create Lead in CRM

**Use Case:** Automatically create a lead in your CRM when someone submits a contact form.

## Step 1: Create a New Zap

1. Go to https://zapier.com
2. Click **"Create Zap"** (orange button in top right)
3. You'll see the Zap editor with Trigger and Action sections

---

## Step 2: Set Up the Trigger

### Choose Your Trigger App

1. In the **Trigger** section, click **"Choose app"**
2. Search for your form app. Popular options:
   - **Google Forms** (recommended for beginners)
   - **Typeform**
   - **Webflow Forms**
   - **JotForm**
   - **Gravity Forms**
   - **Contact Form 7**

3. Select your app (for this example, we'll use **Google Forms**)

### Choose Trigger Event

1. Select trigger event: **"New Response in Spreadsheet"** or **"New Form Response"**
2. Click **Continue**

### Connect Your Account

1. Click **"Sign in to Google Forms"**
2. Authorize Zapier to access your Google account
3. Click **Continue**

### Configure Trigger

1. **Select Form:** Choose your form from the dropdown
2. **Select Spreadsheet:** (if applicable) Choose where responses are stored
3. Click **Continue**

### Test Trigger

1. Click **"Test trigger"**
2. Zapier will fetch a recent form submission
3. You should see sample data appear
4. Click **Continue**

---

## Step 3: Add the Action (Create Lead in CRM)

### Choose Action App

1. Click **"+ Add Step"** or the **Action** section
2. Search for: **"Webhooks by Zapier"**
3. Select **"Webhooks by Zapier"**

### Choose Action Event

1. Select: **"POST"**
2. Click **Continue**

### Set Up Action - URL

1. **URL:** Paste this exactly:
   ```
   https://mortgage-crm-production-7a9a.up.railway.app/api/v1/leads/
   ```

### Set Up Action - Payload Type

1. **Payload Type:** Select **"json"**

### Set Up Action - Data

Click **"Add a field"** for each field below. Use the format:

**Field Name** → **Value from Trigger**

**Required Fields:**

| Field Name | Value | Example |
|------------|-------|---------|
| `name` | Map: First Name + Last Name | "Sarah Johnson" |
| `email` | Map: Email field | "sarah@email.com" |

**Recommended Fields:**

| Field Name | Value | Example |
|------------|-------|---------|
| `phone` | Map: Phone field | "555-123-4567" |
| `stage` | Type: "New" | "New" |
| `source` | Type: "Web Form - Zapier" | "Web Form - Zapier" |
| `credit_score` | Map: Credit Score field | 750 |
| `annual_income` | Map: Annual Income field | 125000 |
| `employment_status` | Map: Employment Status | "Full-time" |
| `property_type` | Map: Property Type | "Single Family" |
| `property_value` | Map: Property Value | 450000 |
| `down_payment` | Map: Down Payment | 75000 |
| `address` | Map: Address field | "123 Main St" |
| `city` | Map: City field | "San Francisco" |
| `state` | Map: State field | "CA" |
| `zip_code` | Map: Zip Code field | "94102" |
| `first_time_buyer` | Map: First Time Buyer | true/false |
| `notes` | Map: Additional Notes | "Any notes from form" |

**Here's how to add each field:**

1. Click **"+"** next to Data
2. In **Key**, type the field name (e.g., `name`)
3. In **Value**, click the field and select from trigger data OR type a static value
4. Repeat for all fields

**Example Data Configuration:**
```
Key: name          | Value: {{First Name}} {{Last Name}}
Key: email         | Value: {{Email Address}}
Key: phone         | Value: {{Phone Number}}
Key: stage         | Value: New
Key: source        | Value: Web Form - Zapier
Key: credit_score  | Value: {{Credit Score}}
Key: annual_income | Value: {{Annual Income}}
Key: notes         | Value: {{Additional Comments}}
```

### Set Up Action - Headers

1. Scroll down to **"Headers"** section
2. Click **"+ Add Header"**

**Header 1:**
- **Key:** `X-API-Key`
- **Value:** `185b7101-9435-44da-87ab-b7582c4e4607`

**Header 2:**
- **Key:** `Content-Type`
- **Value:** `application/json`

### Set Up Action - Wrap Request in Array

1. **Wrap Request In Array:** Select **"no"**

### Set Up Action - Unflatten

1. **Unflatten:** Select **"no"**

2. Click **Continue**

---

## Step 4: Test Your Action

1. Click **"Test action"** or **"Test step"**
2. Zapier will send the request to your CRM
3. You should see a success message with response data:
   ```json
   {
     "id": 45,
     "name": "Sarah Johnson",
     "email": "sarah@email.com",
     "ai_score": 85,
     "sentiment": "positive",
     ...
   }
   ```
4. Look for:
   - ✅ Status: 200 or 201
   - ✅ Response includes an `id` field
   - ✅ Response includes `ai_score` (automatically calculated)

5. If successful, click **Continue**

---

## Step 5: Name and Turn On Your Zap

1. At the top, click the Zap name (e.g., "Google Forms to Webhooks")
2. Rename it: **"Form Submission → Create CRM Lead"**
3. Click **"Publish"** or toggle the switch to **ON**

**Your Zap is now live!**

---

# Setup 2: Update Lead When Email Received

**Use Case:** When you receive an email from a lead, update their status in the CRM.

## Step 1: Create a New Zap

1. Click **"Create Zap"**

## Step 2: Set Up Trigger (Gmail)

### Choose Trigger App

1. Search: **"Gmail"**
2. Select **"Gmail"**

### Choose Trigger Event

1. Select: **"New Email Matching Search"**
2. Click **Continue**

### Connect Gmail Account

1. Click **"Sign in to Gmail"**
2. Authorize Zapier
3. Click **Continue**

### Configure Trigger

1. **Search String:** Enter search criteria (e.g., `from:*@email.com`)
2. **Label:** (Optional) Select a label
3. Click **Continue**

### Test Trigger

1. Click **"Test trigger"**
2. Zapier will find a recent email
3. Click **Continue**

## Step 3: Add Filter (Optional but Recommended)

1. Click **"+"** between Trigger and Action
2. Select **"Filter"**
3. Set condition:
   - **Field:** Subject or From Email
   - **Condition:** Contains
   - **Value:** "mortgage" or specific domain

## Step 4: Add Action (Update Lead)

### Choose Action App

1. Search: **"Webhooks by Zapier"**
2. Select **"Webhooks by Zapier"**

### Choose Action Event

1. Select: **"Custom Request"**
2. Click **Continue**

### Configure Action

1. **Method:** Select **"PATCH"**

2. **URL:**
   ```
   https://mortgage-crm-production-7a9a.up.railway.app/api/v1/leads/{{LEAD_ID}}
   ```
   *(You'll need to know the lead ID - see "Finding Lead ID" section below)*

3. **Headers:**
   - Header 1:
     - Key: `X-API-Key`
     - Value: `185b7101-9435-44da-87ab-b7582c4e4607`
   - Header 2:
     - Key: `Content-Type`
     - Value: `application/json`

4. **Data (JSON):**
   ```json
   {
     "stage": "Attempted Contact",
     "notes": "Email received on {{Date}} - Subject: {{Subject}}"
   }
   ```

5. Click **Continue**

### Test Action

1. Click **"Test action"**
2. Verify success response
3. Click **Continue**

### Publish Zap

1. Name it: **"Gmail → Update CRM Lead"**
2. Turn **ON**

---

# Setup 3: New Lead → Send to Google Sheets

**Use Case:** Every time a new lead is created, add them to a Google Sheet for tracking.

## Step 1: Create Zap with Webhook Trigger

### Set Up Trigger

1. Create new Zap
2. Search: **"Webhooks by Zapier"**
3. Event: **"Catch Hook"**
4. Click **Continue**

### Get Webhook URL

1. Zapier will show you a custom webhook URL
2. **Copy this URL** (you'll use it later)
3. Click **"Test trigger"** (leave this open)

### Send Test Data to Webhook

Open a new terminal and run:

```bash
curl -X POST "YOUR_WEBHOOK_URL_FROM_ZAPIER" \
-H "Content-Type: application/json" \
-d '{
  "id": 44,
  "name": "Sarah Johnson",
  "email": "sarah.johnson@email.com",
  "phone": "555-123-4567",
  "stage": "New",
  "ai_score": 90,
  "credit_score": 750,
  "annual_income": 125000
}'
```

### Complete Test

1. Return to Zapier
2. Click **"Test trigger"** again
3. You should see your test data
4. Click **Continue**

## Step 2: Add Action (Google Sheets)

### Choose Action App

1. Search: **"Google Sheets"**
2. Select **"Google Sheets"**

### Choose Action Event

1. Select: **"Create Spreadsheet Row"**
2. Click **Continue**

### Connect Google Sheets

1. Sign in to Google Sheets
2. Authorize Zapier
3. Click **Continue**

### Configure Action

1. **Drive:** My Google Drive
2. **Spreadsheet:** Select or create a spreadsheet
3. **Worksheet:** Select the worksheet

### Map Fields

Map the webhook data to spreadsheet columns:

| Column | Value from Webhook |
|--------|-------------------|
| Lead ID | `{{id}}` |
| Name | `{{name}}` |
| Email | `{{email}}` |
| Phone | `{{phone}}` |
| Stage | `{{stage}}` |
| AI Score | `{{ai_score}}` |
| Credit Score | `{{credit_score}}` |
| Annual Income | `{{annual_income}}` |
| Created Date | `{{created_at}}` |

### Test and Publish

1. Click **"Test action"**
2. Check your Google Sheet - new row should appear
3. Name Zap: **"New CRM Lead → Google Sheets"**
4. Turn **ON**

---

# Advanced Setup: Polling CRM for New Leads

**Use Case:** Check CRM every 15 minutes for new leads and take action.

## Step 1: Create Polling Zap

1. Create new Zap
2. Trigger: **"Webhooks by Zapier"**
3. Event: **"Retrieve Poll"** (available on paid plans)

### Configure Retrieve Poll

1. **URL:**
   ```
   https://mortgage-crm-production-7a9a.up.railway.app/api/v1/leads?limit=100
   ```

2. **Method:** GET

3. **Headers:**
   - Key: `X-API-Key`
   - Value: `185b7101-9435-44da-87ab-b7582c4e4607`

4. **ID Key:** `id` (tells Zapier which field is unique)

5. Click **Continue**

### Test Trigger

1. Click **"Test trigger"**
2. You should see your leads from the CRM
3. Click **Continue**

## Step 2: Add Filter (High-Quality Leads Only)

1. Add **Filter** step
2. Condition:
   - Field: `AI Score`
   - Condition: `Greater than`
   - Value: `80`

## Step 3: Add Action (Your Choice)

Choose what happens with new high-quality leads:
- Send Slack notification
- Create task in Asana
- Add to email campaign
- Send SMS via Twilio
- etc.

---

# Finding Lead ID for Updates

You have 3 options:

## Option 1: From CRM Response
When you create a lead via Zap, the response includes the ID:
```json
{
  "id": 44,
  ...
}
```
Use this ID in subsequent actions.

## Option 2: Search by Email
Create a Zap step that:
1. Calls: `GET /api/v1/leads`
2. Add Filter to find lead by email
3. Use the ID from matched lead

## Option 3: Manual Lookup
```bash
curl "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/leads" \
-H "X-API-Key: 185b7101-9435-44da-87ab-b7582c4e4607" | grep "sarah@email.com"
```

---

# Testing Your Zaps

## Test 1: Submit a Form
1. Fill out your Google Form (or other trigger)
2. Wait 1-2 minutes
3. Check Zapier Task History
4. Check your CRM for the new lead

## Test 2: Check Zap History
1. Go to https://zapier.com/app/history
2. Click on your Zap
3. View the execution log
4. Look for:
   - ✅ Green checkmarks = Success
   - ❌ Red X = Error (click to see details)

## Test 3: Verify in CRM
```bash
curl "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/leads?limit=10" \
-H "X-API-Key: 185b7101-9435-44da-87ab-b7582c4e4607"
```

---

# Common Issues & Solutions

## Issue 1: "Authentication failed"
**Error:** `{"detail": "Not authenticated"}`

**Solutions:**
1. Check X-API-Key header is exactly: `185b7101-9435-44da-87ab-b7582c4e4607`
2. Ensure you added both headers (X-API-Key AND Content-Type)
3. Check for extra spaces in the API key

## Issue 2: "Invalid JSON"
**Error:** `400 Bad Request - Invalid JSON`

**Solutions:**
1. Make sure Payload Type is set to "json"
2. Check that all field values are properly mapped
3. Don't include extra commas or brackets

## Issue 3: "Field validation error"
**Error:** `422 Unprocessable Entity`

**Solutions:**
1. Ensure `name` and `email` fields are provided (required)
2. Check that email format is valid
3. Verify numeric fields (credit_score, annual_income) are numbers, not text

## Issue 4: Zap not triggering
**Solutions:**
1. Check that Zap is turned ON (toggle in top right)
2. Verify trigger is working (test the trigger)
3. Check Zap Task History for errors
4. For polling triggers, wait for the next poll cycle (up to 15 min)

## Issue 5: Lead not created in CRM
**Solutions:**
1. Check Zapier Task History for the execution
2. Look at the response from the webhook action
3. Verify the URL is exactly: `https://mortgage-crm-production-7a9a.up.railway.app/api/v1/leads/`
4. Check that the method is POST (not GET or PATCH)

---

# Best Practices

## 1. Test First
Always test your Zap with sample data before turning it on.

## 2. Use Filters
Add filters to prevent duplicate leads or irrelevant triggers.

## 3. Name Your Zaps Clearly
Use descriptive names: "Form Submission → CRM Lead" not "My Zap 1"

## 4. Monitor Task History
Check weekly: https://zapier.com/app/history

## 5. Handle Errors
Set up error notifications in Zapier settings.

## 6. Add Delays
If one action depends on another, add a 1-2 second delay between steps.

## 7. Use Folders
Organize Zaps in folders: "Lead Generation", "Lead Nurture", etc.

---

# Quick Reference

**API Key:** `185b7101-9435-44da-87ab-b7582c4e4607`

**Base URL:** `https://mortgage-crm-production-7a9a.up.railway.app`

**Endpoints:**
- Create Lead: `POST /api/v1/leads/`
- Update Lead: `PATCH /api/v1/leads/{id}`
- Get Leads: `GET /api/v1/leads`
- Get Lead by ID: `GET /api/v1/leads/{id}`

**Required Headers:**
```
X-API-Key: 185b7101-9435-44da-87ab-b7582c4e4607
Content-Type: application/json
```

**Minimum Required Fields:**
- `name` (string)
- `email` (string)

**Your Webhook URL:**
```
https://hooks.zapier.com/hooks/catch/2446725/usnpkzc/
```

---

# Next Steps

1. ✅ Set up your first Zap (Form → CRM)
2. ✅ Test with real data
3. ✅ Monitor for 24 hours
4. ✅ Set up additional Zaps as needed
5. ✅ Check analytics in CRM to see AI scores

**Need Help?** Review the test results in `ZAPIER_CONFIGURATION.md`

---

# Example: Complete Form to CRM Setup

Here's a complete example with exact values:

**Trigger: Google Forms**
- Event: New Form Response
- Form: "Mortgage Pre-Qualification"

**Action: Webhooks by Zapier**
- Event: POST
- URL: `https://mortgage-crm-production-7a9a.up.railway.app/api/v1/leads/`

**Headers:**
```
X-API-Key: 185b7101-9435-44da-87ab-b7582c4e4607
Content-Type: application/json
```

**Data:**
```
name: {{First Name}} {{Last Name}}
email: {{Email Address}}
phone: {{Phone Number}}
stage: New
source: Google Form - Zapier
credit_score: {{Credit Score}}
annual_income: {{Annual Income}}
employment_status: {{Employment Status}}
property_type: {{Property Type}}
property_value: {{Desired Property Value}}
down_payment: {{Down Payment Amount}}
first_time_buyer: {{First Time Home Buyer}}
notes: {{Additional Comments}}
```

**Expected Response:**
```json
{
  "id": 45,
  "name": "John Doe",
  "email": "john@email.com",
  "ai_score": 85,
  "sentiment": "positive",
  "stage": "New",
  "source": "Google Form - Zapier"
}
```

✅ **Success!** Lead created with ID 45 and AI Score of 85.
