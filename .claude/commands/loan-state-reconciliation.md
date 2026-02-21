---
name: loan-state-reconciliation
description: >
  Ensures loan files in Perennia AI move to the correct pipeline category (Leads, Active Loans, or MUM)
  based on the current Salesforce Opportunity/Lead status. Use this skill whenever building, debugging,
  or extending the Salesforce sync engine, loan state transitions, pipeline category assignment,
  milestone-based routing, or status change webhooks. Also trigger when the user mentions loan files
  being in the wrong bucket, records not moving between pipelines, Salesforce status not reflected
  in the CRM, or any reconciliation between Salesforce stage values and Perennia AI pipeline categories.
  Covers: sync workers, state machine logic, transition validation, audit trails, and edge cases
  like suspensions, withdrawals, denials, and reactivations.
---

# Loan File State Reconciliation

This skill defines the authoritative rules for moving loan files between Perennia AI's three
pipeline categories—**Leads**, **Active Loans**, and **MUM** (Mortgages Under Management)—based
on the status synced from Salesforce.

## Why This Matters

Perennia AI's CRM organizes every borrower record into one of three pipelines. When a Salesforce
sync brings in a status change, the system must decide: does this record stay where it is, or does
it need to move? Getting this wrong means loan officers see stale data, workflows fire on the wrong
pipeline, and SLA tracking breaks. The rules below exist to prevent that.

---

## Pipeline Categories

| Category | What Lives Here | Salesforce Objects |
|---|---|---|
| **Leads** | Prospects not yet in active processing. Pre-application, pre-qualification, consultation phase. | `Lead`, `Opportunity` (early stages) |
| **Active Loans** | Loans with an active file in processing through funding. The "pipeline" in the traditional LO sense. | `Opportunity` (processing → funded stages) |
| **MUM** | Closed/funded loans under ongoing relationship management. Post-closing portfolio. | `Opportunity` (post-funding), `Contact` (long-term) |

---

## State Transition Rules

### Source of Truth

Salesforce `StageName` (on Opportunity) and `Status` (on Lead) are the **trigger fields**. When
the sync engine detects a change in either, it evaluates the transition rules below.

### Lead → Active Loan Transition

A record moves from Leads to Active Loans when Salesforce status indicates the borrower has
crossed from prospect into an actively processing loan file.

**Trigger conditions (ANY of these):**

```
Salesforce StageName IN:
  - "Contract Received"
  - "Submitted to Processing"
  - "In Processing"
  - "Application Submitted"
  - "Document Collection"
  - "Submitted to Underwriting"
  - "In Underwriting"
```

**OR** any of these Salesforce date fields become non-null:
```
  - Contract_Received_Date__c
  - Submitted_To_Processing_Date__c
  - Processing_Start_Date__c
  - Application_Submission_Date__c
```

**What happens on transition:**
1. Record moves from `leads` table to `active_loans` table
2. `lead.status` set to `"Converted to Active Loan"`
3. `active_loans.status` set to the mapped milestone (see Milestone Map below)
4. All lead-phase tasks marked complete or archived
5. Active loan workflow engine initializes (SLA timers, condition tracking, team assignment)
6. Audit log entry: `{ event: "pipeline_transition", from: "leads", to: "active_loans", trigger: "<sf_stage>", timestamp }`

**Validation before transition:**
- Borrower name, email, and loan amount must be populated
- If missing required fields, flag for manual review instead of auto-transitioning
- Check for duplicate active loans (same borrower + similar loan amount + property)

### Active Loan → MUM Transition

A record moves from Active Loans to MUM when the loan has funded and the file is complete.

**Trigger conditions (ANY of these):**

```
Salesforce StageName IN:
  - "Funded"
  - "Loan Funded"
  - "Closed"
  - "Closed Won"
  - "Post-Closing"
```

**OR** any of these Salesforce date fields become non-null:
```
  - Funding_Date__c
  - Funded_Date__c
  - Fund_Date__c
  - Loan_Funded_Date__c
```

**What happens on transition:**
1. Record moves from `active_loans` table to `mum_clients` table
2. `active_loans.status` set to `"Funded - Moved to MUM"`
3. `mum_clients.status` set to `"Active"`
4. Post-closing workflow initializes (thank you sequence, review request, referral nurture)
5. Servicing data fields populate (payment info, escrow, servicer)
6. SLA timers for active loan phase stop; portfolio monitoring begins
7. Audit log entry: `{ event: "pipeline_transition", from: "active_loans", to: "mum", trigger: "<sf_stage>", timestamp }`

