"""
Document Extraction Model

Stores AI extraction results from document parsing.
Includes extracted fields, confidence scores, provenance, and owner detection.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, JSON, Index,
    Enum as SQLEnum
)

from database import Base


class ReviewStatus(str, enum.Enum):
    """Status of extraction review"""
    PENDING = "PENDING"
    REVIEWED = "REVIEWED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"


class DetectedOwner(str, enum.Enum):
    """Detected document owner"""
    BORROWER = "BORROWER"
    CO_BORROWER = "CO_BORROWER"
    UNKNOWN = "UNKNOWN"


class SmartDocumentExtraction(Base):
    """
    Stores extraction results for document review.

    Each SmartDocument can have one extraction result that contains:
    - Extracted field values from AI/OCR processing
    - Confidence scores per field
    - Provenance snippets showing source text
    - Detected document owner with match confidence
    - Review status and applied field tracking
    """
    __tablename__ = "smart_document_extractions"

    id = Column(Integer, primary_key=True, index=True)

    # Reference to the document (foreign key omitted for flexibility)
    document_id = Column(Integer, nullable=False)  # References smart_documents.id

    # Extraction results
    extracted_fields = Column(JSON, nullable=True)  # {field_name: value}
    confidence_scores = Column(JSON, nullable=True)  # {field_name: 0-100}
    provenance = Column(JSON, nullable=True)  # {field_name: source_text_snippet}

    # Field mapping info
    mappable_fields = Column(JSON, nullable=True)  # List of fields that can map to Lead/Loan
    field_categories = Column(JSON, nullable=True)  # {field_name: category} for grouping

    # Owner detection
    detected_owner = Column(SQLEnum(DetectedOwner), default=DetectedOwner.UNKNOWN)
    owner_confidence = Column(Integer, nullable=True)  # 0-100
    owner_match_details = Column(JSON, nullable=True)  # Details about the match

    # Overall extraction confidence
    overall_confidence = Column(Integer, nullable=True)  # 0-100
    extraction_model = Column(String(64), nullable=True)  # e.g., 'claude-sonnet-4-20250514'
    extraction_duration_ms = Column(Integer, nullable=True)

    # Review status
    review_status = Column(SQLEnum(ReviewStatus), default=ReviewStatus.PENDING)
    reviewed_by = Column(String(100), nullable=True)  # User ID or 'SYSTEM'
    reviewed_at = Column(DateTime, nullable=True)

    # Applied changes tracking
    applied_fields = Column(JSON, nullable=True)  # Fields that were applied to Lead/Loan
    applied_to_profile_type = Column(String(20), nullable=True)  # 'lead' or 'loan'
    applied_to_profile_id = Column(Integer, nullable=True)
    applied_at = Column(DateTime, nullable=True)

    # Error tracking
    extraction_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Indexes
    __table_args__ = (
        Index("ix_smart_doc_extractions_document_id", "document_id"),
        Index("ix_smart_doc_extractions_review_status", "review_status"),
        Index("ix_smart_doc_extractions_detected_owner", "detected_owner"),
        Index("ix_smart_doc_extractions_created_at", "created_at"),
    )


# Field category definitions for UI grouping
FIELD_CATEGORIES = {
    "identity": [
        "full_name", "first_name", "last_name", "middle_name",
        "date_of_birth", "ssn_last4", "license_number"
    ],
    "address": [
        "address", "street_address", "city", "state", "zip_code", "county"
    ],
    "income": [
        "annual_income", "monthly_income", "gross_pay", "net_pay",
        "ytd_gross", "ytd_net", "hourly_rate", "hours_worked"
    ],
    "employment": [
        "employer_name", "employer_address", "employer_ein",
        "job_title", "employment_start_date", "pay_frequency"
    ],
    "assets": [
        "account_balance", "ending_balance", "beginning_balance",
        "average_balance", "account_type", "bank_name", "account_number_last4"
    ],
    "tax": [
        "adjusted_gross_income", "total_income", "taxable_income",
        "tax_year", "filing_status", "federal_tax_withheld"
    ],
    "dates": [
        "document_date", "pay_date", "pay_period_start", "pay_period_end",
        "statement_start_date", "statement_end_date", "expiration_date"
    ],
}


# Field mappings from extracted fields to Lead/Loan model fields
FIELD_TO_LEAD_MAPPING = {
    "first_name": "first_name",
    "last_name": "last_name",
    "address": "address",
    "city": "city",
    "state": "state",
    "zip_code": "zip_code",
    "annual_income": "annual_income",
    "employer_name": "employer_name",
    "credit_score": "credit_score",
}

FIELD_TO_LOAN_MAPPING = {
    "first_name": "borrower_name",  # Combined with last_name
    "last_name": "borrower_name",  # Combined with first_name
    "address": "property_address",
    "city": "property_city",
    "state": "property_state",
    "zip_code": "property_zip",
}
