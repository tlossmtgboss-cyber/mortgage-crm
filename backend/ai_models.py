"""
AI Architecture Models
Mortgage OS: AMAS → Self-Improving → Cognitive → EDWs → AAIO
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class AgentType(str, Enum):
    SPECIALIZED = "specialized"
    META = "meta"
    LEADERSHIP = "leadership"


class AgentStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ToolCategory(str, Enum):
    DATA_READ = "data_read"
    DATA_WRITE = "data_write"
    COMMUNICATION = "communication"
    ANALYSIS = "analysis"
    WORKFLOW = "workflow"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EventStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    ESCALATION = "escalation"


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    TIMEOUT = "timeout"


class FindingType(str, Enum):
    BOTTLENECK = "bottleneck"
    PROMPT_ISSUE = "prompt_issue"
    MISSING_TOOL = "missing_tool"
    SCHEMA_CHANGE = "schema_change"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# PHASE 1: AGENT & TOOL DEFINITIONS
# ============================================================================

class AgentConfig(BaseModel):
    """Agent configuration"""
    id: str
    name: str
    description: str
    agent_type: AgentType
    status: AgentStatus = AgentStatus.ACTIVE
    goals: List[str] = []
    tools: List[str] = []  # Tool names from ToolRegistry
    triggers: List[str] = []  # Event types
    config: Dict[str, Any] = {}
    version: int = 1
    manager_user_id: Optional[int] = None


class ToolDefinition(BaseModel):
    """Tool definition with schema"""
    name: str
    description: str
    category: ToolCategory
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    handler_endpoint: str
    allowed_agents: List[str] = []
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    is_active: bool = True


class AgentEvent(BaseModel):
    """Event that triggers agent execution"""
    event_id: str
    event_type: str
    source: str  # 'system', 'user', 'webhook', 'agent'
    source_agent_id: Optional[str] = None
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = {}
    status: EventStatus = EventStatus.PENDING


class AgentMessage(BaseModel):
    """Message between agents"""
    message_id: str
    from_agent_id: Optional[str] = None
    to_agent_id: Optional[str] = None
    message_type: MessageType
    subject: str
    content: str
    payload: Dict[str, Any] = {}
    priority: Priority = Priority.NORMAL
    requires_human_review: bool = False
    parent_message_id: Optional[int] = None


class AgentExecution(BaseModel):
    """Log of agent action"""
    execution_id: str
    agent_id: str
    event_id: Optional[str] = None
    tool_name: Optional[str] = None
    input: Dict[str, Any]
    output: Optional[Dict[str, Any]] = None
    status: ExecutionStatus
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None
    confidence_score: Optional[float] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


class ToolContext(BaseModel):
    """Context passed to tool handlers"""
    agent_id: str
    execution_id: str
    user_id: Optional[int] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


# ============================================================================
# PHASE 2: SELF-IMPROVEMENT
# ============================================================================

class PromptVersion(BaseModel):
    """Versioned agent prompt"""
    agent_id: str
    version: int
    prompt_text: str
    system_instructions: Optional[str] = None
    tool_selection_strategy: Dict[str, Any] = {}
    routing_rules: Dict[str, Any] = {}
    status: str = "draft"  # 'draft', 'testing', 'active', 'archived'
    performance_metrics: Dict[str, Any] = {}


class AuditFinding(BaseModel):
    """AI-generated improvement proposal"""
    finding_id: str
    finding_type: FindingType
    severity: Severity
    title: str
    description: str
    affected_agent_id: Optional[str] = None
    affected_tool_name: Optional[str] = None
    evidence: Dict[str, Any] = {}
    proposed_solution: str
    proposed_changes: Dict[str, Any] = {}
    estimated_impact: str
    status: str = "pending"


class ImprovementCycle(BaseModel):
    """Self-improvement iteration"""
    cycle_id: str
    start_date: datetime
    end_date: datetime
    findings_count: int = 0
    approved_count: int = 0
    implemented_count: int = 0
    performance_delta: Dict[str, Any] = {}
    summary: Optional[str] = None


# ============================================================================
# PHASE 3: COGNITIVE ARCHITECTURE
# ============================================================================

class LongTermMemory(BaseModel):
    """AI knowledge storage"""
    memory_id: str
    memory_type: str  # 'experience', 'fact', 'pattern', 'reflection', 'sop'
    agent_id: Optional[str] = None
    title: Optional[str] = None
    content: str
    entities: Dict[str, Any] = {}
    tags: List[str] = []
    confidence: Optional[float] = None
    relevance_score: Optional[float] = None


class KnowledgeNode(BaseModel):
    """Knowledge graph node"""
    node_id: str
    node_type: str  # 'lead', 'borrower', 'loan', 'property', 'agent', 'builder'
    entity_id: str
    label: Optional[str] = None
    properties: Dict[str, Any] = {}


class KnowledgeEdge(BaseModel):
    """Knowledge graph relationship"""
    edge_id: str
    source_node_id: str
    target_node_id: str
    relationship_type: str  # 'referred_by', 'owns', 'applied_for'
    properties: Dict[str, Any] = {}
    weight: float = 1.0


class Reflection(BaseModel):
    """AI self-analysis"""
    reflection_id: str
    agent_id: str
    execution_id: Optional[str] = None
    workflow_name: Optional[str] = None
    what_worked: Optional[str] = None
    what_failed: Optional[str] = None
    what_to_change: Optional[str] = None
    lessons_learned: Dict[str, Any] = {}


class ContextPacket(BaseModel):
    """Working memory context"""
    goal: str
    entity_type: str
    entity_id: str
    entity_data: Dict[str, Any]
    related_tasks: List[Dict[str, Any]] = []
    recent_communications: List[Dict[str, Any]] = []
    graph_neighbors: List[Dict[str, Any]] = []
    prior_ai_actions: List[Dict[str, Any]] = []
    relevant_memories: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}


# ============================================================================
# PHASE 4: DIGITAL WORKERS
# ============================================================================

class WorkerKPI(BaseModel):
    """Digital worker KPI"""
    kpi_name: str
    kpi_target: float
    kpi_unit: str  # 'count', 'percent', 'time_minutes', 'dollar'
    current_value: Optional[float] = None
    status: Optional[str] = None  # 'on_track', 'at_risk', 'missed', 'exceeded'


class DigitalWorkerProfile(BaseModel):
    """Enterprise Digital Worker profile"""
    worker_id: str
    agent_id: str
    job_title: str
    department: Optional[str] = None
    manager_user_id: Optional[int] = None
    responsibilities: List[str] = []
    permissions: List[str] = []
    status: str = "active"
    kpis: List[WorkerKPI] = []


class WorkerReport(BaseModel):
    """Digital worker performance report"""
    report_id: str
    worker_id: str
    report_type: str  # 'daily', 'weekly', 'monthly'
    report_period_start: datetime
    report_period_end: datetime
    summary: str
    accomplishments: List[Dict[str, Any]] = []
    challenges: List[Dict[str, Any]] = []
    escalations: List[Dict[str, Any]] = []
    kpi_performance: Dict[str, Any] = {}
    next_priorities: List[str] = []


# ============================================================================
# PHASE 5: AI ORGANIZATION
# ============================================================================

class LeadershipRole(BaseModel):
    """AI leadership position"""
    role_id: str
    agent_id: str
    title: str  # 'AI COO', 'AI CCO', 'AI CRO'
    department: str
    scope: List[str] = []
    managed_workers: List[str] = []
    decision_authority: str = "advisory"  # 'advisory', 'limited', 'full'


class StrategicInitiative(BaseModel):
    """AI-proposed business strategy"""
    initiative_id: str
    proposed_by_agent_id: str
    title: str
    description: str
    category: str  # 'efficiency', 'revenue', 'customer_experience'
    priority: Priority = Priority.MEDIUM
    estimated_impact: Dict[str, Any] = {}
    resources_required: Dict[str, Any] = {}
    timeline: Dict[str, Any] = {}
    status: str = "proposed"


class SystemHealth(BaseModel):
    """Overall AI org health"""
    snapshot_id: str
    snapshot_date: datetime
    overall_status: str  # 'healthy', 'degraded', 'critical'
    total_agents: int
    active_agents: int
    total_executions: int
    success_rate: float
    avg_response_time_ms: int
    total_cost_usd: float
    kpis_on_track: int
    kpis_at_risk: int
    open_escalations: int
    agent_metrics: Dict[str, Any] = {}
    leadership_summary: Optional[str] = None
    recommendations: List[str] = []


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ExecuteAgentRequest(BaseModel):
    """Request to execute an agent"""
    agent_id: str
    event_type: str
    payload: Dict[str, Any]
    user_id: Optional[int] = None


class ExecuteAgentResponse(BaseModel):
    """Response from agent execution"""
    execution_id: str
    status: ExecutionStatus
    output: Optional[Dict[str, Any]] = None
    messages: List[AgentMessage] = []
    requires_approval: bool = False
    confidence_score: Optional[float] = None


class SendMessageRequest(BaseModel):
    """Request to send inter-agent message"""
    from_agent_id: str
    to_agent_id: Optional[str] = None  # None for broadcast
    message_type: MessageType
    subject: str
    content: str
    payload: Dict[str, Any] = {}
    priority: Priority = Priority.NORMAL


class ProvideExecutionFeedbackRequest(BaseModel):
    """User feedback on agent execution"""
    execution_id: str
    feedback: str  # 'positive', 'negative', 'neutral'
    comment: Optional[str] = None
    user_id: int


class ApproveAuditFindingRequest(BaseModel):
    """Approve/reject improvement proposal"""
    finding_id: str
    approved: bool
    review_notes: Optional[str] = None
    reviewer_id: int


class CreatePromptVersionRequest(BaseModel):
    """Create new prompt version"""
    agent_id: str
    prompt_text: str
    system_instructions: Optional[str] = None
    tool_selection_strategy: Dict[str, Any] = {}
    created_by: int


# ============================================================================
# AGENT PLAN & STEP MODELS
# ============================================================================

class AgentPlanStep(BaseModel):
    """Single step in multi-step plan"""
    step_number: int
    action: str
    tool_name: Optional[str] = None
    input_params: Dict[str, Any] = {}
    expected_output: Optional[str] = None
    success_criteria: Optional[str] = None
    status: str = "pending"  # 'pending', 'running', 'success', 'failed'


class AgentPlan(BaseModel):
    """Multi-step plan for complex workflow"""
    plan_id: str
    agent_id: str
    goal: str
    steps: List[AgentPlanStep]
    current_step: int = 0
    status: str = "pending"
    context: Dict[str, Any] = {}
