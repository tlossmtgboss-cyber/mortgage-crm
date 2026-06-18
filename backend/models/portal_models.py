"""
Perennia Portal Models
Complete database models for the client portal system including:
- Lifecycle management
- Milestone tracking
- Close On Time Calendar
- Home Value Intelligence
- Document management
- Notification system
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, Text,
    ForeignKey, JSON, Enum as SQLEnum, func, Numeric, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime, date, timezone
import enum

# Import Base from the main database module
try:
    from database import Base
except Exception as e:  # fail loud — a second Base silently splits the registry
    raise ImportError(f"{__name__} requires the canonical Base from `database`") from e


# =============================================================================
# ENUMS
# =============================================================================

class LifecycleStage(str, enum.Enum):
    """8-stage lifecycle from prospect to annual refresh"""
    PROSPECT = "PROSPECT"
    LEAD = "LEAD"
    PREAPPROVAL = "PREAPPROVAL"
    UNDER_CONTRACT = "UNDER_CONTRACT"
    PROCESSING = "PROCESSING"
    CLEAR_TO_CLOSE = "CLEAR_TO_CLOSE"
    FUNDED = "FUNDED"
    MUM = "MUM"  # Mortgages Under Management
    ANNUAL_REFRESH = "ANNUAL_REFRESH"


class MilestoneStatus(str, enum.Enum):
    """Status for milestone instances"""
    LOCKED = "LOCKED"
    UPCOMING = "UPCOMING"
    ACTIVE = "ACTIVE"
    COMPLETE = "COMPLETE"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class TaskStatus(str, enum.Enum):
    """Status for task instances"""
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    NA = "NA"
    BLOCKED = "BLOCKED"


class PortalUserRole(str, enum.Enum):
    """User roles for the portal"""
    BORROWER = "BORROWER"
    CO_BORROWER = "CO_BORROWER"
    REALTOR = "REALTOR"
    LO = "LO"  # Loan Officer
    PA = "PA"  # Processing Assistant
    UW = "UW"  # Underwriter
    TITLE = "TITLE"
    INSURANCE = "INSURANCE"
    SYSTEM = "SYSTEM"


class DocumentType(str, enum.Enum):
    """Types of documents"""
    # Income documents
    PAYSTUB = "PAYSTUB"
    W2 = "W2"
    TAX_RETURN = "TAX_RETURN"

    # Asset documents
    BANK_STATEMENT = "BANK_STATEMENT"

    # Identity documents
    ID = "ID"
    DRIVERS_LICENSE = "DRIVERS_LICENSE"

    # Property documents
    PURCHASE_AGREEMENT = "PURCHASE_AGREEMENT"
    PURCHASE_CONTRACT = "PURCHASE_CONTRACT"
    APPRAISAL = "APPRAISAL"
    TITLE_REPORT = "TITLE_REPORT"
    PROPERTY_TAX_BILL = "PROPERTY_TAX_BILL"
    HOA_DOCS = "HOA_DOCS"

    # Insurance documents
    HOMEOWNERS_INSURANCE = "HOMEOWNERS_INSURANCE"
    INSURANCE_DEC_PAGE = "INSURANCE_DEC_PAGE"

    # Closing documents
    CLOSING_DISCLOSURE = "CLOSING_DISCLOSURE"

    OTHER = "OTHER"


class DocumentStatus(str, enum.Enum):
    """Document verification status"""
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REUPLOAD = "NEEDS_REUPLOAD"
    EXPIRED = "EXPIRED"


class ExtractionStatus(str, enum.Enum):
    """Status for document AI extraction"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REVIEW_NEEDED = "REVIEW_NEEDED"


class ScenarioType(str, enum.Enum):
    """Types of presentation scenarios"""
    KEEP_CURRENT = "KEEP_CURRENT"
    REFI_RATE_TERM = "REFI_RATE_TERM"
    REFI_CASH_OUT = "REFI_CASH_OUT"
    SELL_NET_PROCEEDS = "SELL_NET_PROCEEDS"
    CONVERT_TO_RENTAL = "CONVERT_TO_RENTAL"


class NotificationChannel(str, enum.Enum):
    """Notification delivery channels"""
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"
    IN_APP = "IN_APP"


