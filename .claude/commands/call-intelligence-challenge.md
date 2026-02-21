---
name: call-intelligence-challenge
description: >
  Comprehensive Call Intelligence Platform Challenge & Validation for Perennia AI.
  Use this skill whenever building, debugging, auditing, or extending any component of
  the call intelligence stack: telephony integrations (Twilio, Telnyx, Vapi, Retell),
  power dialer, AI receptionist, voicemail drops (Vapi/Slybroadcast), call transcription
  and analysis, live call whisper, call screening/DNC, SMS intelligence, voice workflows,
  call recording, click-to-call, call routing/queuing, or the multi-agent call orchestration
  system. Triggers on: 'call intelligence', 'telephony', 'power dialer', 'voicemail drop',
  'AI receptionist', 'call transcription', 'call whisper', 'call screening', 'DNC',
  'click-to-call', 'call routing', 'SMS intelligence', 'Twilio', 'Telnyx', 'Vapi',
  'Retell', 'Slybroadcast', 'call recording', 'sentiment analysis', 'voice biometrics',
  'call compliance', 'TCPA', 'call queue', 'scribe agent', 'call artifact',
  'call monitoring', 'voice workflow', 'ringless voicemail', 'call quality assurance',
  'conversation intelligence', 'call summary', 'five C analysis', 'PII redaction'.
---

# Call Intelligence Platform Challenge

## The Core Problem

Perennia AI's call intelligence platform spans **4 telephony providers**, **6 AI agents**, **30+ route files**, **15+ services**, and **20+ database tables**. It handles everything from click-to-call through real-time AI whisper to post-call artifact generation and compliance monitoring. A failure in any layer — credential misconfiguration, broken webhook, missing TCPA check, orphaned call session, or silent AI agent — directly impacts loan officer productivity and regulatory compliance.

This skill validates every layer of the call intelligence stack against production readiness criteria.

---

## Architecture Overview

```
                          INBOUND                              OUTBOUND
                      +-----------+                       +---------------+
                      |  Telnyx   |                       | Power Dialer  |
                      |  Twilio   |                       | Click-to-Call |
                      |  Vapi     |                       | Voicemail Drop|
                      +-----+-----+                       +-------+-------+
                            |                                     |
                      +-----v-------------------------------------v-------+
                      |              CALL SESSION MANAGER                 |
                      |  (call_monitoring_models.py — CallSession)        |
                      +---+---+---+---+---+---+---+---+---+---+---+------+
                          |       |       |       |       |       |
                    +-----v-+ +---v---+ +-v-----+ +-----v-+ +---v---+ +--v----+
                    |Scribe | |Jr. LO | |  UW   | | Calc  | |Market | |Recept |
                    |Agent  | |Agent  | |Agent  | | Agent | |Agent  | |Agent  |
                    +---+---+ +---+---+ +---+---+ +--+----+ +---+---+ +---+---+
                        |         |         |        |           |         |
                    +---v---------v---------v--------v-----------v---------v---+
                    |                  ARTIFACT PIPELINE                       |
                    |  summary | action_item | risk_flag | intake_field | ...  |
                    +---+------+------+------+-----+-----+------+------+------+
                        |             |            |             |
                   +----v----+  +-----v-----+ +---v----+  +-----v------+
                   |Approval |  |CRM Update |  |  PII  |  |Compliance  |
                   |Workflow |  |(lead/loan) |  |Redact |  |  Monitor   |
                   +---------+  +-----------+  +--------+  +------------+
```

---

## Domain 1: Telephony Provider Health

Read `references/telephony-providers.md` for full provider configuration details.

Every call flows through one of four telephony providers. A misconfigured provider silently kills call functionality.

### Checks

| Check ID | Check | Severity | Weight |
|----------|-------|----------|--------|
| TEL-001 | Twilio credentials valid (ACCOUNT_SID + AUTH_TOKEN) | BLOCKER | 15 |
| TEL-002 | Twilio AUTH_TOKEN has no trailing whitespace/newline | CRITICAL | 10 |
| TEL-003 | Telnyx API key valid and accepted by API | BLOCKER | 15 |
| TEL-004 | Vapi API key valid, webhook secret configured | CRITICAL | 10 |
| TEL-005 | Retell API key valid | CRITICAL | 10 |
| TEL-006 | Slybroadcast credentials valid (c_uid + c_password) | HIGH | 5 |
| TEL-007 | All webhook URLs point to production domain (api.perenniaai.com) | CRITICAL | 10 |
| TEL-008 | Twilio status callback URL registered and reachable | HIGH | 5 |
| TEL-009 | Vapi voicemailDetection uses new format (provider: "vapi") | HIGH | 5 |
| TEL-010 | Vapi voice config uses valid voice ID (deepgram/asteria, not 11labs/paula) | HIGH | 5 |

