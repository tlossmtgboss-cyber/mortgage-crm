"""
Tool Deduplication Audit
=========================
Scans all @mortgage_tool registrations across backend/agents/tools/ and
identifies duplicate, overlapping, and orphaned tools.

This is a read-only analysis module -- it does NOT modify tool registrations.
Run audit_tools() to get a full deduplication report.

Usage:
    from agents.tool_audit import audit_tools, get_tool_overlap_matrix

    report = audit_tools()
    print(f"Total tools: {report['total_tools']}")
    print(f"Proposed deduped: {report['proposed_deduped_count']}")
    for group in report['duplicate_groups']:
        print(f"  MERGE: {group['tools']} -> {group['canonical']}")
"""

import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# KNOWN DUPLICATE / OVERLAP GROUPS
# =============================================================================
#
# These groups were identified by manual inspection of the 233 @mortgage_tool
# registrations. Each group represents tools that do the same thing (or nearly
# the same thing) under different names, or whose functionality is a strict
# subset of another tool.
#
# Format: (canonical_tool, [aliases_or_subsets], reason)

@dataclass
class DuplicateGroup:
    """A group of tools that should be merged into one."""
    canonical: str
    duplicates: Tuple[str, ...]
    reason: str
    action: str  # "merge", "remove", "alias"


