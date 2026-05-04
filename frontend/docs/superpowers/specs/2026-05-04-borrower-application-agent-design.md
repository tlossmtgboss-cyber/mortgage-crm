# Borrower Loan Application Agent — Design Spec

**Date:** 2026-05-04
**Status:** Approved
**Approach:** Core Agent + Essential Tools (Approach 2)

---

## Summary

Replace the existing POS AI Q&A engine (`GuidelinesChatAgent`) with a purpose-built `BorrowerApplicationAgent` that helps borrowers complete their URLA 1003, answers appraisal/title questions with real-time loan data, detects risk, escalates to LO calls via Smart Calendar, emits CRM events, and enforces RESPA/ECOA/TRID/TCPA/Reg B compliance. The agent is the single borrower-facing AI assistant in the portal.

---

## 1. Agent Service Architecture

**New file:** `backend/services/pos/borrower_application_agent.py`

**Class:** `BorrowerApplicationAgent`

- Standalone agent service (not routed through the LO-facing orchestrator)
- Calls Claude Sonnet via `anthropic_client` with `temperature=0.2`
- Tool-use enabled: Claude can call tools mid-turn (check calendar, book meeting, emit event) and weave results into response
- Returns `AgentResponse` dict: `content`, `sources`, `follow_ups`, `structured_output`, `escalation_reason`

**Flow per turn:**

1. `ai_qa_service.ask()` calls `BorrowerApplicationAgent.answer()`
2. Agent pre-loads application state and loan status as context (same pattern as current `_retrieve_loan_context()`) — this is automatic, not a Claude tool call
3. Agent builds messages: system prompt + application context + conversation history + borrower question
4. Claude responds with natural language + structured JSON block. Claude can also request tool calls (book meeting, check calendar, emit event, suggest doc upload).
5. Agent executes any tool calls, feeds results back to Claude, Claude produces final response
6. Returns `AgentResponse`

**Tool call model:** `get_application_state` and `get_loan_status` are pre-loaded as context (always available). The remaining 6 tools (`get_lo_availability`, `book_lo_meeting`, `propose_alternate_window`, `prompt_document_upload`, `emit_crm_event`, `recall_borrower_context`) are Claude-callable tools that fire on demand during the conversation.

**Key architectural decisions:**

- Standalone (not integrated into main orchestrator) because borrower-facing constraints (compliance guardrails, no-approval language, escalation-to-human flow) differ fundamentally from LO-facing agent
- `@mortgage_tool` tools called directly, not through the dynamic tool loader
- Same Anthropic client as the orchestrator (shared connection pooling)

---

## 2. Tools

**New file:** `backend/agents/tools/borrower_application.py`

Eight `@mortgage_tool` tools with `agent_roles=["borrower_application_agent"]`:

| Tool | Purpose | Risk | Data Source |
|---|---|---|---|
| `get_application_state` | Fetch borrower's in-progress URLA sections, completion %, current step | low | `POSApplication` + `POSApplicationSection` |
| `get_loan_status` | Pull real-time loan milestones: stage, appraisal status, title status, closing date, conditions | low | `Loan` model via `POSApplication.loan_id` |
| `get_lo_availability` | Fetch 3-5 calendar slots for the assigned LO in borrower's timezone | low | Smart Scheduler service (existing) |
| `book_lo_meeting` | Confirm a meeting booking, emit calendar invite | medium | Smart Scheduler + event bus |
| `propose_alternate_window` | Widen calendar search window if borrower wants different times | low | Smart Scheduler service |
| `prompt_document_upload` | Return structured prompt directing borrower to Smart Docs uploader with doc type and label | low | Returns UI directive (no DB write) |
| `emit_crm_event` | Publish APPLICATION_ESCALATION, DOCUMENT_SUGGESTED, or APPLICATION_STALL events | medium | Event bus (`event_bus.publish()`) |
| `recall_borrower_context` | Query prior conversation history and borrower profile for cross-session continuity | low | `POSAIQAMessage` + `BorrowerProfile` |

**Tenant isolation:** All tools receive `organization_id` from PURL auth context. DB queries filter on `organization_id`. `emit_crm_event` includes `tenant_id` in every payload.

**Calendar tools** delegate to existing Smart Scheduler service (`backend/services/appointment/`).

