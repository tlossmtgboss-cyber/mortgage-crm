# Call Intelligence Agents — Specifications & Validation

## Overview

The call intelligence system uses a multi-agent orchestration architecture where 6 specialized AI agents process call transcripts in parallel, each producing domain-specific artifacts. The orchestration layer coordinates agent execution, deduplicates outputs, and routes artifacts through approval workflows.

## Architecture

```
                    Raw Transcript
                         |
                  +------v------+
                  | Orchestrator |
                  +--+--+--+--+-+
                     |  |  |  |  \
              +------+  |  |  |   +--------+
              v         v  v  v            v
          +-------+ +----+ +--+ +------+ +-----+  +-----+
          |Scribe | |JrLO| |UW| | Calc | |Mktg |  |Recep|
          +---+---+ +--+-+ +-++ +--+---+ +--+--+  +--+--+
              |        |    |      |        |         |
              v        v    v      v        v         v
          [summary] [pricing] [5Cs] [calc] [story] [appt]
              |        |    |      |        |         |
              +--------+----+------+--------+---------+
                              |
                    +---------v---------+
                    | Unified Extractor |
                    +---------+---------+
                              |
                    +---------v---------+
                    |   PII Redaction   |
                    +---------+---------+
                              |
                    +---------v---------+
                    | Approval Workflow |
                    +---------+---------+
                              |
                    +---------v---------+
                    |  CRM Integration  |
                    +-------------------+
```

---

## Agent Specifications

### 1. Scribe Agent

**Purpose**: Primary call documentation — captures what happened, what was discussed, and what needs to happen next.

**File**: `backend/agents/specialized/receptionist_agent.py` (shared), `backend/services/call_intelligence/agents/`

**Artifact Types Produced**:
| Artifact | Description |
|----------|-------------|
| `summary` | Concise call summary (who, what, outcome) |
| `action_item` | Specific tasks that need to be done |
| `follow_up_draft` | Draft email/SMS for post-call follow-up |
| `scribe_recap` | Detailed chronological recap |
| `stacked_note` | Layered notes building on previous calls |

**Validation Criteria**:
- Summary includes: participants, duration context, key topics, outcome
- Action items have: description, assignee (LO/processor/borrower), due date
- Follow-up drafts are personalized with borrower name and call specifics
- Stacked notes reference previous call context when available

---

### 2. Junior Loan Officer Agent

**Purpose**: Provides pricing analysis and product recommendations based on call discussion.

**Artifact Types Produced**:
| Artifact | Description |
|----------|-------------|
| `pricing_scenario` | Rate/product comparison scenarios |
| `calculator_result` | Payment calculations based on discussed terms |

**Validation Criteria**:
- Pricing scenarios include: loan type, rate, APR, monthly payment, closing costs
- Multiple scenarios compared (e.g., 30yr fixed vs 15yr vs ARM)
- Calculator results match current rate environment
- Product eligibility verified against discussed borrower profile

---

### 3. Underwriter Agent

**Purpose**: Performs credit analysis using the Five C's framework, identifies risks, and generates underwriting notes.

**Artifact Types Produced**:
| Artifact | Description |
|----------|-------------|
| `five_c_credit` | Credit history analysis |
| `five_c_collateral` | Property/collateral assessment |
| `five_c_capacity` | Income/DTI capacity analysis |
| `five_c_characteristics` | Loan characteristics review |
| `five_c_cash` | Assets/reserves evaluation |
| `uw_review_item` | Items requiring underwriter attention |
| `risk_flag` | Identified risks with severity |

**Risk Flag Schema**:
```python
class RiskFlag:
    category: RiskCategory  # credit, income, employment, property, compliance, assets, dti
    severity: RiskSeverity  # low, medium, high, critical
    description: str
    mitigation: str         # Suggested remediation
    source_quote: str       # Exact transcript excerpt
```

**Validation Criteria**:
- All 5 C's addressed when sufficient information discussed
- Risk flags include severity AND category
- UW review items are actionable (not vague)
- Source quotes accurately reference transcript

---

### 4. Calculator Agent

**Purpose**: Performs rate calculations and payment estimates based on discussed scenarios.

**Artifact Types Produced**:
| Artifact | Description |
|----------|-------------|
| `calculator_result` | Detailed payment breakdown |
| `pricing_scenario` | What-if scenario calculations |

**Validation Criteria**:
- Calculations use current market rates (not stale)
- P&I, taxes, insurance, PMI broken out separately
- DTI ratio calculated when income discussed
- LTV computed when property value and loan amount mentioned

---

### 5. Marketing Agent

**Purpose**: Captures borrower stories, testimonial-worthy quotes, and content ideas for marketing use.

**Artifact Types Produced**:
| Artifact | Description |
|----------|-------------|
| `borrower_story_note` | Narrative elements of borrower's journey |
| `content_idea` | Marketing content suggestions based on call |
| `borrower_quote` | Direct quotes suitable for testimonials |
| `story_theme` | Thematic tags (first-time buyer, military, etc.) |
| `marketing_milestone` | Key events worth celebrating |

**Validation Criteria**:
- Quotes are actual borrower words (not paraphrased)
- Story notes capture emotional context (why this matters to them)
- Content ideas are actionable (not generic "write a blog post")
- Only positive/neutral content flagged (not complaints)

---

### 6. Receptionist Agent

**Purpose**: Handles scheduling, appointment management, and meeting coordination.

**Artifact Types Produced**:
| Artifact | Description |
|----------|-------------|
| `scheduled_appointment` | Confirmed appointment details |
| `follow_up_call` | Scheduled callback |
| `calendar_action` | Calendar event to create/modify |
| `meeting_summary` | Summary of meeting outcomes |

