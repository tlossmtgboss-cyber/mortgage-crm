# Borrower Application Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the POS AI Q&A `GuidelinesChatAgent` with a purpose-built `BorrowerApplicationAgent` that helps borrowers complete their 1003, answers appraisal/title questions with real-time loan data, detects risk, escalates to LO calls via Smart Calendar, emits CRM events, and enforces compliance.

**Architecture:** Standalone agent service called by `AIQAService.ask()`. Claude Sonnet with tool-use (8 tools). Structured JSON output on every turn. CRM event handlers translate agent events into Activities, Tasks, and ClientFile records. Same endpoint, same PURL auth — borrower experience is seamless.

**Tech Stack:** FastAPI, Anthropic SDK (Claude Sonnet), SQLAlchemy 2.0, PostgreSQL, existing `@mortgage_tool` decorator, `EventBus`, `AppointmentService`

---

## File Map

| File | Responsibility |
|---|---|
| **Create:** `backend/agents/tools/borrower_application.py` | 8 `@mortgage_tool` tools for the agent |
| **Create:** `backend/services/pos/borrower_application_agent.py` | Agent class — prompt building, Claude call, tool dispatch |
| **Create:** `backend/agents/perennia-prompts/core/borrower_application_agent.txt` | System prompt (~3,700 tokens) |
| **Create:** `backend/services/pos/borrower_agent_event_handlers.py` | CRM event subscribers (4 handlers) |
| **Create:** `backend/tests/test_borrower_application_agent.py` | Unit tests |
| **Create:** `backend/tests/test_borrower_agent_integration.py` | Integration tests |
| **Modify:** `backend/services/pos/ai_qa_service.py` | Swap `GuidelinesChatAgent` → `BorrowerApplicationAgent` |
| **Modify:** `backend/schemas/pos/ai_qa.py` | Add `structured_output`, `meeting_offered`, `meeting_details` |
| **Modify:** `backend/database/models/pos.py` | Add `structured_output` JSONB column to `POSAIQAMessage` |
| **Modify:** `backend/services/event_bus.py` | Add 4 new `EventType` entries |
| **Modify:** `backend/services/event_subscribers.py` | Register borrower agent event handlers |
| **Modify:** `backend/database/models/__init__.py` | No changes needed (POS models already imported) |

---

### Task 1: Add EventType Entries for Borrower Agent Events

**Files:**
- Modify: `backend/services/event_bus.py:80-83`

- [ ] **Step 1: Add 4 new event types to EventType enum**

Open `backend/services/event_bus.py`. After the existing POS event types (line ~82), add:

```python
    # Borrower Application Agent events
    APPLICATION_ESCALATION = "borrower_agent.escalation"
    MEETING_BOOKED = "borrower_agent.meeting_booked"
    DOCUMENT_SUGGESTED = "borrower_agent.document_suggested"
    APPLICATION_STALL = "borrower_agent.application_stall"
```

- [ ] **Step 2: Verify syntax**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from services.event_bus import EventType; print(EventType.APPLICATION_ESCALATION.value)"`

Expected: `borrower_agent.escalation`

- [ ] **Step 3: Commit**

```bash
git add backend/services/event_bus.py
git commit -m "feat(aria): add borrower agent event types to EventBus"
```

---

### Task 2: Add `structured_output` Column to POSAIQAMessage

**Files:**
- Modify: `backend/database/models/pos.py`

- [ ] **Step 1: Add the JSONB column to the POSAIQAMessage model**

Find the `POSAIQAMessage` class in `backend/database/models/pos.py`. It should have columns like `content`, `sources`, `follow_ups`, `confidence`, etc. Add after the `confidence` column:

```python
    structured_output = Column(JSONB, nullable=True)
```

- [ ] **Step 2: Create inline migration for the new column**

The project uses inline migrations (no Alembic). Add to `backend/database/init_db.py` in the migration section where other `ALTER TABLE ADD COLUMN` statements live:

```python
    # POSAIQAMessage — structured_output column (borrower agent)
    try:
        conn.execute(text(
            "ALTER TABLE pos_ai_qa_messages ADD COLUMN IF NOT EXISTS "
            "structured_output JSONB"
        ))
        logger.info("Added structured_output column to pos_ai_qa_messages")
    except Exception as e:
        logger.debug("structured_output column migration: %s", e)
```

- [ ] **Step 3: Verify model loads**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from database.models.pos import POSAIQAMessage; print(hasattr(POSAIQAMessage, 'structured_output'))"`

Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add backend/database/models/pos.py backend/database/init_db.py
git commit -m "feat(pos): add structured_output JSONB column to POSAIQAMessage"
```

---

### Task 3: Update AskResponse Schema

**Files:**
- Modify: `backend/schemas/pos/ai_qa.py`

- [ ] **Step 1: Add structured_output, meeting_offered, meeting_details to AskResponse**

In `backend/schemas/pos/ai_qa.py`, add these fields to the `AskResponse` class (after `escalation_reason`):

```python
    structured_output: dict | None = Field(
        default=None,
        description="Structured JSON output from the agent (intent, risk level, flags, etc.)",
    )
    meeting_offered: bool = Field(
        default=False,
        description="True if the agent offered a meeting with the LO this turn.",
    )
    meeting_details: dict | None = Field(
        default=None,
        description="Calendar slot time, LO name, and confirmation when a meeting is booked.",
    )
```

- [ ] **Step 2: Verify schema compiles**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from schemas.pos.ai_qa import AskResponse; print(AskResponse.model_fields.keys())"`

Expected: Should include `structured_output`, `meeting_offered`, `meeting_details` in the keys.

- [ ] **Step 3: Commit**

```bash
git add backend/schemas/pos/ai_qa.py
git commit -m "feat(pos): add structured_output and meeting fields to AskResponse schema"
```

---

### Task 4: Write the System Prompt

**Files:**
- Create: `backend/agents/perennia-prompts/core/borrower_application_agent.txt`

- [ ] **Step 1: Create the prompts directory if needed**

Run: `mkdir -p /Users/timothyloss/my-project/mortgage-crm/backend/agents/perennia-prompts/core`

- [ ] **Step 2: Write the system prompt**

Create `backend/agents/perennia-prompts/core/borrower_application_agent.txt`:

```text
You are Aria, the AI assistant built into the Perennia borrower portal. You help borrowers complete their URLA 1003 mortgage application.

## The One Rule
NEVER say: "you qualify," "you're approved," "you're denied," "your rate will be," or any language implying a lending decision. You are NOT the decision-maker. When asked: "That's a great question for your loan officer — let me see if we can get you connected."

## How You Help
When a borrower asks about a field on their application:
1. **What it means** — plain-English explanation, no jargon
2. **Why it matters** — how it affects their application
3. **How to answer** — what to enter, with examples
4. **What may be needed** — documents that support this section
5. **When to ask your loan team** — flag complex scenarios

Keep answers 4-8 sentences. Be clear, confident, and non-judgmental.

## URLA Sections You Know

**Personal:** Legal name, SSN, DOB, citizenship, marital status, dependents, contact info. SSN is encrypted — you never see or reference it. Marital status affects community property states.

**Residence:** Current and prior addresses (2-year history required). Rent vs own, monthly payment, landlord info for renters. Gaps in housing history need explanation.

**Employment:** Current and prior employers (2-year history). Self-employed borrowers need 2 years of tax returns + P&L. Employment gaps need LOE. Hourly vs salary affects income calculation.

**Assets:** Checking, savings, retirement, investments, gifts. Gift funds require a gift letter (donor name, relationship, amount, statement that repayment is not expected). Large deposits (>50% of monthly income) need sourcing documentation.

**Liabilities:** Monthly debts — auto loans, student loans, credit cards, child support, alimony. Alimony/child support disclosure is VOLUNTARY (ECOA/Reg B) — never pressure. Liabilities affect DTI ratio.

**REO (Real Estate Owned):** Properties currently owned. Rental income needs lease agreements. Investment properties have different occupancy/DTI rules.

**Loan Details:** Loan purpose (purchase/refinance/construction), property type, occupancy (primary/second/investment), loan amount, down payment. Purchase price vs appraised value drives LTV.

**Declarations:** Legal questions (judgments, bankruptcy, foreclosure, lawsuits, delinquencies, alimony obligation, co-signing, citizenship, occupancy intent). Answer YES triggers escalation to LO.

**Review:** Final review before submission. Summarize what's complete, what's missing, and what needs attention.

## Appraisal & Title Knowledge

**Appraisal:** Ordered by lender after application. Types: full (interior + exterior), drive-by, desktop, hybrid. Timeline: typically 1-3 weeks. Borrower pays via appraisal fee at closing (or upfront if lender requires). If value comes in low: renegotiate price, bring more cash, contest with comps, or walk away. Use `get_loan_status` to check appraisal dates.

**Title:** Title search confirms ownership and uncovers liens, easements, encumbrances. Title insurance: lender's policy (required) protects the lender; owner's policy (optional, recommended) protects the buyer. Common defects: unknown liens, recording errors, undisclosed heirs, forgery. Title company handles closing/settlement in most states.

When borrower asks about appraisal/title status, call `get_loan_status` for real dates, then explain in plain language. Never speculate on outcomes — escalate judgment calls.

## Compliance Guardrails

**ECOA / Reg B:** Alimony, child support, and separate maintenance income disclosure is VOLUNTARY. Never ask "Do you receive alimony?" — instead: "If you have any additional income sources you'd like to include, you can add them here." Flag: `ECOA_VOLUNTARY_INCOME`

**TCPA:** Never initiate calls or texts to the borrower from this agent. Communication is in-portal only.

**RESPA Section 8:** Never recommend specific service providers (title companies, insurance, inspectors). "Your loan officer can discuss provider options with you."

**HMDA:** Demographic questions (race, ethnicity, sex) are optional. "This information is collected for federal monitoring purposes and does not affect your application."

**Fair Housing:** Never reference protected classes. Never suggest a borrower might not qualify based on demographic information.

**Compliance flag codes:** ECOA_VOLUNTARY_INCOME, RESPA_PROVIDER_REQUEST, HMDA_OPTIONAL_DEMOGRAPHIC, DECLARATION_YES_TRIGGER, TRID_FEE_QUESTION

## Escalation Triggers

**Hard triggers** (always escalate, always offer meeting):
- Bankruptcy (any chapter, any timeframe)
- Foreclosure or short sale history
- Self-employment income (complex calculation)
- Gift funds over $5,000
- Divorce affecting title or income
- Foreign income or foreign national status
- Trust or LLC ownership
- Power of attorney involvement
- Declaration section: any YES answer
- Identity or fraud concerns

**Soft triggers** (flag, offer meeting if repeated):
- Same question asked 3+ times
- "I'm confused" / "I don't understand"
- Questions about fees, rates, or closing costs (TRID territory)
- Mentions of other lenders or rate shopping

**Power conversion line** (use when escalating): "Your loan officer is the best person to walk you through this. Want me to find a time for a quick call? It usually takes about 15 minutes and they can answer everything."

## Document Guidance

Common documents by scenario:
- **All borrowers:** Government ID, pay stubs (30 days), W-2s (2 years), bank statements (2 months)
- **Self-employed:** Tax returns (2 years), P&L (YTD), business license
- **Gift funds:** Gift letter, donor bank statement, borrower deposit receipt
- **Rental income:** Lease agreements, tax returns showing Schedule E
- **Divorce:** Divorce decree, property settlement agreement
- **Retirement:** Award letter, 1099-R, pension statement

Never guarantee the document list is exhaustive — "Your loan officer may request additional documents based on your specific situation."

## Tone

- Clear and confident, never condescending
- Non-judgmental about financial situations
- Encouraging: "You're making great progress" / "That's a common question"
- Honest about what you can and can't answer
- Never rush — the borrower sets the pace

Phrases to use: "Great question," "Here's what that means," "Your loan officer can help with the details"
Phrases to avoid: "Unfortunately," "You have to," "You must," "I'm just an AI," "I can't help with that"

## Structured Output

Every response MUST end with a JSON block wrapped in ```json fences:

{
  "borrower_question": "<verbatim input>",
  "application_section": "<section_key or null>",
  "field_name": "<field_name or null>",
  "intent": "explain_field | doc_guidance | escalation | scheduling | reassurance | smalltalk | out_of_scope",
  "risk_level": "low | medium | high",
  "documents_suggested": ["<doc_type>"],
  "escalate_to_human": true | false,
  "meeting_offered": true | false,
  "compliance_flags": ["<flag_code>"],
  "next_best_action": "<short directive>"
}
```

- [ ] **Step 3: Verify file exists**

Run: `wc -l /Users/timothyloss/my-project/mortgage-crm/backend/agents/perennia-prompts/core/borrower_application_agent.txt`

Expected: approximately 100-120 lines

- [ ] **Step 4: Commit**

```bash
git add backend/agents/perennia-prompts/core/borrower_application_agent.txt
git commit -m "feat(aria): add borrower application agent system prompt"
```

---

### Task 5: Write the @mortgage_tool Tools

**Files:**
- Create: `backend/agents/tools/borrower_application.py`

- [ ] **Step 1: Write all 8 tools**

Create `backend/agents/tools/borrower_application.py`:

```python
"""
Borrower Application Agent Tools

8 @mortgage_tool tools for the borrower-facing AI assistant.
All tools are scoped to a single borrower's application via organization_id.
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from agents.tools.base import mortgage_tool, get_db, execute_query, execute_single

logger = logging.getLogger(__name__)


@mortgage_tool(
    name="get_application_state",
    description="Fetch the borrower's in-progress URLA application sections, completion percentage, and current step",
    agent_roles=["borrower_application_agent"],
)
def get_application_state(application_id: str, organization_id: int) -> Dict[str, Any]:
    db = get_db()
    try:
        app_row = execute_single(
            db,
            "SELECT id, status, current_step, completion_pct, created_at, updated_at "
            "FROM pos_applications WHERE id = :app_id AND organization_id = :org_id",
            {"app_id": application_id, "org_id": organization_id},
        )
        if not app_row:
            return {"error": "Application not found"}

        sections = execute_query(
            db,
            "SELECT section_key, is_complete, data, updated_at "
            "FROM pos_application_sections WHERE application_id = :app_id "
            "ORDER BY section_key",
            {"app_id": application_id},
        )

        section_summaries = {}
        for s in sections:
            data = s[2] or {}
            field_count = len([v for v in data.values() if v is not None and v != ""])
            section_summaries[s[0]] = {
                "is_complete": s[1],
                "fields_filled": field_count,
                "last_updated": s[3].isoformat() if s[3] else None,
            }

        return {
            "application_id": str(app_row[0]),
            "status": app_row[1],
            "current_step": app_row[2],
            "completion_pct": app_row[3],
            "created_at": app_row[4].isoformat() if app_row[4] else None,
            "sections": section_summaries,
        }
    finally:
        db.close()


@mortgage_tool(
    name="get_loan_status",
    description="Pull real-time loan milestones: stage, appraisal status, title status, closing date, conditions",
    agent_roles=["borrower_application_agent"],
)
def get_loan_status(loan_id: int, organization_id: int) -> Dict[str, Any]:
    db = get_db()
    try:
        row = execute_single(
            db,
            "SELECT id, stage, loan_type, loan_amount, purchase_price, "
            "property_address, closing_date, appraisal_ordered_date, "
            "appraisal_received_date, appraisal_value, "
            "title_ordered_date, title_received_date, title_company, "
            "updated_at "
            "FROM loans WHERE id = :loan_id AND organization_id = :org_id",
            {"loan_id": loan_id, "org_id": organization_id},
        )
        if not row:
            return {"error": "Loan not found"}

        conditions = execute_query(
            db,
            "SELECT status, COUNT(*) FROM loan_conditions "
            "WHERE loan_id = :loan_id GROUP BY status",
            {"loan_id": loan_id},
        )
        condition_summary = {r[0]: r[1] for r in conditions} if conditions else {}

        return {
            "loan_id": row[0],
            "stage": row[1],
            "loan_type": row[2],
            "loan_amount": float(row[3]) if row[3] else None,
            "purchase_price": float(row[4]) if row[4] else None,
            "property_address": row[5],
            "closing_date": row[6].isoformat() if row[6] else None,
            "appraisal": {
                "ordered_date": row[7].isoformat() if row[7] else None,
                "received_date": row[8].isoformat() if row[8] else None,
                "value": float(row[9]) if row[9] else None,
            },
            "title": {
                "ordered_date": row[10].isoformat() if row[10] else None,
                "received_date": row[11].isoformat() if row[11] else None,
                "company": row[12],
            },
            "conditions": condition_summary,
        }
    except Exception as e:
        logger.warning("get_loan_status query fallback (conditions table may not exist): %s", e)
        if not row:
            return {"error": "Loan not found"}
        return {
            "loan_id": row[0],
            "stage": row[1],
            "loan_type": row[2],
            "loan_amount": float(row[3]) if row[3] else None,
            "purchase_price": float(row[4]) if row[4] else None,
            "property_address": row[5],
            "closing_date": row[6].isoformat() if row[6] else None,
            "appraisal": {
                "ordered_date": row[7].isoformat() if row[7] else None,
                "received_date": row[8].isoformat() if row[8] else None,
                "value": float(row[9]) if row[9] else None,
            },
            "title": {
                "ordered_date": row[10].isoformat() if row[10] else None,
                "received_date": row[11].isoformat() if row[11] else None,
                "company": row[12],
            },
            "conditions": {},
        }
    finally:
        db.close()


@mortgage_tool(
    name="get_lo_availability",
    description="Fetch 3-5 available calendar slots for the assigned LO",
    agent_roles=["borrower_application_agent"],
)
async def get_lo_availability(
    lo_user_id: int,
    organization_id: int,
    duration_minutes: int = 30,
    days_ahead: int = 5,
) -> Dict[str, Any]:
    try:
        from services.appointment.service import AppointmentService
        from db import SessionLocal
        from datetime import date as date_type

        start = date_type.today()
        end = start + timedelta(days=days_ahead)

        db = SessionLocal()
        try:
            svc = AppointmentService(db=db, organization_id=organization_id)
            slots_raw = await svc.get_available_slots(
                lo_id=lo_user_id,
                start_date=start,
                end_date=end,
                duration_minutes=duration_minutes,
            )
            slots = []
            for slot in (slots_raw or [])[:5]:
                slots.append({
                    "start": str(slot.get("start", "")),
                    "end": str(slot.get("end", "")),
                    "date": str(slot.get("date", "")),
                    "day": slot.get("day", ""),
                })
            return {
                "lo_user_id": lo_user_id,
                "available_slots": slots,
                "slot_count": len(slots),
                "duration_minutes": duration_minutes,
            }
        finally:
            db.close()
    except Exception as e:
        logger.error("get_lo_availability failed: %s", e)
        return {"error": str(e), "available_slots": []}


@mortgage_tool(
    name="book_lo_meeting",
    description="Book a meeting with the assigned LO at a specific time slot",
    agent_roles=["borrower_application_agent"],
)
async def book_lo_meeting(
    lo_user_id: int,
    organization_id: int,
    slot_start: str,
    borrower_name: str,
    borrower_email: str = "",
    borrower_phone: str = "",
    duration_minutes: int = 30,
    topic: str = "Application review",
) -> Dict[str, Any]:
    try:
        from services.appointment.service import AppointmentService
        from services.event_bus import event_bus, Event, EventType
        from db import SessionLocal
        from dateutil import parser as dtparser

        scheduled_start = dtparser.parse(slot_start)
        db = SessionLocal()
        try:
            svc = AppointmentService(db=db, organization_id=organization_id)
            result = await svc.create_appointment(
                data={
                    "title": f"Application Review — {borrower_name}",
                    "scheduled_start": scheduled_start.isoformat(),
                    "duration_minutes": duration_minutes,
                    "assigned_user_id": lo_user_id,
                    "attendee_email": borrower_email,
                    "attendee_name": borrower_name,
                    "attendee_phone": borrower_phone,
                    "meeting_type": "consultation",
                    "meeting_mode": "phone",
                    "description": topic,
                },
                source="borrower_application_agent",
                requester_user_id=lo_user_id,
            )
            db.commit()

            appointment_id = (
                getattr(result, "appointment_id", None)
                or (result.get("appointment_id") if isinstance(result, dict) else None)
            )

            await event_bus.publish(Event(
                type=EventType.MEETING_BOOKED,
                data={
                    "appointment_id": appointment_id,
                    "lo_user_id": lo_user_id,
                    "borrower_name": borrower_name,
                    "borrower_email": borrower_email,
                    "scheduled_start": slot_start,
                    "topic": topic,
                },
                org_id=str(organization_id),
                source="borrower_application_agent",
            ))

            return {
                "booked": True,
                "appointment_id": appointment_id,
                "scheduled_start": slot_start,
                "duration_minutes": duration_minutes,
                "borrower_name": borrower_name,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        logger.error("book_lo_meeting failed: %s", e)
        return {"booked": False, "error": str(e)}


@mortgage_tool(
    name="propose_alternate_window",
    description="Widen the calendar search window if borrower wants different times",
    agent_roles=["borrower_application_agent"],
)
async def propose_alternate_window(
    lo_user_id: int,
    organization_id: int,
    start_date: str,
    end_date: str,
    duration_minutes: int = 30,
) -> Dict[str, Any]:
    try:
        from services.appointment.service import AppointmentService
        from db import SessionLocal
        from dateutil import parser as dtparser

        start = dtparser.parse(start_date).date()
        end = dtparser.parse(end_date).date()

        db = SessionLocal()
        try:
            svc = AppointmentService(db=db, organization_id=organization_id)
            slots_raw = await svc.get_available_slots(
                lo_id=lo_user_id,
                start_date=start,
                end_date=end,
                duration_minutes=duration_minutes,
            )
            slots = []
            for slot in (slots_raw or [])[:5]:
                slots.append({
                    "start": str(slot.get("start", "")),
                    "end": str(slot.get("end", "")),
                    "date": str(slot.get("date", "")),
                    "day": slot.get("day", ""),
                })
            return {"available_slots": slots, "slot_count": len(slots)}
        finally:
            db.close()
    except Exception as e:
        logger.error("propose_alternate_window failed: %s", e)
        return {"error": str(e), "available_slots": []}


@mortgage_tool(
    name="prompt_document_upload",
    description="Return a structured prompt directing the borrower to upload a specific document type",
    agent_roles=["borrower_application_agent"],
)
def prompt_document_upload(
    document_type: str,
    reason: str,
    application_id: str,
) -> Dict[str, Any]:
    doc_labels = {
        "pay_stubs": "Recent Pay Stubs (last 30 days)",
        "w2": "W-2 Forms (last 2 years)",
        "tax_returns": "Federal Tax Returns (last 2 years)",
        "bank_statements": "Bank Statements (last 2 months)",
        "gift_letter": "Gift Letter",
        "lease_agreement": "Lease Agreement(s)",
        "divorce_decree": "Divorce Decree / Property Settlement",
        "government_id": "Government-Issued Photo ID",
        "profit_loss": "Year-to-Date Profit & Loss Statement",
        "business_license": "Business License",
        "award_letter": "Pension/Social Security Award Letter",
    }
    label = doc_labels.get(document_type, document_type.replace("_", " ").title())

    return {
        "action": "prompt_upload",
        "document_type": document_type,
        "label": label,
        "reason": reason,
        "upload_url": f"/portal/documents/upload?app={application_id}&type={document_type}",
    }


@mortgage_tool(
    name="emit_crm_event",
    description="Publish APPLICATION_ESCALATION, DOCUMENT_SUGGESTED, or APPLICATION_STALL events to the CRM event bus",
    agent_roles=["borrower_application_agent"],
)
async def emit_crm_event(
    event_type: str,
    organization_id: int,
    application_id: str,
    contact_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    from services.event_bus import event_bus, Event, EventType

    type_map = {
        "APPLICATION_ESCALATION": EventType.APPLICATION_ESCALATION,
        "DOCUMENT_SUGGESTED": EventType.DOCUMENT_SUGGESTED,
        "APPLICATION_STALL": EventType.APPLICATION_STALL,
    }
    resolved_type = type_map.get(event_type)
    if not resolved_type:
        return {"error": f"Unknown event type: {event_type}"}

    await event_bus.publish(Event(
        type=resolved_type,
        data={
            "application_id": application_id,
            "contact_id": contact_id,
            **data,
        },
        org_id=str(organization_id),
        source="borrower_application_agent",
    ))

    return {"published": True, "event_type": event_type}


@mortgage_tool(
    name="recall_borrower_context",
    description="Query prior conversation history and borrower profile for cross-session continuity",
    agent_roles=["borrower_application_agent"],
)
def recall_borrower_context(
    application_id: str,
    organization_id: int,
    limit: int = 10,
) -> Dict[str, Any]:
    db = get_db()
    try:
        messages = execute_query(
            db,
            "SELECT role, content, confidence, created_at "
            "FROM pos_ai_qa_messages WHERE application_id = :app_id "
            "ORDER BY created_at DESC LIMIT :lim",
            {"app_id": application_id, "lim": limit},
        )
        history = []
        for m in reversed(messages or []):
            history.append({
                "role": m[0],
                "content": m[1][:500],
                "confidence": m[2],
                "created_at": m[3].isoformat() if m[3] else None,
            })
        return {"message_count": len(history), "history": history}
    finally:
        db.close()
```

- [ ] **Step 2: Verify tools load**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from agents.tools.borrower_application import get_application_state; print(get_application_state.name)"`

Expected: `get_application_state`

- [ ] **Step 3: Commit**

```bash
git add backend/agents/tools/borrower_application.py
git commit -m "feat(aria): add 8 @mortgage_tool tools for borrower application agent"
```

---

### Task 6: Write the BorrowerApplicationAgent Service

**Files:**
- Create: `backend/services/pos/borrower_application_agent.py`

- [ ] **Step 1: Write the agent class**

Create `backend/services/pos/borrower_application_agent.py`:

```python
"""
BorrowerApplicationAgent — the borrower-facing AI assistant.

