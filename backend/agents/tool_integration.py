"""
Perennia AI - Tool Integration Layer
====================================
Connects agent tools to the AI orchestrator and LangChain workflow.
Provides tool binding, execution management, and result processing.
"""

from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
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


AGENT_CONFIGS = {
    # =========================================================================
    # CRM Agents (8)
    # =========================================================================
    "pipeline_analyst": AgentToolConfig(
        role="pipeline_analyst",
        name="Pipeline Analyst",
        description="Analyzes loan pipeline metrics and performance",
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
        ],
        requires_approval_for=["override_compliance_flag"],
        recommended_model="sonnet",  # Regulatory compliance needs precise reasoning
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
        ],
        requires_approval_for=["send_email"],
        recommended_model="sonnet",  # Email drafting/analysis needs quality
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
        ],
        recommended_model="haiku",  # Calendar CRUD is tool-driven
    ),
    "task_automation": AgentToolConfig(
        role="task_automation",
        name="Task Automation",
        description="Automates task creation, assignment, and workflow management",
        tool_names=[
            "create_task",
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
        description="Generates reports, analytics, and data exports",
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
        recommended_model="sonnet",  # Cross-agent coordination requires analytical reasoning
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
