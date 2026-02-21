"""
SLA (Service Level Agreement) Tracking Models

Models for tracking loan lifecycle milestones, SLA compliance, and performance metrics.
Enables real-time monitoring of:
- Milestone achievement vs targets
- Team/individual performance trending
- At-risk loan identification
- Efficiency reporting
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


# ============ Enums ============

class TimeUnit(str, enum.Enum):
    """Time measurement units for SLA targets."""
    HOURS = "hours"
    DAYS = "days"
    BUSINESS_DAYS = "business_days"


class SLAStatus(str, enum.Enum):
    """Status of a milestone relative to SLA target."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OVERDUE = "overdue"
    COMPLETED = "completed"
    WAIVED = "waived"


class MilestoneType(str, enum.Enum):
    """Types of loan lifecycle milestones."""
    # Lead Stage Milestones
    LEAD_RESPONSE = "lead_response"
    INITIAL_CONSULTATION = "initial_consultation"  # Added for existing data compatibility
    PRE_QUALIFIED = "pre_qualified"
    PREAPPROVAL = "preapproval"
    CONTRACT_RECEIVED = "contract_received"
    DOCUMENTS_REQUESTED = "documents_requested"
    DOCUMENTS_RECEIVED = "documents_received"
    APPLICATION_COMPLETE = "application_complete"

    # Active Loan Stage Milestones
    APPLICATION_SUBMITTED = "application_submitted"
    LE_PENDING = "le_pending"
    LE_DISCLOSED = "le_disclosed"
    DOCUMENT_COLLECTION = "document_collection"

    # Processing Stage
    SUBMITTED_TO_PROCESSING = "submitted_to_processing"
    PROCESSING_START = "processing_start"
    APPRAISAL_ORDERED = "appraisal_ordered"
    APPRAISAL_RECEIVED = "appraisal_received"
    TITLE_ORDERED = "title_ordered"
    TITLE_RECEIVED = "title_received"
    INSURANCE_ORDERED = "insurance_ordered"
    INSURANCE_RECEIVED = "insurance_received"

    # Underwriting Stage
    SUBMITTED_TO_UW = "submitted_to_uw"
    UW_DECISION = "uw_decision"
    APPROVED = "approved"
    CONDITIONS_ISSUED = "conditions_issued"
    CONDITIONS_CLEARED = "conditions_cleared"

    # Closing Stage
    CLEAR_TO_CLOSE = "clear_to_close"
    CLOSING_DOCS_OUT = "closing_docs_out"
    CLOSING_SCHEDULED = "closing_scheduled"
    CLOSING_DATE = "closing_date"
    CLOSED = "closed"
    FUNDED = "funded"