class NotificationPriority(str, enum.Enum):
    """Priority levels for notifications"""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class NotificationStatus(str, enum.Enum):
    """Status of notification delivery"""
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RiskSeverity(str, enum.Enum):
    """Severity levels for risk flags"""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# =============================================================================
# PORTAL LOAN MODEL
# =============================================================================

class PortalLoan(Base):
    """
    Extended loan information for portal features.
    Links to existing loan/deal records in the main CRM.
    """
    __tablename__ = "portal_loans"

    id = Column(Integer, primary_key=True, index=True)

    # Link to existing CRM
    crm_deal_id = Column(Integer, index=True)  # Link to deals table
    crm_client_id = Column(Integer, index=True)  # Link to clients table

    # Borrower info (denormalized for portal access)
    primary_borrower_name = Column(String(255))
    primary_borrower_email = Column(String(255))
    primary_borrower_phone = Column(String(50))
    co_borrower_name = Column(String(255))
    co_borrower_email = Column(String(255))

    # Loan identifiers
    loan_number = Column(String(50), unique=True, index=True)
    external_loan_id = Column(String(100))

    # Loan details
    loan_amount = Column(Numeric(12, 2))
    interest_rate = Column(Numeric(5, 3))
    loan_term_months = Column(Integer, default=360)
    loan_type = Column(String(50))  # conventional, fha, va, usda, jumbo
    loan_purpose = Column(String(50))  # purchase, refinance, cash_out

    # Property
    property_address = Column(String(500))
    property_city = Column(String(100))
    property_state = Column(String(2))
    property_zip = Column(String(10))
    property_county = Column(String(100))
    property_type = Column(String(50))  # single_family, condo, townhouse, etc.
    purchase_price = Column(Numeric(12, 2))

    # Lifecycle management
    lifecycle_stage = Column(SQLEnum(LifecycleStage), default=LifecycleStage.PROSPECT)
    lifecycle_stage_entered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    lifecycle_stage_reason = Column(Text)
    lifecycle_stage_source = Column(String(50), default="system")

    # Key dates
    application_date = Column(Date)
    preapproval_date = Column(Date)
    preapproval_expiry_date = Column(Date)
    contract_date = Column(Date)
    closing_date = Column(Date)
    funding_date = Column(Date)
    first_payment_date = Column(Date)

    # Team assignments
    loan_officer_id = Column(Integer)
    processor_id = Column(Integer)
    underwriter_id = Column(Integer)
    realtor_id = Column(Integer)

    # Status
    is_active = Column(Boolean, default=True)
    is_test_loan = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    milestones = relationship("MilestoneInstance", back_populates="loan", cascade="all, delete-orphan")
    documents = relationship("PortalDocument", back_populates="loan", cascade="all, delete-orphan")
    activity_log = relationship("LoanActivityLog", back_populates="loan", cascade="all, delete-orphan")
    risk_flags = relationship("RiskFlag", back_populates="loan", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_portal_loans_stage', 'lifecycle_stage', postgresql_where=Column('is_active') == True),
        Index('idx_portal_loans_closing', 'closing_date', postgresql_where=Column('is_active') == True),
    )


# =============================================================================
# LIFECYCLE STATE HISTORY
# =============================================================================

class LifecycleStateHistory(Base):
    """Audit log of all lifecycle stage transitions"""
    __tablename__ = "lifecycle_state_history"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), index=True)
    from_stage = Column(SQLEnum(LifecycleStage))
    to_stage = Column(SQLEnum(LifecycleStage), nullable=False)
    reason = Column(Text)
    source = Column(String(100), nullable=False)  # system, user, api, webhook
    triggered_by = Column(Integer)  # User ID
    extra_data = Column(JSON, default={})
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_state_history_loan', 'loan_id', 'created_at'),
    )


# =============================================================================
# MILESTONE SYSTEM
# =============================================================================

