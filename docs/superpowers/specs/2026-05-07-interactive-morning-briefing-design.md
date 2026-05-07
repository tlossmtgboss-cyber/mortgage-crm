# Aria Interactive Briefing System — Unified V1 Specification

**Owner:** Tim Loss
**Status:** Approved scope, pre-implementation
**Last revised:** 2026-05-07
**Document type:** Combined product spec + implementation plan + audit remediation

---

## 1. Executive Summary

The Aria Interactive Briefing System is the V1 milestone of a multi-phase evolution toward a *Mortgage Operating System*. V1 is a closed, email-mediated conversation loop in which Aria proposes a prioritized daily action list, the LO replies in natural language, Aria restates the plan for explicit approval, executes inside a controlled sandbox, and reports back. Every action is human-approved; nothing fires without confirmation.

This document merges three previously separate artifacts into one canonical reference:

1. The **Aria Interactive Briefing System — Full Product Roadmap** (V1 → V4 vision).
2. The **Interactive Morning Briefing** V1 implementation spec (state machine, data model, Celery topology, email examples).
3. The **morning briefing audit cleanup** (correctness, security, and tenant-isolation defects that must land before V1 ships).

It also closes gaps that exist between the three sources — most importantly around reply parsing semantics, idempotency, the compliance flag column promised in the results email, and the trust mode under which V1 actually runs.

---

## 2. Strategic Context

### 2.1 Where V1 sits in the product evolution

| Phase | Identity                                              | Default Trust Mode                  |
| ----- | ----------------------------------------------------- | ----------------------------------- |
| V1    | Interactive Morning Briefing                          | Mode 3 — Approved Automation        |
| V2    | AI Operations Manager (continuous monitoring)         | Mode 3 → Mode 4 per workflow        |
| V3    | Autonomous Mortgage Coordination System               | Mode 4 default, Mode 5 for narrow workflows |
| V4    | The Mortgage Operating System                         | Mode 5 with policy-bounded autonomy |

The five Trust Modes from the roadmap (Observer → Draft Assistant → Approved Automation → Guardrailed Autonomy → Enterprise Autonomous Ops) become a runtime configuration on each tenant and each agent capability — not a versioning concept. V1 hardcodes Mode 3 globally; V2 introduces per-capability mode selection.

### 2.2 The competitive differentiator V1 must establish

V1 is not "an AI inbox assistant." It is the *first proof* that Perennia turns the CRM into an active execution layer. To preserve that positioning the V1 implementation must hold three properties without exception:

- **AI proposes, human approves, AI executes.** The approval gate is non-bypassable in V1.
- **Restate-before-execute.** Confirmation must be lossless against the LO's reply — no silent action substitutions, no inferred extras.
- **Auditable end-to-end.** Every state transition, tool call, and email is persisted with tenant scoping and retrievable for compliance review.

Anything that erodes those three properties is out of scope for V1 regardless of how attractive it looks in a demo.

---

## 3. V1 Scope — In and Out

### 3.1 In scope

- One daily morning briefing per LO, dispatched per the LO's `briefing_hour` in their local timezone.
- Six briefing item categories (priority order in §4.2).
- Natural-language email reply parsing.
- AI-generated confirmation email with explicit task list.
- Single-message approval: `approved`, `approve all`, `approve except N`, or modifications that loop back to a new confirmation.
- Bounded executor with the seven supported action types (§6.2).
- One results email per thread.
- 4-hour reply expiry, then thread auto-expires.
- Manager copy on briefings (read-only — managers cannot reply to drive execution).

### 3.2 Out of scope (deferred to V2+)

- In-app approval flow (email-only in V1).
- Manager reply-driven execution.
- Attachment handling on inbound replies.
- SMS, voice, Slack, or in-app notification channels for the conversation loop itself.
- Continuous (non-morning) pipeline monitoring.
- Close-on-time prediction surfaced inside the briefing item.
- Borrower-side concierge interactions.
- Auto-send drafts (V1 always requires explicit approval).

