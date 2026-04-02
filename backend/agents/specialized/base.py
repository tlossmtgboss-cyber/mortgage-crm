"""
Base Classes for Specialized Agents

Provides the foundation for all specialized AI agents with
common functionality and tool registration patterns.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, TypedDict
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import time
import logging
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# AGENT METRICS (lightweight in-memory tracking)
# =============================================================================

@dataclass
class AgentMetrics:
    """Lightweight per-agent metrics tracker."""
    total_calls: int = 0
    success_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.total_calls if self.total_calls > 0 else 0.0

    @property
    def error_rate(self) -> float:
        return self.error_count / self.total_calls if self.total_calls > 0 else 0.0

    def record_success(self, latency_ms: float):
        self.total_calls += 1
        self.success_count += 1
        self.total_latency_ms += latency_ms
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        self.consecutive_failures = 0

    def record_error(self, latency_ms: float, error: str):
        self.total_calls += 1
        self.error_count += 1
        self.total_latency_ms += latency_ms
        self.consecutive_failures += 1
        self.last_error = error
        self.last_error_time = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "max_latency_ms": round(self.max_latency_ms, 1),
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
        }


# Circuit breaker constants
CIRCUIT_BREAKER_THRESHOLD = 5  # consecutive failures before tripping
CIRCUIT_BREAKER_RESET_SECONDS = 60  # seconds before allowing retry


class ToolCategory(str, Enum):
    """Categories for organizing agent tools"""
    QUERY = "query"           # Read-only data retrieval
    ACTION = "action"         # Write operations that change state
    ANALYSIS = "analysis"     # Complex analysis operations
    COMMUNICATION = "communication"  # External communications
    WORKFLOW = "workflow"     # Process and workflow management


class RiskLevel(str, Enum):
    """Risk levels for autonomous execution"""
    LOW = "low"          # Safe to auto-execute
    MEDIUM = "medium"    # Requires review for new users
    HIGH = "high"        # Always requires confirmation
    CRITICAL = "critical"  # Requires explicit user approval


@dataclass
class ToolResult:
    """Standardized result from tool execution"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "message": self.message,
            "metadata": self.metadata
        }


@dataclass
class AgentTool:
    """Definition for an agent tool"""
    name: str
    description: str
    category: ToolCategory
    risk_level: RiskLevel
    handler: Callable
    input_schema: Optional[type] = None  # Pydantic model for inputs
    requires_confirmation: bool = False
    cooldown_seconds: int = 0
    max_per_hour: Optional[int] = None

    def to_langchain_tool(self) -> StructuredTool:
        """Convert to LangChain StructuredTool"""
        return StructuredTool.from_function(
            func=self.handler,
            name=self.name,
            description=self.description,
            args_schema=self.input_schema
        )


class AgentContext(TypedDict, total=False):
    """Context passed to agent operations"""
    user_id: str
    user_email: str
    user_role: str
    organization_id: str
    db_session: Any
    current_time: datetime
    conversation_id: Optional[str]
    autonomous_mode: bool
    permissions: List[str]


