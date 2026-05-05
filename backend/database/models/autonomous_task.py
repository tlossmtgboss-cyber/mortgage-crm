"""
Autonomous Task Scheduler Models

Powers the proactive AI agent scheduler — the system that runs autonomous agents
on cron/interval schedules (lead nurturing, compliance checking, pipeline
monitoring, document follow-up, rate alerting, lead scoring, reporting,
client lifecycle management).

Tables:
- autonomous_tasks:  Scheduled task definitions with cron/interval triggers
- task_executions:   Append-only log of each autonomous task run
- agent_actions:     Individual actions taken by agents during executions

Usage:
    from database.models.autonomous_task import (
        AutonomousTask, TaskExecution, AgentAction,
    )

    task = AutonomousTask(
        organization_id=1,
        agent_type="lead_nurturing",
        task_name="Daily stale-lead outreach",
        schedule_cron="0 8 * * *",
    )
    db.add(task)
    db.commit()
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from db import Base


# ---------------------------------------------------------------------------
# AutonomousTask — scheduled autonomous agent task definition
# ---------------------------------------------------------------------------

class AutonomousTask(Base):
    """
    A scheduled autonomous agent task.

    Each row defines a recurring job that the autonomous scheduler picks up
    based on ``next_run_at``.  Supports both cron expressions and simple
    minute-interval scheduling.
    """

    __tablename__ = "autonomous_tasks"
    __table_args__ = (
        Index("ix_autotask_org_enabled", "organization_id", "is_enabled"),
        Index("ix_autotask_org_agent", "organization_id", "agent_type"),
        Index("ix_autotask_next_run_enabled", "next_run_at", "is_enabled"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )

    # Agent classification
    agent_type = Column(String(100), nullable=False, index=True)  # lead_nurturing, compliance_watchdog, ...
    task_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Schedule — use one or the other
    schedule_cron = Column(String(100), nullable=True)           # e.g. "0 8 * * *"
    schedule_interval_minutes = Column(Integer, nullable=True)   # simple interval alternative

    # Control
    is_enabled = Column(Boolean, default=True, index=True)
    priority = Column(Integer, default=5)  # 1 = highest, 10 = lowest
    config = Column(JSON, nullable=True)   # agent-specific configuration

    # Run tracking
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_run_status = Column(String(20), nullable=True)  # success, failed, partial, skipped
    consecutive_failures = Column(Integer, default=0)

    # Retry / timeout policy
    max_retries = Column(Integer, default=3)
    timeout_seconds = Column(Integer, default=300)

    # Bookkeeping
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    executions = relationship(
        "TaskExecution",
        back_populates="task",
        lazy="select",
        order_by="TaskExecution.started_at.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<AutonomousTask id={self.id} agent={self.agent_type!r} "
            f"name={self.task_name!r} enabled={self.is_enabled}>"
        )


# ---------------------------------------------------------------------------
# TaskExecution — log of each autonomous task run
# ---------------------------------------------------------------------------

class TaskExecution(Base):
    """
    Append-only log entry for a single autonomous task execution.

    Captures timing, item counts, result summary, errors, and arbitrary
    metrics (tokens used, queries run, etc.).
    """

    __tablename__ = "task_executions"
    __table_args__ = (
        Index("ix_taskexec_org_status", "organization_id", "status"),
        Index("ix_taskexec_task_started", "task_id", "started_at"),
        Index("ix_taskexec_started", "started_at"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        Integer, ForeignKey("autonomous_tasks.id"), nullable=False, index=True
    )
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )

    # Status & timing
    status = Column(
        String(20), nullable=False, default="running"
    )  # running, completed, failed, timeout, cancelled
    started_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Numeric(10, 2), nullable=True)

    # Throughput
    items_processed = Column(Integer, default=0)
    items_acted_on = Column(Integer, default=0)  # subset that required action

    # Results
    actions_taken = Column(JSON, nullable=True)   # [{type, target_id, description}]
    result_summary = Column(Text, nullable=True)  # human-readable summary
    errors = Column(JSON, nullable=True)           # list of errors encountered
    metrics = Column(JSON, nullable=True)          # {queries_run, tokens_used, ...}

    # Trigger source
    trigger = Column(
        String(20), default="scheduled"
    )  # scheduled, manual, event

    # Bookkeeping
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    task = relationship("AutonomousTask", back_populates="executions")
    actions = relationship(
        "AgentAction",
        back_populates="execution",
        lazy="select",
        order_by="AgentAction.created_at.asc()",
    )

    def __repr__(self) -> str:
        return (
            f"<TaskExecution id={self.id} task_id={self.task_id} "
            f"status={self.status!r}>"
        )


# ---------------------------------------------------------------------------
# AgentAction — individual action taken by an autonomous agent
# ---------------------------------------------------------------------------

class AgentAction(Base):
    """
    Granular record of a single action performed by an autonomous agent
    during a task execution (e.g. send SMS, create task, update lead).

    Supports an optional human-approval gate: if ``requires_approval`` is
    True, the action is held in ``pending_approval`` status until a user
    explicitly approves it.
    """

    __tablename__ = "agent_actions"
    __table_args__ = (
        Index("ix_agentact_exec_action", "execution_id", "action_type"),
        Index("ix_agentact_org_action", "organization_id", "action_type"),
        Index("ix_agentact_target", "target_entity", "target_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(
        Integer, ForeignKey("task_executions.id"), nullable=False, index=True
    )
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )

    # What was done
    action_type = Column(
        String(50), nullable=False, index=True
    )  # send_sms, send_email, create_task, update_lead, create_alert, create_notification
    target_entity = Column(String(50), nullable=True)  # lead, loan, user, contact
    target_id = Column(Integer, nullable=True, index=True)
    description = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)  # action details

    # Outcome
    status = Column(
        String(20), default="completed"
    )  # completed, failed, pending_approval

    # Approval gate
    requires_approval = Column(Boolean, default=False)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Bookkeeping
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    execution = relationship("TaskExecution", back_populates="actions")

    def __repr__(self) -> str:
        return (
            f"<AgentAction id={self.id} type={self.action_type!r} "
            f"target={self.target_entity}:{self.target_id} status={self.status!r}>"
        )


# ---------------------------------------------------------------------------
# Table creation helper (called from main.py at startup)
# ---------------------------------------------------------------------------

def create_tables_if_needed(engine):
    """Create autonomous_tasks, task_executions, and agent_actions tables if
    they don't already exist."""
    AutonomousTask.__table__.create(engine, checkfirst=True)
    TaskExecution.__table__.create(engine, checkfirst=True)
    AgentAction.__table__.create(engine, checkfirst=True)