### 3.3 Trust Mode for V1

**Trust Mode 3 — Approved Automation** is the only supported mode in V1. Implementation note: even though V1 is single-mode, store the trust mode on `briefing_threads.trust_mode` from day one so V2's per-capability mode selection ships without a migration.

---

## 4. The Conversation Loop

### 4.1 The five steps

```
1. Briefing      Aria → LO   prioritized action items
2. Reply         LO  → Aria  natural language instructions
3. Confirmation  Aria → LO   restated explicit task list
4. Approval      LO  → Aria  approve / modify / cancel
5. Results       Aria → LO   single execution summary
```

Steps 3 and 4 form a loop: any modification in step 4 returns to step 3 with a regenerated confirmation. Loop depth is capped at **3 modification cycles per thread**; on the fourth, the thread is moved to `MANUAL_REVIEW` and the LO is notified that the conversation has been escalated.

### 4.2 Briefing priority order

Pipeline-first. Within each category items are sorted by urgency × financial impact × SLA risk. Across categories the order is fixed:

1. **At-risk loans** — stalled in stage beyond SLA, missing critical docs, compliance issues.
2. **Expiring rate locks** — within `lock_expiring_days` threshold (default 5).
3. **Conditions & docs due** — open underwriting conditions and pending documents.
4. **Stale leads** — no contact in `stale_lead_days` (default 7).
5. **Today's appointments** — calendar items with attached borrower context.
6. **New leads** — inbound, unworked.

### 4.3 Briefing item enrichment

Each item carries the visible summary plus the following structured fields, available to the parser, the confirmation generator, and the V2 prioritization engine:

| Field                  | Type     | Example                                  | V1 use                            |
| ---------------------- | -------- | ---------------------------------------- | --------------------------------- |
| `urgency_score`        | 0–100    | 87                                       | Sort + risk gate                  |
| `financial_impact_usd` | int      | 425000                                   | Sort + display                    |
| `sla_risk`             | enum     | `none`, `at_risk`, `breached`            | Sort + display                    |
| `days_stalled`         | int      | 8                                        | Display                           |
| `borrower_sentiment`   | enum     | `unknown`, `engaged`, `frustrated`, `ghosting` | Tone-shift confirmation copy |
| `next_best_action`     | string   | `send_borrower_doc_request`              | Default action for the item       |
| `why_it_matters`       | string   | "$2,400 lock extension cost at risk"     | Justification line in briefing    |

`borrower_sentiment` and `urgency_score` are produced by Aria's memory + Call Intelligence stack today. V1 consumes them but does not improve them.

---

## 5. Reply Processing

### 5.1 Parser architecture

Inbound reply email → MIME normalization → quoted-reply stripping → Claude (Haiku, structured output) → `ParsedReply` Pydantic model → task synthesis → confirmation draft.

The parser is a Claude call with strict structured output. The system prompt receives the full briefing JSON (the same items the LO saw) plus the LO's reply text and returns:

```python
class ParsedReply(BaseModel):
    handled_items: list[int]           # item numbers to execute
    skipped_items: list[int]           # explicit skips
    overrides: list[ItemOverride]      # per-item modifications
    bulk_action: BulkAction | None     # "handle all", "do everything except 5"
    free_text_instructions: list[str]  # un-mappable instructions
    confidence: float                  # 0..1
    requires_clarification: bool
    clarification_question: str | None
```

`bulk_action` is resolved against `handled_items` and `skipped_items` deterministically in Python (not the LLM): `handle_all` expands to all item numbers, `except` is set difference.

### 5.2 Override semantics

`ItemOverride` represents the difference between the briefing's `next_best_action` and what the LO asked for:

