# Perennia AI — URLA 1003 Voice Agent

Dedicated LiveKit-based voice agent for intake of the full Uniform Residential Loan Application (Fannie Mae Form 1003 / Freddie Mac Form 65, 2021 redesigned). Separate from Aria (the Vapi receptionist).

---

## What this is

A production-grade, resumable, multi-tenant URLA intake agent. The caller speaks; the agent walks them through all nine URLA sections, saves progress continuously in Redis, and pushes a finalized ULAD payload to BytePro on completion.

**Stack**
- LiveKit Agents 1.0+ (orchestration)
- Deepgram Nova-3 (STT)
- OpenAI GPT-4o or Anthropic Claude (LLM)
- Cartesia Sonic-3 (TTS)
- Silero (VAD)
- Redis (session state, 30-day TTL)
- httpx (BytePro push)
- Pydantic v2 (ULAD-aligned schema)

**Coverage**
- URLA Sections 1 (1a–1e), 2 (2a–2d), 3, 4 (4a–4d), 5 (5a–5b), 6, 7, 8, 9
- Per-borrower sections under `Borrower` records (primary + co-borrowers)
- Shared sections (2, 3, 4, 6, 9) at the top-level application
- Verbal consent capture with timestamp + recording URL hook for Section 6
- Reg B / HMDA demographic notice read verbatim before Section 8
- Caller can pause on any section and resume on a later call using phone + loan ID

---

## Package layout

```
urla_workflow/
├── requirements.txt
└── src/
    └── urla/
        ├── __init__.py                  # public API
        ├── models.py                    # Pydantic schema — all 9 sections + booking
        ├── prompts.py                   # voice-first prompts + compliance scripts
        ├── state.py                     # Redis-backed URLAStateManager
        ├── validators.py                # SSN / date / currency / state / phone parsers
        ├── bytepro_adapter.py           # BytePro LOS push via ULAD JSON
        ├── smart_calendar_adapter.py    # CRM Smart Calendar — availability + booking
        ├── agent.py                     # URLAAgent with @function_tool methods
        └── entrypoint.py                # LiveKit worker entrypoint
```

---

## Environment variables

### Required

| Var | Purpose |
|---|---|
| `LIVEKIT_URL` | wss://your-livekit-deployment |
| `LIVEKIT_API_KEY` | LiveKit server API key |
| `LIVEKIT_API_SECRET` | LiveKit server API secret |
| `DEEPGRAM_API_KEY` | Deepgram Nova-3 STT |
| `CARTESIA_API_KEY` | Cartesia Sonic-3 TTS |
| `OPENAI_API_KEY` | GPT-4o (or swap to `ANTHROPIC_API_KEY` if using Claude) |
| `REDIS_URL` | e.g. `redis://default:pw@host:6379` |
| `BYTEPRO_API_BASE_URL` | e.g. `https://api.bytepro.perennia.ai` |
| `BYTEPRO_API_KEY` | BytePro service account bearer token |
| `SMART_CALENDAR_API_BASE_URL` | CRM Smart Calendar base URL, e.g. `https://api.perennia.ai` |
| `SMART_CALENDAR_API_KEY` | Smart Calendar service account bearer token |

### Optional with defaults

| Var | Default |
|---|---|
| `URLA_TENANT_ID` | `perennia` |
| `URLA_AGENT_NAME` | `urla-agent` |
| `URLA_LLM_MODEL` | `gpt-4o` |
| `URLA_TTS_VOICE` | Cartesia Sonic default |
| `URLA_SESSION_TTL_SECONDS` | `2592000` (30 days) |
| `URLA_LOG_LEVEL` | `INFO` |
| `BYTEPRO_TENANT_ID_HEADER` | `X-Tenant-ID` |
| `BYTEPRO_TIMEOUT` | `30` |
| `BYTEPRO_MAX_RETRIES` | `3` |
| `SMART_CALENDAR_TENANT_HEADER` | `X-Tenant-ID` |
| `SMART_CALENDAR_TIMEOUT` | `15` |
| `SMART_CALENDAR_MAX_RETRIES` | `3` |
| `SMART_CALENDAR_KICKOFF_MINUTES` | `30` (kickoff meeting duration) |
| `SMART_CALENDAR_LOOKAHEAD_DAYS` | `5` (business days to offer from) |
| `SMART_CALENDAR_MAX_SLOTS` | `4` (how many slots the agent offers at once) |
| `URLA_DEFAULT_LO_NAME` | `Perennia Loan Team` |
| `URLA_DEFAULT_LO_NMLSR` | `0000000` |
| `URLA_DEFAULT_LO_EMAIL` | `loans@perennia.ai` |
| `URLA_DEFAULT_LO_PHONE` | `+18005551212` |
| `URLA_ORG_NAME` | `Perennia AI` |
| `URLA_ORG_NMLSR` | `0000000` |

