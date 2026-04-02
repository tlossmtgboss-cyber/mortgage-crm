"""
Income Models for AI-Powered Income Extraction & Management

SQLAlchemy models for tracking income sources, paystub extractions,
and employment data with full underwriting calculation support.
"""

import enum
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, JSON, Enum as SQLEnum, Numeric, Index
)
from database import Base


# =============================================================================
# ENUMS
# =============================================================================

class IncomeType(str, enum.Enum):
    """Types of income sources"""
    W2_EMPLOYMENT = "W2_EMPLOYMENT"
    SELF_EMPLOYED_SCHEDULE_C = "SELF_EMPLOYED_SCHEDULE_C"
    SELF_EMPLOYED_S_CORP = "SELF_EMPLOYED_S_CORP"
    SELF_EMPLOYED_PARTNERSHIP = "SELF_EMPLOYED_PARTNERSHIP"
    CONTRACTOR_1099 = "CONTRACTOR_1099"
    RENTAL_SCHEDULE_E = "RENTAL_SCHEDULE_E"
    RETIREMENT_PENSION = "RETIREMENT_PENSION"
    SOCIAL_SECURITY = "SOCIAL_SECURITY"
    INVESTMENT_DIVIDEND = "INVESTMENT_DIVIDEND"
    BANK_STATEMENT = "BANK_STATEMENT"  # Non-QM
    ALIMONY_CHILD_SUPPORT = "ALIMONY_CHILD_SUPPORT"
    BONUS = "BONUS"
    COMMISSION = "COMMISSION"
    OVERTIME = "OVERTIME"
    OTHER = "OTHER"


class IncomeCalculationMethod(str, enum.Enum):
    """Methods for calculating qualifying income"""
    YTD_ANNUALIZED = "YTD_ANNUALIZED"
    TWO_YEAR_AVERAGE = "TWO_YEAR_AVERAGE"
    MONTHLY_AVERAGE_24 = "MONTHLY_AVERAGE_24"
    HOURLY_STANDARD = "HOURLY_STANDARD"  # rate * 2080
    HOURLY_ACTUAL = "HOURLY_ACTUAL"  # actual hours tracked
    BANK_STATEMENT_12_MONTH = "BANK_STATEMENT_12_MONTH"
    BANK_STATEMENT_24_MONTH = "BANK_STATEMENT_24_MONTH"
    SCHEDULE_E_AVERAGE = "SCHEDULE_E_AVERAGE"
    LEASE_WITH_VACANCY = "LEASE_WITH_VACANCY"
    CUSTOM = "CUSTOM"


class IncomeVerificationStatus(str, enum.Enum):
    """Verification status for income sources"""
    PENDING = "PENDING"
    DOCUMENTS_RECEIVED = "DOCUMENTS_RECEIVED"
    VERIFIED = "VERIFIED"
    NEEDS_ADDITIONAL_DOCS = "NEEDS_ADDITIONAL_DOCS"
    VERBAL_VOE_COMPLETE = "VERBAL_VOE_COMPLETE"
    WRITTEN_VOE_COMPLETE = "WRITTEN_VOE_COMPLETE"
    REJECTED = "REJECTED"


class EmploymentStatus(str, enum.Enum):
    """Employment status for tracking"""
    CURRENT = "CURRENT"
    PREVIOUS = "PREVIOUS"
    SELF_EMPLOYED = "SELF_EMPLOYED"


class PayrollFrequency(str, enum.Enum):
    """Payroll frequency for income calculations"""
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    SEMIMONTHLY = "SEMIMONTHLY"
    MONTHLY = "MONTHLY"


# =============================================================================
# INCOME SOURCE MODEL
# =============================================================================

