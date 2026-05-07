"""
Perennia AI - Tool Integration Layer
====================================
Connects agent tools to the AI orchestrator and LangChain workflow.
Provides tool binding, execution management, and result processing.
"""

from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import asyncio
import json
import os

from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, Field

from .tools import (
    tool_registry,
    ToolResult,
    ToolError,
    execute_tool,
    get_tools_for_agent,
    ALL_TOOLS,
)
from .tools.base import LoanStatus, LoanType

logger = logging.getLogger(__name__)


# =============================================================================
# AGENT ROLE DEFINITIONS
# =============================================================================

@dataclass
class AgentToolConfig:
    """Configuration for an agent's tool access.

    Attributes:
        recommended_model: Advisory model tier for this agent.
            "haiku" = fast/cheap model sufficient (tool-heavy, formatting tasks)
            "sonnet" = full model needed (complex reasoning, analysis, compliance)
            This is advisory metadata for future per-agent model routing.
    """
    role: str
    name: str
    description: str
    tool_names: List[str]
    max_concurrent_tools: int = 3
    tool_timeout_seconds: int = 30
    requires_approval_for: List[str] = field(default_factory=list)
    recommended_model: str = "sonnet"  # Default to Sonnet; override to "haiku" for simpler agents
    temperature: float = 0.3  # Default conservative; compliance=0.1, analytics=0.3, creative=0.7


