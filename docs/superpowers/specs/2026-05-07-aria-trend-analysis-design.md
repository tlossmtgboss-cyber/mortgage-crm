# Aria Trend Analysis & Business Intelligence

**Date:** 2026-05-07
**Status:** Approved

## Overview

Aria gains the ability to analyze trends across all CRM data and email a comprehensive business intelligence report. Users ask "what trends do you see?" for a cross-domain summary, or specify a domain like "show me lead trends" for a deep-dive. Results are delivered exclusively via email.

## Architecture

### Tool Registration
Single `@mortgage_tool` named `analyze_trends` registered with agent roles: `["pipeline_analyst", "reporting_engine", "team_coach", "customer_intelligence"]`.

Parameters:
- `domain` (optional, default "all"): One of `all`, `leads`, `loans`, `pipeline`, `compliance`, `communication`, `dialer`, `referrals`, `mum`, `team`, `ai_ops`, `documents`, `applications`, `system`
- `time_window` (optional, default "month"): One of `week`, `month`, `quarter`
- `email_to` (optional): Override recipient email; defaults to requesting user's email

### File Structure
```
backend/agents/tools/trend_analysis.py   # @mortgage_tool + 13 domain analyzers
backend/services/trend_email.py          # HTML email formatting + send via Microsoft Graph
```

### Execution Flow
1. Tool receives domain + time_window params
2. Resolves user role for scope filtering (LO=own data, manager=team, admin=org)
3. Runs relevant domain analyzer(s) using `execute_query()` with tenant isolation
4. Each analyzer returns a list of `TrendInsight` dicts: `{metric, current_value, prior_value, delta_pct, direction, significance, context}`
5. Cross-domain mode ranks all insights by `abs(delta_pct)` and takes top 5 for "Notable Changes"
6. Passes structured data to `trend_email.py` for HTML rendering
7. Sends email via Microsoft Graph (existing infrastructure)
8. Returns `ToolResult.success(message="Trend report emailed to {email}")` so Aria confirms delivery

## KPI Domains

### 1. Lead Pipeline
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| New leads count | `COUNT(leads) WHERE created_at IN period` | Period-over-period |
| Leads by source | `GROUP BY source` | Mix shift |
| Lead conversion funnel | `COUNT per stage` via StageHistory | Stage-over-stage rates |
| Avg time-to-first-contact | `AVG(first_contact_attempt_date - lead_received_date)` | Period-over-period |
| Avg time-to-successful-contact | `AVG(first_contact_successful_date - lead_received_date)` | Period-over-period |
| AI score distribution | `AVG(ai_score), percentiles` | Period-over-period |
| Credit score distribution | `AVG(credit_score), brackets` | Period-over-period |
| Lead source ROI | `leads per source → closed per source` | Conversion delta |
| First-time buyer % | `COUNT(first_time_buyer=true) / total` | Period-over-period |
| Buying timeline mix | `COUNT per buying_timeline_category` | Mix shift |
| Stale leads | `COUNT WHERE last_contact < NOW() - 14/30/60 days` | Period-over-period |
| Nurture pipeline | `COUNT WHERE stage IN nurture stages, GROUP BY nurture_month` | Size trend |

### 2. Loan Pipeline
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| Active pipeline count & volume | `COUNT/SUM(amount) WHERE stage NOT IN terminal` | Period-over-period |
| Stage distribution | `COUNT per stage` | Mix shift |
| Stage velocity | `AVG(days_in_stage) per stage` | Period-over-period |
| Funded count & volume | `COUNT/SUM(amount) WHERE funded_date IN period` | Period-over-period |
| Pull-through rate | `funded / applications in same cohort` | Period-over-period |
| Fallout by stage | `COUNT entering terminal stages, GROUP BY from_stage` via StageHistory | Period-over-period |
| Avg loan amount | `AVG(amount)` | Period-over-period |
| Avg rate | `AVG(rate)` | Period-over-period |
| Avg LTV | `AVG(ltv)` | Period-over-period |
| Loan type mix | `COUNT per loan_type` | Mix shift |
| Lock status distribution | `COUNT per rate_lock_status` | Mix shift |
| Lock-to-close time | `AVG(closing_date - lock_date)` | Period-over-period |

### 3. Process Flow / SLA
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| SLA compliance % | `tasks WHERE completed_at <= due_date / total` | Period-over-period |
| Cycle time (app→funded) | `AVG(funded_date - application_date)` | Period-over-period |
| Sub-segment times | `AVG(duration_in_previous_stage) per stage pair` via StageHistory | Period-over-period |
| Bottleneck detection | Stages where avg dwell time increased >20% | Delta detection |
| Task completion rate | `completed / total tasks` | Period-over-period |
| Task on-time % | `completed_at <= due_date` | Period-over-period |
| Task backlog | `COUNT(status=pending) per owner` | Period-over-period |
| Escalation frequency | `COUNT(escalation_records)` | Period-over-period |
| Escalation resolution time | `AVG(resolved_at - escalated_at)` | Period-over-period |
| Re-escalation rate | `AVG(re_escalation_count)` | Period-over-period |
| Handoff quality | `AVG(context_completeness_score), COUNT(user_had_to_repeat)` | Period-over-period |

