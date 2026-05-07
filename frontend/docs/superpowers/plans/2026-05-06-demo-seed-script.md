# Demo Seed Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `backend/seed_full_demo.py` — a standalone, idempotent Python script that creates the `demo@perenniaai.com` account with comprehensive CRM data across all features for product demos.

**Architecture:** Single-file script using raw SQL via `sqlalchemy.text()`. Connects via `DATABASE_URL` env var. Each section checks for existing data before inserting (idempotent). Sections run in dependency order: org → users → leads → loans → MUM → partners → tasks → docs → calendar → SMS → calls → activities → AI metrics → rates → workflows → borrower portal → content → chat → notifications.

**Tech Stack:** Python 3.11+, SQLAlchemy (text() only — no ORM), passlib/bcrypt for password hashing, standard library (datetime, random, json, os, sys).

---

## File Structure

| File | Purpose |
|------|---------|
| Create: `backend/seed_full_demo.py` | Main seed script (~2000-2500 lines). All data definitions and insert logic in one file. |

No new modules, no test files (this is a data script, not application code). Follows the pattern of existing `seed_demo_people.py`.

---

### Task 1: Script skeleton — DB connection, helpers, main entrypoint

**Files:**
- Create: `backend/seed_full_demo.py`

- [ ] **Step 1: Create the script with boilerplate, connection, and helper functions**

```python
#!/usr/bin/env python3
"""
Comprehensive Demo Data Seed Script
Creates demo@perenniaai.com with full CRM data for product demos.

Usage:
    DATABASE_URL=postgresql://... python seed_full_demo.py

Idempotent: safe to re-run. Checks existence before every insert.
"""

import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from passlib.context import CryptContext
from sqlalchemy import create_engine, text

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ============================================================================
# CONFIG
# ============================================================================

ORG_NAME = "Summit Home Loans"
ORG_SLUG = "summit-home-loans"
DEMO_EMAIL = "demo@perenniaai.com"
DEMO_PASSWORD = "Password1!"
NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


def days_ago(n):
    return NOW - timedelta(days=n)


def days_from_now(n):
    return NOW + timedelta(days=n)


def date_ago(n):
    return TODAY - timedelta(days=n)


def date_from_now(n):
    return TODAY + timedelta(days=n)


# ============================================================================
# DB CONNECTION
# ============================================================================

def get_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL environment variable required")
        sys.exit(1)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url)


def exists(conn, table, column, value):
    """Check if a row exists. Returns the row or None."""
    result = conn.execute(
        text(f"SELECT * FROM {table} WHERE {column} = :val LIMIT 1"),
        {"val": value},
    )
    return result.fetchone()


def get_id(conn, table, column, value):
    """Get the id of a row by a unique column, or None."""
    result = conn.execute(
        text(f"SELECT id FROM {table} WHERE {column} = :val LIMIT 1"),
        {"val": value},
    )
    row = result.fetchone()
    return row[0] if row else None


# ============================================================================
# MAIN
# ============================================================================

def main():
    engine = get_engine()
    print(f"🔌 Connecting to database...")

    with engine.connect() as conn:
        print("✅ Connected\n")

        org_id = seed_organization(conn)
        branch_id = seed_branch(conn, org_id)
        user_ids = seed_users(conn, org_id, branch_id)
        seed_impersonation_permissions(conn, user_ids)
        lead_ids = seed_leads(conn, org_id, user_ids)
        loan_ids = seed_loans(conn, org_id, user_ids, lead_ids)
        mum_ids = seed_mum_clients(conn, org_id, user_ids)
        partner_ids = seed_referral_partners(conn, org_id, user_ids, lead_ids)
        seed_tasks(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_documents(conn, org_id, user_ids, loan_ids)
        seed_calendar(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_sms_conversations(conn, org_id, user_ids, lead_ids)
        seed_call_intelligence(conn, org_id, user_ids, lead_ids)
        seed_activities_and_history(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_ai_metrics(conn, org_id)
        seed_rate_monitor(conn, org_id, mum_ids, loan_ids)
        seed_workflows_and_compliance(conn, org_id, user_ids, lead_ids, loan_ids)
        seed_borrower_portal(conn, org_id, lead_ids, loan_ids)
        seed_content_and_campaigns(conn, org_id, user_ids, lead_ids)
        seed_team_chat(conn, org_id, user_ids)
        seed_notifications(conn, org_id, user_ids)

        print("\n🎉 Demo seed complete!")
        print(f"   Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print(f"   Org:   {ORG_NAME}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script runs (connects and exits cleanly with no seed functions)**

Add stub functions for every `seed_*` call so the script is syntactically valid:

```python
def seed_organization(conn): pass
def seed_branch(conn, org_id): pass
def seed_users(conn, org_id, branch_id): pass
def seed_impersonation_permissions(conn, user_ids): pass
def seed_leads(conn, org_id, user_ids): pass
def seed_loans(conn, org_id, user_ids, lead_ids): pass
def seed_mum_clients(conn, org_id, user_ids): pass
def seed_referral_partners(conn, org_id, user_ids, lead_ids): pass
def seed_tasks(conn, org_id, user_ids, lead_ids, loan_ids): pass
def seed_documents(conn, org_id, user_ids, loan_ids): pass
def seed_calendar(conn, org_id, user_ids, lead_ids, loan_ids): pass
def seed_sms_conversations(conn, org_id, user_ids, lead_ids): pass
def seed_call_intelligence(conn, org_id, user_ids, lead_ids): pass
def seed_activities_and_history(conn, org_id, user_ids, lead_ids, loan_ids): pass
def seed_ai_metrics(conn, org_id): pass
def seed_rate_monitor(conn, org_id, mum_ids, loan_ids): pass
def seed_workflows_and_compliance(conn, org_id, user_ids, lead_ids, loan_ids): pass
def seed_borrower_portal(conn, org_id, lead_ids, loan_ids): pass
def seed_content_and_campaigns(conn, org_id, user_ids, lead_ids): pass
def seed_team_chat(conn, org_id, user_ids): pass
def seed_notifications(conn, org_id, user_ids): pass
```

Run: `cd backend && python -c "import seed_full_demo; print('syntax OK')"`
Expected: `syntax OK`

- [ ] **Step 3: Commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed script skeleton with DB connection and main entrypoint"
```

