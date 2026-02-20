# Perennia AI — Master Gap Analysis Report

> **Date:** February 20, 2026
> **Skill:** /u-gap-analysis v1.0.0
> **Scope:** 13 Modules | 4 Phases | 20 Agents | ~220 Tools | 80+ DB Models

---

## EXECUTIVE SUMMARY

Perennia AI's architecture achieves **~80% coverage** across all 13 gap analysis modules. The platform demonstrates **world-class compliance integration**, a **consistent Decision Engine framework**, and **deep Todd Duncan sales methodology embedding**. The agent prompt layer (44 files, 4,091 lines) and tool layer (~220 tools, ~29,376 lines) provide comprehensive operational intelligence.

**However, 5 modules have strategic gaps** that will limit enterprise deployments and revenue optimization if unaddressed.

### Overall Scorecard

| Grade | Module | Coverage |
|:---:|---|:---:|
| **A** | 1. Compliance Engine | 90% |
| **A** | 4. Document Intelligence | 90% |
| **A** | 6. Rate Intelligence | 90% |
| **A** | 8. Workflow Triggers | 85% |
| **B+** | 5. Channel Communication | 85% |
| **B+** | 7. Referral & Partner Management | 80% |
| **B+** | 12. LOS Integration (Encompass) | 85% |
| **B** | 2. Conversation Memory & Context | 70% |
| **B** | 9. Refinance Intelligence | 75% |
| **B** | 10. Onboarding & Training | 75% |
| **B-** | 11. Reporting & Analytics | 65% |
| **C+** | 13. Marketing Campaign Orchestration | 55% |
| **C** | 3. Escalation & Handoff Protocol | 45% |

---

## PHASE 1: COMPLIANCE & SAFETY NET (Always Active)

### MODULE 1: MORTGAGE COMPLIANCE ENGINE — Grade: A (90%)

**Status: HIGHLY COMPLETE**

#### What EXISTS:
- **TRID Engine** (`services/trid_engine.py`, 300+ lines): Full LE/CD timing with federal holiday calculations
- **Fair Lending Monitor** (`services/fair_lending_monitor.py`): 4/5ths rule, adverse impact detection, rate variance flagging (>25bps threshold)
- **Compliance Models** (`database/models/compliance.py`): LoanFee, DisclosureEvent, AdverseActionNotice, ComplianceAlert
- **Compliance Tools** (12 tools): check_trid_compliance, check_respa_compliance, check_fair_lending, check_tolerance_violations, audit_loan_file, get_state_requirements, get_disclosure_timeline, get_compliance_history, check_tcpa_consent, check_dnc_status, validate_outbound_contact, check_calling_window
- **Agent Prompts**: Compliance Checker core (104 lines) + universal compliance_rules.md (43 lines) applied to ALL agents
- **State-Specific**: CA, TX, NY, FL rules hardcoded in tools

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| HMDA data collection/reporting framework | Medium | Regulatory risk for larger lenders |
| RESPA Section 8 full kickback detection | Medium | Compliance gap |
| Pricing disparity automated remediation | Low | Enhancement to fair lending |
| Dynamic state requirements (beyond 4 states) | Medium | Scale limitation |

#### Module Compliance Score: 90/100

---

### MODULE 2: CONVERSATION MEMORY & CONTEXT — Grade: B (70%)

**Status: FUNCTIONAL WITH GAPS**

#### What EXISTS:
- **Conversation Memory Service** (`conversation_memory_service.py`, 130+ lines): Persistent RDBMS storage
- **Memory Models** (`conversation_memory_models.py`): ai_conversation_memory table with user_id, session_id, JSON metadata
- **Pinecone Integration**: Vector embeddings for semantic search (conversation_summary, key_points, pinecone_id, sentiment, intent)
- **Entity Tracking Tools**: get_engagement_history, get_interaction_history, get_customer_360
- **Email Threading**: get_email_thread, analyze_email_engagement, get_thread_tone_trends
- **Agent Prompt Coverage**: 16/20 agents include memory/context instructions

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| ConversationSession model (multi-turn tracking) | High | No session abstraction for handoffs |
| EntityExtraction model (structured extraction from conversations) | High | Can't resolve "it"/"that"/"the loan" references |
| Context compression for long conversations | Medium | Token bloat in multi-turn exchanges |
| Conversation summarization for agent handoffs | High | Agents restart from scratch |
| Longitudinal sentiment tracking (not per-email) | Medium | No mood trends |
| Co-reference resolution engine | High | #1 broken behavior per skill spec |

