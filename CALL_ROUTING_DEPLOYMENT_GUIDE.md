# 📞 Call Routing & Transfer System - Deployment Guide

## ✅ What Was Built

You now have a **complete call routing and transfer system** with the following capabilities:

### **1. Database Infrastructure**
- ✅ `call_routing_log` - Tracks all call transfers with whisper messages
- ✅ `staff_availability` - Manages staff availability for routing
- ✅ `call_transfer_config` - Configurable routing rules
- ✅ Database models in `vapi_models.py`

### **2. Core Transfer Functions**
- ✅ `identify_caller()` - Comprehensive caller lookup and routing recommendation
- ✅ `transfer_call_with_whisper()` - Core transfer logic with whisper messages
- ✅ Vapi API integration for call transfers

### **3. VAPI Function Endpoints**
- ✅ `/api/vapi/functions/identify-caller` - Caller identification
- ✅ `/api/vapi/functions/transfer-to-production-assistant` - Transfer to PA
- ✅ `/api/vapi/functions/transfer-to-loan-officer` - Transfer to LO
- ✅ `/api/vapi/functions/transfer-to-processor` - Transfer to Processor

### **4. Management API Endpoints**
- ✅ `GET /api/vapi/receptionist/available-staff` - List available staff
- ✅ `GET /api/vapi/receptionist/routing-log` - View routing history
- ✅ `POST /api/vapi/receptionist/staff-availability` - Update availability

### **5. Updated VAPI Assistant**
- ✅ New configuration: `vapi_assistant_with_transfer.json`
- ✅ Includes all transfer functions
- ✅ Enhanced system prompt with routing protocols

---

## 📋 Deployment Steps

### **Step 1: Run Database Migration**

Run the migration to create the new routing tables:

```bash
cd /Users/timothyloss/my-project/mortgage-crm/backend
python migrations/add_call_routing_tables.py
```

**Expected Output:**
```
Starting call routing tables migration...
Executing command 1/12...
✅ Command 1 executed successfully
...
✅ Call routing tables migration completed successfully!
```

### **Step 2: Set Up Staff Availability**

You need to configure at least one staff member for each role. Use the API endpoint:

```bash
# Example: Set up Production Assistant
curl -X POST https://app.perenniaai.com/api/vapi/receptionist/staff-availability \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "user_id": 1,
    "role": "production_assistant",
    "status": "available",
    "available_for_calls": true,
    "primary_phone": "+15551234567",
    "department": "sales"
  }'
```

**Roles to configure:**
- `production_assistant` - Required (primary routing target)
- `loan_officer` - Optional (for urgent escalations)
- `processor` - Optional (for processing questions)

### **Step 3: Update VAPI Assistant**

You have two options:

#### **Option A: Update via VAPI Dashboard**
1. Go to [vapi.ai/dashboard](https://vapi.ai/dashboard)
2. Find your "Sam" assistant
3. Click "Edit"
4. Replace the configuration with the contents of `backend/vapi_assistant_with_transfer.json`
5. Save changes

#### **Option B: Create New Assistant via API**
```bash
curl -X POST https://api.vapi.ai/assistant \
  -H "Authorization: Bearer YOUR_VAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @backend/vapi_assistant_with_transfer.json
```

### **Step 4: Deploy Backend Changes**

Since you're using Railway, the changes will deploy automatically via git:

```bash
cd /Users/timothyloss/my-project/mortgage-crm
git add backend/
git commit -m "Add call routing and transfer system with whisper capability"
git push
```

**Verify deployment:**
```bash
railway logs --tail
```

Look for successful startup messages.

### **Step 5: Verify Endpoints**

Test that the new endpoints are accessible:

```bash
# Test identify-caller endpoint
curl -X POST https://app.perenniaai.com/api/vapi/functions/identify-caller \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+15551234567"}'

# Expected response:
# {"success": true, "found": false, "caller_type": "new_prospect", ...}
```

---

## 🧪 Testing the Transfer System

### **Test 1: Caller Identification**

**Goal:** Verify the system can identify existing leads

**Steps:**
1. Create a test lead in your CRM with phone number `+15551234567`
2. Call the identify-caller endpoint:
```bash
curl -X POST https://app.perenniaai.com/api/vapi/functions/identify-caller \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+15551234567"}'
```

**Expected Result:**
```json
{
  "success": true,
  "found": true,
  "caller_type": "new_lead",
  "lead_id": 123,
  "lead_name": "Test User",
  "routing_recommendation": "transfer_to_production_assistant"
}
```

### **Test 2: Staff Availability Check**

**Goal:** Verify staff availability is configured

**Steps:**
```bash
curl -X GET "https://app.perenniaai.com/api/vapi/receptionist/available-staff" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Expected Result:**
```json
{
  "success": true,
  "staff": [
    {
      "user_id": 1,
      "role": "production_assistant",
      "status": "available",
      "primary_phone": "+15551234567",
      "available_for_calls": true
    }
  ]
}
```

### **Test 3: Live Call Test**

**Goal:** Test actual call transfer with Vapi

**Prerequisites:**
- VAPI assistant updated with transfer functions
- At least one staff member configured
- Test phone number ready

**Steps:**
1. Call your Vapi phone number (the one configured in your assistant)
2. When Sam answers, say: "Hi, I'd like to speak with someone about getting pre-approved"
3. Provide your name and phone number when asked
4. Sam should:
   - Call `identify_caller` function
   - Determine you're a new lead
   - Call `transfer_to_production_assistant` function
   - Say: "Transferring you to our Production Assistant now. Please hold."
5. You should hear a brief whisper message to the Production Assistant with your info
6. The call should connect to the PA's phone number

**Expected Flow:**
```
You → Vapi AI (Sam) → identify_caller → transfer_to_production_assistant → Whisper → PA Phone
```

### **Test 4: Verify Routing Log**

**Goal:** Confirm transfer was logged

**Steps:**
```bash
curl -X GET "https://app.perenniaai.com/api/vapi/receptionist/routing-log?limit=10" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Expected Result:**
```json
{
  "success": true,
  "routing_logs": [
    {
      "id": 1,
      "routing_decision": "transfer_to_production_assistant",
      "caller_type": "new_lead",
      "routed_to_role": "production_assistant",
      "caller_name": "Your Name",
      "caller_phone": "+15551234567",
      "transfer_successful": true
    }
  ]
}
```

---

## 🔧 Configuration

### **Environment Variables**

Ensure these are set in your Railway environment:

```env
# Vapi Configuration
VAPI_API_KEY=your_vapi_api_key
VAPI_ASSISTANT_ID=your_updated_assistant_id

# Database
DATABASE_URL=postgresql://...

# Production Domain
PRODUCTION_DOMAIN=https://app.perenniaai.com
```

### **Twilio Configuration (if using)**

If you're using Twilio for SMS notifications:
```env
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_FROM_NUMBER=your_twilio_number
```

---

## 📊 Monitoring & Maintenance

### **View Call Routing Logs**

```bash
# Via API
curl -X GET "https://app.perenniaai.com/api/vapi/receptionist/routing-log" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### **Update Staff Availability**

```bash
# Set PA as unavailable
curl -X POST https://app.perenniaai.com/api/vapi/receptionist/staff-availability \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "user_id": 1,
    "status": "busy",
    "available_for_calls": false
  }'