---

### Task 2: Organization, Branch, Users, and Impersonation

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** Check exact column names by reading:
- `backend/database/models/core.py` — Organization, Branch, User columns
- `backend/setup_demo_impersonation.py` — impersonation permission pattern
- `backend/database/models/permission.py` — UserPermission columns

- [ ] **Step 1: Implement `seed_organization()`**

Creates the "Summit Home Loans" organization. Check `organizations` table for exact columns by reading `database/models/core.py`. Must set: `name`, `slug`, `subscription_tier='enterprise'`, `timezone='America/New_York'`, `is_active=True`. Return `org_id`.

Idempotency: check `SELECT id FROM organizations WHERE slug = 'summit-home-loans'` first.

- [ ] **Step 2: Implement `seed_branch()`**

Creates "Charleston HQ" branch linked to org. Check `branches` table columns from `database/models/core.py`. Must set: `name`, `company`, `nmls_id='789012'`, `organization_id`. Return `branch_id`.

Idempotency: check by `nmls_id`.

- [ ] **Step 3: Implement `seed_users()`**

Create 7 users. Define the team data as a list of dicts at the top of the function:

```python
TEAM = [
    {"email": "demo@perenniaai.com", "first_name": "Alex", "last_name": "Rivera",
     "role": "manager", "title": "Branch Manager / SVP", "is_admin": True,
     "phone": "+18431005001", "nmls": "MLO-100501", "has_password": True},
    {"email": "sarah.chen@summithomeloans.com", "first_name": "Sarah", "last_name": "Chen",
     "role": "loan_officer", "title": "Senior Loan Officer",
     "phone": "+18431005002", "nmls": "MLO-100502"},
    {"email": "marcus.johnson@summithomeloans.com", "first_name": "Marcus", "last_name": "Johnson",
     "role": "loan_officer", "title": "Loan Officer",
     "phone": "+18431005003", "nmls": "MLO-100503"},
    {"email": "emily.park@summithomeloans.com", "first_name": "Emily", "last_name": "Park",
     "role": "processor", "title": "Senior Loan Processor",
     "phone": "+18431005004", "nmls": "MLO-100504"},
    {"email": "rachel.kim@summithomeloans.com", "first_name": "Rachel", "last_name": "Kim",
     "role": "underwriter", "title": "Senior Underwriter",
     "phone": "+18431005005", "nmls": "MLO-100505"},
    {"email": "james.mitchell@summithomeloans.com", "first_name": "James", "last_name": "Mitchell",
     "role": "underwriter", "title": "Underwriter",
     "phone": "+18431005006", "nmls": "MLO-100506"},
    {"email": "david.torres@summithomeloans.com", "first_name": "David", "last_name": "Torres",
     "role": "operations", "title": "Operations Manager",
     "phone": "+18431005007", "nmls": "MLO-100507"},
]
```