class MilestoneTemplate(Base):
    """Reusable milestone definitions"""
    __tablename__ = "milestone_templates"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    stage = Column(SQLEnum(LifecycleStage), nullable=False)
    display_order = Column(Integer, nullable=False)

    # Dependencies (list of milestone template keys that must be complete first)
    dependencies = Column(JSON, default=[])

    # SLA configuration
    sla_mode = Column(String(20), default="NONE")  # NONE, BUSINESS_DAYS, CALENDAR_DAYS
    sla_duration = Column(Integer)  # Number of days
    sla_start_event_key = Column(String(100))  # Event that starts the SLA clock

    # Visibility
    visible_to_borrower = Column(Boolean, default=True)
    visible_to_partner = Column(Boolean, default=False)
    visible_to_internal = Column(Boolean, default=True)

    # UI configuration
    icon = Column(String(50))  # Emoji or icon name
    color_code = Column(String(20))
    accent = Column(String(20))  # success, warn, danger, info

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    instances = relationship("MilestoneInstance", back_populates="template")
    task_templates = relationship("TaskTemplate", back_populates="milestone_template", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_milestone_templates_stage', 'stage', 'display_order', postgresql_where=Column('is_active') == True),
    )


class MilestoneInstance(Base):
    """Actual milestone progress for a specific loan"""
    __tablename__ = "milestone_instances"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(Integer, ForeignKey("milestone_templates.id"), nullable=False)

    status = Column(SQLEnum(MilestoneStatus), default=MilestoneStatus.LOCKED)
    entered_at = Column(DateTime)
    completed_at = Column(DateTime)
    due_date = Column(Date)
    business_days_from_today = Column(Integer)

    # Evidence of completion (JSON array of document IDs, notes, etc.)
    evidence = Column(JSON, default=[])
    notes = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    loan = relationship("PortalLoan", back_populates="milestones")
    template = relationship("MilestoneTemplate", back_populates="instances")
    tasks = relationship("TaskInstance", back_populates="milestone", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('loan_id', 'template_id', name='unique_loan_milestone'),
        Index('idx_milestone_instances_loan', 'loan_id', 'status'),
        Index('idx_milestone_instances_due', 'due_date', postgresql_where=Column('status').in_(['ACTIVE', 'UPCOMING'])),
    )


class TaskTemplate(Base):
    """Task templates within milestones"""
    __tablename__ = "task_templates"

    id = Column(Integer, primary_key=True, index=True)
    milestone_template_id = Column(Integer, ForeignKey("milestone_templates.id", ondelete="CASCADE"), nullable=False)

    key = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    instructions = Column(Text)
    owner_role = Column(SQLEnum(PortalUserRole), nullable=False)

    # Call to action
    cta_type = Column(String(20))  # UPLOAD, SCHEDULE, SIGN, CALL, FORM, MESSAGE
    cta_url = Column(String(500))

    display_order = Column(Integer, nullable=False)
    is_required = Column(Boolean, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    milestone_template = relationship("MilestoneTemplate", back_populates="task_templates")


class TaskInstance(Base):
    """Actual task instances for a loan"""
    __tablename__ = "task_instances"

    id = Column(Integer, primary_key=True, index=True)
    milestone_instance_id = Column(Integer, ForeignKey("milestone_instances.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(Integer, ForeignKey("task_templates.id"))

    title = Column(String(255), nullable=False)
    instructions = Column(Text)
    owner_role = Column(SQLEnum(PortalUserRole), nullable=False)
    assigned_to = Column(Integer)  # User ID

    status = Column(SQLEnum(TaskStatus), default=TaskStatus.TODO)
    due_at = Column(DateTime)
    completed_at = Column(DateTime)
    completed_by = Column(Integer)  # User ID

    attachments = Column(JSON, default=[])
    notes = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    milestone = relationship("MilestoneInstance", back_populates="tasks")


# =============================================================================
# CLOSE ON TIME CALENDAR
# =============================================================================

class FederalHoliday(Base):
    """Federal holidays for business day calculations"""
    __tablename__ = "federal_holidays"

    id = Column(Integer, primary_key=True, index=True)
    holiday_date = Column(Date, unique=True, nullable=False)
    holiday_name = Column(String(100), nullable=False)
    is_observed = Column(Boolean, default=True)
    is_auto_generated = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_federal_holidays_date', 'holiday_date', postgresql_where=Column('is_observed') == True),
    )


class CloseOnTimeSchedule(Base):
    """Close On Time Calendar schedule for a loan"""
    __tablename__ = "close_on_time_schedules"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), nullable=False)

    application_date = Column(Date, nullable=False)
    closing_date = Column(Date, nullable=False)
    total_business_days = Column(Integer, nullable=False)
    business_days_remaining = Column(Integer)

    # Warnings
    is_closing_non_business_day = Column(Boolean, default=False)
    non_business_day_warning = Column(Text)

    status = Column(String(20), default="active")  # active, completed, cancelled

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer)

    # Relationships
    milestones = relationship("CloseOnTimeMilestone", back_populates="schedule", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_cot_schedules_loan', 'loan_id'),
    )