#### Module Compliance Score: 70/100

---

### MODULE 3: ESCALATION & HANDOFF PROTOCOL — Grade: C (45%)

**Status: BASIC CAPABILITY ONLY**

#### What EXISTS:
- **Escalation Routes** (`escalation_routes.py`): Lead search + create escalation endpoint
- **Live Agent Escalation** (`services/live_agent_escalation_service.py`): Agent-to-human handoff
- **AI Agent Coordination** (`services/ai_agent_coordination_service.py`): Multi-agent routing
- **Agent Governance** (`routes/agent_governance_routes.py`): Governance rules
- **Task-Based Routing**: Task model supports owner reassignment with priority levels
- **Agent Prompts**: 15/20 agents define escalation targets

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| Escalation strategy rules (auto-escalate by SLA/complexity) | **Critical** | Manual escalation only |
| Escalation queue management | High | No visibility into queue depth |
| Agent workload balancing (round-robin/skill-based) | High | Uneven distribution |
| Warm handoff context package (Module 3.2 spec) | **Critical** | Users repeat themselves |
| Acknowledgment/timeout handling | High | Escalations silently drop |
| De-escalation framework (Module 3.3 spec) | Medium | No anger management protocol |
| EscalationRecord model (dedicated tracking) | High | No audit trail for escalations |
| HandoffLog model (transfer tracking) | High | Can't track handoff quality |
| Cross-agent routing rules (Module 3.4 spec) | High | Ad-hoc routing decisions |

#### Module Compliance Score: 45/100

---

## PHASE 2: CORE INTELLIGENCE

### MODULE 4: DOCUMENT INTELLIGENCE — Grade: A (90%)

**Status: HIGHLY COMPLETE WITH AI ANALYSIS**

#### What EXISTS:
- **AI Document Analysis** (`services/document_analysis_service.py`, 260+ lines): Claude Vision verification
- **Smart Docs Pipeline**: data_extractor.py, review_pipeline.py, freshness_validator.py
- **Document Models** (6): EmailIntake, AttachmentIntake, Document + 24 DocumentTypes, 8 Categories
- **Document Tools** (16): get_missing_documents, get_loan_conditions, track_document_request, send_document_reminder, escalate_issue, get_document_timeline, check_document_expiration, get_third_party_status, categorize_email_attachments, parse_email, match_email_to_loan
- **Agent Prompts**: Document Agent core (79 lines) with TRID-aware prioritization

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| Condition-to-document mapping automation (Module 4.4) | Medium | Manual mapping |
| Borrower document upload portal with drag-drop | Medium | UX gap |
| Doc escalation time triggers (7/14/21 day per Module 4.5) | Medium | Manual follow-up timing |
| OCR fallback for non-Vision formats | Low | Edge case |

#### Module Compliance Score: 90/100

---

### MODULE 5: CHANNEL COMMUNICATION ADAPTER — Grade: B+ (85%)

**Status: WELL-IMPLEMENTED FOR EMAIL/SMS/VOICE**