### 4. Compliance
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| TRID LE compliance | `COUNT(is_on_time=true) WHERE disclosure_type=LE / total` | Period-over-period |
| TRID CD compliance | Same for CD | Period-over-period |
| Adverse action timeliness | `COUNT(is_on_time=true) / total adverse actions` | Period-over-period |
| Fee tolerance violations | `COUNT(is_violation=true) per tolerance_category` | Period-over-period |
| Open compliance alerts | `COUNT per severity WHERE status=open` | Snapshot + trend |
| Disclosure turnaround | `AVG(received_at - sent_at)` | Period-over-period |
| Alert resolution time | `AVG(resolved_at - created_at)` | Period-over-period |

### 5. Communication & Activity
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| Total activities | `COUNT(activities) GROUP BY type` | Period-over-period |
| Inbound/outbound ratio | `email_messages + sms_messages GROUP BY direction` | Period-over-period |
| Contact frequency per lead | `AVG(activities per lead)` | Period-over-period |
| AI-generated message % | `COUNT(ai_generated=true) / total sms` | Period-over-period |
| Sentiment distribution | `COUNT per sentiment` | Mix shift |
| SMS delivery rate | `COUNT(status=delivered) / total sms sent` | Period-over-period |
| Email bounce rate | `COUNT(status=bounced) / total emails sent` | Period-over-period |

### 6. Dialer & Calls
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| Calls per agent per day | `COUNT(call_logs) / distinct days / distinct agents` | Period-over-period |
| Avg call duration | `AVG(duration_seconds)` | Period-over-period |
| Call outcome distribution | `COUNT per outcome` | Mix shift |
| Connect rate | `COUNT(outcome=COMPLETED) / total` | Period-over-period |
| Dialer session completion | `AVG(completed_tasks / total_tasks)` | Period-over-period |
| Contacts per session | `AVG(total_tasks)` | Period-over-period |
| Recording completion rate | `COUNT(recording_status=transcribed) / total` | Period-over-period |

### 7. Referral Partners
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| Total referrals in/out | `SUM(referrals_in), SUM(referrals_out)` | Period-over-period |
| Top partners by volume | `ORDER BY volume DESC LIMIT 10` | Rank changes |
| Partner conversion rate | `closed_loans / referrals_in` per partner | Period-over-period |
| Reciprocity score trend | `AVG(reciprocity_score)` | Period-over-period |
| Loyalty tier distribution | `COUNT per loyalty_tier` | Mix shift |
| New vs dormant ratio | `created_at in period / last_interaction > 90 days` | Period-over-period |
| Revenue per partner | `volume per partner` | Period-over-period |
| Engagement recency | Distribution of days since last_interaction | Shift detection |

### 8. MUM (Mortgage Under Management)
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| Portfolio size & balance | `COUNT, SUM(current_loan_amount)` | Period-over-period |
| Refi opportunity count | `COUNT(refinance_opportunity=true)` | Period-over-period |
| Estimated refi savings | `SUM(estimated_savings)` | Period-over-period |
| Engagement score distribution | `AVG(engagement_score), brackets` | Period-over-period |
| Days since contact distribution | `distribution of NOW() - last_contact` | Shift detection |
| Rate delta | `AVG(current_rate - original_rate)` vs market | Period-over-period |
| LTV distribution | `brackets of current_ltv` | Shift detection |
| Upcoming touchpoints | `COUNT WHERE next_touchpoint IN next 7/30 days` | Snapshot |
| Client referrals | `SUM(referrals_sent)` | Period-over-period |

### 9. Team Performance (managers/admins only)
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| Per-LO funded count & volume | `JOIN loans ON loan_officer_id` | Period-over-period + rank |
| Per-LO pipeline size | `COUNT active loans per LO` | Period-over-period |
| Per-LO lead conversion | `funded / leads assigned` per LO | Period-over-period |
| Per-LO task completion | `completed / total per LO` | Period-over-period |
| Per-LO response time | `AVG(first_contact_attempt - lead_received)` per LO | Period-over-period |
| Workload distribution | `leads + loans per LO` | Gini coefficient or spread |
| Team ranking changes | LO rank by volume, current vs prior period | Rank delta |
| Processor/UW workload | `COUNT loans per processor/underwriter` | Distribution |