### Known Issues (from production history)
- **Telnyx API key INVALID** (Feb 2026): `KEY0185C2...` rejected as malformed. Needs rotation.
- **Twilio AUTH_TOKEN had trailing `\n`**: Caused stale credential errors. Always strip whitespace.
- **Vapi voice "paula" doesn't exist in 11labs**: Changed to deepgram/asteria. Any assistant referencing 11labs/paula will get `pipeline-error-eleven-labs-voice-not-found`.
- **Vapi voicemailDetection format changed (2025+)**: Old `{enabled, machineDetectionTimeout, voicemailMessage}` is rejected. New: `{provider: "vapi", beepMaxAwaitSeconds: 25}`.

### Validation Steps
1. Verify each provider's env vars exist and are non-empty in Railway
2. Make a test API call to each provider's status/account endpoint
3. Confirm webhook URLs resolve to api.perenniaai.com (not localhost)
4. Check for whitespace/newline contamination in credential env vars
5. Verify Vapi assistant configs use supported voice provider + voice ID

---

## Domain 2: Power Dialer & Click-to-Call

Read `references/dialer-models.md` for database schema details.

### Checks

| Check ID | Check | Severity | Weight |
|----------|-------|----------|--------|
| PD-001 | DialerSession model exists with all required columns | CRITICAL | 10 |
| PD-002 | DialerSessionTask tracks lead_id, loan_id, referral_partner_id | HIGH | 5 |
| PD-003 | AgentTelephonySettings supports per-agent caller ID + max calls/day | HIGH | 5 |
| PD-004 | VerifiedCallerId table tracks Twilio verification SID | HIGH | 5 |
| PD-005 | DNC list checked before every outbound dial | BLOCKER | 15 |
| PD-006 | Call disposition recorded with outcome + follow-up date | CRITICAL | 10 |
| PD-007 | WebSocket real-time updates functional for session state changes | HIGH | 5 |
| PD-008 | Auto-advance respects configurable pause_between_calls setting | MEDIUM | 3 |
| PD-009 | Click-to-call preserves lead/loan context through entire call | HIGH | 5 |
| PD-010 | Caller ID selection uses verified numbers only | CRITICAL | 10 |

### Key Files
- `backend/routes/power_dialer_routes.py` — Dialer API endpoints
- `backend/telephony/dialer_engine.py` — Core dialer logic
- `backend/services/click_to_call_service.py` (655 lines) — Click-to-call
- `backend/services/twilio_click_to_call.py` (753 lines) — Twilio-specific click-to-call
- `backend/database/models/dialer.py` — AgentTelephonySettings, VerifiedCallerId, DialerSession, DialerSessionTask
- `backend/services/workflow_dialer_integration.py` — Workflow-to-dialer bridge

### Critical Path
```
User clicks "Call" → click_to_call_service → DNC check → caller ID selection
  → Twilio/Telnyx API → call connected → session created → disposition UI
  → follow-up scheduled → CRM updated
```

---

## Domain 3: AI Receptionist

### Checks

| Check ID | Check | Severity | Weight |
|----------|-------|----------|--------|
| REC-001 | AI receptionist route registered and responding | CRITICAL | 10 |
| REC-002 | Vapi assistant config valid (voice, model, instructions) | HIGH | 5 |
| REC-003 | Webhook handler processes call events (started, ended, transcript) | CRITICAL | 10 |
| REC-004 | Calendar integration functional for appointment scheduling | HIGH | 5 |
| REC-005 | Post-call SMS sends confirmation to caller | MEDIUM | 3 |
| REC-006 | Dashboard analytics populate from call data | HIGH | 5 |
| REC-007 | Multi-tenant: receptionist config isolated per organization | CRITICAL | 10 |
| REC-008 | Fallback behavior when AI fails (transfer to human, voicemail) | HIGH | 5 |

### Key Files
- `backend/routes/voice_ai_receptionist_routes.py` — Receptionist endpoints
- `backend/ai_receptionist_dashboard_routes.py` — Dashboard API
- `backend/ai_receptionist_tool_integration.py` — Tool integration
- `backend/agents/specialized/receptionist_agent.py` — Agent logic
- `backend/services/ai_receptionist_analytics_service.py` — Analytics