#### What EXISTS:
- **Email**: parse_email, send_email, draft_email_response, templates (YAML), engagement analysis (15 tools)
- **Voice**: initiate_outbound_call, drop_voicemail, transcribe_call, call_sentiment (8 tools)
- **SMS**: send_notification with TCPA gate, SMS conversation threading
- **Video**: schedule_video_meeting, async_video, analytics, recordings (9 tools)
- **Voicemail**: VoicemailTemplate, VoicemailCampaign models
- **TCPA Compliance**: Built into notification pipeline
- **Agent Prompts**: Voice OS (161 lines), UVIP (130 lines), Email Intel (73 lines), Notifications (121 lines)

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| ChannelPreference model (unified preferences per contact) | High | No cross-channel coordination |
| MessageTemplate model (standardized across channels) | High | Templates siloed per channel |
| Information boundary enforcement (Module 5.2) | Medium | No auto-blocking of financials to realtors |
| Channel selection logic automation (Module 5.3) | Medium | Manual channel choice |
| NotificationConfig model (delivery rules per user) | Medium | One-size-fits-all |
| WhatsApp/WeChat support | Low | International markets |
| Message delivery status tracking (bounces) | Medium | No bounce handling |

#### Module Compliance Score: 85/100

---

### MODULE 6: RATE INTELLIGENCE & MARKET ADVISORY — Grade: A (90%)

**Status: HIGHLY COMPLETE**

#### What EXISTS:
- **Rate Lock Engine** (`workflows/rate_lock_engine.py`, 280+ lines): Eligibility, lock scoring (0-100), float/lock recommendations
- **Market Data**: FRED/MBS scrapers, volatility scoring, market event tracking
- **Rate Tools** (12): get_current_rates, analyze_rate_trends, calculate_lock_cost, recommend_lock_strategy, monitor_float_position, get_extension_pricing, compare_rate_scenarios, get_market_events
- **Rate Enums**: RateLockStatus (7 states), RateLockRecommendation (5 types), BuyingTimelineCategory, BorrowerRiskProfile
- **Agent Prompts**: Rate Advisor core (150 lines) — strongest individual prompt with lock/float decision framework, price-to-advice transition, 4 objection scenarios

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| RateLock ledger model (individual lock records) | High | No lock history |
| RateMarketData historical model | Medium | No trend database |
| Rate lock alerts tied to borrower locks | High | No auto-notification on float-down |
| Competitor rate shopping integration | Low | Nice-to-have |
| Rate communication guidance for non-rate agents (Module 6.2) | Medium | Only Rate Advisor + Lead Agent have rules |

#### Module Compliance Score: 90/100

---

## PHASE 3: REVENUE & GROWTH

### MODULE 7: REFERRAL & PARTNER MANAGEMENT — Grade: B+ (80%)

**Status: WELL-IMPLEMENTED**

#### What EXISTS:
- **Circle of Cashflow Routes** (`circle_of_cashflow_routes.py`, 500+ lines): Full partner ecosystem
- **Referral Models** (3): ReferralPartner (with loyalty_tier, reciprocity_score, volume tracking), LoanTeamMember, MUMClient
- **Customer Intelligence Tools** (9): get_referral_network, create_referral_partner, map_relationships, find_opportunities
- **Agent Prompts**: Customer Intelligence core (158 lines) — Todd Duncan post-close methodology, 99% question, THE question, referral timeline
- **Lead Tracking**: referral_partner_id, referral_score, employment_referral_flag, circle_of_cashflow_map

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| Partner ROI calculation (Module 7.2 spec) | High | No revenue attribution |
| Partner satisfaction scoring | Medium | No relationship health metric |
| Partner onboarding workflows | Medium | Ad-hoc onboarding |
| 12-sector Circle mapping automation | Low | Manual sector tracking |
| Morning check-in capture (Module 7.4) | Medium | No daily partner activity log |

#### Module Compliance Score: 80/100

---

### MODULE 8: WORKFLOW AUTOMATION TRIGGERS — Grade: A- (85%)

**Status: FUNCTIONAL WITH STRONG FOUNDATION**