class CloseOnTimeMilestone(Base):
    """Individual milestones in the Close On Time Calendar"""
    __tablename__ = "close_on_time_milestones"

    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("close_on_time_schedules.id", ondelete="CASCADE"), nullable=False)

    milestone_name = Column(String(255), nullable=False)
    milestone_description = Column(Text)
    due_date = Column(Date, nullable=False)
    business_days_from_today = Column(Integer)

    status = Column(String(20), default="pending")  # pending, in-progress, completed, overdue
    calculation_type = Column(String(20), nullable=False)  # from_application, from_closing
    day_offset = Column(Integer, nullable=False)  # Days from reference date
    display_order = Column(Integer, nullable=False)

    # UI
    icon = Column(String(50))
    color_code = Column(String(20))

    completed_at = Column(DateTime)
    completed_by = Column(Integer)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    schedule = relationship("CloseOnTimeSchedule", back_populates="milestones")

    __table_args__ = (
        Index('idx_cot_milestones_schedule', 'schedule_id', 'display_order'),
        Index('idx_cot_milestones_due', 'due_date', 'status'),
    )


# =============================================================================
# DOCUMENT MANAGEMENT
# =============================================================================

class PortalDocument(Base):
    """Documents uploaded through the portal"""
    __tablename__ = "portal_documents"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), nullable=False)
    uploaded_by = Column(Integer, nullable=False)  # User ID

    # File info
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)  # S3 path or local path
    file_size = Column(Integer)
    mime_type = Column(String(100))
    checksum = Column(String(64))  # SHA-256

    # Classification
    document_type = Column(SQLEnum(DocumentType))
    classification_confidence = Column(Numeric(3, 2))

    # AI Extraction
    extraction_status = Column(SQLEnum(ExtractionStatus), default=ExtractionStatus.PENDING)
    extraction_started_at = Column(DateTime)
    extraction_completed_at = Column(DateTime)
    extraction_error = Column(Text)

    # Context
    stage = Column(SQLEnum(LifecycleStage))
    milestone_id = Column(Integer, ForeignKey("milestone_instances.id"))
    task_id = Column(Integer, ForeignKey("task_instances.id"))

    # Verification
    is_verified = Column(Boolean, default=False)
    verified_by = Column(Integer)
    verified_at = Column(DateTime)

    # Soft delete
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    loan = relationship("PortalLoan", back_populates="documents")
    extractions = relationship("DocumentExtraction", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_portal_documents_loan', 'loan_id', 'created_at', postgresql_where=Column('is_deleted') == False),
        Index('idx_portal_documents_extraction', 'extraction_status', postgresql_where=Column('extraction_status').in_(['PENDING', 'PROCESSING'])),
    )


class DocumentExtraction(Base):
    """AI-extracted fields from documents"""
    __tablename__ = "document_extractions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("portal_documents.id", ondelete="CASCADE"), nullable=False)

    field_key = Column(String(100), nullable=False)
    field_value = Column(Text, nullable=False)
    field_type = Column(String(20), nullable=False)  # currency, date, text, number, boolean
    field_unit = Column(String(50))  # For measurements, time periods, etc.

    confidence = Column(Numeric(3, 2), nullable=False)
    provenance = Column(JSON, nullable=False)  # Where in doc this was found

    # Validation
    is_validated = Column(Boolean, default=False)
    validated_by = Column(Integer)
    validated_at = Column(DateTime)
    validation_flags = Column(JSON, default=[])

    # Derivation (if calculated from other fields)
    derived_from = Column(String(255))

    # Extraction metadata
    extractor_name = Column(String(100), nullable=False)
    extractor_version = Column(String(20), nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    document = relationship("PortalDocument", back_populates="extractions")

    __table_args__ = (
        Index('idx_extractions_document', 'document_id'),
        Index('idx_extractions_field', 'field_key'),
    )


class PropertyCosts(Base):
    """Normalized property cost data from document extractions"""
    __tablename__ = "property_costs"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), nullable=False)

    # Insurance
    annual_insurance_premium = Column(Numeric(10, 2))
    monthly_insurance_premium = Column(Numeric(10, 2))
    insurance_effective_date = Column(Date)
    insurance_expiry_date = Column(Date)
    insurance_carrier = Column(String(255))
    insurance_policy_number = Column(String(100))
    insurance_source_doc_id = Column(Integer, ForeignKey("portal_documents.id"))

    # Property Tax
    annual_property_tax = Column(Numeric(10, 2))
    monthly_property_tax = Column(Numeric(10, 2))
    tax_year = Column(Integer)
    tax_parcel_id = Column(String(100))
    tax_source_doc_id = Column(Integer, ForeignKey("portal_documents.id"))

    # HOA
    monthly_hoa = Column(Numeric(10, 2))
    hoa_source_doc_id = Column(Integer, ForeignKey("portal_documents.id"))

    # Escrow
    escrow_balance = Column(Numeric(10, 2))

    # Validity
    effective_date = Column(Date, default=date.today)
    is_current = Column(Boolean, default=True)
    superseded_by = Column(Integer, ForeignKey("property_costs.id"))

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_property_costs_loan', 'loan_id', postgresql_where=Column('is_current') == True),
    )


