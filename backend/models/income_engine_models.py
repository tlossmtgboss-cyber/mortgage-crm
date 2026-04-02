"""
Income Intelligence Engine Models

SQLAlchemy models for the Automated Income Intelligence Engine.
These models store calculated income results from the orchestrator.

Tables:
- IncomeSummary: Single source of truth for calculated qualifying income
- IncomeCalculationDetail: Detailed breakdown per income stream (audit trail)
- IncomeFlag: Conditions, warnings, and required actions
- MileageDepreciationRate: IRS mileage rate configuration
- IncomeWorksheet: Generated Excel worksheet tracking
"""

import enum
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, JSON, Enum as SQLEnum, Numeric, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from database import Base


# =============================================================================
# ENUMS
# =============================================================================

class FlagSeverity(str, enum.Enum):
    """Severity levels for income flags."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKING = "BLOCKING"


class SummaryStatus(str, enum.Enum):
    """Status of income summary."""
    CALCULATING = "CALCULATING"
    CALCULATED = "CALCULATED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    STALE = "STALE"  # Source documents updated, needs recalc


class WorksheetType(str, enum.Enum):
    """Types of generated worksheets."""
    ENACT_RENTAL = "ENACT_RENTAL"
    ENACT_1084 = "ENACT_1084"
    ENACT_SCHEDULE_C = "ENACT_SCHEDULE_C"
    ENACT_K1 = "ENACT_K1"
    INCOME_SUMMARY = "INCOME_SUMMARY"
    FULL_WORKBOOK = "FULL_WORKBOOK"


class StreamType(str, enum.Enum):
    """Types of income streams."""
    W2_BASE = "W2_BASE"
    W2_OVERTIME = "W2_OVERTIME"
    W2_BONUS = "W2_BONUS"
    W2_COMMISSION = "W2_COMMISSION"
    SCHEDULE_C = "SCHEDULE_C"
    SCHEDULE_E_RENTAL = "SCHEDULE_E_RENTAL"
    K1_PARTNERSHIP = "K1_PARTNERSHIP"
    K1_SCORP = "K1_SCORP"
    K1_CCORP = "K1_CCORP"
    BANK_STATEMENT = "BANK_STATEMENT"
    SOCIAL_SECURITY = "SOCIAL_SECURITY"
    PENSION = "PENSION"
    ALIMONY = "ALIMONY"
    CHILD_SUPPORT = "CHILD_SUPPORT"
    OTHER = "OTHER"


class ResolutionType(str, enum.Enum):
    """How a flag was resolved."""
    DOCUMENTATION_PROVIDED = "DOCUMENTATION_PROVIDED"
    EXPLANATION_ACCEPTED = "EXPLANATION_ACCEPTED"
    RECALCULATED = "RECALCULATED"
    WAIVED_BY_INVESTOR = "WAIVED_BY_INVESTOR"
    MANUALLY_OVERRIDDEN = "MANUALLY_OVERRIDDEN"
    AUTO_RESOLVED = "AUTO_RESOLVED"


# =============================================================================
# INCOME SUMMARY MODEL (Single Source of Truth)
# =============================================================================

class IncomeSummary(Base):
    """
    Single source of truth for calculated qualifying income.
    Output of the Income Intelligence Engine orchestrator.
    """
    __tablename__ = "income_summaries"

    id = Column(Integer, primary_key=True, index=True)

    # Foreign keys
    loan_id = Column(Integer, nullable=False, index=True)
    borrower_id = Column(Integer, nullable=False, index=True)

    # Summary amounts
    total_monthly_income = Column(Numeric(15, 2), nullable=False, default=0)
    total_annual_income = Column(Numeric(15, 2), nullable=False, default=0)

    # Ruleset version (for reproducibility)
    ruleset_version = Column(String(50), nullable=False, default='2025.1')

    # Full JSON payloads
    income_streams = Column(JSON, nullable=False, default=list)
    source_documents = Column(JSON, nullable=False, default=list)

    # Approvability summary
    is_approvable = Column(Boolean, nullable=False, default=False)
    blocking_flags_count = Column(Integer, nullable=False, default=0)
    error_flags_count = Column(Integer, nullable=False, default=0)
    warning_flags_count = Column(Integer, nullable=False, default=0)
    info_flags_count = Column(Integer, nullable=False, default=0)

    # Calculation metadata
    calculated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    calculated_by = Column(Integer, nullable=True)  # User ID or NULL for system
    calculation_duration_ms = Column(Integer, nullable=True)

    # Status tracking
    status = Column(String(50), nullable=False, default='CALCULATED')
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(Integer, nullable=True)
    review_notes = Column(Text, nullable=True)

    # Investor/program context
    investor_code = Column(String(50), nullable=True)
    program_code = Column(String(50), nullable=True)

    # Audit timestamps
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    calculation_details = relationship("IncomeCalculationDetail", back_populates="summary", cascade="all, delete-orphan")
    flags = relationship("IncomeFlag", back_populates="summary", cascade="all, delete-orphan")
    worksheets = relationship("IncomeWorksheet", back_populates="summary", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_income_summaries_loan_borrower', 'loan_id', 'borrower_id'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'loan_id': self.loan_id,
            'borrower_id': self.borrower_id,
            'total_monthly_income': float(self.total_monthly_income) if self.total_monthly_income else 0,
            'total_annual_income': float(self.total_annual_income) if self.total_annual_income else 0,
            'ruleset_version': self.ruleset_version,
            'income_streams': self.income_streams,
            'source_documents': self.source_documents,
            'is_approvable': self.is_approvable,
            'flags_summary': {
                'blocking': self.blocking_flags_count,
                'errors': self.error_flags_count,
                'warnings': self.warning_flags_count,
                'info': self.info_flags_count,
            },
            'status': self.status,
            'calculated_at': self.calculated_at.isoformat() if self.calculated_at else None,
            'investor_code': self.investor_code,
            'program_code': self.program_code,
        }


# =============================================================================
# INCOME CALCULATION DETAIL MODEL (Audit Trail)
# =============================================================================

class IncomeCalculationDetail(Base):
    """
    Detailed calculation breakdown per income stream.
    Provides complete audit trail for compliance.
    """
    __tablename__ = "income_calculation_details"

    id = Column(Integer, primary_key=True, index=True)

    income_summary_id = Column(Integer, ForeignKey('income_summaries.id', ondelete='CASCADE'), nullable=False)

    # Income stream identification
    stream_type = Column(String(100), nullable=False)
    stream_name = Column(String(255), nullable=True)  # e.g., "ABC Company" or "123 Main St Rental"

    # Calculated amounts
    monthly_income = Column(Numeric(15, 2), nullable=False, default=0)
    annual_income = Column(Numeric(15, 2), nullable=True)

    # Calculation breakdown (full audit trail)
    calculation_inputs = Column(JSON, nullable=False, default=dict)  # Raw inputs used
    calculation_steps = Column(JSON, nullable=False, default=list)   # Step-by-step formula
    add_backs = Column(JSON, nullable=True)                          # Depreciation, mileage, etc.
    subtractions = Column(JSON, nullable=True)                       # Business use of home, etc.

    # Source document reference
    document_id = Column(String(255), nullable=True)
    document_type = Column(String(100), nullable=True)
    tax_year = Column(Integer, nullable=True)

    # Trending analysis
    trending_direction = Column(String(20), nullable=True)  # increasing, stable, declining
    trending_percentage = Column(Numeric(8, 4), nullable=True)  # e.g., -0.0523 for -5.23%

    # Flags specific to this stream
    stream_flags = Column(JSON, nullable=True, default=list)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationship
    summary = relationship("IncomeSummary", back_populates="calculation_details")

    __table_args__ = (
        Index('ix_income_calc_details_summary_type', 'income_summary_id', 'stream_type'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'stream_type': self.stream_type,
            'stream_name': self.stream_name,
            'monthly_income': float(self.monthly_income) if self.monthly_income else 0,
            'annual_income': float(self.annual_income) if self.annual_income else None,
            'calculation_inputs': self.calculation_inputs,
            'calculation_steps': self.calculation_steps,
            'add_backs': self.add_backs,
            'subtractions': self.subtractions,
            'document_id': self.document_id,
            'document_type': self.document_type,
            'tax_year': self.tax_year,
            'trending_direction': self.trending_direction,
            'trending_percentage': float(self.trending_percentage) if self.trending_percentage else None,
            'stream_flags': self.stream_flags,
        }


# =============================================================================
# INCOME FLAG MODEL (Conditions & Required Actions)
# =============================================================================

class IncomeFlag(Base):
    """
    Conditions, warnings, and required actions from income calculation.
    Automatically generated by calculation engines.
    """
    __tablename__ = "income_flags"

    id = Column(Integer, primary_key=True, index=True)

    income_summary_id = Column(Integer, ForeignKey('income_summaries.id', ondelete='CASCADE'), nullable=False)

    # Flag details
    rule_id = Column(String(100), nullable=False)  # e.g., 'RENTAL_LOSS', 'MILEAGE_RATE_NOT_CONFIGURED'
    severity = Column(String(50), nullable=False)  # INFO, WARNING, ERROR, BLOCKING
    message = Column(Text, nullable=False)
    required_action = Column(Text, nullable=True)

    # Context
    affected_stream = Column(String(100), nullable=True)  # Which income stream this applies to
    affected_document_id = Column(String(255), nullable=True)

    # Flag metadata (additional context)
    # Note: renamed from 'metadata' to avoid SQLAlchemy 2.0 reserved attribute conflict
    flag_metadata = Column(JSON, nullable=True, default=dict)

    # Resolution tracking
    resolved = Column(Boolean, nullable=False, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    resolution_type = Column(String(50), nullable=True)

    # Auto-condition creation
    condition_created = Column(Boolean, nullable=False, default=False)
    condition_id = Column(Integer, nullable=True)  # Reference to loan_conditions table

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationship
    summary = relationship("IncomeSummary", back_populates="flags")

    __table_args__ = (
        Index('ix_income_flags_summary_severity', 'income_summary_id', 'severity'),
        Index('ix_income_flags_unresolved', 'income_summary_id', 'resolved'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'rule_id': self.rule_id,
            'severity': self.severity,
            'message': self.message,
            'required_action': self.required_action,
            'affected_stream': self.affected_stream,
            'affected_document_id': self.affected_document_id,
            'metadata': self.flag_metadata,
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'resolution_notes': self.resolution_notes,
            'resolution_type': self.resolution_type,
            'condition_created': self.condition_created,
            'condition_id': self.condition_id,
        }


# =============================================================================
# MILEAGE DEPRECIATION RATE MODEL (Configuration)
# =============================================================================

class MileageDepreciationRate(Base):
    """
    Year-keyed IRS mileage depreciation rates.
    Used by Schedule C engine for mileage add-back calculation.
    """
    __tablename__ = "mileage_depreciation_rates"

    id = Column(Integer, primary_key=True, index=True)

    tax_year = Column(Integer, nullable=False, unique=True, index=True)
    rate_per_mile = Column(Numeric(6, 4), nullable=False)  # e.g., 0.28 for $0.28/mile

    # Source documentation
    source = Column(String(255), nullable=False)  # e.g., "IRS Notice 2024-08"
    source_url = Column(Text, nullable=True)
    effective_date = Column(Date, nullable=False)

    # Notes
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(Integer, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'tax_year': self.tax_year,
            'rate_per_mile': float(self.rate_per_mile) if self.rate_per_mile else 0,
            'source': self.source,
            'source_url': self.source_url,
            'effective_date': self.effective_date.isoformat() if self.effective_date else None,
            'notes': self.notes,
        }


# =============================================================================
# INCOME WORKSHEET MODEL (Generated Excel Tracking)
# =============================================================================

class IncomeWorksheet(Base):
    """
    Tracks generated Excel worksheets from income calculations.
    Supports Enact templates and custom summary reports.
    """
    __tablename__ = "income_worksheets"

    id = Column(Integer, primary_key=True, index=True)

    income_summary_id = Column(Integer, ForeignKey('income_summaries.id', ondelete='CASCADE'), nullable=False)

    # Worksheet details
    worksheet_type = Column(String(100), nullable=False)  # ENACT_RENTAL, INCOME_SUMMARY, etc.
    template_version = Column(String(50), nullable=True)

    # File storage
    file_path = Column(Text, nullable=False)
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)  # bytes
    s3_bucket = Column(String(255), nullable=True)
    s3_key = Column(Text, nullable=True)

    # Generation metadata
    generated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    generated_by = Column(Integer, nullable=True)
    generation_duration_ms = Column(Integer, nullable=True)

    # Download tracking
    download_count = Column(Integer, nullable=False, default=0)
    last_downloaded_at = Column(DateTime, nullable=True)
    last_downloaded_by = Column(Integer, nullable=True)

    # Relationship
    summary = relationship("IncomeSummary", back_populates="worksheets")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'worksheet_type': self.worksheet_type,
            'template_version': self.template_version,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'generated_at': self.generated_at.isoformat() if self.generated_at else None,
            'download_count': self.download_count,
            'download_url': f"/api/v1/income/worksheets/{self.id}/download",
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_mileage_rate(db, tax_year: int) -> Optional[float]:
    """
    Get mileage depreciation rate for a tax year.
    Returns None if not configured (should trigger BLOCKING flag).
    """
    rate = db.query(MileageDepreciationRate).filter(
        MileageDepreciationRate.tax_year == tax_year
    ).first()

    if rate:
        return float(rate.rate_per_mile)
    return None


def create_income_flag(
    rule_id: str,
    severity: str,
    message: str,
    required_action: Optional[str] = None,
    affected_stream: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Helper function to create standardized flag dictionary.
    Used by calculation engines.
    """
    return {
        'rule_id': rule_id,
        'severity': severity,
        'message': message,
        'required_action': required_action,
        'affected_stream': affected_stream,
        'metadata': metadata or {},
    }


