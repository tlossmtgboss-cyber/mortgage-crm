# Power Dialer & Click-to-Dial

Twilio-powered telephony integration for the Mortgage CRM.

## Features

- **Click-to-Dial**: One-click calling from any contact
- **Power Dialer**: Automated session-based calling through task lists
- **Real-time Updates**: WebSocket-based call status notifications
- **Voice Notes**: Record and transcribe call notes with AI summarization
- **Compliance**: TCPA-compliant calling hours and DNC list management
- **Analytics**: Call metrics, connect rates, and performance tracking

## Quick Start

### 1. Environment Variables

Add to your `.env` file:

```bash
# Twilio Configuration
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token

# Base URL for webhooks
BASE_URL=https://your-domain.com

# OpenAI for voice note transcription (optional)
OPENAI_API_KEY=your_openai_key
```

### 2. Twilio Console Setup

1. Log in to [Twilio Console](https://console.twilio.com)
2. Note your Account SID and Auth Token
3. Configure webhooks for your Twilio phone number:
   - **Status Callback URL**: `https://your-domain.com/api/v1/dialer/webhook/status`
   - **Voice URL**: `https://your-domain.com/api/v1/dialer/twiml/outbound`

### 3. Verify Caller IDs

Before making calls, verify your caller IDs:

```bash
# Start verification
POST /api/v1/dialer/admin/caller-ids/verify
{
  "phone_number": "+15551234567",
  "friendly_name": "Main Office"
}
# Twilio will call the number with a verification code
```

### 4. Configure Agent Settings

Each agent needs telephony settings:

```bash
PUT /api/v1/dialer/settings
{
  "cell_phone": "+15551234567",
  "business_caller_id": "+18005551234",
  "dialer_enabled": true,
  "max_calls_per_day": 100,
  "auto_advance": true,
  "pause_between_calls": 3
}
```

## API Endpoints

### Click-to-Dial

```bash
# Initiate a single call
POST /api/v1/dialer/click-to-dial
{
  "phone_number": "+15559876543",
  "contact_name": "John Smith",
  "loan_id": 123,
  "task_id": 456
}
```

### Power Dialer Sessions

```bash
# Start a dialer session
POST /api/v1/dialer/sessions
{
  "task_ids": [1, 2, 3, 4, 5]
}

# Get active session
GET /api/v1/dialer/sessions/active

# Pause session
POST /api/v1/dialer/sessions/{session_id}/pause

# Resume session
POST /api/v1/dialer/sessions/{session_id}/resume

# Stop session
POST /api/v1/dialer/sessions/{session_id}/stop

# Skip current task
POST /api/v1/dialer/sessions/{session_id}/tasks/{task_id}/skip
```

### Dispositions

```bash
# Submit disposition for session task
POST /api/v1/dialer/task/{task_id}/disposition
{
  "disposition": "Answered - Conversation completed",
  "notes": "Discussed refinance options",
  "follow_up_date": "2024-01-15T10:00:00Z",
  "voice_note_audio": "base64_encoded_audio",
  "follow_up_required": true,
  "referral_opportunity": false
}

# Submit disposition for click-to-dial
POST /api/v1/dialer/call-log/{call_log_id}/disposition

# Get disposition options
GET /api/v1/dialer/dispositions
```

### Analytics

```bash
# Daily summary
GET /api/v1/dialer/analytics/daily-summary?target_date=2024-01-15

# Disposition breakdown
GET /api/v1/dialer/analytics/disposition-breakdown?start_date=2024-01-01&end_date=2024-01-31

# Best calling hours
GET /api/v1/dialer/analytics/connect-rate-by-hour?start_date=2024-01-01&end_date=2024-01-31

# Agent performance
GET /api/v1/dialer/analytics/performance?date_range=last_7_days

# Session analytics
GET /api/v1/dialer/analytics/sessions
```

### Admin

```bash
# List caller IDs
GET /api/v1/dialer/admin/caller-ids

# Verify new caller ID
POST /api/v1/dialer/admin/caller-ids/verify

# Set default caller ID
POST /api/v1/dialer/admin/caller-ids/{id}/set-default

# Telephony status
GET /api/v1/dialer/admin/telephony/status
```

### Compliance

```bash
# Check if number can be called
GET /api/v1/dialer/compliance/check?phone_number=+15551234567

# Add to DNC list
POST /api/v1/dialer/dnc/add
{
  "phone_number": "+15551234567",
  "reason": "customer_request"
}
```

## WebSocket Events

Connect to receive real-time updates:

```javascript
const ws = new WebSocket('wss://your-domain.com/api/v1/dialer/ws/{agent_id}');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case 'call_status_update':
      // Call status changed (ringing, connected, completed)
      break;
    case 'click_to_dial_status':
      // Click-to-dial call status
      break;
    case 'disposition_saved':
      // Disposition was saved
      break;
  }
};

// Keep connection alive with ping/pong
setInterval(() => ws.send('ping'), 30000);
```

## Call Flow

### Click-to-Dial Flow

1. Agent clicks "Call" button
2. Backend calls agent's cell phone first
3. Agent answers
4. Backend bridges to contact's number
5. Call status updates via WebSocket
6. Call ends → Disposition modal appears
7. Agent submits disposition

### Power Dialer Flow

1. Agent starts session with task IDs
2. System initiates first call automatically
3. Agent's phone rings, they answer
4. System bridges to contact
5. Call completes → Disposition modal
6. Agent submits disposition
7. After delay, next call initiates automatically
8. Repeat until session complete or paused

## Voice Notes

Voice notes are:
1. Recorded in browser (WebM format)
2. Sent as base64 to backend
3. Transcribed via OpenAI Whisper
4. Summarized with GPT-4o-mini
5. Stored with the disposition

## Compliance Features

- **TCPA Hours**: Blocks calls outside 8am-9pm local time
- **DNC List**: Internal do-not-call list management
- **Soft Locks**: Prevents multiple agents calling same contact
- **Call Limits**: Configurable max calls per day
- **Consent Tracking**: Records calling consent status

## File Structure

```
backend/telephony/
├── __init__.py           # Module exports
├── provider.py           # Twilio integration
├── dialer_engine.py      # Session management
├── compliance.py         # TCPA/DNC compliance
├── websocket.py          # Real-time events
├── schemas.py            # Pydantic models
├── disposition_router.py # Disposition endpoints
├── analytics_router.py   # Analytics endpoints
├── admin_router.py       # Admin endpoints
└── README.md             # This file

frontend/src/
├── types/dialer.js       # Type definitions
├── hooks/
│   ├── useDialerWebSocket.js
│   └── useDialerSession.js
└── components/dialer/
    ├── ClickToDialButton.js
    ├── ClickToDialModal.js
    ├── DialerPanel.js
    └── DispositionModal.js
```