DUPLICATE_GROUPS: List[DuplicateGroup] = [
    # --- Rate / Market overlaps ---
    DuplicateGroup(
        canonical="get_current_rates",
        duplicates=("get_market_events",),
        reason=(
            "get_market_events provides rate context that overlaps with "
            "get_current_rates. Both fetch current market data. Consider "
            "merging market events into get_current_rates as an optional field."
        ),
        action="merge",
    ),
    DuplicateGroup(
        canonical="compare_rate_scenarios",
        duplicates=("compare_refi_scenarios",),
        reason=(
            "compare_refi_scenarios is a specialized version of "
            "compare_rate_scenarios. The refi variant adds breakeven analysis "
            "but the core comparison logic is identical."
        ),
        action="merge",
    ),

    # --- Lead / Customer overlaps ---
    DuplicateGroup(
        canonical="get_lead_details",
        duplicates=("get_customer_360",),
        reason=(
            "get_customer_360 fetches the same core borrower data as "
            "get_lead_details but adds relationship and LTV context. "
            "These should be a single tool with an 'include_relationships' flag."
        ),
        action="merge",
    ),
    DuplicateGroup(
        canonical="get_engagement_history",
        duplicates=("get_interaction_history",),
        reason=(
            "get_engagement_history (leads module) and get_interaction_history "
            "(customer module) query the same interaction log table. Only the "
            "response formatting differs."
        ),
        action="merge",
    ),
    DuplicateGroup(
        canonical="suggest_followup",
        duplicates=("schedule_outreach",),
        reason=(
            "suggest_followup generates a recommendation that schedule_outreach "
            "then executes. In practice, callers always invoke both sequentially. "
            "Merge into suggest_followup with an 'auto_schedule' flag."
        ),
        action="merge",
    ),

    # --- Document overlaps ---
    DuplicateGroup(
        canonical="get_missing_documents",
        duplicates=("get_needs_list",),
        reason=(
            "get_needs_list (smart_documents) is a subset of "
            "get_missing_documents (documents). Both query the same conditions "
            "and return outstanding items."
        ),
        action="alias",
    ),
    DuplicateGroup(
        canonical="check_document_expiration",
        duplicates=("check_document_freshness",),
        reason=(
            "check_document_freshness (smart_documents) performs the same "
            "expiry check as check_document_expiration (documents). The smart "
            "variant adds a freshness score but the core logic is duplicated."
        ),
        action="merge",
    ),
    DuplicateGroup(
        canonical="track_document_request",
        duplicates=("track_portal_activity",),
        reason=(
            "track_portal_activity tracks the same document status transitions "
            "as track_document_request, just from the borrower portal perspective. "
            "Merge into a single tracker with a 'source' parameter."
        ),
        action="merge",
    ),

    # --- Communication overlaps ---
    DuplicateGroup(
        canonical="draft_message",
        duplicates=("draft_email_response",),
        reason=(
            "draft_message (leads) and draft_email_response (email_intel) "
            "both generate text using Claude. draft_message is more general "
            "(SMS or email), while draft_email_response is email-specific. "
            "Merge into draft_message with a 'channel' parameter."
        ),
        action="merge",
    ),
    DuplicateGroup(
        canonical="send_email",
        duplicates=("send_bulk_email_outreach",),
        reason=(
            "send_bulk_email_outreach is a batch wrapper around send_email. "
            "Consider adding a 'recipients' list param to send_email instead "
            "of maintaining a separate bulk tool."
        ),
        action="merge",
    ),
    DuplicateGroup(
        canonical="send_notification",
        duplicates=("batch_send",),
        reason=(
            "batch_send is a multi-recipient version of send_notification. "
            "Merge by adding batch support to send_notification."
        ),
        action="merge",
    ),

    # --- Pipeline / Reporting overlaps ---
    DuplicateGroup(
        canonical="get_pipeline_metrics",
        duplicates=("get_dashboard_metrics",),
        reason=(
            "get_dashboard_metrics is a superset of get_pipeline_metrics with "
            "additional UI-focused fields. The core pipeline data is identical."
        ),
        action="merge",
    ),
    DuplicateGroup(
        canonical="generate_pipeline_report",
        duplicates=("generate_production_report", "generate_lo_performance_report"),
        reason=(
            "All three report generators query the same pipeline data with "
            "different grouping/filtering. Consolidate into generate_pipeline_report "
            "with a 'report_type' parameter."
        ),
        action="merge",
    ),
    DuplicateGroup(
        canonical="get_performance_trends",
        duplicates=("get_profitability_trends",),
        reason=(
            "get_performance_trends (coaching) and get_profitability_trends "
            "(profitability) both compute time-series metrics on the same "
            "underlying loan data. Merge with a 'metric_type' parameter."
        ),
        action="merge",
    ),

    # --- Scheduling overlaps ---
    DuplicateGroup(
        canonical="get_availability",
        duplicates=("get_lo_availability",),
        reason=(
            "get_lo_availability (receptionist) queries the same calendar as "
            "get_availability (scheduler). The receptionist variant adds "
            "call-queue context but the availability check is identical."
        ),
        action="merge",
    ),

    # --- SLA overlaps ---
    DuplicateGroup(
        canonical="check_sla_status",
        duplicates=("check_document_sla",),
        reason=(
            "check_document_sla (smart_documents) is a document-specific "
            "view of check_sla_status. The SLA engine is the same."
        ),
        action="alias",
    ),

    # --- Escalation overlaps ---
    DuplicateGroup(
        canonical="escalate_issue",
        duplicates=("escalate_sla_breach", "create_escalation"),
        reason=(
            "Three tools create escalation records with slightly different "
            "triggers. Consolidate into escalate_issue with a 'trigger_type' "
            "parameter (manual, sla_breach, threshold)."
        ),
        action="merge",
    ),
]


# =============================================================================
# TOOL CATEGORIZATION
# =============================================================================