---

## Run it

### Install
```bash
pip install -r requirements.txt
```

### Dev (hot reload against a LiveKit dev room)
```bash
python -m urla.entrypoint dev
```

### Production
```bash
python -m urla.entrypoint start
```

### Docker (sketch)
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
ENV PYTHONPATH=/app/src
CMD ["python", "-m", "urla.entrypoint", "start"]
```

---

## SIP / telephony dispatch

The URLA agent is a separate worker from Aria. Route inbound calls destined for URLA intake to this worker using LiveKit's dispatch rules.

**LiveKit dispatch rule (SIP)**
```yaml
name: urla-intake
trunk_ids: [<your-telnyx-or-twilio-sip-trunk-id>]
rule:
  dispatchRuleIndividual:
    roomPrefix: urla-
    agentName: urla-agent      # matches WorkerOptions(agent_name=...)
```

When a call hits the SIP trunk, LiveKit creates a room, the URLA worker picks it up, extracts the caller's phone from the SIP participant identity, and kicks off the session.

**Per-call context the entrypoint reads**
- `caller_phone` — from the SIP participant identity (or `job.metadata` fallback)
- `tenant_id` — from `URLA_TENANT_ID` env var
- `loan_officer` — from `URLA_DEFAULT_LO_*` env vars; in production, look up the assigned LO by caller phone against the Perennia CRM and pass it into `URLAAgent(...)` instead of the env defaults

---

## Compliance notes

- **ECOA / Reg B (Section 8)**: The `DEMOGRAPHICS_NOTICE` in `prompts.py` is read verbatim before any demographic question. Demographics are voluntary; the agent accepts decline-to-provide and stores `NOT_PROVIDED` accordingly. Application channel is flagged as `TELEPHONE` per 12 CFR 1002.13(a)(1).
- **Verbal consent (Section 6)**: Captured via `capture_verbal_consent` with a UTC timestamp. Wire your call-recording pipeline to pass the recording URL so it's stored on the application record. The caller still signs the formal acknowledgments electronically post-call.
- **GLBA Safeguards**: PII (SSN, DOB, account numbers) is only logged via last-4 in diagnostic logs. Full values live in Redis with TTL and the BytePro payload only.
- **NMLS**: Section 9 is auto-populated from the assigned LO on finalize. The agent repeatedly deflects rate-quote and qualification questions to the licensed MLO — see `prompts.COMPLIANCE_DEFLECTION_*`.
- **State licensing**: The calling experience is identical across states. Per-state disclosure needs (e.g., CA Dodd-Frank amendments) should be layered in at the LO-level post-call, or injected into `SYSTEM_PROMPT` via the entrypoint based on the caller's state.

---

## LO kickoff booking (Smart Calendar)

Immediately after `finalize_urla` succeeds, Avery offers the caller a kickoff call with their assigned loan officer. The booking goes through the Perennia CRM's **Smart Calendar**, which owns per-LO availability, round-robin, buffers, and calendar invites / confirmation emails.

**Flow (3 tools, offer-then-pick)**

1. `offer_lo_kickoff_slots(lookahead_days=5)` — calls `GET /v1/calendar/availability` on the Smart Calendar. Returns up to `SMART_CALENDAR_MAX_SLOTS` slots for the assigned LO (by NMLSR ID), each with a 1-indexed `option_number` and a `voice_description` ready for natural readback (e.g. *"Thursday, April 23rd at 10 AM Eastern"*). The slots are cached on the agent for the next step.
2. Avery reads the options back and lets the caller pick. If the caller wants different days, Avery just calls `offer_lo_kickoff_slots` again with a larger `lookahead_days`.
3. `book_lo_kickoff_call(slot_choice=N)` — POSTs to `/v1/calendar/bookings` with `X-Idempotency-Key: {loan_id}:{slot_id}`, attaches both the LO (by NMLSR) and the borrower (by name/phone/email), asks the Smart Calendar to send calendar invites + confirmation emails, persists the booking on the application record, and closes the session cleanly.

**Edge cases handled**

- **Race condition (409)** — If the slot was taken between availability fetch and booking, the Smart Calendar returns 409. The tool clears the cached slots and prompts Avery to pull fresh options — no retry on 409.
- **No slots available** — `offer_lo_kickoff_slots` returns `slots_found: 0` with a `fallback_message`. Avery delivers the fallback verbally and calls `skip_kickoff_booking`.
- **Calendar down** — Up to `SMART_CALENDAR_MAX_RETRIES` retries with exponential backoff on 5xx/transient failures. If the booking step fails after retries, the session still closes cleanly (the app is already submitted to BytePro) and the LO is asked to follow up directly.
- **Caller declines** — `skip_kickoff_booking(reason=...)` wraps up with a promise that the LO will reach out directly.

**Expected Smart Calendar API contract**

```
GET /v1/calendar/availability?loan_officer_nmlsr_id=...&duration_minutes=30&lookahead_days=5&max_slots=4&meeting_type=URLA_KICKOFF
→ { "slots": [ { "slot_id", "start" (ISO8601+tz), "end", "loan_officer_nmlsr_id", "loan_officer_name", "timezone" (IANA) } ] }