### 10. AI Operations
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| AI action approval rate | `approved / total ai_actions` | Period-over-period |
| AI accuracy rate | `accuracy_rate from ai_learning_metrics` | Period-over-period |
| Autonomous execution rate | `auto_approved / total` | Period-over-period |
| AI confidence distribution | `AVG(confidence), brackets` | Period-over-period |
| Feedback volume by type | `COUNT per feedback_type` | Period-over-period |
| Feedback resolution rate | `resolved / total feedback` | Period-over-period |
| AI cost trend | `SUM(cost_estimate), SUM(tokens_used)` | Period-over-period |
| Agent handoff patterns | `COUNT per from_agent, to_agent` | Frequency changes |

### 11. Document Flow
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| Documents uploaded | `COUNT(documents) per period` | Period-over-period |
| Document type distribution | `COUNT per doc_type` | Mix shift |
| Email intake match rate | `COUNT(MATCHED) / total intake` | Period-over-period |
| AI classification accuracy | `AVG(ai_confidence) WHERE status=CLASSIFIED` | Period-over-period |
| Pending docs per loan | `AVG pending documents` | Period-over-period |
| Classification turnaround | `AVG(classified_at - created_at)` | Period-over-period |

### 12. Borrower Applications
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| Application starts | `COUNT(started_at IN period)` | Period-over-period |
| Completion rate | `SUBMITTED / started` | Period-over-period |
| Avg time to complete | `AVG(submitted_at - started_at)` | Period-over-period |
| Drop-off stage | `COUNT per current_step WHERE status != SUBMITTED` | Distribution |
| Progress distribution | `brackets of progress_percentage` | Shift detection |
| Voice completion rate | `COUNT(voice_completed_at != null) / total` | Period-over-period |
| Expired applications | `COUNT(status=EXPIRED)` | Period-over-period |

### 13. System Health & Security (admins only)
| KPI | Query Source | Comparison |
|-----|-------------|------------|
| Daily active users | `active_users_total from security_snapshot_daily` | Period-over-period |
| 2FA adoption | `active_users_with_2fa / total` | Period-over-period |
| Failed login attempts | `failed_login_attempts_24h` | Period-over-period |
| Integration health | `integration_status_logs per integration` | Status changes |
| Batch job success rate | `success / total system_jobs_logs` | Period-over-period |
| System alerts | `COUNT per severity` | Period-over-period |

## Time Windows

Each analyzer computes metrics for three comparison pairs:
- **Week:** Current 7 days vs prior 7 days
- **Month:** Current 30 days vs prior 30 days
- **Quarter:** Current 90 days vs prior 90 days

The `time_window` parameter selects which comparison to highlight in the email. The "Notable Changes" section always uses month-over-month.

## Role-Based Scoping

| Role | Data Scope | Domains Available |
|------|-----------|-------------------|
| Sales (LO) | Own leads, loans, activities, MUM, partners | 1-8 (own data only) |
| Processing/Operations | Own assigned loans, tasks, docs | 2, 3, 4, 11 |
| Manager/Leadership | Team aggregate + per-LO breakdowns | All 13 |
| Admin/Site Admin | Org-wide + system health | All 13 |

Scoping is enforced via `owner_id`/`loan_officer_id`/`user_id` filters for LO role, and `organization_id` for all roles (tenant isolation via `execute_query`).

## Email Delivery

### Format
HTML email with inline CSS (no external stylesheets for email client compatibility).

### Structure
```
Subject: Perennia Trend Report — {date_range}

[Notable Changes]
Top 5 most significant movements across all domains, ranked by |delta_pct|.
Each with trend arrow, metric name, values, and one-sentence context.

[Domain Sections] (only domains with data)
Each section:
  - Domain header
  - Table of KPIs with: metric name, current value, prior value, delta %, trend arrow
  - Color coding: green (improving), red (declining), gray (<5% change)

[Footer]
Report generated at {timestamp}
Period: {start_date} to {end_date} vs {prior_start} to {prior_end}
```

### Sending
Uses existing Microsoft Graph email infrastructure (`services/dre_helpers.py` pattern or dedicated email service). Sends from the user's Outlook address.

## TrendInsight Data Structure

```python
@dataclass
class TrendInsight:
    domain: str           # e.g., "leads", "loans"
    metric: str           # e.g., "new_lead_count"
    label: str            # e.g., "New Leads"
    current_value: float
    prior_value: float
    delta_pct: float      # (current - prior) / prior * 100
    direction: str        # "up", "down", "flat"
    significance: float   # abs(delta_pct) — for ranking
    context: str          # e.g., "Web leads drove most of the increase"
    is_positive: bool     # Whether this direction is good (for color coding)
    unit: str             # "count", "currency", "percent", "days"
```

## Edge Cases

- **No prior period data:** Show current values with "N/A" for delta, note "First period tracked"
- **Zero denominator:** Skip percentage KPIs where denominator is 0
- **Empty domains:** Omit domain section from email if no data exists
- **Large orgs:** Limit per-LO breakdowns to top 25 by volume
- **Email send failure:** Return `ToolResult.error()` with specific failure reason so Aria can inform user
