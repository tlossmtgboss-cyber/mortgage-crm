# Demo Account Seed — Design Spec

**Date:** 2026-05-06
**Goal:** Create a comprehensive demo account (`demo@perenniaai.com` / `Password1!`) with realistic seed data across every CRM feature, enabling full product demos and presentations.

---

## 1. Script Architecture

**File:** `backend/seed_full_demo.py`
**Execution:** `python seed_full_demo.py` (standalone, connects via `DATABASE_URL`)
**Idempotency:** Safe to re-run. Every insert checks existence first (by email, loan_number, or unique key). Re-running resets stale data where appropriate.
**Dependencies:** `DATABASE_URL` env var (Railway or local PostgreSQL). No other env vars required — password is hardcoded for the demo account.
**Pattern:** Raw SQL via `sqlalchemy.text()` for performance. Follows existing `seed_demo_people.py` conventions: emoji logging, existence checks, explicit commits per section.

### Execution Order (dependency chain)

```
1. Organization ("Summit Home Loans")
2. Branch ("Charleston HQ")
3. Users (7 team members — manager, 2 LOs, processor, 2 underwriters, ops)
4. Permissions & role assignments
5. Leads (25 across all stages, 12 months back)
6. Loans (15 total: 10 active, 5 funded)
7. MUM Clients (15, spanning 1-10 years back)
8. Referral Partners (8, with referral→lead linkage)
9. Tasks (30 across team, mixed statuses)
10. Documents (40 across loans, mixed review states)
11. Calendar & Appointments (20, ±2 weeks)
12. SMS Conversations (10 threads with messages)
13. Call Intelligence Sessions (8 analyzed calls)
14. Activities & Stage History (100+ timeline entries)
15. AI Metrics & Dashboard Data (30-day daily snapshots)
16. Rate Monitor (market data + 5 refi opportunities)
17. Workflows & Compliance (executions, audit logs, disclosures)
18. Borrower Portal (applications, borrower profiles)
19. Content & Campaigns (templates, drip sequences)
20. Notifications & System Alerts
```

---

## 2. Organization & Users

### Organization

| Field | Value |
|-------|-------|
| name | Summit Home Loans |
| slug | summit-home-loans |
| subscription_tier | enterprise |
| timezone | America/New_York |
| is_active | true |

### Branch

| Field | Value |
|-------|-------|
| name | Charleston HQ |
| company | Summit Home Loans |
| nmls_id | 789012 |

### Team (7 users)

| Role | Name | Email | Title |
|------|------|-------|-------|
| Manager | Alex Rivera | demo@perenniaai.com | Branch Manager / SVP |
| Loan Officer | Sarah Chen | sarah.chen@summithomeloans.com | Senior Loan Officer |
| Loan Officer | Marcus Johnson | marcus.johnson@summithomeloans.com | Loan Officer |
| Processor | Emily Park | emily.park@summithomeloans.com | Senior Loan Processor |
| Underwriter | Rachel Kim | rachel.kim@summithomeloans.com | Senior Underwriter |
| Underwriter | James Mitchell | james.mitchell@summithomeloans.com | Underwriter |
| Operations | David Torres | david.torres@summithomeloans.com | Operations Manager |

- **Only `demo@perenniaai.com` has a login password** (`Password1!`, hashed with bcrypt)
- `demo@perenniaai.com` has `is_admin=True`, `role=manager`, `manager_id=NULL`
- `demo@perenniaai.com` gets **impersonation permissions** (`team.impersonate`, `team.view_all`, `leads.view_all`, `loans.view_all`) — presenter switches into any team member's view without logging out
- Other 6 users are impersonation targets only (no password, no direct login)
- LOs, processor, underwriters, ops have `manager_id` → Alex Rivera
- Each user gets an NMLS number, phone number, and realistic profile
- Each role has role-appropriate data: LOs own their leads/loans, processor has processing queue items, underwriters have UW queue, ops has compliance/doc tasks

---

## 3. Leads (25 total, 12 months back)

Distributed across stages to fill the pipeline kanban:

| Stage | Count | Age Range | Owner Split |
|-------|-------|-----------|-------------|
| New | 3 | 0-7 days | Sarah (2), Marcus (1) |
| Attempted Contact | 2 | 3-14 days | Marcus (1), Sarah (1) |
| Prospect | 3 | 14-30 days | Sarah (1), Marcus (2) |
| Pre-Qualified | 3 | 30-60 days | Sarah (2), Marcus (1) |
| Pre-Approved | 2 | 45-75 days | Sarah (1), Marcus (1) |
| Application | 3 | 60-90 days | Sarah (2), Marcus (1) |
| Long-Term Nurture | 3 | 6-12 months | Sarah (1), Marcus (2) |
| Credit Repair | 2 | 3-6 months | Marcus (1), Sarah (1) |
| Funded (converted) | 2 | 3-6 months ago | Sarah (1), Marcus (1) |
| Does Not Qualify | 1 | 4 months ago | Marcus |
| Withdrawn | 1 | 2 months ago | Sarah |

### Lead Data Fields (all populated)

- `first_name`, `last_name` — realistic names
- `email` — `firstname.lastname@example.com`
- `phone` — `+1843XXXXXXX` (Charleston area)
- `source` — mix: Zillow, Realtor.com, Referral, Website, Facebook, Cold Call
- `credit_score` — 620-795 range
- `annual_income` — $55,000-$185,000
- `loan_amount` — $180,000-$650,000
- `property_address` — real Charleston-area street names, SC zip codes
- `ai_score` — 35-95
- `dti` — 28-45%
- `notes` — 1-2 sentence context per lead
- `first_contact_attempt_date`, `application_started_date`, `preapproval_issued_date` — set where stage-appropriate
- `referral_partner_id` — set for referral-sourced leads (linked to partner records)
- `organization_id`, `owner_id` — properly set

---

## 4. Loans (15 total)

### Active Loans (10, within 3 months)

| Stage | Count | Assigned To |
|-------|-------|-------------|
| APPLICATION | 2 | Emily (processor) |
| PROCESSING | 2 | Emily |
| SUBMITTED | 1 | Emily |
| UNDERWRITING | 2 | Rachel (1), James (1) |
| CONDITIONAL_APPROVAL | 1 | Rachel |
| CLEAR_TO_CLOSE | 1 | Emily |
| CLOSING | 1 | David (ops) |

### Funded Loans (5, 3-12 months ago)

All at stage `FUNDED` with `funded_date` set.

### Loan Data Fields (all populated)

- `loan_number` — `SHL-2026-XXXX`
- `lead_id` — linked to corresponding lead
- `loan_officer_id` — Sarah or Marcus
- `loan_amount` — $180,000-$650,000
- `rate` — 5.875%-7.25% (Numeric)
- `term` — 15 or 30
- `loan_type` — Conventional, FHA, VA, USDA mix
- `loan_purpose` — Purchase (70%), Refinance (30%)
- `property_value` — loan_amount / (1 - down_payment_pct)
- `appraisal_value` — ±2% of property_value
- `ltv` — 75-97%
- `dti` — 28-45%
- `credit_score` — from linked lead
- `property_address` — from linked lead
- `closing_date` — future for active, past for funded
- `created_at` — staggered over 3 months
- `encompass_loan_id` — NULL (no LOS sync in demo)
- `organization_id` — Summit Home Loans

---

## 5. MUM Clients (15, spanning 1-10 years)

Past borrowers for the Manage/Upsell/Maintain portfolio:

| Loan Age | Count | Scenario |
|----------|-------|----------|
| 1-2 years | 4 | Recent closings, high engagement |
| 3-5 years | 6 | Mid-life, some refi candidates |
| 6-10 years | 5 | Long-term, equity-rich, refi opportunities |

### MUM Data Fields

- `first_name`, `last_name`, `email`, `phone`
- `original_loan_date` — 1-10 years back
- `original_loan_amount` — $150,000-$500,000
- `original_rate` — period-appropriate (2016: ~3.5%, 2020: ~2.75%, 2024: ~6.5%)
- `current_balance` — amortized from original
- `property_value` — appreciated 3-6% annually from purchase
- `loan_type` — Conventional, FHA, VA mix
- `term` — 15 or 30
- `monthly_payment` — PITI calculated
- `servicer` — "Summit Home Loans Servicing" or "NewRez"
- `engagement_score` — 40-95
- `last_contact_date` — varies (some recent, some stale for outreach demos)
- `refi_eligible` — true for clients where current rate > market + 0.5%

---

## 6. Referral Partners (8)

