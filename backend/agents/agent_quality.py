"""
Agent Quality Metrics & Tool Contract Validation
==================================================
Defines contract tests for each tool (input schema, expected output schema),
validates tool output against contracts, and tracks per-agent quality metrics.

This is a new overlay module -- it does NOT modify existing tool registrations
or agent service. It provides quality gates for gradual migration.

Usage:
    from agents.agent_quality import (
        get_tool_contract,
        validate_tool_output,
        AgentMetricsCollector,
    )

    # Check a tool's contract
    contract = get_tool_contract("get_pipeline_metrics")

    # Validate tool output
    ok, errors = validate_tool_output("get_pipeline_metrics", result)

    # Track agent metrics
    collector = AgentMetricsCollector.get_instance()
    collector.record_invocation("pipeline_coach", "get_pipeline_metrics", latency_ms=42.5)
    metrics = collector.get_agent_metrics("pipeline_coach")
"""

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)


# =============================================================================
# TOOL CONTRACT DEFINITIONS
# =============================================================================

@dataclass(frozen=True)
class FieldSpec:
    """Specification for a single field in a tool's input or output."""
    name: str
    type: str  # "str", "int", "float", "bool", "list", "dict", "any"
    required: bool = True
    description: str = ""
    example: Any = None
    # For nested dicts / lists
    items_type: Optional[str] = None  # Type of list items


@dataclass(frozen=True)
class ToolContract:
    """
    Contract defining the expected input parameters and output schema
    for a tool. Used for validation and documentation.
    """
    tool_name: str
    description: str
    input_fields: Tuple[FieldSpec, ...]
    output_fields: Tuple[FieldSpec, ...]
    # Expected output structure: "dict", "list", "scalar"
    output_type: str = "dict"
    # Whether the tool is idempotent (safe to retry)
    idempotent: bool = True
    # Expected latency range (ms)
    expected_latency_min_ms: float = 5.0
    expected_latency_max_ms: float = 5000.0
    # Risk level
    risk_level: str = "low"  # low, medium, high


# ---------------------------------------------------------------------------
# Pipeline / Analytics tool contracts
# ---------------------------------------------------------------------------

PIPELINE_METRICS_CONTRACT = ToolContract(
    tool_name="get_pipeline_metrics",
    description="Retrieve pipeline health metrics for the current LO",
    input_fields=(
        FieldSpec("lo_id", "str", required=False, description="Loan officer ID filter"),
        FieldSpec("date_range", "str", required=False, description="Date range filter"),
    ),
    output_fields=(
        FieldSpec("total_loans", "int", required=True, description="Total active loans"),
        FieldSpec("by_stage", "dict", required=True, description="Loan count per stage"),
        FieldSpec("total_volume", "float", required=False, description="Total loan volume"),
        FieldSpec("avg_days_in_pipeline", "float", required=False),
        FieldSpec("conversion_rate", "float", required=False),
    ),
    idempotent=True,
    expected_latency_max_ms=2000.0,
)

GET_LOANS_BY_STATUS_CONTRACT = ToolContract(
    tool_name="get_loans_by_status",
    description="Get loans filtered by pipeline stage",
    input_fields=(
        FieldSpec("status", "str", required=True, description="Pipeline stage to filter"),
        FieldSpec("lo_id", "str", required=False),
    ),
    output_fields=(
        FieldSpec("loans", "list", required=True, items_type="dict"),
        FieldSpec("count", "int", required=True),
    ),
    idempotent=True,
)

# ---------------------------------------------------------------------------
# Lead tool contracts
# ---------------------------------------------------------------------------

GET_LEAD_DETAILS_CONTRACT = ToolContract(
    tool_name="get_lead_details",
    description="Get detailed information about a specific lead",
    input_fields=(
        FieldSpec("lead_id", "str", required=True, description="Lead ID to look up"),
    ),
    output_fields=(
        FieldSpec("id", "int", required=True),
        FieldSpec("first_name", "str", required=False),
        FieldSpec("last_name", "str", required=False),
        FieldSpec("email", "str", required=False),
        FieldSpec("stage", "str", required=False),
        FieldSpec("source", "str", required=False),
    ),
    idempotent=True,
    expected_latency_max_ms=1000.0,
)

