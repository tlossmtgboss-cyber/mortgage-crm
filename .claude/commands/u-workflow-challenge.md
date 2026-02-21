---
name: u-workflow-challenge
description: >
  Active Loan Workflow & SLA-Driven Task Generation Challenge. Use this skill whenever working on
  the connection between SLA milestone dates in the client profile (Important Dates tab), the SLA
  tracking engine, and the workflow task generation system. This covers: reading SLA dates from
  client profiles, calculating days elapsed per milestone, running the workflow engine to determine
  which tasks are due, creating/archiving/replacing workflow tasks, and assigning tasks to the
  correct users based on role routing. Trigger this skill for any work involving SLA date fields,
  workflow day progression, task creation from milestones, task routing to power dialer vs task
  screen, midnight cron task generation, or debugging why tasks are not being created from SLA dates.
---

# Active Loan Workflow & SLA-Driven Task Generation

## The Core Problem

SLA milestone dates live in the client profile's **Important Dates** tab. The **SLA Tracking Engine**
must read these dates, calculate where each loan stands in its workflow, and generate the correct
tasks for the responsible users. If any link in this chain breaks, tasks don't get created and
loans fall through the cracks.

This skill documents the complete data flow, every integration point, and the exact implementation
required to make it work end-to-end.

---

## Architecture Overview: The Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CLIENT PROFILE - IMPORTANT DATES TAB             │
│                                                                     │
│  These date fields are the SOURCE OF TRUTH for workflow triggers:   │
│                                                                     │
│  ┌─────────────────────────┬──────────────────────────────────┐    │
│  │ Milestone Date Field     │ What It Triggers                 │    │
│  ├─────────────────────────┼──────────────────────────────────┤    │
│  │ new_lead_date            │ Prospect workflow activation     │    │
│  │ attempted_contact_date   │ Attempted Contact workflow       │    │
│  │ pre_qual_date            │ Pre-Qual workflow                │    │
│  │ pre_approval_date        │ Pre-Approval workflow            │    │
│  │ application_received_date│ Application workflow             │    │
│  │ disclosed_date           │ LE Pending workflow              │    │
│  │ processing_date          │ In Processing workflow           │    │
│  │ uw_submission_date       │ Underwriting workflow            │    │
│  │ conditional_approval_date│ Approved w/ Conditions workflow  │    │
│  │ clear_to_close_date      │ CTC workflow                    │    │
│  │ closing_scheduled_date   │ Closing workflow                 │    │
│  │ funded_date              │ Post-Close / MUM workflow        │    │
│  │ suspended_date           │ Suspended workflow               │    │
│  └─────────────────────────┴──────────────────────────────────┘    │
│                                                                     │
│  When ANY of these dates gets stamped → workflow engine activates   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    SLA TRACKING ENGINE                               │
│                                                                     │
│  Reads Important Dates → Calculates days_elapsed per milestone     │
│  Compares against SLA targets → Flags approaching/overdue          │
│  Feeds into Workflow Engine for task generation                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW ENGINE (Cron - every 5 min)             │
│                                                                     │
│  For each active loan/lead:                                        │
│  1. Read current_milestone_status                                  │
│  2. Get milestone_entered_at from Important Dates                  │
│  3. Calculate days_elapsed = (now - milestone_entered_at).days     │
│  4. Look up workflow_configuration for this milestone              │
│  5. Find matching workflow_day_config for days_elapsed             │
│  6. Generate tasks for each communication method checked           │
│  7. Archive previous day's incomplete tasks                        │
│  8. Route tasks: phone → power dialer, email/text → task screen   │
│  9. Assign to correct user based on role + loan team               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    TASK SCREEN / POWER DIALER                       │
│                                                                     │
│  Users see their assigned tasks with:                              │
│  - Client name + loan details                                      │
│  - Task type (phone/email/text/internal)                           │
│  - Due date + priority                                             │
│  - Quick action buttons                                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Section 1: Important Dates — The Source of Truth

Read `references/important-dates-schema.md` for the complete database schema, field definitions,
and the mapping between date fields and workflow activations.

**Key rules:**
- When a milestone date is stamped, it means the loan entered that milestone at that moment
- The `current_milestone_status` on the loan/lead record tells the system WHICH workflow to run
- The corresponding date field tells the system WHEN the milestone started (for day calculation)
- Historical dates are preserved in `loan_milestone_history` for audit trails
- A date stamp in Important Dates is what triggers the SLA clock to start

---

## Section 2: SLA Tracking Engine — Reading the Dates