**Validation Criteria**:
- Appointments include: date, time, timezone, participants, type
- Follow-up calls have specific date/time (not "next week")
- Calendar actions include enough detail to create the event
- Meeting summaries capture decisions made

---

## Artifact Lifecycle

### States
```
                +-----------+
                |  Created  |
                +-----+-----+
                      |
                +-----v-----+
                |PII Redacted|
                +-----+------+
                      |
              +-------v-------+
              |   Validated   |
              +---+-------+---+
                  |       |
           +------v-+  +--v--------+
           |  Auto  |  |  Pending  |
           |Approved|  |  Review   |
           +---+----+  +-----+-----+
               |              |
               |        +-----v-----+
               |        |  Approved  |
               |        |    or      |
               |        |  Rejected  |
               |        +-----+------+
               |              |
               +------+-------+
                      |
               +------v------+
               | CRM Updated |
               +--------------+
```

### Approval Rules
| Artifact Type | Auto-Approve? | Requires Review? |
|---------------|---------------|------------------|
| summary | Yes (if confidence > 0.8) | If confidence < 0.8 |
| action_item | No | Always |
| risk_flag (critical) | No | Always |
| risk_flag (low/medium) | Yes | No |
| pricing_scenario | No | Always |
| intake_field | Yes (if confidence > 0.9) | If confidence < 0.9 |
| borrower_quote | No | Always (privacy review) |
| scheduled_appointment | No | Always (calendar impact) |

---

## Call Session Model

### CaptureMode Enum
```python
class CaptureMode(str, Enum):
    mobile_app = "mobile_app"               # Recording from mobile app
    crm_web_call = "crm_web_call"           # Click-to-call from CRM
    ambient_mic = "ambient_mic"             # In-person meeting capture
    video_call = "video_call"               # Video call recording
    call_intelligence = "call_intelligence" # Twilio Intelligence pipeline
```

### CallSessionStatus Enum
```python
class CallSessionStatus(str, Enum):
    active = "active"                 # Call in progress
    processing = "processing"         # Transcript being analyzed
    review_pending = "review_pending" # Artifacts awaiting review
    completed = "completed"           # All artifacts finalized
    failed = "failed"                 # Processing error
```

### ParticipantRole Enum
```python
class ParticipantRole(str, Enum):
    loan_officer = "loan_officer"
    borrower = "borrower"
    co_borrower = "co_borrower"
    realtor = "realtor"
    title_agent = "title_agent"
    insurance_agent = "insurance_agent"
    other = "other"
```

---

## Orchestration Pipeline

### Processing Steps
1. **Transcript ingestion**: Raw transcript with speaker labels
2. **Chunking**: Split into manageable segments for parallel processing
3. **Agent dispatch**: All 6 agents process relevant chunks concurrently
4. **Artifact collection**: Gather outputs from all agents
5. **Deduplication**: Remove overlapping artifacts (e.g., same action item from Scribe and UW)
6. **PII redaction**: Mask SSN, phone numbers, account numbers in all artifacts
7. **Validation**: Check artifact completeness and confidence scores
8. **Approval routing**: Auto-approve or queue for human review
9. **CRM integration**: Update lead/loan records with approved artifacts

### Error Handling
- Individual agent failure does NOT block other agents
- Failed agents are retried once with reduced context
- If > 3 agents fail, session marked as `failed` with partial results preserved
- All errors logged with transcript segment that caused failure

---

## Key Service Files

| File | Size | Purpose |
|------|------|---------|
| `call_intelligence/processor.py` | 27 KB | Main processing engine |
| `call_intelligence/llm_client.py` | 45 KB | LLM interaction layer |
| `call_intelligence/process_transcript.py` | 32 KB | Transcript processing |
| `call_intelligence/unified_extractor.py` | 15 KB | Multi-agent consolidation |
| `call_intelligence/pii_utils.py` | 18 KB | PII masking |
| `call_intelligence/data_contracts.py` | 17 KB | Data models/contracts |
| `call_intelligence/review_service.py` | 17 KB | Human review queue |
| `call_intelligence/webhooks.py` | 26 KB | Webhook handling |
| `call_intelligence/batch_processor.py` | 15 KB | Concurrent processing |
| `call_intelligence/streaming_extractor.py` | 16 KB | Real-time extraction |
| `call_intelligence/extraction_validator.py` | 28 KB | Output validation |
| `call_intelligence/model_versioning.py` | 22 KB | LLM version tracking |
| `call_intelligence/metrics.py` | 16 KB | Processing metrics |
| `call_intelligence/input_formats.py` | 17 KB | Input normalization |
| `call_intelligence/email_templates.py` | 28 KB | Email template gen |
| `call_intelligence/integration.py` | 36 KB | CRM integration |

**Total**: ~864 KB of call intelligence service code

---

## Test Coverage

### Existing Tests
- `backend/tests/unit/test_call_intelligence.py` — Core processing tests
- `backend/tests/unit/test_call_intelligence_orchestration.py` — Orchestration tests

### Recommended Test Scenarios
1. **Happy path**: Full transcript → all 6 agents → all artifact types produced
2. **Partial transcript**: Short call → only relevant agents fire
3. **PII heavy**: Transcript with SSN, phone, CC → all redacted in output
4. **Agent failure**: One agent fails → others complete successfully
5. **Concurrent processing**: 10 transcripts submitted simultaneously
6. **Approval workflow**: Auto-approve vs manual review routing
7. **Empty transcript**: No speech detected → graceful handling
8. **Multi-speaker**: 3+ participants → correct speaker attribution