class IncomeSource(Base):
    """
    Individual income source with complete extraction and calculation data.
    Supports unlimited income sources per borrower.
    """
    __tablename__ = "income_sources"

    id = Column(Integer, primary_key=True, index=True)

    # Relationships
    borrower_id = Column(Integer, nullable=False, index=True)  # 1=primary, 2=co-borrower
    loan_id = Column(Integer, nullable=False, index=True)
    employment_id = Column(Integer, nullable=True, index=True)  # Link to employments table

    # Income Classification
    income_type = Column(SQLEnum(IncomeType), nullable=False)
    is_primary = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Source Details
    source_name = Column(String(255))  # Employer name, property address, pension provider
    source_description = Column(Text)

    # Raw Income Amounts (from documents)
    gross_monthly_income = Column(Numeric(15, 2))
    net_monthly_income = Column(Numeric(15, 2))
    gross_annual_income = Column(Numeric(15, 2))

    # Calculated Qualifying Income (output of calculation service)
    monthly_qualifying_income = Column(Numeric(15, 2))
    annual_qualifying_income = Column(Numeric(15, 2))
    calculation_method = Column(SQLEnum(IncomeCalculationMethod))
    calculation_notes = Column(Text)
    calculation_date = Column(DateTime)

    # Raw Extracted Data (full JSON from AI extraction)
    extracted_data = Column(JSON)

    # Supporting Documents
    supporting_document_ids = Column(JSON)  # Array of SmartDocument IDs

    # Trending Analysis
    trending_direction = Column(String(20))  # increasing, stable, declining
    trending_percentage = Column(Numeric(5, 2))  # YoY change percentage
    months_history = Column(Integer)  # Number of months of history available

    # Underwriting Flags
    requires_24_month_history = Column(Boolean, default=False)
    declining_income_flag = Column(Boolean, default=False)
    variable_income_flag = Column(Boolean, default=False)
    gap_in_employment_flag = Column(Boolean, default=False)

    # Verification Status
    verification_status = Column(SQLEnum(IncomeVerificationStatus), default=IncomeVerificationStatus.PENDING)
    verified_by = Column(String(100))
    verified_at = Column(DateTime)
    verification_notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_income_sources_loan_borrower', 'loan_id', 'borrower_id'),
    )


# =============================================================================
# PAYSTUB EXTRACTION MODEL
# =============================================================================

