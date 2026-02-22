# Perennia AI — CRM Workflow Audit Report
**Generated**: 2026-02-22T00:50:00Z
**Audit Scope**: Workflow Logic & Routing
**Environment**: production

## Executive Summary
- **Total Checks**: 30
- **Critical**: 5 | **Warning**: 7 | **Pass**: 15 | **Skipped**: 3
- **Overall Health Score**: 0 / 100
- **Top Priority**: SLA alert endpoints (`/api/v1/sla/alerts`, `/api/v1/sla/milestones/active`) are publicly accessible without authentication, exposing lead IDs, user IDs, and operational data.

---

## Critical Findings

### [SEC-001] Unauthenticated SLA Endpoints
**Severity**: CRITICAL
**Category**: Security / Routing
**Finding**: `/api/v1/sla/alerts` and `/api/v1/sla/milestones/active` return full data (50 active alerts, 58 active milestones) without any authentication. These expose `organization_id`, `lead_id`, `assigned_to_id`, and milestone timing details to the public internet.
**Impact**: Data leak of internal CRM operational state. Any external actor can enumerate lead IDs and user IDs.
**Recommendation**: Add `Depends(get_current_user)` to both endpoints in `backend/routes/sla_tracking_routes.py`. The sibling endpoint `/api/v1/sla/dashboard/summary` already correctly requires auth — follow that pattern.
**Evidence**: `curl -s https://api.perenniaai.com/api/v1/sla/alerts` returns 200 with 50 records. `curl -s https://api.perenniaai.com/api/v1/sla/milestones/active` returns 200 with 58 records.

### [SLA-004] Two Disconnected SLA Systems
**Severity**: CRITICAL
**Category**: SLA
**Finding**: `sla_milestones_canonical.json` defines 27 milestones across 5 phases, but this file is NOT consumed by runtime code. `workflow_sla_service.py` relies entirely on `workflow_configurations` and `workflow_day_configs` database tables. Meanwhile, `CLAUDE.md` defines `SLA_TARGETS` with 7 loan-stage transitions that also don't connect to either system.
**Impact**: Three SLA truth sources with no bridge. Changes to the canonical JSON have zero runtime effect. SLA compliance reporting may not reflect actual workflow behavior.
**Recommendation**: Choose one source of truth. Either (a) load `sla_milestones_canonical.json` at startup and seed `workflow_configurations` from it, or (b) deprecate the JSON file and maintain config only in the database.
**Evidence**: `grep -r "sla_milestones_canonical" backend/services/` returns zero matches. The JSON is reference-only.

### [RL-004] No Automatic Loan-Side SLA Enrollment on Handoff
**Severity**: CRITICAL
**Category**: Routing / Workflow
**Finding**: When a lead transitions to `Disclosed`, the lead workflow engine creates a "set up loan file" task and starts an `active_loan_updates` drip, but does NOT call `WorkflowSLAService.enroll_loan()`. The loan-side SLA milestones (processing, third-party, underwriting, closing phases) are never automatically triggered.
**Impact**: All 19 loan-phase SLA milestones are effectively dead — they exist in config but never fire automatically. Loan officers must manually enroll each loan or these SLAs are never tracked.
**Recommendation**: In `lead_workflow_engine.py` `_handle_to_disclosed()` (line ~793), add a call to `WorkflowSLAService.enroll_loan(loan_id, workflow_type="active_loan")` after the loan file is created.
**Evidence**: `_handle_to_disclosed` in `lead_workflow_engine.py` does not reference `enroll_loan` or `WorkflowSLAService`.

### [SLA-003] Self-Referential and Broken Trigger Conditions
**Severity**: CRITICAL
**Category**: SLA
**Finding**: In `sla_milestones_canonical.json`, the `clear_to_close` milestone has `trigger_from: "Clear To Close"` — it triggers from itself, which is logically impossible. Additionally, `documents_received` triggers from `"Documents Requested"`, but the `documents_requested` milestone is marked **inactive**.
**Impact**: The `clear_to_close` SLA can never be triggered automatically. `documents_received` SLA deadline calculation depends on a milestone that will never fire.
**Recommendation**: Fix `clear_to_close.trigger_from` to reference the preceding milestone (`conditions_cleared`). Either reactivate `documents_requested` or change `documents_received.trigger_from` to `document_collection`.
**Evidence**: Lines in `sla_milestones_canonical.json`: `clear_to_close.trigger_from = "Clear To Close"`, `documents_requested.is_active = false`.

### [WF-005] Disclosed State is a Dead-End
**Severity**: CRITICAL
**Category**: Task Flow
**Finding**: `VALID_TRANSITIONS["Disclosed"] = ["Closed"]` — once a lead reaches `Disclosed`, the only valid transition is to `Closed`. If the deal falls through, there is no path back to `Pre-Approved`, `Long-Term Nurture`, or `Withdrawn`.
**Impact**: Leads whose loans fall apart after disclosure are trapped in the `Disclosed` stage with no legitimate recovery path. The only remedy is a manual database update.
**Recommendation**: Add recovery transitions: `"Disclosed": ["Closed", "Long-Term Nurture", "Withdrawn", "Does Not Qualify"]` in `lead_workflow_engine.py` `VALID_TRANSITIONS`.
**Evidence**: `VALID_TRANSITIONS` in `lead_workflow_engine.py`.

