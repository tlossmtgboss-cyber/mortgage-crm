# Aria Capability Expansion — Design Spec

**Date:** 2026-05-04
**Status:** Approved
**Approach:** Hybrid — Action mode (existing) + Query mode (new agentic) + Campaign mode (new workflow)

---

## Summary

Expand Aria from an intent-based task executor into a fully agentic AI assistant with three operating modes: Action mode for state-changing operations with confirmation, Query mode for answering any CRM question via tool-use, and Campaign mode for mass text outreach with two-way SMS calendar coordination. Also: personalized greeting by name, refined pre-approval letter flow with review-edit loop, POS incomplete application visibility, and graduated reminder cadence for booked appointments.

---

## 1. Personalized Greeting + Mode Router

### Greeting

When an Aria session starts, the engine has `user_id` and `org_id` from auth. Aria calls `CRMTools.get_user(user_id)` on session init to get the LO's first name, then greets naturally: "Hey Tim, what can I help you with?"

No slot filling needed — automatic on session init. Falls back to "Hey there" if user lookup fails.

### Mode Router

A new classification step runs before the existing NLU/intent node. Lightweight Claude Haiku call (~100ms) returns one of three labels:

| Signal | Mode | Engine |
|---|---|---|
| User requests an action ("send", "text", "schedule", "book", "generate", "create") | **Action** | Existing intent -> slot -> confirm -> execute |
| User asks a question ("how many", "what's the", "show me", "who", "which", "when did") | **Query** | New agentic tool-use (Claude picks tools, chains queries, synthesizes answer) |
| User describes a campaign ("send a text to everyone with", "reach out to all", "mass text") | **Campaign** | New multi-step workflow (filter -> preview -> compose -> confirm -> execute -> track) |

If ambiguous, default to query mode (read-only, safe to try).

**New file:** `backend/aria/core/mode_router.py`

---

## 2. Action Mode — Pre-Approval Letter Flow

The existing `send_preapproval_letter` intent handler gets a complete rewrite from linear slot-filling to a **review-edit loop**.

### Flow

1. LO says "send a pre-approval for John Smith"
2. Aria resolves borrower from CRM, pulls: name, purchase price, loan amount, property address, loan type
3. Aria presents: "I have John Smith — $400K purchase, $360K conventional loan, 123 Main St. Want any changes?"
4. If LO says changes ("make it $500K loan amount"): Aria updates, re-presents: "Updated: $400K purchase, $500K loan. Look good?"
5. Loop until confirmed
6. Property address handling:
   - **Address in CRM:** "I have 123 Main St on file. Keep that, change it, or put TBD?"
   - **No address in CRM:** "Do you have a property address, or should I put TBD?"
   - **LO says TBD:** Letter shows "TBD" in the property address field (standard for buyers still shopping)
7. Aria checks for associated realtor on the lead/loan:
   - **Realtor found:** "I see Sarah Jones is the agent on this file. Want me to send it to her?"
   - **No realtor:** "Who should I send this to?"
8. If LO gives a new realtor name:
   - Aria searches CRM for that realtor
   - If found: "Want me to associate [name] as the agent on this file?"
   - If not found: "I don't have [name] in the system. Want me to add them as a referral partner and text them the portal link?"
9. Generate PDF, deliver via email or SMS based on recipient type
10. Log to loan file: "Pre-approval letter sent to [recipient] for $[amount]"

### Implementation

This is a stateful review loop, not standard slot-fill. The conversation engine's existing multi-turn exchange pattern (slot_fill -> slot_answer loop) supports this: present -> collect edits -> re-present -> confirm.

All fields except `borrower_id` are auto-populated from CRM and presented for review, not collected via slot filling. The handler manages its own state: `phase` cycles through `review -> editing -> recipient_check -> realtor_association -> generating -> done`.

---

## 3. Action Mode — POS Incomplete Applications

### New Intent: `check_pos_applications`

**Trigger phrases:** "who hasn't finished their application", "incomplete applications", "stalled POS apps", "who started an application", "unfinished 1003s", "abandoned applications"

**No required slots** — zero-friction lookup. Optional `date_range` filter if the LO specifies one.

### Flow

1. LO asks about incomplete applications
2. Aria queries `pos_applications` where `status = 'draft'` and `organization_id = org_id`, joined with lead data
3. Count-based branching:
   - **1-5 apps:** Full voice summary: "You have 3 incomplete applications. John Smith started May 1, stuck on employment at 60%. Jane Doe started April 28, stuck on assets at 45%."
   - **6+ apps:** Top 3 summary + offer: "You have 12 incomplete applications. The most recent are [top 3]. Want me to email you the full list?"
