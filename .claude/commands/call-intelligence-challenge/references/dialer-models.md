# Dialer & Telephony Database Models — Schema Reference

## Overview

The power dialer and telephony systems use 4 core models for session management, task tracking, caller ID verification, and per-agent configuration. These live in `backend/database/models/dialer.py`.

---

## AgentTelephonySettings

Per-agent telephony configuration. Each loan officer / agent can have unique settings.

```sql
CREATE TABLE agent_telephony_settings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    organization_id UUID REFERENCES organizations(id),

    -- Phone numbers
    cell_phone      VARCHAR(20),          -- Agent's personal cell
    office_phone    VARCHAR(20),          -- Office line
    caller_id       VARCHAR(20),          -- Default outbound caller ID

    -- Dialer settings
    max_calls_per_day    INTEGER DEFAULT 100,
    auto_advance         BOOLEAN DEFAULT true,    -- Auto-dial next in queue
    pause_between_calls  INTEGER DEFAULT 5,       -- Seconds between auto-advance
    voicemail_drop_enabled BOOLEAN DEFAULT true,

    -- Provider preferences
    preferred_provider   VARCHAR(20) DEFAULT 'twilio',  -- twilio | telnyx
    click_to_call_mode   VARCHAR(20) DEFAULT 'browser',  -- browser | phone

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(user_id, organization_id)
);
```

### Validation Rules
- `caller_id` must reference a verified number (see VerifiedCallerId)
- `max_calls_per_day` enforced by dialer engine (hard stop)
- `pause_between_calls` minimum 3 seconds (compliance)
- `preferred_provider` must be a functioning provider

---

## VerifiedCallerId

Organization-level caller ID verification tracking. Numbers must be verified with Twilio before use as outbound caller ID.

```sql
CREATE TABLE verified_caller_ids (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    phone_number    VARCHAR(20) NOT NULL,       -- E.164 format
    friendly_name   VARCHAR(100),               -- Display name
    twilio_sid      VARCHAR(50),                -- Twilio verification SID
    verification_status VARCHAR(20) DEFAULT 'pending',  -- pending | verified | failed
    verified_at     TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(organization_id, phone_number)
);
```

### Validation Rules
- Only `verified` numbers can be used as caller ID (PD-010)
- Verification initiated via Twilio Outgoing Caller IDs API
- `twilio_sid` populated after verification call completed
- Expired verifications should be re-verified periodically

---

## DialerSession

Tracks an active power dialer session. A session is a continuous calling block where an agent works through a queue of contacts.

```sql
CREATE TABLE dialer_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    organization_id UUID REFERENCES organizations(id),

    -- Session state
    status          VARCHAR(20) DEFAULT 'active',  -- active | paused | completed | stopped
    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at        TIMESTAMP,

    -- Caller ID used for this session
    caller_id_used  VARCHAR(20),

    -- Task counters
    total_tasks     INTEGER DEFAULT 0,
    completed_tasks INTEGER DEFAULT 0,
    skipped_tasks   INTEGER DEFAULT 0,

    -- Source context
    source_type     VARCHAR(50),    -- workflow | manual | campaign | recruiting
    source_id       UUID,           -- ID of workflow/campaign that generated tasks
    campaign_name   VARCHAR(200),

    -- Settings snapshot (captured at session start)
    auto_advance    BOOLEAN DEFAULT true,
    pause_seconds   INTEGER DEFAULT 5,

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Session Lifecycle
```
created → active → (paused ↔ active) → completed | stopped
```

- `active`: Agent is actively making calls
- `paused`: Agent temporarily stepped away
- `completed`: All tasks in queue processed
- `stopped`: Agent manually ended session early

### Validation Rules
- Only ONE active/paused session per user at a time
- `caller_id_used` must be a verified number
- `total_tasks` = `completed_tasks` + `skipped_tasks` + remaining
- Session automatically stops if `max_calls_per_day` reached

---

## DialerSessionTask

Individual contact/task within a dialer session queue. Each task represents one call to make.

```sql
CREATE TABLE dialer_session_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES dialer_sessions(id),

    -- Contact info
    phone_number    VARCHAR(20) NOT NULL,       -- E.164 format
    contact_name    VARCHAR(200),
    contact_type    VARCHAR(20),                -- lead | client | referral_partner

    -- CRM context
    lead_id         UUID REFERENCES leads(id),
    loan_id         UUID REFERENCES loans(id),
    referral_partner_id UUID,

    -- Task state
    status          VARCHAR(20) DEFAULT 'pending',  -- pending | calling | completed | skipped | failed
    position        INTEGER,                         -- Queue position

    -- Call outcome
    disposition     VARCHAR(50),        -- connected | voicemail | no_answer | busy | wrong_number | dnc
    disposition_notes TEXT,
    call_duration   INTEGER,            -- Seconds
    call_sid        VARCHAR(50),        -- Twilio/Telnyx call SID

    -- Follow-up
    follow_up_date  DATE,
    follow_up_notes TEXT,
    follow_up_type  VARCHAR(30),        -- call_back | send_email | send_sms | schedule_meeting

    -- Timestamps
    called_at       TIMESTAMP,
    completed_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Disposition Types