```python
class ItemOverride(BaseModel):
    item_number: int
    new_action_type: str | None        # e.g. "schedule_call" instead of "send_email"
    instruction_delta: str             # natural language delta, e.g. "call instead"
    requires_validation: list[str]     # ["phone_number_on_file", "calendar_availability"]
```

Overrides flow through the same execution sandbox as default actions, but each `requires_validation` item must pass before the confirmation is sent. If validation fails (e.g. LO says "call instead" but no phone is on file), the confirmation surfaces the conflict and does not present the override as approvable.

### 5.3 Quoted-reply handling

Email replies routinely include the entire previous thread inline. The parser MUST receive only the new content. Stripping order:

1. Strip everything below the first `On <date>, ... wrote:` line (Outlook + Apple Mail).
2. Strip everything below `>` quote markers (plaintext clients).
3. Strip everything below `<blockquote class="gmail_quote">` (Gmail HTML).
4. Strip image-only signatures by fingerprint match.

Anything left is the LO's actual reply. If stripping leaves an empty body the thread moves to `AWAITING_REPLY` (treat as no-reply, not as a reply with no instructions).

### 5.4 Free-text instructions

If the LO writes something the parser cannot map to an item override (e.g. "also remind me to call the underwriter about Smith"), it goes into `free_text_instructions` and is surfaced in the confirmation as a separate **"I noticed but won't act on"** section. V1 does not execute free-form instructions — only items that originated in the briefing.

This is deliberate. It is the simplest defensible boundary against scope creep, prompt injection, and the "I told Aria to do X but it did Y" class of failures.

---

## 6. Confirmation, Approval, and Execution

### 6.1 Confirmation contents

Every confirmation email contains, in this order:

1. The numbered list of tasks Aria intends to execute, with the exact tool call and merge-field values rendered for the LO to read.
2. A **risk strip** for any task with `risk_level >= high` (lock extensions, large doc requests, anything with compliance flags).
3. A **"won't act on"** section listing free-text instructions the system saw but is not executing.
4. The single-line approval prompt: *"Reply 'approved' to proceed, or tell me what to change."*

Each task in the confirmation includes its **confidence score** and **risk level** as small inline tags, e.g. `confidence 96%, risk low`.

### 6.2 Supported action types (the executor's allow-list)

V1 executor supports exactly seven action types. Any parsed task that does not map to one of these is rejected before confirmation is sent:

| Action                | Tool                                  | High-risk? |
| --------------------- | ------------------------------------- | ---------- |
| `send_borrower_email` | `email.send_borrower_message`         | No         |
| `send_realtor_update` | `email.send_realtor_update`           | No         |
| `create_crm_task`     | `crm.create_task`                     | No         |
| `schedule_call`       | `calendar.create_event_with_borrower` | No         |
| `assign_processor_task` | `crm.assign_task_to_processor`      | No         |
| `request_docs`        | `smart_docs.request_documents`        | Conditional* |
| `update_pipeline_stage` | `pipeline.transition_stage`         | **Yes**    |
| `send_checklist`      | `email.send_checklist_to_borrower`    | No         |

*`request_docs` becomes high-risk if it touches any doc category flagged GLBA-sensitive (SSN-bearing, full bank statements with account numbers).

### 6.3 Execution sandbox

Before execution, every approved task passes through a **pre-flight validation** function specific to its action type. The pre-flight runs in dry-run mode against the same tool and verifies:

- Recipient email is current and not bounced.
- Loan number, borrower ID, and merge fields resolve to the same record the briefing item referenced.
- Template is current and approved for use in the LO's tenant.
- For `send_borrower_email`, that the borrower has not opted out of email contact (TCPA/CAN-SPAM).
- For `request_docs`, that no duplicate request was sent in the last 24 hours.

A failed pre-flight does **not** retry. The task moves to `failed_preflight` and surfaces in the results email as a "needs human attention" item with the failure reason.

### 6.4 Confidence and risk gates

Each task carries a `confidence_score` (0–1, from the parser) and a `risk_level` (`low`, `medium`, `high`, derived from action type + pre-flight results).