AGENT_CONFIGS = {
    # =========================================================================
    # CRM Agents (8)
    # =========================================================================
    "pipeline_analyst": AgentToolConfig(
        role="pipeline_analyst",
        name="Pipeline Analyst",
        description="Analyzes loan pipeline metrics, trends, and performance",
        tool_names=[
            "get_pipeline_metrics",
            "get_loans_by_status",
            "get_loan_aging_report",
            "calculate_conversion_rates",
            "predict_closing_timeline",
            "get_bottleneck_analysis",
            "compare_to_benchmark",
            "get_lo_pipeline_breakdown",
            # Historical analytics
            "get_performance_by_period",
            "compare_periods",
            "get_data_availability",
            # Trend analysis
            "analyze_trends",
            # CRM write tools
            "update_lead_fields",
            "update_loan_fields",
            "create_note",
            "create_referral_partner",
        ],
        max_concurrent_tools=5,
        recommended_model="sonnet",  # Complex analytical reasoning
    ),
    "compliance_checker": AgentToolConfig(
        role="compliance_checker",
        name="Compliance Checker",
        description="Validates regulatory compliance for loans",
        tool_names=[
            "check_trid_compliance",
            "check_respa_compliance",
            "check_fair_lending",
            "get_state_requirements",
            "audit_loan_file",
            "get_disclosure_timeline",
            "check_tolerance_violations",
            "get_compliance_history",
            # Outbound contact compliance
            "validate_outbound_contact",
            "check_calling_window",
            "check_dnc_status",
            "check_tcpa_consent",
        ],
        requires_approval_for=["override_compliance_flag"],
        recommended_model="sonnet",  # Regulatory compliance needs precise reasoning
        temperature=0.1,
    ),
    "lead_nurturer": AgentToolConfig(
        role="lead_nurturer",
        name="Lead Nurturer",
        description="Manages lead engagement and conversion",
        tool_names=[
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
            # Outreach tools
            "find_clients_for_outreach",
            "send_bulk_sms_outreach",
            "send_mortgage_review_outreach",
            "send_calendar_invite_email",
            "send_bulk_email_outreach",
            # SMS tools
            "send_sms_message",
            "get_sms_conversation_history",
            "start_scheduling_sms",
        ],
        requires_approval_for=["send_email", "send_sms", "make_call"],
        recommended_model="sonnet",  # Lead recommendations need contextual analysis
    ),
    "document_tracker": AgentToolConfig(
        role="document_tracker",
        name="Document Tracker",
        description="Tracks and manages loan documentation",
        tool_names=[
            "get_missing_documents",
            "get_loan_conditions",
            "track_document_request",
            "send_document_reminder",
            "escalate_issue",
            "get_document_timeline",
            "check_document_expiration",
            "get_third_party_status",
            # Smart document tools
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
        ],
        requires_approval_for=["send_document_reminder"],
        recommended_model="haiku",  # Checklist/status lookups, tool-heavy
    ),
    "profitability_analyst": AgentToolConfig(
        role="profitability_analyst",
        name="Profitability Analyst",
        description="Analyzes loan and portfolio profitability",
        tool_names=[
            "calculate_loan_profitability",
            "analyze_margins_by_segment",
            "forecast_revenue",
            "compare_lo_profitability",
            "optimize_pricing",
            "get_cost_breakdown",
            "calculate_pull_through_impact",
            "get_profitability_trends",
        ],
        recommended_model="sonnet",  # Financial analysis needs deep reasoning
    ),
    "rate_advisor": AgentToolConfig(
        role="rate_advisor",
        name="Rate Advisor",
        description="Advises on rate locks and market conditions",
        tool_names=[
            "get_current_rates",
            "analyze_rate_trends",
            "calculate_lock_cost",
            "recommend_lock_strategy",
            "monitor_float_position",
            "get_extension_pricing",
            "compare_rate_scenarios",
            "get_market_events",
            # Home valuation tools
            "calculate_home_value",
            "get_appreciation_rates",
            "calculate_equity_position",
            "calculate_amortization",
            "get_maturity_date",
            "batch_update_valuations",
            "get_value_history",
            "compare_market_appreciation",
            # Refinance tools
            "score_refi_opportunity",
            "calculate_refi_savings",
            "get_refi_candidates",
            "analyze_breakeven",
            "compare_refi_scenarios",
            "get_refi_portfolio_summary",
            "recommend_refi_action",
            "batch_update_refi_scores",
        ],
        requires_approval_for=["lock_rate"],
        recommended_model="sonnet",  # Rate advisory needs analytical reasoning for lock/float decisions
    ),
    "team_coach": AgentToolConfig(
        role="team_coach",
        name="Team Coach",
        description="Provides coaching and performance insights",
        tool_names=[
            "get_lo_metrics",
            "compare_to_peers",
            "identify_training_needs",
            "generate_coaching_plan",
            "track_improvement",
            "get_best_practices",
            "get_performance_trends",
            "set_performance_goals",
            # Historical analytics
            "get_performance_by_period",
            "compare_periods",
            "get_data_availability",
            # Escalation tools
            "create_escalation",
            "evaluate_escalation",
            "resolve_escalation",
            "get_escalation_analytics",
            "get_escalation_status",
            "execute_warm_handoff",
        ],
        recommended_model="sonnet",  # Coaching advice requires nuanced analysis
    ),
    "customer_intelligence": AgentToolConfig(
        role="customer_intelligence",
        name="Customer Intelligence",
        description="Analyzes customer relationships and opportunities",
        tool_names=[
            "get_customer_360",
            "map_relationships",
            "calculate_ltv",
            "assess_churn_risk",
            "find_opportunities",
            "get_interaction_history",
            "get_referral_network",
            "get_market_comparison",
        ],
        recommended_model="haiku",  # Database-driven lookups, tool-heavy
    ),
    # =========================================================================
    # Communication Agents (4)
    # =========================================================================
    "voice_os": AgentToolConfig(
        role="voice_os",
        name="Voice OS",
        description="Manages phone calls, voicemail, transcription, and call analytics",
        tool_names=[
            "initiate_outbound_call",
            "drop_voicemail",
            "get_call_history",
            "analyze_call_sentiment",
            "schedule_callback",
            "get_power_dialer_queue",
            "transcribe_call",
            "get_call_metrics",
        ],
        requires_approval_for=["initiate_outbound_call"],
        recommended_model="haiku",  # Call routing is tool-driven
    ),
    "uvip": AgentToolConfig(
        role="uvip",
        name="UVIP (Video Platform)",
        description="Handles video meetings, recordings, and engagement analysis",
        tool_names=[
            "schedule_video_meeting",
            "get_meeting_recordings",
            "analyze_meeting",
            "send_async_video",
            "get_video_analytics",
            "extract_meeting_action_items",
            "generate_meeting_summary",
            "get_participant_insights",
        ],
        recommended_model="haiku",  # Video management is tool-driven
    ),
    "email_intelligence": AgentToolConfig(
        role="email_intelligence",
        name="Email Intelligence",
        description="Analyzes emails, detects intent, and generates contextual responses",
        tool_names=[
            "parse_email",
            "get_email_thread",
            "draft_email_response",
            "get_email_templates",
            "send_email",
            "categorize_email_attachments",
            "match_email_to_loan",
            "analyze_email_engagement",
            # Extended email tools
            "search_email_inbox",
            "find_contact_email",
            "find_contact_phone",
            "get_emails_needing_response",
            "analyze_tone",
            "get_thread_tone_trends",
            "compare_tone_to_baseline",
        ],
        requires_approval_for=["send_email"],
        recommended_model="sonnet",  # Email drafting/analysis needs quality
        temperature=0.5,
    ),
    "ai_receptionist": AgentToolConfig(
        role="ai_receptionist",
        name="AI Receptionist",
        description="Handles initial inquiries, qualifies leads, and routes to specialists",
        tool_names=[
            "get_greeting_script",
            "qualify_caller",
            "route_call",
            "create_callback_request",
            "get_lo_availability",
            "get_call_queue_status",
            "handle_inbound_call",
            "log_call_interaction",
        ],
        recommended_model="haiku",  # Routing/scripting is deterministic
    ),
    # =========================================================================
    # Operations Agents (4)
    # =========================================================================
    "smart_scheduler": AgentToolConfig(
        role="smart_scheduler",
        name="Smart Scheduler",
        description="Manages appointments, calendar optimization, and scheduling",
        tool_names=[
            "get_availability",
            "book_appointment",
            "reschedule_appointment",
            "cancel_appointment",
            "get_upcoming_appointments",
            "send_appointment_reminder",
            "sync_external_calendar",
            "optimize_schedule",
            # Extended scheduler tools
            "get_scheduler_metrics",
            "get_appointment_history",
            "get_best_booking_times",
            "get_no_show_analysis",
        ],
        recommended_model="haiku",  # Calendar CRUD is tool-driven
    ),
    "task_automation": AgentToolConfig(
        role="task_automation",
        name="Task Automation",
        description="Automates task creation, assignment, and workflow management",
        tool_names=[
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
        ],
        recommended_model="haiku",  # Task CRUD is deterministic
    ),
    "sla_tracker": AgentToolConfig(
        role="sla_tracker",
        name="SLA Tracker",
        description="Monitors SLA compliance, alerts, and breach prevention",
        tool_names=[
            "check_sla_status",
            "get_sla_dashboard",
            "get_sla_alerts",
            "calculate_stage_sla",
            "configure_sla_rules",
            "get_sla_report",
            "project_sla_breach",
            "escalate_sla_breach",
        ],
        recommended_model="haiku",  # SLA tracking is metric/deadline lookup
    ),
    "integrations": AgentToolConfig(
        role="integrations",
        name="Integrations Manager",
        description="Manages LOS, credit, AUS, and vendor integrations",
        tool_names=[
            "sync_los_data",
            "check_integration_status",
            "trigger_credit_pull",
            "submit_to_aus",
            "order_appraisal",
            "order_title",
            "get_pricing_engine_quote",
            "send_for_esign",
            # LOS integration tools
            "trigger_sync",
            "resolve_sync_conflict",
            "update_field_mapping",
            "get_field_mappings",
            "get_sync_status",
            "get_sync_health",
        ],
        requires_approval_for=["trigger_credit_pull", "submit_to_aus"],
        recommended_model="sonnet",  # Complex diagnostic reasoning, conflict resolution, migration planning
    ),
    # =========================================================================
    # Business Agents (4)
    # =========================================================================
    "reporting_engine": AgentToolConfig(
        role="reporting_engine",
        name="Reporting Engine",
        description="Generates reports, analytics, trend analysis, and data exports",
        tool_names=[
            "generate_pipeline_report",
            "generate_production_report",
            "generate_lo_performance_report",
            "get_report_templates",
            "schedule_report",
            "export_report",
            "get_dashboard_metrics",
            "create_custom_report",
            # Historical analytics
            "get_performance_by_period",
            "compare_periods",
            "get_data_availability",
            # Trend analysis & business intelligence
            "analyze_trends",
        ],
        recommended_model="sonnet",  # Complex analytical reasoning, anomaly detection, narrative generation
    ),
    "notification_center": AgentToolConfig(
        role="notification_center",
        name="Notification Center",
        description="Manages notifications, alerts, and communication preferences",
        tool_names=[
            "send_notification",
            "get_pending_notifications",
            "get_notification_templates",
            "schedule_notification",
            "get_delivery_status",
            "update_preferences",
            "get_preferences",
            "batch_send",
        ],
        requires_approval_for=["batch_send"],
        recommended_model="haiku",  # Notification CRUD is deterministic
    ),
    "subscription_manager": AgentToolConfig(
        role="subscription_manager",
        name="Subscription Manager",
        description="Handles subscriptions, billing, and usage tracking",
        tool_names=[
            "get_subscription_status",
            "get_plans",
            "change_plan",
            "get_billing_history",
            "update_payment_method",
            "get_usage_metrics",
            "manage_addons",
            "pause_subscription",
        ],
        requires_approval_for=["change_plan", "update_payment_method"],
        recommended_model="sonnet",  # Consultative retention reasoning, cancellation handling
    ),
    "onboarding_assistant": AgentToolConfig(
        role="onboarding_assistant",
        name="Onboarding Assistant",
        description="Guides new users through setup, training, and platform adoption",
        tool_names=[
            "get_onboarding_status",
            "get_checklist",
            "complete_step",
            "start_guided_tour",
            "get_training_resources",
            "get_setup_wizard",
            "request_support",
            "track_progress",
        ],
        recommended_model="haiku",  # Onboarding checklists are deterministic
    ),
    # =========================================================================
    # Cross-Agent Coordination
    # =========================================================================
    "ops_manager": AgentToolConfig(
        role="ops_manager",
        name="Operations Manager",
        description="Operations Manager — Handles escalations, SLA oversight, pipeline sweep, cross-agent coordination",
        tool_names=[
            "get_pipeline_metrics",
            "get_loan_aging_report",
            "get_bottleneck_analysis",
            "check_sla_status",
            "get_sla_dashboard",
            "escalate_sla_breach",
            "get_lo_pipeline_breakdown",
            "get_compliance_history",
        ],
        max_concurrent_tools=5,
        recommended_model="sonnet",
    ),
    # =========================================================================
    # Revenue & Production Agents (4)
    # =========================================================================
    "revenue_forecaster": AgentToolConfig(
        role="revenue_forecaster",
        name="Revenue Forecaster",
        description="Revenue projection, pull-through modeling, pipeline-to-close prediction",
        tool_names=[
            "forecast_revenue",
            "calculate_pull_through_impact",
            "get_pipeline_metrics",
            "get_profitability_trends",
            "predict_closing_timeline",
            "calculate_conversion_rates",
        ],
        recommended_model="sonnet",
    ),
    "pricing_strategist": AgentToolConfig(
        role="pricing_strategist",
        name="Pricing Strategist",
        description="Loan pricing optimization, margin analysis, competitive positioning",
        tool_names=[
            "optimize_pricing",
            "analyze_margins_by_segment",
            "get_pricing_engine_quote",
            "get_current_rates",
            "compare_rate_scenarios",
            "calculate_loan_profitability",
            "get_cost_breakdown",
            "get_market_events",
        ],
        recommended_model="sonnet",
    ),
    "closing_coordinator": AgentToolConfig(
        role="closing_coordinator",
        name="Closing Coordinator",
        description="End-to-end closing workflow: title, escrow, docs, funding coordination",
        tool_names=[
            "order_title",
            "get_third_party_status",
            "get_disclosure_timeline",
            "check_document_expiration",
            "get_missing_documents",
            "get_loan_conditions",
            "track_document_request",
            "send_document_reminder",
        ],
        recommended_model="haiku",
    ),
    "loan_structuring": AgentToolConfig(
        role="loan_structuring",
        name="Loan Structuring Advisor",
        description="Multi-scenario loan structuring, DTI optimization, product matching",
        tool_names=[
            "compare_rate_scenarios",
            "get_pricing_engine_quote",
            "calculate_loan_profitability",
            "get_current_rates",
            "check_trid_compliance",
            "get_state_requirements",
            "analyze_rate_trends",
            "get_market_events",
        ],
        recommended_model="sonnet",
    ),
    # =========================================================================
    # Borrower Experience Agents (5)
    # =========================================================================
    "borrower_concierge": AgentToolConfig(
        role="borrower_concierge",
        name="Borrower Concierge",
        description="Full borrower journey management, proactive updates, satisfaction tracking",
        tool_names=[
            "get_customer_360",
            "get_interaction_history",
            "get_loan_conditions",
            "get_missing_documents",
            "draft_message",
            "schedule_outreach",
            "get_upcoming_appointments",
            "send_notification",
            # Borrower application tools
            "get_application_state",
            "get_loan_status",
            "book_lo_meeting",
            "propose_alternate_window",
            "prompt_document_upload",
            "emit_crm_event",
            "recall_borrower_context",
        ],
        recommended_model="sonnet",
    ),
    "pre_approval_specialist": AgentToolConfig(
        role="pre_approval_specialist",
        name="Pre-Approval Specialist",
        description="Pre-approval workflow, letter generation, conditions management",
        tool_names=[
            "get_lead_details",
            "score_lead",
            "get_state_requirements",
            "check_fair_lending",
            "get_pricing_engine_quote",
            "get_current_rates",
            "draft_message",
            "create_task",
            # Document generation
            "generate_pre_approval_letter",
        ],
        recommended_model="sonnet",
    ),
    "credit_repair_advisor": AgentToolConfig(
        role="credit_repair_advisor",
        name="Credit Repair Advisor",
        description="Credit improvement strategies, dispute management, score optimization",
        tool_names=[
            "get_lead_details",
            "get_customer_360",
            "draft_message",
            "create_task",
            "schedule_outreach",
            "send_notification",
            "get_engagement_history",
            "suggest_followup",
        ],
        recommended_model="sonnet",
    ),
    "down_payment_advisor": AgentToolConfig(
        role="down_payment_advisor",
        name="Down Payment Advisor",
        description="Down payment assistance programs, gift funds, grant eligibility",
        tool_names=[
            "get_lead_details",
            "get_state_requirements",
            "get_pricing_engine_quote",
            "draft_message",
            "create_task",
            "get_customer_360",
            "schedule_outreach",
            "suggest_followup",
        ],
        recommended_model="sonnet",
    ),
    "post_closing_care": AgentToolConfig(
        role="post_closing_care",
        name="Post-Closing Care",
        description="Post-closing borrower care, referral generation, anniversary outreach",
        tool_names=[
            "get_customer_360",
            "get_referral_network",
            "find_opportunities",
            "draft_message",
            "schedule_outreach",
            "send_email",
            "get_interaction_history",
            "send_notification",
        ],
        recommended_model="haiku",
    ),
    # =========================================================================
    # Risk & Fraud Agents (4)
    # =========================================================================
    "fraud_detector": AgentToolConfig(
        role="fraud_detector",
        name="Fraud Detector",
        description="Wire fraud detection, social engineering alerts, suspicious activity monitoring",
        tool_names=[
            "parse_email",
            "get_email_thread",
            "match_email_to_loan",
            "get_customer_360",
            "get_interaction_history",
            "get_compliance_history",
            "send_notification",
            "escalate_issue",
        ],
        requires_approval_for=["escalate_issue", "send_notification"],
        recommended_model="sonnet",
        temperature=0.1,
    ),
    "risk_assessor": AgentToolConfig(
        role="risk_assessor",
        name="Risk Assessor",
        description="Loan risk assessment, default probability, layered risk analysis",
        tool_names=[
            "get_pipeline_metrics",
            "audit_loan_file",
            "check_fair_lending",
            "get_loan_aging_report",
            "calculate_loan_profitability",
            "get_compliance_history",
            "check_tolerance_violations",
            "get_bottleneck_analysis",
        ],
        requires_approval_for=["audit_loan_file"],
        recommended_model="sonnet",
        temperature=0.1,
    ),
    "quality_control": AgentToolConfig(
        role="quality_control",
        name="Quality Control",
        description="Pre/post-close QC, buyback prevention, audit preparation",
        tool_names=[
            "audit_loan_file",
            "check_trid_compliance",
            "check_respa_compliance",
            "check_fair_lending",
            "get_missing_documents",
            "get_loan_conditions",
            "get_compliance_history",
            "check_tolerance_violations",
        ],
        recommended_model="sonnet",
        temperature=0.1,
    ),
    "turn_down_specialist": AgentToolConfig(
        role="turn_down_specialist",
        name="Turn Down Specialist",
        description="Adverse action handling, declination scripts, alternative referrals",
        tool_names=[
            "get_lead_details",
            "get_customer_360",
            "get_state_requirements",
            "draft_message",
            "send_email",
            "create_task",
            "get_engagement_history",
            "send_notification",
        ],
        requires_approval_for=["send_email", "send_notification"],
        recommended_model="sonnet",
    ),
    # =========================================================================
    # Marketing & Content Agents (5)
    # =========================================================================
    "content_creator": AgentToolConfig(
        role="content_creator",
        name="Content Creator",
        description="Social media posts, blog content, market commentary, drip campaign copy",
        tool_names=[
            "get_market_events",
            "analyze_rate_trends",
            "get_current_rates",
            "draft_message",
            "get_email_templates",
            "send_email",
            "get_report_templates",
            "schedule_notification",
        ],
        recommended_model="sonnet",
        temperature=0.7,
    ),
    "social_media_manager": AgentToolConfig(
        role="social_media_manager",
        name="Social Media Manager",
        description="Multi-platform social posting, engagement tracking, brand management",
        tool_names=[
            "draft_message",
            "get_market_events",
            "get_current_rates",
            "get_report_templates",
            "schedule_notification",
            "get_email_templates",
            "analyze_rate_trends",
            "get_dashboard_metrics",
        ],
        recommended_model="sonnet",
        temperature=0.7,
    ),
    "market_analyst": AgentToolConfig(
        role="market_analyst",
        name="Market Analyst",
        description="Real estate market trends, local market intelligence, rate environment analysis",
        tool_names=[
            "get_market_events",
            "analyze_rate_trends",
            "get_current_rates",
            "get_market_comparison",
            "compare_rate_scenarios",
            "get_profitability_trends",
            "get_data_availability",
            "compare_periods",
        ],
        recommended_model="sonnet",
    ),
    "campaign_manager": AgentToolConfig(
        role="campaign_manager",
        name="Campaign Manager",
        description="Multi-channel campaign orchestration, conversion tracking",
        tool_names=[
            "batch_send",
            "get_email_templates",
            "schedule_notification",
            "get_delivery_status",
            "get_dashboard_metrics",
            "calculate_conversion_rates",
            "draft_message",
            "send_email",
        ],
        requires_approval_for=["batch_send"],
        recommended_model="sonnet",
    ),
    "review_manager": AgentToolConfig(
        role="review_manager",
        name="Review & Reputation Manager",
        description="Online review solicitation, response drafting, reputation management",
        tool_names=[
            "get_customer_360",
            "get_interaction_history",
            "draft_message",
            "send_email",
            "send_notification",
            "schedule_outreach",
            "find_opportunities",
            "get_referral_network",
        ],
        recommended_model="haiku",
    ),
    # =========================================================================
    # HR & Workforce Agents (3)
    # =========================================================================
    "recruiter": AgentToolConfig(
        role="recruiter",
        name="LO Recruiter",
        description="LO recruiting, compensation benchmarking, candidate pipeline tracking",
        tool_names=[
            "get_lo_metrics",
            "compare_to_peers",
            "get_performance_trends",
            "get_dashboard_metrics",
            "create_task",
            "draft_message",
            "send_email",
            "schedule_notification",
        ],
        recommended_model="sonnet",
    ),
    "training_specialist": AgentToolConfig(
        role="training_specialist",
        name="Training Specialist",
        description="LO training programs, certification tracking, skill gap assessment",
        tool_names=[
            "identify_training_needs",
            "generate_coaching_plan",
            "get_best_practices",
            "track_improvement",
            "get_training_resources",
            "get_lo_metrics",
            "create_task",
            "send_notification",
        ],
        recommended_model="haiku",
    ),
    "performance_manager": AgentToolConfig(
        role="performance_manager",
        name="Performance Manager",
        description="KPI tracking, goal setting, incentive calculations, team rankings",
        tool_names=[
            "get_lo_metrics",
            "compare_to_peers",
            "set_performance_goals",
            "track_improvement",
            "get_performance_trends",
            "get_performance_by_period",
            "compare_periods",
            "generate_coaching_plan",
        ],
        recommended_model="sonnet",
    ),
    # =========================================================================
    # Partner & Referral Agents (4)
    # =========================================================================
    "referral_partner_manager": AgentToolConfig(
        role="referral_partner_manager",
        name="Referral Partner Manager",
        description="Realtor/builder/CPA relationships, co-marketing, referral tracking",
        tool_names=[
            "get_referral_network",
            "find_opportunities",
            "get_customer_360",
            "map_relationships",
            "calculate_ltv",
            "draft_message",
            "send_email",
            "schedule_outreach",
        ],
        recommended_model="sonnet",
    ),
    "title_vendor_manager": AgentToolConfig(
        role="title_vendor_manager",
        name="Title & Vendor Manager",
        description="Title company coordination, fee shopping, turnaround tracking",
        tool_names=[
            "order_title",
            "get_third_party_status",
            "get_cost_breakdown",
            "create_task",
            "send_notification",
            "track_document_request",
            "get_document_timeline",
            "escalate_issue",
        ],
        recommended_model="haiku",
    ),
    "appraiser_coordinator": AgentToolConfig(
        role="appraiser_coordinator",
        name="Appraiser Coordinator",
        description="Appraisal ordering, rush requests, rebuttal management",
        tool_names=[
            "order_appraisal",
            "get_third_party_status",
            "track_document_request",
            "get_document_timeline",
            "escalate_issue",
            "create_task",
            "send_notification",
            "get_missing_documents",
        ],
        recommended_model="haiku",
    ),
    "insurance_coordinator": AgentToolConfig(
        role="insurance_coordinator",
        name="Insurance Coordinator",
        description="Homeowner's insurance tracking, hazard insurance, flood determination",
        tool_names=[
            "get_third_party_status",
            "track_document_request",
            "get_document_timeline",
            "get_missing_documents",
            "send_document_reminder",
            "create_task",
            "send_notification",
            "escalate_issue",
        ],
        recommended_model="haiku",
    ),
    # =========================================================================
    # Expanded Operations Agents (5)
    # =========================================================================
    "warehouse_manager": AgentToolConfig(
        role="warehouse_manager",
        name="Warehouse Line Manager",
        description="Warehouse line management, capacity tracking, delivery optimization",
        tool_names=[
            "get_pipeline_metrics",
            "get_loans_by_status",
            "predict_closing_timeline",
            "get_bottleneck_analysis",
            "get_loan_aging_report",
            "get_dashboard_metrics",
            "create_task",
            "send_notification",
        ],
        recommended_model="sonnet",
    ),
    "shipping_coordinator": AgentToolConfig(
        role="shipping_coordinator",
        name="Shipping Coordinator",
        description="Loan shipping, investor delivery, purchase advice tracking",
        tool_names=[
            "get_loans_by_status",
            "get_document_timeline",
            "get_third_party_status",
            "track_document_request",
            "create_task",
            "get_missing_documents",
            "send_notification",
            "get_loan_aging_report",
        ],
        recommended_model="haiku",
    ),
    "secondary_market": AgentToolConfig(
        role="secondary_market",
        name="Secondary Market Analyst",
        description="Loan sale execution, pricing, lock management, hedge tracking",
        tool_names=[
            "get_current_rates",
            "analyze_rate_trends",
            "calculate_lock_cost",
            "recommend_lock_strategy",
            "monitor_float_position",
            "get_extension_pricing",
            "get_market_events",
            "forecast_revenue",
        ],
        recommended_model="sonnet",
    ),
    "servicing_transfer": AgentToolConfig(
        role="servicing_transfer",
        name="Servicing Transfer Coordinator",
        description="Post-closing servicing setup, goodbye letters, transfer coordination",
        tool_names=[
            "get_customer_360",
            "draft_message",
            "send_email",
            "create_task",
            "get_interaction_history",
            "track_document_request",
            "send_notification",
            "get_document_timeline",
        ],
        recommended_model="haiku",
    ),
    "investor_relations": AgentToolConfig(
        role="investor_relations",
        name="Investor Relations",
        description="Investor requirements, overlay management, product eligibility",
        tool_names=[
            "get_state_requirements",
            "audit_loan_file",
            "get_pricing_engine_quote",
            "get_current_rates",
            "get_cost_breakdown",
            "check_tolerance_violations",
            "get_compliance_history",
            "get_report_templates",
        ],
        recommended_model="sonnet",
    ),
    # =========================================================================
    # Technology & Platform Agents (3)
    # =========================================================================
    "system_health_monitor": AgentToolConfig(
        role="system_health_monitor",
        name="System Health Monitor",
        description="API health, performance metrics, error rate tracking, uptime monitoring",
        tool_names=[
            "check_integration_status",
            "get_dashboard_metrics",
            "get_usage_metrics",
            "get_report_templates",
            "send_notification",
            "create_task",
            "get_delivery_status",
            "schedule_report",
        ],
        recommended_model="haiku",
    ),
    "data_quality_manager": AgentToolConfig(
        role="data_quality_manager",
        name="Data Quality Manager",
        description="Data integrity, duplicate detection, field completeness auditing",
        tool_names=[
            "get_pipeline_metrics",
            "get_dashboard_metrics",
            "get_lead_details",
            "audit_loan_file",
            "create_task",
            "get_report_templates",
            "export_report",
            "send_notification",
        ],
        recommended_model="haiku",
    ),
    "migration_assistant": AgentToolConfig(
        role="migration_assistant",
        name="Migration Assistant",
        description="System migration help, data import/export, LOS transition support",
        tool_names=[
            "sync_los_data",
            "check_integration_status",
            "export_report",
            "get_report_templates",
            "create_task",
            "send_notification",
            "get_dashboard_metrics",
            "get_usage_metrics",
        ],
        recommended_model="sonnet",
    ),
    # =========================================================================
    # Specialty Lending Agents (6)
    # =========================================================================
    "va_loan_specialist": AgentToolConfig(
        role="va_loan_specialist",
        name="VA Loan Specialist",
        description="VA-specific: COE, residual income, VA appraisal, funding fee calculations",
        tool_names=[
            "get_state_requirements",
            "get_pricing_engine_quote",
            "get_current_rates",
            "check_trid_compliance",
            "audit_loan_file",
            "get_missing_documents",
            "draft_message",
            "create_task",
        ],
        recommended_model="sonnet",
    ),
    "fha_loan_specialist": AgentToolConfig(
        role="fha_loan_specialist",
        name="FHA Loan Specialist",
        description="FHA-specific: MI premiums, case numbers, UFMIP, hand-off protocol",
        tool_names=[
            "get_state_requirements",
            "get_pricing_engine_quote",
            "get_current_rates",
            "check_trid_compliance",
            "audit_loan_file",
            "get_missing_documents",
            "draft_message",
            "create_task",
        ],
        recommended_model="sonnet",
    ),
    "jumbo_specialist": AgentToolConfig(
        role="jumbo_specialist",
        name="Jumbo & Non-Agency Specialist",
        description="Non-agency: reserve requirements, asset documentation, bank statement programs",
        tool_names=[
            "get_pricing_engine_quote",
            "get_current_rates",
            "compare_rate_scenarios",
            "audit_loan_file",
            "calculate_loan_profitability",
            "get_missing_documents",
            "get_state_requirements",
            "draft_message",
        ],
        recommended_model="sonnet",
    ),
    "reverse_mortgage_advisor": AgentToolConfig(
        role="reverse_mortgage_advisor",
        name="Reverse Mortgage Advisor",
        description="HECM counseling, principal limit factors, disbursement options",
        tool_names=[
            "get_customer_360",
            "get_state_requirements",
            "get_pricing_engine_quote",
            "draft_message",
            "create_task",
            "send_email",
            "schedule_outreach",
            "get_compliance_history",
        ],
        recommended_model="sonnet",
    ),
    "construction_loan_advisor": AgentToolConfig(
        role="construction_loan_advisor",
        name="Construction Loan Advisor",
        description="Draw schedules, builder approval, lot loans, spec lending workflows",
        tool_names=[
            "get_pricing_engine_quote",
            "get_current_rates",
            "get_state_requirements",
            "create_task",
            "track_document_request",
            "get_missing_documents",
            "draft_message",
            "send_notification",
        ],
        recommended_model="sonnet",
    ),
    "commercial_bridge": AgentToolConfig(
        role="commercial_bridge",
        name="Commercial & Bridge Lending",
        description="Commercial/bridge lending: DSCR, NOI analysis, cap rate evaluation",
        tool_names=[
            "calculate_loan_profitability",
            "get_pricing_engine_quote",
            "get_current_rates",
            "compare_rate_scenarios",
            "audit_loan_file",
            "get_state_requirements",
            "draft_message",
            "create_task",
        ],
        recommended_model="sonnet",
    ),
}


