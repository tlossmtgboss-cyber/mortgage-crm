"""
Smart Document Collection - Freshness Validator

Validates document freshness against configurable policies.
Freshness requirements by document type:
- Paystubs: ≤30 days
- Bank Statements: ≤90 days
- Investment Statements: ≤90 days
- P&L Statements: ≤90 days (self-employed)

Calculates expiration dates and days until expiration.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from models.smart_docs_models import DocType

logger = logging.getLogger(__name__)


class FreshnessStatus(str, Enum):
    """Document freshness status."""
    FRESH = "fresh"           # Within freshness window
    EXPIRING_SOON = "expiring_soon"  # Within 7 days of expiration
    EXPIRED = "expired"       # Past freshness window
    UNKNOWN = "unknown"       # Cannot determine (no date extracted)
    NOT_APPLICABLE = "not_applicable"  # Document type has no freshness requirement


@dataclass
class FreshnessResult:
    """Result of freshness validation."""
    status: FreshnessStatus
    doc_date: Optional[date]
    expires_at: Optional[date]
    days_until_expiration: Optional[int]
    is_valid: bool
    message: str
    freshness_days: Optional[int]  # The policy requirement


class FreshnessValidator:
    """
    Validates document freshness based on configurable policies.

    Freshness is calculated from the document date (pay date, statement date, etc.)
    to ensure documents meet underwriting requirements.
    """

    # Default freshness requirements by document type (in days)
    # These can be overridden per-request
    DEFAULT_FRESHNESS_DAYS = {
        DocType.PAYSTUB: 30,
        DocType.BANK_STATEMENT: 90,
        DocType.INVESTMENT_STATEMENT: 90,
        DocType.PROFIT_LOSS: 90,
        DocType.BALANCE_SHEET: 90,
    }

    # Documents that don't have freshness requirements
    NO_FRESHNESS_REQUIRED = {
        DocType.DRIVERS_LICENSE,  # Has its own expiration date
        DocType.W2,               # Annual document, year-based
        DocType.TAX_RETURN,       # Annual document, year-based
        DocType.BUSINESS_TAX_RETURN,
        DocType.DD214,
        DocType.VA_COE,
        DocType.FHA_CERT,
        DocType.BANKRUPTCY_DISCHARGE,
        DocType.PURCHASE_CONTRACT,
        DocType.APPRAISAL,        # Has its own expiration (typically 120 days)
        DocType.TITLE_REPORT,
        DocType.GIFT_LETTER,
        DocType.LOE,
        DocType.OTHER,
    }

    # How many days before expiration to show warning
    EXPIRING_SOON_THRESHOLD = 7

    def __init__(self):
        """Initialize the freshness validator."""
        pass

    def validate(
        self,
        doc_type: DocType,
        doc_date: Optional[date],
        freshness_days: Optional[int] = None,
        reference_date: Optional[date] = None,
    ) -> FreshnessResult:
        """
        Validate document freshness.

        Args:
            doc_type: Type of document
            doc_date: Date extracted from the document
            freshness_days: Override for freshness requirement (days)
            reference_date: Reference date for calculation (default: today)

        Returns:
            FreshnessResult with validation details
        """
        ref_date = reference_date or date.today()

        # Check if freshness applies to this document type
        if doc_type in self.NO_FRESHNESS_REQUIRED:
            return FreshnessResult(
                status=FreshnessStatus.NOT_APPLICABLE,
                doc_date=doc_date,
                expires_at=None,
                days_until_expiration=None,
                is_valid=True,
                message="Document type does not have freshness requirements",
                freshness_days=None,
            )

        # If no date was extracted, we can't validate
        if doc_date is None:
            return FreshnessResult(
                status=FreshnessStatus.UNKNOWN,
                doc_date=None,
                expires_at=None,
                days_until_expiration=None,
                is_valid=False,
                message="Cannot validate freshness - no date extracted from document",
                freshness_days=freshness_days or self.DEFAULT_FRESHNESS_DAYS.get(doc_type),
            )

        # Get the freshness requirement
        max_days = freshness_days or self.DEFAULT_FRESHNESS_DAYS.get(doc_type)

        if max_days is None:
            # No freshness requirement defined
            return FreshnessResult(
                status=FreshnessStatus.NOT_APPLICABLE,
                doc_date=doc_date,
                expires_at=None,
                days_until_expiration=None,
                is_valid=True,
                message="No freshness requirement configured for this document type",
                freshness_days=None,
            )

        # Calculate expiration
        expires_at = doc_date + timedelta(days=max_days)
        days_until = (expires_at - ref_date).days

        # Determine status
        if days_until < 0:
            status = FreshnessStatus.EXPIRED
            is_valid = False
            message = f"Document expired {abs(days_until)} days ago (dated {doc_date}, max {max_days} days)"
        elif days_until <= self.EXPIRING_SOON_THRESHOLD:
            status = FreshnessStatus.EXPIRING_SOON
            is_valid = True
            message = f"Document expires in {days_until} days"
        else:
            status = FreshnessStatus.FRESH
            is_valid = True
            message = f"Document is fresh ({days_until} days until expiration)"

        return FreshnessResult(
            status=status,
            doc_date=doc_date,
            expires_at=expires_at,
            days_until_expiration=days_until,
            is_valid=is_valid,
            message=message,
            freshness_days=max_days,
        )

    def get_expiration_date(
        self,
        doc_type: DocType,
        doc_date: date,
        freshness_days: Optional[int] = None,
    ) -> Optional[date]:
        """
        Calculate expiration date for a document.

        Args:
            doc_type: Type of document
            doc_date: Date from the document
            freshness_days: Override for freshness days

        Returns:
            Expiration date or None if not applicable
        """
        if doc_type in self.NO_FRESHNESS_REQUIRED:
            return None

        max_days = freshness_days or self.DEFAULT_FRESHNESS_DAYS.get(doc_type)
        if max_days is None:
            return None

        return doc_date + timedelta(days=max_days)

    def get_required_freshness(self, doc_type: DocType) -> Optional[int]:
        """Get the freshness requirement for a document type."""
        if doc_type in self.NO_FRESHNESS_REQUIRED:
            return None
        return self.DEFAULT_FRESHNESS_DAYS.get(doc_type)

    def is_freshness_required(self, doc_type: DocType) -> bool:
        """Check if freshness validation is required for document type."""
        return doc_type not in self.NO_FRESHNESS_REQUIRED and \
               doc_type in self.DEFAULT_FRESHNESS_DAYS

    def calculate_renewal_date(
        self,
        doc_type: DocType,
        doc_date: date,
        freshness_days: Optional[int] = None,
        buffer_days: int = 5,
    ) -> Optional[date]:
        """
        Calculate when a renewal request should be sent.

        Args:
            doc_type: Type of document
            doc_date: Date from current document
            freshness_days: Override for freshness days
            buffer_days: Days before expiration to request renewal

        Returns:
            Date to send renewal request, or None if not applicable
        """
        expires_at = self.get_expiration_date(doc_type, doc_date, freshness_days)
        if expires_at is None:
            return None

        renewal_date = expires_at - timedelta(days=buffer_days)

        # Don't return a date in the past
        today = date.today()
        if renewal_date <= today:
            return today

        return renewal_date

    def estimate_next_document_date(
        self,
        doc_type: DocType,
        last_doc_date: date,
        payroll_frequency: Optional[str] = None,
    ) -> Optional[date]:
        """
        Estimate when the next document will be available.

        For paystubs, uses payroll frequency.
        For bank statements, typically monthly.

        Args:
            doc_type: Type of document
            last_doc_date: Date of the last received document
            payroll_frequency: WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY

        Returns:
            Estimated date when next document available
        """
        if doc_type == DocType.PAYSTUB and payroll_frequency:
            freq_days = {
                "WEEKLY": 7,
                "BIWEEKLY": 14,
                "SEMIMONTHLY": 15,  # Approximate
                "MONTHLY": 30,
            }
            days = freq_days.get(payroll_frequency, 14)
            return last_doc_date + timedelta(days=days)

        elif doc_type == DocType.BANK_STATEMENT:
            # Statements typically available a few days after month end
            # Estimate next statement date as ~35 days from last
            return last_doc_date + timedelta(days=35)

        elif doc_type == DocType.INVESTMENT_STATEMENT:
            # Quarterly statements
            return last_doc_date + timedelta(days=90)

        elif doc_type == DocType.PROFIT_LOSS:
            # Monthly P&L
            return last_doc_date + timedelta(days=30)

        return None

    def result_to_dict(self, result: FreshnessResult) -> Dict[str, Any]:
        """Convert result to dictionary for storage/API."""
        return {
            "status": result.status.value,
            "doc_date": result.doc_date.isoformat() if result.doc_date else None,
            "expires_at": result.expires_at.isoformat() if result.expires_at else None,
            "days_until_expiration": result.days_until_expiration,
            "is_valid": result.is_valid,
            "message": result.message,
            "freshness_days": result.freshness_days,
        }

    def batch_validate(
        self,
        documents: list,
        reference_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Validate freshness for multiple documents.

        Args:
            documents: List of dicts with doc_type, doc_date, freshness_days
            reference_date: Reference date for all validations

        Returns:
            Summary with all validation results
        """
        results = []
        expired_count = 0
        expiring_soon_count = 0
        fresh_count = 0

        for doc in documents:
            doc_type = doc.get("doc_type")
            if isinstance(doc_type, str):
                doc_type = DocType(doc_type)

            doc_date_str = doc.get("doc_date")
            doc_date = None
            if doc_date_str:
                if isinstance(doc_date_str, str):
                    doc_date = datetime.fromisoformat(doc_date_str).date()
                elif isinstance(doc_date_str, date):
                    doc_date = doc_date_str

            result = self.validate(
                doc_type=doc_type,
                doc_date=doc_date,
                freshness_days=doc.get("freshness_days"),
                reference_date=reference_date,
            )

            if result.status == FreshnessStatus.EXPIRED:
                expired_count += 1
            elif result.status == FreshnessStatus.EXPIRING_SOON:
                expiring_soon_count += 1
            elif result.status == FreshnessStatus.FRESH:
                fresh_count += 1

            results.append({
                "doc_id": doc.get("id"),
                "doc_type": doc_type.value if hasattr(doc_type, 'value') else doc_type,
                **self.result_to_dict(result),
            })

        return {
            "total": len(documents),
            "fresh": fresh_count,
            "expiring_soon": expiring_soon_count,
            "expired": expired_count,
            "unknown": len(documents) - fresh_count - expiring_soon_count - expired_count,
            "results": results,
        }
