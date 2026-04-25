"""
Agent Governance System Models

SQLAlchemy models for the Agent Governance & Management System.
Enables tracking of:
- Agent profiles and configuration
- Execution audit trails
- Gym testing scenarios and results
- Alerts and notifications
- Time-series metrics
- Chat sessions and messages

Tables defined:
- AgentProfile: Agent metadata, status, config
- AgentTool: Tool registry per agent
- AgentExecution: Execution audit trail
- GymTestScenario: Test case definitions
- GymTestRun: Test execution records
- GymTestResult: Per-scenario results
- AgentAlert: Alerts and notifications
- AgentMetricsTimeseries: Time-series metrics
- AgentChatSession: Chat session tracking
- AgentChatMessage: Chat message history
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
import enum
import uuid

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    Numeric, Index, CheckConstraint, UniqueConstraint, Float
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func

from database import Base


# =============================================================================
# ENUM DEFINITIONS
# =============================================================================

class AgentStatus(str, enum.Enum):
    """Agent operational status"""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    MAINTENANCE = "maintenance"


class HealthStatus(str, enum.Enum):
    """Agent health status"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class RiskTier(str, enum.Enum):
    """Agent risk tier classification"""
    TIER_1 = "1"  # High risk - requires approval
    TIER_2 = "2"  # Medium risk - requires review
    TIER_3 = "3"  # Low risk - autonomous operation


class ExecutionStatus(str, enum.Enum):
    """Agent execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class AlertSeverity(str, enum.Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, enum.Enum):
    """Alert status"""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SNOOZED = "snoozed"


class TestStatus(str, enum.Enum):
    """Gym test status"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class ToolCategory(str, enum.Enum):
    """Tool category types"""
    QUERY = "query"
    ACTION = "action"
    ANALYSIS = "analysis"
    COMMUNICATION = "communication"
    WORKFLOW = "workflow"


