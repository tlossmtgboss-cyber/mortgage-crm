"""
Pydantic schemas for the SLA Tracking System.

Defines request/response models for:
- SLA Measure configuration
- Milestone history tracking
- Performance snapshots
- Alerts management
- Dashboard/reporting data
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum


# ============ Enums for API ============

class TimeUnitEnum(str, Enum):
    HOURS = "hours"
    DAYS = "days"
    BUSINESS_DAYS = "business_days"


class SLAStatusEnum(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OVERDUE = "overdue"
    COMPLETED = "completed"
    WAIVED = "waived"


class MilestoneTypeEnum(str, Enum):
    # Lead Stage
    LEAD_RESPONSE = "lead_response"
    INITIAL_CONSULTATION = "initial_consultation"  # Added for existing data compatibility
    PRE_QUALIFIED = "pre_qualified"
    PREAPPROVAL = "preapproval"
    CONTRACT_RECEIVED = "contract_received"

    # Application Stage
    APPLICATION_SUBMITTED = "application_submitted"
    DOCUMENTS_REQUESTED = "documents_requested"
    DOCUMENTS_RECEIVED = "documents_received"
    DOCUMENT_COLLECTION = "document_collection"
    APPLICATION_COMPLETE = "application_complete"
    DISCLOSED = "disclosed"

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


class AlertStatusEnum(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    SNOOZED = "snoozed"


class TriggerFromEventEnum(str, Enum):
    """Events that can trigger the SLA timer to start."""
    LEAD_CREATED = "lead_created"
    LEAD_RESPONSE = "lead_response"
    PRE_QUALIFIED = "pre_qualified"
    PREAPPROVAL = "preapproval"
    APPLICATION_SUBMITTED = "application_submitted"
    DOCUMENTS_REQUESTED = "documents_requested"
    DOCUMENTS_RECEIVED = "documents_received"
    DOCUMENT_COLLECTION = "document_collection"
    APPLICATION_COMPLETE = "application_complete"
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


# ============ SLA Measure Schemas ============

class SLAMeasureBase(BaseModel):
    """Base schema for SLA Measure."""
    model_config = ConfigDict(json_encoders={Decimal: str})

    milestone_type: MilestoneTypeEnum
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    target_value: float = Field(...)  # Can be negative for "before" events (e.g., -10 = 10 days before trigger)
    target_unit: TimeUnitEnum = TimeUnitEnum.HOURS
    trigger_from: Optional[str] = "previous_milestone"  # What event triggers the SLA timer
    trigger_from_is_default: bool = False  # If true, this trigger is the default for this milestone type
    warning_threshold_pct: Decimal = Field(default=Decimal("75"), ge=0, le=100)
    critical_threshold_pct: float = Field(default=100, ge=0, le=200)
    applies_to_loan_types: Optional[List[str]] = None
    applies_to_channels: Optional[List[str]] = None
    business_hours_only: bool = True
    is_active: bool = True
    workflow_configuration_id: Optional[int] = None  # Which workflow to trigger when milestone is reached


class SLAMeasureCreate(SLAMeasureBase):
    """Schema for creating an SLA Measure."""
    pass


class SLAMeasureUpdate(BaseModel):
    """Schema for updating an SLA Measure."""
    model_config = ConfigDict(json_encoders={Decimal: str})

    name: Optional[str] = None
    description: Optional[str] = None
    target_value: Optional[float] = None
    target_unit: Optional[TimeUnitEnum] = None
    trigger_from: Optional[str] = None  # What event triggers the SLA timer
    trigger_from_is_default: Optional[bool] = None  # Make this the default trigger
    warning_threshold_pct: Optional[Decimal] = None
    critical_threshold_pct: Optional[float] = None
    applies_to_loan_types: Optional[List[str]] = None
    applies_to_channels: Optional[List[str]] = None
    business_hours_only: Optional[bool] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None
    workflow_configuration_id: Optional[int] = None  # Which workflow to trigger when milestone is reached


class WorkflowOptionResponse(BaseModel):
    """Schema for workflow option in dropdown."""
    id: int
    workflow_key: str
    workflow_name: str

    class Config:
        from_attributes = True


class SLAMeasureResponse(SLAMeasureBase):
    """Schema for SLA Measure response."""
    id: int
    organization_id: int
    trigger_from: Optional[str] = "previous_milestone"
    trigger_from_is_default: bool = False
    display_order: int = 0
    stage_type: Optional[str] = None  # Override stage: 'lead' or 'loan', null = auto-detect
    workflow_configuration_id: Optional[int] = None
    workflow_key: Optional[str] = None  # Populated from join for display
    workflow_name: Optional[str] = None  # Populated from join for display
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Milestone History Schemas ============

class MilestoneHistoryBase(BaseModel):
    """Base schema for milestone history."""
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    loan_number: Optional[str] = None
    sla_measure_id: int
    milestone_type: MilestoneTypeEnum
    assigned_to_id: Optional[int] = None
    notes: Optional[str] = None


class MilestoneHistoryCreate(MilestoneHistoryBase):
    """Schema for creating a milestone history record."""
    started_at: Optional[datetime] = None


class MilestoneHistoryUpdate(BaseModel):
    """Schema for updating a milestone history record."""
    status: Optional[SLAStatusEnum] = None
    completed_at: Optional[datetime] = None
    completed_by_id: Optional[int] = None
    notes: Optional[str] = None
    waive_reason: Optional[str] = None


class MilestoneHistoryResponse(BaseModel):
    """Schema for milestone history response."""
    id: int
    organization_id: int
    loan_id: Optional[int]
    lead_id: Optional[int]
    loan_number: Optional[str]
    sla_measure_id: int
    milestone_type: MilestoneTypeEnum
    started_at: Optional[datetime]
    target_deadline: Optional[datetime]
    completed_at: Optional[datetime]
    status: SLAStatusEnum
    target_hours: Optional[float]
    actual_hours: Optional[float]
    variance_hours: Optional[float]
    variance_pct: Optional[float]
    assigned_to_id: Optional[int]
    completed_by_id: Optional[int]
    notes: Optional[str]
    waive_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    # Nested SLA Measure info
    sla_measure_name: Optional[str] = None
    target_value: Optional[float] = None
    target_unit: Optional[str] = None

    class Config:
        from_attributes = True


class MilestoneStartRequest(BaseModel):
    """Request to start tracking a milestone."""
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    loan_number: Optional[str] = None
    milestone_type: MilestoneTypeEnum
    assigned_to_id: Optional[int] = None
    notes: Optional[str] = None


class MilestoneCompleteRequest(BaseModel):
    """Request to complete a milestone."""
    completed_by_id: Optional[int] = None
    notes: Optional[str] = None


class MilestoneWaiveRequest(BaseModel):
    """Request to waive a milestone."""
    waive_reason: str = Field(..., min_length=1)


# ============ Performance Snapshot Schemas ============

class PerformanceSnapshotResponse(BaseModel):
    """Schema for performance snapshot response."""
    id: int
    organization_id: int
    snapshot_date: date
    period_type: str
    scope_type: str
    scope_id: Optional[int]
    milestone_type: Optional[MilestoneTypeEnum]
    total_milestones: int
    completed_on_time: int
    completed_late: int
    still_in_progress: int
    overdue: int
    on_time_rate: Optional[float]
    avg_completion_time_hours: Optional[float]
    avg_variance_hours: Optional[float]
    avg_variance_pct: Optional[float]
    p50_completion_hours: Optional[float]
    p90_completion_hours: Optional[float]
    p95_completion_hours: Optional[float]
    status_breakdown: Optional[Dict[str, int]]
    created_at: datetime

    class Config:
        from_attributes = True


class PerformanceTrendPoint(BaseModel):
    """Single data point for performance trending."""
    date: date
    on_time_rate: float
    avg_completion_hours: float
    total_milestones: int
    overdue_count: int


class PerformanceTrendResponse(BaseModel):
    """Response for performance trending data."""
    scope_type: str
    scope_id: Optional[int]
    milestone_type: Optional[MilestoneTypeEnum]
    period_start: date
    period_end: date
    data_points: List[PerformanceTrendPoint]


# ============ Alert Schemas ============

class SLAAlertBase(BaseModel):
    """Base schema for SLA alerts."""
    milestone_history_id: int
    loan_id: Optional[int] = None
    lead_id: Optional[int] = None
    alert_type: str
    milestone_type: MilestoneTypeEnum
    title: str = Field(..., min_length=1, max_length=200)
    message: Optional[str] = None
    assigned_to_id: Optional[int] = None


class SLAAlertCreate(SLAAlertBase):
    """Schema for creating an SLA alert."""
    pass


class SLAAlertUpdate(BaseModel):
    """Schema for updating an SLA alert."""
    status: Optional[AlertStatusEnum] = None
    assigned_to_id: Optional[int] = None
    escalated_to_id: Optional[int] = None
    resolution_notes: Optional[str] = None
    snooze_until: Optional[datetime] = None


class SLAAlertResponse(BaseModel):
    """Schema for SLA alert response."""
    id: int
    organization_id: int
    milestone_history_id: int
    loan_id: Optional[int]
    lead_id: Optional[int]
    alert_type: str
    milestone_type: MilestoneTypeEnum
    title: str
    message: Optional[str]
    status: AlertStatusEnum
    assigned_to_id: Optional[int]
    escalated_to_id: Optional[int]
    triggered_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    snooze_until: Optional[datetime]
    resolution_notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    # Nested info
    loan_number: Optional[str] = None
    borrower_name: Optional[str] = None
    assigned_to_name: Optional[str] = None

    class Config:
        from_attributes = True


class AlertAcknowledgeRequest(BaseModel):
    """Request to acknowledge an alert."""
    notes: Optional[str] = None


class AlertResolveRequest(BaseModel):
    """Request to resolve an alert."""
    resolution_notes: str = Field(..., min_length=1)


class AlertEscalateRequest(BaseModel):
    """Request to escalate an alert."""
    escalated_to_id: int
    notes: Optional[str] = None


class AlertSnoozeRequest(BaseModel):
    """Request to snooze an alert."""
    snooze_until: datetime
    notes: Optional[str] = None


# ============ Dashboard/Reporting Schemas ============

class SLADashboardSummary(BaseModel):
    """Summary metrics for SLA dashboard."""
    total_active_milestones: int
    on_track_count: int
    at_risk_count: int
    overdue_count: int
    overall_on_time_rate: float
    avg_completion_time_hours: float
    active_alerts_count: int

    # By milestone type breakdown
    milestone_breakdown: Dict[str, Dict[str, Any]]


class SLADashboardResponse(BaseModel):
    """Complete SLA dashboard response."""
    summary: SLADashboardSummary
    recent_alerts: List[SLAAlertResponse]
    at_risk_loans: List[MilestoneHistoryResponse]
    performance_trend: List[PerformanceTrendPoint]


class TeamPerformanceItem(BaseModel):
    """Performance metrics for a team member."""
    user_id: int
    user_name: str
    role: Optional[str]
    total_milestones: int
    completed_on_time: int
    on_time_rate: float
    avg_completion_hours: float
    overdue_count: int


class TeamPerformanceResponse(BaseModel):
    """Team performance response."""
    team_id: Optional[int]
    team_name: Optional[str]
    period_start: date
    period_end: date
    team_on_time_rate: float
    members: List[TeamPerformanceItem]


class StageBottleneck(BaseModel):
    """Bottleneck analysis for a stage."""
    milestone_type: MilestoneTypeEnum
    milestone_name: str
    avg_delay_hours: float
    delay_frequency_pct: float
    total_affected_loans: int
    estimated_impact_days: float


class BottleneckAnalysisResponse(BaseModel):
    """Bottleneck analysis response."""
    period_start: date
    period_end: date
    bottlenecks: List[StageBottleneck]
    recommendations: List[str]


# ============ Efficiency Report Schemas ============

class EfficiencyReportResponse(BaseModel):
    """Schema for efficiency report response."""
    id: int
    organization_id: int
    report_date: date
    period_start: date
    period_end: date
    total_loans_processed: Optional[int]
    avg_days_to_close: Optional[float]
    avg_days_to_fund: Optional[float]
    overall_sla_compliance_rate: Optional[float]
    bottleneck_stages: Optional[List[Dict[str, Any]]]
    top_performers: Optional[List[Dict[str, Any]]]
    improvement_areas: Optional[List[Dict[str, Any]]]
    vs_prior_period: Optional[Dict[str, Any]]
    recommendations: Optional[List[str]]
    created_at: datetime

    class Config:
        from_attributes = True


class EfficiencyReportGenerateRequest(BaseModel):
    """Request to generate an efficiency report."""
    period_start: date
    period_end: date


# ============ Loan SLA Status Schemas ============

class LoanSLAStatus(BaseModel):
    """Current SLA status for a specific loan."""
    loan_id: Optional[int]
    lead_id: Optional[int]
    loan_number: Optional[str]
    borrower_name: Optional[str]
    current_stage: Optional[str]
    overall_status: SLAStatusEnum
    days_in_pipeline: int
    estimated_close_date: Optional[date]

    # Milestone statuses
    milestones: List[MilestoneHistoryResponse]

    # Risk indicators
    at_risk_milestones: int
    overdue_milestones: int
    next_deadline: Optional[datetime]
    next_deadline_milestone: Optional[str]


class LoanSLAStatusListResponse(BaseModel):
    """List of loans with SLA status."""
    total: int
    loans: List[LoanSLAStatus]
    filters_applied: Dict[str, Any]


# ============ Bulk Operations Schemas ============

class BulkMilestoneStartRequest(BaseModel):
    """Request to start milestones for multiple loans."""
    loan_ids: Optional[List[int]] = None
    lead_ids: Optional[List[int]] = None
    milestone_type: MilestoneTypeEnum


class BulkOperationResponse(BaseModel):
    """Response for bulk operations."""
    success_count: int
    failure_count: int
    failures: List[Dict[str, Any]]


# ============ Configuration Schemas ============

class SLAConfigResponse(BaseModel):
    """Complete SLA configuration response."""
    measures: List[SLAMeasureResponse]
    business_hours: Dict[str, Any]
    holidays: List[date]
    escalation_rules: Dict[str, Any]


class BusinessHoursConfig(BaseModel):
    """Business hours configuration."""
    start_hour: int = Field(default=9, ge=0, le=23)
    end_hour: int = Field(default=17, ge=0, le=23)
    work_days: List[int] = Field(default=[0, 1, 2, 3, 4])  # Mon-Fri


class HolidayConfig(BaseModel):
    """Holiday configuration."""
    date: date
    name: str
    is_recurring: bool = False


class EscalationRule(BaseModel):
    """Escalation rule configuration."""
    trigger_after_hours: float
    escalate_to_role: str
    notification_channels: List[str]
