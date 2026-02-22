# Telephony Provider Consolidation

## Current State
- Dual providers: Telnyx AND Twilio (with Vapi on top)
- Three separate credential management flows
- Three webhook handlers
- Three failure modes and billing relationships
- Telnyx API key is currently invalid
- Unnecessary complexity with no business justification

## Recommendation: Consolidate to Twilio

### Why Twilio Over Telnyx

| Factor | Twilio | Telnyx |
|--------|--------|--------|
| Current state | Active, working | API key invalid |
| Industry adoption | Dominant in mortgage tech | Emerging |
| Vapi compatibility | Native integration | Supported but less mature |
| Documentation | Extensive | Good but smaller community |
| Existing code | More Perennia features built on it | Fewer integrations |
| Compliance (TCPA) | Robust DNC/compliance tools | Basic |

The decision is straightforward: Twilio has more Perennia code depending on it, the Telnyx key is already broken, and Twilio's compliance tooling is superior for mortgage (TCPA/DNC matters).

## Migration Playbook

### Phase 1: Audit Current Usage (Day 1)

```bash
# Find all Telnyx references
grep -rn "telnyx\|TELNYX" --include="*.py" --include="*.js" --include="*.ts" --include="*.env*"

# Find all Twilio references
grep -rn "twilio\|TWILIO" --include="*.py" --include="*.js" --include="*.ts" --include="*.env*"

# Map which features use which provider:
# - Outbound calls: Twilio? Telnyx? Both?
# - Inbound calls: Which webhooks?
# - SMS: Which provider?
# - Voicemail drop: Which provider?
# - Power dialer: Which provider?
# - AI receptionist: Vapi → which underlying provider?
```

Document every feature and its current provider dependency.

### Phase 2: Migrate Telnyx Features to Twilio (Days 2–5)

For each feature currently on Telnyx:

1. **Identify the Telnyx API calls** in the codebase
2. **Map to Twilio equivalents**:
   - Telnyx `Call Control` → Twilio `Programmable Voice`
   - Telnyx `Messaging` → Twilio `Programmable Messaging`
   - Telnyx `Number Management` → Twilio `Phone Numbers`
   - Telnyx `SIP Trunking` → Twilio `Elastic SIP Trunking`
3. **Update webhook handlers** — Telnyx and Twilio have different webhook payload formats
4. **Test each feature** after migration

### Phase 3: Remove Telnyx Code (Days 5–7)

```bash
# Remove Telnyx dependency
pip uninstall telnyx
# Remove from requirements.txt / requirements.lock

# Remove Telnyx config
# Delete TELNYX_API_KEY, TELNYX_* from .env files and config

# Remove Telnyx service files
# Delete any telnyx_service.py, telnyx_webhooks.py, etc.

# Remove Telnyx webhook routes
# Delete /api/webhooks/telnyx/* endpoints

# Update provider selection logic
# Remove any if/else that chooses between Twilio and Telnyx
```

### Phase 4: Simplify Telephony Architecture (Day 7–10)

Create a clean telephony service layer:

```python
# app/services/telephony/service.py
"""
Single telephony service backed by Twilio.
All telephony features go through this service — no direct Twilio
imports anywhere else in the codebase.
"""
from twilio.rest import Client
from app.core.config import settings

class TelephonyService:
    def __init__(self):
        self.client = Client(
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN
        )

    async def make_call(self, from_number: str, to_number: str, **kwargs) -> dict:
        """Initiate an outbound call."""
        call = self.client.calls.create(
            to=to_number,
            from_=from_number,
            url=kwargs.get("twiml_url", f"{settings.BASE_URL}/api/telephony/twiml/outbound"),
            status_callback=f"{settings.BASE_URL}/api/webhooks/twilio/call-status",
            **{k: v for k, v in kwargs.items() if k not in ("twiml_url",)}
        )
        return {"call_sid": call.sid, "status": call.status}

    async def send_sms(self, from_number: str, to_number: str, body: str) -> dict:
        """Send an SMS message."""
        message = self.client.messages.create(
            to=to_number,
            from_=from_number,
            body=body,
            status_callback=f"{settings.BASE_URL}/api/webhooks/twilio/sms-status"
        )
        return {"message_sid": message.sid, "status": message.status}

    async def drop_voicemail(self, call_sid: str, audio_url: str) -> dict:
        """Drop a pre-recorded voicemail on an active call."""
        call = self.client.calls(call_sid).update(
            twiml=f'<Response><Play>{audio_url}</Play><Hangup/></Response>'
        )
        return {"status": call.status}

    async def check_dnc(self, phone_number: str) -> bool:
        """Check if a number is on the Do Not Call list."""
        # Implement DNC check logic
        pass

# Singleton
telephony = TelephonyService()
```

### Webhook Consolidation

Before: 3 webhook handlers (Twilio + Telnyx + Vapi)
After: 1 webhook router for Twilio + 1 for Vapi (if Vapi is kept)

```python
# app/routes/webhooks/twilio.py
from fastapi import APIRouter, Request
from app.services.telephony.service import telephony

router = APIRouter(prefix="/api/webhooks/twilio")

@router.post("/call-status")
async def handle_call_status(request: Request):
    """Handle Twilio call status callbacks."""
    form = await request.form()
    call_sid = form.get("CallSid")
    status = form.get("CallStatus")
    # Update call record in database
    ...

@router.post("/sms-status")
async def handle_sms_status(request: Request):
    """Handle Twilio SMS delivery callbacks."""
    form = await request.form()
    message_sid = form.get("MessageSid")
    status = form.get("MessageStatus")
    ...

@router.post("/incoming-call")
async def handle_incoming_call(request: Request):
    """Handle inbound calls — route to AI receptionist or LO."""
    ...
```

## Environment Cleanup

Remove from all `.env` files:
```
# DELETE these
TELNYX_API_KEY=
TELNYX_API_SECRET=
TELNYX_PUBLIC_KEY=
TELNYX_MESSAGING_PROFILE_ID=
TELNYX_CONNECTION_ID=

# KEEP these
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
VAPI_API_KEY=  # If keeping Vapi
```

## Validation Checklist

- [ ] All Telnyx references removed from codebase (`grep -rn telnyx` returns 0)
- [ ] Telnyx package removed from requirements
- [ ] All outbound calls route through Twilio
- [ ] All SMS messages route through Twilio
- [ ] Voicemail drop works via Twilio
- [ ] Power dialer works via Twilio
- [ ] Inbound call webhooks consolidated to single handler
- [ ] DNC checking works with Twilio
- [ ] No dead Telnyx API keys in config
- [ ] Vapi integration (if kept) routes through Twilio as carrier