# Tools that are read-only (safe for any agent)
READ_ONLY_TOOLS: Set[str] = {
    "get_pipeline_metrics", "get_loans_by_status", "get_loan_aging_report",
    "calculate_conversion_rates", "predict_closing_timeline",
    "get_bottleneck_analysis", "compare_to_benchmark",
    "get_lo_pipeline_breakdown", "get_missing_documents",
    "get_loan_conditions", "get_document_timeline",
    "check_document_expiration", "get_third_party_status",
    "get_current_rates", "analyze_rate_trends", "get_market_events",
    "get_lead_details", "get_engagement_history", "get_interaction_history",
    "score_lead", "get_similar_converted_leads", "get_optimal_contact_time",
    "get_stale_leads", "get_top_leads", "get_customer_360",
    "map_relationships", "calculate_ltv", "assess_churn_risk",
    "find_opportunities", "get_referral_network", "get_market_comparison",
    "get_lo_metrics", "compare_to_peers", "get_best_practices",
    "get_performance_trends", "get_call_history", "get_call_metrics",
    "get_meeting_recordings", "get_video_analytics",
    "get_participant_insights", "get_email_thread", "get_email_templates",
    "analyze_email_engagement", "get_task_queue", "get_task_templates",
    "get_workflow_status", "check_sla_status", "get_sla_dashboard",
    "get_sla_alerts", "get_sla_report", "check_integration_status",
    "get_report_templates", "get_dashboard_metrics",
    "get_pending_notifications", "get_notification_templates",
    "get_delivery_status", "get_preferences", "get_subscription_status",
    "get_plans", "get_billing_history", "get_usage_metrics",
    "get_onboarding_status", "get_checklist", "get_training_resources",
    "get_setup_wizard", "calculate_home_value", "get_appreciation_rates",
    "calculate_equity_position", "calculate_amortization",
    "get_maturity_date", "get_value_history", "compare_market_appreciation",
    "score_refi_opportunity", "calculate_refi_savings",
    "get_refi_candidates", "analyze_breakeven", "get_refi_portfolio_summary",
    "get_smart_doc_status", "check_document_freshness",
    "get_document_decisions", "get_needs_list", "check_document_sla",
    "get_screenshot_flags", "get_document_extraction",
    "track_portal_activity", "get_followup_campaign_status",
    "get_policy_events", "get_performance_by_period", "compare_periods",
    "get_data_availability", "get_sms_conversation_history",
    "check_trid_compliance", "check_respa_compliance",
    "check_fair_lending", "get_state_requirements", "audit_loan_file",
    "get_disclosure_timeline", "check_tolerance_violations",
    "get_compliance_history", "get_call_queue_status", "get_power_dialer_queue",
    "get_availability", "get_upcoming_appointments",
    "get_scheduler_metrics", "get_appointment_history",
    "get_best_booking_times", "get_no_show_analysis",
    "get_escalation_status", "get_escalation_analytics",
    "check_dnc_status", "check_tcpa_consent", "check_calling_window",
    "validate_outbound_contact", "get_sync_status", "get_field_mappings",
    "get_sync_health", "parse_email", "match_email_to_loan",
    "categorize_email_attachments", "search_email_inbox",
    "find_contact_email", "find_contact_phone",
    "get_emails_needing_response", "analyze_tone",
    "get_thread_tone_trends", "compare_tone_to_baseline",
    "get_daily_call_list", "get_daily_priorities",
    "get_greeting_script", "get_lo_availability",
    "analyze_call_sentiment", "transcribe_call",
    "calculate_lock_cost", "monitor_float_position",
    "get_extension_pricing", "compare_rate_scenarios",
    "calculate_loan_profitability", "analyze_margins_by_segment",
    "forecast_revenue", "compare_lo_profitability",
    "get_cost_breakdown", "calculate_pull_through_impact",
    "compare_refi_scenarios", "recommend_refi_action",
    "analyze_meeting", "extract_meeting_action_items",
    "generate_meeting_summary",
}