**`get_loan_status`** reads: `appraisal_ordered_date`, `appraisal_received_date`, `appraisal_value`, `title_ordered_date`, `title_received_date`, `title_company`, `stage`, `closing_date`, conditions (pending/cleared counts). Agent explains in plain language, escalates judgment calls.

---

## 3. System Prompt

**New file:** `backend/agents/perennia-prompts/core/borrower_application_agent.txt`

~3,700 tokens covering:

- **Identity & guardrails (~300 tokens):** Role definition, the One Rule (never say qualify/approved/denied/rate), standing deflection language
- **Response framework (~200 tokens):** 5-beat structure (What it means, Why it matters, How to answer, What may be needed, When to ask your loan team). 4-8 sentences for field questions.
- **URLA field knowledge (~1,500 tokens):** All 8 sections, top 30-40 fields that drive 90% of questions
- **Appraisal & title knowledge (~400 tokens):** Types, timeline, who pays, common defects, owner's vs lender's policy, when to use `get_loan_status`
- **Compliance guardrails (~400 tokens):** ECOA/Reg B (alimony voluntary), TCPA, RESPA Section 8, HMDA optional, Fair Housing, compliance flag codes
- **Escalation triggers (~300 tokens):** Hard triggers (BK, foreclosure, self-employment, gift funds, divorce, foreign income, trust, POA), soft triggers (repeated questions, "I'm not sure"), power conversion line
- **Document guidance (~200 tokens):** Common doc types by scenario, closing caveat
- **Tone rules (~150 tokens):** Clear, confident, professional, non-judgmental. Phrases to use/avoid.
- **Structured output contract (~200 tokens):** JSON schema returned alongside every response

---

## 4. CRM Wiring & Client File Connection

**The chain:** `POSApplication.contact_id` → `Lead.id` → `ClientFile.lead_id`

**New file:** `backend/services/pos/borrower_agent_event_handlers.py`

Event subscribers that translate agent events into CRM records:

| Agent Event | CRM Effect |
|---|---|
| `APPLICATION_ESCALATION` | Activity on Lead + Task for LO ("Review escalation: {trigger}") + `ensure_client_file()` + update `ClientFile.last_contact_at` |
| `MEETING_BOOKED` | Appointment linked to Lead + Loan + Task + LO notification email |
| `DOCUMENT_SUGGESTED` | Activity on Lead noting docs suggested and why |
| `APPLICATION_STALL` | Task for LO ("Borrower stalled on {section}") + nurture workflow trigger |

**ClientFile guarantee:** `ensure_client_file()` called on every escalation ensures a ClientFile exists before any CRM-visible action. Covers the case where borrower starts an application but no one has viewed their lead yet.

**Identity unification:** `contact_id` → `Lead` → `ClientFile`. LO sees the same client in CRM with all AI interactions logged as Activities. One record, two surfaces.

---

## 5. POS AI Q&A Integration

**Minimal changes to existing code.** Route and endpoint stay the same.

### Service changes (`backend/services/pos/ai_qa_service.py`)

- Import `BorrowerApplicationAgent` instead of `GuidelinesChatAgent`
- In `ask()`, call `BorrowerApplicationAgent.answer()` with additional context: `organization_id`, `contact_id`, `loan_id`
- Parse structured output JSON from agent response, persist alongside message
- If `escalate_to_human=True`, set `confidence="escalate"` on `POSAIQAMessage`

### Schema additions (`backend/schemas/pos/ai_qa.py`)

- `structured_output: dict | None` on `AskResponse`
- `meeting_offered: bool` on `AskResponse`
- `meeting_details: dict | None` (slot time, LO name, confirmation) when meeting booked mid-conversation

### Frontend changes (`AriaChatPanel.tsx` / `useAriaChat.ts`)