| Name | Company | Type | Tier | Referrals |
|------|---------|------|------|-----------|
| Jennifer Walsh | Walsh Realty Group | Realtor | Gold | 12 |
| Michael Thornton | Thornton & Associates | Attorney | Silver | 5 |
| Lisa Patel | Lowcountry Insurance | Insurance Agent | Bronze | 3 |
| Robert Kim | Kim Financial Advisory | Financial Advisor | Silver | 7 |
| Amanda Foster | Coastal Builders Inc | Builder | Gold | 9 |
| Chris Martinez | Martinez CPA Group | CPA | Bronze | 2 |
| Nicole Williams | Carolina Real Estate | Realtor | Gold | 15 |
| Daniel Brooks | Brooks Law Firm | Attorney | Silver | 4 |

- Each partner has `total_referrals`, `closed_deals`, `pipeline_value` populated
- Gold tier partners have referral→lead linkages (some leads sourced from them)
- Mix of active/high-engagement and lower-activity partners

---

## 7. Tasks (30 total)

Distributed to show a realistic workload:

| Status | Count | Examples |
|--------|-------|---------|
| Overdue | 5 | "Follow up with Sarah Thompson — docs outstanding 3 days", "Review appraisal for Henderson file" |
| Due Today | 8 | "Call back James Wilson re: rate lock decision", "Send pre-approval letter to Chen" |
| Upcoming (3-7 days) | 10 | "Schedule closing for Martinez loan", "Request updated paystubs from Rivera" |
| Completed (last 7 days) | 7 | "Sent rate lock confirmation to Brooks", "Verified employment for Patel" |

- Tasks linked to leads/loans via `lead_id`/`loan_id`
- `owner_id` distributed across team (manager sees all, LOs see theirs)
- `priority` mix: 3 critical, 7 high, 12 medium, 8 low
- `source` mix: Workflow (40%), AI Engine (30%), Manual (30%)
- `sla_milestone_type` set where applicable

---

## 8. Documents (40 across loans)

Each active/funded loan gets 3-6 documents:

| Category | Types | Status Mix |
|----------|-------|------------|
| Income | W-2, Paystubs, Tax Returns (1040) | Approved (60%), Pending Review (25%), Outstanding (15%) |
| Assets | Bank Statements, Investment Accounts | Approved (50%), Pending (30%), Outstanding (20%) |
| Property | Appraisal, Title Report, Insurance | Approved (40%), Pending (40%), Outstanding (20%) |
| Legal | Purchase Agreement, Disclosures | Approved (70%), Pending (30%) |
| Identity | Driver's License, SSN Verification | Approved (80%), Pending (20%) |

- `file_url` — placeholder S3-style URLs (`https://docs.summithomeloans.com/demo/...`)
- `uploaded_by_id` — borrower (via portal) or LO
- `classification_confidence` — 0.85-0.99 for AI-classified docs
- Outstanding docs generate tasks in the task queue

---

## 9. Calendar & Appointments (20)

| Timeframe | Count | Types |
|-----------|-------|-------|
| Past week | 5 | Completed consultations, closing meetings |
| This week | 8 | Discovery calls, doc review meetings, team standup |
| Next week | 5 | Pre-approval meetings, closing prep, partner lunch |
| Next 2 weeks | 2 | Closing appointments |

- Appointment types: Consultation (30 min), Document Review (15 min), Closing (60 min), Team Meeting (30 min)
- Linked to leads/loans where applicable
- Booking links created for both LOs
- Availability slots seeded (Mon-Fri 9-5 for each user)
- 2-3 blocked time periods (PTO, lunch blocks)

---

## 10. SMS Conversations (10 threads)

| Category | Count | Status |
|----------|-------|--------|
| Scheduling | 3 | 1 pending, 1 auto-responded, 1 completed |
| Document Request | 2 | 1 pending, 1 in_progress |
| Status Update | 2 | 1 completed, 1 pending |
| Rate Inquiry | 2 | 1 auto-responded, 1 pending |
| General | 1 | completed |

- Each thread has 3-8 messages (mix of inbound/outbound)
- `ai_suggested_response` populated on pending items
- `confidence_score` varies (65-95)
- Linked to leads via phone number

---

## 11. Call Intelligence (8 analyzed calls)

| Type | Count | Duration |
|------|-------|----------|
| Inbound (AI receptionist) | 3 | 2-5 min |
| Outbound (LO follow-up) | 3 | 5-15 min |
| Outbound (voicemail drop) | 2 | 30 sec |

