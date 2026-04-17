# LiveKit Aria Voice Agent — Design Specification

**Date**: 2026-04-17
**Status**: Draft
**Author**: Timothy Loss + Claude

## Overview

Replace the current Vapi/Twilio voice stack with a native LiveKit-based voice AI agent ("Aria") for Perennia AI mortgage CRM. Aria handles inbound calls (AI receptionist — qualify, book, route) and outbound calls (follow-ups, reminders, voicemail drops). The agent connects to the existing FastAPI backend for all CRM operations and mortgage tools.

**Hard cut** — Vapi is retired entirely, not run in parallel.

---

## Architecture

### Two-Service Model

```
Service 1: LiveKit Agent Worker (Railway)
  - Python process using livekit-agents SDK
  - Connects outbound to LiveKit Cloud (wss://aria-7q60gwyk.livekit.cloud)
  - Runs Claude conversation loop (single streaming call per voice turn)
  - All CRM/tool access via HTTP to Service 2
  - No direct DB access — hard boundary

Service 2: FastAPI Backend (Railway, existing)
  - New /internal/aria/* endpoints for agent tool calls
  - Telnyx webhook handler for inbound call routing
  - LangGraph async workflows on dedicated thread pool
  - Existing 210+ mortgage tools exposed as internal API
```

### Codebase Layout

```
backend/
  agents/                    # Agent process ONLY — no DB imports
    aria_agent.py            # LiveKit agent entrypoint + health server
    aria_tools.py            # Tool definitions — all HTTP calls to /internal/*
    aria_prompts.py          # System prompts, voicemail templates
    aria_config.py           # Voice, AMD, guardrail configuration

  routes/
    internal/                # Backend endpoints for agent tool calls
      aria_tool_routes.py    # Loan status, lead lookup, booking, etc.
      aria_workflow_routes.py # LangGraph workflow dispatch
      aria_call_routes.py    # Warm transfer, voicemail, call logging
    telnyx_call_routes.py    # Inbound/outbound call routing via Telnyx webhooks
```

The agent process never imports from `db`, `database.models`, or `services` directly. Every data access goes through `/internal/` endpoints. This boundary enables migration to Fly.io by changing one environment variable (`INTERNAL_BACKEND_URL`).

---

## Voice Turn Architecture

### Why Not LangGraph for Voice Turns

The existing Aria LangGraph engine (`backend/aria/core/conversation_engine.py`) uses a phased model: UNDERSTANDING -> SLOT_FILLING -> CONFIRMING -> EXECUTING -> RESPONDING. Each phase transition is a potential LLM call. In text chat, 3 calls at 400ms = 1.2s (acceptable). In voice, that 1.2s kills the <500ms latency target.

### Hybrid Brain

```
Voice turn arrives (STT transcript)
       |
       v
LiveKit Agent -> Claude (single streaming call)
       |         Tools = extracted from existing 210+ tool registry
       |
       +-- Simple turn (status check, rate question, doc status)
       |         -> Claude calls tool directly -> responds in <500ms
       |
       +-- Complex workflow (full qualification, multi-step booking,
                            document collection sequence)
                  -> Claude calls trigger_workflow(workflow_id, params)
                  -> LangGraph runs async on dedicated FastAPI executor
                  -> Aria responds immediately: "Got it, I'm kicking
                    that off now. You'll see it update in your pipeline."
                  -> LangGraph pushes result via websocket/notification
```

### Turn Detection

The agent must use semantic turn detection, not silence-timeout. Silence-based detection produces false starts and interruptions on hesitant borrowers (common in mortgage calls where people pause to think about financial details).

```python
# Required in AgentSession config — not optional
turn_detection=MultilingualModel(),   # semantic, not silence-based
min_endpointing_delay=0.4,            # 400ms — sweet spot for mortgage calls
max_endpointing_delay=6.0,
```

This is the single setting that most separates natural-feeling voice from IVR-feeling voice.

### What's Extracted from Existing Engine

**KEEP (as direct HTTP-callable tools):**
- All 210+ tool implementations (the actual business logic)
- Intent definitions (used as Claude tool descriptions)
- Slot schemas (used as Claude tool parameter types)
- Task executor (called directly via `/internal/aria/trigger-workflow`)