Replaces GuidelinesChatAgent. Uses Claude Sonnet with tool-use to help
borrowers complete their 1003, answer appraisal/title questions, detect
risk, and escalate to LO calls via Smart Calendar.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / (
    "agents/perennia-prompts/core/borrower_application_agent.txt"
)

TOOL_DEFINITIONS = [
    {
        "name": "get_lo_availability",
        "description": "Fetch 3-5 available calendar slots for the assigned LO. Call when the borrower wants to schedule a call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lo_user_id": {"type": "integer", "description": "The assigned loan officer's user ID"},
                "organization_id": {"type": "integer"},
                "duration_minutes": {"type": "integer", "default": 30},
                "days_ahead": {"type": "integer", "default": 5},
            },
            "required": ["lo_user_id", "organization_id"],
        },
    },
    {
        "name": "book_lo_meeting",
        "description": "Book a meeting with the assigned LO at a specific time slot the borrower chose.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lo_user_id": {"type": "integer"},
                "organization_id": {"type": "integer"},
                "slot_start": {"type": "string", "description": "ISO datetime of the chosen slot"},
                "borrower_name": {"type": "string"},
                "borrower_email": {"type": "string"},
                "borrower_phone": {"type": "string"},
                "duration_minutes": {"type": "integer", "default": 30},
                "topic": {"type": "string", "default": "Application review"},
            },
            "required": ["lo_user_id", "organization_id", "slot_start", "borrower_name"],
        },
    },
    {
        "name": "propose_alternate_window",
        "description": "Search for calendar slots in a different date range if the borrower wants different times.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lo_user_id": {"type": "integer"},
                "organization_id": {"type": "integer"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "duration_minutes": {"type": "integer", "default": 30},
            },
            "required": ["lo_user_id", "organization_id", "start_date", "end_date"],
        },
    },
    {
        "name": "prompt_document_upload",
        "description": "Direct the borrower to upload a specific document. Returns a structured upload prompt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_type": {"type": "string", "description": "e.g. pay_stubs, w2, tax_returns, bank_statements, gift_letter"},
                "reason": {"type": "string", "description": "Why this document is needed"},
                "application_id": {"type": "string"},
            },
            "required": ["document_type", "reason", "application_id"],
        },
    },
    {
        "name": "emit_crm_event",
        "description": "Publish a CRM event (APPLICATION_ESCALATION, DOCUMENT_SUGGESTED, APPLICATION_STALL).",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_type": {"type": "string", "enum": ["APPLICATION_ESCALATION", "DOCUMENT_SUGGESTED", "APPLICATION_STALL"]},
                "organization_id": {"type": "integer"},
                "application_id": {"type": "string"},
                "contact_id": {"type": "integer"},
                "data": {"type": "object", "description": "Event payload (trigger, section, details)"},
            },
            "required": ["event_type", "organization_id", "application_id", "contact_id", "data"],
        },
    },
    {
        "name": "recall_borrower_context",
        "description": "Retrieve prior conversation history for this application (cross-session continuity).",
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string"},
                "organization_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["application_id", "organization_id"],
        },
    },
]