#### What EXISTS:
- **Lead Workflow Engine** (`workflows/lead_workflow_engine.py`, 280+ lines): State machine transitions, valid stage rules
- **Workflow Models** (9): Workflow, ScheduledWorkflow, WorkflowExecution, ProcessTemplate, ProcessRole, ProcessMilestone, ProcessTask, CalendarMapping, OnboardingStep
- **Workflow Tools** (35+): execute_workflow, get_workflow_status, create_task, bulk_update_tasks
- **Status Change Triggers**: Lead stage automation, task creation on transition, email/SMS sequences
- **Time-Based**: Scheduled workflows with cron expressions
- **Agent Prompts**: 18/20 agents define trigger points

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| Full status-to-action mapping (Module 8.1 spec) | High | Partial coverage |
| Advanced conditional logic (IF credit < 650 THEN...) | Medium | Simple triggers only |
| Multi-step approval chains | Medium | No multi-level approvals |
| Workflow version control/rollback | Low | No version history |
| Time-based trigger schedule (Module 8.2 spec) | Medium | Missing daily 8AM/6PM checks |
| Webhook-triggered workflows | Low | Enhancement |

#### Module Compliance Score: 85/100

---

### MODULE 9: REFINANCE INTELLIGENCE — Grade: B (75%)

**Status: TOOLS COMPLETE, MODELS PARTIAL**

#### What EXISTS:
- **Refi Tools** (11): score_refi_opportunity (0-100), get_refi_candidates, calculate_refi_savings, compare_refi_scenarios, analyze_breakeven, get_refi_portfolio_summary, batch_update_refi_scores, recommend_refi_action
- **Refi Services**: refinance_call_service.py, refinance_outreach_service.py (280+ lines), opportunity_detection_service.py
- **MUM Client Model**: Tracks original loan terms, current market rate, estimated equity, refi score, engagement metrics
- **Outreach Automation**: AI outbound call orchestration via VAPI, SMS + call sequences

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| RefiOpportunity model (individual opportunity tracking) | **Critical** | Only Boolean flag exists |
| RefiScenario model (rate/term/cashout comparison) | High | No scenario persistence |
| PortfolioMonitoring model (batch analysis jobs) | High | No run history |
| 16 refi type detection (Module 9.1 spec) | Medium | Limited type coverage |
| ARM conversion detection | Medium | Missing refi trigger |
| MI removal trigger (LTV < 78% auto-cancel) | Medium | No automated detection |
| Federal/state refi program awareness | Low | HARP/streamline programs |
| Todd Duncan refi outreach rules (Module 9.2) | Medium | Not in agent prompts |

#### Module Compliance Score: 75/100

---

## PHASE 4: SCALE & POLISH

### MODULE 10: ONBOARDING & TRAINING — Grade: B (75%)

**Status: FUNCTIONAL CORE**

#### What EXISTS:
- **Onboarding Routes** (`routes/onboarding_routes.py`, 500+ lines): Multi-step flows
- **Models** (4): OnboardingProgress, OnboardingError, OnboardingStep, VerificationToken
- **Permission System**: EmployeeInvite, PermissionTemplate, role-based checklists
- **Onboarding Tools** (12): get_onboarding_status, get_checklist, complete_step, guided_tour, training_resources, setup_wizard, request_support, track_progress
- **Agent Prompt**: Onboarding Assistant core (102 lines) — role-based checklists (LO: 8 steps/48h, Processor: 10 steps/72h, Manager: 12 steps/1wk, Admin: 15 steps/2wk)
- **Borrower Onboarding**: ApplicationStep enum with 10 steps

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| Checklist automation (auto-advance) | Medium | Manual step tracking |
| Training/certification tracking | Medium | No skill validation |
| Competency assessment | Low | Enhancement |
| Video onboarding content tracking | Low | No media tracking |
| Onboarding completion detection | Medium | No automated milestone alerts |

#### Module Compliance Score: 75/100

---

### MODULE 11: REPORTING & ANALYTICS INTELLIGENCE — Grade: B- (65%)

**Status: FOUNDATIONAL, MISSING NARRATIVE LAYER**

