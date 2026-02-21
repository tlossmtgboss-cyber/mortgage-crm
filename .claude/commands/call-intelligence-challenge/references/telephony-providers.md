# Telephony Providers — Configuration & Validation Reference

## Overview

Perennia AI uses four telephony providers, each serving distinct purposes. No single provider handles everything — understanding the routing is critical.

## Provider Matrix

| Provider | Purpose | Auth Method | Key Env Vars |
|----------|---------|-------------|--------------|
| **Twilio** | Voice calls, SMS, Intelligence, Click-to-call | Account SID + Auth Token | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` |
| **Telnyx** | Direct SIP telephony, Click-to-call, SMS | API Key (v2) | `TELNYX_API_KEY`, `TELNYX_PHONE_NUMBER` |
| **Vapi** | AI voicemail drops, AI receptionist, Outbound AI calls | API Key + Webhook Secret | `VAPI_API_KEY`, `VAPI_WEBHOOK_SECRET` |
| **Retell** | AI voice agents, Advanced voice AI | API Key | `RETELL_API_KEY` |

### Secondary Provider
| Provider | Purpose | Auth Method | Key Env Vars |
|----------|---------|-------------|--------------|
| **Slybroadcast** | Ringless voicemail (RVM) | Username + Password | `SLYBROADCAST_UID` (email), `SLYBROADCAST_PASSWORD` |

---

## Twilio Configuration

### Service Files
```
backend/integrations/twilio_service.py              (208 lines)  — Core Twilio client
backend/integrations/twilio_voice_service.py         (381 lines)  — Voice call management
backend/integrations/twilio_intelligence_service.py  (594 lines)  — Call transcription & analysis
backend/integrations/twilio_lookup_service.py        (248 lines)  — Phone number validation
backend/routes/twilio_setup_routes.py                             — Setup endpoints
backend/routes/twilio_status_callback_routes.py                   — Status callbacks
backend/services/twilio_click_to_call.py             (753 lines)  — Click-to-call impl
```

### Intelligence Service
The Twilio Intelligence Service provides:
- Automatic transcription with speaker diarization
- PII redaction (phone, SSN, credit card)
- Sentiment analysis
- Entity recognition (names, amounts, dates)
- Conversation summarization
- Escalation detection
- Recording disclosure compliance

**Setup requirement**: Must create an Intelligence Service SID (one-time):
```python
# Twilio Intelligence operators
OPERATORS = [
    "sentiment",           # Call sentiment scoring
    "summary",             # Conversation summary
    "entity",              # Entity extraction
    "escalation",          # Escalation detection
    "recording_disclosure" # Consent/disclosure validation
]
```

**Audio constraints**: WAV, MP3, FLAC | max 3GB | max 8 hours

### Dual Twilio Accounts
Perennia uses TWO Twilio accounts:
1. **Primary**: Main CRM telephony (calls, SMS, Intelligence)
2. **Vapi-backed**: `+18434169589` (voicemail/receptionist) and `+18326482297` (different account)

### Known Issues
- AUTH_TOKEN had trailing `\n` (Feb 2026) — caused intermittent auth failures
- Always verify: `len(TWILIO_AUTH_TOKEN.strip()) == len(TWILIO_AUTH_TOKEN)`

---

## Telnyx Configuration

### Service Files
```
backend/integrations/telnyx_retell_bridge.py  (450 lines)  — Telnyx-to-Retell bridge
backend/routes/telnyx_setup_routes.py                      — Setup endpoints
backend/routes/telnyx_webhook_routes.py                    — Webhook handlers
backend/routes/telnyx_retell_routes.py                     — Retell integration routes
```

### Known Issues
- **API key INVALID** (Feb 2026): `KEY0185C2...` rejected by Telnyx API as malformed
- Needs rotation/update in Railway environment variables
- Until fixed, Telnyx-dependent features (direct SIP, Telnyx SMS) are non-functional

### Validation
```python
# Test Telnyx API key validity
import telnyx
telnyx.api_key = os.getenv("TELNYX_API_KEY")
try:
    telnyx.MessagingProfile.list(page_size=1)
    print("Telnyx API key valid")
except telnyx.error.AuthenticationError:
    print("INVALID — rotate key")
