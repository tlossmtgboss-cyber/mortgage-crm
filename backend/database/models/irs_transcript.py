"""
IRS Transcript Models

Models for IRS 4506-C transcript requests, import, and income verification
comparison. Used by the document_tracker and compliance_checker agents to
validate borrower-submitted income documents against IRS records.

Key tables:
    irs_transcript_requests  - 4506-C request tracking and transcript storage

Fannie Mae Selling Guide references:
    - B1-1-03: Allowable Age of Credit Documents (transcript freshness)
    - B3-3.1-06: Requirements and Uses of IRS IVES Request for Transcript
    - B3-3.1-07: Using the IRS Form 4506-C

Usage:
    from database.models.irs_transcript import (
        IRSTranscriptRequest,
        TranscriptType,
        TranscriptStatus,
    )
"""

from datetime import datetime, timezone
import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy import Enum as SQLEnum

from database import Base


__all__ = [
    "TranscriptType",
    "TranscriptStatus",
    "IRSTranscriptRequest",
]


# ============================================================================
# ENUMS
# ============================================================================

class TranscriptType(str, enum.Enum):
    """Type of IRS transcript requested via 4506-C."""
    TAX_RETURN = "tax_return"       # Full tax return transcript (Form 1040)
    WAGE_INCOME = "wage_income"     # W-2 transcript (wage and income)
    ACCOUNT = "account"             # Account transcript (balance due, payments)


class TranscriptStatus(str, enum.Enum):
    """Lifecycle status of a transcript request."""
    REQUESTED = "requested"         # 4506-C submitted to IRS/vendor
    RECEIVED = "received"           # Transcript data received
    COMPARED = "compared"           # Compared against borrower documents
    FAILED = "failed"               # Request failed or IRS returned error


# ============================================================================
# IRS TRANSCRIPT REQUEST MODEL
# ============================================================================

class IRSTranscriptRequest(Base):
    """IRS transcript request and comparison record.

    Tracks the full lifecycle of a 4506-C transcript request: from the
    initial request through receipt and comparison against borrower-submitted
    income documents. Stores both the raw transcript data and comparison
    findings for audit.

    Workflow:
        1. LO or system creates request (status=REQUESTED)
        2. Transcript received from IRS IVES or vendor (status=RECEIVED)
        3. Comparison engine runs against submitted docs (status=COMPARED)
        4. If comparison_passed is False, compliance alert is generated

    Vendor integrations (future):
        - IRS IVES (Income Verification Express Service)
        - TaxStatus API
        - AccountChek / FormFree
    """
    __tablename__ = "irs_transcript_requests"
    __table_args__ = (
        Index("ix_irs_transcript_org_loan", "organization_id", "loan_id"),
        Index("ix_irs_transcript_status", "status"),
        Index("ix_irs_transcript_borrower", "borrower_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, index=True)   # ref organizations.id
    loan_id = Column(Integer, nullable=False)                       # ref loans.id
    borrower_id = Column(Integer, nullable=False)                   # ref leads.id

    # Request details
    tax_years = Column(JSON, nullable=False)        # List of years, e.g. [2024, 2025]
    transcript_type = Column(
        SQLEnum(TranscriptType),
        nullable=False,
        default=TranscriptType.TAX_RETURN,
    )
    status = Column(
        SQLEnum(TranscriptStatus),
        nullable=False,
        default=TranscriptStatus.REQUESTED,
    )

    # Vendor / source
    vendor = Column(String(50), nullable=True)      # "ives", "taxstatus", "manual"

    # Transcript content (received from IRS/vendor)
    transcript_data = Column(JSON, nullable=True)
    # Expected structure for tax_return transcript:
    # {
    #     "tax_year": 2024,
    #     "filing_status": "married_filing_jointly",
    #     "agi": 125000.00,
    #     "total_income": 140000.00,
    #     "wages_salaries_tips": 120000.00,
    #     "self_employment_income": 20000.00,
    #     "tax_liability": 22500.00,
    #     "taxable_income": 105000.00
    # }
    # Expected structure for wage_income transcript:
    # {
    #     "tax_year": 2024,
    #     "employers": [
    #         {
    #             "ein": "12-3456789",
    #             "employer_name": "Acme Corp",
    #             "wages": 120000.00,
    #             "federal_withholding": 18000.00,
    #             "social_security_wages": 120000.00,
    #             "medicare_wages": 120000.00
    #         }
    #     ]
    # }

    # Comparison results
    comparison_result = Column(JSON, nullable=True)
    # Expected structure:
    # {
    #     "passed": true/false,
    #     "tax_year": 2024,
    #     "compared_at": "2026-03-12T10:30:00Z",
    #     "discrepancies": [
    #         {
    #             "field": "agi",
    #             "submitted_value": 130000.00,
    #             "transcript_value": 125000.00,
    #             "difference": 5000.00,
    #             "variance_pct": 4.0,
    #             "severity": "warning"  # "pass", "warning", "fail"
    #         }
    #     ],
    #     "summary": "1 discrepancy found: AGI variance of 4.0%"
    # }
    comparison_passed = Column(Boolean, nullable=True)

    # Who requested
    requested_by_user_id = Column(Integer, nullable=True)   # ref users.id

    # Timestamps
    requested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    received_at = Column(DateTime, nullable=True)
    compared_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return (
            f"<IRSTranscriptRequest id={self.id} loan_id={self.loan_id} "
            f"type={self.transcript_type} status={self.status}>"
        )
