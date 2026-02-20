"""
Task Models

Task and AI Task models for tracking work items.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.task import Task, AITask

    # Query tasks
    tasks = db.query(Task).filter(Task.status == "pending").all()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Enum as SQLEnum, Index
)
from sqlalchemy.orm import relationship

# Import Base from the db module
from db import Base

# Import enums from the database package
from database.enums import TaskType


# ============================================================================
# AI TASK MODEL
# ============================================================================

class AITask(Base):
    """AI-generated tasks for the CRM pipeline"""
    __tablename__ = "ai_tasks"
    __table_args__ = (
        Index('ix_ai_tasks_assigned_to_id', 'assigned_to_id'),
        Index('ix_ai_tasks_lead_id', 'lead_id'),
        Index('ix_ai_tasks_loan_id', 'loan_id'),
        Index('ix_ai_tasks_due_date', 'due_date'),
        Index('ix_ai_tasks_organization_id', 'organization_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    title = Column(String, nullable=False)
    description = Column(Text)
    type = Column(SQLEnum(TaskType), default=TaskType.IN_PROGRESS)
    category = Column(String)
    priority = Column(String, default="medium")
    ai_confidence = Column(Integer)
    ai_reasoning = Column(Text)
    suggested_action = Column(Text)
    completed_action = Column(Text)
    borrower_name = Column(String)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    loan_id = Column(Integer, ForeignKey("loans.id"))
    assigned_to_id = Column(Integer, ForeignKey("users.id"))
    due_date = Column(DateTime)
    completed_at = Column(DateTime)
    estimated_time = Column(String)
    feedback = Column(Text)
    user_metadata = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    loan = relationship("Loan", back_populates="tasks")


# ============================================================================
# TASK MODEL
# ============================================================================

class Task(Base):
    """User-facing tasks in the CRM"""
    __tablename__ = "tasks"
    __table_args__ = (
        Index('ix_tasks_owner_id', 'owner_id'),
        Index('ix_tasks_status', 'status'),
        Index('ix_tasks_due_date', 'due_date'),
        Index('ix_tasks_lead_id', 'lead_id'),
        Index('ix_tasks_loan_id', 'loan_id'),
        Index('ix_tasks_owner_status', 'owner_id', 'status'),
        Index('ix_tasks_organization_id', 'organization_id'),
        Index('ix_tasks_org_status', 'organization_id', 'status'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)  # Multi-tenant isolation
    title = Column(String, nullable=False)
    description = Column(Text)
    status = Column(String, default="pending")  # pending, in_progress, completed
    priority = Column(String, default="medium")  # low, medium, high
    due_date = Column(DateTime)
    owner_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    related_contact_name = Column(String)
    related_type = Column(String)
    completed_at = Column(DateTime)

    # SLA milestone tracking fields
    sla_milestone_id = Column(Integer, nullable=True)  # Links to loan_milestone_history.id
    sla_milestone_type = Column(String, nullable=True)  # e.g., 'appraisal_ordered', 'title_received'
    sla_date_field = Column(String, nullable=True)  # Loan field to update (e.g., 'appraisal_ordered_date')
    milestone_date = Column(DateTime, nullable=True)  # Date entered by user when completing task

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    owner = relationship("User", backref="tasks")
    lead = relationship("Lead", backref="tasks")
    loan = relationship("Loan", backref="user_tasks")

    # Document intake classification task relationship
    email_intake_id = Column(Integer, ForeignKey("email_intakes.id"), nullable=True)
    email_intake = relationship("EmailIntake", back_populates="classification_task")

    # Workflow task linkage
    workflow_task_instance_id = Column(Integer, nullable=True)
    task_group_key = Column(String(100), nullable=True)


# ============================================================================
# ESCALATION & HANDOFF (Module 3 Gap Fix)
# ============================================================================

class EscalationRecord(Base):
    """Dedicated escalation event tracking.

    Provides audit trail for all escalations with level tracking,
    resolution management, and SLA enforcement per Module 3.1.
    """
    __tablename__ = "escalation_records"
    __table_args__ = (
        Index('ix_escalation_org_id', 'organization_id'),
        Index('ix_escalation_status', 'status'),
        Index('ix_escalation_level', 'escalation_level'),
        Index('ix_escalation_loan_id', 'loan_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)

    # Escalation details
    escalation_level = Column(Integer, default=1)  # 1=agent-to-agent, 2=agent-to-human, 3=emergency
    escalation_type = Column(String, nullable=False)  # compliance, sla_breach, borrower_distress, tool_failure, domain_mismatch

    # Routing
    original_owner_id = Column(Integer, ForeignKey("users.id"))
    original_agent = Column(String)  # AI agent that escalated
    escalated_to_id = Column(Integer, ForeignKey("users.id"))
    escalated_to_agent = Column(String)  # Target AI agent (for level 1)
    escalated_to_role = Column(String)  # compliance_officer, branch_manager, processor

    # Context (Module 3.2 — warm handoff)
    escalation_reason = Column(Text, nullable=False)
    conversation_summary = Column(Text)
    active_entities = Column(JSON)  # [{"type": "loan", "id": 123}]
    data_retrieved = Column(JSON)  # Key data already pulled
    tools_used = Column(JSON)  # ["check_trid_compliance", "get_pipeline_metrics"]
    user_emotional_state = Column(String)  # neutral, frustrated, urgent, confused
    pending_question = Column(Text)  # What the user is waiting for

    # SLA
    sla_deadline = Column(DateTime)  # When this escalation must be resolved
    acknowledged_at = Column(DateTime)
    acknowledged_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Resolution
    status = Column(String, default="open")  # open, acknowledged, in_progress, resolved, expired
    resolved_at = Column(DateTime)
    resolved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(Text)
    resolution_action = Column(String)  # handled, re_routed, false_alarm

    # Re-escalation
    re_escalated = Column(Boolean, default=False)
    re_escalation_count = Column(Integer, default=0)
    parent_escalation_id = Column(Integer, ForeignKey("escalation_records.id"), nullable=True)

    escalated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class HandoffLog(Base):
    """Tracks agent-to-agent and agent-to-human transfers.

    Captures the context package sent during handoffs per Module 3.2.
    Enables quality measurement of handoff completeness.
    """
    __tablename__ = "handoff_logs"
    __table_args__ = (
        Index('ix_handoff_org_id', 'organization_id'),
        Index('ix_handoff_session_id', 'session_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    session_id = Column(String, index=True)  # Conversation session UUID

    # Participants
    from_agent = Column(String, nullable=False)  # AI agent name or "human:user_id"
    to_agent = Column(String, nullable=False)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Handoff reason
    handoff_reason = Column(String, nullable=False)  # domain_mismatch, escalation, user_request, multi_domain
    handoff_trigger = Column(String)  # tool_name or "user_request" or "sla_breach"

    # Context package (Module 2.4)
    conversation_summary = Column(Text)
    active_entities = Column(JSON)
    pending_question = Column(Text)
    tools_already_used = Column(JSON)
    data_already_retrieved = Column(JSON)
    user_emotional_state = Column(String)

    # Quality tracking
    context_completeness_score = Column(Float)  # 0-1, how complete was the handoff
    user_had_to_repeat = Column(Boolean)  # Did the user need to re-explain?

    # Timing
    handoff_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    pickup_at = Column(DateTime)  # When receiving party engaged
    pickup_delay_seconds = Column(Integer)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "AITask",
    "Task",
    "EscalationRecord",
    "HandoffLog",
]