# =============================================================================
# HOME VALUE INTELLIGENCE
# =============================================================================

class HomePriceIndex(Base):
    """Home price index data from FHFA/Zillow"""
    __tablename__ = "home_price_index"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(20), nullable=False)  # FHFA, ZILLOW, CASE_SHILLER
    geo_type = Column(String(20), nullable=False)  # ZIP, COUNTY, MSA, STATE, NATIONAL
    geo_key = Column(String(50), nullable=False)  # ZIP code, county FIPS, etc.
    period = Column(Date, nullable=False)  # Month of the index value
    index_value = Column(Numeric, nullable=False)
    data_quality = Column(String(20), default="VERIFIED")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('provider', 'geo_type', 'geo_key', 'period', name='unique_hpi_entry'),
        Index('idx_hpi_lookup', 'provider', 'geo_type', 'geo_key', 'period'),
    )


class PropertyValueBaseline(Base):
    """Property value baseline (purchase price or appraisal)"""
    __tablename__ = "property_value_baselines"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), nullable=False)

    baseline_value = Column(Numeric, nullable=False)
    baseline_date = Column(Date, nullable=False)
    baseline_source = Column(String(50), nullable=False)  # PURCHASE_PRICE, APPRAISAL, REFINANCE_APPRAISAL, MANUAL_ENTRY
    baseline_confidence = Column(String(20), default="HIGH")  # HIGH, MEDIUM, LOW

    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    valuations = relationship("PropertyValuation", back_populates="baseline", cascade="all, delete-orphan")


class PropertyValuation(Base):
    """Monthly computed property valuations"""
    __tablename__ = "property_valuations"

    id = Column(Integer, primary_key=True, index=True)
    baseline_id = Column(Integer, ForeignKey("property_value_baselines.id", ondelete="CASCADE"), nullable=False)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), nullable=False)

    as_of_date = Column(Date, nullable=False)
    estimated_value = Column(Numeric, nullable=False)
    low_range = Column(Numeric, nullable=False)
    high_range = Column(Numeric, nullable=False)

    value_change_amount = Column(Numeric)
    value_change_percent = Column(Numeric)
    annualized_appreciation = Column(Numeric)

    confidence_level = Column(String(20), nullable=False)  # HIGH, MEDIUM, LOW
    calculation_details = Column(JSON, nullable=False)  # Index used, methodology, etc.

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    baseline = relationship("PropertyValueBaseline", back_populates="valuations")
    insights = relationship("HomeValueInsight", back_populates="valuation")

    __table_args__ = (
        UniqueConstraint('baseline_id', 'as_of_date', name='unique_valuation_date'),
        Index('idx_valuations_loan', 'loan_id', 'as_of_date'),
    )