---

## Domain 4: Voicemail Drop System

### Checks

| Check ID | Check | Severity | Weight |
|----------|-------|----------|--------|
| VM-001 | TCPA compliance: calls restricted to 8AM-9PM recipient local time | BLOCKER | 15 |
| VM-002 | Area code to timezone mapping covers all US area codes | CRITICAL | 10 |
| VM-003 | DNC list enforced before every voicemail drop | BLOCKER | 15 |
| VM-004 | Slybroadcast API response parsed correctly (OK/session_id/phone count) | HIGH | 5 |
| VM-005 | Slybroadcast audio files > 5 seconds (API requirement) | HIGH | 5 |
| VM-006 | Vapi voicemail uses assistant-level voicemailMessage (not inside voicemailDetection) | HIGH | 5 |
| VM-007 | Delivery status webhook processes Slybroadcast POST correctly | HIGH | 5 |
| VM-008 | Call status check uses session_id + c_phone for Slybroadcast | MEDIUM | 3 |
| VM-009 | BorrowerProfile consent checked before voicemail drop | BLOCKER | 15 |
| VM-010 | Consent check matches on email (BorrowerProfile has NO phone column) | CRITICAL | 10 |

### TCPA Compliance (Non-Negotiable)
```
ALLOWED WINDOW: 8:00 AM - 9:00 PM in recipient's LOCAL timezone
ENFORCEMENT: Area code → timezone lookup before every drop
DNC CHECK: Must query DNC list before every outbound attempt
CONSENT: BorrowerProfile.consent fields must be checked
WARNING: BorrowerProfile has NO phone column — match on email only
```

### Slybroadcast API Reference
```
URL: https://mobile-sphere.com/gateway/vmb.php
Account: tloss@cmghomeloans.com (NOT cmgfi.com)
Response format: "OK\nsession_id=NNN\nnumber of phone=N"
Status check: c_option=callstatus with session_id + c_phone
Webhook: $_POST['var'] = 6 pipe-delimited quoted fields
Audio: Must be > 5 seconds duration
```

---

## Domain 5: Call Intelligence & Multi-Agent Orchestration

Read `references/call-intelligence-agents.md` for agent specifications.

This is the most complex subsystem — 18+ files in `backend/services/call_intelligence/` totaling ~864 KB.

### Checks

| Check ID | Check | Severity | Weight |
|----------|-------|----------|--------|
| CI-001 | CallSession model supports all CaptureMode values | HIGH | 5 |
| CI-002 | All 6 AI agents registered and callable (Scribe, Jr LO, UW, Calc, Marketing, Receptionist) | CRITICAL | 10 |
| CI-003 | Artifact pipeline produces all 25+ ArtifactType values | HIGH | 5 |
| CI-004 | Approval workflow routes artifacts to correct approver | CRITICAL | 10 |
| CI-005 | PII redaction runs before artifact storage (phone, SSN) | BLOCKER | 15 |
| CI-006 | Five C's analysis covers all 5 categories (credit, collateral, capacity, characteristics, cash) | HIGH | 5 |
| CI-007 | Intake field extraction maps to 1003 form fields | HIGH | 5 |
| CI-008 | Risk flags include severity (low/medium/high/critical) and category | HIGH | 5 |
| CI-009 | Batch processor handles concurrent transcript processing | HIGH | 5 |
| CI-010 | Model versioning tracks which LLM version produced each artifact | MEDIUM | 3 |
| CI-011 | Streaming extractor processes real-time transcript chunks | HIGH | 5 |
| CI-012 | Unified extractor consolidates multi-agent outputs | HIGH | 5 |
| CI-013 | Review service queues artifacts for human review | CRITICAL | 10 |
| CI-014 | Webhook handlers process Twilio Intelligence callbacks | HIGH | 5 |
| CI-015 | Call metrics service tracks processing latency and throughput | MEDIUM | 3 |

### Agent Responsibilities

| Agent | Primary Artifacts | Key Capability |
|-------|------------------|----------------|
| **Scribe** | summary, action_item, follow_up_draft, scribe_recap | Call documentation |
| **Junior LO** | pricing_scenario, calculator_result | Rate/product recommendations |
| **Underwriter** | five_c_*, uw_review_item, risk_flag | Credit analysis |
| **Calculator** | calculator_result, pricing_scenario | Payment calculations |
| **Marketing** | borrower_story_note, content_idea, borrower_quote, story_theme | Content capture |
| **Receptionist** | scheduled_appointment, follow_up_call, calendar_action, meeting_summary | Scheduling |

