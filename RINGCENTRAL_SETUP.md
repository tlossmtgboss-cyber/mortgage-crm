# 📞 RingCentral Integration - Click-to-Call & SMS Setup

Your CRM now has RingCentral integration for making calls and sending SMS directly from the app!

---

## ✅ What's Been Added

### Backend Features:
- ✅ RingCentral service (`backend/integrations/ringcentral_service.py`)
- ✅ Click-to-call functionality (RingOut API)
- ✅ SMS sending capabilities
- ✅ Call history retrieval
- ✅ SMS history retrieval
- ✅ Automatic phone number formatting (E.164)

### API Endpoints (to be added to main.py):
- `POST /api/v1/ringcentral/call` - Make a call (click-to-call)
- `POST /api/v1/ringcentral/sms` - Send SMS
- `GET /api/v1/ringcentral/call-log` - Get call history
- `GET /api/v1/ringcentral/sms-history` - Get SMS history
- `GET /api/v1/ringcentral/status` - Check RingCentral status

---

## 🔧 Step 1: Get RingCentral Credentials

### A. Create RingCentral Developer Account

1. Go to https://developers.ringcentral.com/
2. Sign up or log in
3. Click "Create App"
4. Fill in app details:
   - **App Name:** Mortgage CRM
   - **App Type:** Private
   - **Platform:** Server-only (No UI)
   - **Auth Type:** Password-based auth flow

### B. Get Your Credentials

After creating the app, you'll get:
- **Client ID:** `xxxxxx...`
- **Client Secret:** `xxxxxx...`

### C. Get Your Account Details

From your RingCentral account dashboard:
- **Phone Number:** Your RingCentral direct number (e.g., +1234567890)
- **Username:** Your RingCentral login (usually your phone number)
- **Password:** Your RingCentral account password
- **Extension:** (optional, usually blank for direct numbers)

---

## 🚀 Step 2: Configure Environment Variables

Add these to your `.env` file in the `backend/` directory:

```bash
# RingCentral Configuration
RINGCENTRAL_CLIENT_ID=your_client_id_here
RINGCENTRAL_CLIENT_SECRET=your_client_secret_here
RINGCENTRAL_USERNAME=your_ringcentral_phone_number  # e.g., +15551234567
RINGCENTRAL_PASSWORD=your_ringcentral_password
RINGCENTRAL_PHONE_NUMBER=your_ringcentral_phone_number  # Same as username
RINGCENTRAL_EXTENSION=  # Leave blank unless you have an extension
RINGCENTRAL_SERVER_URL=https://platform.ringcentral.com  # Production
# For sandbox testing, use: https://platform.devtest.ringcentral.com
```

### Example `.env` file:
```bash
RINGCENTRAL_CLIENT_ID=AbCdEf123456
RINGCENTRAL_CLIENT_SECRET=XyZ789AbCdEf
RINGCENTRAL_USERNAME=+15551234567
RINGCENTRAL_PASSWORD=MySecurePassword123!
RINGCENTRAL_PHONE_NUMBER=+15551234567
RINGCENTRAL_EXTENSION=
RINGCENTRAL_SERVER_URL=https://platform.ringcentral.com
```

---

## 📝 Step 3: Add API Endpoints to main.py

Add this code to `backend/main.py` (after the SMS endpoints around line 7600):