class SpecializedAgent(ABC):
    """
    Base class for all specialized AI agents.

    Each specialized agent:
    - Manages a specific domain (leads, loans, tasks, etc.)
    - Provides a set of tools for that domain
    - Handles context and permissions
    - Supports autonomous or supervised operation
    """

    def __init__(self, context: AgentContext):
        """
        Initialize the specialized agent.

        Args:
            context: Agent execution context with user info and DB session
        """
        self.context = context
        self._tools: Dict[str, AgentTool] = {}
        self._tool_usage_counts: Dict[str, int] = {}
        self._last_tool_use: Dict[str, datetime] = {}
        self._metrics: Dict[str, AgentMetrics] = {}  # per-tool metrics
        self._agent_metrics = AgentMetrics()  # aggregate agent metrics

        # Register agent-specific tools
        self._register_tools()

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name for identification"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Agent description for routing"""
        pass

    @property
    def tools(self) -> Dict[str, AgentTool]:
        """Get all registered tools"""
        return self._tools

    @abstractmethod
    def _register_tools(self):
        """Register agent-specific tools. Override in subclasses."""
        pass

    def register_tool(self, tool: AgentTool):
        """Register a tool with the agent"""
        self._tools[tool.name] = tool
        self._tool_usage_counts[tool.name] = 0
        logger.debug(f"Registered tool: {tool.name} for agent: {self.name}")

    def get_tool(self, name: str) -> Optional[AgentTool]:
        """Get a tool by name"""
        return self._tools.get(name)

    def get_tools_by_category(self, category: ToolCategory) -> List[AgentTool]:
        """Get all tools in a category"""
        return [t for t in self._tools.values() if t.category == category]

    def get_safe_tools(self) -> List[AgentTool]:
        """Get tools safe for autonomous execution"""
        return [
            t for t in self._tools.values()
            if t.risk_level == RiskLevel.LOW and not t.requires_confirmation
        ]

    # =========================================================================
    # TENANT ISOLATION HELPERS
    # =========================================================================

    def require_org_id(self) -> str:
        """Get organization_id from context, raising if missing.

        Every data-access tool MUST call this to enforce tenant isolation.
        """
        org_id = self.context.get("organization_id")
        if not org_id:
            raise ValueError(
                f"Agent '{self.name}' requires organization_id in context for tenant isolation"
            )
        return org_id

    def org_filter_sql(self, table_alias: str = "") -> str:
        """Return a SQL WHERE fragment for tenant isolation.

        Usage: f"SELECT ... WHERE {self.org_filter_sql('l')} AND ..."
        """
        prefix = f"{table_alias}." if table_alias else ""
        return f"{prefix}organization_id = :org_id"

    def org_filter_params(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return params dict with org_id set, merged with extras."""
        params: Dict[str, Any] = {"org_id": self.require_org_id()}
        if extra:
            params.update(extra)
        return params

    def verify_loan_tenant(self, db: Any, loan_id: int) -> None:
        """Verify a loan belongs to this agent's organization.

        Raises ValueError if the loan does not exist or belongs to a
        different organization.  The error message intentionally omits
        organization identifiers to prevent information leakage.
        """
        from sqlalchemy import text as _text

        org_id = self.require_org_id()
        row = db.execute(
            _text(
                "SELECT id FROM loans "
                "WHERE id = :loan_id AND organization_id = :org_id"
            ),
            {"loan_id": loan_id, "org_id": org_id},
        ).fetchone()
        if not row:
            logger.warning(
                "TENANT_ISOLATION: loan %s access denied for org %s by agent %s",
                loan_id, org_id, self.name,
            )
            raise ValueError(f"Loan {loan_id} not found")

    def verify_document_tenant(self, db: Any, document_id: int) -> None:
        """Verify a smart_document belongs to this agent's organization
        (via its parent loan).

        Raises ValueError if the document does not exist or belongs to a
        different organization.
        """
        from sqlalchemy import text as _text

        org_id = self.require_org_id()
        row = db.execute(
            _text(
                "SELECT sd.id FROM smart_documents sd "
                "JOIN loans l ON l.id = sd.loan_id AND l.organization_id = :org_id "
                "WHERE sd.id = :document_id"
            ),
            {"document_id": document_id, "org_id": org_id},
        ).fetchone()
        if not row:
            logger.warning(
                "TENANT_ISOLATION: document %s access denied for org %s by agent %s",
                document_id, org_id, self.name,
            )
            raise ValueError(f"Document {document_id} not found")

    def verify_entity_tenant(
        self, db: Any, table: str, entity_id: int,
        org_column: str = "organization_id",
    ) -> None:
        """Generic tenant verification for any table with an org column.

        Args:
            db: SQLAlchemy session
            table: Table name (must be an expected safe value)
            entity_id: Primary key value
            org_column: Name of the organization column (default: organization_id)

        Raises ValueError if the entity does not exist or belongs to a
        different organization.
        """
        from sqlalchemy import text as _text

        # Allowlist of tables to prevent SQL injection via table name
        ALLOWED_TABLES = {
            "loans", "leads", "smart_documents", "followup_campaigns",
            "smart_document_requests", "income_calculations",
            "bank_statement_analyses", "compliance_alerts",
            "documents", "tasks", "activities",
        }
        if table not in ALLOWED_TABLES:
            raise ValueError(f"Table '{table}' is not allowed for tenant verification")

        org_id = self.require_org_id()
        row = db.execute(
            _text(
                f"SELECT id FROM {table} "
                f"WHERE id = :entity_id AND {org_column} = :org_id"
            ),
            {"entity_id": entity_id, "org_id": org_id},
        ).fetchone()
        if not row:
            logger.warning(
                "TENANT_ISOLATION: %s %s access denied for org %s by agent %s",
                table, entity_id, org_id, self.name,
            )
            raise ValueError(f"{table} entity {entity_id} not found")

    def verify_campaign_tenant(self, db: Any, campaign_id: int) -> None:
        """Verify a follow-up campaign belongs to this agent's organization
        (via its parent loan).

        Raises ValueError if the campaign does not exist or belongs to a
        different organization.
        """
        from sqlalchemy import text as _text

        org_id = self.require_org_id()
        row = db.execute(
            _text(
                "SELECT fc.id FROM followup_campaigns fc "
                "JOIN loans l ON l.id = fc.loan_id AND l.organization_id = :org_id "
                "WHERE fc.id = :campaign_id"
            ),
            {"campaign_id": campaign_id, "org_id": org_id},
        ).fetchone()
        if not row:
            logger.warning(
                "TENANT_ISOLATION: campaign %s access denied for org %s by agent %s",
                campaign_id, org_id, self.name,
            )
            raise ValueError(f"Campaign {campaign_id} not found")

    # =========================================================================
    # AUDIT LOGGING
    # =========================================================================

    def audit_log(
        self,
        action: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Log an auditable action performed by this agent.

        Writes to the standard Python logger at INFO level with structured
        metadata so log aggregators can index it.  A future enhancement can
        persist to the DB audit table.
        """
        log_entry = {
            "agent": self.name,
            "action": action,
            "user_id": self.context.get("user_id"),
            "organization_id": self.context.get("organization_id"),
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if details:
            log_entry["details"] = details
        logger.info(f"AGENT_AUDIT: {log_entry}")

    async def execute_tool(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        force_confirm: bool = False
    ) -> ToolResult:
        """
        Execute a tool with the given input.

        Args:
            tool_name: Name of the tool to execute
            input_data: Input parameters for the tool
            force_confirm: Force confirmation even for low-risk tools

        Returns:
            ToolResult with execution outcome
        """
        tool = self.get_tool(tool_name)

        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found in agent '{self.name}'"
            )

        # Circuit breaker check
        tool_metrics = self._metrics.get(tool_name)
        if tool_metrics and tool_metrics.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            if tool_metrics.last_error_time:
                elapsed = (datetime.now(timezone.utc) - tool_metrics.last_error_time).total_seconds()
                if elapsed < CIRCUIT_BREAKER_RESET_SECONDS:
                    return ToolResult(
                        success=False,
                        error="circuit_breaker_open",
                        message=f"Tool '{tool_name}' temporarily disabled after {CIRCUIT_BREAKER_THRESHOLD} consecutive failures. Retry in {int(CIRCUIT_BREAKER_RESET_SECONDS - elapsed)}s."
                    )
                else:
                    # Reset circuit breaker after cooldown
                    tool_metrics.consecutive_failures = 0

        # Check rate limits
        if not self._check_rate_limit(tool):
            return ToolResult(
                success=False,
                error=f"Rate limit exceeded for tool '{tool_name}'"
            )

        # Check if confirmation needed
        autonomous_mode = self.context.get("autonomous_mode", True)
        if force_confirm or (tool.requires_confirmation and not autonomous_mode):
            return ToolResult(
                success=False,
                error="confirmation_required",
                message=f"Tool '{tool_name}' requires user confirmation",
                metadata={"tool": tool_name, "input": input_data}
            )

        # Check risk level for autonomous execution
        if not autonomous_mode and tool.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            return ToolResult(
                success=False,
                error="approval_required",
                message=f"Tool '{tool_name}' requires approval for risk level: {tool.risk_level.value}",
                metadata={"tool": tool_name, "risk_level": tool.risk_level.value}
            )

        # Initialize per-tool metrics if needed
        if tool_name not in self._metrics:
            self._metrics[tool_name] = AgentMetrics()

        start_time = time.time()
        try:
            # Execute the tool handler
            result = await tool.handler(input_data, self.context)

            latency_ms = (time.time() - start_time) * 1000

            # Update usage tracking
            self._tool_usage_counts[tool_name] += 1
            self._last_tool_use[tool_name] = datetime.now(timezone.utc)

            # Wrap raw result if needed
            if isinstance(result, ToolResult):
                tool_result = result
            elif isinstance(result, dict):
                tool_result = ToolResult(
                    success=result.get("success", True),
                    data=result.get("data", result),
                    error=result.get("error"),
                    message=result.get("message")
                )
            else:
                tool_result = ToolResult(success=True, data={"result": result})

            # Record metrics
            if tool_result.success:
                self._metrics[tool_name].record_success(latency_ms)
                self._agent_metrics.record_success(latency_ms)
            else:
                self._metrics[tool_name].record_error(latency_ms, tool_result.error or "unknown")
                self._agent_metrics.record_error(latency_ms, tool_result.error or "unknown")

            return tool_result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            self._metrics[tool_name].record_error(latency_ms, str(e))
            self._agent_metrics.record_error(latency_ms, str(e))
            logger.error(f"Tool execution failed: {tool_name} - {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e),
                message=f"Tool '{tool_name}' execution failed"
            )

    def _check_rate_limit(self, tool: AgentTool) -> bool:
        """Check if tool execution is within rate limits"""
        now = datetime.now(timezone.utc)

        # Check cooldown
        if tool.cooldown_seconds > 0:
            last_use = self._last_tool_use.get(tool.name)
            if last_use:
                elapsed = (now - last_use).total_seconds()
                if elapsed < tool.cooldown_seconds:
                    return False

        # Check hourly limit
        if tool.max_per_hour:
            count = self._tool_usage_counts.get(tool.name, 0)
            if count >= tool.max_per_hour:
                # Reset if hour has passed (simplified - in production use proper windowing)
                return False

        return True

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions for LLM function calling"""
        definitions = []
        for tool in self._tools.values():
            definition = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }

            # Add input schema if provided
            if tool.input_schema and hasattr(tool.input_schema, "model_json_schema"):
                schema = tool.input_schema.model_json_schema()
                definition["function"]["parameters"] = schema

            definitions.append(definition)

        return definitions

    def get_langchain_tools(self) -> List[StructuredTool]:
        """Get all tools as LangChain StructuredTools"""
        return [tool.to_langchain_tool() for tool in self._tools.values()]


class AgentRegistry:
    """
    Registry for all specialized agents.

    Provides agent discovery and routing based on query intent.
    """

    _agents: Dict[str, type] = {}

    @classmethod
    def register(cls, agent_class: type):
        """Register an agent class"""
        cls._agents[agent_class.__name__] = agent_class
        return agent_class

    @classmethod
    def get_agent(cls, name: str, context: AgentContext) -> Optional[SpecializedAgent]:
        """Get an instantiated agent by name"""
        agent_class = cls._agents.get(name)
        if agent_class:
            return agent_class(context)
        return None

    @classmethod
    def get_all_agents(cls, context: AgentContext) -> List[SpecializedAgent]:
        """Get all instantiated agents"""
        return [agent_class(context) for agent_class in cls._agents.values()]

    @classmethod
    def get_agent_for_intent(
        cls,
        intent: str,
        context: AgentContext
    ) -> Optional[SpecializedAgent]:
        """Get the most appropriate agent for a given intent.

        Only OpsManagerAgent is currently active. Returns None for
        intents that don't match a registered agent.
        """
        intent_mapping = {
            "ops manager": "OpsManagerAgent",
            "operations manager": "OpsManagerAgent",
            "pipeline sweep": "OpsManagerAgent",
            "impediment": "OpsManagerAgent",
            "team gap": "OpsManagerAgent",
            "stalled file": "OpsManagerAgent",
            "missing processor": "OpsManagerAgent",
            "missing closer": "OpsManagerAgent",
            "unassigned lead": "OpsManagerAgent",
            "unassigned loan": "OpsManagerAgent",
        }

        intent_lower = intent.lower()
        for keyword, agent_name in intent_mapping.items():
            if keyword in intent_lower:
                return cls.get_agent(agent_name, context)

        return None
