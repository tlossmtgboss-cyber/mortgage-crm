# Intelligent Click-to-Dial & Power Dialer System - PRD

## 1. Product Overview

Build an integrated telephony module inside the Agentic AI Mortgage CRM that allows:

- **Click-to-Dial** from any contact/loan/MUM/referral record, using the loan officer's cell phone as the first leg and the business caller ID for the client leg.
- **Power Dialer** mode that auto-dials through a list of contacts/tasks while the agent remains on a single bridged call, with Pause, Resume, Skip, and Stop controls.
- **Automatic call logging**, dispositioning, and manual notes tied to contacts, loans, and referral partners.
- **CRM integration** into tasks, pipeline, and partner records with full TCPA/DNC and calling-hours compliance.

**Primary telephony provider:** Twilio Programmable Voice (pluggable design so later providers like Plivo/Vonage can be swapped with minimal code changes).

> **Note:** Calls are placed from agent's cell phone and bridged to client. The system does NOT record calls - all call intelligence comes from manual disposition entries and optional voice notes.

---

## 2. Objectives & Success Criteria

### Objectives

- Allow loan officers to rapidly clear their daily call tasks via automated dialing with minimal clicks.
- Reduce friction for starting calls from within the CRM UI.
- Improve follow-up quality and speed using structured dispositions and optional AI-enhanced voice notes.
- Ensure all telephony events are logged for compliance, analytics, and coaching.

### Success Criteria

| Metric | Target |
|--------|--------|
| Click-to-Dial latency | Time from click to agent's phone ringing under 2 seconds (network permitting) |
| Power Dialer inter-call gap | Time between call end and next call start under 4 seconds while session is ACTIVE |
| Logging accuracy | ≥ 99% of calls have complete call_log entries (agent, contact, timestamps, outcome) |
| TCPA / DNC compliance | 100% of calls blocked when number is on CRM DNC list or outside approved calling hours |
| Session reliability | 100% of sessions recoverable after browser/network interruption |

---

## 3. Telephony Architecture

### Provider Abstraction

Implement a telephony service interface (e.g., `TelephonyProvider`) supporting:

- `placeCall()`
- `getCallStatus()`
- `hangupCall()`
- `verifyCallerId()`

**Default implementation:** Twilio Programmable Voice (using server-side REST API and TwiML webhooks).

**Future:** Plivo/Vonage providers implementing the same interface.

### Call Flow

1. **Leg 1 (Agent):** System dials the agent's cell using the selected business caller ID.
2. **Leg 2 (Client):** After agent answers, TwiML dials the client number with business caller ID, then bridges both legs.
3. **Completion:** Twilio sends status webhook when either party hangs up (system cannot distinguish which party).

### Infrastructure - SELECTED ARCHITECTURE

**Option A - Integrated FastAPI Module** (SELECTED)

Implement inside existing FastAPI backend (Python) with a dedicated telephony module:

- Shared authentication and database context
- Single deployment unit
- Simpler operations and debugging
- Direct access to CRM models and services

**Components:**

| Component | Description |
|-----------|-------------|
| Telephony Module | `/api/dialer/*` endpoints within FastAPI |
| Dialer Session Queue | PostgreSQL-backed queue (use existing DB) to track ordered contact tasks per session and next-call pointer |
| Real-time Updates | WebSockets for bidirectional communication (dialer panel status updates, pause/resume/skip commands) |
| Webhooks | Expose publicly accessible HTTPS endpoints for call events (status callbacks, agent-answer TwiML) |

**WebSocket Events:**

- `dialer.status` - session state changes
- `dialer.call.started` - new call initiated
- `dialer.call.completed` - call ended, disposition needed
- `dialer.task.updated` - task status changed

---

## 4. User Experience & Interface

### Click-to-Dial Placement

Phone icon next to every phone field on:

- Lead profile
- Active loan profile
- MUM profile
- Referral partner profile
- Pipeline views
- Tasks views
- Call list views
- Rate lock update pages (optional)

### Click-to-Dial Modal

On click, open modal with:

- Contact name + context (lead/loan/referral)
- Target phone number (editable but default from record)
- Caller ID dropdown (default: agent's business caller ID)
- "Call" and "Cancel" buttons
- Visual indication of DNC status or calling hours violation

### Power Dialer UI

Dedicated "Dialer Panel" (persistent component) with:

**Current Contact Section:**
- Name, phone, context, tags
- Record link (clickable to open in new tab)

**Call Status Display:**
- Status indicator: "Dialing", "In Call", "Wrap-up", "Paused", "Stopped"
- Timer for call duration
- Current task: "X of Y calls completed"

**Control Buttons:**
- Start Session
- Pause
- Resume
- Stop Session
- Skip Current

**Queue Preview:**
- Next 5 contacts in queue (name, phone, context)
- "Remove from Queue" option per contact

**Session Actions:**
- Restart Session (reset all to pending)
- View Session History

**Disposition modal** auto-opens after each call, blocking auto-advance until:
- Disposition submitted, OR
- Timeout reached (configurable, default: 90 seconds)
- On timeout: session auto-pauses, requires manual resume

---

## 5. Features

### 5.1 Click-to-Dial

**Flow:**

1. User clicks phone icon.
2. Modal appears with contact info, number, and caller ID selection.
3. On confirm, backend:
   - Validates DNC / calling-hours rules (reject if violation)
   - Validates caller ID is verified in Twilio
   - Creates a `call_logs` draft record (status: `INITIATED`)
   - Invokes telephony provider to call agent's cell (Leg 1), with action URL pointing to `/api/dialer/twiml/agent-answer` webhook
4. UI updates via WebSocket to show "Dialing…" then "In Call" after event from backend
5. On call completion callback, backend updates `call_logs` and triggers disposition modal on frontend

**Error Handling:**

| Scenario | Behavior |
|----------|----------|
| Agent doesn't answer Leg 1 | Retry once after 5 seconds. If no answer, mark call as `FAILED` (agent_unavailable), notify via WebSocket. |
| Client number invalid/unreachable | Mark as `FAILED` (client_unreachable), open disposition modal with error message pre-filled. |
| Twilio service error | Mark as `FAILED` (service_error), show user-friendly error, log to admin dashboard. |

### 5.2 Call Disposition

**Required Fields:**
- Disposition (dropdown, required)
- Notes (text area, optional)
- Follow-up date/time (datetime picker, conditional on disposition)

**Disposition Options:**

| Disposition | Description |
|-------------|-------------|
| Answered | Conversation completed |
| No Answer | Rang but no pickup |
| Left Voicemail | Left a message |
| Wrong Number | Invalid number |
| Wrong Person | Right number, wrong contact |
| Do Not Call Again | Auto-adds to DNC list |
| Busy Signal | Line busy |
| Follow-up Required | Requires follow-up date |
| Referral Opportunity | Flags for referral team |
| Appointment Set | Requires appointment date |
| Spanish Speaker | Flags for Spanish-speaking agent |
| Callback Scheduled | Requires callback date/time |

### Optional: Voice Note Feature

Below disposition dropdown, add:

- "Record Quick Note" button (microphone icon)
- Click to record 30-60 second voice memo (browser speech-to-text or audio blob)
- System transcribes using OpenAI Whisper API
- AI generates structured summary from agent's recap using existing AI orchestrator
- Summary added to `call_logs.ai_note_summary` field
- Much cheaper than full call recording, provides AI value without compliance issues

**AI Note Prompt:**
```
The loan officer just completed a call and provided this voice note recap:
[TRANSCRIPT]

Generate a structured summary including:
1. Call outcome and next steps
2. Action items (if any)
3. Referral opportunities mentioned (if any)
4. Buyer psychology indicators or concerns
```

### 5.3 Power Dialer

**Dialer Control:**
- Buttons: Start Dialer, Pause, Resume, Stop, Skip
- Display: current contact, call state, timer, "X of Y calls completed", plus link to underlying task/contact record

**Workflow:**

1. User filters/creates a list of call tasks in CRM (e.g., 30 overdue tasks)
2. User selects tasks and clicks "Start Dialer"
3. Backend:
   - Deduplicates contacts (remove duplicates from queue by phone number)
   - Checks for multi-agent collision (soft-lock contacts during session)
   - Creates a `dialer_sessions` record (status: `ACTIVE`)
   - Creates associated `dialer_session_tasks` records in order
4. System initiates Leg 1 to agent's cell; once answered, starts dialing Contact #1 (Leg 2)
5. After each call ends:
   - Backend updates `call_logs` and `dialer_session_tasks` status
   - Frontend opens disposition modal via WebSocket
   - Agent submits disposition or 90-second timeout occurs
6. After disposition saved and session is still `ACTIVE`:
   - Backend waits <4 seconds
   - Initiates next call (Contact #2)
7. Process continues until:
   - All tasks completed → session status = `COMPLETED`
   - Agent pauses → after current call ends, no new call started
   - Agent stops → after current call, remaining tasks remain `PENDING`

**Session Recovery:**

- Sessions persist in database with `current_task_id` pointer
- If browser crashes or agent refreshes:
  - On reconnect, system detects active session for agent
  - Prompt: "You have an active dialer session. Resume or Stop?"
  - Resume continues from `current_task_id`
- If agent's phone drops during call:
  - Twilio webhook marks call as `FAILED`
  - Session auto-pauses
  - Require manual resume

**Pause:**
- When Pause pressed, backend sets `session.status = PAUSED`
- Current call allowed to complete; no further calls initiated
- WebSocket updates UI to show PAUSED state
- Disposition modal still required for completed call

**Resume:**
- When Resume pressed, backend sets `session.status = ACTIVE`
- If not currently in a call and tasks remain, initiate next pending call immediately

**Stop:**
- When Stop pressed, backend sets `session.status = STOPPED`
- Let active call complete but do not dial additional calls
- Remaining tasks left in `PENDING` status
- Can view session summary: completed count, outcomes distribution

**Skip:**
- When Skip pressed during ringing or active call:
  - Backend sets current `dialer_session_task.status = SKIPPED`
  - Hangup active call if still ringing/connected via Twilio API
  - Create `call_logs` entry with outcome = `SKIPPED`
  - If session is `ACTIVE` and tasks remain, move immediately to next contact (<2 second gap)

### 5.4 Contact Deduplication & Collision Prevention

**Deduplication:**
- When starting dialer session, system checks for duplicate phone numbers in task list
- Keeps first occurrence, removes duplicates, notifies user: "Removed X duplicate contacts from queue"

**Multi-Agent Collision:**
- When call initiated (Click-to-Dial or Power Dialer), system creates soft lock:
  - `active_calls` table: `contact_id`, `agent_id`, `call_sid`, `locked_at`
  - Lock expires after 5 minutes (configurable)
- Before any call, check if contact has active lock:
  - If locked by different agent: Show warning "Contact currently being called by [Agent Name]. Continue anyway?"
  - If locked by same agent: Allow (prevents false positives from failed attempts)
- Lock released on call completion webhook

### 5.5 Task Integration

When call is dispositioned:

| Disposition | Task Action | Additional Behavior |
|-------------|-------------|---------------------|
| Answered | Complete current task | None |
| No Answer | Complete task as "no answer" | None |
| Left Voicemail | Complete task | None |
| Wrong Number | Complete task, flag contact | Update contact record with "wrong number" flag |
| Wrong Person | Complete task | None |
| Do Not Call Again | Complete task | Add contact to DNC list |
| Busy Signal | Complete task as "no answer" | None |
| Follow-up Required | Complete task | Create new task with follow-up date |
| Referral Opportunity | Complete task | Create referral task for referral coordinator |
| Appointment Set | Complete task | Create calendar event + follow-up task |
| Spanish Speaker | Complete task | Add language preference flag to contact |
| Callback Scheduled | Complete task | Create callback task with specified date/time |

---

## 6. System Behavior

### 6.1 Dialer Session Backend Logic

**Session States:**
- `ACTIVE` - Currently dialing through queue
- `PAUSED` - Temporarily stopped, can resume
- `STOPPED` - Permanently ended, cannot resume
- `COMPLETED` - All tasks processed

**Task States:**
- `PENDING` - Not yet dialed
- `IN_PROGRESS` - Currently being called
- `COMPLETED` - Successfully dispositioned
- `NO_ANSWER` - No answer received
- `FAILED` - Technical failure (bad number, service error, agent unavailable)
- `SKIPPED` - Agent manually skipped

**Core Function (pseudo-code):**

```python
def initiate_next_call(session_id):
    session = load_session(session_id)

    # Check session state
    if session.status != ACTIVE:
        return

    # Get next pending task
    next_task = get_next_pending_task(session_id)
    if not next_task:
        session.status = COMPLETED
        session.save()
        send_websocket_event(session.agent_id, 'dialer.completed')
        return

    # Check contact collision
    if is_contact_locked(next_task.contact_id, session.agent_id):
        # Notify agent, skip to next
        send_websocket_event(session.agent_id, 'dialer.collision_warning', next_task)
        next_task.status = SKIPPED
        next_task.save()
        initiate_next_call(session_id)  # Recursive to get next
        return

    # Create soft lock
    lock_contact(next_task.contact_id, session.agent_id)

    # Update session and task
    session.current_task_id = next_task.id
    session.save()
    next_task.status = IN_PROGRESS
    next_task.save()

    # Create call log draft
    call_log = create_call_log(
        agent_id=session.agent_id,
        contact_id=next_task.contact_id,
        loan_id=next_task.loan_id,
        referring_partner_id=next_task.referring_partner_id,
        status=INITIATED
    )

    # Invoke Twilio
    try:
        call = twilio_client.calls.create(
            to=session.agent.cell_phone,
            from_=session.agent.business_caller_id,
            url=f"{BASE_URL}/api/dialer/twiml/agent-answer?task_id={next_task.id}&session_id={session_id}",
            status_callback=f"{BASE_URL}/api/dialer/webhook/status",
            status_callback_event=['answered', 'completed']
        )

        next_task.call_sid = call.sid
        next_task.save()
        call_log.call_sid = call.sid
        call_log.save()

        send_websocket_event(session.agent_id, 'dialer.call.started', next_task)

    except TwilioException as e:
        handle_twilio_error(session, next_task, call_log, e)
```

### 6.2 Agent Answer / TwiML

When agent answers Leg 1, `/api/dialer/twiml/agent-answer` webhook returns TwiML:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial callerId="{business_caller_id}">
        {contact_phone}
    </Dial>
</Response>
```

**Error Handling:**
- If agent doesn't answer (no-answer status from Twilio), webhook still fires
- Mark call as `FAILED` (agent_unavailable)
- If session is `ACTIVE`, retry once after 5 seconds
- If second attempt fails, auto-pause session and notify agent

### 6.3 Call Completion Handling

**Call Status Webhook:** `/api/dialer/webhook/status`

On completion (`completed`, `busy`, `no-answer`, `failed`):

1. Map Twilio status to internal outcome:
   - `completed` → depends on duration: >10 seconds = likely answered, <10 = likely no answer
   - `busy` → `NO_ANSWER`
   - `no-answer` → `NO_ANSWER`
   - `failed` → `FAILED`

2. Update `call_logs` record:
   - `end_time = now`
   - `duration_seconds = Twilio duration`
   - `outcome = mapped status`
   - `status = COMPLETED`

3. Release contact soft lock

4. If it is a dialer session task:
   - Update `dialer_session_tasks.status` accordingly
   - Send WebSocket event to open disposition modal
   - Wait for disposition submission or 90-second timeout
   - If timeout: auto-pause session
   - If disposition submitted and session is `ACTIVE`:
     - Wait <4 seconds (configurable)
     - Call `initiate_next_call(session_id)`

5. If session status is `PAUSED`/`STOPPED`: do nothing more

**Call Duration Tracking:**
- Twilio provides accurate call duration via status callback
- Duration includes time from agent answer to call end (either party hangs up)
- System cannot distinguish which party ended call
- For analytics: average duration, talk time per day tracked in dashboard

---

## 7. Data Model

Use existing UUID standard and timestamps (`created_at`, `updated_at`).

### Agent Settings

Extend existing agents table or create `agent_telephony_settings`:

```sql
agent_id (UUID, FK to agents)
cell_phone (VARCHAR, required)
business_caller_id (VARCHAR, required, must be Twilio-verified)
dialer_enabled (BOOLEAN, default true)
max_calls_per_day (INTEGER, default 200)
max_concurrent_sessions (INTEGER, default 1)
preferred_pause_timeout (INTEGER, seconds, default 90)
created_at (TIMESTAMP)
updated_at (TIMESTAMP)
```

### Dialer Sessions

```sql
session_id (UUID, PK)
agent_id (UUID, FK to agents)
status (ENUM: ACTIVE, PAUSED, STOPPED, COMPLETED)
current_task_id (UUID, FK to dialer_session_tasks, nullable)
total_tasks (INTEGER)
completed_tasks (INTEGER)
failed_tasks (INTEGER)
skipped_tasks (INTEGER)
created_at (TIMESTAMP)
updated_at (TIMESTAMP)
completed_at (TIMESTAMP, nullable)
```

### Dialer Session Tasks

```sql
id (UUID, PK)
session_id (UUID, FK to dialer_sessions)
contact_id (UUID, FK to contacts)
phone (VARCHAR)
loan_id (UUID, FK to loans, nullable)
referring_partner_id (UUID, FK to referring_partners, nullable)
status (ENUM: PENDING, IN_PROGRESS, COMPLETED, NO_ANSWER, FAILED, SKIPPED)
call_sid (VARCHAR, Twilio call ID, nullable)
disposition (VARCHAR, nullable)
notes (TEXT, nullable)
ai_note_summary (TEXT, nullable)
follow_up_date (TIMESTAMP, nullable)
task_order (INTEGER) -- for queue ordering
created_at (TIMESTAMP)
updated_at (TIMESTAMP)
completed_at (TIMESTAMP, nullable)
```

### Call Logs

```sql
id (UUID, PK)
agent_id (UUID, FK to agents)
contact_id (UUID, FK to contacts)
loan_id (UUID, FK to loans, nullable)
referring_partner_id (UUID, FK to referring_partners, nullable)
session_id (UUID, FK to dialer_sessions, nullable)
start_time (TIMESTAMP)
end_time (TIMESTAMP, nullable)
duration_seconds (INTEGER, nullable)
call_sid (VARCHAR, Twilio call ID)
outcome (ENUM: COMPLETED, NO_ANSWER, BUSY, FAILED, SKIPPED)
failure_reason (VARCHAR, nullable) -- agent_unavailable, client_unreachable, service_error
disposition (VARCHAR, nullable)
notes (TEXT, nullable)
ai_note_summary (TEXT, nullable) -- from optional voice note feature
caller_id_used (VARCHAR)
created_at (TIMESTAMP)
updated_at (TIMESTAMP)
```

### Active Calls (Soft Lock)

```sql
id (UUID, PK)
contact_id (UUID, FK to contacts)
agent_id (UUID, FK to agents)
call_sid (VARCHAR)
locked_at (TIMESTAMP)
expires_at (TIMESTAMP) -- locked_at + 5 minutes
```

Index on `contact_id` and `expires_at` for fast collision detection.

### Verified Caller IDs

```sql
id (UUID, PK)
phone_number (VARCHAR, unique)
friendly_name (VARCHAR)
verification_status (ENUM: PENDING, VERIFIED, FAILED)
twilio_sid (VARCHAR)
organization_id (UUID, FK to organizations)
verified_at (TIMESTAMP, nullable)
created_at (TIMESTAMP)
updated_at (TIMESTAMP)
```

---

## 8. Caller ID Verification & Management

### Twilio Requirements

Before using any business phone number as caller ID, it must be verified with Twilio. Verification methods:
- Automated call verification (Twilio calls the number, user enters code)
- Text message verification (for mobile numbers)
- Phone bill upload (for landlines)

### Admin Interface Required

**Caller ID Management Page:** `/admin/telephony/caller-ids`

Features:
- List all registered caller IDs (phone, name, status, verified date)
- "Add New Caller ID" button
  - Enter phone number and friendly name
  - Trigger Twilio verification process
  - Show verification code instructions
- Status indicators: Pending, Verified, Failed
- Set default caller ID per agent or organization
- STIR/SHAKEN attestation status display (if available from Twilio)

**Agent Settings:**
- Allow agents to select from verified caller IDs in their organization
- Default caller ID auto-selected in Click-to-Dial modal

### STIR/SHAKEN Compliance

Twilio automatically handles STIR/SHAKEN attestation for verified caller IDs. Display attestation level in admin interface:
- A (Full attestation)
- B (Partial attestation)
- C (Gateway attestation)

Higher attestation levels reduce spam flag risk.

---

## 9. Compliance Requirements

### DNC / Opt-Out

Before any call, backend checks:
1. CRM-level DNC flag on contact record
2. Phone-level opt-out in `contacts_phones` table
3. Federal DNC list (if integrated)

**Rejection:** If any DNC flag is true, reject call immediately with error message to agent.

### Calling Hours

**Default hours:** 8am–9pm in contact's local timezone

**Timezone Detection:**
- First priority: Contact record has timezone field set
- Second priority: Infer from area code (maintain area code → timezone mapping table)
- Third priority: Use business default timezone

**Enforcement:**
- Before initiating call, check current time in contact's timezone
- If outside allowed hours, reject call with message: "Cannot call [Contact] outside allowed hours (8am-9pm their local time)"
- Display contact's current local time in UI

**Admin Settings:**
- Configurable calling hours per organization
- Override for specific contact (if they've consented to different hours)

### Rate Limiting

**Per-Agent Limits:**
- Max concurrent calls: 1 (agent can't be on multiple calls)
- Max calls per minute: 10 (system throttle)
- Max calls per day: 200 (configurable per agent)

**Organization Limits:**
- Based on Twilio account tier concurrent call limit
- Track organization-wide active calls
- Reject if at limit, show error to agent

### Data Retention

- Store call metadata (`call_logs`) for minimum 7 years (configurable per compliance policy)
- Store dialer sessions for minimum 3 years
- Disposition notes and voice note summaries for minimum 7 years
- Soft-delete only (never hard delete telephony data)

### Role-Based Permissions

Admin interface to configure:
- `telephony.click_to_dial` - Can use click-to-dial
- `telephony.power_dialer` - Can use power dialer
- `telephony.admin` - Can manage caller IDs and settings
- `telephony.view_all_calls` - Can view all agents' call logs

Enforce at API level and hide UI elements if insufficient permissions.

---

## 10. API Endpoints

### Agent Telephony Settings

```
GET    /api/agent/telephony/settings
POST   /api/agent/telephony/settings
PUT    /api/agent/telephony/settings
```

**Response body:**
```json
{
  "cell_phone": "+15551234567",
  "business_caller_id": "+18005551234",
  "dialer_enabled": true,
  "max_calls_per_day": 200,
  "verified_caller_ids": [
    {
      "phone": "+18005551234",
      "name": "Main Business Line",
      "is_default": true
    }
  ]
}
```

### Click-to-Dial

```
POST   /api/dialer/call
```

**Request body:**
```json
{
  "contact_id": "uuid",
  "phone": "+15551234567",
  "loan_id": "uuid",
  "referring_partner_id": "uuid",
  "caller_id": "+18005551234"
}
```

**Response:**
```json
{
  "call_id": "uuid",
  "call_sid": "CAxxxx",
  "status": "initiated",
  "contact": {
    "name": "John Doe",
    "phone": "+15551234567"
  }
}
```

**Error responses:**
- 400: DNC violation, calling hours violation, invalid caller ID
- 429: Rate limit exceeded
- 503: Twilio service unavailable

### Dialer Sessions

```
POST   /api/dialer/session/start
POST   /api/dialer/session/{id}/pause
POST   /api/dialer/session/{id}/resume
POST   /api/dialer/session/{id}/stop
POST   /api/dialer/session/{id}/skip-current
POST   /api/dialer/session/{id}/restart
DELETE /api/dialer/session/{id}/tasks/{task_id}
GET    /api/dialer/session/{id}
GET    /api/dialer/session/{id}/tasks
GET    /api/agent/dialer/active-session
```

**Start session request:**
```json
{
  "task_ids": ["uuid1", "uuid2", "uuid3"],
  "caller_id": "+18005551234"
}
```

**Start session response:**
```json
{
  "session_id": "uuid",
  "status": "ACTIVE",
  "total_tasks": 30,
  "deduplicated_count": 2,
  "first_call_initiating": true
}
```

**Get session response:**
```json
{
  "session_id": "uuid",
  "status": "ACTIVE",
  "total_tasks": 30,
  "completed_tasks": 15,
  "failed_tasks": 2,
  "skipped_tasks": 1,
  "current_task": {
    "contact_name": "Jane Smith",
    "phone": "+15559876543",
    "context": "Loan Application #12345"
  },
  "next_tasks": []
}
```

### Dispositions

```
POST   /api/dialer/task/{task_id}/disposition
POST   /api/dialer/call-log/{id}/disposition
```

**Request body:**
```json
{
  "disposition": "Answered",
  "notes": "Client interested in refinance options",
  "follow_up_date": "2024-03-15T10:00:00Z",
  "voice_note_audio": "base64_encoded_audio_blob",
  "flags": {
    "follow_up_required": true,
    "referral_opportunity": false,
    "appointment_set": false
  }
}
```

**Response:**
```json
{
  "success": true,
  "ai_note_summary": "Client expressed interest in refinance. Action: Follow up with rate options by Friday.",
  "task_created": {
    "id": "uuid",
    "type": "follow_up",
    "due_date": "2024-03-15T10:00:00Z"
  }
}
```

### Telephony Webhooks (Public)

```
POST   /api/dialer/webhook/status
POST   /api/dialer/twiml/agent-answer
```

These must be publicly accessible HTTPS endpoints for Twilio callbacks.

### Admin - Caller ID Management

```
GET    /api/admin/telephony/caller-ids
POST   /api/admin/telephony/caller-ids/verify
GET    /api/admin/telephony/caller-ids/{id}/status
DELETE /api/admin/telephony/caller-ids/{id}
```

### Analytics

```
GET    /api/dialer/analytics/daily-summary?agent_id={uuid}&date={YYYY-MM-DD}
GET    /api/dialer/analytics/disposition-breakdown?start_date={}&end_date={}
GET    /api/dialer/analytics/connect-rate-by-hour
GET    /api/dialer/analytics/agent-performance?agent_id={uuid}&date_range={}
```

**Daily summary response:**
```json
{
  "date": "2024-03-01",
  "total_calls": 87,
  "total_talk_time_minutes": 245,
  "connect_rate": 0.68,
  "average_call_duration_seconds": 168,
  "dispositions": {
    "Answered": 59,
    "No Answer": 18,
    "Left Voicemail": 10
  }
}
```

---

## 11. Engineering Deliverables

### Backend

**Telephony Module (`/app/telephony/`):**
- `provider.py` - TelephonyProvider interface and TwilioProvider implementation
- `dialer.py` - Dialer session engine (state machine + next-call logic)
- `call_logs.py` - Call log service
- `compliance.py` - DNC checks, calling hours validation
- `caller_id.py` - Caller ID verification and management
- `websocket.py` - WebSocket connection manager and event broadcaster

**API Endpoints (`/app/api/dialer/`):**
- `settings.py` - Agent settings endpoints
- `click_to_dial.py` - Click-to-dial endpoints
- `sessions.py` - Dialer session CRUD and control endpoints
- `dispositions.py` - Disposition submission endpoints
- `webhooks.py` - Twilio webhook handlers
- `admin.py` - Admin caller ID management endpoints
- `analytics.py` - Analytics and reporting endpoints

**Database Migrations:**
- Create tables: `dialer_sessions`, `dialer_session_tasks`, `call_logs`, `active_calls`, `verified_caller_ids`
- Add indexes for performance (`contact_id`, `agent_id`, `session_id`, `call_sid`)

**Background Workers (Celery or similar):**
- Voice note transcription worker (if feature enabled)
- AI summary generation worker (if feature enabled)
- Stale session cleanup (auto-stop sessions inactive >2 hours)
- Soft lock expiration cleanup

**Twilio Integration:**
- Account configuration
- Webhook URL registration
- Error handling and retry logic
- Rate limit monitoring

### Frontend

**Components (`/src/components/dialer/`):**
- `ClickToDialButton.tsx` - Phone icon button
- `ClickToDialModal.tsx` - Click-to-dial confirmation modal
- `DialerPanel.tsx` - Power dialer control panel (persistent)
- `DialerSessionControls.tsx` - Start/pause/resume/stop/skip buttons
- `DialerQueuePreview.tsx` - Next 5 contacts display
- `DispositionModal.tsx` - Call disposition form
- `VoiceNoteRecorder.tsx` - Optional voice note recording UI
- `CallStatusIndicator.tsx` - Real-time call status display

**WebSocket Integration:**
- Connect to `/ws/dialer/{agent_id}` on component mount
- Listen for events: `dialer.status`, `dialer.call.started`, `dialer.call.completed`, `dialer.task.updated`
- Reconnect logic with exponential backoff
- Session recovery on reconnect

**Pages (`/src/pages/`):**
- `/dialer/dashboard` - Dialer analytics dashboard
- `/admin/telephony/caller-ids` - Caller ID management (admin only)

**Hooks:**
- `useDialerSession()` - Manage active dialer session state
- `useCallStatus()` - Subscribe to call status updates
- `useVoiceNote()` - Handle voice note recording and upload

### Testing & QA

**Unit Tests:**
- TelephonyProvider interface implementation
- Dialer session state machine logic
- DNC and calling hours validation
- Deduplication and collision detection

**Integration Tests:**
- Click-to-Dial full flow (mock Twilio)
- Power Dialer session lifecycle
- WebSocket event delivery
- Webhook handling (status callbacks)

**QA Scenarios:**
- No answer: Client doesn't pick up
- Busy signal: Client line busy
- Failed call: Invalid number, network error
- Agent doesn't answer Leg 1: Retry logic, eventual failure
- Pause/resume cycles: Mid-session, between calls
- Stop mid-session: Remaining tasks stay pending
- Skip during ringing: Immediate next call
- Skip during active call: Hangup + next call
- Session recovery: Browser refresh, network interruption
- Multi-agent collision: Warning display, lock behavior
- Disposition timeout: Auto-pause after 90 seconds
- Voice note feature: Recording, transcription, AI summary

**Manual Testing Requirements:**
- Use Twilio test credentials for dev/staging environments
- Twilio test phone numbers:
  - `+15005550006` (success scenario)
  - `+15005550001` (invalid number)
  - `+15005550002` (cannot route)
- Real phone testing required before production launch
- Test with actual cell phones for Leg 1 (agent) in staging

**Performance Tests:**
- 10 agents with concurrent active dialer sessions
- 100+ contact queue per session
- WebSocket connection stability under load
- Database query performance with 100k+ call logs

### Documentation

**Developer Docs:**
- Telephony architecture diagram
- WebSocket event schema
- TwiML generation logic
- Error handling and retry policies
- Testing guide (Twilio test credentials, mock setup)

**Admin Docs:**
- Caller ID verification process
- Compliance configuration (DNC, calling hours)
- Role permissions setup
- Monitoring and troubleshooting

**User Docs:**
- Click-to-Dial quick start
- Power Dialer workflow guide
- Disposition best practices
- Voice note tips (if enabled)

---

## 12. Cost Management

### Twilio Costs

**Per-Minute Charges:**
- Outbound calls to US: ~$0.013/minute per leg
- Each call has 2 legs (agent + client) = ~$0.026/minute total
- Example: 100 calls/day, avg 3 min each = 300 min = $7.80/day per agent

**Storage (if enabled):**
- Not applicable since no call recordings

**Admin Dashboard Requirements:**
- Display current month telephony spend per agent
- Alert if agent approaching daily call limit
- Organization-wide spend tracking

### Rate Limits

**Twilio Account Limits:**
- Concurrent call limits vary by account tier
- Starter: 1-10 concurrent calls
- Professional: 10-100 concurrent calls
- Enterprise: 100+ concurrent calls

**System Limits (configurable):**
- Max 10 concurrent calls per agent (system throttle)
- Max 5 dialer sessions per organization simultaneously
- Max 200 calls per agent per day (default, adjustable)

### Cost Optimization

- Track average call duration per agent for cost forecasting
- Implement warnings at 80% of daily call limit
- Admin can set custom limits per agent or role
- Monthly cost reports in admin dashboard

---

## 13. Monitoring & Observability

### Key Metrics

**Real-time:**
- Active dialer sessions (count)
- Active calls (count)
- WebSocket connections (count)
- Twilio API error rate

**Daily:**
- Total calls placed
- Total talk time (minutes)
- Average call duration
- Connect rate (answered / total)
- Disposition breakdown
- Cost per agent

**Alerts:**
- Twilio API errors exceed 5% of requests
- WebSocket disconnect rate exceeds 10%
- Any dialer session stuck in `IN_PROGRESS` for >10 minutes
- Agent exceeds daily call limit
- Organization approaching concurrent call limit

### Logging

**Required Log Events:**
- Call initiated (agent_id, contact_id, call_sid)
- Call completed (call_sid, duration, outcome)
- Disposition submitted (task_id, disposition, agent_id)
- Session state changes (session_id, old_status, new_status)
- Twilio errors (error_code, error_message, call_sid)
- DNC violations blocked (agent_id, contact_id, reason)
- Calling hours violations blocked (agent_id, contact_id, timezone)

**Log Level Guidelines:**
- INFO: Normal operations (call started, call ended, session created)
- WARNING: Recoverable errors (agent didn't answer retry, soft lock collision)
- ERROR: Service errors (Twilio API failure, database error)
- CRITICAL: System-wide issues (WebSocket server down, DB connection pool exhausted)

---

## 14. Security Considerations

### API Authentication

- All dialer endpoints require authenticated agent JWT
- Admin endpoints require `telephony.admin` permission
- Webhook endpoints validate Twilio signature (`X-Twilio-Signature` header)

### Data Protection

- Agent cell phone numbers encrypted at rest
- Call logs contain PII - enforce row-level security
- WebSocket connections require valid session token
- Soft locks contain agent/contact associations - limit to authorized agents only

### Twilio Security

- Store Twilio credentials in secure environment variables or secrets manager
- Rotate Twilio Auth Token quarterly
- Use Twilio IP whitelisting for webhooks if available
- Enable Twilio geographic permissions (restrict to US/Canada if applicable)

### Rate Limiting & Abuse Prevention

- Per-agent API rate limits (100 requests/minute)
- Prevent agents from starting multiple concurrent sessions
- Block excessive skip actions (>50% of session skipped = warning)
- Admin audit log for all telephony config changes

---

## Appendix A: Example TwiML Responses

### Agent Answer Webhook Response

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial callerId="+18005551234" timeout="30" action="/api/dialer/webhook/dial-complete">
        +15551234567
    </Dial>
</Response>
```

### Agent Didn't Answer (No Response Needed)

Twilio automatically handles no-answer scenario - just log the event.

---

## Appendix B: WebSocket Event Schema

### Event: dialer.status

```json
{
  "event": "dialer.status",
  "session_id": "uuid",
  "status": "ACTIVE",
  "current_task_id": "uuid",
  "completed_tasks": 15,
  "total_tasks": 30
}
```

### Event: dialer.call.started

```json
{
  "event": "dialer.call.started",
  "session_id": "uuid",
  "task_id": "uuid",
  "call_sid": "CAxxxx",
  "contact": {
    "name": "John Doe",
    "phone": "+15551234567",
    "context": "Loan #12345"
  }
}
```

### Event: dialer.call.completed

```json
{
  "event": "dialer.call.completed",
  "session_id": "uuid",
  "task_id": "uuid",
  "call_sid": "CAxxxx",
  "duration_seconds": 145,
  "outcome": "COMPLETED",
  "show_disposition_modal": true
}
```

### Event: dialer.collision_warning

```json
{
  "event": "dialer.collision_warning",
  "contact_id": "uuid",
  "locked_by_agent": {
    "name": "Sarah Johnson",
    "id": "uuid"
  },
  "message": "This contact is currently being called by Sarah Johnson"
}
```

---

**END OF PRD**

*This document is ready to hand to your development team. All architecture decisions are finalized, error handling is specified, and compliance requirements are clear. The optional voice note feature provides AI value without the complexity of full call recording.*