# =============================================================================
# TOOL EXECUTOR
# =============================================================================

class ToolExecutionResult(BaseModel):
    """Result from tool execution."""
    tool_name: str
    success: bool
    data: Any = None
    message: str = ""
    error: Optional[str] = None
    execution_time_ms: int = 0
    requires_approval: bool = False
    approval_id: Optional[str] = None


class AgentToolExecutor:
    """
    Manages tool execution for agents.
    Handles concurrency, timeouts, and approval workflows.
    """

    def __init__(self, agent_role: str):
        self.agent_role = agent_role
        self.config = AGENT_CONFIGS.get(agent_role)
        if not self.config:
            raise ValueError(f"Unknown agent role: {agent_role}")

        self._execution_history: List[Dict] = []
        self._pending_approvals: Dict[str, Dict] = {}

    def get_available_tools(self) -> List[str]:
        """Get list of tools available to this agent."""
        return self.config.tool_names.copy()

    def get_langchain_tools(self) -> List[BaseTool]:
        """Get LangChain-compatible tools for this agent."""
        return tool_registry.get_langchain_tools(self.agent_role)

    async def execute(
        self,
        tool_name: str,
        params: Dict[str, Any],
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        pre_approved: bool = False,
    ) -> ToolExecutionResult:
        """
        Execute a tool with given parameters.

        Args:
            tool_name: Name of the tool to execute
            params: Parameters to pass to the tool
            user_id: User executing the tool (for audit)
            user_role: Role of the user (only 'platform_admin' can set pre_approved)
            pre_approved: Skip approval check — ONLY honored for platform_admin users

        Returns:
            ToolExecutionResult with data or error
        """
        start_time = datetime.now(timezone.utc)

        # Validate tool is available to this agent
        if tool_name not in self.config.tool_names:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool {tool_name} not available to {self.agent_role}",
            )

        # Only platform admins can bypass approval
        can_skip_approval = pre_approved and user_role == "platform_admin"

        # Check if approval required
        if not can_skip_approval and tool_name in self.config.requires_approval_for:
            approval_id = f"approval_{tool_name}_{datetime.now(timezone.utc).timestamp()}"
            self._pending_approvals[approval_id] = {
                "tool_name": tool_name,
                "params": params,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc),
            }
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                message=f"Tool {tool_name} requires approval",
                requires_approval=True,
                approval_id=approval_id,
            )

        # Execute the tool
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(execute_tool, tool_name, **params),
                timeout=self.config.tool_timeout_seconds
            )

            execution_time = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            if isinstance(result, ToolResult):
                execution_result = ToolExecutionResult(
                    tool_name=tool_name,
                    success=result.status.value == "success",
                    data=result.data,
                    message=result.message or "",
                    error=result.errors[0] if result.errors else None,
                    execution_time_ms=execution_time,
                )
            else:
                execution_result = ToolExecutionResult(
                    tool_name=tool_name,
                    success=True,
                    data=result,
                    execution_time_ms=execution_time,
                )

            # Record execution
            self._execution_history.append({
                "tool_name": tool_name,
                "params": params,
                "success": execution_result.success,
                "execution_time_ms": execution_time,
                "timestamp": start_time,
            })

            return execution_result

        except asyncio.TimeoutError:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool execution timed out after {self.config.tool_timeout_seconds}s",
            )
        except Exception as e:
            logger.exception(f"Tool {tool_name} failed")
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=str(e),
            )

    async def execute_many(
        self,
        tool_calls: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
    ) -> List[ToolExecutionResult]:
        """
        Execute multiple tools, respecting concurrency limits.

        Args:
            tool_calls: List of {tool_name, params} dicts
            user_id: User executing the tools
            user_role: Role of the user for approval checks

        Returns:
            List of ToolExecutionResults in same order
        """
        results = []

        # Process in batches based on max_concurrent
        for i in range(0, len(tool_calls), self.config.max_concurrent_tools):
            batch = tool_calls[i:i + self.config.max_concurrent_tools]

            batch_tasks = [
                self.execute(
                    call["tool_name"],
                    call.get("params", {}),
                    user_id=user_id,
                    user_role=user_role,
                )
                for call in batch
            ]

            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    results.append(ToolExecutionResult(
                        tool_name=batch[j]["tool_name"],
                        success=False,
                        error=str(result),
                    ))
                else:
                    results.append(result)

        return results

    def approve(self, approval_id: str, approved_by: str) -> Optional[Dict]:
        """Approve a pending tool execution."""
        if approval_id not in self._pending_approvals:
            return None

        approval = self._pending_approvals.pop(approval_id)
        approval["approved_by"] = approved_by
        approval["approved_at"] = datetime.now(timezone.utc)
        return approval

    def reject(self, approval_id: str, rejected_by: str, reason: str) -> Optional[Dict]:
        """Reject a pending tool execution."""
        if approval_id not in self._pending_approvals:
            return None

        approval = self._pending_approvals.pop(approval_id)
        approval["rejected_by"] = rejected_by
        approval["rejected_at"] = datetime.now(timezone.utc)
        approval["rejection_reason"] = reason
        return approval

    def get_pending_approvals(self) -> List[Dict]:
        """Get all pending approvals for this executor."""
        return list(self._pending_approvals.values())

    def get_execution_stats(self) -> Dict:
        """Get execution statistics."""
        if not self._execution_history:
            return {"total_executions": 0}

        total = len(self._execution_history)
        successes = sum(1 for e in self._execution_history if e["success"])
        avg_time = sum(e["execution_time_ms"] for e in self._execution_history) / total

        # Tool usage counts
        tool_counts = {}
        for e in self._execution_history:
            name = e["tool_name"]
            tool_counts[name] = tool_counts.get(name, 0) + 1

        return {
            "total_executions": total,
            "success_count": successes,
            "failure_count": total - successes,
            "success_rate": round(successes / total * 100, 1),
            "avg_execution_time_ms": round(avg_time, 1),
            "tool_usage": tool_counts,
        }