**REPLACE (for voice turns only):**
- LangGraph phase router (Claude's native tool-calling handles this)
- Multi-phase LLM reasoning (single streaming Claude call instead)
- Dialogue state machine (LiveKit AgentSession manages turn state)

---

## STT / TTS Providers

- **STT**: Deepgram (existing account, proven accuracy)
  - Plugin: `livekit-plugins-deepgram`
  - Model: `nova-3` (current generation, largest accuracy gain on telephony audio)

- **TTS**: Evaluate Cartesia vs ElevenLabs during build
  - Cartesia: `livekit-plugins-cartesia`, Sonic-3 model, ultra-low latency
  - ElevenLabs: `livekit-plugins-elevenlabs`, existing account, known voice quality
  - Decision criteria: first-byte latency, voice naturalness, cost per character
  - Default to Cartesia for voice turns (latency-critical), ElevenLabs for voicemail TTS (quality-critical)

- **LLM**: Claude via `livekit-plugins-anthropic`
  - Model: `claude-sonnet-4-20250514` for voice turns — hits the <500ms latency target where Opus would not
  - Model: `claude-opus-4-20250514` for complex tool orchestration — runs async so latency is not the constraint, accuracy matters more
  - Do not downgrade voice turns to Haiku: the quality drop on nuanced mortgage conversations is significant

---

## Telephony — Telnyx Integration

### Inbound Call Flow

```
Caller dials +18438838956 (Telnyx)
       |
       v
Telnyx webhook -> POST /telnyx/inbound (FastAPI)
       |
       v
decide_route(borrower, payload)
       |
       +-- "aria"       -> Create LiveKit room, bridge Telnyx call as SIP participant
       +-- "direct_lo"  -> Telnyx blind transfer to LO phone (hot lead + LO available)
       +-- "voicemail"  -> Bridge to voicemail LiveKit room
```

### Routing Logic

```python
async def decide_route(borrower, payload) -> str:
    if not borrower:
        return "aria"           # Unknown caller — Aria qualifies

    if borrower.qualification_status == "hot":
        lo = await crm.get_assigned_lo(borrower.id)
        if await calendar.is_lo_available(lo.id):
            return "direct_lo"  # Hot lead + LO available = skip Aria

    if is_business_hours():
        return "aria"

    return "aria"               # Default: always Aria outside business hours
```

### SIP Bridge

Telnyx call bridged into LiveKit room as SIP participant:
```python
await telnyx.bridge_to_sip(
    call_control_id=call_control_id,
    sip_uri=f"sip:{room.name}@aria-7q60gwyk.sip.livekit.cloud"
)
```

### Warm Transfer

When Aria decides to hand off to an LO:

1. Aria tells borrower: "One moment while I get Sarah on the line"
2. Backend adds LO as SIP participant to the same LiveKit room via Telnyx
3. LO's phone rings (2-4 second gap — Aria fills naturally)
4. LO picks up, can hear Aria finishing the handoff
5. Aria delivers verbal brief: "Sarah, I have Marcus on the line — he's looking at a $420k conventional purchase in Charleston, 720+ credit, ready to apply today."
6. LO speaks directly to borrower
7. Aria drops out of room, call continues LO <-> borrower on Telnyx SIP

```python
@function_tool
async def warm_transfer_to_lo(
    ctx: RunContext,
    reason: str,   # ready_to_apply, complex_scenario, customer_request
    summary: str,  # 2-sentence brief for the LO
) -> str:
    borrower_id = ctx.room.metadata["borrower_id"]
    lo = await crm.get_assigned_lo(borrower_id)

    await livekit_client.create_sip_participant(
        room_name=ctx.room.name,
        sip_trunk_id=TELNYX_TRUNK_ID,
        sip_call_to=f"sip:{lo.phone}@pstn.telnyx.com",
        participant_identity=f"lo_{lo.id}",
        participant_name=lo.full_name,
    )

    borrower = await call_backend_tool(
        "/internal/aria/lead-info", {"lead_id": borrower_id}
    )
    return (
        f"{lo.first_name}, I have {borrower['first_name']} on the line. "
        f"{summary} "
        f"I'll let you two take it from here."
    )
```

---

## Outbound Calls

### Autonomy Model

**Phase B (launch):** LO approval required for every outbound call.

**Phase C (graduated):** Per-workflow auto-approve based on performance data.

### Approval UX

Push notification with three options (not two):
```
[phone icon] Aria -> Marcus Webb
Rate lock expires tomorrow. Remind + offer extension?
[Call Now]  [Schedule for 9am]  [Skip]
```

Three-option pattern prevents false urgency. "Schedule for 9am" gives LOs control over timing while still approving Aria's judgment.

### Graduation Criteria (B -> C)

Per workflow type, evaluated over rolling 30 days:

| Workflow Type | Min Calls | LO Override Rate | Success Rate | Complaint Rate |
|---|---|---|---|---|
| appointment_reminder | 50 | <5% | >80% | 0% |
| rate_lock_reminder | 30 | <8% | >75% | 0% |
| document_chase | 40 | <10% | >70% | 0% |

When thresholds are met, LO receives: "Appointment reminders running at 83% success with zero complaints over 50 calls. Enable auto-approve for this type?"

**Never graduate (always require LO approval):**
- rate_renegotiation
- first_touch_outreach
- complaint_followup
- legal_or_escalation

### Autonomous Call Guardrails (Phase C)

Non-negotiable rules that cannot be toggled off:

```python
AUTONOMOUS_CALL_GUARDRAILS = {
    "calling_hours":          "08:00-20:00 local borrower time",
    "days_allowed":           ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    "no_call_days":           "Federal holidays + state-specific",
    "max_calls_per_lead_day": 1,
    "max_calls_per_lead_week": 3,
    "max_attempts_no_answer": 3,
    "cooling_off_after_dnc":  "permanent",

    "permitted_intents": [
        "appointment_reminder",
        "document_chase",
        "rate_lock_expiry_warning",
        "closing_date_reminder",
        "post_close_satisfaction",
    ],
    "never_autonomous": [
        "first_touch",
        "rate_renegotiation",
        "price_objection_handling",
        "complaint_resolution",
        "legal_reference_in_file",
    ],

    "immediate_lo_alert": [
        "borrower_mentions_lawyer",
        "borrower_mentions_complaint",
        "borrower_expresses_distress",
        "dnc_request",
        "three_consecutive_no_answers",
        "call_duration_under_15_seconds",
    ],
}
```

### TCPA Authorization Chain

Every call — manual, approved, or autonomous — gets an audit record:

```sql
CREATE TABLE call_authorizations (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    borrower_id             INTEGER NOT NULL REFERENCES leads(id),
    call_id                 UUID,
    authorization_type      TEXT NOT NULL,  -- 'lo_manual', 'lo_approval', 'auto_rule'
    authorized_by           INTEGER REFERENCES users(id),  -- NULL if auto_rule
    rule_id                 TEXT,
    borrower_consent_source TEXT,  -- 'web_form', 'verbal', 'signed_disclosure'
    borrower_consent_date   TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT now()
);
```

---

## Voicemail Handling

### AMD Confidence Bands

Telnyx AMD returns a confidence score, not a binary. Three-way branch:

| Confidence | Action |
|---|---|
| result=human | Route to Aria agent (live pickup) |
| result=machine, confidence >= 0.92 | Drop full TTS voicemail (Option B) |
| result=machine, confidence >= 0.75 | Drop short TTS voicemail (max 18s) |
| confidence < 0.75 or unknown | No voicemail — mark no-answer, schedule retry (Option C) |

### Telnyx AMD Configuration

```python
OUTBOUND_CALL_CONFIG = {
    "answering_machine_detection": "premium",
    "answering_machine_detection_config": {
        "total_analysis_time_millis": 6000,
        "after_greeting_silence_millis": 1000,
        "between_words_silence_millis": 1000,
        "greeting_duration_millis": 3500,
        "initial_silence_millis": 4000,
        "maximum_number_of_words": 5,
        "silence_threshold": 256,
    },
    "timeout_secs": 30,  # Ring 30 seconds before no-answer
}
```

Phone must ring before AMD fires — no ringless voicemail (RVM). RVMs are in active TCPA litigation and banned in several states.

### Voicemail Message Structure

Every voicemail does four things in under 25 seconds:
1. State who you are
2. Give one specific reason to call back
3. Tell them exactly how to reach you
4. Get off the phone

```python
VOICEMAIL_TEMPLATES = {
    "appointment_reminder": (
        "Hi {first_name}, this is Aria from Perennia. "
        "Quick reminder — you have a call with {lo_name} tomorrow at {time}. "
        "If you need to reschedule, just reply to the text I'm sending you now. "
        "Talk soon."
    ),
    "rate_lock_expiry": (
        "Hi {first_name}, Aria from Perennia. "
        "Your rate lock on the {loan_amount} {loan_type} expires {expiry_day}. "
        "{lo_name} has a couple of options to discuss — "
        "call us back at {company_phone} or just reply to my text. "
        "Thanks."
    ),
    "document_chase": (
        "Hi {first_name}, Aria from Perennia. "
        "The one thing holding up your file right now is {top_missing_doc}. "
        "You can upload it directly at the link I'm texting you — takes two minutes. "
        "Any questions, reply to that text. Thanks."
    ),
    "post_close": (
        "Hi {first_name}, Aria from Perennia — just calling to say congratulations "
        "on closing! {lo_name} wanted to check in and make sure everything's going smoothly. "
        "Give us a call at {company_phone} whenever you get a chance. "
        "Enjoy the new home."
    ),
}

MAX_VOICEMAIL_SECONDS = 28  # Telnyx cuts at 30s — 2s buffer
```

### Paired SMS (Non-Optional)

Every voicemail drop simultaneously sends an SMS matching the voicemail content. The voicemail creates awareness ("I got a call from Perennia"), the SMS creates the response path ("here's the link"). Without paired SMS, callback rates are under 8%. With it, 25-35%.

```python
async def drop_tts_voicemail(call_control_id, ctx, max_seconds=28):
    message = render_voicemail_template(ctx)
    audio_url = await tts_provider.tts_to_url(text=message, voice_id=ARIA_VOICE_ID)

    await telnyx.play_audio(call_control_id=call_control_id, audio_url=audio_url)

    # Send SMS simultaneously — don't wait for voicemail to finish
    asyncio.create_task(
        sms.send_template(borrower_id=ctx.borrower_id, template=ctx.intent)
    )

    await telnyx.hangup(call_control_id)
    await crm.log_voicemail_drop(
        borrower_id=ctx.borrower_id, intent=ctx.intent,
        message_text=message, sms_sent=True,
    )
```

---

## Agent Tool Architecture

### Circuit Breaker

All agent tool calls go through a retry-with-timeout wrapper:

```python
BACKEND_URL = os.environ["INTERNAL_BACKEND_URL"]  # http://perennia-api.railway.internal

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.1, min=0.1, max=0.3))
async def call_backend_tool(endpoint: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.post(f"{BACKEND_URL}{endpoint}", json=payload)
        resp.raise_for_status()
        return resp.json()
```

3-second timeout. Fail fast, degrade gracefully, keep the conversation moving.

### Graceful Degradation

Every tool wraps the circuit breaker with a spoken fallback:

```python
@function_tool
async def get_loan_status(ctx: RunContext) -> str:
    try:
        result = await call_backend_tool(
            "/internal/aria/loan-status",
            {"borrower_id": ctx.room.metadata["borrower_id"]}
        )
        return result["spoken_summary"]
    except Exception:
        return (
            "I'm having a little trouble pulling that up right now. "
            "Let me have your loan officer send you an update directly — "
            "I'll flag it for them."
        )
```

### LangGraph Workflow Isolation

LangGraph workflows run on a dedicated thread pool executor to avoid competing with HTTP request workers:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    langgraph_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="langgraph")
    app.state.langgraph_executor = langgraph_executor
    yield
    langgraph_executor.shutdown(wait=False)