class PaystubExtraction(Base):
    """
    Detailed paystub extraction with all required fields.
    Stores AI-extracted data from paystub documents.
    """
    __tablename__ = "paystub_extractions"

    id = Column(Integer, primary_key=True, index=True)

    # Relationships
    document_id = Column(Integer, nullable=False, index=True)  # References smart_documents.id
    income_source_id = Column(Integer, nullable=True, index=True)  # References income_sources.id
    borrower_id = Column(Integer, nullable=False, index=True)
    loan_id = Column(Integer, nullable=False, index=True)

    # === EMPLOYER INFORMATION ===
    employer_name = Column(String(255))
    employer_address_line1 = Column(String(255))
    employer_address_line2 = Column(String(255))
    employer_city = Column(String(100))
    employer_state = Column(String(2))
    employer_zip = Column(String(10))
    employer_phone = Column(String(20))
    employer_ein = Column(String(15))  # Masked in display

    # === EMPLOYEE INFORMATION ===
    employee_name = Column(String(255))
    employee_address_line1 = Column(String(255))
    employee_address_line2 = Column(String(255))
    employee_city = Column(String(100))
    employee_state = Column(String(2))
    employee_zip = Column(String(10))
    employee_ssn_last4 = Column(String(4))
    employee_id = Column(String(50))
    hire_date = Column(Date)

    # === PAY PERIOD INFORMATION ===
    pay_period_start = Column(Date)
    pay_period_end = Column(Date)
    pay_date = Column(Date, nullable=False)
    pay_frequency = Column(SQLEnum(PayrollFrequency))

    # === CURRENT PERIOD EARNINGS ===
    gross_pay = Column(Numeric(12, 2))
    net_pay = Column(Numeric(12, 2))
    regular_hours = Column(Numeric(6, 2))
    overtime_hours = Column(Numeric(6, 2))
    hourly_rate = Column(Numeric(8, 2))
    regular_earnings = Column(Numeric(12, 2))
    overtime_earnings = Column(Numeric(12, 2))
    bonus = Column(Numeric(12, 2))
    commission = Column(Numeric(12, 2))
    tips = Column(Numeric(12, 2))
    other_earnings = Column(Numeric(12, 2))

    # === YEAR-TO-DATE TOTALS ===
    ytd_gross = Column(Numeric(15, 2))
    ytd_net = Column(Numeric(15, 2))
    ytd_regular_earnings = Column(Numeric(15, 2))
    ytd_overtime_earnings = Column(Numeric(15, 2))
    ytd_bonus = Column(Numeric(15, 2))
    ytd_commission = Column(Numeric(15, 2))
    ytd_tips = Column(Numeric(15, 2))

    # === CURRENT PERIOD DEDUCTIONS ===
    federal_tax = Column(Numeric(10, 2))
    state_tax = Column(Numeric(10, 2))
    local_tax = Column(Numeric(10, 2))
    social_security = Column(Numeric(10, 2))
    medicare = Column(Numeric(10, 2))
    health_insurance = Column(Numeric(10, 2))
    dental_insurance = Column(Numeric(10, 2))
    vision_insurance = Column(Numeric(10, 2))
    life_insurance = Column(Numeric(10, 2))
    retirement_401k = Column(Numeric(10, 2))
    hsa_fsa = Column(Numeric(10, 2))
    other_deductions = Column(Numeric(10, 2))
    deductions_breakdown = Column(JSON)  # Detailed breakdown

    # === YTD DEDUCTIONS ===
    ytd_federal_tax = Column(Numeric(15, 2))
    ytd_state_tax = Column(Numeric(15, 2))
    ytd_social_security = Column(Numeric(15, 2))
    ytd_medicare = Column(Numeric(15, 2))
    ytd_retirement = Column(Numeric(15, 2))

    # === CALCULATED FIELDS ===
    calculated_annual_income = Column(Numeric(15, 2))
    calculated_monthly_income = Column(Numeric(15, 2))
    annualization_method = Column(String(50))  # YTD extrapolation, period * frequency

    # === EXTRACTION METADATA ===
    extraction_confidence = Column(Integer)  # 0-100 overall confidence
    field_confidences = Column(JSON)  # Per-field confidence scores
    extraction_model = Column(String(64))
    raw_ocr_text = Column(Text)
    extraction_warnings = Column(JSON)
    extraction_errors = Column(JSON)

    # === DOCUMENT FRESHNESS ===
    doc_date = Column(Date)  # Typically same as pay_date
    expires_at = Column(Date)  # Based on pay frequency
    is_expired = Column(Boolean, default=False)

    # === APPLICATION STATUS ===
    applied_to_profile = Column(Boolean, default=False)
    applied_at = Column(DateTime)
    applied_by = Column(String(100))
    applied_fields = Column(JSON)  # Which fields were applied

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_paystub_loan_borrower', 'loan_id', 'borrower_id'),
    )


# =============================================================================
# EMPLOYMENT MODEL
# =============================================================================