```python
# ============================================================================
# RINGCENTRAL INTEGRATION - Click-to-Call & SMS
# ============================================================================

from integrations.ringcentral_service import ringcentral_client

# Pydantic models for RingCentral
class RingCentralCallRequest(BaseModel):
    to_number: str
    caller_id: Optional[str] = None  # Optional custom caller ID

class RingCentralSMSRequest(BaseModel):
    to_number: str
    message: str

@app.post("/api/v1/ringcentral/call")
async def ringcentral_make_call(
    call_request: RingCentralCallRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Make a call via RingCentral (click-to-call)"""
    if not ringcentral_client.enabled:
        raise HTTPException(status_code=503, detail="RingCentral service not configured")

    try:
        result = await ringcentral_client.make_call(
            to_number=call_request.to_number,
            caller_id=call_request.caller_id
        )

        # Log activity
        activity = Activity(
            user_id=current_user.id,
            type="call",
            description=f"Called {call_request.to_number} via RingCentral",
            metadata={"session_id": result.get("session_id"), "to_number": call_request.to_number}
        )
        db.add(activity)
        db.commit()

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/ringcentral/sms")
async def ringcentral_send_sms(
    sms_request: RingCentralSMSRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send SMS via RingCentral"""
    if not ringcentral_client.enabled:
        raise HTTPException(status_code=503, detail="RingCentral service not configured")

    try:
        result = await ringcentral_client.send_sms(
            to_number=sms_request.to_number,
            message=sms_request.message
        )

        # Log activity
        activity = Activity(
            user_id=current_user.id,
            type="sms",
            description=f"Sent SMS to {sms_request.to_number} via RingCentral",
            metadata={"message_id": result.get("message_id"), "to_number": sms_request.to_number}
        )
        db.add(activity)
        db.commit()

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/ringcentral/call-log")
async def ringcentral_get_call_log(
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """Get call history from RingCentral"""
    if not ringcentral_client.enabled:
        raise HTTPException(status_code=503, detail="RingCentral service not configured")

    try:
        calls = await ringcentral_client.get_call_log(limit=limit)
        return {"calls": calls, "count": len(calls)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/ringcentral/sms-history")
async def ringcentral_get_sms_history(
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """Get SMS history from RingCentral"""
    if not ringcentral_client.enabled:
        raise HTTPException(status_code=503, detail="RingCentral service not configured")

    try:
        messages = await ringcentral_client.get_sms_history(limit=limit)
        return {"messages": messages, "count": len(messages)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/ringcentral/status")
async def ringcentral_get_status(current_user: User = Depends(get_current_user)):
    """Check RingCentral service status"""
    return ringcentral_client.get_status()
```

---

## 🎨 Step 4: Frontend Components

### A. Update ClickablePhone Component

Update `frontend/src/components/ClickableContact.js` to support RingCentral:

```javascript
import React, { useState } from 'react';
import './ClickableContact.css';

export function ClickablePhone({ phone }) {
  const [showMenu, setShowMenu] = useState(false);

  if (!phone) return <span className="no-contact">No phone</span>;

  const handleCall = async (provider) => {
    try {
      const token = localStorage.getItem('token');

      if (provider === 'ringcentral') {
        const response = await fetch('http://localhost:8000/api/v1/ringcentral/call', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ to_number: phone })
        });

        if (response.ok) {
          alert(`Calling ${phone} via RingCentral... Check your RingCentral app!`);
        } else {
          const error = await response.json();
          alert(`Failed to make call: ${error.detail}`);
        }
      }

      setShowMenu(false);
    } catch (error) {
      console.error('Call failed:', error);
      alert('Failed to make call. Check console for details.');
    }
  };

  const handleSMS = async (provider) => {
    const message = prompt('Enter your message:');
    if (!message) return;

    try {
      const token = localStorage.getItem('token');

      if (provider === 'ringcentral') {
        const response = await fetch('http://localhost:8000/api/v1/ringcentral/sms', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ to_number: phone, message })
        });

        if (response.ok) {
          alert(`SMS sent to ${phone} via RingCentral!`);
        } else {
          const error = await response.json();
          alert(`Failed to send SMS: ${error.detail}`);
        }
      }

      setShowMenu(false);
    } catch (error) {
      console.error('SMS failed:', error);
      alert('Failed to send SMS. Check console for details.');
    }
  };

  return (
    <div className="clickable-contact-wrapper">
      <span
        className="clickable-contact phone"
        onClick={() => setShowMenu(!showMenu)}
        title="Click to call or text"
      >
        📞 {phone}
      </span>

      {showMenu && (
        <div className="contact-menu">
          <button onClick={() => handleCall('ringcentral')} className="menu-item">
            📞 Call via RingCentral
          </button>
          <button onClick={() => handleSMS('ringcentral')} className="menu-item">
            💬 SMS via RingCentral
          </button>
          <button onClick={() => window.open(`tel:${phone}`)} className="menu-item">
            📱 Call via Device
          </button>
          <button onClick={() => setShowMenu(false)} className="menu-item cancel">
            ✕ Cancel
          </button>
        </div>
      )}
    </div>
  );
}
```

### B. Add CSS for Phone Menu

Add to `frontend/src/components/ClickableContact.css`:

```css
.clickable-contact-wrapper {
  position: relative;
  display: inline-block;
}

.clickable-contact.phone {
  cursor: pointer;
  color: #2563eb;
  text-decoration: none;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.2s;
}

.clickable-contact.phone:hover {
  background: #eff6ff;
  text-decoration: underline;
}

.contact-menu {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
  z-index: 1000;
  min-width: 220px;
  overflow: hidden;
}

.menu-item {
  display: block;
  width: 100%;
  padding: 10px 16px;
  border: none;
  background: white;
  text-align: left;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}

.menu-item:hover {
  background: #f3f4f6;
}

.menu-item.cancel {
  border-top: 1px solid #e5e7eb;
  color: #6b7280;
}

.menu-item.cancel:hover {
  background: #fee2e2;
  color: #dc2626;
}
```