# Tools that perform write/side-effect operations
WRITE_TOOLS: Set[str] = {
    "create_task", "bulk_create_tasks", "update_task_status",
    "assign_task", "bulk_update_tasks", "execute_workflow",
    "book_appointment", "reschedule_appointment", "cancel_appointment",
    "send_appointment_reminder", "sync_external_calendar",
    "send_email", "send_notification", "batch_send",
    "schedule_notification", "schedule_report",
    "draft_message", "draft_email_response",
    "send_document_reminder", "track_document_request",
    "escalate_issue", "escalate_sla_breach",
    "initiate_outbound_call", "drop_voicemail", "schedule_callback",
    "send_sms_message", "start_scheduling_sms",
    "send_bulk_sms_outreach", "send_bulk_email_outreach",
    "send_mortgage_review_outreach", "send_calendar_invite_email",
    "find_clients_for_outreach",
    "schedule_outreach", "suggest_followup",
    "create_callback_request", "handle_inbound_call",
    "log_call_interaction", "route_call", "qualify_caller",
    "complete_step", "start_guided_tour", "request_support",
    "track_progress",
    "change_plan", "update_payment_method", "manage_addons",
    "pause_subscription", "update_preferences",
    "sync_los_data", "trigger_credit_pull", "submit_to_aus",
    "order_appraisal", "order_title", "send_for_esign",
    "get_pricing_engine_quote",
    "batch_update_valuations", "batch_update_refi_scores",
    "configure_sla_rules", "project_sla_breach",
    "set_performance_goals", "identify_training_needs",
    "generate_coaching_plan", "track_improvement",
    "optimize_pricing", "recommend_lock_strategy",
    "optimize_schedule", "export_report", "create_custom_report",
    "generate_pipeline_report", "generate_production_report",
    "generate_lo_performance_report",
    "schedule_video_meeting", "send_async_video",
    "generate_pre_approval_letter",
    "evaluate_escalation", "create_escalation",
    "execute_warm_handoff", "resolve_escalation",
    "create_referral_partner",
    "resolve_sync_conflict", "trigger_sync", "update_field_mapping",
}


# =============================================================================
# AUDIT ENGINE
# =============================================================================

def _scan_tool_files() -> Dict[str, List[str]]:
    """
    Scan backend/agents/tools/*.py and extract @mortgage_tool registrations.

    Returns:
        Dict mapping filename -> list of tool names registered in that file
    """
    tools_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "tools"
    )

    file_tools: Dict[str, List[str]] = {}

    if not os.path.isdir(tools_dir):
        logger.warning(f"Tools directory not found: {tools_dir}")
        return file_tools

    # Pattern to match @mortgage_tool(name="...")
    name_pattern = re.compile(r'@mortgage_tool\s*\([\s\S]*?name\s*=\s*"([^"]+)"')

    for filename in sorted(os.listdir(tools_dir)):
        if not filename.endswith(".py"):
            continue
        if filename.startswith("test_") or filename == "__init__.py":
            continue

        filepath = os.path.join(tools_dir, filename)
        try:
            with open(filepath, "r") as f:
                content = f.read()
        except (IOError, OSError) as e:
            logger.warning(f"Could not read {filepath}: {e}")
            continue

        names = name_pattern.findall(content)
        if names:
            file_tools[filename] = names

    return file_tools


def _get_agent_tool_assignments() -> Dict[str, List[str]]:
    """
    Get the current agent -> tool assignments from tool_integration.py.

    Returns:
        Dict mapping agent role -> list of tool names
    """
    try:
        from .tool_integration import AGENT_CONFIGS
        return {
            role: config.tool_names
            for role, config in AGENT_CONFIGS.items()
        }
    except ImportError:
        logger.warning("Could not import AGENT_CONFIGS from tool_integration")
        return {}