Check `users` table columns from `database/models/core.py`. Key columns: `email`, `hashed_password`, `full_name`, `first_name`, `last_name`, `role`, `organization_id`, `branch_id`, `manager_id`, `is_admin`, `account_status`, `phone`, `nmls_number`, `title`.

Only `demo@perenniaai.com` gets `hashed_password` set. Other users get NULL password (impersonation targets only). After inserting all users, do a second pass to set `manager_id` for non-manager users → Alex Rivera's ID.

Return a dict mapping role keys to user IDs: `{"manager": id, "lo_sarah": id, "lo_marcus": id, "processor": id, "uw_rachel": id, "uw_james": id, "ops": id}`.

Idempotency: check by email.

- [ ] **Step 4: Implement `seed_impersonation_permissions()`**

Follow the pattern in `setup_demo_impersonation.py`. Insert into `employee_permissions` table (if it exists) or `user_permissions` table. Grant the manager user these permissions: `team.impersonate`, `team.view_all`, `leads.view_all`, `loans.view_all`.

Check which permission table the codebase actually uses by reading `setup_demo_impersonation.py` line 67-73 pattern.

- [ ] **Step 5: Test locally**

Run: `DATABASE_URL=<local_or_railway_url> python seed_full_demo.py`
Expected: Organization, branch, 7 users created with emoji logging. Re-run should show "⏭️ Skipped" for each.

- [ ] **Step 6: Commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — org, branch, users, impersonation permissions"
```

---

### Task 3: Leads (25 across all stages, 12 months back)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** Check exact column names by reading:
- `backend/database/models/lead_loan.py` — Lead columns
- `backend/seed_demo_people.py:982-1027` — existing lead insert pattern

- [ ] **Step 1: Define lead data**

Create a `DEMO_LEADS` list with 25 entries. Each dict must have: `first_name`, `last_name`, `email`, `phone` (Charleston +1843 area), `stage`, `source`, `credit_score`, `annual_income`, `loan_amount`, `property_address`, `city` (Charleston area), `state` ("SC"), `ai_score`, `dti`, `notes`, `days_ago` (for `created_at`), `owner_key` ("lo_sarah" or "lo_marcus").

Stage distribution per spec:
- 3x New (0-7 days), 2x "Attempted Contact" (3-14 days), 3x Prospect (14-30 days)
- 3x "Pre-Qualified" (30-60 days), 2x "Pre-Approved" (45-75 days), 3x Application (60-90 days)
- 3x "Long-Term Nurture" (180-365 days), 2x "Credit Repair" (90-180 days)
- 2x Funded (90-180 days ago), 1x "Does Not Qualify" (120 days), 1x Withdrawn (60 days)

Use real Charleston-area street names: "Meeting St", "King St", "Broad St", "East Bay St", "Calhoun St", "Ashley Ave", "Folly Rd", "Coleman Blvd", "Savannah Hwy", "Rivers Ave", etc. SC zip codes: 29401-29492.

Sources: Zillow, Realtor.com, Referral, Website, Facebook, Cold Call (mixed).

- [ ] **Step 2: Implement `seed_leads()`**

Loop through `DEMO_LEADS`, check existence by email, insert with all fields. Set `organization_id`, `owner_id` from `user_ids[lead["owner_key"]]`. Calculate `ltv` from `loan_amount / property_value`. Set `created_at` using `days_ago(lead["days_ago"])`. Set `first_contact_attempt_date`, `application_started_date`, `preapproval_issued_date` where stage-appropriate.

Return a dict mapping lead email → lead ID (query back after inserts).

Commit after all inserts: `conn.commit()`.

- [ ] **Step 3: Test**

Run script. Expected: 25 leads created with stage distribution logged.

- [ ] **Step 4: Commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — 25 leads across all pipeline stages"
```