V1 gating rules:

- `risk_level == high` always requires explicit per-task approval; bulk approval (`approve all`) does **not** authorize high-risk tasks. The LO must reply with the explicit task numbers.
- `confidence_score < 0.75` blocks the task from auto-inclusion in confirmation — it is surfaced separately as a "Did I understand this right?" item.
- Pipeline stage transitions (`update_pipeline_stage`) are always high-risk in V1.

### 6.5 Approval semantics

Recognized approval forms:

- `approved` / `approve` / `yes proceed` → executes all tasks in the latest confirmation that are not high-risk.
- `approve all` → executes all tasks including high-risk if they were explicitly enumerated.
- `approve 1, 3, 5` → executes only those tasks.
- `approve except 2` → executes all but task 2.
- `cancel` / `nevermind` → moves thread to `CANCELLED`.
- Anything else → treated as a modification, loops back to step 3.

Approval matching is bound to the **most recent confirmation in the thread**. If the LO replies "approved" after a confirmation was superseded by a later modification cycle, the approval applies to whichever confirmation it threads against (using `In-Reply-To`), not to the latest. This prevents stale approvals from racing.

---

## 7. Results Summary

The results email is the only post-execution communication. It contains:

| Section                  | Contents                                                         |
| ------------------------ | ---------------------------------------------------------------- |
| **Completed**            | Tasks that ran successfully, with timestamps and key result data |
| **Failed**               | Tasks that errored mid-execution, with reason                    |
| **Needs human attention**| Pre-flight failures, partial successes, ambiguous outcomes       |
| **Carryover to tomorrow**| Tasks the LO skipped that are still relevant                     |
| **Compliance flags**     | Anything the compliance check surfaced (see §10.2)               |
| **SLA risk changes**     | Items where SLA risk changed during execution                    |

"Compliance flags" and "SLA risk changes" are required sections even when empty. An empty section reads `No flags raised during execution.` This makes their absence in the email an actionable signal that something is wrong with the pipeline, not noise.

---

## 8. State Machine

### 8.1 Full state diagram

```
BRIEFING_SENT
  └─► AWAITING_REPLY  (timer: 4h)
        ├─► [reply received] PARSING_INSTRUCTIONS
        │     ├─► [parse ok] CONFIRMATION_SENT
        │     │                └─► AWAITING_APPROVAL
        │     │                      ├─► [approved] EXECUTING
        │     │                      │                ├─► [done] RESULTS_SENT
        │     │                      │                └─► [unrecoverable] FAILED
        │     │                      ├─► [modification] CONFIRMATION_SENT (loop, max 3)
        │     │                      ├─► [cancel] CANCELLED
        │     │                      └─► [4h elapsed] EXPIRED
        │     ├─► [parse needs clarification] CLARIFICATION_SENT
        │     │                                  └─► AWAITING_REPLY (timer reset)
        │     └─► [parse fail] MANUAL_REVIEW
        └─► [4h elapsed, no reply] EXPIRED
```

### 8.2 Terminal states

`RESULTS_SENT`, `EXPIRED`, `CANCELLED`, `FAILED`, `MANUAL_REVIEW`. No transitions out of terminal states. Re-engaging requires a new briefing tomorrow.

### 8.3 Idempotency

State transitions are idempotent: the same inbound message processed twice (Graph webhook retry, Celery double-pickup) produces no duplicate confirmations, executions, or emails. This is enforced by:

- Unique constraint on `(thread_id, inbound_message_id)` for replies.
- Unique constraint on `(thread_id, state, transitioned_at_minute)` to prevent simultaneous duplicate transitions.
- Tool execution wrapped in an idempotency key derived from `(briefing_task_id, attempt_number)`; tool layer rejects duplicate keys within a 1-hour window.

---

## 9. Data Model

### 9.1 `briefing_threads`