# =============================================================================
# COMMON FLAG RULE IDS (for reference)
# =============================================================================

class FlagRuleId:
    """Standard flag rule IDs used by calculation engines."""

    # Rental Income
    RENTAL_LOSS = "RENTAL_LOSS"
    RENTAL_INCOME_DECLINING = "RENTAL_INCOME_DECLINING"
    RENTAL_NO_SCHEDULE_E = "RENTAL_NO_SCHEDULE_E"

    # Schedule C
    SCHEDULE_C_LOSS = "SCHEDULE_C_LOSS"
    SCHEDULE_C_INCOME_DECLINING = "SCHEDULE_C_INCOME_DECLINING"
    MILEAGE_RATE_NOT_CONFIGURED = "MILEAGE_RATE_NOT_CONFIGURED"
    HOME_OFFICE_DEDUCTION = "HOME_OFFICE_DEDUCTION"

    # Bank Statement
    BANK_12MO_DECLINE_REQUIRES_24MO = "BANK_12MO_DECLINE_REQUIRES_24MO"
    BANK_24MO_DECLINE_EXPLANATION = "BANK_24MO_DECLINE_EXPLANATION"
    BANK_24MO_DECLINE_INELIGIBLE = "BANK_24MO_DECLINE_INELIGIBLE"
    BANK_INSUFFICIENT_MONTHS = "BANK_INSUFFICIENT_MONTHS"

    # K-1
    K1_NO_DISTRIBUTIONS_OR_LIQUIDITY = "K1_NO_DISTRIBUTIONS_OR_LIQUIDITY"
    K1_OWNERSHIP_BELOW_25 = "K1_OWNERSHIP_BELOW_25"
    CCORP_NOT_100_PERCENT = "CCORP_NOT_100_PERCENT"

    # W-2
    W2_VARIABLE_INCOME_DECLINING = "W2_VARIABLE_INCOME_DECLINING"
    W2_NO_DOCUMENTED_HOURS = "W2_NO_DOCUMENTED_HOURS"
    W2_INSUFFICIENT_HISTORY = "W2_INSUFFICIENT_HISTORY"

    # General
    DOCUMENT_EXPIRED = "DOCUMENT_EXPIRED"
    MISSING_REQUIRED_DOCUMENT = "MISSING_REQUIRED_DOCUMENT"
    CALCULATION_ERROR = "CALCULATION_ERROR"