---

### Task 4: Loans (15 total — 10 active, 5 funded)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** Check exact column names by reading:
- `backend/database/models/lead_loan.py` — Loan columns
- `backend/seed_demo_people.py:1037-1079` — existing loan insert pattern

- [ ] **Step 1: Define loan data**

Create a `DEMO_LOANS` list with 15 entries. Each dict: `loan_number` (SHL-2026-XXXX), `lead_email` (links to a lead from Task 3), `stage`, `loan_amount`, `rate`, `term`, `loan_type` (Conventional/FHA/VA/USDA), `loan_purpose` (Purchase/Refinance), `property_value`, `appraisal_value`, `ltv`, `dti`, `days_ago` (created_at offset), `closing_days_from_now` (for active) or `funded_days_ago` (for funded), `processor_key` / `underwriter_key` (which team member handles it).

Active loan stages: APPLICATION(2), PROCESSING(2), SUBMITTED(1), UNDERWRITING(2), CONDITIONAL_APPROVAL(1), CLEAR_TO_CLOSE(1), CLOSING(1).
Funded: 5 loans at stage "FUNDED" with `funded_date` set 3-12 months ago.

- [ ] **Step 2: Implement `seed_loans()`**

Loop through `DEMO_LOANS`. Link each loan to its lead via `lead_email` → `lead_ids[email]`. Set `loan_officer_id` from the lead's owner. Set `organization_id`. For funded loans, set `funded_date`. For active loans, set `closing_date` in the future.

Return dict mapping `loan_number` → loan ID.

- [ ] **Step 3: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — 15 loans across pipeline stages"
```

---

### Task 5: MUM Clients (15, spanning 1-10 years)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** Check exact column names by reading:
- `backend/database/models/referral.py` — MUMClient columns
- `backend/seed_demo_people.py` — existing MUM create pattern

- [ ] **Step 1: Define MUM client data**

15 clients. Each: `first_name`, `last_name`, `email`, `phone`, `years_ago` (1-10), `original_loan_amount` ($150K-$500K), `original_rate` (period-appropriate: 2016≈3.5%, 2019≈3.75%, 2020≈2.75%, 2022≈5.5%, 2024≈6.5%), `loan_type`, `term` (15 or 30), `servicer`, `engagement_score` (40-95).

Calculate `current_balance` using basic amortization. Calculate `property_value` with 3-6% annual appreciation. Set `last_contact_date` — some recent (good engagement), some 6+ months ago (stale — refi outreach candidates).

- [ ] **Step 2: Implement `seed_mum_clients()`**

Insert into `mum_clients` table. Check existence by email. Set `organization_id`. Calculate `monthly_payment` (PITI). Flag `refi_eligible` where current rate > 6.5% + 0.5%.

Return list of MUM client IDs.

- [ ] **Step 3: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — 15 MUM clients spanning 10 years"
```

---

### Task 6: Referral Partners (8 with referral→lead linkage)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** `backend/database/models/referral.py` — ReferralPartner columns

- [ ] **Step 1: Define partner data and implement `seed_referral_partners()`**