class BorrowerApplicationAgent:
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        )
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        try:
            return PROMPT_PATH.read_text()
        except FileNotFoundError:
            logger.warning("System prompt not found at %s — using fallback", PROMPT_PATH)
            return "You are Aria, the AI assistant in the Perennia borrower portal. Help borrowers complete their mortgage application."

    async def answer(
        self,
        *,
        question: str,
        loan_context: dict[str, Any],
        history: list[dict[str, Any]],
        current_step: str | None = None,
        organization_id: int | None = None,
        contact_id: int | None = None,
        application_id: str | None = None,
    ) -> dict[str, Any]:
        messages = self._build_messages(question, loan_context, history, current_step)

        response = await self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            temperature=0.2,
            system=self._system_prompt,
            messages=messages,
            tools=TOOL_DEFINITIONS,
        )

        tool_results = await self._process_tool_calls(
            response, organization_id, contact_id, application_id
        )

        if tool_results:
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            response = await self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                temperature=0.2,
                system=self._system_prompt,
                messages=messages,
                tools=TOOL_DEFINITIONS,
            )

        return self._parse_response(response)

    def _build_messages(
        self,
        question: str,
        loan_context: dict[str, Any],
        history: list[dict[str, Any]],
        current_step: str | None,
    ) -> list[dict[str, Any]]:
        context_block = f"""<application_context>
Current step: {current_step or 'unknown'}
Completion: {loan_context.get('completion_pct', 0)}%
Sections: {json.dumps(loan_context.get('sections', {}), indent=2)}
Loan: {json.dumps(loan_context.get('loan', {}), indent=2)}
PII flags: {json.dumps(loan_context.get('presence_flags', {}), indent=2)}
</application_context>"""

        messages = []
        messages.append({
            "role": "user",
            "content": f"[CONTEXT — do not repeat to borrower]\n{context_block}",
        })
        messages.append({
            "role": "assistant",
            "content": "Understood. I have the application context loaded. Ready to help the borrower.",
        })

        for turn in history:
            role = "user" if turn["role"] == "borrower" else "assistant"
            messages.append({"role": role, "content": turn["content"]})

        messages.append({"role": "user", "content": question})
        return messages

    async def _process_tool_calls(
        self,
        response,
        organization_id: int | None,
        contact_id: int | None,
        application_id: str | None,
    ) -> list[dict[str, Any]] | None:
        tool_use_blocks = [
            block for block in response.content
            if block.type == "tool_use"
        ]
        if not tool_use_blocks:
            return None

        results = []
        for block in tool_use_blocks:
            result = await self._execute_tool(
                block.name, block.input,
                organization_id, contact_id, application_id,
            )
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })
        return results

    async def _execute_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        organization_id: int | None,
        contact_id: int | None,
        application_id: str | None,
    ) -> dict[str, Any]:
        import asyncio
        from agents.tools import borrower_application as tools

        tool_input.setdefault("organization_id", organization_id)
        if "application_id" in tool_input or tool_name in ("prompt_document_upload", "emit_crm_event", "recall_borrower_context"):
            tool_input.setdefault("application_id", application_id)
        if "contact_id" in tool_input or tool_name == "emit_crm_event":
            tool_input.setdefault("contact_id", contact_id)

        tool_fn = getattr(tools, tool_name, None)
        if tool_fn is None:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            if asyncio.iscoroutinefunction(tool_fn):
                return await tool_fn(**tool_input)
            else:
                return await asyncio.to_thread(tool_fn, **tool_input)
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e, exc_info=True)
            return {"error": str(e)}

    def _parse_response(self, response) -> dict[str, Any]:
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]
        full_text = "\n".join(text_blocks)

        structured_output = self._extract_structured_output(full_text)
        content = self._strip_json_block(full_text)

        escalation_reason = None
        if structured_output and structured_output.get("escalate_to_human"):
            escalation_reason = structured_output.get("next_best_action", "Escalation triggered")

        follow_ups = []
        if structured_output:
            intent = structured_output.get("intent", "")
            if intent == "explain_field":
                section = structured_output.get("application_section", "")
                follow_ups = [
                    f"What documents do I need for {section}?",
                    "Can I talk to my loan officer about this?",
                ]
            elif intent == "doc_guidance":
                follow_ups = [
                    "Where do I upload documents?",
                    "What else do I need to provide?",
                ]
            elif intent == "escalation":
                follow_ups = [
                    "When is my loan officer available?",
                    "Can I schedule a call?",
                ]

        meeting_offered = bool(structured_output and structured_output.get("meeting_offered"))

        return {
            "content": content,
            "sources": [],
            "follow_ups": follow_ups[:3],
            "tokens_used": response.usage.output_tokens if response.usage else None,
            "escalation_reason": escalation_reason,
            "structured_output": structured_output,
            "meeting_offered": meeting_offered,
        }

    @staticmethod
    def _extract_structured_output(text: str) -> dict[str, Any] | None:
        pattern = r"```json\s*(\{.*?\})\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                logger.warning("Failed to parse structured output JSON")
        return None

    @staticmethod
    def _strip_json_block(text: str) -> str:
        return re.sub(r"```json\s*\{.*?\}\s*```", "", text, flags=re.DOTALL).strip()
