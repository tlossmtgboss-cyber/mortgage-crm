# Perennia AI -- Agent Inventory

## Overview

The platform has **two agent systems** running in parallel:

1. **Legacy system**: 46 agents defined in `tool_integration.py` AGENT_CONFIGS, routed by `intent_router.py`
2. **Consolidated overlay**: 10 agents defined in `consolidation.py`, available as opt-in but not yet wired as default

The intent router maps 27 intent categories to legacy agents via INTENT_TO_AGENTS. The consolidation module maps the same intents to 10 consolidated agents via INTENT_TO_CONSOLIDATED.

---

## Active Agents (Legacy -- 46 in AGENT_CONFIGS)

### CRM Agents (8)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 1 | pipeline_analyst | Pipeline Analyst | 16 | sonnet | Loan pipeline metrics, trends, conversion rates, bottleneck analysis |
| 2 | compliance_checker | Compliance Checker | 12 | sonnet | TRID, RESPA, fair lending, state requirements, TCPA/DNC |
| 3 | lead_nurturer | Lead Nurturer | 18 | sonnet | Lead engagement, scoring, follow-up, outreach, SMS scheduling |
| 4 | document_tracker | Document Tracker | 18 | haiku | Missing docs, conditions, freshness, portal activity, SLA |
| 5 | profitability_analyst | Profitability Analyst | 8 | sonnet | Loan/portfolio profitability, margin analysis, revenue forecast |
| 6 | rate_advisor | Rate Advisor | 24 | sonnet | Rate lock/float, market conditions, home valuation, refinance analysis |
| 7 | team_coach | Team Coach | 16 | sonnet | LO metrics, coaching plans, improvement tracking, escalation handling |
| 8 | customer_intelligence | Customer Intelligence | 8 | haiku | Customer 360, relationships, LTV, churn risk, referral networks |

### Communication Agents (4)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 9 | voice_os | Voice OS | 8 | haiku | Outbound calls, voicemail drops, call history, power dialer |
| 10 | uvip | UVIP (Video Platform) | 8 | haiku | Video meetings, recordings, meeting analysis, async video |
| 11 | email_intelligence | Email Intelligence | 15 | sonnet | Email parsing, intent detection, tone analysis, response drafting |
| 12 | ai_receptionist | AI Receptionist | 8 | haiku | Inbound call handling, caller qualification, call routing |

### Operations Agents (4)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 13 | smart_scheduler | Smart Scheduler | 12 | haiku | Calendar management, booking, reminders, schedule optimization |
| 14 | task_automation | Task Automation | 10 | haiku | Task CRUD, workflows, daily call lists, bulk operations |
| 15 | sla_tracker | SLA Tracker | 8 | haiku | SLA compliance, alerts, breach projection, escalation |
| 16 | integrations | Integrations Manager | 14 | sonnet | LOS sync, credit pulls, AUS, vendor integrations |

### Business Agents (4)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 17 | reporting_engine | Reporting Engine | 12 | sonnet | Pipeline/production reports, trend analysis, data exports |
| 18 | notification_center | Notification Center | 8 | haiku | Notification CRUD, delivery tracking, preferences |
| 19 | subscription_manager | Subscription Manager | 8 | sonnet | Billing, plan changes, usage metrics, add-ons |
| 20 | onboarding_assistant | Onboarding Assistant | 8 | haiku | Setup wizard, guided tours, training resources, checklists |

### Cross-Agent Coordination (1)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 21 | ops_manager | Operations Manager | 8 | sonnet | Pipeline sweep, SLA oversight, cross-agent coordination |

### Revenue & Production Agents (4)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 22 | revenue_forecaster | Revenue Forecaster | 6 | sonnet | Revenue projection, pull-through modeling |
| 23 | pricing_strategist | Pricing Strategist | 8 | sonnet | Loan pricing optimization, margin analysis |
| 24 | closing_coordinator | Closing Coordinator | 8 | haiku | Title, escrow, docs, funding coordination |
| 25 | loan_structuring | Loan Structuring Advisor | 8 | sonnet | Multi-scenario structuring, DTI optimization |

### Borrower Experience Agents (5)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 26 | borrower_concierge | Borrower Concierge | 15 | sonnet | Borrower journey management, proactive updates |
| 27 | pre_approval_specialist | Pre-Approval Specialist | 9 | sonnet | Pre-approval workflow, letter generation |
| 28 | credit_repair_advisor | Credit Repair Advisor | 8 | sonnet | Credit improvement strategies, dispute management |
| 29 | down_payment_advisor | Down Payment Advisor | 8 | sonnet | DPA programs, gift funds, grant eligibility |
| 30 | post_closing_care | Post-Closing Care | 8 | haiku | Post-closing outreach, referral generation, anniversaries |