8 partners per spec. Insert into `referral_partners` table. Set `total_referrals`, `closed_deals`, `pipeline_value`. For Gold tier partners (Jennifer Walsh, Amanda Foster, Nicole Williams), update 3-5 leads to set `referral_partner_id` and `source='Referral'`.

Return dict of partner name → ID.

- [ ] **Step 2: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — 8 referral partners with lead linkage"
```

---

### Task 7: Tasks (30 across team)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** `backend/database/models/task.py` — Task columns

- [ ] **Step 1: Define task data and implement `seed_tasks()`**

30 tasks with realistic titles tied to lead/loan names. Mix:
- 5 overdue (due_date 1-5 days ago, status='pending')
- 8 due today (due_date=today, status='pending' or 'in_progress')
- 10 upcoming (due_date 1-7 days from now, status='pending')
- 7 completed (completed_at within last 7 days, status='completed')

Distribute `owner_id` across team. Link to leads/loans via `lead_id`/`loan_id`. Set `priority` (critical/high/medium/low), `source` (Workflow/AI Engine/Manual).

- [ ] **Step 2: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — 30 tasks across team members"
```

---

### Task 8: Documents (40 across loans)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** `backend/database/models/document.py` — Document columns

- [ ] **Step 1: Implement `seed_documents()`**

For each active/funded loan, create 3-6 document records. Types: W-2, Paystub, 1040, Bank Statement, Appraisal, Title Report, Insurance Binder, Purchase Agreement, Driver's License. Status mix: approved (60%), pending_review (25%), outstanding (15%).

Set `file_url` as placeholder: `https://docs.summithomeloans.com/demo/{loan_number}/{doc_type}.pdf`. Set `uploaded_by_id`, `classification_confidence` (0.85-0.99).

- [ ] **Step 2: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — 40 documents across loans"
```

---

### Task 9: Calendar & Appointments (20)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:**
- `backend/database/models/scheduler.py` — SchedulerConfig, SchedulerAppointmentType, Appointment, BookingLink, BlockedTime, AvailabilitySlot columns
- `backend/database/models/communication.py` — CalendarEvent columns

- [ ] **Step 1: Implement `seed_calendar()`**

Sub-steps:
1. Create `SchedulerConfig` for the org (timezone, business hours 9-5 ET)
2. Create 4 `SchedulerAppointmentType` records (Consultation 30min, Document Review 15min, Closing 60min, Team Meeting 30min)
3. Create `BookingLink` for each LO
4. Create `RecurringAvailability` Mon-Fri 9-5 for each user
5. Create 2-3 `BlockedTime` records (PTO, lunch)
6. Create 20 appointments spread across past week, this week, next 2 weeks. Link to leads/loans where applicable. Set status (completed for past, confirmed for future).

- [ ] **Step 2: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — calendar config, appointments, availability"
```

---

### Task 10: SMS Conversations (10 threads)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** `backend/database/models/communication.py` — SMSConversation, SMSMessage columns

- [ ] **Step 1: Implement `seed_sms_conversations()`**

Create 10 `SMSConversation` records linked to leads. For each, create 3-8 `SMSMessage` records alternating inbound/outbound with realistic mortgage-related content. Categories: scheduling (3), document_request (2), status_update (2), rate_inquiry (2), general (1). Set `ai_suggested_response` and `confidence_score` on pending items.

- [ ] **Step 2: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — 10 SMS conversation threads"
```

---

### Task 11: Call Intelligence (8 analyzed calls)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:**
- `backend/vapi_models.py` — VapiCall, VapiCallNote columns
- Check if call intelligence uses a different model: `grep -n "class.*Session" backend/routes/ci_voice_routes.py`

- [ ] **Step 1: Implement `seed_call_intelligence()`**

Determine which table(s) call intelligence sessions use (could be `vapi_calls`, `call_monitoring_sessions`, or similar). Create 8 call records: 3 inbound (AI receptionist), 3 outbound (LO follow-up), 2 voicemail drops.

Each gets: `transcript` (20-50 lines of realistic mortgage conversation), `ai_summary`, `sentiment`, `duration`. For inbound calls, include caller identification and routing data. Create associated `VapiCallNote` or artifact records.

- [ ] **Step 2: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — 8 call intelligence sessions with transcripts"
```