#### What EXISTS:
- **Daily Snapshots**: SecuritySnapshotDaily, AIMetricsDaily, AIChangelogDaily
- **Dashboard Routes** (`routes/dashboard_routes.py`): Pipeline metrics, aggregations
- **Scorecard Routes**: Performance scoring (individual, team)
- **AI Insights** (`services/ai_insights_service.py`): AI-generated insights
- **Receptionist Analytics**: Executive summary generation
- **Predictive AI** (`services/predictive_ai_service.py`): Prediction framework
- **Reporting Tools** (8): create_custom_report, generate_pipeline_report, generate_production_report, get_report_templates, schedule_report, export_report
- **Agent Prompts**: Pipeline Analyst (94 lines), Profitability Analyst (115 lines), Team Coach (102 lines) — all strong on metrics

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| **Narrative analytics** (Module 11.1 — "Your pipeline slowed 15% because...") | **Critical** | Data without meaning |
| Automated anomaly detection & explanation | High | Manual pattern finding |
| Comparative benchmarking (vs. peer LOs, industry) | Medium | Limited context |
| ReportDefinition model (saved report configs) | Medium | No reusable reports |
| AnalyticsConfig model (custom metrics/thresholds) | Medium | Hardcoded metrics |
| Executive weekly summary (Module 11.3 spec) | High | No automated weekly digest |
| Customer analytics (satisfaction, engagement trends) | Medium | Pipeline-heavy, customer-light |
| Marketing analytics (campaign ROI) | Medium | No campaign measurement |

#### Module Compliance Score: 65/100

---

### MODULE 12: LOS INTEGRATION & SYNC — Grade: B+ (85%)

**Status: HIGHLY COMPLETE FOR ENCOMPASS**

#### What EXISTS:
- **Sync Service** (`services/los_integration/sync_service.py`, 280+ lines): Bidirectional CRM <-> LOS
- **Encompass Client** (`services/los_integration/encompass_client.py`): Full API client
- **Field Mapping**: 48+ fields mapped
- **Conflict Resolution**: CRM-wins, LOS-wins, manual strategies
- **Webhook Ingestion**: Encompass -> CRM real-time updates
- **Integration Tools** (8): sync_los_data, check_integration_status, trigger_credit_pull, submit_to_aus, order_appraisal, order_title, send_for_esign, get_pricing_engine_quote
- **Salesforce Sync**: Full bidirectional sync for leads + loans
- **Agent Prompt**: Integrations Manager core (123 lines) — health monitoring, retry policy, data integrity checks

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| LosFieldMapping model (field-level audit trail) | Medium | No mapping transparency |
| LosSyncLog model (per-loan sync state) | Medium | Limited sync visibility |
| Multi-LOS support (Calyx, Blend, Fiserv) | Low | Encompass-only currently |
| Real-time bidirectional sync on every field change | Low | Batch sync sufficient |
| LOS error handling/retry logic in tools | Medium | Tools lack retry |
| Conflict resolution in edge cases | Low | Enhancement |

#### Module Compliance Score: 85/100

---

### MODULE 13: MARKETING CAMPAIGN ORCHESTRATION — Grade: C+ (55%)

**Status: ACQUISITION ENGINE EXISTS, CAMPAIGNS UNDERDEVELOPED**

#### What EXISTS:
- **Acquisition Engine**: conversion_orchestrator.py (280+ lines), speed_to_lead_service.py, temperature_service.py
- **Campaign Models**: VoicemailCampaign (with contact filters), ScheduledWorkflow (campaign-like)
- **Speed-to-Lead**: SMS within 30 seconds of lead creation
- **Lead Nurture**: workflow_day tracking, nurture_month, current_workflow_id
- **Content Personalization**: content_personalization_service.py
- **Lead Outreach Tools**: draft_message, schedule_outreach, get_email_templates, get_stale_leads, batch_send
- **Agent Prompts**: Lead Agent (71 lines), Notification Center (121 lines) — but NO dedicated marketing agent

#### What's MISSING:
| Gap | Priority | Impact |
|---|---|---|
| AudienceSegment model (saved audience definitions) | High | No segmentation |
| CampaignDefinition model (campaign templates) | High | No campaign lifecycle |
| DripSequence model (multi-touch sequences) | High | Hardcoded sequences |
| Pre-built campaigns (Module 13.1 — welcome, post-close, stale re-engagement, rate drop) | **Critical** | No campaign library |
| A/B testing framework | Medium | No optimization |
| Campaign performance tracking/ROI | **Critical** | No measurement |
| Campaign compliance (CAN-SPAM, TCPA per Module 13.3) | Medium | Partial via TCPA tools |
| Audience segmentation by lifecycle/source/product/engagement (Module 13.2) | High | No segment builder |
| Seasonal campaign triggers | Low | Enhancement |
| Dedicated Marketing Campaign Agent prompt | High | No agent owns this domain |