```

- [ ] **Step 2: Verify agent loads**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from services.pos.borrower_application_agent import BorrowerApplicationAgent; print('Agent loaded')"`

Expected: `Agent loaded`

- [ ] **Step 3: Commit**

```bash
git add backend/services/pos/borrower_application_agent.py
git commit -m "feat(aria): add BorrowerApplicationAgent service with Claude tool-use"
```

---

### Task 7: Write CRM Event Handlers

**Files:**
- Create: `backend/services/pos/borrower_agent_event_handlers.py`

- [ ] **Step 1: Write the 4 event handlers**

Create `backend/services/pos/borrower_agent_event_handlers.py`:

```python
"""
CRM event subscribers for BorrowerApplicationAgent events.

Translates agent events into CRM records:
- APPLICATION_ESCALATION → Activity + Task + ensure ClientFile
- MEETING_BOOKED → Activity + Task + LO notification
- DOCUMENT_SUGGESTED → Activity on Lead
- APPLICATION_STALL → Task for LO + nurture workflow trigger
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.event_bus import Event

logger = logging.getLogger(__name__)


async def on_application_escalation(event: Event) -> None:
    data = event.data
    contact_id = data.get("contact_id")
    application_id = data.get("application_id")
    trigger = data.get("trigger", "unknown")
    org_id = event.org_id

    if not contact_id:
        logger.warning("on_application_escalation: missing contact_id")
        return

    try:
        from db import SessionLocal
        from database.models.lead_loan import Lead
        from database.models.task import Task
        from database.models.communication import Activity
        from database.enums import ActivityType
        from database.models.client_file import ClientFile

        session = SessionLocal()
        try:
            lead = session.query(Lead).filter(Lead.id == int(contact_id)).first()
            if not lead:
                logger.warning("Escalation: Lead %s not found", contact_id)
                return

            activity = Activity(
                organization_id=int(org_id) if org_id else lead.organization_id,
                lead_id=lead.id,
                type=ActivityType.NOTE,
                content=f"Borrower application agent escalation: {trigger}",
                user_metadata={
                    "source": "borrower_application_agent",
                    "application_id": application_id,
                    "trigger": trigger,
                    "event_type": event.type.value,
                },
            )
            session.add(activity)

            task = Task(
                title=f"Review escalation: {trigger}",
                description=(
                    f"The borrower application agent escalated for: {trigger}. "
                    f"Application: {application_id}. Review and follow up."
                ),
                status="pending",
                priority="high",
                owner_id=lead.owner_id,
                lead_id=lead.id,
                organization_id=int(org_id) if org_id else lead.organization_id,
                related_type="borrower_agent_escalation",
                due_date=datetime.now(timezone.utc),
            )
            session.add(task)

            existing_cf = (
                session.query(ClientFile)
                .filter(ClientFile.lead_id == lead.id)
                .first()
            )
            if not existing_cf:
                cf = ClientFile(
                    lead_id=lead.id,
                    organization_id=int(org_id) if org_id else lead.organization_id,
                    created_by_user_id=lead.owner_id,
                )
                session.add(cf)
                logger.info("Created ClientFile for lead %s via escalation", lead.id)
            else:
                existing_cf.last_contact_at = datetime.now(timezone.utc)

            session.commit()
            logger.info("Escalation processed: lead=%s trigger=%s", contact_id, trigger)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except ImportError:
        logger.debug("DB models not available — skipping escalation handler")
    except Exception as e:
        logger.error("on_application_escalation failed: %s", e, exc_info=True)
        raise


async def on_meeting_booked(event: Event) -> None:
    data = event.data
    appointment_id = data.get("appointment_id")
    lo_user_id = data.get("lo_user_id")
    borrower_name = data.get("borrower_name", "Borrower")
    org_id = event.org_id

    if not appointment_id or not lo_user_id:
        return

    try:
        from db import SessionLocal
        from database.models.task import Task
        from database.models.communication import Activity
        from database.enums import ActivityType

        session = SessionLocal()
        try:
            activity = Activity(
                organization_id=int(org_id) if org_id else None,
                type=ActivityType.NOTE,
                content=(
                    f"Borrower {borrower_name} booked application review meeting "
                    f"(appointment #{appointment_id}) via Aria."
                ),
                user_metadata={
                    "source": "borrower_application_agent",
                    "appointment_id": appointment_id,
                    "event_type": event.type.value,
                },
            )
            session.add(activity)

            task = Task(
                title=f"Prepare for application review — {borrower_name}",
                description=(
                    f"{borrower_name} booked an application review meeting "
                    f"(appointment #{appointment_id}) through the borrower portal. "
                    f"Review their application before the call."
                ),
                status="pending",
                priority="medium",
                owner_id=int(lo_user_id),
                organization_id=int(org_id) if org_id else None,
                related_type="borrower_agent_meeting",
                due_date=datetime.now(timezone.utc),
            )
            session.add(task)
            session.commit()
            logger.info("Meeting booked handler: appointment=%s", appointment_id)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except ImportError:
        logger.debug("DB models not available — skipping meeting booked handler")
    except Exception as e:
        logger.error("on_meeting_booked failed: %s", e, exc_info=True)
        raise


async def on_document_suggested(event: Event) -> None:
    data = event.data
    contact_id = data.get("contact_id")
    documents = data.get("documents", [])
    reason = data.get("reason", "")
    org_id = event.org_id

    if not contact_id:
        return

    try:
        from db import SessionLocal
        from database.models.communication import Activity
        from database.enums import ActivityType

        session = SessionLocal()
        try:
            activity = Activity(
                organization_id=int(org_id) if org_id else None,
                lead_id=int(contact_id),
                type=ActivityType.NOTE,
                content=(
                    f"Aria suggested documents to borrower: {', '.join(documents)}. "
                    f"Reason: {reason}"
                ),
                user_metadata={
                    "source": "borrower_application_agent",
                    "documents": documents,
                    "reason": reason,
                    "event_type": event.type.value,
                },
            )
            session.add(activity)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except ImportError:
        logger.debug("DB models not available — skipping document suggested handler")
    except Exception as e:
        logger.error("on_document_suggested failed: %s", e, exc_info=True)
        raise


async def on_application_stall(event: Event) -> None:
    data = event.data
    contact_id = data.get("contact_id")
    application_id = data.get("application_id")
    section = data.get("section", "unknown")
    org_id = event.org_id

    if not contact_id:
        return

    try:
        from db import SessionLocal
        from database.models.lead_loan import Lead
        from database.models.task import Task

        session = SessionLocal()
        try:
            lead = session.query(Lead).filter(Lead.id == int(contact_id)).first()
            if not lead:
                return

            task = Task(
                title=f"Borrower stalled on {section}",
                description=(
                    f"The borrower's application ({application_id}) appears stalled "
                    f"on the {section} section. Consider reaching out to offer help."
                ),
                status="pending",
                priority="medium",
                owner_id=lead.owner_id,
                lead_id=lead.id,
                organization_id=int(org_id) if org_id else lead.organization_id,
                related_type="borrower_agent_stall",
                due_date=datetime.now(timezone.utc),
            )
            session.add(task)
            session.commit()
            logger.info("Stall task created: lead=%s section=%s", contact_id, section)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except ImportError:
        logger.debug("DB models not available — skipping stall handler")
    except Exception as e:
        logger.error("on_application_stall failed: %s", e, exc_info=True)
        raise
```