| Disposition | Description | Typical Follow-up |
|-------------|-------------|-------------------|
| `connected` | Spoke with contact | Based on conversation |
| `voicemail` | Left voicemail | Call back in 24-48h |
| `no_answer` | No answer, no VM | Retry in 2-4h |
| `busy` | Line busy | Retry in 1h |
| `wrong_number` | Number incorrect | Update CRM, skip |
| `dnc` | Requested Do Not Call | Add to DNC list immediately |

### Validation Rules
- `phone_number` must pass DNC check BEFORE dialing (PD-005)
- `disposition` required before moving to next task
- `dnc` disposition must trigger immediate DNC list addition
- At least one CRM context field (lead_id, loan_id, or referral_partner_id) should be populated

---

## Communication Models

From `backend/database/models/communication.py`:

### Activity (Call Touchpoint Log)
```sql
CREATE TABLE activities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID REFERENCES leads(id),
    loan_id         UUID REFERENCES loans(id),
    user_id         UUID REFERENCES users(id),
    organization_id UUID REFERENCES organizations(id),

    activity_type   VARCHAR(50),    -- call, email, sms, meeting, note
    direction       VARCHAR(10),    -- inbound | outbound
    subject         VARCHAR(500),
    description     TEXT,
    sentiment       VARCHAR(20),    -- positive | neutral | negative | mixed
    duration        INTEGER,        -- Seconds (for calls)

    -- Call-specific
    phone_number    VARCHAR(20),
    call_sid        VARCHAR(50),
    recording_url   TEXT,

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### SMSMessage
```sql
CREATE TABLE sms_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES sms_conversations(id),
    twilio_sid      VARCHAR(50),
    direction       VARCHAR(10),    -- inbound | outbound
    from_number     VARCHAR(20),
    to_number       VARCHAR(20),
    body            TEXT,
    status          VARCHAR(20),    -- queued | sent | delivered | failed | received
    template_used   VARCHAR(50),
    disposition     VARCHAR(30),    -- See SMS disposition types
    metadata        JSONB,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### SMSConversation
```sql
CREATE TABLE sms_conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number    VARCHAR(20) NOT NULL,
    lead_id         UUID REFERENCES leads(id),
    user_id         UUID REFERENCES users(id),
    organization_id UUID REFERENCES organizations(id),
    ai_enabled      BOOLEAN DEFAULT false,
    context         JSONB,          -- Conversation context for AI
    last_message_at TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Call Monitoring Models

From `backend/models/call_monitoring_models.py`:

### Key Enums
```python
class CaptureMode(str, Enum):
    mobile_app = "mobile_app"
    crm_web_call = "crm_web_call"
    ambient_mic = "ambient_mic"
    video_call = "video_call"
    call_intelligence = "call_intelligence"

class CallSessionStatus(str, Enum):
    active = "active"
    processing = "processing"
    review_pending = "review_pending"
    completed = "completed"
    failed = "failed"

class ArtifactType(str, Enum):
    summary = "summary"
    action_item = "action_item"
    task = "task"
    document_request = "document_request"
    risk_flag = "risk_flag"
    intake_field = "intake_field"
    uw_note = "uw_note"
    follow_up_draft = "follow_up_draft"
    pricing_scenario = "pricing_scenario"
    calculator_result = "calculator_result"
    scribe_recap = "scribe_recap"
    five_c_credit = "five_c_credit"
    five_c_collateral = "five_c_collateral"
    five_c_capacity = "five_c_capacity"
    five_c_characteristics = "five_c_characteristics"
    five_c_cash = "five_c_cash"
    uw_review_item = "uw_review_item"
    stacked_note = "stacked_note"
    borrower_story_note = "borrower_story_note"
    marketing_milestone = "marketing_milestone"
    content_idea = "content_idea"
    borrower_quote = "borrower_quote"
    story_theme = "story_theme"
    scheduled_appointment = "scheduled_appointment"
    follow_up_call = "follow_up_call"
    calendar_action = "calendar_action"
    meeting_summary = "meeting_summary"

class ApprovalStatus(str, Enum):
    pending = "pending"
    auto_approved = "auto_approved"
    approved = "approved"
    rejected = "rejected"

class RiskCategory(str, Enum):
    credit = "credit"
    income = "income"
    employment = "employment"
    property = "property"
    compliance = "compliance"
    assets = "assets"
    dti = "dti"

class RiskSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"
```

---

## Migration Files

| File | Purpose |
|------|---------|
| `alembic/versions/001_telephony_tables.py` | Core telephony tables |
| `alembic/versions/007_call_intelligence_review_queue.py` | Review queue schema |
| `alembic/versions/008_call_intelligence_orchestration.py` | Orchestration schema |
| `migrations/add_advanced_telephony_tables.py` | Advanced telephony |
| `migrations/add_call_screening_tables.py` | Call screening |
| `migrations/add_call_routing_tables.py` | Call routing/queue |
| `migrations/add_voicemail_system.sql` | Voicemail drops |
| `migrations/add_voice_workflow_tables.sql` | Voice workflows |
| `migrations/001_voice_os_schema.sql` | Voice OS platform |

### Migration Validation
- All migrations must be applied in production
- `checkfirst=True` only checks table existence, NOT missing columns
- New columns need explicit `ALTER TABLE ADD COLUMN IF NOT EXISTS`