class ToolRiskLevel(str, enum.Enum):
    """Tool risk levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# =============================================================================
# AGENT PROFILE MODEL
# =============================================================================

class AgentProfile(Base):
    """
    Agent profile with metadata, status, and configuration.

    Tracks agent health, metrics, and governance settings.
    """
    __tablename__ = "agent_profiles"
    __table_args__ = (
        Index('ix_agent_profiles_status', 'status'),
        Index('ix_agent_profiles_category', 'category'),
        Index('ix_agent_profiles_health', 'health_status'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # Multi-tenant isolation
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)

    # Agent identification
    agent_name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200))
    description = Column(Text)
    category = Column(String(50))  # core_crm, extended, custom
    version = Column(String(20), default='1.0.0')

    # Status
    status = Column(String(20), nullable=False, default='active')
    health_status = Column(String(20), default='unknown')

    # Tool configuration
    tool_count = Column(Integer, default=0)

    # Governance
    risk_tier = Column(String(10), default='2')
    elite_status = Column(Boolean, default=False)
    requires_approval = Column(Boolean, default=False)
    approval_threshold = Column(Float, default=0.95)

    # Configuration
    config = Column(JSONB, default=dict)

    # Metrics snapshot (updated periodically)
    total_executions = Column(Integer, default=0)
    successful_executions = Column(Integer, default=0)
    failed_executions = Column(Integer, default=0)
    avg_response_time_ms = Column(Float, default=0)
    success_rate = Column(Float, default=0)

    # Cost tracking
    total_cost = Column(Numeric(12, 4), default=0)
    cost_this_month = Column(Numeric(12, 4), default=0)

    # Timestamps
    last_execution_at = Column(DateTime(timezone=True))
    last_health_check = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    tools = relationship("AgentTool", back_populates="agent", cascade="all, delete-orphan")
    executions = relationship("AgentExecution", back_populates="agent", cascade="all, delete-orphan")
    alerts = relationship("AgentAlert", back_populates="agent", cascade="all, delete-orphan")
    metrics = relationship("AgentMetricsTimeseries", back_populates="agent", cascade="all, delete-orphan")
    chat_sessions = relationship("AgentChatSession", back_populates="agent", cascade="all, delete-orphan")
    gym_scenarios = relationship("GymTestScenario", back_populates="agent", cascade="all, delete-orphan")
    training_sessions = relationship("TrainingSession", back_populates="agent", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
            "version": self.version,
            "status": self.status,
            "health_status": self.health_status,
            "tool_count": self.tool_count,
            "risk_tier": self.risk_tier,
            "elite_status": self.elite_status,
            "total_executions": self.total_executions,
            "success_rate": self.success_rate,
            "avg_response_time_ms": self.avg_response_time_ms,
            "last_execution_at": self.last_execution_at.isoformat() if self.last_execution_at else None,
        }


# =============================================================================
# AGENT TOOL MODEL
# =============================================================================

class AgentTool(Base):
    """
    Tool registry for each agent.

    Tracks tool definitions, usage, and risk settings.
    """
    __tablename__ = "agent_tools"
    __table_args__ = (
        UniqueConstraint('agent_id', 'tool_name', name='uq_agent_tool_name'),
        Index('ix_agent_tools_category', 'category'),
        Index('ix_agent_tools_risk_level', 'risk_level'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # Agent reference
    agent_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False, index=True)

    # Tool identification
    tool_name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50))  # query, action, analysis, communication, workflow
    risk_level = Column(String(20), default='low')  # low, medium, high, critical

    # Schema
    input_schema = Column(JSONB, default=dict)
    output_schema = Column(JSONB, default=dict)

    # Configuration
    requires_confirmation = Column(Boolean, default=False)
    cooldown_seconds = Column(Integer, default=0)
    max_per_hour = Column(Integer, nullable=True)

    # Usage tracking
    execution_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    avg_response_time_ms = Column(Float, default=0)

    # Timestamps
    last_used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    agent = relationship("AgentProfile", back_populates="tools")


# =============================================================================
# AGENT EXECUTION MODEL
# =============================================================================

class AgentExecution(Base):
    """
    Execution audit trail for agent operations.

    Tracks every agent invocation with full context.
    """
    __tablename__ = "agent_executions"
    __table_args__ = (
        Index('ix_agent_executions_agent', 'agent_id', 'created_at'),
        Index('ix_agent_executions_user', 'user_id', 'created_at'),
        Index('ix_agent_executions_status', 'status'),
        Index('ix_agent_executions_created', 'created_at'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # Unique execution ID
    execution_id = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False, index=True)

    # Agent reference
    agent_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(100), nullable=False)
    tool_name = Column(String(100))

    # User context
    user_id = Column(Integer, nullable=True, index=True)
    user_email = Column(String(255))

    # Input/Output
    input_text = Column(Text)
    input_data = Column(JSONB, default=dict)
    output_data = Column(JSONB, default=dict)

    # Status
    status = Column(String(20), nullable=False, default='pending')
    success = Column(Boolean)
    error_message = Column(Text)

    # Performance
    response_time_ms = Column(Integer)
    tokens_used = Column(Integer, default=0)
    total_cost = Column(Numeric(10, 4), default=0)

    # Execution trace
    trajectory = Column(JSONB, default=list)  # Step-by-step execution trace
    tool_calls = Column(JSONB, default=list)  # All tool invocations

    # Timestamps
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    agent = relationship("AgentProfile", back_populates="executions")


# =============================================================================
# GYM TEST SCENARIO MODEL
# =============================================================================

class GymTestScenario(Base):
    """
    Test case definitions for agent gym testing.

    Defines scenarios to validate agent behavior.
    """
    __tablename__ = "gym_test_scenarios"
    __table_args__ = (
        Index('ix_gym_scenarios_agent', 'agent_id'),
        Index('ix_gym_scenarios_category', 'category'),
        Index('ix_gym_scenarios_enabled', 'enabled'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # Scenario identification
    scenario_name = Column(String(200), nullable=False)
    description = Column(Text)

    # Agent reference (nullable for global scenarios)
    agent_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=True)
    agent_name = Column(String(100))

    # Categorization
    category = Column(String(50))  # functionality, edge_case, regression, performance
    priority = Column(String(20), default='medium')  # low, medium, high, critical

    # Test configuration
    input_text = Column(Text, nullable=False)
    input_data = Column(JSONB, default=dict)
    expected_output = Column(Text)
    success_criteria = Column(JSONB, nullable=False, default=dict)

    # Performance thresholds
    max_response_time_ms = Column(Integer)

    # Status
    enabled = Column(Boolean, default=True)

    # Historical results
    pass_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)
    last_run = Column(DateTime(timezone=True))
    last_result = Column(String(20))  # passed, failed, error

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(Integer, nullable=True)

    # Relationships
    agent = relationship("AgentProfile", back_populates="gym_scenarios")
    results = relationship("GymTestResult", back_populates="scenario", cascade="all, delete-orphan")


# =============================================================================
# GYM TEST RUN MODEL
# =============================================================================

class GymTestRun(Base):
    """
    Test execution records.

    Tracks each gym test run with aggregate results.
    """
    __tablename__ = "gym_test_runs"
    __table_args__ = (
        Index('ix_gym_runs_agent', 'agent_name'),
        Index('ix_gym_runs_status', 'status'),
        Index('ix_gym_runs_created', 'created_at'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # Run identification
    run_id = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False, index=True)

    # Target
    agent_name = Column(String(100))  # null for all-agent runs

    # Status
    status = Column(String(20), nullable=False, default='pending')  # pending, running, completed, failed

    # Results summary
    total_scenarios = Column(Integer, default=0)
    passed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    skipped = Column(Integer, default=0)

    # Performance
    avg_response_time_ms = Column(Float)
    total_duration_ms = Column(Integer)

    # Configuration
    run_config = Column(JSONB, default=dict)

    # Timestamps
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    triggered_by_id = Column(Integer, nullable=True)

    # Relationships
    results = relationship("GymTestResult", back_populates="run", cascade="all, delete-orphan")

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate percentage."""
        total = self.passed + self.failed
        return (self.passed / total * 100) if total > 0 else 0