| Column                  | Type           | Notes                                          |
| ----------------------- | -------------- | ---------------------------------------------- |
| `id`                    | Integer PK     |                                                |
| `organization_id`       | Integer FK     | Tenant isolation; **indexed and required on every query** |
| `user_id`               | Integer FK     | The LO                                         |
| `morning_briefing_id`   | Integer FK     | Source briefing                                |
| `thread_token`          | UUID           | Unique, indexed                                |
| `outbound_message_id`   | String         | Graph Message-ID for threading                 |
| `state`                 | String         | State machine value                            |
| `trust_mode`            | Integer        | 1–5; V1 always stores 3                        |
| `loop_count`            | Integer        | Number of modification cycles; capped at 3     |
| `briefing_items`        | JSONB          | Snapshot of items at send time                 |
| `extracted_tasks`       | JSONB          | Parsed from LO reply                           |
| `lo_reply_raw`          | Text           | Raw reply email body, post-strip               |
| `lo_approval_raw`       | Text           | Raw approval email body                        |
| `expires_at`            | TimestampTZ    | 4 hours after briefing sent                    |
| `created_at`            | TimestampTZ    |                                                |
| `updated_at`            | TimestampTZ    |                                                |

**Indexes:**
`(organization_id, user_id, state)`, `(organization_id, expires_at) WHERE state IN ('AWAITING_REPLY','AWAITING_APPROVAL')`, `(thread_token)` unique, `(outbound_message_id)`.

### 9.2 `briefing_tasks`

| Column                   | Type        | Notes                                      |
| ------------------------ | ----------- | ------------------------------------------ |
| `id`                     | Integer PK  |                                            |
| `thread_id`              | Integer FK  |                                            |
| `organization_id`        | Integer FK  | Denormalized; required on every query      |
| `briefing_item_number`   | Integer     | Reference to item # in briefing            |
| `briefing_item_summary`  | Text        |                                            |
| `action_type`            | String      | One of the seven supported                 |
| `action_params`          | JSONB       | Tool-specific parameters                   |
| `tool_name`              | String      | Resolved tool function name                |
| `lo_override_notes`      | Text        |                                            |
| `confidence_score`       | Float       | 0–1                                        |
| `risk_level`             | String      | `low`, `medium`, `high`                    |
| `preflight_result`       | JSONB       | Validations passed/failed                  |
| `idempotency_key`        | String      | Indexed unique                             |
| `status`                 | String      | `pending`, `approved`, `executing`, `completed`, `failed`, `failed_preflight`, `carryover` |
| `carryover_target_date`  | Date        | Next briefing date if status is carryover  |
| `result_data`            | JSONB       |                                            |
| `error_message`          | Text        |                                            |
| `executed_at`            | TimestampTZ |                                            |

### 9.3 `briefing_audit_log`

New table added under this V1 work to back the compliance section of the results email and to satisfy the audit requirement that every action is traceable.

| Column            | Type         | Notes                                     |
| ----------------- | ------------ | ----------------------------------------- |
| `id`              | BigInt PK    |                                           |
| `organization_id` | Integer FK   | Required, indexed                         |
| `thread_id`       | Integer FK   |                                           |
| `task_id`         | Integer FK   | Nullable for thread-level events          |
| `event_type`      | String       | `state_transition`, `tool_call`, `email_sent`, `email_received`, `compliance_flag` |
| `actor`           | String       | `system`, `user:<user_id>`, `aria`        |
| `payload`         | JSONB        | Redacted; SSN/DOB/account-number scrubbed |
| `payload_hash`    | String       | SHA-256 of un-redacted payload (chain)    |
| `prev_hash`       | String       | Hash of previous row in same thread       |
| `created_at`      | TimestampTZ  | Indexed                                   |

The `prev_hash` chain matches the e-sign audit log pattern already in place — same hashing utility, same verification command in the SOC 2 module.

### 9.4 Tenant isolation

