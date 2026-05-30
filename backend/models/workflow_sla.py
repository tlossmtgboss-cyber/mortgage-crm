"""
SLA Workflow System Models

SQLAlchemy models for the SLA-driven workflow task generation system.
These models work alongside the existing workflow_config_models.py.

Tables defined:
- WorkflowInstance: Tracks workflow lifecycle for leads/loans
- WorkflowAIConfidence: AI decision tracking for task execution
- LeadWorkflowRoleAssignment: Per-lead role assignments
- LoanWorkflowRoleAssignment: Per-loan role assignments

Enum types:
- WorkflowInstanceStatus
- WorkflowTaskStatus
- WorkflowTaskType
- WorkflowRoute
- LeadSourceCategory
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
import enum

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    Numeric, Index, CheckConstraint, UniqueConstraint, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declared_attr


# =============================================================================
# ENUM DEFINITIONS
# =============================================================================

class WorkflowInstanceStatus(str, enum.Enum):
    """Workflow instance lifecycle status"""
    ACTIVE = "active"           # Currently executing, generating tasks
    PAUSED = "paused"           # Temporarily stopped
    COMPLETED = "completed"     # Reached terminal status
    CANCELLED = "cancelled"     # Manually cancelled or superseded
    ERROR = "error"             # System error, requires attention


class WorkflowTaskStatus(str, enum.Enum):
    """Individual workflow task status"""
    SCHEDULED = "scheduled"     # Task created, waiting for due date
    PENDING = "pending"         # Due date reached, ready for execution
    IN_PROGRESS = "in_progress" # Task being worked on
    COMPLETED = "completed"     # Successfully completed
    SKIPPED = "skipped"         # Skipped (contact made via other method)
    FAILED = "failed"           # Execution failed, will be retried
    CANCELLED = "cancelled"     # Cancelled (workflow cancelled or sibling completed)
    DEAD_LETTER = "dead_letter" # Permanently failed after max retries


class WorkflowTaskType(str, enum.Enum):
    """Task type/communication method"""
    PHONE = "phone"             # Phone call task
    PHONE_AM = "phone_am"       # Morning phone call (Lead Purchase)
    PHONE_PM = "phone_pm"       # Afternoon phone call (Lead Purchase)
    TEXT = "text"               # SMS/Text message
    TEXT_AM = "text_am"         # Morning text (Lead Purchase)
    TEXT_PM = "text_pm"         # Afternoon text (Lead Purchase)
    EMAIL = "email"             # Email outreach
    REFERRAL_PARTNER = "referral_partner"  # Referral partner notification
    DIALER = "dialer"           # Power dialer queue task
    MANUAL = "manual"           # Manual follow-up task


class WorkflowRoute(str, enum.Enum):
    """Task routing destination"""
    TASK_LIST = "task_list"         # Standard task list assignment
    DIALER_QUEUE = "dialer_queue"   # Power dialer queue
    AI_AUTONOMOUS = "ai_autonomous" # AI handles autonomously
    EMAIL_AUTOMATION = "email_automation"  # Automated email system
    SMS_AUTOMATION = "sms_automation"      # Automated SMS system


class LeadSourceCategory(str, enum.Enum):
    """Lead source category for workflow assignment"""
    ORGANIC = "organic"         # Website, referral, walk-in
    PURCHASED = "purchased"     # Purchased lead (triggers Lead Purchase workflow)
    PARTNER = "partner"         # Partner/agent referral
    MARKETING = "marketing"     # Paid advertising leads
    OTHER = "other"             # Uncategorized


# =============================================================================
# MODEL FACTORY
# =============================================================================

# Cache for SLA models keyed by id(Base), mirroring workflow_config_models.py.
# Without this, every call to create_workflow_sla_models() defined a NEW
# WorkflowInstance class against the same declarative Base, registering a
# duplicate mapper. The duplicate broke string resolution for the
# WorkflowInstance <-> WorkflowTaskInstance back_populates pair, causing
# configure_mappers() to fail ("Mapper[WorkflowInstance] ... failed to locate
# a name") on the first ORM query of ANY request once a second registration
# occurred (e.g. tests calling the factory after app import). Caching makes the
# factory idempotent so repeated calls return the same classes.
_workflow_sla_models_cache = {}


def create_workflow_sla_models(Base):
    """
    Factory function to create workflow SLA models with the provided SQLAlchemy Base.

    This follows the pattern used in workflow_config_models.py to avoid circular imports.
    Idempotent: repeated calls with the same Base return the cached classes rather
    than re-defining (and re-mapping) them.
    """
    base_id = id(Base)
    if base_id in _workflow_sla_models_cache:
        return _workflow_sla_models_cache[base_id]

    class WorkflowInstance(Base):
        """
        Tracks the lifecycle of a workflow assigned to a lead/loan.

        A workflow instance represents an active execution of a workflow configuration
        against a specific lead or loan. It tracks:
        - Which workflow template is being used
        - Current status (active, paused, completed, cancelled, error)
        - When the workflow was triggered and by what milestone
        - Task generation progress
        """
        __tablename__ = "workflow_instances"
        __table_args__ = (
            # Only one active workflow per entity per workflow type
            Index(
                'ix_workflow_instances_active_lead',
                'lead_id', 'workflow_configuration_id',
                unique=True,
                postgresql_where='lead_id IS NOT NULL AND status = \'active\''
            ),
            Index(
                'ix_workflow_instances_active_loan',
                'loan_id', 'workflow_configuration_id',
                unique=True,
                postgresql_where='loan_id IS NOT NULL AND status = \'active\''
            ),
            Index('ix_workflow_instances_org_status', 'organization_id', 'status'),
            Index(
                'ix_workflow_instances_next_task_due',
                'next_task_due_at',
                postgresql_where='status = \'active\''
            ),
            CheckConstraint(
                '(lead_id IS NOT NULL AND loan_id IS NULL) OR (lead_id IS NULL AND loan_id IS NOT NULL)',
                name='chk_workflow_instance_entity'
            ),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)

        # Multi-tenant isolation
        organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)

        # Workflow template reference
        workflow_configuration_id = Column(
            Integer,
            ForeignKey("workflow_configurations.id", ondelete="RESTRICT"),
            nullable=False
        )

        # Target entity (exactly one must be set)
        lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True)
        loan_id = Column(Integer, ForeignKey("loans.id", ondelete="CASCADE"), nullable=True, index=True)

        # Current state
        status = Column(
            SQLEnum(WorkflowInstanceStatus, name='workflow_instance_status', create_type=False),
            nullable=False,
            default=WorkflowInstanceStatus.ACTIVE
        )

        # Milestone tracking (what triggered this workflow)
        trigger_milestone_status = Column(String(100))
        trigger_milestone_entered_at = Column(DateTime(timezone=True))

        # Lifecycle timestamps
        started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
        paused_at = Column(DateTime(timezone=True))
        completed_at = Column(DateTime(timezone=True))
        cancelled_at = Column(DateTime(timezone=True))

        # Cancellation tracking
        cancelled_by_id = Column(Integer, ForeignKey("users.id"))
        cancellation_reason = Column(Text)
        superseded_by_id = Column(Integer, ForeignKey("workflow_instances.id"))

        # Task generation tracking
        last_task_generated_day = Column(Integer, default=0)
        next_task_due_at = Column(DateTime(timezone=True))

        # Metadata
        created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

        # Relationships
        organization = relationship("Organization", backref=backref("workflow_instances", lazy="dynamic"))
        workflow_configuration = relationship("WorkflowConfiguration", backref=backref("instances", lazy="dynamic"))
        lead = relationship("Lead", backref=backref("workflow_instances", lazy="dynamic"))
        loan = relationship("Loan", backref=backref("workflow_instances", lazy="dynamic"))
        cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])
        superseded_by = relationship("WorkflowInstance", remote_side=[id], foreign_keys=[superseded_by_id])
        task_instances = relationship("WorkflowTaskInstance", back_populates="workflow_instance",
                                     cascade="all, delete-orphan")

        def pause(self, reason: str = None):
            """Pause the workflow instance."""
            self.status = WorkflowInstanceStatus.PAUSED
            self.paused_at = datetime.now(timezone.utc)

        def resume(self):
            """Resume a paused workflow."""
            if self.status == WorkflowInstanceStatus.PAUSED:
                self.status = WorkflowInstanceStatus.ACTIVE
                self.paused_at = None

        def cancel(self, user_id: int, reason: str, superseded_by_id: int = None):
            """Cancel the workflow instance."""
            self.status = WorkflowInstanceStatus.CANCELLED
            self.cancelled_at = datetime.now(timezone.utc)
            self.cancelled_by_id = user_id
            self.cancellation_reason = reason
            self.superseded_by_id = superseded_by_id

        def complete(self):
            """Mark workflow as completed."""
            self.status = WorkflowInstanceStatus.COMPLETED
            self.completed_at = datetime.now(timezone.utc)

        @property
        def target_entity(self) -> tuple:
            """Returns (entity_type, entity_id) for the workflow target."""
            if self.lead_id:
                return ("lead", self.lead_id)
            return ("loan", self.loan_id)


    class WorkflowAIConfidence(Base):
        """
        Tracks AI confidence levels for task execution decisions.

        Records each AI evaluation for a workflow task, including:
        - The confidence score (0.000 - 1.000)
        - Factors that influenced the score
        - The decision made (auto_execute, queue_for_review, escalate)
        - Whether execution occurred and its result
        """
        __tablename__ = "workflow_ai_confidence"
        __table_args__ = (
            Index('ix_workflow_ai_confidence_task', 'workflow_task_instance_id'),
            Index('ix_workflow_ai_confidence_decision', 'decision', 'created_at'),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)

        # Reference to task
        workflow_task_instance_id = Column(
            Integer,
            ForeignKey("workflow_task_instances.id", ondelete="CASCADE"),
            nullable=False
        )

        # AI evaluation details
        evaluated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
        confidence_score = Column(Numeric(4, 3), nullable=False)  # 0.000 to 1.000

        # Factors that influenced the score
        factors = Column(JSONB, nullable=False, default=dict)
        # Example: {
        #   "contact_history_quality": 0.8,
        #   "lead_engagement_score": 0.7,
        #   "time_since_last_contact": 0.9,
        #   "template_match_score": 0.85
        # }

        # Decision made
        decision = Column(String(50), nullable=False)  # 'auto_execute', 'queue_for_review', 'escalate'
        threshold_used = Column(Numeric(4, 3), nullable=False)  # The threshold applied (e.g., 0.950)

        # Execution details (if auto-executed)
        executed = Column(Boolean, nullable=False, default=False)
        execution_result = Column(JSONB)  # Result/error details

        # Audit trail
        model_version = Column(String(50))  # AI model version used

        created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

        # Relationships
        task_instance = relationship("WorkflowTaskInstance", backref=backref("ai_evaluations", lazy="dynamic"))

        # Constants
        AUTO_EXECUTE_THRESHOLD = Decimal("0.950")
        REVIEW_THRESHOLD = Decimal("0.700")

        @classmethod
        def determine_decision(cls, confidence: Decimal) -> str:
            """Determine decision based on confidence score."""
            if confidence >= cls.AUTO_EXECUTE_THRESHOLD:
                return "auto_execute"
            elif confidence >= cls.REVIEW_THRESHOLD:
                return "queue_for_review"
            else:
                return "escalate"


    class LeadWorkflowRoleAssignment(Base):
        """
        Per-lead role assignments for workflow task routing.

        Allows assigning specific users to roles for a particular lead's workflow.
        Example: John Smith is assigned as the LO for lead #123.
        """
        __tablename__ = "lead_workflow_role_assignments"
        __table_args__ = (
            UniqueConstraint('lead_id', 'role_id', 'is_active', name='uq_lead_role_assignment', deferrable=True),
            Index('ix_lead_role_assignments_lead', 'lead_id', 'is_active'),
            Index('ix_lead_role_assignments_user', 'assigned_user_id', 'is_active'),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)

        # Multi-tenant
        organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)

        # Target lead
        lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)

        # Role assignment
        role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
        assigned_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

        # Assignment metadata
        assigned_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
        assigned_by_id = Column(Integer, ForeignKey("users.id"))

        # Active/inactive for soft deletes
        is_active = Column(Boolean, nullable=False, default=True)
        deactivated_at = Column(DateTime(timezone=True))

        created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

        # Relationships
        organization = relationship("Organization")
        lead = relationship("Lead", backref=backref("workflow_role_assignments", lazy="dynamic"))
        role = relationship("Role")
        assigned_user = relationship("User", foreign_keys=[assigned_user_id])
        assigned_by = relationship("User", foreign_keys=[assigned_by_id])

        def deactivate(self):
            """Soft delete this assignment."""
            self.is_active = False
            self.deactivated_at = datetime.now(timezone.utc)


    class LoanWorkflowRoleAssignment(Base):
        """
        Per-loan role assignments for workflow task routing.

        Allows assigning specific users to roles for a particular loan's workflow.
        Example: Jane Doe is assigned as the Processor for loan #456.
        """
        __tablename__ = "loan_workflow_role_assignments"
        __table_args__ = (
            UniqueConstraint('loan_id', 'role_id', 'is_active', name='uq_loan_role_assignment', deferrable=True),
            Index('ix_loan_role_assignments_loan', 'loan_id', 'is_active'),
            Index('ix_loan_role_assignments_user', 'assigned_user_id', 'is_active'),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)

        # Multi-tenant
        organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)

        # Target loan
        loan_id = Column(Integer, ForeignKey("loans.id", ondelete="CASCADE"), nullable=False)

        # Role assignment
        role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
        assigned_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

        # Assignment metadata
        assigned_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
        assigned_by_id = Column(Integer, ForeignKey("users.id"))

        # Active/inactive for soft deletes
        is_active = Column(Boolean, nullable=False, default=True)
        deactivated_at = Column(DateTime(timezone=True))

        created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

        # Relationships
        organization = relationship("Organization")
        loan = relationship("Loan", backref=backref("workflow_role_assignments", lazy="dynamic"))
        role = relationship("Role")
        assigned_user = relationship("User", foreign_keys=[assigned_user_id])
        assigned_by = relationship("User", foreign_keys=[assigned_by_id])

        def deactivate(self):
            """Soft delete this assignment."""
            self.is_active = False
            self.deactivated_at = datetime.now(timezone.utc)


    models = {
        'WorkflowInstance': WorkflowInstance,
        'WorkflowAIConfidence': WorkflowAIConfidence,
        'LeadWorkflowRoleAssignment': LeadWorkflowRoleAssignment,
        'LoanWorkflowRoleAssignment': LoanWorkflowRoleAssignment,
    }
    _workflow_sla_models_cache[base_id] = models
    return models


# =============================================================================
# MIXIN FOR WORKFLOW TASK INSTANCE EXTENSIONS
# =============================================================================

class WorkflowTaskInstanceSLAMixin:
    """
    Mixin to add SLA-related fields to WorkflowTaskInstance.

    Apply this to the existing WorkflowTaskInstance model to add the new fields
    without creating a separate model.
    """

    @declared_attr
    def workflow_instance_id(cls):
        return Column(Integer, ForeignKey("workflow_instances.id", ondelete="CASCADE"))

    @declared_attr
    def task_type(cls):
        return Column(SQLEnum(WorkflowTaskType, name='workflow_task_type', create_type=False))

    @declared_attr
    def route(cls):
        return Column(
            SQLEnum(WorkflowRoute, name='workflow_route', create_type=False),
            nullable=False,
            default=WorkflowRoute.TASK_LIST
        )

    @declared_attr
    def task_group_key(cls):
        return Column(String(100))

    @declared_attr
    def linked_task_id(cls):
        return Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"))

    @declared_attr
    def dialer_session_task_id(cls):
        return Column(Integer)

    @declared_attr
    def assigned_role_id(cls):
        return Column(Integer, ForeignKey("roles.id"))

    @declared_attr
    def ai_eligible(cls):
        return Column(Boolean, nullable=False, default=False)

    @declared_attr
    def ai_confidence(cls):
        return Column(Numeric(3, 3))

    @declared_attr
    def ai_executed_at(cls):
        return Column(DateTime(timezone=True))

    @declared_attr
    def completion_source(cls):
        return Column(String(50))  # 'user', 'ai', 'dialer', 'automation'

    @declared_attr
    def completed_by_id(cls):
        return Column(Integer, ForeignKey("users.id"))