```

---

## Deployment

### Railway Configuration

**Service 1: aria-agent-worker**
- Python process running `livekit-agents` SDK
- Health check endpoint on PORT (default 8081)
- Environment: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `INTERNAL_BACKEND_URL`, `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY` (or `ELEVEN_API_KEY`)

```toml
# railway.toml
[deploy]
startCommand = "python -m backend.agents.aria_agent start"
healthcheckPath = "/"
healthcheckTimeout = 30
restartPolicyType = "always"
```

**Service 2: perennia-api (existing)**
- New `/internal/aria/*` endpoints added
- LangGraph executor added to lifespan
- `INTERNAL_BACKEND_URL=http://perennia-api.railway.internal` set on agent worker

### Migration Trigger Criteria

**Stay on Railway if:**
- Agent restarts < 2x per week
- No dropped sessions during business hours
- Tool call latency to FastAPI < 50ms (same Railway network)
- Concurrent sessions < 20

**Migrate to Fly.io if:**
- Agent crashes correlate with high session concurrency
- Railway memory limits hit during peak (Silero VAD loads ~150MB per worker)
- Need multiple worker replicas with session affinity
- Concurrent sessions consistently > 50

---

## LiveKit Cloud Configuration

All credentials stored as environment variables on the agent worker service — never hardcoded.

| Setting | Environment Variable |
|---|---|
| Project | `aria` |
| WebSocket URL | `LIVEKIT_URL` |
| API Key | `LIVEKIT_API_KEY` |
| API Secret | `LIVEKIT_API_SECRET` |
| SIP Domain | Derived from project name: `{project}.sip.livekit.cloud` |

### SIP Trunk Setup

Telnyx SIP trunk configured in LiveKit Cloud to accept inbound from Telnyx and place outbound via Telnyx PSTN.

---

## Key Metrics

| Metric | Target |
|---|---|
| Voice turn latency (STT -> response audio start) | <500ms |
| Tool call round-trip (agent -> FastAPI -> agent) | <50ms |
| Warm transfer handoff time | <5 seconds after LO picks up |
| Voicemail drop success rate | >95% when AMD confidence >= 0.92 |
| Outbound call approval latency (LO notification -> tap) | <10 seconds |

---

## Out of Scope

- Multi-language support (English only at launch)
- Video calls via LiveKit (audio only)
- Custom wake word / always-listening mode
- Local STT/TTS (cloud providers only)
- Agent-to-agent calls (Aria talks to one party at a time)