class AlertStatus(str, enum.Enum):
    """Status of SLA alerts."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    SNOOZED = "snoozed"


# ============ SLA Measure Configuration ============

class TriggerFromEvent(str, enum.Enum):
    """Events that can trigger the SLA timer to start."""
    # Lead Stage Events
    LEAD_CREATED = "lead_created"
    LEAD_RESPONSE = "lead_response"
    PRE_QUALIFIED = "pre_qualified"
    PREAPPROVAL = "preapproval"
    CONTRACT_RECEIVED = "contract_received"
    DOCUMENTS_REQUESTED = "documents_requested"
    DOCUMENTS_RECEIVED = "documents_received"
    APPLICATION_COMPLETE = "application_complete"
    # Active Loan Stage Events
    APPLICATION_SUBMITTED = "application_submitted"
    LE_PENDING = "le_pending"
    LE_DISCLOSED = "le_disclosed"
    DOCUMENT_COLLECTION = "document_collection"
    SUBMITTED_TO_PROCESSING = "submitted_to_processing"
    PROCESSING_START = "processing_start"
    APPRAISAL_ORDERED = "appraisal_ordered"
    APPRAISAL_RECEIVED = "appraisal_received"
    TITLE_ORDERED = "title_ordered"
    TITLE_RECEIVED = "title_received"
    INSURANCE_ORDERED = "insurance_ordered"
    INSURANCE_RECEIVED = "insurance_received"
    SUBMITTED_TO_UW = "submitted_to_uw"
    UW_DECISION = "uw_decision"
    APPROVED = "approved"
    CONDITIONS_ISSUED = "conditions_issued"
    CONDITIONS_CLEARED = "conditions_cleared"
    CLEAR_TO_CLOSE = "clear_to_close"
    CLOSING_DOCS_OUT = "closing_docs_out"
    CLOSING_SCHEDULED = "closing_scheduled"
    CLOSING_DATE = "closing_date"
    CLOSED = "closed"
    LOAN_CREATED = "loan_created"
    PREVIOUS_MILESTONE = "previous_milestone"


class SLAMeasure(Base):
    """
    Configuration for each SLA measure/milestone.
    Defines the target time and thresholds for each stage transition.
    """
    __tablename__ = "sla_measures"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False, default=1)

    # Milestone identification
    milestone_type = Column(SQLEnum(MilestoneType), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)

    # Target configuration
    target_value = Column(Float, nullable=False)  # e.g., 4 hours, 2 days
    target_unit = Column(SQLEnum(TimeUnit), nullable=False, default=TimeUnit.HOURS)

    # Trigger configuration - what event starts the timer for this milestone
    trigger_from = Column(String(50), nullable=True, default="previous_milestone")  # What triggers the timer
    trigger_from_is_default = Column(Boolean, default=False)  # If true, this trigger is the default for this milestone type

    # Thresholds (as percentage of target)
    warning_threshold_pct = Column(Float, default=75)  # At 75% of target = warning
    critical_threshold_pct = Column(Float, default=100)  # At 100% = overdue

    # Business rules
    applies_to_loan_types = Column(JSON)  # ["conventional", "fha", "va"] or null for all
    applies_to_channels = Column(JSON)  # ["retail", "wholesale"] or null for all
    business_hours_only = Column(Boolean, default=True)

    # Activation
    is_active = Column(Boolean, default=True)

    # Display order for UI sorting
    display_order = Column(Integer, default=0)

    # Stage type override (allows moving milestones between Lead/Loan stages)
    # Values: 'lead', 'loan', or null (auto-detect from milestone_type)
    stage_type = Column(String(20), nullable=True)

    # Workflow configuration - which workflow to trigger when this milestone is reached
    # Foreign key to workflow_configurations table (no import to avoid circular dependency)
    workflow_configuration_id = Column(Integer, ForeignKey("workflow_configurations.id", ondelete="SET NULL"), nullable=True, index=True)

    # Relationships
    history_records = relationship("LoanMilestoneHistory", back_populates="sla_measure")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ============ Loan Milestone History ============

class LoanMilestoneHistory(Base):
    """
    Tracks each milestone event for every loan.
    Used to calculate actual vs. target times and SLA compliance.
    """
    __tablename__ = "loan_milestone_history"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False, default=1)

    # Loan/Lead reference - no FK constraints to avoid import order issues
    loan_id = Column(Integer, nullable=True, index=True)
    lead_id = Column(Integer, nullable=True, index=True)
    loan_number = Column(String(50), index=True)

    # Milestone tracking - FK to sla_measures is safe since it's in the same module
    sla_measure_id = Column(Integer, ForeignKey("sla_measures.id"), nullable=False)
    milestone_type = Column(SQLEnum(MilestoneType), nullable=False, index=True)

    # Timing
    started_at = Column(DateTime(timezone=True))  # When milestone timer started
    target_deadline = Column(DateTime(timezone=True))  # Calculated deadline
    completed_at = Column(DateTime(timezone=True))  # When actually completed

    # Status
    status = Column(SQLEnum(SLAStatus), default=SLAStatus.NOT_STARTED, index=True)

    # Performance metrics
    target_hours = Column(Float)  # Target in hours (normalized)
    actual_hours = Column(Float)  # Actual time taken
    variance_hours = Column(Float)  # Difference (negative = ahead, positive = behind)
    variance_pct = Column(Float)  # Percentage over/under

    # Assignment - simple integer references to avoid import order issues with users table
    # FK constraints exist in database but not in model to prevent SQLAlchemy mapping errors
    assigned_to_id = Column(Integer, nullable=True, index=True)
    completed_by_id = Column(Integer, nullable=True)

    # Notes
    notes = Column(Text)
    waive_reason = Column(Text)  # If milestone was waived

    # Relationships
    sla_measure = relationship("SLAMeasure", back_populates="history_records")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ============ Company Holidays ============

class CompanyHoliday(Base):
    """
    Holiday calendar for business day calculations.
    Used by the SLA Tracker and Workflow Engine to exclude
    non-business days when calculating days_elapsed and deadlines.
    """
    __tablename__ = "company_holidays"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False, default=0)

    holiday_date = Column(Date, nullable=False)
    holiday_name = Column(String(100))
    is_recurring = Column(Boolean, default=False)  # Same date every year?

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============ SLA Performance Snapshots ============

class SLAPerformanceSnapshot(Base):
    """
    Daily/weekly snapshots of SLA performance for trending and reporting.
    Aggregated metrics at team and individual level.
    """
    __tablename__ = "sla_performance_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False, default=1)

    # Snapshot timing
    snapshot_date = Column(Date, nullable=False, index=True)
    period_type = Column(String(20), default="daily")  # daily, weekly, monthly

    # Scope
    scope_type = Column(String(20), nullable=False)  # organization, team, user
    scope_id = Column(Integer)  # team_id or user_id, null for org-wide

    # Milestone type (null = all milestones)
    milestone_type = Column(SQLEnum(MilestoneType), nullable=True)

    # Volume metrics
    total_milestones = Column(Integer, default=0)
    completed_on_time = Column(Integer, default=0)
    completed_late = Column(Integer, default=0)
    still_in_progress = Column(Integer, default=0)
    overdue = Column(Integer, default=0)

    # Performance metrics
    on_time_rate = Column(Float)  # Percentage
    avg_completion_time_hours = Column(Float)
    avg_variance_hours = Column(Float)
    avg_variance_pct = Column(Float)

    # Percentiles
    p50_completion_hours = Column(Float)  # Median
    p90_completion_hours = Column(Float)  # 90th percentile
    p95_completion_hours = Column(Float)  # 95th percentile

    # Breakdown by status (JSON for flexibility)
    status_breakdown = Column(JSON)  # {"on_track": 10, "at_risk": 3, "overdue": 1}

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============ SLA Alerts ============

class SLAAlert(Base):
    """
    Alerts for SLA violations and at-risk milestones.
    Used for notifications and escalation workflows.
    """
    __tablename__ = "sla_alerts"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False, default=1)

    # Related records - FK to loan_milestone_history is safe since it's in same module
    milestone_history_id = Column(Integer, ForeignKey("loan_milestone_history.id"), nullable=False)
    # No FK constraints for loan_id/lead_id to avoid import order issues
    loan_id = Column(Integer, nullable=True, index=True)
    lead_id = Column(Integer, nullable=True, index=True)

    # Alert details
    alert_type = Column(String(50), nullable=False)  # "warning", "critical", "escalation"
    milestone_type = Column(SQLEnum(MilestoneType), nullable=False)

    # Message
    title = Column(String(200), nullable=False)
    message = Column(Text)

    # Status
    status = Column(SQLEnum(AlertStatus), default=AlertStatus.ACTIVE, index=True)

    # Assignment - simple integer references to avoid import order issues with users table
    # FK constraints exist in database but not in model to prevent SQLAlchemy mapping errors
    assigned_to_id = Column(Integer, nullable=True, index=True)
    escalated_to_id = Column(Integer, nullable=True)

    # Timing
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    snooze_until = Column(DateTime(timezone=True))

    # Actions taken
    resolution_notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ============ SLA Efficiency Reports ============

class SLAEfficiencyReport(Base):
    """
    Detailed efficiency reports for analysis.
    Generated periodically for management review.
    """
    __tablename__ = "sla_efficiency_reports"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, index=True, nullable=False, default=1)

    # Report period
    report_date = Column(Date, nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Overall metrics
    total_loans_processed = Column(Integer)
    avg_days_to_close = Column(Float)
    avg_days_to_fund = Column(Float)

    # SLA compliance
    overall_sla_compliance_rate = Column(Float)

    # Bottleneck analysis (JSON for flexibility)
    bottleneck_stages = Column(JSON)  # [{"stage": "underwriting", "avg_delay_hours": 12}]

    # Top performers
    top_performers = Column(JSON)  # [{"user_id": 1, "on_time_rate": 98.5}]

    # Areas needing improvement
    improvement_areas = Column(JSON)  # [{"milestone": "appraisal_received", "avg_variance_pct": 25}]

    # Trend comparison
    vs_prior_period = Column(JSON)  # {"on_time_rate_change": +5.2, "avg_time_change": -0.5}

    # Recommendations (AI-generated or manual)
    recommendations = Column(JSON)  # ["Consider adding processing staff", "Review appraisal vendor SLAs"]

    created_at = Column(DateTime(timezone=True), server_default=func.now())
