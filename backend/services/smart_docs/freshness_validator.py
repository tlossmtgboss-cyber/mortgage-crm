"""
Smart Document Collection - Freshness Validator

Validates document freshness against configurable policies.
Freshness requirements by document type:
- Paystubs: ≤30 days
- Bank Statements: ≤90 days
- Investment Statements: ≤90 days
- P&L Statements: ≤90 days (self-employed)
- W-2s: Year-based (expire Feb 1 of the 2nd year after tax year)
- Tax Returns: Year-based (expire Feb 1 of the 2nd year after tax year)

Calculates expiration dates and days until expiration.

W-2/Tax Return Expiration Logic:
- W-2s for a tax year expire on February 1st, two years after that tax year
- Example: 2023 W-2 expires Feb 1, 2025 (when 2024 W-2s become available)
- Example: 2024 W-2 expires Feb 1, 2026
- New W-2s become available after January 31 of the following year
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

    # Annual documents with year-based expiration (expire Feb 1 of 2nd year after tax year)
    ANNUAL_DOCUMENTS = {
        DocType.W2,
        DocType.TAX_RETURN,
        DocType.BUSINESS_TAX_RETURN,
    }

    # How many days before expiration to show warning
    EXPIRING_SOON_THRESHOLD = 7

    def __init__(self):
        """Initialize the freshness validator."""
        pass

    def get_annual_document_expiration(
        self,
        tax_year: int,
        reference_date: Optional[date] = None,
    ) -> date:
        """
        Calculate expiration date for annual documents (W-2, Tax Returns).

        Annual documents expire on February 1st, two years after the tax year.
        Example: 2023 W-2 expires Feb 1, 2025 (when 2024 W-2s become available)

        Args:
            tax_year: The tax year of the document (e.g., 2023)
            reference_date: Reference date for calculation (default: today)

        Returns:
            The expiration date (February 1st of tax_year + 2)
        """
        return date(tax_year + 2, 2, 1)

    def get_current_required_tax_years(
        self,
        num_years: int = 2,
        reference_date: Optional[date] = None,
    ) -> list:
        """
        Get the tax years currently required for W-2s/Tax Returns.

        W-2s for a year become available after January 31 of the following year.
        On February 1st, we start requiring the new year's W-2.

        Args:
            num_years: Number of years of W-2s required (default: 2)
            reference_date: Reference date (default: today)

        Returns:
            List of tax years required, ordered newest to oldest
        """
        ref_date = reference_date or date.today()

        # Determine the most recent available tax year
        # W-2s for year X become available after Jan 31 of year X+1
        # So on Feb 1, 2025, we can request 2024 W-2s
        if ref_date.month >= 2:  # February or later
            newest_available_year = ref_date.year - 1
        else:  # January - still waiting for previous year's W-2s
            newest_available_year = ref_date.year - 2

        # Return the required years (newest to oldest)
        return [newest_available_year - i for i in range(num_years)]

    def validate_annual_document(
        self,
        doc_type: DocType,
        tax_year: int,
        reference_date: Optional[date] = None,
    ) -> FreshnessResult:
        """
        Validate freshness of annual documents (W-2, Tax Returns).

        Args:
            doc_type: Type of document (W2, TAX_RETURN, BUSINESS_TAX_RETURN)
            tax_year: The tax year of the document
            reference_date: Reference date for calculation (default: today)

        Returns:
            FreshnessResult with validation details
        """
        ref_date = reference_date or date.today()
        expires_at = self.get_annual_document_expiration(tax_year)
        days_until = (expires_at - ref_date).days

        # Get the currently required tax years
        required_years = self.get_current_required_tax_years(num_years=2, reference_date=ref_date)

        # Check if this tax year is still valid
        if days_until < 0:
            status = FreshnessStatus.EXPIRED
            is_valid = False
            message = f"{tax_year} {doc_type.value} expired on {expires_at.strftime('%m/%d/%Y')} - request {required_years[0]} {doc_type.value}"
        elif days_until <= self.EXPIRING_SOON_THRESHOLD:
            status = FreshnessStatus.EXPIRING_SOON
            is_valid = True
            message = f"{tax_year} {doc_type.value} expires in {days_until} days - {required_years[0]} will be needed"
        elif tax_year not in required_years:
            # Document is too old even if not technically expired
            status = FreshnessStatus.EXPIRED
            is_valid = False
            message = f"{tax_year} {doc_type.value} is too old - need years {required_years}"
        else:
            status = FreshnessStatus.FRESH
            is_valid = True
            message = f"{tax_year} {doc_type.value} is valid until {expires_at.strftime('%m/%d/%Y')}"

        return FreshnessResult(
            status=status,
            doc_date=date(tax_year, 12, 31),  # Use end of tax year as doc_date
            expires_at=expires_at,
            days_until_expiration=days_until,
            is_valid=is_valid,
            message=message,
            freshness_days=None,  # N/A for annual documents
        )

    def validate(
        self,
        doc_type: DocType,
        doc_date: Optional[date],
        freshness_days: Optional[int] = None,
        reference_date: Optional[date] = None,
        tax_year: Optional[int] = None,
    ) -> FreshnessResult:
        """
        Validate document freshness.

        Args:
            doc_type: Type of document
            doc_date: Date extracted from the document
            freshness_days: Override for freshness requirement (days)
            reference_date: Reference date for calculation (default: today)
            tax_year: For annual documents (W-2, Tax Returns), the tax year

        Returns:
            FreshnessResult with validation details
        """
        ref_date = reference_date or date.today()

        # Handle annual documents (W-2, Tax Returns) with year-based expiration
        if doc_type in self.ANNUAL_DOCUMENTS:
            # Try to determine tax_year from parameter or doc_date
            if tax_year is None and doc_date is not None:
                # Assume the doc_date year is the tax year
                tax_year = doc_date.year

            if tax_year is not None:
                return self.validate_annual_document(doc_type, tax_year, ref_date)
            else:
                # Can't validate without tax year
                return FreshnessResult(
                    status=FreshnessStatus.UNKNOWN,
                    doc_date=doc_date,
                    expires_at=None,
                    days_until_expiration=None,
                    is_valid=False,
                    message=f"Cannot validate {doc_type.value} freshness - tax year unknown",
                    freshness_days=None,
                )

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
        tax_year: Optional[int] = None,
    ) -> Optional[date]:
        """
        Calculate expiration date for a document.

        Args:
            doc_type: Type of document
            doc_date: Date from the document
            freshness_days: Override for freshness days
            tax_year: For annual documents, the tax year

        Returns:
            Expiration date or None if not applicable
        """
        # Handle annual documents (W-2, Tax Returns)
        if doc_type in self.ANNUAL_DOCUMENTS:
            year = tax_year or doc_date.year
            return self.get_annual_document_expiration(year)

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
        # Annual documents have year-based freshness requirements
        if doc_type in self.ANNUAL_DOCUMENTS:
            return True
        return doc_type not in self.NO_FRESHNESS_REQUIRED and \
               doc_type in self.DEFAULT_FRESHNESS_DAYS

    def calculate_renewal_date(
        self,
        doc_type: DocType,
        doc_date: date,
        freshness_days: Optional[int] = None,
        buffer_days: int = 5,
        tax_year: Optional[int] = None,
    ) -> Optional[date]:
        """
        Calculate when a renewal request should be sent.

        For annual documents (W-2, Tax Returns):
        - Request should be sent on February 1st when new documents become available
        - Example: On Feb 1, 2025, request 2024 W-2 (replacing 2023 which just expired)

        Args:
            doc_type: Type of document
            doc_date: Date from current document
            freshness_days: Override for freshness days
            buffer_days: Days before expiration to request renewal
            tax_year: For annual documents, the tax year

        Returns:
            Date to send renewal request, or None if not applicable
        """
        # For annual documents, renewal date is February 1st of the next renewal year
        if doc_type in self.ANNUAL_DOCUMENTS:
            year = tax_year or doc_date.year
            # W-2 for year X expires Feb 1 of year X+2
            # So request new one on Feb 1 of year X+2 (same as expiration)
            return self.get_annual_document_expiration(year)

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
        tax_year: Optional[int] = None,
    ) -> Optional[date]:
        """
        Estimate when the next document will be available.

        For paystubs, uses payroll frequency.
        For bank statements, typically monthly.
        For W-2s/Tax Returns, available after January 31 of the following year.

        Args:
            doc_type: Type of document
            last_doc_date: Date of the last received document
            payroll_frequency: WEEKLY, BIWEEKLY, SEMIMONTHLY, MONTHLY
            tax_year: For annual documents, the tax year of the current document

        Returns:
            Estimated date when next document available
        """
        # W-2s and Tax Returns are available after January 31 of the following year
        if doc_type in self.ANNUAL_DOCUMENTS:
            year = tax_year or last_doc_date.year
            # Next year's document becomes available Feb 1 of the year after that
            # e.g., 2024 W-2 becomes available Feb 1, 2025
            return date(year + 2, 2, 1)

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
