"""
Perennia AI - Agent Tools Package
=================================
Comprehensive tooling for 20 specialized mortgage CRM agents.

Usage:
    from backend.agents.tools import tool_registry, get_tools_for_agent

    # Get all tools for an agent
    pipeline_tools = get_tools_for_agent("pipeline_analyst")

    # Execute a specific tool
    from backend.agents.tools import execute_tool
    result = execute_tool("get_pipeline_metrics", lo_id="LO123")

    # Get LangChain-compatible tools
    langchain_tools = tool_registry.get_langchain_tools("pipeline_analyst")
"""

# Import base infrastructure
from .base import (
    # Database
    get_db,
    execute_query,
    execute_single,

    # Tenant Isolation
    set_tenant_context,
    get_tenant_context,
    clear_tenant_context,

    # Types
    ToolStatus,
    ToolResult,
    ToolError,
    ToolDefinition,

    # Registry
    ToolRegistry,
    tool_registry,

    # Decorator
    mortgage_tool,

    # Helpers
    get_tools_for_agent,
    execute_tool,
    format_currency,
    format_percentage,
    format_date,
    days_between,
    calculate_percentage_change,

    # Enums
    LoanStatus,
    LoanType,
    PropertyType,
    OccupancyType,
    SLA_TARGETS,
    DOCUMENT_CATEGORIES,
)

# =============================================================================
# Import all tool modules to register tools
# =============================================================================

# CRM Tools (8 agents, 64 tools)
from . import pipeline
from . import compliance
from . import leads
from . import documents
from . import profitability
from . import rates
from . import coaching
from . import customer

# Communication Tools (4 agents, 32 tools)
from . import voice
from . import video
from . import email_intel
from . import receptionist

# Operations Tools (4 agents, 32 tools)
from . import scheduler
from . import tasks
from . import sla
from . import integrations

# Business Tools (4 agents, 32 tools)
from . import reporting
from . import notifications
from . import subscription
from . import onboarding

# Valuation & Refinance Tools (2 agents, 16 tools)
from . import home_valuation
from . import refinance

# Analytics Tools
from . import historical
from . import trend_analysis

# Aria Voice Tools (SMS, Documents, Outreach)
from . import sms_tools
from . import document_tools
from . import outreach_tools

# Smart Docs Bridge Tools
from . import smart_documents


# =============================================================================
# Agent Configuration
# =============================================================================

# Agent role to module mapping (20 agents)
AGENT_MODULES = {
    # CRM Agents
    "pipeline_analyst": pipeline,
    "compliance_checker": compliance,
    "lead_nurturer": leads,
    "document_tracker": documents,
    "profitability_analyst": profitability,
    "rate_advisor": rates,
    "team_coach": coaching,
    "customer_intelligence": customer,
    # Communication Agents
    "voice_os": voice,
    "uvip": video,
    "email_intelligence": email_intel,
    "ai_receptionist": receptionist,
    # Operations Agents
    "smart_scheduler": scheduler,
    "task_automation": tasks,
    "sla_tracker": sla,
    "integrations": integrations,
    # Valuation & Refinance Agents
    "home_valuation": home_valuation,
    "refinance_advisor": refinance,
    # Business Agents
    "reporting_engine": reporting,
    "notification_center": notifications,
    "subscription_manager": subscription,
    "onboarding_assistant": onboarding,
}


# =============================================================================
# Tool Lists by Category
# =============================================================================

# CRM Tools
PIPELINE_TOOLS = [
    "get_pipeline_metrics",
    "get_loans_by_status",
    "get_loan_aging_report",
    "calculate_conversion_rates",
    "predict_closing_timeline",
    "get_bottleneck_analysis",
    "compare_to_benchmark",
    "get_lo_pipeline_breakdown",
]

COMPLIANCE_TOOLS = [
    "check_trid_compliance",
    "check_respa_compliance",
    "check_fair_lending",
    "get_state_requirements",
    "audit_loan_file",
    "get_disclosure_timeline",
    "check_tolerance_violations",
    "get_compliance_history",
]