#### Module Compliance Score: 55/100

---

## CROSS-CUTTING ANALYSIS

### Agent-to-Module Mapping — Actual vs. Expected

| Agent | Expected Modules | Prompt Exists | Tools Exist | Gap |
|---|---|---|---|---|
| Pipeline Analyst | 1,2,3,8,11 | Yes (94 lines) | Yes (8 tools) | Missing Module 11 narrative analytics |
| Compliance Checker | 1,2,3 | Yes (104 lines) | Yes (12 tools) | Complete |
| Lead Nurturer | 1,2,3,7,8,9,13 | Yes (71 lines) | Yes (9 tools) | Missing Modules 9,13 in prompt |
| Document Tracker | 1,2,3,4 | Yes (79 lines) | Yes (16 tools) | Complete |
| Profitability Analyst | 1,2,3,11 | Yes (115 lines) | Yes (8 tools) | Missing Module 11 narrative |
| Rate Advisor | 1,2,3,6,9 | Yes (150 lines) | Yes (12 tools) | Missing Module 9 in prompt |
| Team Coach | 1,2,3,11 | Yes (102 lines) | Yes (8 tools) | Missing Module 11 narrative |
| Customer Intelligence | 1,2,3,7,9 | Yes (158 lines) | Yes (9 tools) | Module 9 implicit only |
| Voice OS | 1,2,3,5 | Yes (161 lines) | Yes (8 tools) | Complete |
| UVIP | 1,2,3,5 | Yes (130 lines) | Yes (9 tools) | Complete |
| Email Intelligence | 1,2,3,4,5,13 | Yes (73 lines) | Yes (15 tools) | Missing Module 13 campaign logic |
| AI Receptionist | 1,2,3,5 | Yes (163 lines) | Yes (8 tools) | Complete |
| Smart Scheduler | 1,2,3 | Yes (106 lines) | Yes (8 tools) | Complete |
| Task Automation | 1,2,3,8 | N/A (workflow engine) | Yes (9 tools) | No dedicated prompt |
| SLA Tracker | 1,2,3,8 | Yes (109 lines) | Yes (8 tools) | Complete |
| Integrations | 1,2,3,12 | Yes (123 lines) | Yes (8 tools) | Complete |
| Reporting | 1,2,3,11 | N/A (service-based) | Yes (8 tools) | No dedicated prompt + missing narrative |
| Notifications | 1,2,3,5,8 | Yes (121 lines) | Yes (8 tools) | Complete |
| Subscription | 1,2,3,10 | Yes (101 lines) | Yes (8 tools) | Complete |
| Onboarding | 1,2,3,10 | Yes (102 lines) | Yes (12 tools) | Complete |

### Database Model Coverage

| Module | Models Exist | Models Missing | Gap Severity |
|---|---|---|---|
| 1. Compliance | 4 models | 0 | None |
| 2. Memory | 2 models | 3 (Session, Entity, Context) | Medium |
| 3. Escalation | 3 task-based | 2 (EscalationRecord, HandoffLog) | Low |
| 4. Documents | 6 models | 0 | None |
| 5. Channel | 7 messaging | 3 (Preference, Template, Config) | Medium |
| 6. Rates | 4 enum+fields | 2 (RateLock, MarketData) | Medium |
| 7. Referrals | 3 models | 0 | None |
| 8. Workflows | 9 models | 0 | None |
| 9. Refi | 1 partial (MUMClient) | 4 (Opportunity, Scenario, Portfolio, Target) | **High** |
| 10. Onboarding | 4 models | 0 | None |
| 11. Reporting | 5 snapshots | 2 (ReportDefinition, AnalyticsConfig) | Low |
| 12. LOS | 3 models | 3 (FieldMapping, SyncLog, Config) | Medium |
| 13. Marketing | 5 partial | 3 (Segment, Campaign, DripSequence) | Medium |
| **TOTAL** | **80+ models** | **~22 models needed** | |