4. If LO says "email it": Aria compiles HTML report table (name, start date, last activity, current step, completion %, phone, email), sends to LO's email
5. Aria proactively asks: "Want me to text any of them a reminder to finish?"
6. If LO picks someone: SMS nudge with portal link

### Data pulled per application

- `borrower_first_name`, `borrower_last_name` from POSApplication or linked Lead
- `current_step` (personal, residence, employment, assets, etc.)
- `completion_pct`
- `created_at`, `last_activity_at`
- `borrower_email`, `borrower_phone` from Lead

---

## 4. Query Mode — Agentic CRM Access

When the mode router classifies a message as a question, Aria switches from slot-filling to **agentic tool-use**.

### Architecture

Aria sends the LO's question to Claude Sonnet with:
- System prompt: Aria's identity + "You have access to CRM query tools. Use them to answer the LO's question. Chain multiple tools if needed."
- Available tools: 12 read-only CRM query tools
- Conversation history: Last 10 messages for context

Claude picks which tools to call, Aria executes them, feeds results back, Claude synthesizes a natural-language answer. Standard tool-use loop — no slot filling, no confirmation (read-only operations).

### Query Tools

**New file:** `backend/aria/tools/crm_query_tools.py`

| Tool | Answers questions like |
|---|---|
| `search_loans` | "Show me all loans in processing", "loans closing this month" |
| `search_leads` | "Zillow leads from last week", "leads with no activity in 30 days" |
| `get_pipeline_summary` | "How's my pipeline look?", "how many loans in each stage?" |
| `get_production_stats` | "How many loans did I close last month?", "total volume this year" |
| `get_rate_analysis` | "Average rate on my pipeline", "who has rates above 6%?" |
| `get_commission_data` | "Commission earned in Q1", "revenue this month" |
| `get_referral_stats` | "Who referred the most deals?", "top producing realtors" |
| `get_loan_details` | "What conditions are outstanding on the Smith file?" |
| `get_lead_activity` | "When did I last contact Jane?", "activity on the Johnson file" |
| `get_task_summary` | "What tasks are due today?", "overdue follow-ups" |
| `get_document_status` | "What docs are missing on the Doe file?" |
| `get_pos_stats` | "How many applications came in this week?" |

Each tool takes flexible filter parameters (date range, stage, source, LO, amount range, rate range, etc.) and returns structured data. Claude decides which tool(s) to call — the LO never sees tool names.

### Safety

All tools are read-only. They filter on `organization_id` for tenant isolation. No writes, no mutations, no confirmation needed.

### Performance

Query mode uses a single Claude Sonnet call with tool-use (typically 1-2 tool calls per question). Target: under 4 seconds for voice, under 3 seconds for chat.

---

## 5. Campaign Mode — Mass Text with Calendar Coordination

When Aria detects a mass outreach request, she enters a multi-step campaign workflow.

### Step 1 — Parse & Confirm Audience

LO says: "Text everyone with a rate above 6% and set up calls"

Aria translates to structured filter: `loans WHERE interest_rate > 6.0 AND stage IN ('FUNDED','CLOSING') AND organization_id = :org_id`

Aria confirms: "I found 23 borrowers with rates above 6%. Want to see the list or go ahead with the outreach?"

Filter approach: Aria understands a defined set of filterable fields (rate, stage, loan amount, closing date, last contact date, source, LO assignment, etc.) and confirms the filter before running. Shows count before sending.

### Step 2 — Compose Message

Aria drafts the SMS based on the LO's intent. LO can review/edit:

> "Hi [first_name], this is [LO name]. Rates have come down and I'd like to review your options. When works for a quick call? Here are some times I'm available: [slot_1], [slot_2], [slot_3]. Just reply with the one that works best."

Times are pulled from the LO's real calendar via `get_schedule()`. Each recipient gets the same available slots (refreshed per batch to avoid overbooking).

### Step 3 — Confirm & Send

Aria shows: "Ready to text 23 borrowers. Message preview: [message]. Send now?"

LO confirms -> Aria sends via Telnyx in batches (respects TCPA/DNC scrub, rate limits). Each message logged to `sms_panel_messages`.

### Step 4 — Inbound Reply Handling

When a borrower replies to the SMS thread, the inbound SMS webhook routes the message to a **campaign conversation handler**. The handler uses a Claude Haiku call to interpret the borrower's reply (parse dates/times, detect intent: schedule, decline, or question):