- [ ] **Step 2: Verify handlers load**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from services.pos.borrower_agent_event_handlers import on_application_escalation; print('Handlers loaded')"`

Expected: `Handlers loaded`

- [ ] **Step 3: Commit**

```bash
git add backend/services/pos/borrower_agent_event_handlers.py
git commit -m "feat(aria): add CRM event handlers for borrower application agent"
```

---

### Task 8: Register Event Handlers in event_subscribers.py

**Files:**
- Modify: `backend/services/event_subscribers.py:881-931`

- [ ] **Step 1: Add import and registration for borrower agent handlers**

In `backend/services/event_subscribers.py`, inside `register_all_subscribers()`, after the POS appointment handlers (line ~930), add:

```python
    # -- borrower_agent.escalation --
    try:
        from services.pos.borrower_agent_event_handlers import (
            on_application_escalation,
            on_meeting_booked,
            on_document_suggested,
            on_application_stall,
        )
        event_bus.subscribe(EventType.APPLICATION_ESCALATION, on_application_escalation)
        event_bus.subscribe(EventType.MEETING_BOOKED, on_meeting_booked)
        event_bus.subscribe(EventType.DOCUMENT_SUGGESTED, on_document_suggested)
        event_bus.subscribe(EventType.APPLICATION_STALL, on_application_stall)
    except ImportError:
        logger.debug("Borrower agent event handlers not available — skipping")
```

- [ ] **Step 2: Verify registration compiles**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from services.event_subscribers import register_all_subscribers; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/services/event_subscribers.py
git commit -m "feat(aria): register borrower agent event handlers in event_subscribers"
```

---

### Task 9: Swap AIQAService to Use BorrowerApplicationAgent

**Files:**
- Modify: `backend/services/pos/ai_qa_service.py`

- [ ] **Step 1: Replace _resolve_guidelines_agent and update ask()**

In `backend/services/pos/ai_qa_service.py`, make these changes:

1. Replace the `_resolve_guidelines_agent` function at the bottom of the file with:

```python
def _resolve_guidelines_agent() -> Any | None:
    try:
        from services.pos.borrower_application_agent import BorrowerApplicationAgent
        return BorrowerApplicationAgent()
    except Exception as e:
        logger.warning("Could not load BorrowerApplicationAgent: %s", e)
        return None
```

2. Update the `_call_guidelines_agent` method to pass extra context:

Replace the existing `_call_guidelines_agent` method with:

```python
    async def _call_guidelines_agent(
        self,
        *,
        question: str,
        loan_context: dict[str, Any],
        history: list[dict[str, Any]],
        current_step: str | None,
        organization_id: int | None = None,
        contact_id: int | None = None,
        application_id: str | None = None,
    ) -> dict[str, Any]:
        if self._guidelines_agent is None:
            logger.warning("BorrowerApplicationAgent unavailable; returning deflection")
            return _deflection_response(question)

        try:
            return await self._guidelines_agent.answer(
                question=question,
                loan_context=loan_context,
                history=history,
                current_step=current_step,
                organization_id=organization_id,
                contact_id=contact_id,
                application_id=application_id,
            )
        except Exception as exc:
            logger.exception("BorrowerApplicationAgent raised; deflecting: %s", exc)
            return _deflection_response(
                question,
                escalation_reason=f"Agent error: {type(exc).__name__}",
            )
```

3. Update the `ask()` method to pass `organization_id`, `contact_id`, `application_id` through to the agent call. Replace the line:

```python
        agent_response = await self._call_guidelines_agent(
            question=question,
            loan_context=loan_context,
            history=history,
            current_step=current_step,
        )
```

With:

```python
        agent_response = await self._call_guidelines_agent(
            question=question,
            loan_context=loan_context,
            history=history,
            current_step=current_step,
            organization_id=getattr(application, 'organization_id', None),
            contact_id=getattr(application, 'contact_id', None),
            application_id=str(application.id),
        )
```

4. After persisting the `aria_msg`, add structured_output persistence. After `session.add(aria_msg)` and before `session.flush()`:

```python
        aria_msg.structured_output = agent_response.get("structured_output")
```

5. Update the return dict to include new fields. Add these to the return dict:

```python
            "structured_output": agent_response.get("structured_output"),
            "meeting_offered": agent_response.get("meeting_offered", False),
            "meeting_details": agent_response.get("meeting_details"),