- When `meeting_offered=true`, render calendar confirmation card inline in chat
- When `escalation_recommended=true`, render "Your loan officer can help with this" banner with meeting slots
- Follow-up chips continue working unchanged (agent's `follow_ups` field feeds them)

### No breaking changes

- Same endpoints, same auth (PURL token), same `POSAIQAMessage` storage
- Borrower experience is seamless — Aria gets smarter, not different

---

## 6. Structured Output (Per Turn)

Every turn, alongside the natural-language response, the agent returns:

```json
{
  "borrower_question": "<verbatim input>",
  "application_section": "<urla_section_id>",
  "field_name": "<urla_field_or_null>",
  "intent": "explain_field | doc_guidance | escalation | scheduling | reassurance | smalltalk | out_of_scope",
  "risk_level": "low | medium | high",
  "documents_suggested": ["<doc_type>"],
  "escalate_to_human": true | false,
  "meeting_offered": true | false,
  "compliance_flags": ["<flag>"],
  "next_best_action": "<short directive>"
}
```

Persisted in `POSAIQAMessage` as a new JSONB column `structured_output`. Used by:
- LO heads-up display (see escalation flags before reviewing file)
- Analytics (which sections cause stalls, which triggers fire most)
- Orchestrator routing (downstream automation based on `next_best_action`)

---

## 7. Testing

### Unit tests (`backend/tests/test_borrower_application_agent.py`)

- Each `@mortgage_tool` independently: correct data returned, tenant isolation enforced
- Compliance guardrail enforcement: mock responses violating rules, verify structured output flags
- Escalation trigger detection: trigger phrases → `escalate_to_human=True`
- Structured output parsing: JSON correctly extracted from mixed response

### Integration tests (`backend/tests/test_borrower_agent_integration.py`)

- Create `POSApplication` with sample data, call `BorrowerApplicationAgent.answer()` with real questions
- Verify: content + structured output returned, CRM events emitted, confidence scored
- Calendar flow: escalation trigger → `get_lo_availability` called → slots in response
- Loan status: link Loan with appraisal dates, ask about appraisal, verify real dates referenced

### E2E smoke test (`backend/tests/test_pos_ai_qa_e2e.py`)

- Hit `/api/v1/pos/ai-qa/ask` with PURL-authenticated request
- Verify response shape matches updated `AskResponse` schema
- Verify `POSAIQAMessage` persisted with structured output
- Verify Activity record on Lead when escalation fires
- Verify `ClientFile` exists after escalation event

---

## 8. New Files Summary

| File | Type | Purpose |
|---|---|---|
| `backend/services/pos/borrower_application_agent.py` | Service | Agent class — prompt building, Claude call, tool dispatch |
| `backend/agents/tools/borrower_application.py` | Tools | 8 @mortgage_tool tools for the agent |
| `backend/agents/perennia-prompts/core/borrower_application_agent.txt` | Prompt | System prompt (~3,700 tokens) |
| `backend/services/pos/borrower_agent_event_handlers.py` | Events | CRM event subscribers (4 handlers) |
| `backend/tests/test_borrower_application_agent.py` | Test | Unit tests |
| `backend/tests/test_borrower_agent_integration.py` | Test | Integration tests |
| `backend/tests/test_pos_ai_qa_e2e.py` | Test | E2E smoke tests |

### Modified Files

| File | Change |
|---|---|
| `backend/services/pos/ai_qa_service.py` | Swap GuidelinesChatAgent → BorrowerApplicationAgent |
| `backend/schemas/pos/ai_qa.py` | Add structured_output, meeting_offered, meeting_details fields |
| `backend/database/models/pos.py` | Add `structured_output` JSONB column to POSAIQAMessage |
| `backend/services/event_subscribers.py` | Register 4 new event handlers |
| `backend/agents/tools/__init__.py` | Import borrower_application module |
| `backend/agents/tool_integration.py` | Add borrower_application_agent AgentToolConfig |
| `frontend/src/features/pos/hooks/useAriaChat.ts` | Handle meeting_offered, meeting_details in response |
| `frontend/src/features/pos/components/AriaChatPanel.tsx` | Render calendar card and escalation banner |

---

## 9. Future Work (Not in This Build)

- **Reference files:** `urla_field_guide.md`, `document_matrix.md`, `escalation_triggers.md`, `compliance_guardrails.md`, `scenario_playbooks.md`, `conversation_examples.md` — add depth to the system prompt
- **Asset files:** `system_prompt.txt`, `tool_schemas.json`, `crm_event_schemas.json`, `escalation_response_templates.md` — deployable artifacts for platform integration
- **Agent config in tool_integration.py:** Already added for registry visibility, but routing is direct (not through orchestrator)
- **Voice mode:** Aria voice agent using same BorrowerApplicationAgent with condensed responses
- **Borrower re-engagement:** Automated follow-up when APPLICATION_STALL fires and no meeting is booked within 24h