---

### Task 12: Activities & Stage History (100+ records)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** `backend/database/models/communication.py` — Activity, StageHistory columns

- [ ] **Step 1: Implement `seed_activities_and_history()`**

For each lead: create 3-10 `Activity` records (call, email_sent, email_received, note, sms_sent, meeting, document_uploaded, stage_change). Timestamps progress from lead creation to present.

For each lead: create `StageHistory` records tracing the path from "New" to current stage. For funded leads: full chain New→Prospect→Pre-Qualified→Pre-Approved→Application→Funded.

For each loan: create 2-5 activity records and `StageHistory` from APPLICATION through current stage.

- [ ] **Step 2: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — activities and stage history"
```

---

### Task 13: AI Metrics & Dashboard (30-day snapshots)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** `backend/database/models/ai.py` — AIPerformanceDaily, AIMetricsDaily columns. Also check `backend/ai_receptionist_dashboard_models.py` for AIReceptionistMetricsDaily.

- [ ] **Step 1: Implement `seed_ai_metrics()`**

Create 30 rows each for:
- `AIPerformanceDaily` / `AIMetricsDaily`: tasks_completed (5-15, trending up), actions_approved (3-10), feedback_quality_avg (0.78-0.92)
- `AIReceptionistMetricsDaily` (if table exists): total_conversations (3-8), appointments_scheduled (1-3), escalations (0-2)

Use slight daily variance with an upward trend to make charts look realistic.

- [ ] **Step 2: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — 30 days of AI performance metrics"
```

---

### Task 14: Rate Monitor (market data + refi opportunities)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** `backend/database/models/rate_lock.py` — RateLock, RateMarketData columns. Also `backend/database/models/refinance_intelligence.py` — RefiOpportunity columns.

- [ ] **Step 1: Implement `seed_rate_monitor()`**

Sub-steps:
1. Insert 30 days of `RateMarketData` — daily snapshots for 30yr Fixed (~6.75%), 15yr Fixed (~6.125%), FHA 30yr (~6.375%), VA 30yr (~6.25%), 5/1 ARM (~6.0%). Apply ±0.125% random daily variance.
2. Create 5 `RateLock` records on active loans (some locked, some expired, some monitoring).
3. Create 5 `RefiOpportunity` records linked to MUM clients with high rates. Status: identified(2), contacted(2), in_progress(1). Calculate estimated savings.

- [ ] **Step 2: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — rate monitor data and refi opportunities"
```

---

### Task 15: Workflows & Compliance

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:**
- `backend/database/models/workflow.py` — Workflow, WorkflowExecution columns
- `backend/database/models/compliance.py` — DisclosureEvent, ComplianceAlert columns
- `backend/database/models/security.py` — AuditLog columns
- `backend/database/models/tcpa_smart_docs.py` — SmartDocsConsentRecord columns

- [ ] **Step 1: Implement `seed_workflows_and_compliance()`**

Sub-steps:
1. Create 3 `Workflow` definitions (Lead Nurture, Underwriting, Post-Closing). Create 5 `WorkflowExecution` records: 2 lead nurture (active), 2 underwriting (active), 1 post-closing (completed).
2. Create 50 `AuditLog` records: logins, data changes, permission grants over 90 days.
3. Create 10 `DisclosureEvent` records across loans (LE sent, CD sent, signed).
4. Create 5 `ComplianceAlert` records (2 resolved, 3 pending).
5. Create 8 `SmartDocsConsentRecord` records for borrower doc consent.

- [ ] **Step 2: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — workflows, audit logs, compliance records"
```

---

### Task 16: Borrower Portal (profiles + applications)

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** `backend/database/models/borrower.py` — BorrowerProfile, BorrowerApplication, ApplicationEvent columns

- [ ] **Step 1: Implement `seed_borrower_portal()`**

