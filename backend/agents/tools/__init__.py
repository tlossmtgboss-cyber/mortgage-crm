"""
Perennia AI - Agent Tools Package
=================================
Comprehensive tooling for 8 specialized mortgage CRM agents.

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

# Import all tool modules to register tools
from . import pipeline
from . import compliance
from . import leads
from . import documents
from . import profitability
from . import rates
from . import coaching
from . import customer

# Agent role to module mapping
AGENT_MODULES = {
    "pipeline_analyst": pipeline,
    "compliance_checker": compliance,
    "lead_nurturer": leads,
    "document_tracker": documents,
    "profitability_analyst": profitability,
    "rate_advisor": rates,
    "team_coach": coaching,
    "customer_intelligence": customer,
}

# All tool names by category
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

# All tools organized
ALL_TOOLS = {
    "pipeline": PIPELINE_TOOLS,
    "compliance": COMPLIANCE_TOOLS,
    "leads": LEAD_TOOLS,
    "documents": DOCUMENT_TOOLS,
    "profitability": PROFITABILITY_TOOLS,
    "rates": RATE_TOOLS,
    "coaching": COACHING_TOOLS,
    "customer": CUSTOMER_TOOLS,
}


def get_all_tool_names() -> list:
    """Get flat list of all tool names."""
    names = []
    for tools in ALL_TOOLS.values():
        names.extend(tools)
    return names


def get_tool_count() -> dict:
    """Get count of tools by category."""
    return {k: len(v) for k, v in ALL_TOOLS.items()}


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
    print("=" * 60)


__all__ = [
    # Infrastructure
    "get_db",
    "execute_query",
    "execute_single",
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

    # Modules
    "pipeline",
    "compliance",
    "leads",
    "documents",
    "profitability",
    "rates",
    "coaching",
    "customer",

    # Tool lists
    "AGENT_MODULES",
    "ALL_TOOLS",
    "PIPELINE_TOOLS",
    "COMPLIANCE_TOOLS",
    "LEAD_TOOLS",
    "DOCUMENT_TOOLS",
    "PROFITABILITY_TOOLS",
    "RATE_TOOLS",
    "COACHING_TOOLS",
    "CUSTOMER_TOOLS",

    # Utilities
    "get_all_tool_names",
    "get_tool_count",
    "print_tool_summary",
]