Every query on `briefing_threads`, `briefing_tasks`, or `briefing_audit_log` MUST filter on `organization_id`. The repository layer enforces this with a runtime guard: any query that does not include `organization_id` in its WHERE clause raises `TenantIsolationError` before execution. This is the same pattern used in the security audit skill and is non-negotiable.

---

## 10. Security & Compliance

### 10.1 PII handling

- Reply and approval bodies are stored in `lo_reply_raw` and `lo_approval_raw` for replay debugging. Both pass through the standard PII redactor (SSN, DOB, full account numbers) before storage. The redactor is the same one used in the conversational SMS system.
- The `briefing_audit_log.payload` column stores redacted payloads. The chained hash is computed on the un-redacted payload so integrity is verifiable without storing the original.
- The 90-day cleanup task purges raw reply bodies but retains the audit log for 7 years per SOC 2 retention policy.

### 10.2 Compliance flags surfaced in results

V1 ships with three core compliance checks. Two additional flags (`eccoa_adverse_action_due`, `licensed_state_mismatch`) are deferred to a fast follow once the LO licensing table is queryable from the executor.

| Flag                           | Trigger                                                                 | V1 |
| ------------------------------ | ----------------------------------------------------------------------- | -- |
| `tcpa_optout_violation_blocked`| Borrower contact attempted on a record with `tcpa_opt_out=true`         | ✓  |
| `trid_clock_change`            | An action would alter a TRID-tracked timestamp                          | ✓  |
| `glbasensitive_doc_request`    | A doc request includes a GLBA-flagged category                          | ✓  |
| `eccoa_adverse_action_due`     | Loan in a state where Reg B §1002.9 timing applies and no notice queued | Deferred |
| `licensed_state_mismatch`      | Outbound communication targeted to a borrower in a state the LO is not licensed in | Deferred |

Hits do not block execution unless the flag is `tcpa_optout_violation_blocked` (which is hard-blocked at the executor). The rest are surfaced for review in the next morning's briefing as at-risk items.

### 10.3 Email security

- Outbound `aria@perenniaai.com` is sent from a dedicated subdomain (`perenniaai.com` MAIL FROM aligned). SPF, DKIM, and DMARC are all `pass` required on the sending domain; the deployment ticket includes DNS verification as a pre-launch gate.
- Inbound is processed via Graph subscription webhook with signature validation (Ed25519 like the Telnyx pattern is not applicable here — Microsoft Graph uses validation tokens; the validator must verify the token on every webhook before enqueueing).
- Rate limit on inbound parse: max 10 reply parses per thread per hour, max 50 replies per LO per day. Beyond either, replies queue and an alert fires.

### 10.4 Authorization

The LO who received the briefing is the only user authorized to drive its thread. `lo_reply_raw` from any other sender is logged as `email_received` in the audit log but does not advance the state machine. This handles the assistant-replies-on-behalf-of-LO edge case explicitly: such replies are visible in the audit log but require the LO to forward and reply themselves to act on them.

---

## 11. Celery Task Architecture

| Task                       | Schedule         | Purpose                                                | Status   |
| -------------------------- | ---------------- | ------------------------------------------------------ | -------- |
| `dispatch_briefings`       | Every 15 min     | Generates briefings by timezone                        | Existing |
| `poll_briefing_replies`    | Every 60 sec     | Polls inbox, matches replies to threads                | New      |
| `process_briefing_reply`   | On-demand        | Parses reply, extracts tasks, sends confirmation       | New      |
| `execute_briefing_tasks`   | On-demand        | Runs approved tasks, sends results                     | New      |
| `expire_stale_threads`     | Every 30 min     | Moves threads past 4h to EXPIRED                       | New      |
| `cleanup_old_briefings`    | Daily            | Deletes briefings older than 90 days, retains audit log | Existing |

All on-demand tasks are dispatched from `poll_briefing_replies`. Running the executor on Celery — not synchronously inside the webhook handler — gives us idempotency by way of the broker, not just at the database layer.