LEAD_TOOLS = [
    "get_lead_details",
    "get_engagement_history",
    "score_lead",
    "suggest_followup",
    "draft_message",
    "schedule_outreach",
    "get_similar_converted_leads",
    "get_optimal_contact_time",
]

DOCUMENT_TOOLS = [
    "get_missing_documents",
    "get_loan_conditions",
    "track_document_request",
    "send_document_reminder",
    "escalate_issue",
    "get_document_timeline",
    "check_document_expiration",
    "get_third_party_status",
]

PROFITABILITY_TOOLS = [
    "calculate_loan_profitability",
    "analyze_margins_by_segment",
    "forecast_revenue",
    "compare_lo_profitability",
    "optimize_pricing",
    "get_cost_breakdown",
    "calculate_pull_through_impact",
    "get_profitability_trends",
]

RATE_TOOLS = [
    "get_current_rates",
    "analyze_rate_trends",
    "calculate_lock_cost",
    "recommend_lock_strategy",
    "monitor_float_position",
    "get_extension_pricing",
    "compare_rate_scenarios",
    "get_market_events",
]

COACHING_TOOLS = [
    "get_lo_metrics",
    "compare_to_peers",
    "identify_training_needs",
    "generate_coaching_plan",
    "track_improvement",
    "get_best_practices",
    "get_performance_trends",
    "set_performance_goals",
]

CUSTOMER_TOOLS = [
    "get_customer_360",
    "map_relationships",
    "calculate_ltv",
    "assess_churn_risk",
    "find_opportunities",
    "get_interaction_history",
    "get_referral_network",
    "get_market_comparison",
]

# Communication Tools
VOICE_TOOLS = [
    "initiate_outbound_call",
    "drop_voicemail",
    "get_call_history",
    "analyze_call_sentiment",
    "schedule_callback",
    "get_power_dialer_queue",
    "transcribe_call",
    "get_call_metrics",
]

VIDEO_TOOLS = [
    "schedule_video_meeting",
    "get_meeting_recordings",
    "analyze_meeting",
    "send_async_video",
    "get_video_analytics",
    "extract_meeting_action_items",
    "generate_meeting_summary",
    "get_participant_insights",
]

EMAIL_INTEL_TOOLS = [
    "parse_email",
    "get_email_thread",
    "draft_email_response",
    "get_email_templates",
    "send_email",
    "categorize_email_attachments",
    "match_email_to_loan",
    "analyze_email_engagement",
]

RECEPTIONIST_TOOLS = [
    "get_greeting_script",
    "qualify_caller",
    "route_call",
    "create_callback_request",
    "get_lo_availability",
    "get_call_queue_status",
    "handle_inbound_call",
    "log_call_interaction",
]

# Operations Tools
SCHEDULER_TOOLS = [
    "get_availability",
    "book_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "get_upcoming_appointments",
    "send_appointment_reminder",
    "sync_external_calendar",
    "optimize_schedule",
]

TASK_TOOLS = [
    "create_task",
    "get_task_queue",
    "update_task_status",
    "assign_task",
    "get_task_templates",
    "bulk_update_tasks",
    "execute_workflow",
    "get_workflow_status",
]

SLA_TOOLS = [
    "check_sla_status",
    "get_sla_dashboard",
    "get_sla_alerts",
    "calculate_stage_sla",
    "configure_sla_rules",
    "get_sla_report",
    "project_sla_breach",
    "escalate_sla_breach",
]

INTEGRATION_TOOLS = [
    "sync_los_data",
    "check_integration_status",
    "trigger_credit_pull",
    "submit_to_aus",
    "order_appraisal",
    "order_title",
    "get_pricing_engine_quote",
    "send_for_esign",
]

# Business Tools
REPORTING_TOOLS = [
    "generate_pipeline_report",
    "generate_production_report",
    "generate_lo_performance_report",
    "get_report_templates",
    "schedule_report",
    "export_report",
    "get_dashboard_metrics",
    "create_custom_report",
    "analyze_trends",
]