SCORE_LEAD_CONTRACT = ToolContract(
    tool_name="score_lead",
    description="Calculate engagement/qualification score for a lead",
    input_fields=(
        FieldSpec("lead_id", "str", required=True),
    ),
    output_fields=(
        FieldSpec("score", "float", required=True, description="Score 0-100"),
        FieldSpec("factors", "list", required=False, description="Scoring factors"),
        FieldSpec("recommendation", "str", required=False),
    ),
    idempotent=True,
)

# ---------------------------------------------------------------------------
# Rate / Calculator contracts
# ---------------------------------------------------------------------------

GET_CURRENT_RATES_CONTRACT = ToolContract(
    tool_name="get_current_rates",
    description="Get current mortgage interest rates",
    input_fields=(
        FieldSpec("loan_type", "str", required=False, description="FHA, VA, Conv, etc."),
    ),
    output_fields=(
        FieldSpec("rates", "list", required=True, items_type="dict"),
        FieldSpec("as_of", "str", required=False, description="Rate date"),
        FieldSpec("source", "str", required=False),
    ),
    idempotent=True,
    expected_latency_max_ms=3000.0,
)

COMPARE_RATE_SCENARIOS_CONTRACT = ToolContract(
    tool_name="compare_rate_scenarios",
    description="Compare multiple rate lock scenarios",
    input_fields=(
        FieldSpec("loan_amount", "float", required=True),
        FieldSpec("scenarios", "list", required=False, description="List of scenario dicts"),
    ),
    output_fields=(
        FieldSpec("scenarios", "list", required=True, items_type="dict"),
        FieldSpec("recommendation", "str", required=False),
    ),
    idempotent=True,
)

# ---------------------------------------------------------------------------
# Document contracts
# ---------------------------------------------------------------------------

GET_MISSING_DOCUMENTS_CONTRACT = ToolContract(
    tool_name="get_missing_documents",
    description="Get list of outstanding/missing documents for a loan",
    input_fields=(
        FieldSpec("loan_id", "str", required=True),
    ),
    output_fields=(
        FieldSpec("documents", "list", required=True, items_type="dict"),
        FieldSpec("count", "int", required=True),
        FieldSpec("critical_count", "int", required=False),
    ),
    idempotent=True,
)

# ---------------------------------------------------------------------------
# Compliance contracts
# ---------------------------------------------------------------------------

CHECK_TRID_COMPLIANCE_CONTRACT = ToolContract(
    tool_name="check_trid_compliance",
    description="Check TRID timeline compliance for a loan",
    input_fields=(
        FieldSpec("loan_id", "str", required=True),
    ),
    output_fields=(
        FieldSpec("compliant", "bool", required=True),
        FieldSpec("violations", "list", required=False, items_type="dict"),
        FieldSpec("deadlines", "dict", required=False),
        FieldSpec("days_remaining", "int", required=False),
    ),
    idempotent=True,
    risk_level="high",
)

AUDIT_LOAN_FILE_CONTRACT = ToolContract(
    tool_name="audit_loan_file",
    description="Full compliance audit of a loan file",
    input_fields=(
        FieldSpec("loan_id", "str", required=True),
    ),
    output_fields=(
        FieldSpec("score", "float", required=True, description="Audit score 0-100"),
        FieldSpec("findings", "list", required=True, items_type="dict"),
        FieldSpec("critical_issues", "int", required=False),
    ),
    idempotent=True,
    risk_level="high",
    expected_latency_max_ms=5000.0,
)

# ---------------------------------------------------------------------------
# Communication contracts
# ---------------------------------------------------------------------------