### 11.1 Reply matching priority

Three strategies in fixed order:

1. `In-Reply-To` / `References` headers match `outbound_message_id`.
2. Custom `X-Perennia-Thread-Id` header matches `thread_token`.
3. Sender email + briefing date — fall back only if 1 and 2 produce no match. Match must resolve to exactly one active thread for that LO from today; ambiguous matches go to manual review.

### 11.2 Failure handling inside `execute_briefing_tasks`

Tasks within a single approval batch run **sequentially** in the order the LO approved them. A task failure does **not** halt the batch; subsequent tasks continue and the failed task surfaces in the "Failed" section of the results. Exception: if a `update_pipeline_stage` task fails, all subsequent tasks in the batch that depend on the new stage are skipped and surface as "Needs human attention" with a dependency-failure reason.

---

## 12. Pre-V1 Audit Cleanup

These items must land *before* V1 ships. They are not refactors — each is a correctness, security, or tenant-isolation defect in the code path V1 builds on.

| # | Defect                                                                                    | Severity | Why it must land first                                                                 |
| - | ----------------------------------------------------------------------------------------- | -------- | -------------------------------------------------------------------------------------- |
| 1 | Delete `agents/autonomous/morning_briefing.py` — divergent dead code with no tenant isolation | High     | V1 introduces a new code path; leaving the old one creates drift and a tenant-leak surface |
| 2 | Add `html.escape()` to all interpolated values in the morning briefing email template     | High     | Briefing items now include borrower names from CRM — XSS-via-CRM-injection becomes a real vector |
| 3 | Fix DB session leaks in `morning_briefing_tasks.py` — use context managers throughout     | High     | V1 quadruples task volume; a leak that was tolerable becomes pool exhaustion           |
| 4 | Extract shared components from `BriefingPage.js` and `MorningBriefingCard.js`              | Medium   | V1 adds a third surface (thread review); duplicating again triples maintenance cost    |
| 5 | Fix UTC dismiss date → local timezone                                                     | Medium   | The 4-hour expiry is local-aware; the dismiss date must be too or LOs will see ghost briefings |
| 6 | Add error boundary around `MorningBriefingCard` on Dashboard                               | Medium   | A render error in the card currently white-screens the whole dashboard                 |
| 7 | Unify status filtering between card and page                                              | Low      | Two filters drift; LOs report mismatches between dashboard count and page count        |

The order in the table is not the implementation order. The implementation order is **1 → 3 → 2 → 6 → 5 → 7 → 4** so that the tenant-isolation defect is closed first and the React refactor (which has the largest blast radius) lands last.

---

## 13. Gap Analysis — Issues Not Resolved by Either Source Document

These are gaps identified while merging the roadmap, the V1 spec, and the audit. Each needs a decision before implementation begins.