NOTIFICATION_TOOLS = [
    "send_notification",
    "get_pending_notifications",
    "get_notification_templates",
    "schedule_notification",
    "get_delivery_status",
    "update_preferences",
    "get_preferences",
    "batch_send",
]

SUBSCRIPTION_TOOLS = [
    "get_subscription_status",
    "get_plans",
    "change_plan",
    "get_billing_history",
    "update_payment_method",
    "get_usage_metrics",
    "manage_addons",
    "pause_subscription",
]

ONBOARDING_TOOLS = [
    "get_onboarding_status",
    "get_checklist",
    "complete_step",
    "start_guided_tour",
    "get_training_resources",
    "get_setup_wizard",
    "request_support",
    "track_progress",
]

# Valuation & Refinance Tools
HOME_VALUATION_TOOLS = [
    "calculate_home_value",
    "get_appreciation_rates",
    "calculate_equity_position",
    "calculate_amortization",
    "get_maturity_date",
    "batch_update_valuations",
    "get_value_history",
    "compare_market_appreciation",
]

REFINANCE_TOOLS = [
    "score_refi_opportunity",
    "calculate_refi_savings",
    "get_refi_candidates",
    "analyze_breakeven",
    "compare_refi_scenarios",
    "get_refi_portfolio_summary",
    "recommend_refi_action",
    "batch_update_refi_scores",
]

# Outreach & Campaign Tools
OUTREACH_TOOLS = [
    "find_clients_for_outreach",
    "send_bulk_sms_outreach",
    "send_mortgage_review_outreach",
    "send_calendar_invite_email",
]

# Smart Documents Bridge Tools
SMART_DOCUMENT_TOOLS = [
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
]

# Analytics Tools
HISTORICAL_TOOLS = [
    "get_performance_by_period",
    "compare_periods",
    "get_data_availability",
]


# =============================================================================
# All Tools Organized by Category
# =============================================================================

ALL_TOOLS = {
    # CRM
    "pipeline": PIPELINE_TOOLS,
    "compliance": COMPLIANCE_TOOLS,
    "leads": LEAD_TOOLS,
    "documents": DOCUMENT_TOOLS,
    "profitability": PROFITABILITY_TOOLS,
    "rates": RATE_TOOLS,
    "coaching": COACHING_TOOLS,
    "customer": CUSTOMER_TOOLS,
    # Communication
    "voice": VOICE_TOOLS,
    "video": VIDEO_TOOLS,
    "email_intel": EMAIL_INTEL_TOOLS,
    "receptionist": RECEPTIONIST_TOOLS,
    # Operations
    "scheduler": SCHEDULER_TOOLS,
    "tasks": TASK_TOOLS,
    "sla": SLA_TOOLS,
    "integrations": INTEGRATION_TOOLS,
    # Business
    "reporting": REPORTING_TOOLS,
    "notifications": NOTIFICATION_TOOLS,
    "subscription": SUBSCRIPTION_TOOLS,
    "onboarding": ONBOARDING_TOOLS,
    # Valuation & Refinance
    "home_valuation": HOME_VALUATION_TOOLS,
    "refinance": REFINANCE_TOOLS,
    # Outreach & Campaigns
    "outreach": OUTREACH_TOOLS,
    # Smart Documents Bridge
    "smart_documents": SMART_DOCUMENT_TOOLS,
    # Analytics
    "historical": HISTORICAL_TOOLS,
}


# =============================================================================
# Agent Configurations (Full 20-agent system)
# =============================================================================

