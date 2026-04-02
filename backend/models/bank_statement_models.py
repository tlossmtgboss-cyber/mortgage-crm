"""
Bank Statement Extraction Models

Models for storing bank statement data extracted by AI for Non-QM income calculation.
Supports personal and business bank statements with multiple calculation methods.
"""

import enum
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, JSON, Enum as SQLEnum, Numeric, Index
)

from database import Base


class StatementType(str, enum.Enum):
    """Type of bank statement"""
    PERSONAL = "PERSONAL"
    BUSINESS = "BUSINESS"


class CalculationMethod(str, enum.Enum):
    """Business income calculation method"""
    UNIFORM_EXPENSE_RATIO = "UNIFORM_EXPENSE_RATIO"  # Method 1: Standard 50%/60% ratio
    CPA_PL = "CPA_PL"  # Method 2: CPA Prepared P&L
    CPA_EXPENSE_RATIO = "CPA_EXPENSE_RATIO"  # Method 3: CPA Letter Expense Ratio


class ExtractionStatus(str, enum.Enum):
    """Status of bank statement extraction"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class BankStatementWorksheet(Base):
    """
    Main worksheet record linking all bank statement data for a loan.
    One worksheet per loan/borrower combination.
    """
    __tablename__ = "bank_statement_worksheets"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, nullable=False, index=True)
    borrower_id = Column(Integer, nullable=False, index=True)

    # Borrower Info
    borrower_name = Column(String(255), nullable=True)

    # Business Info (for business statements)
    business_name = Column(String(255), nullable=True)
    ownership_percentage = Column(Numeric(5, 2), nullable=True)  # e.g., 100.00 for 100%

    # Calculation Settings
    months_of_statements = Column(Integer, default=12)  # 12 or 24
    calculation_method = Column(SQLEnum(CalculationMethod), default=CalculationMethod.UNIFORM_EXPENSE_RATIO)
    cpa_expense_ratio = Column(Numeric(5, 2), nullable=True)  # For Method 3
    ltv_percentage = Column(Numeric(5, 2), nullable=True)  # For determining expense ratio

    # Has separate business account?
    has_separate_business_account = Column(Boolean, default=False)

    # Results Summary
    total_eligible_deposits_personal = Column(Numeric(15, 2), default=0)
    total_eligible_deposits_business = Column(Numeric(15, 2), default=0)
    calculated_monthly_income = Column(Numeric(15, 2), nullable=True)
    calculated_annual_income = Column(Numeric(15, 2), nullable=True)

    # Status
    status = Column(SQLEnum(ExtractionStatus), default=ExtractionStatus.PENDING)
    extraction_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_worksheet_loan_borrower', 'loan_id', 'borrower_id'),
    )


class BankStatementAccount(Base):
    """
    Bank account information for a worksheet.
    One worksheet can have multiple accounts (personal + business).
    """
    __tablename__ = "bank_statement_accounts"

    id = Column(Integer, primary_key=True, index=True)
    worksheet_id = Column(Integer, nullable=False, index=True)

    # Account Info
    statement_type = Column(SQLEnum(StatementType), nullable=False)
    bank_name = Column(String(255), nullable=True)
    account_last_four = Column(String(4), nullable=True)

    # Document reference
    document_ids = Column(JSON, default=list)  # List of SmartDocument IDs

    # Extraction status for this account
    extraction_status = Column(SQLEnum(ExtractionStatus), default=ExtractionStatus.PENDING)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class BankStatementMonth(Base):
    """
    Monthly bank statement data extracted from documents.
    12 records per account (or 24 for 24-month programs).
    """
    __tablename__ = "bank_statement_months"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, nullable=False, index=True)
    worksheet_id = Column(Integer, nullable=False, index=True)

    # Month Info
    month_number = Column(Integer, nullable=False)  # 1-12 (or 1-24), 1 = most recent
    statement_month = Column(String(20), nullable=True)  # "January", "February", etc.
    statement_end_date = Column(Date, nullable=True)

    # Financial Data
    total_deposits = Column(Numeric(15, 2), default=0)
    ineligible_deposits = Column(Numeric(15, 2), default=0)
    eligible_deposits = Column(Numeric(15, 2), default=0)
    beginning_balance = Column(Numeric(15, 2), default=0)
    ending_balance = Column(Numeric(15, 2), default=0)
    nsf_count = Column(Integer, default=0)

    # Extraction metadata
    source_document_id = Column(Integer, nullable=True)  # SmartDocument ID
    extraction_confidence = Column(Float, nullable=True)  # 0-100
    manually_verified = Column(Boolean, default=False)
    verification_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_month_account', 'account_id'),
        Index('idx_month_worksheet', 'worksheet_id'),
    )


class BankStatementIneligibleItem(Base):
    """
    Tracks ineligible deposits that were excluded from income calculation.
    Used for audit trail and review.
    """
    __tablename__ = "bank_statement_ineligible_items"

    id = Column(Integer, primary_key=True, index=True)
    month_id = Column(Integer, nullable=False, index=True)

    # Transaction details
    transaction_date = Column(Date, nullable=True)
    description = Column(Text, nullable=True)
    amount = Column(Numeric(15, 2), nullable=False)

    # Reason for ineligibility
    reason = Column(String(255), nullable=True)  # "Transfer", "Loan", "One-time", etc.

    # AI confidence
    ai_flagged = Column(Boolean, default=True)
    confidence = Column(Float, nullable=True)

    # Manual override
    manually_reviewed = Column(Boolean, default=False)
    override_eligible = Column(Boolean, default=False)  # If user marks as eligible
    reviewer_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