### Artifact Lifecycle
```
Transcript → Agent Processing → Raw Artifact → PII Redaction
  → Validation → Approval Queue → (auto_approved | pending)
  → CRM Integration → Lead/Loan Update
```

### Key Files
- `backend/services/call_intelligence/processor.py` (27 KB) — Main processing engine
- `backend/services/call_intelligence/llm_client.py` (45 KB) — LLM interaction layer
- `backend/services/call_intelligence/process_transcript.py` (32 KB) — Transcript processing
- `backend/services/call_intelligence/unified_extractor.py` (15 KB) — Multi-agent consolidation
- `backend/services/call_intelligence/pii_utils.py` (18 KB) — PII masking
- `backend/services/call_intelligence/data_contracts.py` (17 KB) — Data models
- `backend/services/call_intelligence/review_service.py` (17 KB) — Human review queue
- `backend/services/call_intelligence/webhooks.py` (26 KB) — Webhook handling
- `backend/services/call_intelligence/orchestration/` — Agent coordination
- `backend/services/call_intelligence/agents/` — Specialized agent implementations

---

## Domain 6: Live Call Whisper

### Checks

| Check ID | Check | Severity | Weight |
|----------|-------|----------|--------|
| WH-001 | WebSocket connection established for whisper delivery | CRITICAL | 10 |
| WH-002 | Whisper types categorized (pricing, guidance, alert, information, action) | HIGH | 5 |
| WH-003 | Rate quotes calculated and delivered in real-time during call | HIGH | 5 |
| WH-004 | Objection handling tips triggered by keyword detection | MEDIUM | 3 |
| WH-005 | Multi-recipient broadcast functional (supervisor monitoring) | MEDIUM | 3 |
| WH-006 | Whisper latency under 2 seconds from trigger to delivery | HIGH | 5 |

### Key Files
- `backend/routes/live_call_whisper_routes.py` — WebSocket endpoints
- `backend/services/live_call_whisper_service.py` (705 lines) — Core whisper logic
- `backend/services/live_call_whisper_calculator.py` (504 lines) — Rate calculation during calls

---

## Domain 7: Call Compliance & Quality Assurance

### Checks

| Check ID | Check | Severity | Weight |
|----------|-------|----------|--------|
| CC-001 | Recording disclosure detected/enforced per state requirements | BLOCKER | 15 |
| CC-002 | Call recording consent tracked per participant | CRITICAL | 10 |
| CC-003 | TCPA compliance enforced for all outbound channels | BLOCKER | 15 |
| CC-004 | DNC list synchronized and checked within 24 hours | CRITICAL | 10 |
| CC-005 | Call quality scoring applied to completed calls | HIGH | 5 |
| CC-006 | Compliance violations flagged and escalated automatically | CRITICAL | 10 |
| CC-007 | Call screening blocks known spam/blocked numbers | HIGH | 5 |
| CC-008 | Sentiment analysis runs on completed call transcripts | MEDIUM | 3 |

### Compliance Requirements
- **One-party consent states**: Only LO consent needed for recording
- **Two-party consent states** (CA, FL, IL, etc.): All parties must consent
- **Recording disclosure**: Twilio Intelligence "Recording Disclosure" operator validates
- **TCPA calling hours**: 8AM-9PM local time for ALL outbound (calls + voicemail + SMS)
- **DNC enforcement**: Federal + state DNC lists, internal opt-out list

### Key Files
- `backend/services/call_compliance_service.py` — Compliance engine
- `backend/services/call_quality_assurance_service.py` — QA scoring
- `backend/services/call_screening_service.py` — Spam/block screening
- `backend/integrations/twilio_intelligence_service.py` (594 lines) — Twilio analysis

---

## Domain 8: SMS Intelligence

### Checks

| Check ID | Check | Severity | Weight |
|----------|-------|----------|--------|
| SMS-001 | Two-way SMS messaging functional via Twilio | CRITICAL | 10 |
| SMS-002 | SMS templates load from sms_templates.yaml | HIGH | 5 |
| SMS-003 | Opt-out processing removes contact from future SMS | BLOCKER | 15 |
| SMS-004 | SMS conversation threading by phone + lead | HIGH | 5 |
| SMS-005 | AI-powered SMS generation available | MEDIUM | 3 |
| SMS-006 | Document mention tracking in SMS content | MEDIUM | 3 |
| SMS-007 | SLA tracking for response times (immediate/standard/low_priority) | HIGH | 5 |