```

### **View Available Staff**

```bash
curl -X GET "https://app.perenniaai.com/api/vapi/receptionist/available-staff?role=production_assistant" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## 🚨 Troubleshooting

### **Issue: "No Production Assistant configured"**

**Cause:** No staff availability record exists for Production Assistant role

**Fix:**
```bash
curl -X POST https://app.perenniaai.com/api/vapi/receptionist/staff-availability \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "user_id": YOUR_USER_ID,
    "role": "production_assistant",
    "status": "available",
    "available_for_calls": true,
    "primary_phone": "+15551234567"
  }'
```

### **Issue: "Transfer failed" or "recipient_unavailable"**

**Causes:**
1. Staff member marked as unavailable
2. Invalid phone number
3. Vapi API error

**Debug Steps:**
1. Check staff availability:
   ```bash
   curl -X GET "https://app.perenniaai.com/api/vapi/receptionist/available-staff" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN"
   ```

2. Check routing logs for error details:
   ```bash
   curl -X GET "https://app.perenniaai.com/api/vapi/receptionist/routing-log?limit=1" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN"
   ```

3. Look for `transfer_error` field in the response

### **Issue: "identify_caller not working"**

**Causes:**
1. Lead phone number format mismatch
2. Database connection issue

**Fix:**
- Phone numbers are matched by last 10 digits
- Ensure leads have phone numbers in format: `+15551234567` or `(555) 123-4567`
- Test with: `curl -X POST .../identify-caller -d '{"phone_number": "+15551234567"}'`

---

## 📈 Next Steps

Now that call routing is implemented, you can:

1. **Add more routing rules** - Modify routing logic in `identify_caller()` function
2. **Implement Priority 2 features**:
   - Pre-approval data collection with dedicated table
   - Calendly direct booking
   - SSN encryption
3. **Build frontend UI** for:
   - Staff availability management
   - Routing log visualization
   - Real-time call monitoring
4. **Add analytics** - Track routing efficiency, transfer success rates

---

## 🎯 Success Criteria

Your system is working correctly if:

- ✅ Database migration completes without errors
- ✅ Staff availability can be set via API
- ✅ `identify_caller` returns caller information
- ✅ Live calls are successfully transferred with whisper context
- ✅ Routing logs show transfer history
- ✅ Production Assistant receives calls with context

---

## 📞 Support

If you encounter issues:

1. Check Railway logs: `railway logs --tail`
2. Test endpoints with curl commands above
3. Verify VAPI assistant configuration
4. Check database migration status
5. Review routing logs for error details

**Files Created:**
- `backend/migrations/add_call_routing_tables.py` - Database migration
- `backend/vapi_models.py` - Updated with routing models
- `backend/vapi_service.py` - Transfer functions added
- `backend/vapi_routes.py` - API endpoints added
- `backend/vapi_assistant_with_transfer.json` - New assistant config

**Modified Files:**
- `backend/vapi_models.py` - Added CallRoutingLog, StaffAvailability, CallTransferConfig
- `backend/vapi_service.py` - Added identify_caller, transfer_call_with_whisper
- `backend/vapi_routes.py` - Added 7 new endpoints

---

## 🎉 Congratulations!

You've successfully implemented **Priority 1: Call Routing & Transfer System** with:

- ✅ Intelligent caller identification
- ✅ Role-based call routing
- ✅ Whisper transfers with context
- ✅ Comprehensive logging
- ✅ Staff availability management

Your AI Receptionist can now intelligently route calls to the right team members with full context! 🚀