Each call record includes:
- `transcript` — 20-50 line realistic mortgage conversation
- `ai_summary` — 2-3 sentence summary
- `sentiment` — positive/neutral/negative mix
- `artifacts` — extracted action items, borrower data, compliance flags
- `approval_status` — approved (5), pending_review (3)
- Linked to leads and LOs

---

## 12. Activities & Stage History (100+)

- Every lead gets 3-10 activity records (calls, emails, notes, stage changes)
- Every loan gets 2-5 activity records
- `StageHistory` records for each lead/loan stage transition with realistic timestamps
- Activity types: `call`, `email_sent`, `email_received`, `note`, `sms_sent`, `sms_received`, `meeting`, `document_uploaded`, `stage_change`

---

## 13. AI Metrics & Dashboard (30-day snapshots)

### AIPerformanceDaily / AIMetricsDaily
- 30 rows, one per day
- `tasks_completed`: 5-15/day (trending up)
- `actions_approved`: 3-10/day
- `feedback_quality_avg`: 0.78-0.92

### AIReceptionistMetricsDaily
- 30 rows
- `total_conversations`: 3-8/day
- `appointments_scheduled`: 1-3/day
- `escalations`: 0-2/day

### Dashboard endpoint data
- `pipeline_stats` — aggregated from loan stages
- `production` — annual goal $25M, monthly goal $2.1M, progress calculated from funded loans
- `lead_metrics` — calculated from lead data (new_today, conversion_rate, hot_leads)
- `team_stats` — per-LO metrics calculated from their leads/loans

---

## 14. Rate Monitor

### Market Data (30 days)
- Daily rate snapshots for: 30yr Fixed, 15yr Fixed, FHA 30yr, VA 30yr, 5/1 ARM
- Realistic rate movements (±0.125% daily variance)
- Starting from current market (~6.75% for 30yr conventional)

### Rate Targets (5)
- 3 active targets, 1 achieved, 1 pending
- Programs: 30yr Fixed, FHA, VA

### Refi Opportunities (5)
- Linked to MUM clients with rates > current market + 0.5%
- Status mix: identified (2), contacted (2), in_progress (1)
- Estimated savings calculated per opportunity

---

## 15. Workflows & Compliance

### Workflow Executions (5)
- Lead Nurture workflow (2 active)
- Underwriting workflow (2 active)
- Post-closing workflow (1 completed)
- Each has 3-5 step completions logged

### Compliance Records
- `AuditLog`: 50 records (login, data changes, permission grants)
- `DisclosureEvent`: 10 records across loans (LE sent, CD sent, signed)
- `ComplianceAlert`: 5 records (2 resolved, 3 pending)
- `SmartDocsConsentRecord`: 8 records (borrower consent for doc access)

---

## 16. Borrower Portal

### BorrowerProfile (5)
- 5 borrowers with portal accounts (linked to active loan leads)
- Mix of Google, Apple, email auth providers
- Marketing consent: 4 opted in, 1 opted out

### BorrowerApplication (5)
- 2 submitted, 1 in-progress (60% complete), 1 draft, 1 completed
- Each has `ApplicationEvent` records showing progression
- Coborrower invitations on 2 applications

---

## 17. Content & Campaigns

### Email/SMS Templates (10)
- Welcome drip (3 steps), Rate alert (2), Follow-up (3), Pre-approval (1), Closing countdown (1)

### AriaCampaign (2)
- 1 completed mass text (rate drop alert, 15 recipients)
- 1 in-progress campaign (holiday greeting, 10 recipients)

### Drip Sequences (2)
- New lead nurture (5 steps over 14 days)
- Post-close follow-up (3 steps over 90 days)

---

## 18. Team Chat

### Channels (4)
- #general, #deals, #underwriting, #ops

### Messages (40 total)
- 10 per channel, realistic mortgage team chatter
- Mix of users posting
- A few reactions and read receipts

---

## 19. Notifications & Alerts

- 15 unread notifications for demo@perenniaai.com (new lead assigned, doc uploaded, rate lock expiring, task overdue, etc.)
- 5 system alerts (integration health, rate threshold breach, SLA warning)

---

## Non-Goals (Explicitly Out of Scope)

- No real file uploads (documents are metadata-only with placeholder URLs)
- No Vapi assistant provisioning (lives in Vapi API, not our DB)
- No Microsoft Graph email sync
- No external calendar sync
- No Encompass/Salesforce integration data
- No real phone numbers or SMS delivery
- Script does NOT modify existing production data — only creates within the new "Summit Home Loans" org