POST /v1/calendar/bookings
Headers: X-Idempotency-Key: {loan_id}:{slot_id}
Body:    { slot_id, meeting_type, meeting_title, duration_minutes,
           attendees: [{role:"loan_officer", nmlsr_id}, {role:"borrower", name, phone, email}],
           related_loan_id, notes, send_confirmations: true }
→ 200/201 { event_id, confirmation_number, scheduled_start, scheduled_end, timezone, loan_officer_name }
→ 409     (slot no longer available — agent re-offers)
```

**Persistence**

When a booking succeeds, `URLAApplication.lo_kickoff_booking` is populated with event ID, confirmation number, scheduled window, timezone, and LO name. This is included in the Redis record for 30 days and serialized in `to_ulad_dict()`, so any downstream system (CRM sync, Salesforce mirror, BytePro note) can read it.



- On every tool call that mutates state, the agent saves back to Redis and refreshes the 30-day TTL.
- Each caller phone has an "active loan" pointer (`urla:{tenant}:active:{phone}`) that points at the most recent in-progress application.
- The entrypoint reads that pointer on call start. If an active loan exists, the greeting switches to `GREETING_RETURNING_CALLER_TEMPLATE` and the agent's `_active_loan_id` is pre-loaded.
- A caller can also supply their loan ID verbally to resume a specific application (`resume_urla_application(loan_id=...)`).
- On `finalize_urla` the active pointer is cleared so the next call starts fresh.

---

## LiveKit decorator note

This package uses `@function_tool` from `livekit.agents`, which is the current stable API (LiveKit Agents 1.0+, released 2025). If you're pinned to an older version using `@llm.tool` or `@llm.ai_callable()`:

```python
# Old
from livekit.agents import llm
@llm.tool
async def my_tool(...):

# New (what this package uses)
from livekit.agents import function_tool
@function_tool
async def my_tool(...):
```

Method bodies are identical — decorator swap only.

---

## Swapping LLM provider

### Claude instead of GPT-4o
```bash
pip install livekit-plugins-anthropic
```
```python
# In entrypoint.py, replace:
from livekit.plugins import openai
# with:
from livekit.plugins import anthropic