SEND_EMAIL_CONTRACT = ToolContract(
    tool_name="send_email",
    description="Send an email to a contact",
    input_fields=(
        FieldSpec("to", "str", required=True, description="Recipient email"),
        FieldSpec("subject", "str", required=True),
        FieldSpec("body", "str", required=True),
        FieldSpec("loan_id", "str", required=False),
    ),
    output_fields=(
        FieldSpec("success", "bool", required=True),
        FieldSpec("message_id", "str", required=False),
        FieldSpec("error", "str", required=False),
    ),
    idempotent=False,
    risk_level="medium",
)

CREATE_TASK_CONTRACT = ToolContract(
    tool_name="create_task",
    description="Create a new task",
    input_fields=(
        FieldSpec("title", "str", required=True),
        FieldSpec("description", "str", required=False),
        FieldSpec("due_date", "str", required=False),
        FieldSpec("assigned_to", "str", required=False),
        FieldSpec("priority", "str", required=False),
    ),
    output_fields=(
        FieldSpec("success", "bool", required=True),
        FieldSpec("task_id", "int", required=False),
        FieldSpec("message", "str", required=False),
    ),
    idempotent=False,
    risk_level="low",
)

SEND_SMS_CONTRACT = ToolContract(
    tool_name="send_sms_message",
    description="Send an SMS message to a contact",
    input_fields=(
        FieldSpec("to", "str", required=True, description="Recipient phone number"),
        FieldSpec("message", "str", required=True),
    ),
    output_fields=(
        FieldSpec("success", "bool", required=True),
        FieldSpec("message_id", "str", required=False),
        FieldSpec("error", "str", required=False),
    ),
    idempotent=False,
    risk_level="medium",
)

# ---------------------------------------------------------------------------
# SLA contracts
# ---------------------------------------------------------------------------

CHECK_SLA_STATUS_CONTRACT = ToolContract(
    tool_name="check_sla_status",
    description="Check SLA compliance for loans in pipeline",
    input_fields=(
        FieldSpec("loan_id", "str", required=False),
        FieldSpec("lo_id", "str", required=False),
    ),
    output_fields=(
        FieldSpec("compliant", "bool", required=True),
        FieldSpec("alerts", "list", required=False, items_type="dict"),
        FieldSpec("breaches", "int", required=False),
        FieldSpec("at_risk", "int", required=False),
    ),
    idempotent=True,
)

# ---------------------------------------------------------------------------
# Scheduling contracts
# ---------------------------------------------------------------------------

BOOK_APPOINTMENT_CONTRACT = ToolContract(
    tool_name="book_appointment",
    description="Book an appointment on the calendar",
    input_fields=(
        FieldSpec("start_time", "str", required=True, description="ISO datetime"),
        FieldSpec("end_time", "str", required=False),
        FieldSpec("title", "str", required=True),
        FieldSpec("attendees", "list", required=False),
    ),
    output_fields=(
        FieldSpec("success", "bool", required=True),
        FieldSpec("appointment_id", "str", required=False),
        FieldSpec("message", "str", required=False),
    ),
    idempotent=False,
    risk_level="low",
)


# =============================================================================
# CONTRACT REGISTRY
# =============================================================================

# All defined contracts, keyed by tool_name
TOOL_CONTRACTS: Dict[str, ToolContract] = {}

def _register_contracts():
    """Register all contract constants defined in this module."""
    import sys
    module = sys.modules[__name__]
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, ToolContract):
            TOOL_CONTRACTS[obj.tool_name] = obj

_register_contracts()


def get_tool_contract(tool_name: str) -> Optional[ToolContract]:
    """
    Get the expected contract for a tool.

    Args:
        tool_name: Name of the tool (e.g., "get_pipeline_metrics")

    Returns:
        ToolContract or None if no contract is defined
    """
    return TOOL_CONTRACTS.get(tool_name)


def list_contracts() -> List[str]:
    """Return list of tool names that have defined contracts."""
    return sorted(TOOL_CONTRACTS.keys())


# =============================================================================
# OUTPUT VALIDATION
# =============================================================================