# =============================================================================
# TOOL BINDING FOR LANGGRAPH
# =============================================================================

def create_tool_node(agent_role: str):
    """
    Create a LangGraph tool node for an agent.

    Usage in LangGraph workflow:
        from backend.agents.tool_integration import create_tool_node

        tool_node = create_tool_node("pipeline_analyst")
        workflow.add_node("tools", tool_node)
    """
    executor = AgentToolExecutor(agent_role)

    async def tool_node(state: Dict) -> Dict:
        """Process tool calls from the agent."""
        messages = state.get("messages", [])

        # Get the last message with tool calls
        last_message = messages[-1] if messages else None
        if not last_message or not hasattr(last_message, "tool_calls"):
            return state

        tool_calls = last_message.tool_calls
        if not tool_calls:
            return state

        # Execute each tool call
        tool_messages = []
        for tool_call in tool_calls:
            result = await executor.execute(
                tool_name=tool_call["name"],
                params=tool_call.get("args", {}),
                user_id=state.get("user_id"),
            )

            # Format result as ToolMessage
            content = json.dumps(result.data, default=str) if result.success else result.error
            tool_messages.append(
                ToolMessage(
                    content=content,
                    tool_call_id=tool_call["id"],
                    name=tool_call["name"],
                )
            )

        return {
            **state,
            "messages": messages + tool_messages,
            "tool_results": [msg.content for msg in tool_messages],
        }

    return tool_node