### Risk & Fraud Agents (4)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 31 | fraud_detector | Fraud Detector | 8 | sonnet | Wire fraud detection, social engineering alerts |
| 32 | risk_assessor | Risk Assessor | 8 | sonnet | Default probability, layered risk analysis |
| 33 | quality_control | Quality Control | 8 | sonnet | Pre/post-close QC, buyback prevention |
| 34 | turn_down_specialist | Turn Down Specialist | 8 | sonnet | Adverse action handling, declination scripts |

### Marketing & Content Agents (5)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 35 | content_creator | Content Creator | 8 | sonnet | Social media posts, blog content, drip campaign copy |
| 36 | social_media_manager | Social Media Manager | 8 | sonnet | Multi-platform posting, engagement tracking |
| 37 | market_analyst | Market Analyst | 8 | sonnet | Real estate market trends, rate environment analysis |
| 38 | campaign_manager | Campaign Manager | 8 | sonnet | Multi-channel campaign orchestration |
| 39 | review_manager | Review & Reputation | 8 | haiku | Online review solicitation, reputation management |

### HR & Workforce Agents (3)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 40 | recruiter | LO Recruiter | 8 | sonnet | Recruiting, compensation benchmarking |
| 41 | training_specialist | Training Specialist | 8 | haiku | Training programs, certification tracking |
| 42 | performance_manager | Performance Manager | 8 | sonnet | KPI tracking, goal setting, incentive calculations |

### Partner & Referral Agents (4)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 43 | referral_partner_manager | Referral Partner Manager | 8 | sonnet | Realtor/builder relationships, co-marketing |
| 44 | title_vendor_manager | Title & Vendor Manager | 8 | haiku | Title company coordination, fee shopping |
| 45 | appraiser_coordinator | Appraiser Coordinator | 8 | haiku | Appraisal ordering, rush requests, rebuttals |
| 46 | insurance_coordinator | Insurance Coordinator | 8 | haiku | Homeowner's insurance tracking, flood determination |

### Expanded Operations Agents (5)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 47 | warehouse_manager | Warehouse Line Manager | 8 | sonnet | Warehouse capacity, delivery optimization |
| 48 | shipping_coordinator | Shipping Coordinator | 8 | haiku | Loan shipping, investor delivery |
| 49 | secondary_market | Secondary Market Analyst | 8 | sonnet | Loan sale execution, hedge tracking |
| 50 | servicing_transfer | Servicing Transfer | 8 | haiku | Post-closing servicing setup, transfer coordination |
| 51 | investor_relations | Investor Relations | 8 | sonnet | Investor requirements, overlay management |

### Technology & Platform Agents (3)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 52 | system_health_monitor | System Health Monitor | 8 | haiku | API health, performance metrics, uptime |
| 53 | data_quality_manager | Data Quality Manager | 8 | haiku | Data integrity, duplicate detection |
| 54 | migration_assistant | Migration Assistant | 8 | sonnet | Data import/export, LOS transition support |

### Specialty Lending Agents (6)

| # | Agent Role | Name | Tools | Model | Unique Responsibility |
|---|------------|------|-------|-------|-----------------------|
| 55 | va_loan_specialist | VA Loan Specialist | 8 | sonnet | COE, residual income, VA appraisal, funding fee |
| 56 | fha_loan_specialist | FHA Loan Specialist | 8 | sonnet | MI premiums, case numbers, UFMIP |
| 57 | jumbo_specialist | Jumbo & Non-Agency | 8 | sonnet | Reserve requirements, bank statement programs |
| 58 | reverse_mortgage_advisor | Reverse Mortgage | 8 | sonnet | HECM counseling, principal limit, disbursement |
| 59 | construction_loan_advisor | Construction Loan | 8 | sonnet | Draw schedules, builder approval, lot loans |
| 60 | commercial_bridge | Commercial & Bridge | 8 | sonnet | DSCR, NOI analysis, cap rate evaluation |

---

## Tool Files (44 non-test files in agents/tools/)

base.py, borrower_application.py, coaching.py, compliance.py, compliance_utils.py,
content_marketing.py, credit_monitoring_tools.py, customer.py, dedup_tools.py,
document_tools.py, documents.py, email_intel.py, escalation.py, historical.py,
home_valuation.py, integrations.py, leads.py, los_integration.py, metrics.py,
mum_tools.py, notifications.py, onboarding.py, outreach_tools.py, pipeline.py,
portal_tools.py, profitability.py, rates.py, receptionist.py, referral_tools.py,
refinance.py, reporting.py, scheduler.py, sla.py, smart_documents.py, sms_tools.py,
subscription.py, tasks.py, team_org.py, tool_router.py, trend_analysis.py,
u_agent_challenge.py, usage_tracker.py, video.py, voice.py