Read `references/sla-tracking-engine.md` for the complete SLA calculation logic, business day
handling, and compliance reporting integration.

**The SLA Tracker does three things:**
1. Reads each milestone date from the client profile
2. Calculates business days elapsed (excluding weekends + holidays)
3. Compares elapsed days against SLA targets to determine status:
   - `ON_TRACK` — within target
   - `APPROACHING` — within warning threshold (configurable, default 2 days before)
   - `OVERDUE` — past target deadline
   - `COMPLETED` — milestone was completed (next date stamped)

**SLA targets are configurable per user/team/company.** Each user sets their own SLA targets
during onboarding. If no custom SLA exists, system defaults apply.

---

## Section 3: Workflow Engine — Generating Tasks from Dates

Read `references/workflow-task-engine.md` for the complete task generation logic, the cron
scheduler design, idempotency handling, and task routing.

**This is where the rubber meets the road.** The Workflow Engine:

1. Runs every 5 minutes via cron (not just at midnight — handles multi-timezone)
2. For each organization that just crossed midnight in their timezone:
   a. Queries all active workflow instances
   b. For each instance, calculates `days_elapsed` from the Important Dates field
   c. Looks up the workflow day configuration for that day number
   d. Generates one task per communication method checked for that day
   e. Archives any incomplete tasks from the previous day
   f. Routes each task to the correct destination (power dialer vs task screen)
   g. Assigns to the correct user based on role mapping on the loan team

**Critical: If the Important Dates field is empty or null, the workflow engine has nothing to
calculate against and NO tasks will be generated.** This is the most common failure point.

---

## Section 4: Task Assignment & Routing

**Task routing rules:**
- Phone tasks → Power Dialer queue
- Email tasks → Task Screen
- Text/SMS tasks → Task Screen
- AI tasks → AI Queue (auto-execute at 95%+ confidence)
- Internal tasks → Task Screen (assigned to specific role)

**Role-based assignment:**
- Each loan has a `loan_team_members` table with role assignments
- When a task is generated for role "Processor", the system finds WHO holds that role on THIS loan
- If no specific user assigned to that role on the loan, falls to team-level default
- If no team default, falls to organization-level routing rules

---

## Section 5: The Complete Lifecycle — Step by Step

Here is exactly what happens when a loan moves to a new milestone:

### Step 1: Milestone Change Detected
Something triggers the milestone change:
- User manually updates status
- Online application received (auto-detection)
- Email parsed by AI with 95%+ confidence
- Document received that satisfies milestone criteria

### Step 2: Important Dates Updated
```python
# MilestoneService.change_milestone() — SINGLE entry point
entity.current_milestone_status = "IN_PROCESSING"
entity.current_milestone_entered_at = datetime.now(company_tz)

# Record in history
loan_milestone_history.insert({
    loan_id: entity.id,
    milestone_type: "IN_PROCESSING",
    started_at: datetime.now(company_tz),
    target_deadline: calculate_sla_deadline("IN_PROCESSING", user_sla_config),
    status: "IN_PROGRESS"
})
```

### Step 3: Previous Workflow Cancelled
```python
# Cancel all active tasks from the PREVIOUS milestone's workflow
previous_workflow_instance.status = "completed"
# All pending tasks under that instance → status = "cancelled"
```

### Step 4: New Workflow Activated
```python
# Find which workflow(s) apply to this milestone
workflows = get_workflows_for_milestone("IN_PROCESSING", loan)
for workflow in workflows:
    create_workflow_instance(
        loan=loan,
        workflow=workflow,
        started_at=entity.current_milestone_entered_at
    )
```

### Step 5: Day 1 Tasks Generated (Immediate or Next Cron Cycle)
```python
# Workflow engine reads the Important Dates field
milestone_start = entity.current_milestone_entered_at  # ← THIS IS THE KEY DATE
days_elapsed = business_days_between(milestone_start, now)

# Look up what tasks are configured for Day 1
day_config = workflow.day_configs.filter(day_number=days_elapsed)

# Generate tasks for each communication method
for method in day_config.communication_methods:
    create_task(
        loan=loan,
        task_type=method.type,        # phone, email, text, etc.
        assigned_to=resolve_user(loan, method.responsible_role),
        due_at=now,
        routed_to=determine_route(method.type),  # power_dialer or task_screen
        workflow_instance=instance,
        day_config=day_config
    )
```