AGENT_CONFIGS = {
    # CRM Agents
    "pipeline_analyst": {
        "description": "Analyzes loan pipeline health, bottlenecks, and conversion rates",
        "tools": PIPELINE_TOOLS,
        "category": "crm",
    },
    "compliance_checker": {
        "description": "Monitors TRID, RESPA, and fair lending compliance",
        "tools": COMPLIANCE_TOOLS,
        "category": "crm",
    },
    "lead_nurturer": {
        "description": "Manages lead engagement, scoring, and follow-up strategies",
        "tools": LEAD_TOOLS,
        "category": "crm",
    },
    "document_tracker": {
        "description": "Tracks documents, conditions, and third-party orders",
        "tools": DOCUMENT_TOOLS + SMART_DOCUMENT_TOOLS,
        "category": "crm",
    },
    "profitability_analyst": {
        "description": "Analyzes loan profitability, margins, and revenue optimization",
        "tools": PROFITABILITY_TOOLS,
        "category": "crm",
    },
    "rate_advisor": {
        "description": "Provides rate analysis, lock recommendations, and market insights",
        "tools": RATE_TOOLS,
        "category": "crm",
    },
    "team_coach": {
        "description": "Tracks LO performance, provides coaching, and identifies training needs",
        "tools": COACHING_TOOLS,
        "category": "crm",
    },
    "customer_intelligence": {
        "description": "Provides customer 360 view, LTV analysis, and opportunity identification",
        "tools": CUSTOMER_TOOLS,
        "category": "crm",
    },
    # Communication Agents
    "voice_os": {
        "description": "Manages phone calls, voicemail, SMS outreach, campaigns, and call analytics",
        "tools": VOICE_TOOLS + OUTREACH_TOOLS,
        "category": "communication",
    },
    "uvip": {
        "description": "Handles video meetings, recordings, and engagement analysis",
        "tools": VIDEO_TOOLS,
        "category": "communication",
    },
    "email_intelligence": {
        "description": "Analyzes emails, detects intent, and generates contextual responses",
        "tools": EMAIL_INTEL_TOOLS,
        "category": "communication",
    },
    "ai_receptionist": {
        "description": "Handles initial inquiries, qualifies leads, and routes to specialists",
        "tools": RECEPTIONIST_TOOLS,
        "category": "communication",
    },
    # Operations Agents
    "smart_scheduler": {
        "description": "Manages appointments, calendar optimization, and scheduling",
        "tools": SCHEDULER_TOOLS,
        "category": "operations",
    },
    "task_automation": {
        "description": "Automates task creation, assignment, and workflow management",
        "tools": TASK_TOOLS,
        "category": "operations",
    },
    "sla_tracker": {
        "description": "Monitors SLA compliance, alerts, and breach prevention",
        "tools": SLA_TOOLS,
        "category": "operations",
    },
    "integrations": {
        "description": "Manages LOS, credit, AUS, and vendor integrations",
        "tools": INTEGRATION_TOOLS,
        "category": "operations",
    },
    # Valuation & Refinance Agents
    "home_valuation": {
        "description": "Calculates home values, equity positions, amortization, and maturity dates using state-level appreciation",
        "tools": HOME_VALUATION_TOOLS,
        "category": "valuation",
    },
    "refinance_advisor": {
        "description": "Scores refinance opportunities, calculates savings, identifies candidates, and compares scenarios",
        "tools": REFINANCE_TOOLS,
        "category": "valuation",
    },
    # Business Agents
    "reporting_engine": {
        "description": "Generates reports, analytics, and data exports",
        "tools": REPORTING_TOOLS,
        "category": "business",
    },
    "notification_center": {
        "description": "Manages notifications, alerts, and communication preferences",
        "tools": NOTIFICATION_TOOLS,
        "category": "business",
    },
    "subscription_manager": {
        "description": "Handles subscriptions, billing, and usage tracking",
        "tools": SUBSCRIPTION_TOOLS,
        "category": "business",
    },
    "onboarding_assistant": {
        "description": "Guides new users through setup, training, and platform adoption",
        "tools": ONBOARDING_TOOLS,
        "category": "business",
    },
}


# =============================================================================
# Utility Functions
# =============================================================================

def get_all_tool_names() -> list:
    """Get flat list of all tool names."""
    names = []
    for tools in ALL_TOOLS.values():
        names.extend(tools)
    return names


def get_tool_count() -> dict:
    """Get count of tools by category."""
    return {k: len(v) for k, v in ALL_TOOLS.items()}


def get_total_tool_count() -> int:
    """Get total number of tools."""
    return sum(len(v) for v in ALL_TOOLS.values())