Create 5 `BorrowerProfile` records linked to leads with active loans. Provider mix: email(3), google(1), apple(1). Marketing consent: 4 opted in, 1 out.

Create 5 `BorrowerApplication` records: 2 submitted, 1 in_progress (60%), 1 draft, 1 completed. Each gets 3-5 `ApplicationEvent` records (step_started, step_completed, etc.).

Create 2 `CoborrowerInvitation` records (1 accepted, 1 pending).

- [ ] **Step 2: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — borrower profiles and applications"
```

---

### Task 17: Content, Campaigns & Team Chat

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:**
- `backend/database/models/marketing.py` — AudienceSegment, CampaignDefinition, DripSequence columns
- `backend/database/models/aria_campaign.py` — AriaCampaign, AriaCampaignRecipient columns
- `backend/database/models/team_chat.py` — TeamChatChannel, TeamChatMessage columns

- [ ] **Step 1: Implement `seed_content_and_campaigns()`**

Create 2 `AriaCampaign` records: 1 completed (rate drop alert, 15 recipients), 1 in-progress (holiday greeting, 10 recipients). Create associated `AriaCampaignRecipient` records linked to leads.

Create 2 `DripSequence` records: new lead nurture (5 steps over 14 days), post-close follow-up (3 steps over 90 days).

- [ ] **Step 2: Implement `seed_team_chat()`**

Create 4 `TeamChatChannel` records: #general, #deals, #underwriting, #ops. For each, create 10 `TeamChatMessage` records with realistic mortgage team content, timestamps spread across recent days, authored by various team members.

- [ ] **Step 3: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — campaigns, drip sequences, team chat"
```

---

### Task 18: Notifications & Alerts

**Files:**
- Modify: `backend/seed_full_demo.py`

**Reference:** `backend/database/models/security.py` — Notification, SystemAlert columns

- [ ] **Step 1: Implement `seed_notifications()`**

Create 15 `Notification` records for the manager user (unread). Types: new_lead_assigned, document_uploaded, rate_lock_expiring, task_overdue, loan_stage_changed, team_member_activity, compliance_alert, appointment_reminder. Timestamps spread across last 24 hours.

Create 5 `SystemAlert` records: integration health check, rate threshold breach, SLA warning, storage usage, scheduled maintenance. Mix of active and resolved.

- [ ] **Step 2: Test and commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: demo seed — notifications and system alerts"
```

---

### Task 19: Final integration test and cleanup

**Files:**
- Modify: `backend/seed_full_demo.py`

- [ ] **Step 1: Run full script end-to-end**

Run: `DATABASE_URL=<url> python seed_full_demo.py`
Expected: All 20 sections complete without errors. Each section logs creation counts.

- [ ] **Step 2: Run idempotency test**

Run the script again. Expected: All sections log "⏭️ Skipped" for existing records. No duplicates created.

- [ ] **Step 3: Verify via API**

Log in as `demo@perenniaai.com` / `Password1!` at `app.perenniaai.com`. Verify:
- Dashboard shows pipeline metrics, tasks, production data
- Leads page shows 25 leads across stages
- Loans page shows active/funded loans
- Referral Partners page shows 8 partners
- Tasks page shows overdue/today/upcoming/completed
- Calendar shows appointments
- Smart Docs shows documents pending review

- [ ] **Step 4: Final commit**

```bash
git add backend/seed_full_demo.py
git commit -m "feat: comprehensive demo seed script — all CRM features populated"
```

---

### Task 20: Update demo cheat sheet

**Files:**
- Modify: `demo-cheat-sheet.md`

- [ ] **Step 1: Update login credentials and add impersonation instructions**

Update the cheat sheet to reference the new demo account:
- Login: `demo@perenniaai.com` / `Password1!`
- Org: Summit Home Loans
- Add section on impersonation: how to switch between team member views

- [ ] **Step 2: Commit**

```bash
git add demo-cheat-sheet.md
git commit -m "docs: update demo cheat sheet with new demo account"
```