---

## STRENGTHS ASSESSMENT

### Best-in-Class Implementations

1. **Compliance Guardrails** (95% confidence) — Universal compliance_rules.md + agent-specific TRID/RESPA/ECOA/Fair Lending implementation across 18/20 agents with clear values hierarchy: Compliance > Borrower Experience > Company Risk > Efficiency

2. **Decision Engine Framework** — 6-point protocol (Clarify > Priority > Confidence > Complete > Evaluate > Learn) applied consistently across 18+ agents with confidence thresholds tied to action types

3. **Todd Duncan Integration** — Sales methodology deeply embedded in 5+ core agents: Lead Agent (20/80 talk ratio), Customer Intelligence (THE question), Rate Advisor (price-to-advice transition), Voice OS (telephony profile), Team Coach (strengths-first coaching)

4. **Tool Selection Chains** — Explicit sequencing prevents misuse: Lead Agent: `get_lead_details` -> `score_lead` -> `validate_outbound_contact` -> `draft_message`

5. **Document Intelligence** — Claude Vision AI + Smart Docs pipeline with 24 document types, freshness validation, and DRE email intake integration

6. **Rate Lock Engine** — Sophisticated lock scoring (0-100), float monitoring, market data from FRED/MBS, and comprehensive objection handling

---

## PRIORITIZED REMEDIATION PLAN

### TIER 1 — CRITICAL (Next 2 Weeks)

| # | Action | Module | Lines | Impact |
|---|---|---|---|---|
| 1 | Build escalation strategy rules + warm handoff protocol | 3 | ~200 | Agents stop operating in silos |
| 2 | Add narrative analytics layer to reporting tools | 11 | ~150 | Data becomes actionable insight |
| 3 | Create RefiOpportunity + RefiScenario DB models | 9 | ~150 | Unlocks portfolio revenue |
| 4 | Implement co-reference resolution for conversation memory | 2 | ~100 | Fixes #1 broken behavior |

### TIER 2 — HIGH (Weeks 3-4)

| # | Action | Module | Lines | Impact |
|---|---|---|---|---|
| 5 | Create AudienceSegment + CampaignDefinition + DripSequence models | 13 | ~120 | Enables marketing automation |
| 6 | Build dedicated Marketing Campaign Agent prompt | 13 | ~180 | No agent owns this domain |
| 7 | Add ChannelPreference + MessageTemplate models | 5 | ~150 | Unified omnichannel |
| 8 | Add RateLock ledger + RateMarketData models | 6 | ~80 | Lock history tracking |
| 9 | Add rate communication guidance to Voice OS, Video, Customer Intel prompts | 6 | ~60 | Prevent incorrect rate discussions |

### TIER 3 — MEDIUM (Weeks 5-6)

| # | Action | Module | Lines | Impact |
|---|---|---|---|---|
| 10 | Pre-built campaign library (welcome, post-close, stale, rate drop) | 13 | ~200 | Campaign templates |
| 11 | Partner ROI calculation implementation | 7 | ~100 | Revenue attribution |
| 12 | LosFieldMapping + LosSyncLog models | 12 | ~100 | Sync audit trail |
| 13 | ConversationSession + EntityExtraction models | 2 | ~100 | Multi-turn context |
| 14 | Full Module 8.1 status-to-action mapping | 8 | ~150 | Complete automation triggers |

### TIER 4 — ENHANCEMENTS (Weeks 7-8)