def get_tool_descriptions(agent_role: str) -> str:
    """
    Get formatted tool descriptions for agent prompts.

    Returns a string suitable for including in system prompts.
    """
    config = AGENT_CONFIGS.get(agent_role)
    if not config:
        return ""

    lines = [f"You have access to the following tools:\n"]

    for tool_name in config.tool_names:
        defn = tool_registry.get(tool_name)
        if defn:
            lines.append(f"- **{tool_name}**: {defn.description}")
            if defn.risk_level in ("HIGH", "CRITICAL"):
                lines.append(f"  Warning: This tool requires approval before execution.")

    return "\n".join(lines)


def bind_tools_to_model(model, agent_role: str):
    """
    Bind tools to a LangChain model for function calling.

    Usage:
        from langchain_anthropic import ChatAnthropic
        from backend.agents.tool_integration import bind_tools_to_model

        model = ChatAnthropic(model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"))
        model_with_tools = bind_tools_to_model(model, "pipeline_analyst")
    """
    executor = AgentToolExecutor(agent_role)
    tools = executor.get_langchain_tools()
    return model.bind_tools(tools)


# =============================================================================
# TOOL RESULT FORMATTERS
# =============================================================================

def format_tool_result_for_agent(result: ToolExecutionResult) -> str:
    """Format tool result as a natural language response for agents."""
    if not result.success:
        if result.requires_approval:
            return f"The action '{result.tool_name}' requires approval before it can be executed."
        return f"Error executing {result.tool_name}: {result.error}"

    if isinstance(result.data, dict):
        # Try to use the message if available
        if "message" in result.data:
            return f"{result.data['message']}"

        # Format key metrics
        lines = [f"{result.tool_name} completed:"]
        for key, value in result.data.items():
            if isinstance(value, (int, float, str)) and not key.startswith("_"):
                lines.append(f"  - {key}: {value}")
        return "\n".join(lines[:10])  # Limit output

    return f"{result.message or result.tool_name + ' completed'}"