class HomeValueInsight(Base):
    """AI-generated insights about home value"""
    __tablename__ = "home_value_insights"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), nullable=False)
    valuation_id = Column(Integer, ForeignKey("property_valuations.id"))

    insight_type = Column(String(50), nullable=False)  # VALUE_MILESTONE, EQUITY_POSITION, REFINANCE_OPPORTUNITY, HELOC_ELIGIBLE, MARKET_TREND
    priority = Column(SQLEnum(NotificationPriority), nullable=False)

    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    action_cta = Column(String(100))  # Call to action text
    action_url = Column(String(500))

    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime)
    is_dismissed = Column(Boolean, default=False)
    dismissed_at = Column(DateTime)
    expires_at = Column(DateTime)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    valuation = relationship("PropertyValuation", back_populates="insights")

    __table_args__ = (
        Index('idx_insights_loan', 'loan_id', 'created_at', postgresql_where=Column('is_dismissed') == False),
    )


# =============================================================================
# NOTIFICATIONS
# =============================================================================

class NotificationTemplate(Base):
    """Notification templates for automated messaging"""
    __tablename__ = "notification_templates"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)

    trigger_event = Column(String(100), nullable=False)
    target_role = Column(SQLEnum(PortalUserRole), nullable=False)
    channels = Column(JSON, nullable=False)  # List of NotificationChannel values
    priority = Column(SQLEnum(NotificationPriority), default=NotificationPriority.MEDIUM)

    subject_template = Column(Text)  # For email
    body_template = Column(Text, nullable=False)
    sms_template = Column(Text)  # Shorter version for SMS

    is_active = Column(Boolean, default=True)

    # Targeting
    send_to_borrower = Column(Boolean, default=True)
    send_to_coborrower = Column(Boolean, default=False)
    send_to_realtor = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class NotificationQueue(Base):
    """Queue for sending notifications"""
    __tablename__ = "notification_queue"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("notification_templates.id"))
    recipient_id = Column(Integer, nullable=False)  # User ID
    loan_id = Column(Integer, ForeignKey("portal_loans.id"))

    channel = Column(SQLEnum(NotificationChannel), nullable=False)
    priority = Column(SQLEnum(NotificationPriority), nullable=False)

    subject = Column(String(500))
    body = Column(Text, nullable=False)
    context = Column(JSON, nullable=False)  # Template variables

    status = Column(String(20), default="pending")  # pending, sent, failed, cancelled
    sent_at = Column(DateTime)
    delivery_error = Column(Text)
    external_message_id = Column(String(255))  # ID from Telnyx/SendGrid

    # Tracking
    opened_at = Column(DateTime)
    clicked_at = Column(DateTime)

    # Scheduling
    send_after = Column(DateTime)
    expires_at = Column(DateTime)
    retry_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_notifications_pending', 'status', 'send_after', postgresql_where=Column('status') == 'pending'),
        Index('idx_notifications_recipient', 'recipient_id', 'created_at'),
    )


# =============================================================================
# ACTIVITY & HEARTBEAT
# =============================================================================

class LoanActivityLog(Base):
    """Activity log for the Heartbeat feature"""
    __tablename__ = "loan_activity_log"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), nullable=False)

    activity_type = Column(String(50), nullable=False)
    activity_title = Column(String(255), nullable=False)
    activity_description = Column(Text)

    actor_id = Column(Integer)  # User ID
    actor_role = Column(SQLEnum(PortalUserRole))

    # References
    milestone_id = Column(Integer, ForeignKey("milestone_instances.id"))
    task_id = Column(Integer, ForeignKey("task_instances.id"))
    document_id = Column(Integer, ForeignKey("portal_documents.id"))

    extra_data = Column(JSON, default={})

    # Visibility
    visible_to_borrower = Column(Boolean, default=True)
    visible_to_partner = Column(Boolean, default=False)

    icon = Column(String(50))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    loan = relationship("PortalLoan", back_populates="activity_log")

    __table_args__ = (
        Index('idx_activity_loan_recent', 'loan_id', 'created_at'),
        Index('idx_activity_borrower_visible', 'loan_id', 'created_at', postgresql_where=Column('visible_to_borrower') == True),
    )


# =============================================================================
# RISK RADAR
# =============================================================================

class RiskFlag(Base):
    """Risk flags for proactive issue tracking"""
    __tablename__ = "risk_flags"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), nullable=False)

    flag_type = Column(String(50), nullable=False)
    severity = Column(SQLEnum(RiskSeverity), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    mitigation_steps = Column(JSON, default=[])  # List of steps to resolve

    # References
    milestone_id = Column(Integer, ForeignKey("milestone_instances.id"))
    document_id = Column(Integer, ForeignKey("portal_documents.id"))

    # Resolution
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)
    resolved_by = Column(Integer)
    resolution_notes = Column(Text)
    auto_resolve_condition = Column(Text)  # Condition that auto-resolves this flag

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    loan = relationship("PortalLoan", back_populates="risk_flags")

    __table_args__ = (
        Index('idx_risk_flags_active', 'loan_id', 'severity', 'created_at', postgresql_where=Column('is_resolved') == False),
    )


