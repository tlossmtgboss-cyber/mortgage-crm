"""
Workflow Configuration Models
Defines the structure for editable workflow definitions with:
- Days/timing configuration
- Communication methods (Phone, Text, Email, Referral Partner)
- Task responsibility (dynamic roles from Role table and user assignments)
- Task health status tracking

Updated: Now uses dynamic roles from the Role table instead of hardcoded enum.
Role responsibilities are stored as JSON: {"role_id": true/false, ...}
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum


class CommunicationMethod(str, enum.Enum):
    PHONE = "phone"
    TEXT = "text"
    EMAIL = "email"
    REFERRAL_PARTNER = "referral_partner"


class TaskResponsibility(str, enum.Enum):
    LO = "loan_officer"
    JR_LO = "junior_loan_officer"
    PRODUCTION_ASSISTANT = "production_assistant"
    CONCIERGE = "concierge"
    AI = "ai"
    PROCESSOR = "processor"
    UNDERWRITER = "underwriter"
    CLOSER = "closer"


class TaskHealthStatus(str, enum.Enum):
    HEALTHY = "healthy"  # Green dot - task is active and working
    BROKEN = "broken"    # Red dot - task has issues
    DISABLED = "disabled"  # Gray dot - task is turned off


# Cache for workflow config models to avoid duplicate class registration
_workflow_models_cache = {}


def get_workflow_config_models():
    """
    Get the cached workflow config models if they exist.
    Returns None if models haven't been created yet.
    """
    if _workflow_models_cache:
        # Return the first (and only) cached models
        return list(_workflow_models_cache.values())[0]
    return None


def create_workflow_config_models(Base):
    """
    Factory function to create workflow config models with the provided SQLAlchemy Base.
    Returns cached models if already created to avoid duplicate class registration.
    """
    # Return cached models if already created for this Base
    base_id = id(Base)
    if base_id in _workflow_models_cache:
        return _workflow_models_cache[base_id]

    class WorkflowConfiguration(Base):
        """
        Master workflow configuration for each stage.
        One record per workflow (Prospect, PreQual, etc.)
        Supports multi-tenancy with organization_id for org-specific configs.
        """
        __tablename__ = "workflow_configurations"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        workflow_key = Column(String(50), nullable=False, index=True)  # e.g., 'prospect', 'prequal'
        workflow_name = Column(String(100), nullable=False)  # Display name
        description = Column(Text)
        objective = Column(Text)
        statuses_impacted = Column(JSON)  # List of statuses this workflow applies to
        color = Column(String(20))
        is_active = Column(Boolean, default=True)

        # Multi-tenancy support
        organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
        is_system_template = Column(Boolean, default=False)  # True for system-wide templates

        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

        # Relationships
        days = relationship("WorkflowDayConfig", back_populates="workflow", cascade="all, delete-orphan", order_by="WorkflowDayConfig.day_order")
        role_assignments = relationship("WorkflowRoleAssignment", back_populates="workflow", cascade="all, delete-orphan")


    class WorkflowDayConfig(Base):
        """
        Configuration for each day/timing in a workflow.
        E.g., "First 24 Hours", "Day 2", "Month 2", etc.
        """
        __tablename__ = "workflow_day_configs"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        workflow_id = Column(Integer, ForeignKey("workflow_configurations.id"), nullable=False)
        day_label = Column(String(50), nullable=False)  # "First 24 Hours", "Day 2", "Month 3"
        day_order = Column(Integer, nullable=False)  # Order for display/execution
        day_value = Column(Integer)  # Numeric value in days (1, 2, 30, 60, etc.)

        # Communication method flags
        phone_enabled = Column(Boolean, default=False)
        phone_am_enabled = Column(Boolean, default=False)  # AM Phone call (Lead Purchase workflow)
        phone_pm_enabled = Column(Boolean, default=False)  # PM Phone call (Lead Purchase workflow)
        text_enabled = Column(Boolean, default=False)
        text_am_enabled = Column(Boolean, default=False)   # AM Text message (Lead Purchase workflow)
        text_pm_enabled = Column(Boolean, default=False)   # PM Text message (Lead Purchase workflow)
        email_enabled = Column(Boolean, default=False)
        referral_partner_enabled = Column(Boolean, default=False)

        # Task responsibility flags - LEGACY: kept for backwards compatibility
        # For new implementations, use role_responsibilities JSON column instead
        lo_responsible = Column(Boolean, default=False)
        jr_lo_responsible = Column(Boolean, default=False)
        production_asst_responsible = Column(Boolean, default=False)
        concierge_responsible = Column(Boolean, default=False)
        ai_responsible = Column(Boolean, default=False)

        # Dynamic role responsibilities - stores role_id -> boolean mapping
        # Format: {"1": true, "2": false, "3": true} where keys are role IDs
        # This allows any admin-created role to be assigned as responsible
        role_responsibilities = Column(JSON, default=dict)

        # Task health status
        health_status = Column(SQLEnum(TaskHealthStatus), default=TaskHealthStatus.HEALTHY)
        health_message = Column(String(255))  # Error message if broken
        last_health_check = Column(DateTime)

        # Weekly recurring task settings
        # When repeat_weekly=True, task repeats every week until loan closes
        # repeat_day_of_week: 0=Monday, 1=Tuesday, ..., 6=Sunday
        # First task goes out on the NEXT occurrence of that day after trigger date
        # (e.g., if Disclosed added on Monday, first Monday update is NEXT Monday)
        repeat_weekly = Column(Boolean, default=False)
        repeat_day_of_week = Column(Integer, nullable=True)  # 0=Monday, 6=Sunday
        repeat_until_status = Column(JSON, default=list)  # List of statuses that stop the repeat
        # e.g., ['closed', 'canceled', 'withdrawn', 'denied']

        # Additional config
        is_active = Column(Boolean, default=True)
        task_description = Column(Text)  # What should happen on this day
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

        # Relationships
        workflow = relationship("WorkflowConfiguration", back_populates="days")


    class WorkflowRoleAssignment(Base):
        """
        Assigns specific users to roles within a workflow.
        E.g., "John Doe" is the LO for the Prospect workflow.

        Updated: Now uses role_id from the Role table for dynamic roles.
        The legacy 'role' column is kept for backwards compatibility.
        """
        __tablename__ = "workflow_role_assignments"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        workflow_id = Column(Integer, ForeignKey("workflow_configurations.id"), nullable=False)

        # LEGACY: Keep old enum column for backwards compatibility
        role = Column(SQLEnum(TaskResponsibility), nullable=True)

        # NEW: Dynamic role from Role table
        # Note: Not using ForeignKey constraint because 'roles' table is created by
        # a different module and may not exist when this table is created.
        # Referential integrity is enforced at the application level.
        role_id = Column(Integer, nullable=True, index=True)

        user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Assigned user
        is_active = Column(Boolean, default=True)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

        # Relationships
        workflow = relationship("WorkflowConfiguration", back_populates="role_assignments")
        user = relationship("User", backref="workflow_role_assignments")
        # Note: For dynamic roles, use role_id to query the Role table directly
        # We don't define a relationship here because Role is in a different module
        # and would cause mapper initialization issues. Query Role explicitly when needed.


    class WorkflowTaskInstance(Base):
        """
        Individual task instances generated from workflow configurations.
        Tracks actual tasks for leads/loans.
        """
        __tablename__ = "workflow_task_instances"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        workflow_id = Column(Integer, ForeignKey("workflow_configurations.id"), nullable=False)
        workflow_instance_id = Column(Integer, ForeignKey("workflow_instances.id"), nullable=True)
        day_config_id = Column(Integer, ForeignKey("workflow_day_configs.id"), nullable=False)
        lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
        loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True)

        # Task details
        task_name = Column(String(255))
        task_description = Column(Text)
        communication_method = Column(SQLEnum(CommunicationMethod))
        assigned_role = Column(SQLEnum(TaskResponsibility))
        assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

        # Scheduling
        scheduled_date = Column(DateTime)
        due_date = Column(DateTime)
        completed_at = Column(DateTime)

        # Status
        status = Column(String(50), default="pending")  # pending, in_progress, completed, skipped, failed, dead_letter
        health_status = Column(SQLEnum(TaskHealthStatus), default=TaskHealthStatus.HEALTHY)
        error_message = Column(Text)
        escalation_level = Column(Integer, default=0)

        # Dead letter / retry tracking
        # NOTE: These columns need migration — run:
        #   ALTER TABLE workflow_task_instances ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;
        #   ALTER TABLE workflow_task_instances ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMP;
        retry_count = Column(Integer, default=0, nullable=False, server_default="0")
        last_failed_at = Column(DateTime, nullable=True)

        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

        # Relationships
        workflow = relationship("WorkflowConfiguration")
        day_config = relationship("WorkflowDayConfig")
        assigned_user = relationship("User", foreign_keys=[assigned_user_id])


    class BrokenTaskAlert(Base):
        """
        Alerts for broken workflow tasks that need admin attention.
        """
        __tablename__ = "broken_task_alerts"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        workflow_id = Column(Integer, ForeignKey("workflow_configurations.id"), nullable=False)
        day_config_id = Column(Integer, ForeignKey("workflow_day_configs.id"), nullable=True)
        task_instance_id = Column(Integer, ForeignKey("workflow_task_instances.id"), nullable=True)

        # Alert details
        alert_type = Column(String(50))  # 'missing_user', 'config_error', 'execution_failed', etc.
        alert_message = Column(Text)
        severity = Column(String(20), default="medium")  # low, medium, high, critical

        # Admin task created for this alert
        admin_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)

        # Status
        is_resolved = Column(Boolean, default=False)
        resolved_at = Column(DateTime)
        resolved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

        # Relationships
        workflow = relationship("WorkflowConfiguration")
        day_config = relationship("WorkflowDayConfig")
        task_instance = relationship("WorkflowTaskInstance")
        resolved_by = relationship("User", foreign_keys=[resolved_by_id])


    # Cache the models before returning
    models = {
        'WorkflowConfiguration': WorkflowConfiguration,
        'WorkflowDayConfig': WorkflowDayConfig,
        'WorkflowRoleAssignment': WorkflowRoleAssignment,
        'WorkflowTaskInstance': WorkflowTaskInstance,
        'BrokenTaskAlert': BrokenTaskAlert
    }
    _workflow_models_cache[base_id] = models
    return models


# Default workflow configurations matching the spreadsheet
DEFAULT_WORKFLOW_CONFIGS = {
    'prospect': {
        'name': 'Prospect Workflow',
        'description': 'Initial lead engagement and qualification workflow',
        'objective': 'Get the lead to complete the application for pre-approval',
        'statuses_impacted': ['New', 'Attempted Contact', 'Prospect'],
        'color': '#3b82f6',
        'days': [
            {'label': 'First 24 Hours', 'order': 1, 'value': 1, 'phone': True, 'text': True, 'email': False, 'partner': False, 'lo': True, 'jr_lo': False, 'pa': False, 'ai': False},
            {'label': 'Day 2', 'order': 2, 'value': 2, 'phone': True, 'text': False, 'email': False, 'partner': False, 'lo': False, 'jr_lo': True, 'pa': False, 'ai': False},
            {'label': 'Day 3', 'order': 3, 'value': 3, 'phone': True, 'text': True, 'email': False, 'partner': False, 'lo': False, 'jr_lo': True, 'pa': False, 'ai': False},
            {'label': 'Day 5', 'order': 4, 'value': 5, 'phone': False, 'text': True, 'email': True, 'partner': True, 'lo': False, 'jr_lo': True, 'pa': False, 'ai': False},
            {'label': 'Day 8', 'order': 5, 'value': 8, 'phone': True, 'text': False, 'email': False, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
            {'label': 'Day 12', 'order': 6, 'value': 12, 'phone': False, 'text': True, 'email': True, 'partner': True, 'lo': False, 'jr_lo': True, 'pa': False, 'ai': False},
            {'label': 'Day 17', 'order': 7, 'value': 17, 'phone': True, 'text': False, 'email': False, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
            {'label': 'Day 22', 'order': 8, 'value': 22, 'phone': False, 'text': True, 'email': False, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
            {'label': 'Day 30', 'order': 9, 'value': 30, 'phone': True, 'text': True, 'email': False, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
            {'label': 'Month 2', 'order': 10, 'value': 60, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
            {'label': 'Month 3', 'order': 11, 'value': 90, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
            {'label': 'Month 4', 'order': 12, 'value': 120, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
            {'label': 'Month 5', 'order': 13, 'value': 150, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
            {'label': 'Month 6', 'order': 14, 'value': 180, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
            {'label': 'Month 7', 'order': 15, 'value': 210, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
            {'label': 'Month 8', 'order': 16, 'value': 240, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
            {'label': 'Month 9', 'order': 17, 'value': 270, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
            {'label': 'Month 10-24', 'order': 18, 'value': 300, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'ai': True},
        ]
    },
    'prequal': {
        'name': 'PreQual Workflow',
        'description': 'Pre-qualification process workflow - Application and Prequal statuses',
        'objective': 'The objective is to have clients return supporting documents',
        'statuses_impacted': ['Application', 'Pre-Qualified'],
        'color': '#8b5cf6',
        'days': [
            {'label': 'Day 1', 'order': 1, 'value': 1, 'phone': True, 'text': True, 'email': True, 'partner': False, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Day 3', 'order': 2, 'value': 3, 'phone': True, 'text': False, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Day 4', 'order': 3, 'value': 4, 'phone': False, 'text': True, 'email': False, 'partner': True, 'lo': False, 'jr_lo': True, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Day 6', 'order': 4, 'value': 6, 'phone': True, 'text': False, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Day 8', 'order': 5, 'value': 8, 'phone': False, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Day 12', 'order': 6, 'value': 12, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': True, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Day 16', 'order': 7, 'value': 16, 'phone': False, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Day 22', 'order': 8, 'value': 22, 'phone': True, 'text': False, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Day 30', 'order': 9, 'value': 30, 'phone': True, 'text': True, 'email': False, 'partner': True, 'lo': False, 'jr_lo': True, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Month 2', 'order': 10, 'value': 60, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Month 3', 'order': 11, 'value': 90, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Month 4', 'order': 12, 'value': 120, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Month 5', 'order': 13, 'value': 150, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Month 6', 'order': 14, 'value': 180, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Month 7', 'order': 15, 'value': 210, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Month 8', 'order': 16, 'value': 240, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Month 9', 'order': 17, 'value': 270, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Month 10-24', 'order': 18, 'value': 300, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': False},
        ]
    },
    'pre_approved': {
        'name': 'Pre-Approval Workflow',
        'description': 'Pre-approval maintenance and house hunting support',
        'objective': 'Support the borrower through house hunting to contract',
        'statuses_impacted': ['Pre-Approved'],
        'color': '#10b981',
        'days': [
            {'label': 'Day 1', 'order': 1, 'value': 1, 'phone': True, 'text': True, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Day 3', 'order': 2, 'value': 3, 'phone': True, 'text': False, 'email': False, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Week 1', 'order': 3, 'value': 7, 'phone': False, 'text': True, 'email': True, 'partner': True, 'lo': False, 'jr_lo': True, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Week 2', 'order': 4, 'value': 14, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Week 3', 'order': 5, 'value': 21, 'phone': False, 'text': True, 'email': False, 'partner': True, 'lo': False, 'jr_lo': True, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Month 1', 'order': 6, 'value': 30, 'phone': True, 'text': True, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Month 2', 'order': 7, 'value': 60, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 3', 'order': 8, 'value': 90, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 4', 'order': 9, 'value': 120, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 5', 'order': 10, 'value': 150, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 6', 'order': 11, 'value': 180, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 9', 'order': 12, 'value': 270, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
        ]
    },
    'under_contract': {
        'name': 'Under Contract Workflow',
        'description': 'Active loan processing workflow',
        'objective': 'Guide the loan from contract to closing',
        'statuses_impacted': ['Under Contract'],
        'color': '#f59e0b',
        'days': [
            {'label': 'Day 1', 'order': 1, 'value': 1, 'phone': True, 'text': True, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Day 2', 'order': 2, 'value': 2, 'phone': True, 'text': True, 'email': False, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Day 3', 'order': 3, 'value': 3, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Day 5', 'order': 4, 'value': 5, 'phone': True, 'text': True, 'email': False, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Week 1', 'order': 5, 'value': 7, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Day 10', 'order': 6, 'value': 10, 'phone': False, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Week 2', 'order': 7, 'value': 14, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Week 3', 'order': 8, 'value': 21, 'phone': True, 'text': True, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Week 4', 'order': 9, 'value': 28, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Week 5', 'order': 10, 'value': 35, 'phone': True, 'text': True, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
        ]
    },
    'lead_purchase': {
        'name': 'Lead Purchase Workflow',
        'description': 'Purchased lead engagement workflow',
        'objective': 'Convert purchased leads to applications',
        'statuses_impacted': ['New'],
        'color': '#ec4899',
        'days': [
            {'label': 'Day 1 AM', 'order': 1, 'value': 1, 'phone': True, 'phone_am': True, 'text': True, 'text_am': True, 'email': True, 'partner': False, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Day 1 PM', 'order': 2, 'value': 1, 'phone': True, 'phone_pm': True, 'text': True, 'text_pm': True, 'email': False, 'partner': False, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Day 2', 'order': 3, 'value': 2, 'phone': True, 'text': True, 'email': False, 'partner': False, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Day 3', 'order': 4, 'value': 3, 'phone': True, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': True, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Day 4', 'order': 5, 'value': 4, 'phone': True, 'text': False, 'email': False, 'partner': False, 'lo': False, 'jr_lo': True, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Day 5', 'order': 6, 'value': 5, 'phone': True, 'text': True, 'email': True, 'partner': False, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Week 1', 'order': 7, 'value': 7, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': True, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Day 10', 'order': 8, 'value': 10, 'phone': False, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Week 2', 'order': 9, 'value': 14, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Week 3', 'order': 10, 'value': 21, 'phone': True, 'text': True, 'email': False, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 1', 'order': 11, 'value': 30, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 2', 'order': 12, 'value': 60, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 3', 'order': 13, 'value': 90, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 6', 'order': 14, 'value': 180, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
        ]
    },
    'theme_day': {
        'name': 'Theme Day Workflow',
        'description': 'Daily themed outreach activities',
        'objective': 'Maintain consistent touchpoints through themed campaigns',
        'statuses_impacted': [],
        'color': '#06b6d4',
        'days': [
            {'label': 'Monday', 'order': 1, 'value': 0, 'repeat_weekly': True, 'repeat_day_of_week': 0, 'phone': False, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Tuesday', 'order': 2, 'value': 0, 'repeat_weekly': True, 'repeat_day_of_week': 1, 'phone': False, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Wednesday', 'order': 3, 'value': 0, 'repeat_weekly': True, 'repeat_day_of_week': 2, 'phone': False, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Thursday', 'order': 4, 'value': 0, 'repeat_weekly': True, 'repeat_day_of_week': 3, 'phone': False, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Friday', 'order': 5, 'value': 0, 'repeat_weekly': True, 'repeat_day_of_week': 4, 'phone': False, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
        ]
    },
    'last_mile': {
        'name': 'Last Mile Workflow',
        'description': 'Final steps to closing',
        'objective': 'Ensure smooth closing process',
        'statuses_impacted': ['CTC'],
        'color': '#14b8a6',
        'days': [
            {'label': 'Day 1', 'order': 1, 'value': 1, 'phone': True, 'text': True, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Day 2', 'order': 2, 'value': 2, 'phone': True, 'text': True, 'email': False, 'partner': False, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Day 3', 'order': 3, 'value': 3, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Day 5', 'order': 4, 'value': 5, 'phone': True, 'text': True, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Day 6', 'order': 5, 'value': 6, 'phone': True, 'text': True, 'email': False, 'partner': False, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
            {'label': 'Day 7', 'order': 6, 'value': 7, 'phone': True, 'text': True, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': True, 'concierge': False, 'ai': False},
        ]
    },
    'post_close': {
        'name': 'Post Close Workflow',
        'description': 'Post-closing follow-up and referral generation',
        'objective': 'Generate referrals and maintain client relationships',
        'statuses_impacted': ['Funded'],
        'color': '#22c55e',
        'days': [
            {'label': 'Week 1', 'order': 1, 'value': 7, 'phone': True, 'text': True, 'email': True, 'partner': False, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Month 1', 'order': 2, 'value': 30, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Month 3', 'order': 3, 'value': 90, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 6', 'order': 4, 'value': 180, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
        ]
    },
    'credit_repair': {
        'name': 'Credit Repair Workflow',
        'description': 'Credit improvement tracking and support',
        'objective': 'Help clients improve credit for future qualification',
        'statuses_impacted': ['Does Not Qualify'],
        'color': '#f97316',
        'days': [
            {'label': 'Day 1', 'order': 1, 'value': 1, 'phone': True, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Week 1', 'order': 2, 'value': 7, 'phone': True, 'text': False, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Month 1', 'order': 3, 'value': 30, 'phone': True, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
            {'label': 'Month 2', 'order': 4, 'value': 60, 'phone': True, 'text': False, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': True},
            {'label': 'Month 3', 'order': 5, 'value': 90, 'phone': True, 'text': False, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': True},
            {'label': 'Month 4', 'order': 6, 'value': 120, 'phone': True, 'text': False, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': True},
            {'label': 'Month 5', 'order': 7, 'value': 150, 'phone': True, 'text': False, 'email': True, 'partner': False, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': True},
            {'label': 'Month 6', 'order': 8, 'value': 180, 'phone': True, 'text': True, 'email': True, 'partner': False, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': True, 'ai': False},
        ]
    },
    'nurture': {
        'name': 'Nurture Workflow',
        'description': 'Long-term relationship maintenance',
        'objective': 'Keep leads warm until they are ready to buy',
        'statuses_impacted': ['Long-Term Nurture'],
        'color': '#6366f1',
        'days': [
            {'label': 'Day 1', 'order': 1, 'value': 1, 'phone': True, 'text': True, 'email': True, 'partner': False, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': False},
            {'label': 'Week 2', 'order': 2, 'value': 14, 'phone': False, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 1', 'order': 3, 'value': 30, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 2', 'order': 4, 'value': 60, 'phone': False, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 3', 'order': 5, 'value': 90, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 4', 'order': 6, 'value': 120, 'phone': False, 'text': True, 'email': True, 'partner': False, 'lo': False, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 6', 'order': 7, 'value': 180, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
            {'label': 'Month 9', 'order': 8, 'value': 270, 'phone': True, 'text': False, 'email': True, 'partner': True, 'lo': True, 'jr_lo': False, 'pa': False, 'concierge': False, 'ai': True},
        ]
    }
}
