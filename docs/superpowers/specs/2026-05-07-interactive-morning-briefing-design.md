# Interactive Morning Briefing — Design Spec

**Date:** 2026-05-07
**Status:** Approved
**Author:** Tim Loss + Claude

---

## Overview

The morning briefing becomes a 5-step email conversation between Aria and the loan officer. The LO receives a prioritized task list, replies with what they want AI to handle, reviews a confirmation, approves, and receives a single results summary. All interaction happens via email — no app required.

## Conversation Loop

### Step 1 — Briefing (System → LO, daily at user's briefing_hour)

Aria sends a prioritized action-item email from `aria@perenniaai.com`. Pipeline-first ordering:

1. **At-risk loans** needing action today (days stalled, missing docs, compliance issues)
2. **Expiring rate locks** (within `lock_expiring_days` threshold)
3. **Conditions/docs due** (outstanding underwriting conditions, pending documents)
4. **Stale leads** to follow up (no contact in `stale_lead_days`)
5. **Today's appointments** (calendar items with context)
6. **New leads** to contact (unworked inbound leads)

Each item includes:
- A numbered reference (e.g., `#1`, `#2`)
- Brief context (borrower name, loan number, what's happening)
- Suggested action ("Send follow-up email", "Check on appraisal status")

The email embeds a hidden thread token (`X-Perennia-Thread-Id` header + HTML comment) for reply matching.

### Step 2 — LO Reply (LO → System)

The LO replies to the email with natural language instructions. Examples:
- "Handle 1, 3, and 5"
- "Send the follow-up to Torres and check on the Smith appraisal"
- "Do everything except item 2"
- "For item 4, call instead of emailing"

The system polls the `aria@perenniaai.com` inbox via Microsoft Graph every 60 seconds. Replies are matched to the original briefing thread via `In-Reply-To`/`References` headers, `X-Perennia-Thread-Id`, or sender+date fallback.

### Step 3 — Confirmation (System → LO)

AI parses the reply against the original briefing items and sends a structured confirmation listing each task with specifics:

```
Here's what I'll do:

1. ✉️ Send follow-up email to Maria Torres (stale lead, 12 days no contact)
   → Using your pre-approval follow-up template

2. 📋 Create underwriting condition checklist for Johnson loan (#2024-1847)
   → 3 outstanding conditions: bank statements, VOE, appraisal

3. 📞 Schedule call with James Wilson re: expiring rate lock (expires May 9)
   → Adding to your calendar for today at 2 PM

Reply "approved" to proceed, or tell me what to change.
```

### Step 4 — Approval (LO → System)

LO replies with one of:
- **Approval:** "approved", "go", "yes", "do it", "looks good" → proceed to execution
- **Modifications:** "Change item 2 to email instead of call" → AI sends updated confirmation (loop back to Step 3)
- **Cancel:** "cancel", "nevermind", "stop" → thread moves to CANCELLED

### Step 5 — Results (System → LO)

After all tasks complete, one summary email:

```
✅ All 3 tasks completed:

1. ✅ Email sent to Maria Torres at 8:47 AM
   → Subject: "Quick update on your pre-approval, Maria"

2. ✅ Condition checklist created for Johnson loan
   → 3 items added, assigned to processor Sarah Kim

3. ⚠️ Call scheduled but needs attention
   → James Wilson's number not on file. Added task to your queue.

No further action needed unless noted above.
```

## Thread State Machine

```
BRIEFING_SENT → AWAITING_REPLY → PARSING_INSTRUCTIONS → CONFIRMATION_SENT
→ AWAITING_APPROVAL → EXECUTING → RESULTS_SENT

Loops:
  AWAITING_APPROVAL → CONFIRMATION_SENT (LO requests changes)

Terminal states:
  RESULTS_SENT — all tasks completed
  EXPIRED — no reply within 4 hours of briefing send
  CANCELLED — LO explicitly cancels
  FAILED — unrecoverable error during execution
```

## Thread Identity & Reply Matching

Outbound briefing emails include:
- `X-Perennia-Thread-Id: briefing_{thread_uuid}` custom header
- `<!-- perennia-thread:{thread_uuid} -->` hidden HTML comment in body
- Standard `Message-ID` for email threading

Reply matching priority:
1. `In-Reply-To` / `References` headers (standard email threading)
2. `X-Perennia-Thread-Id` header match
3. Fallback: sender email + briefing date within 24 hours

## Data Model

### BriefingThread

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| organization_id | Integer FK | Tenant isolation |
| user_id | Integer FK → users | The LO |
| morning_briefing_id | Integer FK → morning_briefings | Link to source briefing |
| thread_token | UUID | Unique, indexed |
| outbound_message_id | String | Graph Message-ID for threading |
| state | String | State machine value |
| briefing_items | JSONB | The prioritized items sent |
| extracted_tasks | JSONB | Parsed from LO reply |
| lo_reply_raw | Text | Raw reply email body |
| lo_approval_raw | Text | Raw approval email body |
| state_changed_at | TimestampTZ | Last transition |
| expires_at | TimestampTZ | 4 hours after briefing sent |
| created_at | TimestampTZ | |
| updated_at | TimestampTZ | |

Indexes: `(user_id, state)`, `(thread_token)` unique, `(organization_id, created_at DESC)`

### BriefingTask

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| thread_id | Integer FK → briefing_threads | |
| organization_id | Integer FK | Tenant isolation |
| briefing_item_number | Integer | Reference to item # in briefing |
| briefing_item_summary | Text | "Follow up with Maria Torres" |
| action_type | String | send_email, create_task, schedule_call, update_lead, etc. |
| action_params | JSONB | Tool-specific parameters |
| tool_name | String | @mortgage_tool function name |
| lo_override_notes | Text | "Call instead of email" |
| status | String | pending, approved, executing, completed, failed |
| result_data | JSONB | Execution result |
| error_message | Text | If failed |
| started_at | TimestampTZ | |
| completed_at | TimestampTZ | |

Indexes: `(thread_id, status)`, `(organization_id)`

## Task Extraction

Claude parses the LO's natural language reply using the original briefing items as grounding context. The prompt includes:

- The numbered briefing items with their suggested actions
- The LO's raw reply text
- Instructions to extract: which items are selected, any action overrides, any additional instructions

Output: a structured list of `BriefingTask` records with action types and parameters mapped to specific `@mortgage_tool` functions.

Action type → tool mapping examples:
- `send_email` → `send_email_to_contact` or `compose_contextual_email`
- `create_task` → `create_task`
- `schedule_call` → `schedule_appointment` or `create_task` with call type
- `update_lead` → `update_lead_status`
- `send_sms` → `send_sms_message`
- `check_conditions` → `get_loan_conditions`

## Task Execution

Once approved, each `BriefingTask` executes sequentially via the existing `AIAgentService`:

1. Instantiate `AIAgentService(db, user, autonomous_mode=True)` for the LO
2. For each approved task, call the mapped `@mortgage_tool` function
3. Log result to `BriefingTask.result_data`
4. On failure, log error and continue to next task (don't abort the batch)
5. After all tasks complete, send results email

The existing risk classification applies internally as a safety net, but from the LO's perspective everything was pre-approved.

## Infrastructure

### Monitored Inbox

- Dedicated `aria@perenniaai.com` mailbox with Microsoft Graph API access
- Requires a service account or app-only Graph token (not user-delegated)
- New Celery Beat task: `poll_briefing_replies` every 60 seconds
- Polls unread messages, matches to active threads, dispatches `process_briefing_reply` Celery task

### Email Sending

- Uses `send_email_via_graph` from existing `dre_helpers.py`
- Sends FROM `aria@perenniaai.com`
- Applies org's white-label branding (logo, colors, company name)
- All user-controlled values HTML-escaped via `html.escape()`

### Celery Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| `dispatch_briefings` | Every 15 min | Existing — generates briefings by timezone |
| `poll_briefing_replies` | Every 60 sec | NEW — polls inbox, matches to threads |
| `process_briefing_reply` | On-demand | NEW — parses reply, extracts tasks, sends confirmation |
| `execute_briefing_tasks` | On-demand | NEW — runs approved tasks, sends results |
| `expire_stale_threads` | Every 30 min | NEW — moves threads past 4h to EXPIRED |
| `cleanup_old_briefings` | Daily | Existing — deletes briefings older than 90 days |

### Reply Classifier

New mode in the DRE pipeline: `classify_briefing_reply(reply_text, briefing_items)`. Returns:
- `intent`: `approve`, `modify`, `cancel`, `task_selection`
- `selected_items`: list of item numbers
- `overrides`: dict of item → override instructions
- `additional_instructions`: free text

## Cleanup (from audit)

These fixes are bundled with this feature work:

1. **Delete** `agents/autonomous/morning_briefing.py` — dead divergent code with no tenant isolation
2. **Add `html.escape()`** to all interpolated values in `templates/morning_briefing_email.py`
3. **Fix DB session leaks** in `tasks/morning_briefing_tasks.py` — use context managers
4. **Extract shared components** from BriefingPage.js + MorningBriefingCard.js into `components/briefing/`
5. **Fix UTC dismiss date** in MorningBriefingCard.js → use local timezone
6. **Add error boundary** around MorningBriefingCard on Dashboard
7. **Unify status filtering** between card and page

## What Stays Unchanged

- `MorningBriefing` model and data gathering queries in `morning_briefing_service.py`
- Briefing preferences (sections, thresholds, AI tone)
- Celery Beat dispatch every 15 min by timezone
- BriefingPage.js and MorningBriefingCard.js (read-only views — updated but not replaced)
- User's `briefing_hour` and `briefing_enabled` settings

## Out of Scope

- In-app approval flow (email-only for v1)
- Multi-LO manager briefing replies (managers receive briefings but reply flow is per-LO only)
- Attachments in reply emails
- Voice/SMS alternative channels for the conversation loop