**Validation before transition:**
- Funding date must be present
- Loan number must be assigned
- Final loan amount and rate must be populated
- All prior-to-funding conditions should be cleared (warn if not)

### Lead → MUM (Direct, Rare)

In some cases a record bypasses Active Loans entirely—for example, a past client imported
directly into MUM, or a referral partner whose existing loan was never tracked as active.

**Trigger:** Manual action or bulk import only. Never auto-transition Lead → MUM from Salesforce
status alone. Flag for review if Salesforce shows a Lead jumping directly to "Funded."

---

## Active Loan Status Mapping (Salesforce → Perennia Milestones)

When a Salesforce Opportunity stage changes, the active loan's internal milestone updates
accordingly. This determines which workflow rules fire, which SLA timers start, and what
the loan officer sees on their dashboard.

```
Salesforce StageName              → Perennia Milestone
─────────────────────────────────────────────────────────
"Contract Received"               → CONTRACT_RECEIVED
"Submitted to Processing"        → SUBMITTED_TO_PROCESSING
"In Processing"                  → LOAN_IN_PROCESSING
"Application Submitted"          → APPLICATION_SUBMITTED
"Document Collection"            → DOCUMENT_COLLECTION
"Documents Requested"            → DOCUMENTS_REQUESTED
"Documents Received"             → DOCUMENTS_RECEIVED
"Appraisal Ordered"              → APPRAISAL_ORDERED
"Appraisal Received"             → APPRAISAL_RECEIVED
"Insurance Ordered"              → INSURANCE_ORDERED
"Insurance Received"             → INSURANCE_RECEIVED
"Title Ordered"                  → TITLE_ORDERED
"Title Received"                 → TITLE_RECEIVED
"Submitted to Underwriting"      → LOAN_SUBMITTED_TO_UW
"In Underwriting"                → LOAN_IN_UW
"Underwriting Decision"          → UW_DECISION
"Approved"                       → LOAN_APPROVED
"Conditional Approval"           → LOAN_APPROVED  (substatus: "conditional")
"Conditions Cleared"             → CONDITIONS_CLEARED
"Clear to Close"                 → LOAN_CTC
"Closing Docs Out"               → CLOSING_DOCS_OUT
"Closing Scheduled"              → LOAN_CLOSING_SCHEDULED
"Closing Date"                   → LOAN_CLOSING_SCHEDULED
"Funded" / "Loan Funded"         → LOAN_FUNDED  (triggers → MUM transition)
```

### Handling Unmapped Stages

If the sync engine encounters a Salesforce `StageName` that doesn't match any mapping above:

1. Log a warning: `{ event: "unmapped_stage", stage: "<value>", opportunity_id: "<id>" }`
2. Do NOT change the loan's current milestone
3. Create an admin notification for the user to update their field mapping
4. Store the raw value in `active_loans.salesforce_raw_stage` for debugging

---

## Edge Cases & Special Statuses

### Suspended / On Hold
```
Salesforce StageName: "Suspended", "On Hold", "Paused"
```
- Record stays in its CURRENT pipeline (do not move it)
- Set `substatus = "suspended"`
- Pause all SLA timers
- Create reactivation task for loan officer
- AI generates suspension reason analysis if Salesforce notes field is populated

### Withdrawn / Cancelled
```
Salesforce StageName: "Withdrawn", "Cancelled", "Lost", "Closed Lost"
```
- If in **Leads**: Set `lead.status = "Withdrawn"`, archive record
- If in **Active Loans**: Set `active_loans.status = "Withdrawn"`, stop all workflows
- Do NOT move to MUM
- Create win-back nurture campaign task (optional, based on LO preference)
- Audit log with reason if available

### Denied
```
Salesforce StageName: "Denied", "Declined", "Adverse Action"
```
- If in **Active Loans**: Set `active_loans.status = "Denied"`
- Stop all active workflows
- Trigger compliance workflow (adverse action notice tracking)
- Do NOT move to MUM
- Create re-engagement task (6-month follow-up)

### Reactivation
```
A "Withdrawn", "Suspended", or "Denied" record that gets a new active stage in Salesforce
```
- If the record was in Active Loans and is still there: Clear the substatus, restart SLA timers
- If the record was archived from Leads: Restore to Leads with the appropriate new stage
- Log: `{ event: "reactivation", previous_status: "...", new_stage: "..." }`