- Borrower replies "Tuesday at 2" -> Aria parses via Claude into a datetime, checks LO availability at that time, books via `AppointmentService`, sends confirmation: "You're set for Tuesday at 2pm with [LO name]. Calendar invite on the way!"
- Borrower replies "none of those work" -> Aria proposes 3 new slots: "How about [slot_4], [slot_5], or [slot_6]?"
- Borrower replies "not interested" / "stop" -> Aria acknowledges, marks contact as declined, no further outreach
- Ambiguous reply -> Aria asks one clarifying question: "Would you like to pick a time for a quick call, or would you prefer I have [LO name] reach out another way?"

### Step 5 — Reminder Cadence

Once booked, the appointment enters graduated reminder flow:

- **Day before:** "Reminder: you have a call with [LO name] tomorrow at [time]"
- **1 hour before:** "Your call with [LO name] is in 1 hour"
- **No-show follow-up** (15 min after missed): "We missed you today — want to reschedule? Reply with a time that works"

Reminders are scheduled tasks that fire via the existing task/notification system.

### Step 6 — Campaign Dashboard

Aria can report on active campaigns: "How's the rate outreach going?" -> "23 texted, 14 replied, 8 booked, 3 completed, 2 no-shows, 6 pending reply."

### Data Model

New `aria_campaigns` table:
- `id`, `organization_id`, `created_by_user_id`
- `name`, `description`
- `filter_criteria` (JSONB — the structured filter)
- `message_template` (text with `[first_name]`, `[lo_name]`, `[slot_N]` placeholders)
- `status` (draft, sending, active, completed, cancelled)
- `recipient_count`, `sent_count`, `replied_count`, `booked_count`, `declined_count`
- `created_at`, `completed_at`

New `aria_campaign_recipients` table:
- `id`, `campaign_id` (FK), `lead_id`, `loan_id`
- `phone`, `email`, `first_name`
- `status` (pending, sent, delivered, replied, booked, completed, no_show, declined, failed)
- `message_id` (Telnyx message ID for thread matching)
- `appointment_id` (FK to scheduler_appointments, nullable)
- `sent_at`, `replied_at`, `booked_at`
- `reminder_day_before_sent`, `reminder_hour_before_sent`, `no_show_followup_sent` (booleans)

---

## 6. New Files

| File | Purpose | Est. Lines |
|---|---|---|
| `backend/aria/core/mode_router.py` | Classify messages into action/query/campaign | ~100 |
| `backend/aria/tools/crm_query_tools.py` | 12 read-only CRM query tools for agentic mode | ~800 |
| `backend/aria/tools/campaign_tools.py` | Campaign filter builder, batch sender, reply handler | ~500 |
| `backend/aria/campaigns/campaign_engine.py` | Multi-step campaign state machine | ~600 |
| `backend/aria/campaigns/reply_handler.py` | Inbound SMS -> campaign conversation routing + scheduling | ~400 |
| `backend/aria/campaigns/reminder_service.py` | Graduated reminder cadence | ~200 |
| `backend/database/models/aria_campaign.py` | `aria_campaigns` + `aria_campaign_recipients` models | ~150 |
| `backend/migrations/add_aria_campaigns.py` | Table creation migration | ~50 |

## 7. Modified Files

| File | Change |
|---|---|
| `backend/aria/core/conversation_engine.py` | Add mode router before NLU node, add query mode branch, add greeting with user name |
| `backend/aria/core/intent_registry.py` | Add `check_pos_applications` intent, update `send_preapproval_letter` trigger phrases |
| `backend/aria/tasks/task_executor.py` | Add `_check_pos_applications` handler, rewrite `_send_preapproval_letter` with review-edit loop |
| `backend/aria/tools/communication_tools.py` | Add `send_batch_sms()`, `send_reminder()` methods |
| `backend/agents/aria_prompts.py` | Update all 3 prompts with greeting pattern, query mode capabilities, campaign capabilities |
| `backend/routes/sms_webhook_routes.py` | Route inbound SMS to campaign reply handler when campaign thread detected |
| `backend/services/event_subscribers.py` | Register campaign event handlers |
| `backend/database/models/__init__.py` | Import AriaCampaign, AriaCampaignRecipient |

---

## 8. Future Work (Not in This Build)

- Campaign scheduling ("send this tomorrow at 9am")
- A/B message testing within a campaign
- Campaign templates library
- Voice-initiated campaigns (workflow is text-based, but triggered via voice)
- Campaign analytics dashboard in frontend