---

## Overlap Analysis

### Heavy Overlap Clusters

1. **Pipeline/Analytics overlap**: `pipeline_analyst`, `revenue_forecaster`, `ops_manager`, `reporting_engine` all share `get_pipeline_metrics`, `get_loan_aging_report`, `get_bottleneck_analysis`, `predict_closing_timeline`, `calculate_conversion_rates`. These four agents are doing the same analysis from slightly different angles.

2. **Compliance/Risk/QC overlap**: `compliance_checker`, `quality_control`, `risk_assessor`, `fraud_detector`, `turn_down_specialist`, `investor_relations` all share `audit_loan_file`, `check_trid_compliance`, `check_fair_lending`, `get_compliance_history`, `check_tolerance_violations`. The difference between them is mostly prompt framing, not tool access.

3. **Borrower outreach overlap**: `lead_nurturer`, `borrower_concierge`, `pre_approval_specialist`, `credit_repair_advisor`, `down_payment_advisor`, `post_closing_care` all share `get_lead_details`, `draft_message`, `schedule_outreach`, `create_task`, `send_notification`. These represent different stages of the same borrower lifecycle.

4. **Document/vendor overlap**: `document_tracker`, `closing_coordinator`, `title_vendor_manager`, `appraiser_coordinator`, `insurance_coordinator` all share `get_missing_documents`, `track_document_request`, `get_document_timeline`, `get_third_party_status`, `escalate_issue`. They are sub-functions of a single document operations agent.

5. **Marketing/content overlap**: `content_creator`, `social_media_manager`, `campaign_manager`, `review_manager` all share `draft_message`, `get_market_events`, `get_current_rates`, `schedule_notification`. The creative differences are purely prompt-level.

6. **HR/coaching overlap**: `team_coach`, `recruiter`, `training_specialist`, `performance_manager` all share `get_lo_metrics`, `compare_to_peers`, `get_performance_trends`, `track_improvement`. These are views of the same team data.

7. **Rate/pricing overlap**: `rate_advisor`, `pricing_strategist`, `secondary_market`, `loan_structuring` all share `get_current_rates`, `compare_rate_scenarios`, `get_pricing_engine_quote`. Rate advisory vs. pricing strategy is a distinction without a meaningful difference in tool access.

8. **Specialty lending overlap**: `va_loan_specialist`, `fha_loan_specialist`, `jumbo_specialist`, `reverse_mortgage_advisor`, `construction_loan_advisor`, `commercial_bridge` all use nearly identical tool sets (`get_state_requirements`, `get_pricing_engine_quote`, `audit_loan_file`, `draft_message`, `create_task`). The differentiation is entirely in the system prompt, not in tool access.

---

## Consolidation Recommendations

The existing `consolidation.py` already proposes a 10-agent target that is well-designed. Below is an adjusted recommendation to consolidate from 60 to **10 first-class agents**, aligning with the consolidation module:

### Proposed 10 First-Class Agents

| # | Agent | Absorbs (Legacy Roles) | Model | Rationale |
|---|-------|------------------------|-------|-----------|
| 1 | **Aria** | ai_receptionist, voice_os | haiku | Single voice interface. Inbound + outbound call management. |
| 2 | **Avery** | lead_nurturer, pre_approval_specialist, credit_repair_advisor, down_payment_advisor, borrower_concierge, onboarding_assistant | sonnet | All borrower-facing outreach in one agent. Lifecycle stages differentiated by prompt context, not tool sets. |
| 3 | **Pipeline Coach** | pipeline_analyst, sla_tracker, task_automation, smart_scheduler, ops_manager, reporting_engine, notification_center, closing_coordinator, warehouse_manager, shipping_coordinator, uvip | sonnet | Central operational hub. Pipeline health, tasks, scheduling, reporting, and closing coordination under one roof. |
| 4 | **Calculator** | rate_advisor, profitability_analyst, revenue_forecaster, pricing_strategist, loan_structuring, secondary_market, commercial_bridge | sonnet | All financial computation: rates, profitability, pricing, scenarios, forecasting. |
| 5 | **Document Intelligence** | document_tracker, title_vendor_manager, appraiser_coordinator, insurance_coordinator | haiku | All document lifecycle: tracking, conditions, third-party orders, vendor coordination. |
| 6 | **Compliance Sentry** | compliance_checker, quality_control, fraud_detector, risk_assessor, turn_down_specialist, investor_relations | sonnet | All regulatory and risk: TRID, RESPA, QC, fraud, adverse action. No guessing on compliance. |
| 7 | **Email Intelligence** | email_intelligence, content_creator, social_media_manager, campaign_manager, review_manager | sonnet | All written communication: email, content, campaigns, reviews. |
| 8 | **Talent Radar** | team_coach, recruiter, training_specialist, performance_manager | sonnet | All people management: coaching, recruiting, training, performance. |
| 9 | **Opportunity Agent** | customer_intelligence, referral_partner_manager, post_closing_care, market_analyst, servicing_transfer | sonnet | Market intelligence and revenue discovery from existing book. |
| 10 | **Underwriter Copilot** | integrations, va_loan_specialist, fha_loan_specialist, jumbo_specialist, reverse_mortgage_advisor, construction_loan_advisor, subscription_manager, system_health_monitor, data_quality_manager, migration_assistant | sonnet | Guideline RAG, product matching, LOS integration, platform admin. |