# =============================================================================
# GYM TEST RESULT MODEL
# =============================================================================

class GymTestResult(Base):
    """
    Per-scenario test results.

    Detailed results for each scenario in a test run.
    """
    __tablename__ = "gym_test_results"
    __table_args__ = (
        Index('ix_gym_results_run', 'run_id'),
        Index('ix_gym_results_scenario', 'scenario_id'),
        Index('ix_gym_results_status', 'status'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # References
    run_id = Column(Integer, ForeignKey("gym_test_runs.id", ondelete="CASCADE"), nullable=False)
    scenario_id = Column(Integer, ForeignKey("gym_test_scenarios.id", ondelete="CASCADE"), nullable=False)

    # Result
    status = Column(String(20), nullable=False)  # passed, failed, error, skipped

    # Details
    actual_output = Column(Text)
    error_message = Column(Text)

    # Performance
    response_time_ms = Column(Integer)

    # Validation results
    criteria_results = Column(JSONB, default=dict)  # Per-criterion pass/fail

    # Timestamps
    executed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    run = relationship("GymTestRun", back_populates="results")
    scenario = relationship("GymTestScenario", back_populates="results")


# =============================================================================
# AGENT ALERT MODEL
# =============================================================================

class AgentAlert(Base):
    """
    Alerts and notifications for agents.

    Tracks issues requiring attention.
    """
    __tablename__ = "agent_alerts"
    __table_args__ = (
        Index('ix_agent_alerts_agent', 'agent_id'),
        Index('ix_agent_alerts_status', 'status'),
        Index('ix_agent_alerts_severity', 'severity'),
        Index('ix_agent_alerts_active', 'status', 'severity'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # Agent reference
    agent_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(100), nullable=False)

    # Alert details
    alert_type = Column(String(50), nullable=False)  # error_rate, latency, failure, governance
    severity = Column(String(20), nullable=False, default='medium')  # low, medium, high, critical

    # Content
    title = Column(String(200), nullable=False)
    message = Column(Text)
    details = Column(JSONB, default=dict)

    # Status
    status = Column(String(20), nullable=False, default='active')  # active, acknowledged, resolved, snoozed

    # Tracking
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledged_by_id = Column(Integer, nullable=True)
    resolved_at = Column(DateTime(timezone=True))
    resolved_by_id = Column(Integer, nullable=True)
    resolution_notes = Column(Text)
    snooze_until = Column(DateTime(timezone=True))

    # Timestamps
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    agent = relationship("AgentProfile", back_populates="alerts")


# =============================================================================
# AGENT METRICS TIMESERIES MODEL
# =============================================================================

class AgentMetricsTimeseries(Base):
    """
    Time-series metrics for agents.

    Stores periodic metrics snapshots for trending.
    """
    __tablename__ = "agent_metrics_timeseries"
    __table_args__ = (
        Index('ix_agent_metrics_agent_time', 'agent_id', 'timestamp'),
        Index('ix_agent_metrics_timestamp', 'timestamp'),
        Index('ix_agent_metrics_period', 'period_type', 'timestamp'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # Agent reference
    agent_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(100), nullable=False)

    # Time bucket
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    period_type = Column(String(20), nullable=False, default='hour')  # minute, hour, day

    # Execution metrics
    execution_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)

    # Performance metrics
    avg_response_time_ms = Column(Float, default=0)
    min_response_time_ms = Column(Float)
    max_response_time_ms = Column(Float)
    p95_response_time_ms = Column(Float)
    p99_response_time_ms = Column(Float)

    # Cost metrics
    total_cost = Column(Numeric(10, 4), default=0)
    total_tokens = Column(Integer, default=0)

    # Health metrics
    error_rate = Column(Float, default=0)
    health_score = Column(Float)  # 0-100

    # Tool breakdown (JSONB for flexibility)
    tool_usage = Column(JSONB, default=dict)  # {"tool_name": {"count": 10, "success": 9}}

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    agent = relationship("AgentProfile", back_populates="metrics")


# =============================================================================
# AGENT CHAT SESSION MODEL
# =============================================================================

class AgentChatSession(Base):
    """
    Chat session tracking for agent conversations.
    """
    __tablename__ = "agent_chat_sessions"
    __table_args__ = (
        Index('ix_chat_sessions_agent', 'agent_id'),
        Index('ix_chat_sessions_user', 'user_id'),
        Index('ix_chat_sessions_active', 'is_active'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # Session identification
    session_id = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False, index=True)

    # Agent reference
    agent_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(100), nullable=False)

    # User context
    user_id = Column(Integer, nullable=True, index=True)
    user_email = Column(String(255))

    # Session state
    is_active = Column(Boolean, default=True)
    context = Column(JSONB, default=dict)  # Conversation context

    # Metrics
    message_count = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    total_cost = Column(Numeric(10, 4), default=0)

    # Timestamps
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    agent = relationship("AgentProfile", back_populates="chat_sessions")
    messages = relationship("AgentChatMessage", back_populates="session", cascade="all, delete-orphan")


# =============================================================================
# AGENT CHAT MESSAGE MODEL
# =============================================================================

class AgentChatMessage(Base):
    """
    Chat message history for agent conversations.
    """
    __tablename__ = "agent_chat_messages"
    __table_args__ = (
        Index('ix_chat_messages_session', 'session_id', 'created_at'),
        Index('ix_chat_messages_role', 'role'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # Session reference
    session_id = Column(Integer, ForeignKey("agent_chat_sessions.id", ondelete="CASCADE"), nullable=False)

    # Message content
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)

    # Message metadata (renamed from 'metadata' - reserved in SQLAlchemy)
    message_metadata = Column(JSONB, default=dict)
    tool_calls = Column(JSONB, default=list)

    # Performance
    tokens_used = Column(Integer, default=0)
    response_time_ms = Column(Integer)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("AgentChatSession", back_populates="messages")


# =============================================================================
# TRAINING SCENARIO MODEL
# =============================================================================

class TrainingScenario(Base):
    """
    Training scenarios for the Agent Gym.
    """
    __tablename__ = "training_scenarios"
    __table_args__ = (
        Index('ix_training_scenarios_category', 'category'),
        Index('ix_training_scenarios_difficulty', 'difficulty'),
        Index('ix_training_scenarios_agent', 'target_agent_type'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # Scenario identification
    name = Column(String(200), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False)  # communication, processing, compliance, etc.

    # Target agent
    target_agent_type = Column(String(100))  # Can be null for universal scenarios

    # Difficulty and scoring
    difficulty = Column(String(20), default='medium')  # easy, medium, hard, expert
    max_score = Column(Integer, default=100)
    time_limit_seconds = Column(Integer)  # Optional time limit

    # Scenario configuration
    input_data = Column(JSONB, default=dict)  # Test input data
    expected_output = Column(JSONB, default=dict)  # Expected results for scoring
    evaluation_criteria = Column(JSONB, default=list)  # Scoring rubric

    # Status
    is_active = Column(Boolean, default=True)

    # Usage stats
    times_run = Column(Integer, default=0)
    avg_score = Column(Float)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    sessions = relationship("TrainingSession", back_populates="scenario", cascade="all, delete-orphan")


# =============================================================================
# TRAINING SESSION MODEL
# =============================================================================

class TrainingSession(Base):
    """
    Training session results from Agent Gym.
    """
    __tablename__ = "training_sessions"
    __table_args__ = (
        Index('ix_training_sessions_agent', 'agent_id'),
        Index('ix_training_sessions_scenario', 'scenario_id'),
        Index('ix_training_sessions_score', 'score'),
        Index('ix_training_sessions_date', 'started_at'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)

    # Session reference
    session_id = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False, index=True)

    # Agent reference
    agent_id = Column(Integer, ForeignKey("agent_profiles.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(100), nullable=False)

    # Scenario reference
    scenario_id = Column(Integer, ForeignKey("training_scenarios.id", ondelete="CASCADE"), nullable=False)

    # Results
    score = Column(Float)
    max_score = Column(Integer, default=100)
    passed = Column(Boolean)
    pass_threshold = Column(Float, default=70.0)

    # Detailed feedback
    feedback = Column(Text)
    detailed_results = Column(JSONB, default=dict)  # Per-criteria scores

    # Performance metrics
    duration_seconds = Column(Float)
    tokens_used = Column(Integer, default=0)
    cost = Column(Numeric(10, 4), default=0)

    # Session state
    status = Column(String(20), default='completed')  # running, completed, failed, cancelled

    # Timestamps
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    agent = relationship("AgentProfile", back_populates="training_sessions")
    scenario = relationship("TrainingScenario", back_populates="sessions")