class Employment(Base):
    """
    Employment record extracted from paystubs and verified.
    Used to populate Employment tab in client profile.
    """
    __tablename__ = "employments"

    id = Column(Integer, primary_key=True, index=True)

    # Relationships
    borrower_id = Column(Integer, nullable=False, index=True)
    loan_id = Column(Integer, nullable=False, index=True)

    # === EMPLOYER INFORMATION ===
    employer_name = Column(String(255), nullable=False)
    employer_address_line1 = Column(String(255))
    employer_address_line2 = Column(String(255))
    employer_city = Column(String(100))
    employer_state = Column(String(2))
    employer_zip = Column(String(10))
    employer_phone = Column(String(20))
    employer_ein = Column(String(15))
    employer_website = Column(String(255))

    # === EMPLOYMENT DETAILS ===
    status = Column(SQLEnum(EmploymentStatus), default=EmploymentStatus.CURRENT)
    job_title = Column(String(255))
    department = Column(String(255))
    start_date = Column(Date)
    end_date = Column(Date)  # NULL for current employment
    years_employed = Column(Numeric(4, 2))  # Calculated
    months_employed = Column(Integer)  # Calculated
    years_in_profession = Column(Numeric(4, 2))

    # === COMPENSATION STRUCTURE ===
    is_salaried = Column(Boolean, default=True)
    is_hourly = Column(Boolean, default=False)
    has_overtime = Column(Boolean, default=False)
    has_bonus = Column(Boolean, default=False)
    has_commission = Column(Boolean, default=False)
    pay_frequency = Column(SQLEnum(PayrollFrequency))

    # === INCOME SUMMARY (from most recent paystub) ===
    current_base_salary = Column(Numeric(12, 2))
    hourly_rate = Column(Numeric(8, 2))
    average_hours_per_week = Column(Numeric(4, 1))
    monthly_income = Column(Numeric(12, 2))
    annual_income = Column(Numeric(15, 2))

    # === VERIFICATION ===
    verification_status = Column(SQLEnum(IncomeVerificationStatus), default=IncomeVerificationStatus.PENDING)
    verified_by_voe = Column(Boolean, default=False)
    voe_type = Column(String(50))  # verbal, written, electronic
    voe_date = Column(Date)
    voe_contact_name = Column(String(255))
    voe_contact_phone = Column(String(20))
    voe_contact_email = Column(String(255))

    # === SOURCE TRACKING ===
    source_document_ids = Column(JSON)  # Paystub IDs that contributed
    first_seen_at = Column(DateTime)
    last_updated_from_paystub_at = Column(DateTime)
    last_paystub_id = Column(Integer)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_employments_loan_borrower', 'loan_id', 'borrower_id'),
    )


# =============================================================================
# SELF-EMPLOYMENT INCOME MODEL
# =============================================================================

class SelfEmploymentIncome(Base):
    """
    Self-employment income from tax returns and P&L statements.
    Supports Schedule C, S-Corp K-1, Partnership K-1.
    """
    __tablename__ = "self_employment_income"

    id = Column(Integer, primary_key=True, index=True)

    # Relationships
    income_source_id = Column(Integer, nullable=False, index=True)
    borrower_id = Column(Integer, nullable=False, index=True)
    loan_id = Column(Integer, nullable=False, index=True)

    # Business Information
    business_name = Column(String(255))
    business_type = Column(String(50))  # sole_prop, s_corp, partnership, llc
    business_ein = Column(String(15))
    business_address = Column(Text)
    business_phone = Column(String(20))
    ownership_percentage = Column(Numeric(5, 2))  # 0-100
    years_in_business = Column(Numeric(4, 2))

    # Tax Year Data
    tax_year = Column(Integer, nullable=False)

    # Schedule C / Business Income
    gross_receipts = Column(Numeric(15, 2))
    cost_of_goods_sold = Column(Numeric(15, 2))
    gross_profit = Column(Numeric(15, 2))
    total_expenses = Column(Numeric(15, 2))
    net_profit_loss = Column(Numeric(15, 2))

    # Non-Cash Expense Add-Backs
    depreciation_addback = Column(Numeric(15, 2))
    amortization_addback = Column(Numeric(15, 2))
    depletion_addback = Column(Numeric(15, 2))
    business_use_of_home = Column(Numeric(15, 2))
    meals_entertainment_addback = Column(Numeric(15, 2))

    # K-1 Data (for S-Corp/Partnership)
    k1_ordinary_income = Column(Numeric(15, 2))
    k1_guaranteed_payments = Column(Numeric(15, 2))
    k1_distributions = Column(Numeric(15, 2))
    k1_section_179 = Column(Numeric(15, 2))

    # Calculated Qualifying Income
    adjusted_business_income = Column(Numeric(15, 2))
    qualifying_income_for_year = Column(Numeric(15, 2))

    # Source Documents
    source_document_ids = Column(JSON)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_self_employment_income_source', 'income_source_id', 'tax_year'),
    )