# =============================================================================
# PARTNER PORTAL
# =============================================================================

class PartnerAccessToken(Base):
    """Magic link tokens for partner portal access"""
    __tablename__ = "partner_access_tokens"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, nullable=False)  # Realtor/partner ID
    loan_id = Column(Integer, ForeignKey("portal_loans.id"), nullable=False)

    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False)

    last_used_at = Column(DateTime)
    use_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_partner_tokens', 'token', postgresql_where=(Column('is_revoked') == False)),
    )


# =============================================================================
# ANNUAL REFRESH
# =============================================================================

class AnnualRefreshCycle(Base):
    """Annual document refresh cycles for MUM clients"""
    __tablename__ = "annual_refresh_cycles"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(Integer, nullable=False)  # Borrower ID

    cycle_year = Column(Integer, nullable=False)
    due_date = Column(Date, nullable=False)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Document tracking
    w2_uploaded = Column(Boolean, default=False)
    w2_doc_id = Column(Integer, ForeignKey("portal_documents.id"))
    paystubs_uploaded = Column(Boolean, default=False)
    paystubs_doc_id = Column(Integer, ForeignKey("portal_documents.id"))
    tax_return_uploaded = Column(Boolean, default=False)
    tax_return_doc_id = Column(Integer, ForeignKey("portal_documents.id"))

    # Reminders sent
    reminder_60_days_sent = Column(Boolean, default=False)
    reminder_30_days_sent = Column(Boolean, default=False)
    reminder_7_days_sent = Column(Boolean, default=False)

    # Gamification
    completion_percentage = Column(Integer, default=0)
    mortgage_ready_score = Column(Integer, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('loan_id', 'cycle_year', name='unique_loan_year'),
        Index('idx_refresh_due', 'due_date', postgresql_where=Column('completed_at').is_(None)),
        Index('idx_refresh_loan', 'loan_id', 'cycle_year'),
    )


# =============================================================================
# PRESENTATION ENGINE
# =============================================================================

class PresentationSession(Base):
    """Sessions for the scenario simulator"""
    __tablename__ = "presentation_sessions"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(Integer, nullable=False)  # User viewing the presentation

    session_start = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    session_end = Column(DateTime)
    total_duration_seconds = Column(Integer)
    scenarios_explored = Column(Integer, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    scenarios = relationship("PortalPresentationScenario", back_populates="session", cascade="all, delete-orphan")


class PortalPresentationScenario(Base):
    """Individual scenarios explored in a presentation (portal version)"""
    __tablename__ = "portal_presentation_scenarios"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("presentation_sessions.id", ondelete="CASCADE"), nullable=False)
    loan_id = Column(Integer, ForeignKey("portal_loans.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(Integer, nullable=False)

    scenario_type = Column(SQLEnum(ScenarioType), nullable=False)
    params = Column(JSON, nullable=False)  # Input parameters
    results = Column(JSON, nullable=False)  # Calculated results

    view_count = Column(Integer, default=1)
    view_duration_seconds = Column(Integer)
    is_saved = Column(Boolean, default=False)
    notes = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    session = relationship("PresentationSession", back_populates="scenarios")
    citations = relationship("PresentationCitation", back_populates="scenario", cascade="all, delete-orphan")


class PresentationCitation(Base):
    """Data provenance citations for presentation values"""
    __tablename__ = "presentation_citations"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("portal_presentation_scenarios.id", ondelete="CASCADE"), nullable=False)

    metric_key = Column(String(100), nullable=False)
    metric_value = Column(Numeric)

    source_type = Column(String(20), nullable=False)  # DOCUMENT, APPRAISAL, MODEL, USER_INPUT, CRM
    source_doc_id = Column(Integer, ForeignKey("portal_documents.id"))
    source_description = Column(Text, nullable=False)
    confidence = Column(Numeric(3, 2))

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    scenario = relationship("PortalPresentationScenario", back_populates="citations")