def _compute_tool_agent_reverse_map(
    agent_tools: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """
    Build reverse map: tool_name -> list of agents that use it.
    """
    reverse: Dict[str, List[str]] = defaultdict(list)
    for agent, tools in agent_tools.items():
        for tool in tools:
            reverse[tool].append(agent)
    return dict(reverse)


def _find_orphaned_tools(
    registered_tools: Set[str],
    assigned_tools: Set[str],
) -> Set[str]:
    """
    Find tools that are registered via @mortgage_tool but not assigned to
    any agent in AGENT_CONFIGS.
    """
    return registered_tools - assigned_tools


def _find_phantom_tools(
    registered_tools: Set[str],
    assigned_tools: Set[str],
) -> Set[str]:
    """
    Find tools that are referenced in AGENT_CONFIGS but not registered
    via @mortgage_tool (phantom references).
    """
    return assigned_tools - registered_tools


def get_tool_overlap_matrix() -> Dict[str, Dict[str, List[str]]]:
    """
    Build a matrix showing which tools are shared between agents.

    Returns:
        Dict[agent_a][agent_b] -> list of shared tool names
    """
    agent_tools = _get_agent_tool_assignments()
    overlap: Dict[str, Dict[str, List[str]]] = {}

    agents = sorted(agent_tools.keys())
    for i, agent_a in enumerate(agents):
        tools_a = set(agent_tools[agent_a])
        overlap[agent_a] = {}
        for agent_b in agents[i + 1:]:
            tools_b = set(agent_tools[agent_b])
            shared = sorted(tools_a & tools_b)
            if shared:
                overlap[agent_a][agent_b] = shared

    return overlap


def audit_tools() -> Dict:
    """
    Run a full tool deduplication audit.

    Returns a dict with:
        - total_tools: Number of unique tools registered via @mortgage_tool
        - tools_by_file: Dict[filename -> list[tool_name]]
        - total_agents: Number of agent configs
        - agent_tool_counts: Dict[agent -> tool_count]
        - orphaned_tools: Tools registered but not assigned to any agent
        - phantom_tools: Tools referenced in agent configs but not registered
        - duplicate_groups: List of identified duplicate/overlap groups
        - proposed_deduped_count: Estimated tool count after deduplication
        - tools_per_agent_avg: Average tools per agent
        - most_shared_tools: Top 10 tools shared across most agents
        - read_only_count: Number of read-only tools
        - write_count: Number of write/side-effect tools
        - consolidated_coverage: How well consolidated agents cover all tools
    """
    # Scan tool files
    file_tools = _scan_tool_files()
    all_registered: Set[str] = set()
    for tools in file_tools.values():
        all_registered.update(tools)

    # Get agent assignments
    agent_tools = _get_agent_tool_assignments()
    all_assigned: Set[str] = set()
    for tools in agent_tools.values():
        all_assigned.update(tools)

    # Reverse map
    tool_agents = _compute_tool_agent_reverse_map(agent_tools)

    # Orphaned and phantom
    orphaned = _find_orphaned_tools(all_registered, all_assigned)
    phantom = _find_phantom_tools(all_registered, all_assigned)

    # Duplicate analysis
    tools_to_remove: Set[str] = set()
    for group in DUPLICATE_GROUPS:
        tools_to_remove.update(group.duplicates)

    proposed_deduped = len(all_registered) - len(tools_to_remove & all_registered)

    # Most shared tools
    shared_counts = [
        (tool, len(agents))
        for tool, agents in tool_agents.items()
    ]
    shared_counts.sort(key=lambda x: -x[1])
    most_shared = shared_counts[:10]

    # Read/write classification
    read_only_in_registry = READ_ONLY_TOOLS & all_registered
    write_in_registry = WRITE_TOOLS & all_registered
    unclassified = all_registered - READ_ONLY_TOOLS - WRITE_TOOLS

    # Consolidated agent coverage
    try:
        from .consolidation import CONSOLIDATED_AGENTS
        consolidated_tools: Set[str] = set()
        for agent in CONSOLIDATED_AGENTS.values():
            consolidated_tools.update(agent.tool_names)
        consolidated_coverage = len(consolidated_tools & all_registered)
        consolidated_missing = sorted(all_registered - consolidated_tools)
    except ImportError:
        consolidated_coverage = 0
        consolidated_missing = []

    return {
        "total_tools": len(all_registered),
        "tools_by_file": {
            filename: {
                "count": len(tools),
                "tools": tools,
            }
            for filename, tools in sorted(file_tools.items())
        },
        "total_agents": len(agent_tools),
        "agent_tool_counts": {
            agent: len(tools)
            for agent, tools in sorted(agent_tools.items())
        },
        "orphaned_tools": sorted(orphaned),
        "orphaned_count": len(orphaned),
        "phantom_tools": sorted(phantom),
        "phantom_count": len(phantom),
        "duplicate_groups": [
            {
                "canonical": g.canonical,
                "duplicates": list(g.duplicates),
                "reason": g.reason,
                "action": g.action,
            }
            for g in DUPLICATE_GROUPS
        ],
        "duplicate_group_count": len(DUPLICATE_GROUPS),
        "proposed_deduped_count": proposed_deduped,
        "tools_removed_by_dedup": sorted(tools_to_remove & all_registered),
        "tools_per_agent_avg": (
            round(sum(len(t) for t in agent_tools.values()) / len(agent_tools), 1)
            if agent_tools else 0
        ),
        "most_shared_tools": [
            {"tool": tool, "agent_count": count}
            for tool, count in most_shared
        ],
        "read_only_count": len(read_only_in_registry),
        "write_count": len(write_in_registry),
        "unclassified_count": len(unclassified),
        "unclassified_tools": sorted(unclassified),
        "consolidated_coverage": consolidated_coverage,
        "consolidated_missing_tools": consolidated_missing,
    }


def print_audit_summary(report: Optional[Dict] = None) -> str:
    """
    Generate a human-readable summary of the audit report.

    Args:
        report: Pre-computed audit report (calls audit_tools() if None)

    Returns:
        Formatted string summary
    """
    if report is None:
        report = audit_tools()

    lines = [
        "=" * 60,
        "TOOL DEDUPLICATION AUDIT REPORT",
        "=" * 60,
        "",
        f"Total registered tools:     {report['total_tools']}",
        f"Total agent configs:        {report['total_agents']}",
        f"Avg tools per agent:        {report['tools_per_agent_avg']}",
        f"Read-only tools:            {report['read_only_count']}",
        f"Write/side-effect tools:    {report['write_count']}",
        f"Unclassified tools:         {report['unclassified_count']}",
        "",
        "--- Deduplication ---",
        f"Duplicate groups found:     {report['duplicate_group_count']}",
        f"Tools to remove/merge:      {len(report['tools_removed_by_dedup'])}",
        f"Proposed deduped count:     {report['proposed_deduped_count']}",
        f"Reduction:                  {report['total_tools'] - report['proposed_deduped_count']} tools "
        f"({((report['total_tools'] - report['proposed_deduped_count']) / max(report['total_tools'], 1) * 100):.1f}%)",
        "",
        "--- Orphaned & Phantom ---",
        f"Orphaned (registered, no agent): {report['orphaned_count']}",
        f"Phantom (in agent, not registered): {report['phantom_count']}",
        "",
        "--- Consolidated Agent Coverage ---",
        f"Tools covered by 10 agents: {report['consolidated_coverage']} / {report['total_tools']}",
        f"Missing from consolidated:  {len(report['consolidated_missing_tools'])}",
    ]

    if report['orphaned_tools']:
        lines.append("")
        lines.append("Orphaned tools:")
        for t in report['orphaned_tools']:
            lines.append(f"  - {t}")

    if report['phantom_tools']:
        lines.append("")
        lines.append("Phantom tools:")
        for t in report['phantom_tools']:
            lines.append(f"  - {t}")

    if report['consolidated_missing_tools']:
        lines.append("")
        lines.append("Tools missing from consolidated agents:")
        for t in report['consolidated_missing_tools']:
            lines.append(f"  - {t}")

    lines.append("")
    lines.append("--- Most Shared Tools ---")
    for item in report['most_shared_tools']:
        lines.append(f"  {item['tool']}: used by {item['agent_count']} agents")

    lines.append("")
    lines.append("--- Duplicate Groups ---")
    for group in report['duplicate_groups']:
        lines.append(f"  [{group['action'].upper()}] {group['canonical']} <- {', '.join(group['duplicates'])}")
        lines.append(f"    {group['reason'][:100]}...")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)