# And the session LLM:
llm=anthropic.LLM(model="claude-sonnet-4-5", temperature=0.2),
```

Set `ANTHROPIC_API_KEY` instead of `OPENAI_API_KEY`.

---

## Testing

### Syntax check
```bash
python -m py_compile src/urla/*.py
```

### Model roundtrip (what I ran during build)
```python
from urla.models import URLAApplication
# build a minimal app -> app.validate_complete() returns [] when complete
# app.model_dump_json() -> model_validate_json roundtrip preserves all fields
```

### Validator harness
```python
from urla import validators as V
V.parse_ssn("five five five four four three three two two")  # -> "555-44-3322"
V.parse_date("June 15, 1988")                                 # -> date(1988,6,15)
V.parse_currency("four thousand five hundred")                # -> Decimal("4500")
V.parse_state("south carolina")                               # -> "SC"
V.parse_phone("843-555-1212")                                 # -> "+18435551212"
V.parse_yes_no("absolutely")                                  # -> True
```

### End-to-end local smoke (no telephony)
```bash
python -m urla.entrypoint dev
```
Then use the LiveKit Playground to connect a browser client, simulate a call, and walk through the workflow.

---

## Key design calls (why things are the way they are)

- **All fields Optional at the top level.** Callers interrupt, pause, and come back. Partial state must persist. Hard requirements are enforced once, at finalize, via `URLAApplication.validate_complete()`.
- **Enums use ULAD controlled vocabularies.** The BytePro mapping is near-1:1 — `to_ulad_dict()` is the only thing the adapter needs.
- **Validators are explicit and voice-aware.** Deepgram returns spelled-out digits, mixed case states, "four thousand five hundred" for currency. The validators handle all of that without an extra LLM roundtrip.
- **Section 8 handled with care.** The notice is read before questions, decline-to-provide is first-class, and the channel is correctly flagged `TELEPHONE`.
- **`_norm_enum` tolerates loose LLM output.** If GPT-4o returns `"PURCHASE"` or `"purchase"` or `"Primary Residence"`, the normalizer finds the right enum value without throwing.
- **Idempotency on BytePro push.** The `X-Idempotency-Key` header uses the Perennia loan ID, so retries don't duplicate.
- **Multi-tenant scoping end-to-end.** Redis keys, BytePro header, and the agent constructor all honor `tenant_id`.

---

## What's NOT in this package (and where to put it)

- **LO lookup by caller phone.** The entrypoint reads LO from env. In production, replace `_loan_officer_from_env()` with a CRM lookup against the Perennia backend.
- **Call recording URL capture.** `Section6_Acknowledgments.verbal_consent_recording_url` exists; wire your telephony webhook to set it post-call.
- **Salesforce mirror.** BytePro is the system of record for the loan. If you want a parallel Salesforce mirror, add a sibling adapter and call it from `finalize_urla` alongside `push_to_bytepro`. The `lo_kickoff_booking` record on the application makes it easy to mirror the scheduled meeting too.
- **Per-state disclosure overlays.** Would go in `prompts.py` as a dict keyed by state, selected at session start from the caller's current address.
- **SMS/email confirmation of submission.** The Smart Calendar already dispatches calendar invites + confirmation emails for the kickoff call. If you also want a separate "application received" SMS/email independent of the booking, wire it into `finalize_urla` alongside the BytePro push.

---

## Quick reference — tool catalog

| Section | Tool | Purpose |
|---|---|---|
| Lifecycle | `start_urla_application` | Create new loan ID |
| Lifecycle | `resume_urla_application` | Pick up prior session |
| Lifecycle | `get_urla_status` | Progress snapshot |
| Lifecycle | `pause_application` | Save + pause |
| Lifecycle | `request_human_transfer` | Hand off to LO |
| 1a | `save_section_1a_personal`, `save_prior_address` | Identity + residence |
| 1b | `save_section_1b_employment`, `mark_no_current_employment` | Current job + income |
| 1c | `save_additional_employment`, `no_additional_employment` | Second jobs |
| 1d | `save_previous_employment`, `no_previous_employment_needed` | Prior job (<2yr tenure) |
| 1e | `add_other_income_source`, `complete_other_income` | Non-employment income |
| 2 | `add_asset`, `add_other_credit`, `add_liability`, `add_other_liability`, `complete_section_2` | Assets & debts |
| 3 | `add_property_owned`, `add_mortgage_on_reo`, `no_real_estate_owned`, `complete_section_3` | Real estate owned |
| 4 | `save_section_4a_loan_and_property`, `save_section_4b_other_mortgages`, `save_section_4c_rental_income`, `add_gift_or_grant`, `no_gifts_or_grants`, `complete_section_4d` | Loan terms + property |
| 5 | `save_section_5a_declarations`, `save_section_5b_declarations` | Legal declarations |
| 7 | `save_section_7_military` | Military service |
| 8 | `save_section_8_demographics` | HMDA demographics (voluntary) |
| Co-borrower | `add_coborrower`, `no_coborrower` | Branch back to Section 1a |
| 6 | `capture_verbal_consent` | Verbal "I agree" with timestamp |
| Finalize | `read_final_summary`, `finalize_urla` | Validate + push to BytePro |
| Booking | `offer_lo_kickoff_slots` | Fetch LO availability from Smart Calendar (1-indexed options) |
| Booking | `book_lo_kickoff_call` | Book the slot the caller picked; handles 409 re-offer |
| Booking | `skip_kickoff_booking` | Caller declines or calendar unavailable — clean session close |

---

## Contact / next steps

- **Expand co-borrower coverage**: `add_coborrower` routes the agent back to Section 1a for the new borrower. The system prompt already knows to repeat the intake for them. Verify Aria-style handoff wording if you want to give the primary caller a chance to "put them on the line" vs answer on their behalf with permission.
- **Add Salesforce mirror**: parallel adapter off `finalize_urla`.
- **Package as installable `.skill` file**: say the word and I'll wrap this into the Perennia skill format matching the rest of your library.
