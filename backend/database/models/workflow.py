"""
Workflow Models

Models for workflow automation and scheduled tasks.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.workflow import ScheduledWorkflow, WorkflowExecution

    # Query active workflows
    workflows = db.query(ScheduledWorkflow).filter(ScheduledWorkflow.is_active == True).all()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship

# Import Base from the db module
from db import Base


# ============================================================================
# SCHEDULED WORKFLOWS
# ============================================================================

class ScheduledWorkflow(Base):
    """Autonomous scheduled workflows for recurring AI tasks"""
    __tablename__ = "scheduled_workflows"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    workflow_type = Column(String, nullable=False)  # weekly_borrower_update, daily_task_summary, pipeline_report, follow_up_sequence
    schedule_cron = Column(String)  # Cron expression: "0 9 * * 1" = 9am every Monday
    schedule_interval = Column(String)  # Alternative: daily, weekly, monthly
    next_run = Column(DateTime, index=True)
    last_run = Column(DateTime)
    is_active = Column(Boolean, default=True, index=True)
    config = Column(JSON)  # Workflow-specific configuration
    target_criteria = Column(JSON)  # Filter criteria for targets (e.g., loan status, lead stage)
    template_id = Column(String)  # Email/message template to use
    retry_on_failure = Column(Boolean, default=True)
    max_retries = Column(Integer, default=3)
    notify_on_completion = Column(Boolean, default=False)
    notify_on_failure = Column(Boolean, default=True)
    total_executions = Column(Integer, default=0)
    successful_executions = Column(Integer, default=0)
    failed_executions = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class WorkflowExecution(Base):
    """Track each execution of a scheduled workflow"""
    __tablename__ = "workflow_executions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    workflow_id = Column(Integer, ForeignKey("scheduled_workflows.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="running")  # running, completed, failed, partial
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime)
    targets_processed = Column(Integer, default=0)
    targets_succeeded = Column(Integer, default=0)
    targets_failed = Column(Integer, default=0)
    actions_taken = Column(JSON)  # List of actions performed
    errors = Column(JSON)  # Any errors encountered
    execution_log = Column(Text)  # Detailed execution log
    retry_count = Column(Integer, default=0)
    trigger_type = Column(String, default="scheduled")  # scheduled, manual, event
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Workflow(Base):
    """User-defined workflows"""
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)  # Multi-tenant isolation
    user_id = Column(Integer, ForeignKey("users.id"))  # Account owner
    name = Column(String, nullable=False)
    description = Column(Text)
    workflow_type = Column(String)  # lead_intake, application_processing, underwriting, etc
    steps = Column(JSON)  # Array of workflow steps
    assigned_roles = Column(JSON)  # Which team member roles handle this
    triggers = Column(JSON)  # What triggers this workflow
    automation_rules = Column(JSON)  # AI automation rules
    is_active = Column(Boolean, default=True)
    created_by_ai = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# CALENDAR MAPPINGS
# ============================================================================

class CalendarMapping(Base):
    """Maps lead stages to Calendly event types for automatic scheduling"""
    __tablename__ = "calendar_mappings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    stage = Column(String, index=True)  # Lead stage (new, qualified, meeting_scheduled, etc.)
    event_type_uuid = Column(String)  # Calendly event type UUID
    event_type_name = Column(String)  # Friendly name (e.g., "Discovery Call")
    event_type_url = Column(String)  # Calendly booking page URL
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class OnboardingStep(Base):
    """Customizable onboarding step templates"""
    __tablename__ = "onboarding_steps"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))  # Owner who customized this
    step_number = Column(Integer, nullable=False)  # Order: 1, 2, 3, etc.
    title = Column(String, nullable=False)  # "Upload Documents", "Add Team Members", etc.
    description = Column(Text)  # Detailed description of what to do
    icon = Column(String, default="")  # Emoji or icon identifier
    required = Column(Boolean, default=True)  # Must complete to finish onboarding
    fields = Column(JSON)  # Form fields configuration: [{"name": "document", "type": "file", "label": ""}]
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# PROCESS TEMPLATES & ROLES
# ============================================================================

class ProcessTemplate(Base):
    """Process templates for workflow automation"""
    __tablename__ = "process_templates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role_name = Column(String, nullable=False)  # Loan Officer, Processor, Underwriter, etc.
    task_title = Column(String, nullable=False)
    task_description = Column(Text)
    sequence_order = Column(Integer, default=0)  # Order in the process
    estimated_duration = Column(Integer)  # In minutes
    dependencies = Column(JSON)  # Array of task IDs this depends on
    is_required = Column(Boolean, default=True)
    automation_potential = Column(String)  # AI suggestion: high, medium, low, none
    efficiency_notes = Column(Text)  # AI-generated efficiency suggestions
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="process_templates")


class ProcessRole(Base):
    """Stores AI-extracted roles from onboarding documents"""
    __tablename__ = "process_roles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role_name = Column(String, nullable=False)
    role_title = Column(String, nullable=False)  # Display title
    responsibilities = Column(Text)  # AI-extracted responsibilities summary
    skills_required = Column(JSON)  # Array of required skills
    key_activities = Column(JSON)  # Array of key activities
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="process_roles")


class ProcessMilestone(Base):
    """Stores milestones from parsed process documents"""
    __tablename__ = "process_milestones"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    sequence_order = Column(Integer, default=0)
    estimated_duration = Column(Integer)  # Total duration in hours
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="process_milestones")


class ProcessTask(Base):
    """Stores tasks extracted from process documents"""
    __tablename__ = "process_tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    milestone_id = Column(Integer, ForeignKey("process_milestones.id"))
    role_id = Column(Integer, ForeignKey("process_roles.id"))
    task_name = Column(String, nullable=False)
    task_description = Column(Text)
    sequence_order = Column(Integer, default=0)
    estimated_duration = Column(Integer)  # In minutes
    sla = Column(Integer)  # SLA in hours
    sla_unit = Column(String, default="hours")  # hours, days, minutes
    ai_automatable = Column(Boolean, default=False)
    dependencies = Column(JSON)  # Array of task IDs
    is_required = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", backref="process_tasks")
    milestone = relationship("ProcessMilestone", backref="tasks")
    role = relationship("ProcessRole", backref="assigned_tasks")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Scheduled Workflows
    "ScheduledWorkflow",
    "WorkflowExecution",
    "Workflow",
    # Calendar
    "CalendarMapping",
    "OnboardingStep",
    # Process
    "ProcessTemplate",
    "ProcessRole",
    "ProcessMilestone",
    "ProcessTask",
]