| # | Action | Module | Lines | Impact |
|---|---|---|---|---|
| 15 | Campaign A/B testing framework | 13 | ~100 | Campaign optimization |
| 16 | Automated anomaly detection + explanation | 11 | ~150 | Proactive intelligence |
| 17 | Executive weekly summary automation | 11 | ~100 | Management visibility |
| 18 | Advanced conditional workflow logic | 8 | ~100 | Complex automation |
| 19 | EscalationRecord + HandoffLog models | 3 | ~50 | Escalation audit trail |
| 20 | Dynamic state requirements (beyond 4 states) | 1 | ~200 | Scale compliance |

---

## NEW FILES TO CREATE

```
backend/database/models/
  refinance.py        (NEW — 150 lines: RefiOpportunity, RefiScenario, PortfolioMonitoring)
  rates.py            (NEW — 80 lines: RateLock, RateMarketData)
  marketing.py        (NEW — 120 lines: AudienceSegment, CampaignDefinition, DripSequence)
  los_integration.py  (NEW — 100 lines: LosFieldMapping, LosSyncLog)

backend/database/models/communication.py  (EXTEND +150 lines: ConversationSession, EntityExtraction, ChannelPreference, MessageTemplate)
backend/database/models/task.py           (EXTEND +50 lines: EscalationRecord, HandoffLog)

backend/agents/perennia-prompts/core/
  marketing_campaign_core.md  (NEW — 180 lines)
  reporting_analyst_core.md   (NEW — 120 lines)

backend/services/
  narrative_analytics_service.py    (NEW — 150 lines)
  escalation_strategy_service.py    (NEW — 200 lines)
  coreference_resolution_service.py (NEW — 100 lines)
```

**Total new code: ~1,550 lines across 11 files**

---

## MASTER SELF-CHECK PROTOCOL STATUS

Per the skill specification, every agent should run this before every response:

| Check | Status | Coverage |
|---|---|---|
| COMPLIANCE (Module 1): Response complies with regulations? | **IMPLEMENTED** | 18/20 agents |
| COMPLIANCE: Sharing info only with authorized parties? | **PARTIAL** | No auto-enforcement of Module 5.2 boundaries |
| COMPLIANCE: Required disclosures included? | **IMPLEMENTED** | In compliance tools |
| MEMORY (Module 2): Using context from this conversation? | **PARTIAL** | No co-reference resolution |
| MEMORY: Resolved pronouns/implicit references? | **NOT IMPLEMENTED** | Critical gap |
| MEMORY: Building on conversation, not starting over? | **PARTIAL** | No handoff context |
| ESCALATION (Module 3): Within my domain? If not, route? | **PARTIAL** | No auto-routing |
| ESCALATION: 100% confident? If not, flag? | **IMPLEMENTED** | Confidence thresholds in agents |
| ESCALATION: User asked for human? Transfer? | **IMPLEMENTED** | In receptionist |
| CHANNEL (Module 5): Formatted for right channel? | **PARTIAL** | Channel-specific but not cross-channel |
| METHODOLOGY: Talking less than 25%? | **IMPLEMENTED** | Todd Duncan 20/80 ratio |
| METHODOLOGY: Emotion before economics? | **IMPLEMENTED** | In 5+ agent prompts |

---

## CONCLUSION

Perennia AI is a **mature, compliance-first mortgage CRM** with exceptional agent intelligence for loan processing, regulatory compliance, and individual borrower management. The platform's greatest strengths — its Decision Engine, Todd Duncan integration, and compliance framework — represent genuine competitive advantages.

**The critical gaps are in three areas:**

1. **Escalation Intelligence (Module 3, 45%)** — Agents operate in silos without proper handoff protocols. This is the #1 operational gap affecting user experience.

2. **Marketing Campaign Orchestration (Module 13, 55%)** — No campaign lifecycle management, no segmentation, no measurement. This directly impacts revenue growth.

3. **Narrative Analytics (Module 11, 65%)** — The platform collects excellent data but doesn't tell the story. "Your pipeline has 47 loans" is not as useful as "Your pipeline slowed 18% — here's why and what to do."

**Addressing these three gaps would move the platform from 80% to ~92% coverage** across all 13 modules.

---

*Generated by /u-gap-analysis v1.0.0 | Perennia AI Platform*
*© 2026 TL Development LLC*