### Backward Stage Movement
```
Example: Salesforce moves from "Clear to Close" back to "In Underwriting"
```
- This is valid (UW can pull a file back for re-review)
- Update milestone to the new (earlier) stage
- Restart SLA timers for the new stage
- Create alert for loan officer: "Loan moved backward from CTC to UW"
- Do NOT move between pipeline categories for backward movement within Active Loans

---

## Sync Engine Integration

### Where This Logic Lives

The state reconciliation runs inside the Salesforce sync worker, specifically in the
**post-transform, pre-upsert** phase:

```
Sync Flow:
1. Fetch modified records from Salesforce
2. Transform fields via user's field mapping
3. ★ RECONCILIATION STEP ★ — Evaluate transition rules (this skill)
4. Execute transitions (move records, update statuses)
5. Upsert remaining field changes
6. Fire workflow triggers
7. Log audit trail
```

### Reconciliation Function Signature

```typescript
interface ReconciliationResult {
  action: 'stay' | 'transition' | 'flag_for_review';
  from_pipeline?: 'leads' | 'active_loans' | 'mum';
  to_pipeline?: 'leads' | 'active_loans' | 'mum';
  new_milestone?: string;
  new_substatus?: string;
  validation_errors?: string[];
  audit_entry: AuditEntry;
}

function reconcileLoanState(
  currentRecord: CRMRecord,
  incomingSalesforceData: SalesforceRecord,
  transitionRules: TransitionRuleSet
): ReconciliationResult
```

### Conflict Resolution

When Salesforce data conflicts with the CRM's current state:

1. **Salesforce is source of truth for stage/status** — always accept the Salesforce stage
2. **CRM is source of truth for pipeline category** — only move pipelines if transition rules are met
3. **Timestamp wins for date fields** — if both have a value, use the most recent
4. **Never auto-delete** — transitions archive the old record, they don't delete it

### Idempotency

The reconciliation must be idempotent. If the sync runs twice with the same Salesforce data,
the second run should be a no-op. Achieve this by:

- Checking if the record is already in the target pipeline before transitioning
- Comparing the incoming stage against the current milestone (skip if unchanged)
- Using the audit log to detect if this transition already happened

---

## Monitoring & Alerts

### Dashboard Metrics to Track

- **Transition volume**: How many records moved between pipelines today/week/month
- **Stuck records**: Records that haven't progressed in stage for >X days
- **Unmapped stages**: Count of Salesforce stages not in the mapping table
- **Failed transitions**: Records that failed validation and were flagged for review
- **Reactivations**: Records that came back from withdrawn/denied/suspended

### Alert Conditions

| Condition | Severity | Action |
|---|---|---|
| Record stuck in same stage >14 days | Warning | Notify LO |
| Unmapped Salesforce stage detected | Info | Notify admin |
| Transition validation failed | High | Flag for manual review |
| Backward stage movement | Info | Notify LO |
| Direct Lead → Funded detected | Critical | Block transition, flag for admin |
| Bulk transitions (>50 in one sync) | Warning | Pause and verify before executing |

---

## Implementation Checklist

When building or modifying the reconciliation engine, verify:

- [ ] All 24+ Salesforce stage values are mapped (see Milestone Map above)
- [ ] Transition validation runs before any record move
- [ ] Audit log captures every transition with before/after state
- [ ] SLA timers start/stop correctly on transitions
- [ ] Suspended/Withdrawn/Denied records don't accidentally move to MUM
- [ ] Reactivation path works for all three special statuses
- [ ] Backward stage movement is handled gracefully
- [ ] Unmapped stages don't crash the sync — they log and skip
- [ ] Idempotency: double-sync doesn't create duplicates or double-transitions
- [ ] Bulk transition safety: large batches get paused for verification
- [ ] Post-transition workflows fire (welcome sequences, task creation, notifications)
- [ ] Field mapping transforms apply BEFORE reconciliation evaluates the stage

---

## Reference Files

- `references/transition-rules.yaml` — Machine-readable transition rule definitions
- `references/milestone-sla-config.yaml` — SLA windows for each milestone
- `scripts/reconciliation-engine.ts` — Reference implementation of the reconciliation function
- `scripts/audit-logger.ts` — Audit trail helper for transition events
