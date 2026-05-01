"""
Agent Consolidation Framework
==============================
Maps the current 60 agent roles to 10 first-class agents for gradual migration.

This is an OVERLAY module -- it does NOT modify existing agent service, orchestrator,
or tool files. The consolidated agent configs are used by new code paths that opt in
to the consolidated routing, while the legacy 60-agent system continues to work.

The 10 first-class agents:
    1. Aria           - Inbound receptionist + general voice
    2. Avery          - Outbound URLA / data collection
    3. Pipeline Coach - Proactive next-best-action per loan
    4. Calculator     - Affordability, scenarios, rate-shopping
    5. Doc Intel      - Smart Docs unified
    6. Compliance     - TRID, fair lending, TCPA, RESPA
    7. Email Intel    - Inbox management, DRE
    8. Talent Radar   - Recruiting, coaching, performance
    9. Opportunity    - MUM / market analysis, customer intel
   10. UW Copilot     - Guideline RAG + scenario reasoning

Usage:
    from agents.consolidation import (
        get_consolidated_agent_config,
        CONSOLIDATED_AGENTS,
        resolve_legacy_role,
        get_tools_for_consolidated_agent,
    )

    # Get a consolidated agent config
    config = get_consolidated_agent_config("aria")

    # Map a legacy role to its consolidated agent
    consolidated = resolve_legacy_role("ai_receptionist")
    # -> "aria"
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# CONSOLIDATED AGENT DEFINITIONS
# =============================================================================

@dataclass(frozen=True)
class ConsolidatedAgent:
    """
    First-class agent definition in the consolidated 10-agent system.

    Attributes:
        id: Unique short identifier (e.g. "aria", "pipeline_coach")
        name: Human-readable display name
        description: What this agent does
        persona: Brief persona description for prompt building
        recommended_model: "sonnet" for complex reasoning, "haiku" for tool-heavy
        legacy_roles: Set of legacy agent roles this absorbs
        tool_names: Deduplicated union of all tools from absorbed roles + extras
        requires_approval_for: Tools that need user confirmation
        max_concurrent_tools: Parallel tool execution limit
    """
    id: str
    name: str
    description: str
    persona: str
    recommended_model: str
    legacy_roles: FrozenSet[str]
    tool_names: Tuple[str, ...]
    requires_approval_for: Tuple[str, ...] = ()
    max_concurrent_tools: int = 5


# ---------------------------------------------------------------------------
# 1. Aria -- Inbound receptionist + general voice
# ---------------------------------------------------------------------------
ARIA = ConsolidatedAgent(
    id="aria",
    name="Aria",
    description=(
        "Inbound AI receptionist and general-purpose voice agent. Handles "
        "greetings, caller qualification, call routing, voicemail, and live "
        "call management. The primary voice interface for the platform."
    ),
    persona=(
        "You are Aria, the AI receptionist for the loan team. You are warm, "
        "professional, and efficient. You qualify callers, route to the right "
        "LO, manage callbacks, and handle basic CRM lookups via voice."
    ),
    recommended_model="haiku",
    legacy_roles=frozenset({
        "ai_receptionist",
        "voice_os",
    }),
    tool_names=(
        # Receptionist tools
        "get_greeting_script",
        "qualify_caller",
        "route_call",
        "create_callback_request",
        "get_lo_availability",
        "get_call_queue_status",
        "handle_inbound_call",
        "log_call_interaction",
        # Voice tools
        "initiate_outbound_call",
        "drop_voicemail",
        "get_call_history",
        "analyze_call_sentiment",
        "schedule_callback",
        "get_power_dialer_queue",
        "transcribe_call",
        "get_call_metrics",
        # SMS tools (voice agents need SMS too)
        "send_sms_message",
        "get_sms_conversation_history",
        "start_scheduling_sms",
        # Quick CRM lookups for voice context
        "search_leads",
        "search_loans",
        "get_lead_details",
        "get_customer_360",
        "get_interaction_history",
        "get_daily_priorities",
    ),
    requires_approval_for=("initiate_outbound_call",),
    max_concurrent_tools=3,
)

# ---------------------------------------------------------------------------
# 2. Avery -- Outbound URLA / data collection
# ---------------------------------------------------------------------------
AVERY = ConsolidatedAgent(
    id="avery",
    name="Avery",
    description=(
        "Outbound data collection agent. Handles URLA data gathering, lead "
        "qualification via SMS/phone, scheduling conversations, pre-approval "
        "workflows, and borrower onboarding data capture."
    ),
    persona=(
        "You are Avery, the outbound engagement specialist. You reach out to "
        "leads and borrowers to collect loan application data, qualify them, "
        "schedule appointments, and guide them through pre-approval."
    ),
    recommended_model="sonnet",
    legacy_roles=frozenset({
        "lead_nurturer",
        "pre_approval_specialist",
        "credit_repair_advisor",
        "down_payment_advisor",
        "borrower_concierge",
        "onboarding_assistant",
    }),
    tool_names=(
        # Lead engagement
        "get_lead_details",
        "get_engagement_history",
        "score_lead",
        "suggest_followup",
        "draft_message",
        "schedule_outreach",
        "get_similar_converted_leads",
        "get_optimal_contact_time",
        "get_stale_leads",
        "get_top_leads",
        # Pre-approval
        "get_state_requirements",
        "check_fair_lending",
        "get_pricing_engine_quote",
        "get_current_rates",
        "generate_pre_approval_letter",
        # Borrower concierge
        "get_customer_360",
        "get_interaction_history",
        "get_loan_conditions",
        "get_missing_documents",
        "get_upcoming_appointments",
        "send_notification",
        # Onboarding
        "get_onboarding_status",
        "get_checklist",
        "complete_step",
        "start_guided_tour",
        "get_training_resources",
        "get_setup_wizard",
        "request_support",
        "track_progress",
        # Scheduling
        "get_availability",
        "book_appointment",
        "reschedule_appointment",
        "cancel_appointment",
        "send_appointment_reminder",
        # Outreach
        "find_clients_for_outreach",
        "send_bulk_sms_outreach",
        "send_mortgage_review_outreach",
        "send_calendar_invite_email",
        # SMS
        "send_sms_message",
        "get_sms_conversation_history",
        "start_scheduling_sms",
        # Base
        "search_leads",
        "search_loans",
        "create_task",
    ),
    requires_approval_for=("send_email", "send_sms", "make_call"),
    max_concurrent_tools=5,
)

# ---------------------------------------------------------------------------
# 3. Pipeline Coach -- Proactive next-best-action per loan
# ---------------------------------------------------------------------------
PIPELINE_COACH = ConsolidatedAgent(
    id="pipeline_coach",
    name="Pipeline Coach",
    description=(
        "Proactive pipeline management and next-best-action advisor. Analyzes "
        "pipeline health, identifies bottlenecks, tracks SLA compliance, "
        "manages tasks/workflows, and coaches LOs on performance improvement."
    ),
    persona=(
        "You are the Pipeline Coach. You provide proactive, data-driven "
        "recommendations on which loans need attention, what tasks to "
        "prioritize, and how to optimize pipeline throughput and pull-through."
    ),
    recommended_model="sonnet",
    legacy_roles=frozenset({
        "pipeline_analyst",
        "sla_tracker",
        "task_automation",
        "smart_scheduler",
        "ops_manager",
        "reporting_engine",
        "notification_center",
        "closing_coordinator",
        "warehouse_manager",
        "shipping_coordinator",
        "uvip",
    }),
    tool_names=(
        # Pipeline analytics
        "get_pipeline_metrics",
        "get_loans_by_status",
        "get_loan_aging_report",
        "calculate_conversion_rates",
        "predict_closing_timeline",
        "get_bottleneck_analysis",
        "compare_to_benchmark",
        "get_lo_pipeline_breakdown",
        # SLA
        "check_sla_status",
        "get_sla_dashboard",
        "get_sla_alerts",
        "calculate_stage_sla",
        "configure_sla_rules",
        "get_sla_report",
        "project_sla_breach",
        "escalate_sla_breach",
        # Tasks
        "create_task",
        "bulk_create_tasks",
        "get_task_queue",
        "update_task_status",
        "assign_task",
        "get_task_templates",
        "bulk_update_tasks",
        "execute_workflow",
        "get_workflow_status",
        "get_daily_call_list",
        # Scheduling
        "get_availability",
        "book_appointment",
        "reschedule_appointment",
        "cancel_appointment",
        "get_upcoming_appointments",
        "send_appointment_reminder",
        "sync_external_calendar",
        "optimize_schedule",
        # Reporting
        "generate_pipeline_report",
        "generate_production_report",
        "generate_lo_performance_report",
        "get_report_templates",
        "schedule_report",
        "export_report",
        "get_dashboard_metrics",
        "create_custom_report",
        # Historical
        "get_performance_by_period",
        "compare_periods",
        "get_data_availability",
        # Notifications
        "send_notification",
        "get_pending_notifications",
        "get_notification_templates",
        "schedule_notification",
        "get_delivery_status",
        "update_preferences",
        "get_preferences",
        "batch_send",
        # Closing coordination
        "order_title",
        "get_third_party_status",
        "get_disclosure_timeline",
        "check_document_expiration",
        "get_missing_documents",
        "get_loan_conditions",
        "track_document_request",
        "send_document_reminder",
        # Base
        "get_daily_priorities",
        "get_pipeline",
        "get_tasks",
        "search_leads",
        "search_loans",
        # Escalation
        "escalate_issue",
        "evaluate_escalation",
        "create_escalation",
        "get_escalation_status",
        "execute_warm_handoff",
        "resolve_escalation",
        "get_escalation_analytics",
    ),
    requires_approval_for=("batch_send",),
    max_concurrent_tools=5,
)

# ---------------------------------------------------------------------------
# 4. Calculator Agent -- Affordability, scenarios, rate-shopping
# ---------------------------------------------------------------------------
CALCULATOR = ConsolidatedAgent(
    id="calculator",
    name="Calculator Agent",
    description=(
        "Financial calculator and rate advisory agent. Handles affordability "
        "analysis, rate lock/float decisions, scenario comparison, loan "
        "structuring, profitability analysis, and revenue forecasting."
    ),
    persona=(
        "You are the Calculator Agent. You provide precise financial analysis "
        "including rate comparisons, lock strategy recommendations, loan "
        "profitability calculations, and multi-scenario structuring."
    ),
    recommended_model="sonnet",
    legacy_roles=frozenset({
        "rate_advisor",
        "profitability_analyst",
        "revenue_forecaster",
        "pricing_strategist",
        "loan_structuring",
        "secondary_market",
        "commercial_bridge",
    }),
    tool_names=(
        # Rates
        "get_current_rates",
        "analyze_rate_trends",
        "calculate_lock_cost",
        "recommend_lock_strategy",
        "monitor_float_position",
        "get_extension_pricing",
        "compare_rate_scenarios",
        "get_market_events",
        # Profitability
        "calculate_loan_profitability",
        "analyze_margins_by_segment",
        "forecast_revenue",
        "compare_lo_profitability",
        "optimize_pricing",
        "get_cost_breakdown",
        "calculate_pull_through_impact",
        "get_profitability_trends",
        # Home valuation / amortization
        "calculate_home_value",
        "get_appreciation_rates",
        "calculate_equity_position",
        "calculate_amortization",
        "get_maturity_date",
        "get_value_history",
        "compare_market_appreciation",
        # Refinance analysis
        "score_refi_opportunity",
        "calculate_refi_savings",
        "get_refi_candidates",
        "analyze_breakeven",
        "compare_refi_scenarios",
        "get_refi_portfolio_summary",
        "recommend_refi_action",
        # Pricing
        "get_pricing_engine_quote",
        # Pipeline context
        "get_pipeline_metrics",
        "predict_closing_timeline",
        "calculate_conversion_rates",
        # Base
        "search_loans",
        "get_pipeline",
    ),
    requires_approval_for=("lock_rate",),
    max_concurrent_tools=5,
)

# ---------------------------------------------------------------------------
# 5. Document Intelligence -- Smart Docs unified
# ---------------------------------------------------------------------------
DOC_INTEL = ConsolidatedAgent(
    id="doc_intel",
    name="Document Intelligence",
    description=(
        "Unified document management agent. Tracks conditions, missing docs, "
        "third-party orders, document freshness, SLA compliance, OCR "
        "extraction, portal activity, and follow-up campaigns."
    ),
    persona=(
        "You are the Document Intelligence agent. You track every document "
        "across the loan lifecycle -- conditions, third-party orders, "
        "expirations, and portal activity -- and proactively flag what needs "
        "attention."
    ),
    recommended_model="haiku",
    legacy_roles=frozenset({
        "document_tracker",
        "title_vendor_manager",
        "appraiser_coordinator",
        "insurance_coordinator",
    }),
    tool_names=(
        # Core document tracking
        "get_missing_documents",
        "get_loan_conditions",
        "track_document_request",
        "send_document_reminder",
        "escalate_issue",
        "get_document_timeline",
        "check_document_expiration",
        "get_third_party_status",
        # Smart docs bridge
        "get_smart_doc_status",
        "check_document_freshness",
        "get_document_decisions",
        "get_needs_list",
        "check_document_sla",
        "get_screenshot_flags",
        "get_document_extraction",
        "track_portal_activity",
        "get_followup_campaign_status",
        "get_policy_events",
        # Pre-approval letter
        "generate_pre_approval_letter",
        # Third-party ordering
        "order_title",
        "order_appraisal",
        # Notifications for doc reminders
        "send_notification",
        "create_task",
        # Base
        "search_loans",
        "get_pipeline",
    ),
    requires_approval_for=("send_document_reminder",),
    max_concurrent_tools=5,
)

# ---------------------------------------------------------------------------
# 6. Compliance Sentry -- TRID, fair lending, TCPA, RESPA
# ---------------------------------------------------------------------------
COMPLIANCE = ConsolidatedAgent(
    id="compliance",
    name="Compliance Sentry",
    description=(
        "Regulatory compliance agent. Monitors TRID timelines, RESPA "
        "violations, fair lending, state requirements, tolerance cures, "
        "QC audits, fraud detection, and DNC/TCPA consent checks."
    ),
    persona=(
        "You are the Compliance Sentry. You ensure every loan meets federal "
        "and state regulatory requirements. You never guess on compliance "
        "questions -- you cite specific regulations and flag ambiguity."
    ),
    recommended_model="sonnet",
    legacy_roles=frozenset({
        "compliance_checker",
        "quality_control",
        "fraud_detector",
        "risk_assessor",
        "turn_down_specialist",
        "investor_relations",
    }),
    tool_names=(
        # Core compliance
        "check_trid_compliance",
        "check_respa_compliance",
        "check_fair_lending",
        "get_state_requirements",
        "audit_loan_file",
        "get_disclosure_timeline",
        "check_tolerance_violations",
        "get_compliance_history",
        # TCPA / DNC (outreach compliance)
        "check_dnc_status",
        "check_tcpa_consent",
        "check_calling_window",
        "validate_outbound_contact",
        # Fraud detection tools (reuse email for wire fraud)
        "parse_email",
        "get_email_thread",
        "match_email_to_loan",
        # Risk assessment context
        "get_pipeline_metrics",
        "get_loan_aging_report",
        "get_bottleneck_analysis",
        "calculate_loan_profitability",
        # Adverse action
        "get_lead_details",
        "get_customer_360",
        "draft_message",
        "send_email",
        "send_notification",
        "escalate_issue",
        "create_task",
        # Base
        "search_loans",
        "get_pipeline",
    ),
    requires_approval_for=("override_compliance_flag",),
    max_concurrent_tools=5,
)

# ---------------------------------------------------------------------------
# 7. Email Intelligence -- Inbox management, DRE
# ---------------------------------------------------------------------------
EMAIL_INTEL = ConsolidatedAgent(
    id="email_intel",
    name="Email Intelligence",
    description=(
        "Email management and DRE (Data Recognition Engine) agent. Parses "
        "inbound emails, classifies intent, drafts contextual responses, "
        "manages templates, and handles content creation for drip campaigns."
    ),
    persona=(
        "You are the Email Intelligence agent. You parse emails to extract "
        "loan-relevant data, draft professional responses matching the LO's "
        "tone, and manage email-based borrower communication workflows."
    ),
    recommended_model="sonnet",
    legacy_roles=frozenset({
        "email_intelligence",
        "content_creator",
        "social_media_manager",
        "campaign_manager",
        "review_manager",
    }),
    tool_names=(
        # Core email
        "parse_email",
        "get_email_thread",
        "draft_email_response",
        "get_email_templates",
        "send_email",
        "categorize_email_attachments",
        "match_email_to_loan",
        "analyze_email_engagement",
        "search_email_inbox",
        "find_contact_email",
        "find_contact_phone",
        "get_emails_needing_response",
        "analyze_tone",
        "get_thread_tone_trends",
        "compare_tone_to_baseline",
        # Content / campaigns
        "draft_message",
        "schedule_notification",
        "get_notification_templates",
        "batch_send",
        "get_delivery_status",
        # Outreach
        "send_bulk_email_outreach",
        "send_calendar_invite_email",
        # Market context for content
        "get_market_events",
        "analyze_rate_trends",
        "get_current_rates",
        "get_report_templates",
        "get_dashboard_metrics",
        # Customer context
        "get_customer_360",
        "get_interaction_history",
        "get_referral_network",
        "find_opportunities",
        # Base
        "search_leads",
        "search_loans",
        "create_task",
    ),
    requires_approval_for=("send_email", "batch_send"),
    max_concurrent_tools=5,
)

# ---------------------------------------------------------------------------
# 8. Talent Radar -- Recruiting, coaching, performance
# ---------------------------------------------------------------------------
TALENT_RADAR = ConsolidatedAgent(
    id="talent_radar",
    name="Talent Radar",
    description=(
        "Recruiting, coaching, and performance management agent. Handles LO "
        "recruiting, training needs assessment, coaching plans, performance "
        "benchmarking, and team analytics."
    ),
    persona=(
        "You are Talent Radar. You help branch managers recruit top LOs, "
        "coach underperformers, benchmark team metrics, and build training "
        "programs that drive production growth."
    ),
    recommended_model="sonnet",
    legacy_roles=frozenset({
        "team_coach",
        "recruiter",
        "training_specialist",
        "performance_manager",
    }),
    tool_names=(
        # Coaching
        "get_lo_metrics",
        "compare_to_peers",
        "identify_training_needs",
        "generate_coaching_plan",
        "track_improvement",
        "get_best_practices",
        "get_performance_trends",
        "set_performance_goals",
        # Historical
        "get_performance_by_period",
        "compare_periods",
        "get_data_availability",
        # Recruiting context
        "get_dashboard_metrics",
        "get_training_resources",
        # Communication
        "draft_message",
        "send_email",
        "send_notification",
        "schedule_notification",
        "create_task",
        "schedule_outreach",
    ),
    requires_approval_for=(),
    max_concurrent_tools=5,
)

# ---------------------------------------------------------------------------
# 9. Opportunity Agent -- MUM / market analysis, customer intel
# ---------------------------------------------------------------------------
OPPORTUNITY = ConsolidatedAgent(
    id="opportunity",
    name="Opportunity Agent",
    description=(
        "Market intelligence and opportunity identification agent. Analyzes "
        "customer relationships, identifies refinance/purchase opportunities, "
        "tracks referral networks, monitors market trends, and manages "
        "home valuations and post-closing care."
    ),
    persona=(
        "You are the Opportunity Agent. You identify hidden revenue "
        "opportunities in the existing book of business -- refinance "
        "candidates, referral potential, equity plays, and market timing."
    ),
    recommended_model="sonnet",
    legacy_roles=frozenset({
        "customer_intelligence",
        "home_valuation",
        "refinance_advisor",
        "referral_partner_manager",
        "post_closing_care",
        "market_analyst",
        "servicing_transfer",
    }),
    tool_names=(
        # Customer intelligence
        "get_customer_360",
        "map_relationships",
        "calculate_ltv",
        "assess_churn_risk",
        "find_opportunities",
        "get_interaction_history",
        "get_referral_network",
        "get_market_comparison",
        "create_referral_partner",
        # Home valuation
        "calculate_home_value",
        "get_appreciation_rates",
        "calculate_equity_position",
        "calculate_amortization",
        "get_maturity_date",
        "batch_update_valuations",
        "get_value_history",
        "compare_market_appreciation",
        # Refinance
        "score_refi_opportunity",
        "calculate_refi_savings",
        "get_refi_candidates",
        "analyze_breakeven",
        "compare_refi_scenarios",
        "get_refi_portfolio_summary",
        "recommend_refi_action",
        "batch_update_refi_scores",
        # Market
        "get_market_events",
        "analyze_rate_trends",
        "get_current_rates",
        "get_profitability_trends",
        # Outreach
        "draft_message",
        "send_email",
        "schedule_outreach",
        "send_notification",
        "send_bulk_sms_outreach",
        "send_mortgage_review_outreach",
        "find_clients_for_outreach",
        # Base
        "search_leads",
        "search_loans",
        "create_task",
        "get_pipeline",
    ),
    requires_approval_for=(),
    max_concurrent_tools=5,
)

# ---------------------------------------------------------------------------
# 10. Underwriter Copilot -- Guideline RAG + scenario reasoning
# ---------------------------------------------------------------------------
UW_COPILOT = ConsolidatedAgent(
    id="uw_copilot",
    name="Underwriter Copilot",
    description=(
        "Guideline RAG and scenario reasoning agent. Handles LOS integration, "
        "loan-product matching (VA, FHA, jumbo, construction, reverse), "
        "underwriting condition analysis, and investor overlay checks."
    ),
    persona=(
        "You are the Underwriter Copilot. You apply guideline knowledge to "
        "specific loan scenarios -- product eligibility, condition clearing, "
        "investor overlays, and exception justification."
    ),
    recommended_model="sonnet",
    legacy_roles=frozenset({
        "integrations",
        "va_loan_specialist",
        "fha_loan_specialist",
        "jumbo_specialist",
        "reverse_mortgage_advisor",
        "construction_loan_advisor",
        "subscription_manager",
        "system_health_monitor",
        "data_quality_manager",
        "migration_assistant",
    }),
    tool_names=(
        # LOS integration
        "sync_los_data",
        "check_integration_status",
        "trigger_credit_pull",
        "submit_to_aus",
        "order_appraisal",
        "order_title",
        "get_pricing_engine_quote",
        "send_for_esign",
        # LOS sync bridge
        "get_sync_status",
        "get_field_mappings",
        "resolve_sync_conflict",
        "trigger_sync",
        "get_sync_health",
        "update_field_mapping",
        # Guideline context
        "get_state_requirements",
        "check_trid_compliance",
        "check_fair_lending",
        "audit_loan_file",
        "get_missing_documents",
        "get_loan_conditions",
        "get_compliance_history",
        "check_tolerance_violations",
        # Pricing
        "get_current_rates",
        "compare_rate_scenarios",
        "calculate_loan_profitability",
        # Customer context
        "get_customer_360",
        "draft_message",
        "send_email",
        "create_task",
        "send_notification",
        "schedule_outreach",
        # Subscription / platform admin (absorbs subscription_manager)
        "get_subscription_status",
        "get_plans",
        "change_plan",
        "get_billing_history",
        "update_payment_method",
        "get_usage_metrics",
        "manage_addons",
        "pause_subscription",
        # System health
        "get_dashboard_metrics",
        "get_report_templates",
        "export_report",
        "schedule_report",
        # Base
        "search_loans",
        "search_leads",
        "get_pipeline",
    ),
    requires_approval_for=(
        "trigger_credit_pull",
        "submit_to_aus",
        "change_plan",
        "update_payment_method",
    ),
    max_concurrent_tools=5,
)


# =============================================================================
# CONSOLIDATED AGENTS REGISTRY
# =============================================================================

CONSOLIDATED_AGENTS: Dict[str, ConsolidatedAgent] = {
    agent.id: agent
    for agent in [
        ARIA,
        AVERY,
        PIPELINE_COACH,
        CALCULATOR,
        DOC_INTEL,
        COMPLIANCE,
        EMAIL_INTEL,
        TALENT_RADAR,
        OPPORTUNITY,
        UW_COPILOT,
    ]
}


# =============================================================================
# LEGACY ROLE -> CONSOLIDATED AGENT MAPPING
# =============================================================================

def _build_legacy_mapping() -> Dict[str, str]:
    """Build reverse mapping from legacy role to consolidated agent ID."""
    mapping: Dict[str, str] = {}
    for agent in CONSOLIDATED_AGENTS.values():
        for legacy_role in agent.legacy_roles:
            if legacy_role in mapping:
                logger.warning(
                    f"Legacy role '{legacy_role}' mapped to both "
                    f"'{mapping[legacy_role]}' and '{agent.id}' -- "
                    f"keeping first mapping"
                )
                continue
            mapping[legacy_role] = agent.id
    return mapping


LEGACY_TO_CONSOLIDATED: Dict[str, str] = _build_legacy_mapping()


# =============================================================================
# INTENT -> CONSOLIDATED AGENT MAPPING
# =============================================================================

# Maps the intent strings from intent_router.py to consolidated agents.
# This replaces the legacy INTENT_TO_AGENTS mapping for consolidated mode.
INTENT_TO_CONSOLIDATED: Dict[str, List[str]] = {
    # Simple / fast-path
    "greeting": ["aria"],
    "simple": ["pipeline_coach"],

    # Core workflow
    "pipeline": ["pipeline_coach", "calculator"],
    "historical": ["pipeline_coach"],
    "tasks": ["pipeline_coach"],
    "priorities": ["pipeline_coach"],
    "sla": ["pipeline_coach"],
    "reports": ["pipeline_coach"],
    "operations": ["pipeline_coach"],
    "schedule": ["pipeline_coach"],

    # Communication
    "calls": ["aria"],
    "email": ["email_intel"],
    "video": ["pipeline_coach"],  # Video meetings folded into pipeline ops
    "notifications": ["pipeline_coach"],

    # Finance
    "rates": ["calculator"],
    "profit": ["calculator"],
    "pricing": ["calculator"],
    "structuring": ["calculator"],
    "revenue": ["calculator"],

    # Documents
    "documents": ["doc_intel"],
    "closing": ["doc_intel", "pipeline_coach"],

    # Compliance & risk
    "compliance": ["compliance"],
    "qc": ["compliance"],
    "fraud": ["compliance"],
    "risk": ["compliance"],
    "turn_down": ["compliance"],

    # Leads & outreach
    "leads": ["avery"],
    "top_leads": ["avery"],
    "borrower": ["avery"],
    "pre_approval": ["avery"],
    "credit_repair": ["avery"],
    "down_payment": ["avery"],
    "onboarding": ["avery"],

    # Opportunity & market
    "customer": ["opportunity"],
    "market": ["opportunity"],
    "referral": ["opportunity"],
    "post_closing": ["opportunity"],
    "reviews": ["opportunity"],

    # Talent
    "coaching": ["talent_radar"],
    "recruiting": ["talent_radar"],
    "training": ["talent_radar"],
    "performance": ["talent_radar"],

    # Integrations & specialty lending
    "integrations": ["uw_copilot"],
    "billing": ["uw_copilot"],
    "va_loan": ["uw_copilot"],
    "fha_loan": ["uw_copilot"],
    "jumbo": ["uw_copilot"],
    "reverse_mortgage": ["uw_copilot"],
    "construction": ["uw_copilot"],
    "commercial": ["uw_copilot"],
    "secondary": ["calculator"],
    "investor": ["uw_copilot"],

    # Platform
    "system_health": ["uw_copilot"],
    "data_quality": ["uw_copilot"],
    "migration": ["uw_copilot"],

    # Content & marketing
    "content": ["email_intel"],
    "social_media": ["email_intel"],
    "campaign": ["email_intel"],

    # Partner management
    "title": ["doc_intel"],
    "appraisal": ["doc_intel"],
    "insurance": ["doc_intel"],
    "warehouse": ["pipeline_coach"],
    "shipping": ["pipeline_coach"],
    "servicing": ["opportunity"],

    # Compound & fallback
    "compound": ["pipeline_coach", "avery", "email_intel", "aria"],
    "general": ["pipeline_coach"],
}


# =============================================================================
# PUBLIC API
# =============================================================================

def get_consolidated_agent_config(agent_id: str) -> Optional[ConsolidatedAgent]:
    """
    Get the consolidated agent configuration by ID.

    Args:
        agent_id: One of the 10 consolidated agent IDs

    Returns:
        ConsolidatedAgent or None if not found
    """
    return CONSOLIDATED_AGENTS.get(agent_id)


def resolve_legacy_role(legacy_role: str) -> Optional[str]:
    """
    Map a legacy agent role to its consolidated agent ID.

    Args:
        legacy_role: Legacy role name (e.g., "ai_receptionist")

    Returns:
        Consolidated agent ID (e.g., "aria") or None if unmapped
    """
    return LEGACY_TO_CONSOLIDATED.get(legacy_role)


def get_tools_for_consolidated_agent(agent_id: str) -> List[str]:
    """
    Get the full list of tool names for a consolidated agent.

    Args:
        agent_id: Consolidated agent ID

    Returns:
        List of tool names (empty if agent not found)
    """
    agent = CONSOLIDATED_AGENTS.get(agent_id)
    if agent is None:
        return []
    return list(agent.tool_names)


def get_consolidated_agents_for_intent(intent: str) -> List[str]:
    """
    Get consolidated agent IDs for a given intent string.

    Args:
        intent: Intent string from intent_router.py

    Returns:
        List of consolidated agent IDs
    """
    return INTENT_TO_CONSOLIDATED.get(intent, INTENT_TO_CONSOLIDATED["general"])


def get_consolidated_tools_for_intent(intent: str) -> List[str]:
    """
    Get all tool names needed for an intent in consolidated mode.
    Merges tools from all consolidated agents assigned to the intent.

    Args:
        intent: Intent string from intent_router.py

    Returns:
        Deduplicated list of tool names
    """
    agent_ids = get_consolidated_agents_for_intent(intent)
    tools: Set[str] = set()
    for agent_id in agent_ids:
        tools.update(get_tools_for_consolidated_agent(agent_id))
    return sorted(tools)


def get_migration_report() -> Dict:
    """
    Generate a report showing the legacy-to-consolidated mapping.
    Useful for auditing and planning gradual migration.

    Returns:
        Dict with migration statistics and mappings
    """
    # Collect all legacy roles from tool_integration
    try:
        from .tool_integration import AGENT_CONFIGS as LEGACY_CONFIGS
        all_legacy_roles = set(LEGACY_CONFIGS.keys())
    except ImportError:
        all_legacy_roles = set()

    mapped_roles = set(LEGACY_TO_CONSOLIDATED.keys())
    unmapped_roles = all_legacy_roles - mapped_roles

    # Tool coverage analysis
    all_consolidated_tools: Set[str] = set()
    for agent in CONSOLIDATED_AGENTS.values():
        all_consolidated_tools.update(agent.tool_names)

    all_legacy_tools: Set[str] = set()
    try:
        from .tool_integration import AGENT_CONFIGS as LEGACY_CONFIGS
        for config in LEGACY_CONFIGS.values():
            all_legacy_tools.update(config.tool_names)
    except ImportError:
        pass

    tools_missing_from_consolidated = all_legacy_tools - all_consolidated_tools

    return {
        "consolidated_agent_count": len(CONSOLIDATED_AGENTS),
        "legacy_agent_count": len(all_legacy_roles),
        "mapped_legacy_roles": len(mapped_roles),
        "unmapped_legacy_roles": sorted(unmapped_roles),
        "total_consolidated_tools": len(all_consolidated_tools),
        "total_legacy_tools": len(all_legacy_tools),
        "tools_missing_from_consolidated": sorted(tools_missing_from_consolidated),
        "agents": {
            agent.id: {
                "name": agent.name,
                "legacy_roles_absorbed": sorted(agent.legacy_roles),
                "tool_count": len(agent.tool_names),
                "recommended_model": agent.recommended_model,
            }
            for agent in CONSOLIDATED_AGENTS.values()
        },
    }
