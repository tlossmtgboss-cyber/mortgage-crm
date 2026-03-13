"""
Income Calculation Models

Models for AI-assisted income calculation, income source breakdown, and
verification task management. Supports multi-year trending analysis,
DTI computation, and LO review workflows.

Key tables:
    income_calculations         — top-level calculation per loan/borrower
    income_sources              — individual income streams within a calculation
    income_verification_tasks   — action items for LO review and verification

Usage:
    from database.models.income_calculation import (
        IncomeCalculation,
        IncomeSource,
        IncomeVerificationTask,
        CalculationType,
        CalculationStatus,
        IncomeSourceType,
        TrendingDirection,
        VerificationStatus,
        VerificationTaskType,
        TaskPriority,
        TaskStatus,
    )
"""

from datetime import datetime, timezone
import enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import validates

from database import Base


__all__ = [
    # Enums
    "CalculationType",
    "CalculationStatus",
    "IncomeSourceType",
    "TrendingDirection",
    "VerificationStatus",
    "VerificationTaskType",
    "TaskPriority",
    "TaskStatus",
    # Models
    "IncomeCalculation",
    "IncomeSource",
    "IncomeVerificationTask",
]


# ============================================================================
# ENUMS
# ============================================================================

class CalculationType(str, enum.Enum):
    """Type of income calculation pass."""
    INITIAL = "initial"
    RECALCULATION = "recalculation"
    FINAL_VERIFICATION = "final_verification"