1. **Compliance flag column was promised but never wired.** The V1 results email format includes a "Compliance Flags" section but neither source document defines what populates it. §10.2 above proposes the V1 set; this needs sign-off because the licensed-state-mismatch check requires the LO licensing table to be queryable from the executor (it currently isn't).
2. **Confirmation idempotency under multiple replies.** If the LO replies twice in quick succession (modification, then "actually, just approved"), the system needs deterministic behavior. §6.5 binds approvals to the specific confirmation they thread against. This is the simplest defensible rule but it can produce surprising outcomes. Alternative: latest-reply-wins.
3. **Override validation surfaces failure but doesn't suggest an alternative.** When the LO says "call instead of email" for an item with no phone on file, §5.2 says we surface the conflict. Proposed: the confirmation says "I can't call — no phone on file. Fall back to email, or skip?" The LO reply on a single open question advances the loop without consuming a modification cycle.
4. **Manager-copy semantics are underspecified.** Managers are CC'd on briefings but cannot reply to drive execution. What happens if a manager replies anyway? Proposed: it is logged in the audit log as an inbound email and ignored for state purposes; the LO is not notified.
5. **The 4-hour expiry is timezone-naive in the source spec.** It is stated as "4 hours after briefing sent" in UTC. Proposed: keep `expires_at` in UTC but compute it as `briefing_sent_at_local + 4h` then convert. This means a briefing sent at 7am local expires at 11am local regardless of DST shifts during the window.
6. **No explicit kill-switch.** V1 should ship with a per-tenant feature flag (`interactive_briefing_enabled`) and a per-org executor disable (`interactive_briefing_executor_disabled`). The first lets you roll out gradually; the second lets you halt all execution while leaving briefing dispatch running if a runaway is detected.
7. **Loop cap of 3 modification cycles is a guess.** The roadmap doesn't specify a cap; 3 is proposed because anything higher in production rapidly produces threads that LOs lose track of.
8. **Stale-lead `borrower_sentiment` may be empty.** §4.3 lists the field but stale leads, by definition, may have no recent communication to derive sentiment from. The parser should treat `unknown` as the default and not let it influence sort order.
9. **The "new lead" category is ambiguous about source.** For V1 we need a precedence rule for when a single lead has both a website inquiry and a realtor referral attached. **Decision: most recent source wins** — whatever source came in last determines the template, regardless of type.
10. **Carryover-to-tomorrow has no persistence model.** §7 mentions it; nothing in the data model captures it. Proposed: `briefing_tasks.status='carryover'` with a `carryover_target_date` column, and the next morning's briefing pulls them in as item-1 candidates.

---

## 14. V1 → V2 Setup

Decisions in V1 that pay off in V2 if made correctly now, and cost a migration if not:

- **Trust mode column on `briefing_threads`** (§3.3). Hardcoded to 3 in V1; per-capability in V2.
- **Audit log with chained hashes** (§9.3). V1 needs it for SOC 2 anyway; V2's continuous monitoring multiplies the volume but reuses the schema.
- **Idempotency keys at the tool layer** (§8.3). Required for V2 autonomous execution; if V1 ships without them, V2 cannot turn on auto-execute without a coordinated tool-layer rewrite.
- **Capability registry for the seven action types** (§6.2). Currently a flat enum. If we wrap it in a registry pattern now, V2's AI Tool Router slots in without refactoring callers.
- **Borrower sentiment + urgency score consumed but not produced** (§4.3). Keep the consumption side clean. V2 will introduce active sentiment monitoring and these fields will start moving in real time.

---

## 15. Resolved Decisions

All decisions signed off 2026-05-07:

1. **Compliance flags — 3 core only.** Ship with `tcpa_optout_violation_blocked`, `trid_clock_change`, `glbasensitive_doc_request`. Defer `eccoa_adverse_action_due` and `licensed_state_mismatch` to fast follow (LO licensing table not yet queryable from executor).
2. **Confirmation idempotency — bind-to-confirmation.** Approval applies to whichever confirmation the reply threads against via `In-Reply-To`. Prevents stale approvals from racing.
3. **Override-fail fallback — yes, suggest fallback.** Confirmation says "I can't call — no phone on file. Fall back to email, or skip?" Reply advances without consuming a modification cycle.
4. **Manager-replies-anyway — log and ignore.** Reply logged in audit log, does not advance state machine, LO is not notified.
5. **Loop cap — 3 modification cycles.** On the 4th, thread escalates to `MANUAL_REVIEW`.
6. **Lead-source precedence — most recent source wins.** Whatever source came in last determines the template, regardless of type.
7. **Carryover schema — accepted.** `briefing_tasks.status='carryover'` with `carryover_target_date` column. Next morning's briefing pulls carryover items as priority candidates.
8. **V1 ship order — confirmed.** Audit fixes (1→3→2→6→5→7→4), then briefing system, then feature flag rollout.

---

*End of unified specification.*