---

## Warnings

### [WF-001] Inconsistent Lead Stage Definitions Across Sources
**Severity**: WARNING
**Category**: Task Flow
**Finding**: Three separate definitions of lead stages disagree. `database/enums.py` has `APPLICATION_STARTED` and `DOCUMENT_FULFILLMENT`; `lead_workflow_engine.py` uses `Application` and `Referral Source` instead. The handler at line 157 checks for `"Application Started"` which doesn't exist in `VALID_TRANSITIONS`.
**Recommendation**: Align `lead_workflow_engine.py` `VALID_TRANSITIONS` with `database/enums.py` `LeadStage`. Remove dead handler code for `Application Started`/`Application Complete`.

### [WF-004] DNQ Re-Entry Has No Workflow Restart
**Severity**: WARNING
**Category**: Task Flow
**Finding**: `Does Not Qualify` can transition to `["Prospect", "Application"]` (re-entry), but there is no mechanism to re-trigger the intake workflow when a DNQ lead re-enters.
**Recommendation**: Add a hook in the `Prospect` handler to check if the lead was previously DNQ and re-enroll in the appropriate workflow.

### [WF-006] Dead Code: Application Started/Complete Handlers
**Severity**: WARNING
**Category**: Task Flow
**Finding**: Handlers at lines 157-168 in `lead_workflow_engine.py` check for `"Application Started"` and `"Application Complete"`, but neither string exists in `VALID_TRANSITIONS`. These handlers can never execute.
**Recommendation**: Remove the dead handlers or update `VALID_TRANSITIONS` to include these stages if they are still needed.

### [WF-007] Bidirectional Loop Risk
**Severity**: WARNING
**Category**: Task Flow
**Finding**: `Attempted Contact <-> Prospect <-> Application` creates a bidirectional loop. Rapid cycling would flood the LO with duplicate tasks. No guard exists to prevent infinite re-entry.
**Recommendation**: Add a cooldown mechanism or max-transition counter to prevent rapid cycling between states.

### [AT-004] Tasks Can Be Created With No User Assignment
**Severity**: WARNING
**Category**: Automation
**Finding**: If role resolution fails AND `lead.owner_id`/`loan.loan_officer_id` is NULL, the linked task in the `tasks` table is never created. The workflow task instance exists but is invisible in the UI.
**Recommendation**: Always create the linked task, even if unassigned. Add an "Unassigned" filter to the task dashboard.

### [RL-003] No Backpressure on Task Generation
**Severity**: WARNING
**Category**: Routing
**Finding**: `MAX_PENDING_TASKS_PER_USER = 50`. When all users for a role exceed capacity, the system still assigns to the first user. No alert or redistribution mechanism exists.
**Recommendation**: Add a Slack/email alert when any user exceeds 40 pending tasks.

### [RL-006] Partial Time-Based Rule Implementation
**Severity**: WARNING
**Category**: Routing
**Finding**: `application_incomplete` (48h) checks for stage `'Application Started'` which doesn't exist in `VALID_TRANSITIONS`. `preapproval_expiring` (720h / 30 days) has no handler implementation.
**Recommendation**: Fix the stage name to match `VALID_TRANSITIONS`. Implement the `preapproval_expiring` handler.

---

## SLA Compliance Summary

| Alert Type | Active Count | Oldest Overdue | Status |
|-----------|-------------|----------------|--------|
| Preapproval | 38 | 72 days (since 2025-12-12) | All overdue, none acknowledged |
| Lead Response | 12 | Unknown | All overdue, none acknowledged |
| **Total** | **50** | — | **0% acknowledged** |

58 active milestones — all in `overdue` status. Zero SLA alerts have been acknowledged or resolved.

## Task Distribution Analysis

SKIPPED — Requires authenticated access to `/api/v1/workflow/dashboard/summary`.

## Workflow Dependency Map

```
Lead Created
    |
    v
[New] --1hr--> ALERT: No Contact
    |  --4hr--> ESCALATE to Manager
    v
[Attempted Contact] --72hr--> Re-engagement
    |
    v
[Prospect] --14d--> Stalled Alert
    |
    v
[Application] --48hr--> Incomplete Alert (BROKEN: wrong stage name)
    |
    v
[Pre-Qualified] --> [Pre-Approved] --30d--> Expiring (NOT IMPLEMENTED)
    |
    v
[Under Contract] --> [Disclosed] --> [Closed] --> [AMR]
                          |
                          X  NO RECOVERY PATH (CRITICAL)
                          X  NO LOAN-SIDE SLA ENROLLMENT (CRITICAL)
```

## Skipped Checks

| Check | Reason |
|-------|--------|
| TH-001 through TH-006 | Auth required for live task health data |
| SR-001 through SR-005 | Auth required for SLA compliance rates |
| RD-001 through RD-005 | Auth required for task distribution data |
| TE-001 through TE-005 | No trigger execution log endpoint found |