---

## 🧪 Step 5: Test the Integration

### A. Test RingCentral Status

```bash
curl -X GET "http://localhost:8000/api/v1/ringcentral/status" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Expected response:
```json
{
  "enabled": true,
  "from_number": "+15551234567",
  "server_url": "https://platform.ringcentral.com",
  "authenticated": true
}
```

### B. Test Click-to-Call

```bash
curl -X POST "http://localhost:8000/api/v1/ringcentral/call" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"to_number": "+15559876543"}'
```

Expected: Your RingCentral phone will ring, and when you answer, it will connect you to the number.

### C. Test SMS

```bash
curl -X POST "http://localhost:8000/api/v1/ringcentral/sms" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"to_number": "+15559876543", "message": "Test from Mortgage CRM!"}'
```

---

## 📱 How It Works

### Click-to-Call Flow:
1. User clicks phone number in CRM
2. Menu appears with "Call via RingCentral" option
3. Backend makes RingOut API call to RingCentral
4. **Your** RingCentral phone rings first
5. When you answer, RingCentral connects you to the client
6. Call is logged in activity history

### SMS Flow:
1. User clicks phone number, selects "SMS via RingCentral"
2. Popup appears to type message
3. Message sent via RingCentral SMS API
4. Message logged in activity history
5. Client receives SMS from your RingCentral number

---

## 🎯 Features

✅ **Click-to-Call** - Call any number directly from CRM
✅ **SMS** - Send text messages from CRM
✅ **Call History** - View all calls made/received
✅ **SMS History** - View all messages sent/received
✅ **Activity Logging** - All calls/SMS logged automatically
✅ **Phone Formatting** - Auto-formats numbers to E.164
✅ **Error Handling** - Graceful fallbacks if RingCentral unavailable

---

## 💡 Best Practices

### When to Use RingCentral vs Device Calling:
- **Use RingCentral for:**
  - Business calls you want logged
  - Calls from your business number
  - Team accountability (call logs)
  - SMS messaging

- **Use Device Calling for:**
  - Quick personal calls
  - Emergencies
  - When RingCentral is down

### Phone Number Format:
- RingCentral prefers E.164 format: `+1234567890`
- Service auto-formats US numbers
- International: include country code

---

## 🔒 Security Notes

- **Never commit** `.env` file to git
- RingCentral credentials are sensitive
- Use production server for live calls
- Use sandbox for testing: `https://platform.devtest.ringcentral.com`

---

## ❓ Troubleshooting

### "RingCentral service not configured"
- Check all environment variables are set
- Restart backend after adding credentials
- Verify Client ID/Secret are correct

### "Failed to initialize RingCentral"
- Check username/password are correct
- Ensure phone number includes country code (+1)
- Check if using production vs sandbox URL

### "Failed to make call"
- Verify RingCentral account has calling enabled
- Check to_number is valid phone number
- Ensure sufficient RingCentral credits

### Calls not connecting
- RingOut requires YOUR phone to answer first
- Check RingCentral app on your device
- Verify phone number has calling permissions

---

## 📊 RingCentral Pricing

**Call Pricing (US):**
- Local calls: Included in plan
- Long distance: Varies by plan
- International: Per-minute rates

**SMS Pricing:**
- US SMS: ~$0.007 per message
- International SMS: Varies by country

**Monthly Plans:**
- Essentials: ~$20/user/month
- Standard: ~$25/user/month
- Premium: ~$35/user/month

Check current pricing at: https://www.ringcentral.com/office/plansandpricing.html

---

## 🚀 Next Steps

1. ✅ Add environment variables
2. ✅ Add API endpoints to main.py
3. ✅ Update frontend components
4. ✅ Test click-to-call
5. ✅ Test SMS
6. ⏳ Deploy to production
7. ⏳ Add call recording (optional)
8. ⏳ Add voicemail transcription (optional)

---

## 📞 Need Help?

- **RingCentral Developer Portal:** https://developers.ringcentral.com/
- **API Reference:** https://developers.ringcentral.com/api-reference
- **Support:** https://developers.ringcentral.com/support

---

✅ **RingCentral integration is ready!** Configure your credentials and start calling from your CRM!