### Migration Notes

- The consolidation.py module is already built and ready to use. It defines all 10 agents with tool lists, personas, and legacy role mappings.
- Migration is a routing-layer change: swap `INTENT_TO_AGENTS` for `INTENT_TO_CONSOLIDATED` in the orchestrator.
- Legacy agents remain available during transition -- the consolidation module is an overlay, not a replacement.
- The main risk is tool-count inflation per agent (Pipeline Coach has ~70 tools). Monitor for LLM context window impact and tool-selection confusion.
- Consider a phased rollout: start with low-risk agents (Aria, Document Intelligence, Talent Radar) where haiku model and tool-driven responses make consolidation low-risk.

---

## Agent-to-Intent Mapping (from intent_router.py)

| Intent | Legacy Agents | Consolidated Agent(s) |
|--------|---------------|-----------------------|
| greeting | (none -- direct response) | aria |
| simple | pipeline_analyst | pipeline_coach |
| pipeline | pipeline_analyst, revenue_forecaster | pipeline_coach, calculator |
| historical | pipeline_analyst | pipeline_coach |
| compliance | compliance_checker, quality_control | compliance |
| tasks | task_automation | pipeline_coach |
| priorities | pipeline_analyst, task_automation | pipeline_coach |
| top_leads | lead_nurturer | avery |
| leads | lead_nurturer, pre_approval_specialist | avery |
| documents | document_tracker, closing_coordinator | doc_intel |
| rates | rate_advisor, secondary_market | calculator |
| schedule | smart_scheduler | pipeline_coach |
| sla | sla_tracker | pipeline_coach |
| calls | voice_os, ai_receptionist | aria |
| email | email_intelligence | email_intel |
| video | uvip | pipeline_coach |
| reports | reporting_engine | pipeline_coach |
| billing | subscription_manager | uw_copilot |
| team | team_coach | talent_radar |
| coaching | team_coach, training_specialist | talent_radar |
| customer | customer_intelligence, borrower_concierge | opportunity |
| integrations | integrations, migration_assistant | uw_copilot |
| operations | ops_manager | pipeline_coach |
| profit | profitability_analyst, pricing_strategist | calculator |
| notifications | notification_center | pipeline_coach |
| onboarding | onboarding_assistant | avery |
| compound | pipeline_analyst + lead_nurturer + smart_scheduler + email_intelligence + voice_os + task_automation + closing_coordinator | pipeline_coach + avery + email_intel + aria |
| general | pipeline_analyst, task_automation | pipeline_coach |

---

## Model Selection Summary

### Haiku agents (fast, tool-driven -- 16 of 60 legacy agents):
document_tracker, voice_os, uvip, ai_receptionist, smart_scheduler, task_automation,
sla_tracker, notification_center, onboarding_assistant, customer_intelligence,
closing_coordinator, post_closing_care, review_manager, training_specialist,
title_vendor_manager, appraiser_coordinator, insurance_coordinator, shipping_coordinator,
servicing_transfer, system_health_monitor, data_quality_manager

### Sonnet agents (complex reasoning -- 39 of 60 legacy agents):
All remaining agents require analytical reasoning, compliance precision, or creative generation.

---

## Key Files

- Agent configs: `backend/agents/tool_integration.py` (AGENT_CONFIGS, 1633 lines)
- Intent routing: `backend/agents/intent_router.py` (INTENT_TO_AGENTS, INTENT_PATTERNS, 1281 lines)
- Consolidation plan: `backend/agents/consolidation.py` (CONSOLIDATED_AGENTS, 1106 lines)
- Agent service: `backend/agents/service.py` (~2799 lines)
- Orchestrator: `backend/agents/orchestrator.py`
- Tool files: `backend/agents/tools/` (44 files)