def get_agents_by_category(category: str) -> list:
    """Get agent names by category (crm, communication, operations, business)."""
    return [
        name for name, config in AGENT_CONFIGS.items()
        if config.get("category") == category
    ]


def print_tool_summary():
    """Print summary of all registered tools."""
    print("=" * 60)
    print("Perennia AI - Registered Agent Tools")
    print("=" * 60)

    total = 0
    for category, tools in ALL_TOOLS.items():
        print(f"\n{category.upper()} ({len(tools)} tools)")
        print("-" * 40)
        for tool_name in tools:
            defn = tool_registry.get(tool_name)
            if defn:
                print(f"  • {tool_name}")
                print(f"    {defn.description[:60]}..." if len(defn.description) > 60 else f"    {defn.description}")
            else:
                print(f"  • {tool_name} (not registered)")
            total += 1

    print("\n" + "=" * 60)
    print(f"Total: {total} tools across {len(ALL_TOOLS)} categories")
    print(f"Agents: {len(AGENT_CONFIGS)} specialized agents")
    print("=" * 60)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Infrastructure
    "get_db",
    "execute_query",
    "execute_single",
    # Tenant Isolation
    "set_tenant_context",
    "get_tenant_context",
    "clear_tenant_context",
    "ToolStatus",
    "ToolResult",
    "ToolError",
    "ToolDefinition",
    "ToolRegistry",
    "tool_registry",
    "mortgage_tool",
    "get_tools_for_agent",
    "execute_tool",

    # Helpers
    "format_currency",
    "format_percentage",
    "format_date",
    "days_between",
    "calculate_percentage_change",

    # Enums
    "LoanStatus",
    "LoanType",
    "PropertyType",
    "OccupancyType",
    "SLA_TARGETS",
    "DOCUMENT_CATEGORIES",

    # CRM Modules
    "pipeline",
    "compliance",
    "leads",
    "documents",
    "profitability",
    "rates",
    "coaching",
    "customer",

    # Communication Modules
    "voice",
    "video",
    "email_intel",
    "receptionist",

    # Operations Modules
    "scheduler",
    "tasks",
    "sla",
    "integrations",

    # Business Modules
    "reporting",
    "notifications",
    "subscription",
    "onboarding",

    # Valuation & Refinance Modules
    "home_valuation",
    "refinance",

    # Outreach Modules
    "outreach_tools",

    # Smart Documents Bridge Module
    "smart_documents",

    # Analytics Modules
    "historical",

    # Configuration
    "AGENT_MODULES",
    "AGENT_CONFIGS",
    "ALL_TOOLS",

    # CRM Tool Lists
    "PIPELINE_TOOLS",
    "COMPLIANCE_TOOLS",
    "LEAD_TOOLS",
    "DOCUMENT_TOOLS",
    "PROFITABILITY_TOOLS",
    "RATE_TOOLS",
    "COACHING_TOOLS",
    "CUSTOMER_TOOLS",

    # Communication Tool Lists
    "VOICE_TOOLS",
    "VIDEO_TOOLS",
    "EMAIL_INTEL_TOOLS",
    "RECEPTIONIST_TOOLS",

    # Operations Tool Lists
    "SCHEDULER_TOOLS",
    "TASK_TOOLS",
    "SLA_TOOLS",
    "INTEGRATION_TOOLS",

    # Business Tool Lists
    "REPORTING_TOOLS",
    "NOTIFICATION_TOOLS",
    "SUBSCRIPTION_TOOLS",
    "ONBOARDING_TOOLS",

    # Valuation & Refinance Tool Lists
    "HOME_VALUATION_TOOLS",
    "REFINANCE_TOOLS",

    # Outreach Tool Lists
    "OUTREACH_TOOLS",

    # Smart Documents Bridge Tool Lists
    "SMART_DOCUMENT_TOOLS",

    # Analytics Tool Lists
    "HISTORICAL_TOOLS",

    # Utilities
    "get_all_tool_names",
    "get_tool_count",
    "get_total_tool_count",
    "get_agents_by_category",
    "print_tool_summary",
]