class CalculationStatus(str, enum.Enum):
    """Lifecycle status of an income calculation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


class IncomeSourceType(str, enum.Enum):
    """Classification of income source."""
    W2_EMPLOYMENT = "w2_employment"
    SELF_EMPLOYMENT = "self_employment"
    COMMISSION = "commission"
    BONUS = "bonus"
    OVERTIME = "overtime"
    PENSION = "pension"
    SOCIAL_SECURITY = "social_security"
    DISABILITY = "disability"
    CHILD_SUPPORT = "child_support"
    ALIMONY = "alimony"
    RENTAL = "rental"
    INVESTMENT = "investment"
    PART_TIME = "part_time"
    MILITARY = "military"
    OTHER = "other"


class TrendingDirection(str, enum.Enum):
    """Year-over-year income trending direction."""
    INCREASING = "increasing"
    STABLE = "stable"
    DECLINING = "declining"
    VARIABLE = "variable"


class VerificationStatus(str, enum.Enum):
    """Verification lifecycle for an income source."""
    UNVERIFIED = "unverified"
    PENDING_VOE = "pending_voe"
    VOE_RECEIVED = "voe_received"
    VERIFIED = "verified"
    FLAGGED = "flagged"


class VerificationTaskType(str, enum.Enum):
    """Types of income verification tasks."""
    VERIFY_EMPLOYMENT = "verify_employment"
    REQUEST_VOE = "request_voe"
    REVIEW_DECLINING_INCOME = "review_declining_income"
    REVIEW_VARIABLE_INCOME = "review_variable_income"
    REVIEW_GAP_IN_EMPLOYMENT = "review_gap_in_employment"
    REVIEW_LARGE_DEPOSIT = "review_large_deposit"
    VERIFY_SELF_EMPLOYMENT = "verify_self_employment"
    CALCULATE_RENTAL_INCOME = "calculate_rental_income"
    REVIEW_COMMISSION_TREND = "review_commission_trend"
    MANUAL_OVERRIDE_NEEDED = "manual_override_needed"


class TaskPriority(str, enum.Enum):
    """Priority levels for verification tasks."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, enum.Enum):
    """Lifecycle status of a verification task."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DEFERRED = "deferred"


# ============================================================================
# INCOME CALCULATION
# ============================================================================

class IncomeCalculation(Base):
    """Top-level income calculation for a loan/borrower pair.

    Each calculation aggregates multiple IncomeSource records to produce
    total qualifying income, DTI ratios, and AI-generated recommendations.
    A loan may have multiple calculations (initial, recalculation, final).
    """
    __tablename__ = "income_calculations"
    __table_args__ = (
        Index("ix_income_calculations_organization_id", "organization_id"),
        Index("ix_income_calculations_loan_id", "loan_id"),
        Index("ix_income_calculations_borrower_id", "borrower_id"),
        Index("ix_income_calculations_status", "status"),
        Index("ix_income_calculations_calculation_type", "calculation_type"),
        CheckConstraint(
            "dti_front_end IS NULL OR (dti_front_end >= 0 AND dti_front_end <= 100)",
            name="ck_income_calculations_dti_front_end_range",
        ),
        CheckConstraint(
            "dti_back_end IS NULL OR (dti_back_end >= 0 AND dti_back_end <= 100)",
            name="ck_income_calculations_dti_back_end_range",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True, index=True)  # ref organizations.id
    loan_id = Column(Integer, nullable=False)  # ref loans.id
    borrower_id = Column(Integer, nullable=True)  # ref leads.id

    # Calculation classification
    calculation_type = Column(
        SQLEnum(CalculationType),
        nullable=False,
        default=CalculationType.INITIAL,
    )
    status = Column(
        SQLEnum(CalculationStatus),
        nullable=False,
        default=CalculationStatus.PENDING,
    )

    # Qualifying income totals
    total_qualifying_monthly_income = Column(Numeric(15, 2))
    total_qualifying_annual_income = Column(Numeric(15, 2))

    # Calculation methodology
    calculation_method = Column(String(64))  # 'standard', 'self_employed_avg', 'variable_trending'

    # DTI ratios
    dti_front_end = Column(Numeric(5, 2))  # Front-end DTI ratio (housing / income)
    dti_back_end = Column(Numeric(5, 2))   # Back-end DTI ratio (total obligations / income)

    # Housing and obligations
    proposed_housing_expense = Column(Numeric(12, 2))
    total_monthly_obligations = Column(Numeric(12, 2))

    # AI analysis
    ai_confidence_score = Column(Integer)  # 0-100
    ai_flags = Column(JSON)  # List of AI-detected issues/flags
    ai_recommendations = Column(JSON)  # AI recommendations for LO review
    ai_model_used = Column(String(64))  # Model identifier used for calculation
    calculation_duration_ms = Column(Integer)  # Execution time in milliseconds

    # Source documents
    source_documents = Column(JSON)  # List of document IDs used in calculation

    # Who performed the calculation (user ID for maker-checker enforcement)
    calculated_by_user_id = Column(Integer, nullable=True)  # ref users.id

    # Review workflow (maker-checker: reviewer must differ from calculator)
    reviewed_by = Column(String(100))       # Display name (legacy compat)
    reviewed_by_user_id = Column(Integer, nullable=True)  # ref users.id
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)

    # Approval workflow (maker-checker: approver must differ from calculator)
    approved_by = Column(String(100))       # Display name (legacy compat)
    approved_by_user_id = Column(Integer, nullable=True)  # ref users.id
    approved_at = Column(DateTime)

    # Rejection tracking
    rejection_reason = Column(Text)
    rejected_by_user_id = Column(Integer, nullable=True)  # ref users.id

    # Audit timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @validates("dti_front_end")
    def _validate_dti_front_end(self, key, value):
        """Enforce DTI front-end ratio within 0-100."""
        if value is not None:
            val = float(value)
            if val < 0 or val > 100:
                raise ValueError(
                    f"dti_front_end must be between 0 and 100, got {val}"
                )
        return value

    @validates("dti_back_end")
    def _validate_dti_back_end(self, key, value):
        """Enforce DTI back-end ratio within 0-100."""
        if value is not None:
            val = float(value)
            if val < 0 or val > 100:
                raise ValueError(
                    f"dti_back_end must be between 0 and 100, got {val}"
                )
        return value

    def __repr__(self):
        return (
            f"<IncomeCalculation id={self.id} loan_id={self.loan_id} "
            f"type={self.calculation_type} status={self.status}>"
        )


# ============================================================================
# INCOME SOURCE
# ============================================================================

class IncomeSource(Base):
    """Individual income stream within a calculation.

    Represents a single employment or income source with base pay breakdown,
    multi-year trending analysis, and verification tracking. Multiple
    IncomeSource records roll up into one IncomeCalculation.
    """
    __tablename__ = "income_sources"
    __table_args__ = (
        Index("ix_income_sources_calculation_id", "calculation_id"),
        Index("ix_income_sources_borrower_id", "borrower_id"),
        Index("ix_income_sources_source_type", "source_type"),
        Index("ix_income_sources_verification_status", "verification_status"),
        Index("ix_income_sources_is_primary", "is_primary"),
    )

    id = Column(Integer, primary_key=True, index=True)
    calculation_id = Column(Integer, nullable=False)  # ref income_calculations.id
    borrower_id = Column(Integer, nullable=True)  # ref leads.id

    # Source classification
    source_type = Column(
        SQLEnum(IncomeSourceType),
        nullable=False,
        default=IncomeSourceType.W2_EMPLOYMENT,
    )

    # Employer / source details
    employer_name = Column(String(255))
    position_title = Column(String(255))
    employment_start_date = Column(Date)
    employment_years = Column(Numeric(4, 1))  # e.g. 3.5 years
    is_primary = Column(Boolean, default=False)

    # Monthly income breakdown
    base_monthly_income = Column(Numeric(12, 2))
    overtime_monthly = Column(Numeric(12, 2))
    bonus_monthly = Column(Numeric(12, 2))
    commission_monthly = Column(Numeric(12, 2))
    other_monthly = Column(Numeric(12, 2))

    # Totals
    total_monthly_income = Column(Numeric(12, 2))
    total_annual_income = Column(Numeric(15, 2))

    # Year-over-year trending analysis
    trending_direction = Column(SQLEnum(TrendingDirection), nullable=True)
    year1_income = Column(Numeric(15, 2))  # Most recent year
    year2_income = Column(Numeric(15, 2))  # Prior year
    year_over_year_change_pct = Column(Numeric(6, 2))  # e.g. -12.50 for 12.5% decline

    # Verification
    verification_status = Column(
        SQLEnum(VerificationStatus),
        nullable=False,
        default=VerificationStatus.UNVERIFIED,
    )
    verification_notes = Column(Text)

    # Supporting documents
    source_document_ids = Column(JSON)  # List of document IDs used for this source

    # AI analysis
    ai_confidence = Column(Integer)  # 0-100
    ai_notes = Column(Text)

    # Audit timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (
            f"<IncomeSource id={self.id} type={self.source_type} "
            f"employer={self.employer_name!r} monthly={self.total_monthly_income}>"
        )


# ============================================================================
# INCOME VERIFICATION TASK
# ============================================================================

class IncomeVerificationTask(Base):
    """Action item generated during income calculation for LO follow-up.

    Tasks are created automatically by the AI engine when it detects
    conditions that require human review — declining income, employment
    gaps, self-employment documentation needs, etc.
    """
    __tablename__ = "income_verification_tasks"
    __table_args__ = (
        Index("ix_income_verification_tasks_calculation_id", "calculation_id"),
        Index("ix_income_verification_tasks_income_source_id", "income_source_id"),
        Index("ix_income_verification_tasks_loan_id", "loan_id"),
        Index("ix_income_verification_tasks_organization_id", "organization_id"),
        Index("ix_income_verification_tasks_status", "status"),
        Index("ix_income_verification_tasks_priority", "priority"),
        Index("ix_income_verification_tasks_assigned_to", "assigned_to_user_id"),
        Index("ix_income_verification_tasks_due_date", "due_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    calculation_id = Column(Integer, nullable=False)  # ref income_calculations.id
    income_source_id = Column(Integer, nullable=True)  # ref income_sources.id
    loan_id = Column(Integer, nullable=False)  # ref loans.id
    organization_id = Column(Integer, nullable=True)  # ref organizations.id

    # Task classification
    task_type = Column(
        SQLEnum(VerificationTaskType),
        nullable=False,
    )
    title = Column(String(500), nullable=False)
    description = Column(Text)

    # Priority and status
    priority = Column(
        SQLEnum(TaskPriority),
        nullable=False,
        default=TaskPriority.MEDIUM,
    )
    status = Column(
        SQLEnum(TaskStatus),
        nullable=False,
        default=TaskStatus.OPEN,
    )

    # Assignment
    assigned_to_user_id = Column(Integer, nullable=True)  # ref users.id

    # AI guidance
    ai_recommendation = Column(Text)  # What AI suggests for this task

    # Resolution
    resolution_notes = Column(Text)
    resolved_by = Column(String(100))
    resolved_at = Column(DateTime)

    # Deadline
    due_date = Column(DateTime)

    # Audit timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (
            f"<IncomeVerificationTask id={self.id} type={self.task_type} "
            f"priority={self.priority} status={self.status}>"
        )