# =============================================================================
# RENTAL INCOME MODEL
# =============================================================================

class RentalIncomeProperty(Base):
    """
    Rental income from Schedule E properties.
    Supports multiple properties per borrower.
    """
    __tablename__ = "rental_income_properties"

    id = Column(Integer, primary_key=True, index=True)

    # Relationships
    income_source_id = Column(Integer, nullable=False, index=True)
    borrower_id = Column(Integer, nullable=False, index=True)
    loan_id = Column(Integer, nullable=False, index=True)

    # Property Information
    property_address_line1 = Column(String(255), nullable=False)
    property_address_line2 = Column(String(255))
    property_city = Column(String(100))
    property_state = Column(String(2))
    property_zip = Column(String(10))
    property_type = Column(String(50))  # sfr, multi_2_4, commercial
    number_of_units = Column(Integer, default=1)

    # Tax Year Data (from Schedule E)
    tax_year = Column(Integer)
    schedule_e_gross_rents = Column(Numeric(15, 2))
    schedule_e_total_expenses = Column(Numeric(15, 2))
    schedule_e_depreciation = Column(Numeric(15, 2))
    schedule_e_net_income_loss = Column(Numeric(15, 2))

    # Lease Information (current)
    current_monthly_rent = Column(Numeric(12, 2))
    lease_start_date = Column(Date)
    lease_end_date = Column(Date)
    tenant_name = Column(String(255))
    security_deposit = Column(Numeric(12, 2))

    # PITIA (for subject property offset)
    monthly_mortgage_payment = Column(Numeric(12, 2))
    monthly_taxes = Column(Numeric(12, 2))
    monthly_insurance = Column(Numeric(12, 2))
    monthly_hoa = Column(Numeric(12, 2))

    # Calculation Parameters
    vacancy_factor = Column(Numeric(5, 2), default=25.0)  # 25% default
    use_schedule_e = Column(Boolean, default=True)  # vs lease

    # Calculated Values
    monthly_qualifying_income = Column(Numeric(12, 2))
    annual_qualifying_income = Column(Numeric(15, 2))
    net_rental_income = Column(Numeric(12, 2))  # After PITIA offset if subject

    # Flags
    is_subject_property = Column(Boolean, default=False)
    is_departing_residence = Column(Boolean, default=False)

    # Source Documents
    source_document_ids = Column(JSON)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# =============================================================================
# INCOME CALCULATION HISTORY
# =============================================================================

class IncomeCalculationHistory(Base):
    """
    Audit trail for income calculations.
    Tracks all calculation runs and their results.
    """
    __tablename__ = "income_calculation_history"

    id = Column(Integer, primary_key=True, index=True)

    # Relationships
    income_source_id = Column(Integer, nullable=False, index=True)
    loan_id = Column(Integer, nullable=False, index=True)

    # Calculation Details
    calculation_method = Column(SQLEnum(IncomeCalculationMethod))
    input_data = Column(JSON)  # Data used for calculation
    calculation_steps = Column(JSON)  # Step-by-step breakdown

    # Results
    monthly_qualifying_income = Column(Numeric(15, 2))
    annual_qualifying_income = Column(Numeric(15, 2))

    # Flags Applied
    declining_income_adjustment = Column(Boolean, default=False)
    variable_income_adjustment = Column(Boolean, default=False)

    # Metadata
    calculated_by = Column(String(100))  # system or user email
    calculation_notes = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