_TYPE_CHECKERS: Dict[str, Callable[[Any], bool]] = {
    "str": lambda v: isinstance(v, str),
    "int": lambda v: isinstance(v, (int,)) and not isinstance(v, bool),
    "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
    "list": lambda v: isinstance(v, (list, tuple)),
    "dict": lambda v: isinstance(v, dict),
    "any": lambda v: True,
}


def validate_tool_output(
    tool_name: str,
    output: Any,
) -> Tuple[bool, List[str]]:
    """
    Validate a tool's output against its contract.

    Args:
        tool_name: Name of the tool
        output: The actual output from the tool

    Returns:
        Tuple of (is_valid, list_of_error_messages)
    """
    contract = TOOL_CONTRACTS.get(tool_name)
    if contract is None:
        return True, [f"No contract defined for '{tool_name}' -- skipping validation"]

    errors: List[str] = []

    # Handle error results (always valid structure-wise)
    if isinstance(output, dict) and output.get("error"):
        return True, []

    # Handle ToolResult objects
    if hasattr(output, "to_dict"):
        output = output.to_dict()

    # Check output type
    if contract.output_type == "dict":
        if not isinstance(output, dict):
            errors.append(
                f"Expected dict output, got {type(output).__name__}"
            )
            return False, errors
    elif contract.output_type == "list":
        if not isinstance(output, (list, tuple)):
            errors.append(
                f"Expected list output, got {type(output).__name__}"
            )
            return False, errors
        return True, []  # List outputs don't have field-level validation
    elif contract.output_type == "scalar":
        return True, []

    # Validate individual fields (only for dict outputs)
    if isinstance(output, dict):
        # Check if output is wrapped in a "data" key (ToolResult pattern)
        data = output.get("data", output)
        if isinstance(data, dict):
            check_target = data
        else:
            check_target = output

        for field_spec in contract.output_fields:
            value = check_target.get(field_spec.name)

            if value is None and field_spec.required:
                # Check if it exists in the outer dict (some tools nest differently)
                if field_spec.name not in check_target and field_spec.name not in output:
                    errors.append(
                        f"Required field '{field_spec.name}' is missing"
                    )
                continue

            if value is not None:
                checker = _TYPE_CHECKERS.get(field_spec.type)
                if checker and not checker(value):
                    errors.append(
                        f"Field '{field_spec.name}' expected type "
                        f"'{field_spec.type}', got {type(value).__name__}"
                    )

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_tool_input(
    tool_name: str,
    input_args: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """
    Validate input arguments against a tool's contract.

    Args:
        tool_name: Name of the tool
        input_args: The input arguments dict

    Returns:
        Tuple of (is_valid, list_of_error_messages)
    """
    contract = TOOL_CONTRACTS.get(tool_name)
    if contract is None:
        return True, []

    errors: List[str] = []

    for field_spec in contract.input_fields:
        value = input_args.get(field_spec.name)

        if value is None and field_spec.required:
            errors.append(f"Required input '{field_spec.name}' is missing")
            continue

        if value is not None:
            checker = _TYPE_CHECKERS.get(field_spec.type)
            if checker and not checker(value):
                errors.append(
                    f"Input '{field_spec.name}' expected type "
                    f"'{field_spec.type}', got {type(value).__name__}"
                )

    is_valid = len(errors) == 0
    return is_valid, errors


# =============================================================================
# PER-AGENT METRICS COLLECTOR
# =============================================================================

@dataclass
class ToolInvocationRecord:
    """Single tool invocation record."""
    tool_name: str
    latency_ms: float
    success: bool
    error: Optional[str] = None
    timestamp: float = field(default_factory=lambda: time.time())
    token_cost: float = 0.0  # Estimated cost in USD


@dataclass
class AgentMetrics:
    """Aggregated metrics for a single agent."""
    agent_id: str
    total_invocations: int = 0
    successful_invocations: int = 0
    failed_invocations: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0
    total_cost: float = 0.0
    tool_call_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tool_error_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    contract_violations: int = 0
    # Rolling window tracking (last N invocations for percentile)
    _recent_latencies: List[float] = field(default_factory=list)
    _window_size: int = 100

    @property
    def avg_latency_ms(self) -> float:
        if self.total_invocations == 0:
            return 0.0
        return self.total_latency_ms / self.total_invocations

    @property
    def error_rate(self) -> float:
        if self.total_invocations == 0:
            return 0.0
        return self.failed_invocations / self.total_invocations

    @property
    def p95_latency_ms(self) -> float:
        if not self._recent_latencies:
            return 0.0
        sorted_latencies = sorted(self._recent_latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    @property
    def p99_latency_ms(self) -> float:
        if not self._recent_latencies:
            return 0.0
        sorted_latencies = sorted(self._recent_latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    def record(self, record: ToolInvocationRecord) -> None:
        """Record a single tool invocation."""
        self.total_invocations += 1
        self.total_latency_ms += record.latency_ms
        self.total_cost += record.token_cost
        self.min_latency_ms = min(self.min_latency_ms, record.latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, record.latency_ms)
        self.tool_call_counts[record.tool_name] += 1

        if record.success:
            self.successful_invocations += 1
        else:
            self.failed_invocations += 1
            self.tool_error_counts[record.tool_name] += 1

        # Rolling window
        self._recent_latencies.append(record.latency_ms)
        if len(self._recent_latencies) > self._window_size:
            self._recent_latencies.pop(0)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metrics to a dict."""
        return {
            "agent_id": self.agent_id,
            "total_invocations": self.total_invocations,
            "successful_invocations": self.successful_invocations,
            "failed_invocations": self.failed_invocations,
            "error_rate": round(self.error_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "min_latency_ms": round(self.min_latency_ms, 1) if self.min_latency_ms != float("inf") else 0.0,
            "max_latency_ms": round(self.max_latency_ms, 1),
            "p95_latency_ms": round(self.p95_latency_ms, 1),
            "p99_latency_ms": round(self.p99_latency_ms, 1),
            "total_cost_usd": round(self.total_cost, 4),
            "contract_violations": self.contract_violations,
            "top_tools": dict(
                sorted(
                    self.tool_call_counts.items(),
                    key=lambda x: -x[1],
                )[:10]
            ),
            "error_tools": dict(
                sorted(
                    self.tool_error_counts.items(),
                    key=lambda x: -x[1],
                )[:5]
            ),
        }


class AgentMetricsCollector:
    """
    Thread-safe singleton that collects per-agent quality metrics.

    In production, this runs in-process. Metrics can be flushed to
    Redis/PostgreSQL on a timer if persistence is needed.
    """

    _instance: Optional["AgentMetricsCollector"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._metrics: Dict[str, AgentMetrics] = {}
        self._metrics_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "AgentMetricsCollector":
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    def _get_or_create_metrics(self, agent_id: str) -> AgentMetrics:
        """Get or create metrics for an agent (NOT thread-safe -- caller holds lock)."""
        if agent_id not in self._metrics:
            self._metrics[agent_id] = AgentMetrics(agent_id=agent_id)
        return self._metrics[agent_id]

    def record_invocation(
        self,
        agent_id: str,
        tool_name: str,
        latency_ms: float,
        success: bool = True,
        error: Optional[str] = None,
        token_cost: float = 0.0,
        output: Any = None,
    ) -> None:
        """
        Record a tool invocation for an agent.

        Args:
            agent_id: Consolidated or legacy agent ID
            tool_name: Name of the tool that was called
            latency_ms: Execution time in milliseconds
            success: Whether the tool call succeeded
            error: Error message if failed
            token_cost: Estimated LLM token cost in USD
            output: Tool output (for contract validation)
        """
        record = ToolInvocationRecord(
            tool_name=tool_name,
            latency_ms=latency_ms,
            success=success,
            error=error,
            token_cost=token_cost,
        )

        with self._metrics_lock:
            metrics = self._get_or_create_metrics(agent_id)
            metrics.record(record)

            # Optional contract validation
            if output is not None and success:
                is_valid, errors = validate_tool_output(tool_name, output)
                if not is_valid:
                    metrics.contract_violations += 1
                    logger.warning(
                        f"[QUALITY] Contract violation for {agent_id}/{tool_name}: "
                        f"{'; '.join(errors)}"
                    )

    def get_agent_metrics(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metrics for a specific agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Metrics dict or None if no data
        """
        with self._metrics_lock:
            metrics = self._metrics.get(agent_id)
            if metrics is None:
                return None
            return metrics.to_dict()

    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics for all agents that have recorded invocations."""
        with self._metrics_lock:
            return {
                agent_id: metrics.to_dict()
                for agent_id, metrics in self._metrics.items()
            }

    def get_summary(self) -> Dict[str, Any]:
        """Get a high-level summary across all agents."""
        with self._metrics_lock:
            total_invocations = sum(m.total_invocations for m in self._metrics.values())
            total_errors = sum(m.failed_invocations for m in self._metrics.values())
            total_cost = sum(m.total_cost for m in self._metrics.values())
            total_violations = sum(m.contract_violations for m in self._metrics.values())

            # Find worst error rate
            worst_agent = None
            worst_error_rate = 0.0
            for m in self._metrics.values():
                if m.total_invocations >= 10 and m.error_rate > worst_error_rate:
                    worst_error_rate = m.error_rate
                    worst_agent = m.agent_id

            # Find slowest agent
            slowest_agent = None
            slowest_latency = 0.0
            for m in self._metrics.values():
                if m.total_invocations >= 10 and m.avg_latency_ms > slowest_latency:
                    slowest_latency = m.avg_latency_ms
                    slowest_agent = m.agent_id

            return {
                "total_agents_tracked": len(self._metrics),
                "total_invocations": total_invocations,
                "total_errors": total_errors,
                "overall_error_rate": (
                    round(total_errors / total_invocations, 4)
                    if total_invocations > 0 else 0.0
                ),
                "total_cost_usd": round(total_cost, 4),
                "total_contract_violations": total_violations,
                "worst_error_rate_agent": worst_agent,
                "worst_error_rate": round(worst_error_rate, 4),
                "slowest_agent": slowest_agent,
                "slowest_avg_latency_ms": round(slowest_latency, 1),
            }


# =============================================================================
# QUALITY GATE: Pre-flight check before agent invocation
# =============================================================================

def preflight_check(
    agent_id: str,
    tool_name: str,
    input_args: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """
    Run pre-flight validation before invoking a tool.

    Checks:
    1. Tool has a defined contract
    2. Input args match contract
    3. Agent error rate is below threshold

    Args:
        agent_id: The agent requesting the tool
        tool_name: Tool to invoke
        input_args: Arguments to pass

    Returns:
        (should_proceed, warnings)
    """
    warnings: List[str] = []

    # Validate input
    input_valid, input_errors = validate_tool_input(tool_name, input_args)
    if not input_valid:
        warnings.extend(input_errors)

    # Check agent health
    collector = AgentMetricsCollector.get_instance()
    metrics = collector.get_agent_metrics(agent_id)
    if metrics is not None:
        error_rate = metrics.get("error_rate", 0)
        if error_rate > 0.5:
            warnings.append(
                f"Agent '{agent_id}' has high error rate ({error_rate:.0%}). "
                f"Consider fallback."
            )

        # Check tool-specific errors
        error_tools = metrics.get("error_tools", {})
        tool_errors = error_tools.get(tool_name, 0)
        total_tool_calls = metrics.get("top_tools", {}).get(tool_name, 0)
        if total_tool_calls > 5 and tool_errors / total_tool_calls > 0.3:
            warnings.append(
                f"Tool '{tool_name}' has high failure rate for agent '{agent_id}'"
            )

    # Input validation failures are advisory, not blocking
    should_proceed = True
    return should_proceed, warnings