### Step 6: Daily Progression
- Each midnight (in the org's timezone), the cron recalculates `days_elapsed`
- If Day 2 tasks exist and Day 1 tasks weren't completed → Day 1 tasks archived
- Day 2 tasks generated and assigned
- Cycle repeats until milestone changes or workflow completes

---

## Section 6: Debugging — Why Tasks Aren't Being Created

When tasks aren't being generated, check these in order:

### Check 1: Does the Important Dates field have a value?
```sql
SELECT id, current_milestone_status, current_milestone_entered_at
FROM loans
WHERE id = :loan_id;
```
If `current_milestone_entered_at` is NULL → **that's your problem.** The milestone change
didn't stamp the date. Fix: ensure ALL milestone changes go through `MilestoneService.change_milestone()`.

### Check 2: Does a workflow instance exist for this loan?
```sql
SELECT wi.*
FROM workflow_instances wi
WHERE wi.loan_id = :loan_id
  AND wi.status = 'active';
```
If no active instance → the workflow wasn't activated when the milestone changed.

### Check 3: Does a workflow configuration exist for this milestone?
```sql
SELECT wc.*
FROM workflow_configurations wc
WHERE wc.milestone_type = :current_milestone_status
  AND wc.is_active = true
  AND wc.organization_id = :org_id;
```
If no config → no one set up a workflow template for this milestone.

### Check 4: Does the day configuration have entries for the current day?
```sql
SELECT wdc.*
FROM workflow_day_configs wdc
WHERE wdc.workflow_id = :workflow_id
  AND wdc.day_number = :days_elapsed;
```
If no entries for this day number → no tasks are configured for this day.

### Check 5: Is the cron scheduler running?
```sql
SELECT MAX(created_at) as last_task_generated,
       NOW() - MAX(created_at) as time_since_last
FROM workflow_task_instances;
```
If `time_since_last` is hours old → the scheduler may have stopped.

### Check 6: Is the task being created but assigned to nobody?
```sql
SELECT wti.*, wti.assigned_to_user_id, wti.assigned_role
FROM workflow_task_instances wti
WHERE wti.workflow_instance_id = :instance_id
  AND wti.status = 'pending';
```
If `assigned_to_user_id` is NULL → role resolution failed. Check `loan_team_members`.

---

## Section 7: Database Tables Required

See `references/database-schema.md` for the complete CREATE TABLE statements, indexes,
constraints, enums, and seed data.

**Core tables for this flow:**

| Table | Purpose |
|-------|---------|
| `loans` / `leads` | Has `current_milestone_status` + `current_milestone_entered_at` |
| `loan_milestone_history` | Audit trail of all milestone transitions with timestamps |
| `sla_configurations` | Per-user/team/company SLA targets per milestone |
| `workflow_configurations` | Workflow templates (which milestones they cover) |
| `workflow_day_configs` | What happens on each day (communication methods, roles) |
| `workflow_instances` | Active workflow per loan (links loan ↔ workflow config) |
| `workflow_task_instances` | Individual generated tasks (the actual work items) |
| `loan_team_members` | Who holds what role on each loan (for task assignment) |
| `company_holidays` | Holiday calendar for business day calculations |

---

## Section 8: Implementation Checklist

Use this to validate the complete chain is wired correctly:

- [ ] **Important Dates fields exist** on `loans` and `leads` tables
- [ ] **MilestoneService** is the ONLY code path that writes milestone dates
- [ ] **Milestone change stamps the date** in `current_milestone_entered_at`
- [ ] **Milestone change records history** in `loan_milestone_history`
- [ ] **Milestone change cancels** previous workflow's pending tasks
- [ ] **Milestone change activates** new workflow instance
- [ ] **SLA configuration** exists for each milestone (per user or system default)
- [ ] **Workflow configuration** exists and is active for each milestone
- [ ] **Workflow day configs** are populated with communication methods + roles
- [ ] **Cron scheduler** is running (every 5 min, checks per-org timezone)
- [ ] **Day calculation** uses business days (excluding weekends + holidays)
- [ ] **Task generation** creates one task per communication method per day config
- [ ] **Task archival** archives previous day's incomplete tasks before generating new ones
- [ ] **Task routing** sends phone → power dialer, email/text → task screen
- [ ] **Task assignment** resolves the correct user from loan_team_members by role
- [ ] **Idempotency constraint** prevents duplicate task generation on re-runs
- [ ] **Holiday calendar** is populated for business day calculations
- [ ] **SLA status calculation** correctly flags ON_TRACK / APPROACHING / OVERDUE
- [ ] **Task completion** feeds back into SLA compliance tracking