```

- [ ] **Step 2: Verify service compiles**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from services.pos.ai_qa_service import AIQAService; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/services/pos/ai_qa_service.py
git commit -m "feat(aria): swap AIQAService to use BorrowerApplicationAgent"
```

---

### Task 10: Update Route to Pass New Response Fields

**Files:**
- Modify: `backend/routes/pos/ai_qa.py:94-105`

- [ ] **Step 1: Add new fields to the AskResponse construction**

In `backend/routes/pos/ai_qa.py`, update the `AskResponse(...)` constructor in `ask_aria()` to include:

```python
        structured_output=result.get("structured_output"),
        meeting_offered=result.get("meeting_offered", False),
        meeting_details=result.get("meeting_details"),
```

Add these lines after `escalation_reason=result.get("escalation_reason"),`.

- [ ] **Step 2: Verify route compiles**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from routes.pos.ai_qa import router; print(len(router.routes), 'routes')"`

Expected: `2 routes`

- [ ] **Step 3: Commit**

```bash
git add backend/routes/pos/ai_qa.py
git commit -m "feat(pos): pass structured_output and meeting fields through AI QA route"
```

---

### Task 11: Write Unit Tests

**Files:**
- Create: `backend/tests/test_borrower_application_agent.py`

- [ ] **Step 1: Write unit tests for tools and structured output parsing**

Create `backend/tests/test_borrower_application_agent.py`:

```python
"""Unit tests for the BorrowerApplicationAgent and its tools."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestStructuredOutputParsing:
    def test_extracts_json_from_response(self):
        from services.pos.borrower_application_agent import BorrowerApplicationAgent

        text = (
            "Great question! The employment section asks about your work history.\n\n"
            "```json\n"
            '{"borrower_question": "what is employment", "application_section": "employment", '
            '"field_name": null, "intent": "explain_field", "risk_level": "low", '
            '"documents_suggested": ["pay_stubs", "w2"], "escalate_to_human": false, '
            '"meeting_offered": false, "compliance_flags": [], "next_best_action": "continue"}\n'
            "```"
        )
        result = BorrowerApplicationAgent._extract_structured_output(text)
        assert result is not None
        assert result["intent"] == "explain_field"
        assert result["risk_level"] == "low"
        assert "pay_stubs" in result["documents_suggested"]

    def test_strips_json_block_from_content(self):
        from services.pos.borrower_application_agent import BorrowerApplicationAgent

        text = 'Hello!\n\n```json\n{"intent": "test"}\n```'
        result = BorrowerApplicationAgent._strip_json_block(text)
        assert "```json" not in result
        assert "Hello!" in result

    def test_returns_none_for_invalid_json(self):
        from services.pos.borrower_application_agent import BorrowerApplicationAgent

        text = '```json\n{invalid json}\n```'
        result = BorrowerApplicationAgent._extract_structured_output(text)
        assert result is None

    def test_returns_none_when_no_json_block(self):
        from services.pos.borrower_application_agent import BorrowerApplicationAgent

        text = "Just a plain text response with no JSON."
        result = BorrowerApplicationAgent._extract_structured_output(text)
        assert result is None


class TestPromptDocumentUpload:
    def test_known_document_type(self):
        from agents.tools.borrower_application import prompt_document_upload

        result = prompt_document_upload(
            document_type="pay_stubs",
            reason="Needed for income verification",
            application_id="abc-123",
        )
        assert result["action"] == "prompt_upload"
        assert result["label"] == "Recent Pay Stubs (last 30 days)"
        assert "abc-123" in result["upload_url"]

    def test_unknown_document_type_uses_title_case(self):
        from agents.tools.borrower_application import prompt_document_upload

        result = prompt_document_upload(
            document_type="custom_doc",
            reason="Special request",
            application_id="xyz-456",
        )
        assert result["label"] == "Custom Doc"


class TestRecallBorrowerContext:
    @patch("agents.tools.borrower_application.get_db")
    @patch("agents.tools.borrower_application.execute_query")
    def test_returns_history(self, mock_query, mock_db):
        from agents.tools.borrower_application import recall_borrower_context
        from datetime import datetime

        mock_db.return_value = MagicMock()
        mock_query.return_value = [
            ("borrower", "What is DTI?", "high", datetime(2026, 5, 1, 12, 0)),
            ("aria", "DTI stands for...", None, datetime(2026, 5, 1, 12, 1)),
        ]

        result = recall_borrower_context(
            application_id="test-app",
            organization_id=1,
            limit=10,
        )
        assert result["message_count"] == 2
        assert result["history"][0]["role"] == "borrower"


class TestEmitCrmEvent:
    @pytest.mark.asyncio
    @patch("agents.tools.borrower_application.event_bus")
    async def test_publishes_escalation_event(self, mock_bus):
        from agents.tools.borrower_application import emit_crm_event

        mock_bus.publish = AsyncMock()

        result = await emit_crm_event(
            event_type="APPLICATION_ESCALATION",
            organization_id=1,
            application_id="app-123",
            contact_id=42,
            data={"trigger": "bankruptcy"},
        )
        assert result["published"] is True
        mock_bus.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_unknown_event_type(self):
        from agents.tools.borrower_application import emit_crm_event

        result = await emit_crm_event(
            event_type="INVALID_TYPE",
            organization_id=1,
            application_id="app-123",
            contact_id=42,
            data={},
        )
        assert "error" in result
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -m pytest tests/test_borrower_application_agent.py -v --tb=short 2>&1 | head -40`

Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_borrower_application_agent.py
git commit -m "test(aria): add unit tests for borrower application agent"
```

---

### Task 12: Verify Full Integration

- [ ] **Step 1: Run full import chain verification**

Run:
```bash
cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "
from services.event_bus import EventType
print('EventType.APPLICATION_ESCALATION:', EventType.APPLICATION_ESCALATION.value)

from schemas.pos.ai_qa import AskResponse
print('AskResponse fields:', list(AskResponse.model_fields.keys()))

from services.pos.borrower_application_agent import BorrowerApplicationAgent
agent = BorrowerApplicationAgent()
print('Agent loaded, prompt length:', len(agent._system_prompt))

from services.pos.ai_qa_service import AIQAService
svc = AIQAService()
print('AIQAService agent type:', type(svc._guidelines_agent).__name__)

from services.pos.borrower_agent_event_handlers import on_application_escalation
print('Event handlers loaded')

print('All checks passed')
"
```

Expected: All checks pass, `AIQAService agent type: BorrowerApplicationAgent`

- [ ] **Step 2: Run all tests**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -m pytest tests/test_borrower_application_agent.py -v 2>&1 | tail -20`

Expected: All tests pass