### SMS Templates (from sms_templates.yaml)
- welcome, document_reminder, appointment_reminder, callback_reminder
- application_link, rate_alert, prequal_ready, closing_reminder

### SMS Disposition Types
- pending_review, general_correspondence, document_mention, appointment_related
- status_inquiry, action_required, opt_out, skip, processed

### Key Files
- `backend/routes/sms_intelligence_routes.py` — SMS API
- `backend/integrations/sms_service.py` (312 lines) — Twilio SMS
- `backend/services/call_intelligence/templates/sms_templates.yaml` — Templates

---

## Domain 9: Call Recording & Transcription

### Checks

| Check ID | Check | Severity | Weight |
|----------|-------|----------|--------|
| CR-001 | Call recordings captured and stored securely | CRITICAL | 10 |
| CR-002 | Twilio Intelligence Service SID configured | HIGH | 5 |
| CR-003 | Transcription with speaker diarization functional | HIGH | 5 |
| CR-004 | Supported audio formats: WAV, MP3, FLAC (max 3GB, 8 hours) | MEDIUM | 3 |
| CR-005 | Recording playback URLs generated with expiring tokens | HIGH | 5 |
| CR-006 | Deepgram STT integration functional for real-time transcription | HIGH | 5 |
| CR-007 | Voice sentiment analysis runs on completed transcripts | MEDIUM | 3 |
| CR-008 | Entity recognition extracts names, amounts, dates from calls | HIGH | 5 |

### Key Files
- `backend/api/routes/call_recording.py` — Recording API
- `backend/integrations/twilio_intelligence_service.py` (594 lines) — Transcription + analysis
- `backend/services/voice_sentiment_service.py` (333 lines) — Sentiment
- `backend/services/voice_biometrics_service.py` (649 lines) — Speaker recognition
- `backend/services/voice_slot_extractor.py` (344 lines) — Entity extraction

---

## Domain 10: Call Routing, Queuing & Voice Workflows

### Checks

| Check ID | Check | Severity | Weight |
|----------|-------|----------|--------|
| CQ-001 | Call queue tracks position and estimated wait time | HIGH | 5 |
| CQ-002 | Queue statistics available for monitoring | MEDIUM | 3 |
| CQ-003 | Voice workflow WebSocket sessions managed properly | CRITICAL | 10 |
| CQ-004 | Multi-step conversation flows preserve context across turns | HIGH | 5 |
| CQ-005 | Twilio IVR integration routes calls to correct queue/agent | HIGH | 5 |
| CQ-006 | Session cleanup on call disconnect (no orphaned sessions) | CRITICAL | 10 |

### Key Files
- `backend/routes/call_queue_routes.py` — Queue management
- `backend/routes/voice_workflow_routes.py` — Voice workflow API
- `backend/services/voice_workflow_service.py` (830 lines) — Workflow engine
- `backend/models/voice_workflow_models.py` — Workflow data models

---

## Domain 11: Database & Model Integrity

### Checks

| Check ID | Check | Severity | Weight |
|----------|-------|----------|--------|
| DB-001 | All call-related tables exist in production (migrations applied) | BLOCKER | 15 |
| DB-002 | CallSession enum values match code (CaptureMode, CallSessionStatus) | CRITICAL | 10 |
| DB-003 | ArtifactType enum covers all 25+ artifact types | HIGH | 5 |
| DB-004 | Foreign keys link call sessions to leads/loans/users | HIGH | 5 |
| DB-005 | Organization_id present on all tenant-scoped call tables | CRITICAL | 10 |
| DB-006 | Activity model logs call touchpoints with sentiment + duration | HIGH | 5 |
| DB-007 | SMSMessage and SMSConversation models support Twilio SID tracking | HIGH | 5 |
| DB-008 | EmailDraft supports call summary source (source_type, recording_url, call_summary) | MEDIUM | 3 |

### Key Database Models
- `backend/database/models/communication.py` — Activity, SMSMessage, SMSConversation, EmailDraft
- `backend/database/models/dialer.py` — AgentTelephonySettings, VerifiedCallerId, DialerSession, DialerSessionTask
- `backend/models/call_monitoring_models.py` — CallSession, enums, artifact types

