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
# EXPORTS
# ============================================================================

__all__ = [
    "AITask",
    "Task",
]