def format_tool_results_summary(results: List[ToolExecutionResult]) -> str:
    """Format multiple tool results as a summary."""
    if not results:
        return "No tools were executed."

    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    pending = [r for r in results if r.requires_approval]

    lines = []

    if successes:
        lines.append(f"{len(successes)} tool(s) executed successfully")
    if failures:
        lines.append(f"{len(failures)} tool(s) failed")
    if pending:
        lines.append(f"{len(pending)} tool(s) awaiting approval")

    # Add details for each
    for result in results:
        lines.append(f"\n{result.tool_name}:")
        if result.success and result.message:
            lines.append(f"  {result.message}")
        elif result.error:
            lines.append(f"  Error: {result.error}")
        elif result.requires_approval:
            lines.append(f"  Requires approval (ID: {result.approval_id})")

    return "\n".join(lines)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_all_agent_tools() -> Dict[str, List[str]]:
    """Get all tools organized by agent role."""
    return {role: config.tool_names for role, config in AGENT_CONFIGS.items()}


def get_tool_risk_levels() -> Dict[str, str]:
    """Get risk levels for all registered tools."""
    levels = {}
    for tool_name in get_all_tool_names():
        defn = tool_registry.get(tool_name)
        if defn:
            levels[tool_name] = defn.risk_level
    return levels


def get_all_tool_names() -> List[str]:
    """Get flat list of all tool names."""
    names = []
    for config in AGENT_CONFIGS.values():
        names.extend(config.tool_names)
    return list(set(names))  # Remove duplicates


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Config
    "AgentToolConfig",
    "AGENT_CONFIGS",

    # Executor
    "ToolExecutionResult",
    "AgentToolExecutor",

    # LangGraph integration
    "create_tool_node",
    "get_tool_descriptions",
    "bind_tools_to_model",

    # Formatters
    "format_tool_result_for_agent",
    "format_tool_results_summary",

    # Utilities
    "get_all_agent_tools",
    "get_tool_risk_levels",
    "get_all_tool_names",
]