---

## Scoring

**Total possible: 100 points**

```
Score = 100 - sum(failed_check_weights)
```

| Grade | Score | Assessment |
|-------|-------|------------|
| A | 90-100 | Production ready — all critical paths validated |
| B | 75-89 | Mostly ready — non-blocking issues remain |
| C | 60-74 | Significant gaps — fix before production calls |
| D | 40-59 | Major issues — telephony unreliable |
| F | 0-39 | Broken — calls will fail in production |

**Any BLOCKER failure = automatic F regardless of score.**

BLOCKER checks (automatic F if failed):
- TEL-001: Twilio credentials
- TEL-003: Telnyx credentials
- PD-005: DNC list enforcement
- VM-001: TCPA compliance
- VM-009: Consent check
- CI-005: PII redaction
- CC-001: Recording disclosure
- CC-003: TCPA enforcement
- SMS-003: Opt-out processing
- DB-001: Tables exist

---

## Debugging Guide

### "Calls aren't connecting"
1. Check TEL-001 through TEL-004 (provider credentials)
2. Verify webhook URLs point to api.perenniaai.com
3. Check Twilio/Telnyx account balance
4. Look for trailing whitespace in AUTH_TOKEN env vars
5. Check Telnyx API key validity (known invalid as of Feb 2026)

### "Voicemail drops failing"
1. Check TCPA window (8AM-9PM recipient local time)
2. Verify Slybroadcast credentials and account email
3. Confirm audio files are > 5 seconds
4. Check Vapi voicemailDetection format (must use new provider format)
5. Verify voice ID exists (deepgram/asteria, NOT 11labs/paula)

### "Call intelligence not producing artifacts"
1. Verify call session created with correct CaptureMode
2. Check that transcript is being captured (Deepgram STT or Twilio)
3. Confirm LLM client can reach AI provider (OpenAI/Claude)
4. Check PII utils not stripping entire transcript
5. Verify agent orchestration pipeline executing all 6 agents
6. Check review service queue for stuck artifacts

### "Power dialer not advancing"
1. Verify WebSocket connection active
2. Check DNC list not blocking all numbers
3. Confirm caller ID is verified
4. Check auto-advance setting and pause_between_calls value
5. Verify session status is "active" not "paused"

### "SMS not sending"
1. Check Twilio SMS credentials (may differ from voice credentials)
2. Verify opt-out list not blocking recipient
3. Check SMS template exists in sms_templates.yaml
4. Confirm phone number format (E.164: +1XXXXXXXXXX)
5. Check Twilio sending limits and account status

---

## Implementation Checklist

### Phase 1: Provider Health (must pass before anything else)
- [ ] All 4 provider credentials valid and tested
- [ ] Webhook URLs configured for production domain
- [ ] Telnyx API key rotated (known invalid)
- [ ] Twilio Intelligence Service SID created
- [ ] Vapi assistant configs use valid voice IDs

### Phase 2: Compliance (non-negotiable)
- [ ] TCPA window enforcement on all outbound channels
- [ ] DNC list checked before every outbound attempt
- [ ] Recording disclosure validation active
- [ ] Consent checking functional (email-based for BorrowerProfile)
- [ ] PII redaction running on all stored transcripts/artifacts
- [ ] SMS opt-out processing immediate and permanent
- [ ] Two-party consent states identified and enforced

### Phase 3: Core Call Flow
- [ ] Click-to-call connects with lead/loan context
- [ ] Power dialer sessions create, pause, resume, stop correctly
- [ ] Call dispositions recorded with follow-up actions
- [ ] Call recordings captured and accessible
- [ ] Transcription producing accurate text with speaker labels

### Phase 4: AI Intelligence
- [ ] All 6 agents produce expected artifact types
- [ ] Artifact approval workflow routes correctly
- [ ] Five C's analysis covers all categories
- [ ] Intake field extraction maps to 1003 form
- [ ] Risk flags generated with proper severity
- [ ] Live whisper delivers in under 2 seconds
- [ ] Batch processor handles concurrent loads

### Phase 5: Integration & Monitoring
- [ ] Call data flows to CRM (leads, loans, activities)
- [ ] SMS conversations thread correctly
- [ ] Dashboard analytics populate from real data
- [ ] Call quality scores computed and stored
- [ ] Sentiment analysis runs on completed calls
- [ ] WebSocket connections clean up on disconnect
- [ ] Multi-tenant isolation enforced on all call data