```

---

## Vapi Configuration

### Service Files
```
backend/vapi_routes.py        — Webhook & API endpoints
backend/vapi_service.py       — Vapi client service
backend/vapi_models.py        — Data models
vapi_assistant_*.json          — Assistant configurations
vapi_voice_*.json              — Voice configurations
vapi_transcriber_fix.json      — Transcriber patches
```

### VoicemailDetection Format (2025+)
```json
// OLD FORMAT (REJECTED by Vapi API)
{
  "enabled": true,
  "machineDetectionTimeout": 30,
  "voicemailMessage": "Hi, this is..."
}

// NEW FORMAT (REQUIRED)
{
  "provider": "vapi",
  "beepMaxAwaitSeconds": 25
}
// voicemailMessage goes at assistant level, NOT inside voicemailDetection
```

### Voice Configuration
```json
// BROKEN — 11labs/paula does NOT exist
{ "provider": "11labs", "voiceId": "paula" }
// ERROR: pipeline-error-eleven-labs-voice-not-found

// CORRECT — deepgram/asteria (matches Vapi assistant default)
{ "provider": "deepgram", "voiceId": "asteria" }
```

### Webhook Authentication
Vapi webhooks use `X-Vapi-Secret` header for authentication.

---

## Retell Configuration

### Service Files
```
backend/integrations/retell_service.py  (610 lines)  — Full Retell AI management
backend/routes/retell_routes.py                       — Retell API endpoints
```

### Capabilities
- Agent creation, update, delete
- Phone number management
- Call initiation and management
- LLM configuration (Retell default, custom, OpenAI)
- Voice options:
  - **11labs**: Emma, Dorothy, Matilda, Rachel, Adam, Josh, Michael, Chris
  - **OpenAI**: Alloy, Echo, Nova, Shimmer
- Call settings: silence timeout (30s), max duration (1 hour)

---

## Slybroadcast Configuration

### API Reference
```
URL:      https://mobile-sphere.com/gateway/vmb.php
Account:  tloss@cmghomeloans.com (NOT cmgfi.com)
Method:   POST with form data

Required fields:
  c_uid       — Account email
  c_password  — Account password
  c_phone     — Recipient phone (E.164)
  c_url       — Audio file URL (must be > 5 seconds)
  c_callerID  — Caller ID to display

Response (plain text):
  OK
  session_id=12345
  number of phone=1

Status check:
  c_option=callstatus
  session_id=12345
  c_phone=+1XXXXXXXXXX

Webhook:
  $_POST['var'] = 6 pipe-delimited quoted fields
  Example: "field1"|"field2"|"field3"|"field4"|"field5"|"field6"
```

---

## Provider Health Validation Script

```python
"""Quick provider health check — run from backend/"""
import os, httpx

async def check_providers():
    results = {}

    # Twilio
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if sid and token:
        if token != token.strip():
            results["twilio"] = "WARN: AUTH_TOKEN has whitespace"
        else:
            async with httpx.AsyncClient() as c:
                r = await c.get(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json",
                    auth=(sid, token)
                )
                results["twilio"] = "OK" if r.status_code == 200 else f"FAIL: {r.status_code}"
    else:
        results["twilio"] = "MISSING credentials"

    # Telnyx
    telnyx_key = os.getenv("TELNYX_API_KEY", "")
    if telnyx_key:
        async with httpx.AsyncClient() as c:
            r = await c.get(
                "https://api.telnyx.com/v2/messaging_profiles",
                headers={"Authorization": f"Bearer {telnyx_key}"},
                params={"page[size]": 1}
            )
            results["telnyx"] = "OK" if r.status_code == 200 else f"FAIL: {r.status_code}"
    else:
        results["telnyx"] = "MISSING credentials"

    # Vapi
    vapi_key = os.getenv("VAPI_API_KEY", "")
    if vapi_key:
        async with httpx.AsyncClient() as c:
            r = await c.get(
                "https://api.vapi.ai/assistant",
                headers={"Authorization": f"Bearer {vapi_key}"},
                params={"limit": 1}
            )
            results["vapi"] = "OK" if r.status_code == 200 else f"FAIL: {r.status_code}"
    else:
        results["vapi"] = "MISSING credentials"

    # Retell
    retell_key = os.getenv("RETELL_API_KEY", "")
    if retell_key:
        async with httpx.AsyncClient() as c:
            r = await c.get(
                "https://api.retellai.com/list-agents",
                headers={"Authorization": f"Bearer {retell_key}"}
            )
            results["retell"] = "OK" if r.status_code == 200 else f"FAIL: {r.status_code}"
    else:
        results["retell"] = "MISSING credentials"

    return results
```
