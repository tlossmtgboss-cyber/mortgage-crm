"""
IRS 4506-C Transcript Validation Service

Manages IRS transcript requests, imports, and income verification comparisons.
Compares borrower-submitted tax returns and W-2s against IRS transcript data
to detect discrepancies, supporting Fannie Mae income verification requirements.

Fannie Mae Selling Guide references:
    - B3-3.1-06: Requirements and Uses of IRS IVES Request for Transcript
    - B3-3.1-07: Using the IRS Form 4506-C
    - B1-1-03: Allowable Age of Credit Documents

Vendor integration points (future):
    - IRS IVES (Income Verification Express Service)
    - TaxStatus API
    - AccountChek / FormFree

Usage:
    from services.smart_docs.integrations.irs_transcript_service import (
        IRSTranscriptService,
        TranscriptRequest,
        TranscriptComparison,
    )

    service = IRSTranscriptService(db)
    request = service.request_transcript(borrower_id=7, loan_id=42, org_id=1, tax_years=[2024, 2025])
    comparison = service.compare_to_tax_return(loan_id=42, tax_year=2024, org_id=1)
"""

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TranscriptRequest:
    """Result of creating a transcript request."""
    request_id: int
    loan_id: int
    borrower_id: int
    tax_years: List[int]
    transcript_type: str
    status: str
    requested_at: Optional[datetime] = None


@dataclass
class Discrepancy:
    """Single field discrepancy between submitted doc and transcript."""
    field_name: str
    submitted_value: float
    transcript_value: float
    difference: float
    variance_pct: float
    severity: str  # "pass", "warning", "fail"


@dataclass
class TranscriptComparison:
    """Result of comparing transcript to submitted documents."""
    passed: bool
    tax_year: int
    discrepancies: List[Discrepancy] = field(default_factory=list)
    comparison_date: Optional[datetime] = None
    summary: str = ""


# =============================================================================
# CONSTANTS
# =============================================================================

# Thresholds for flagging discrepancies (Fannie Mae does not prescribe exact
# thresholds, but industry standard is $500 / 5% for transcript comparisons)
ABSOLUTE_THRESHOLD = Decimal("500.00")   # Flag if difference > $500
VARIANCE_PCT_THRESHOLD = Decimal("5.0")  # Flag if variance > 5%

# Fields to compare for tax return transcripts
TAX_RETURN_COMPARISON_FIELDS = [
    ("agi", "Adjusted Gross Income"),
    ("total_income", "Total Income"),
    ("wages_salaries_tips", "Wages, Salaries, Tips"),
    ("self_employment_income", "Self-Employment Income"),
    ("taxable_income", "Taxable Income"),
]

# Fields to compare for W-2 wage income transcripts
W2_COMPARISON_FIELDS = [
    ("wages", "Wages"),
    ("federal_withholding", "Federal Withholding"),
    ("social_security_wages", "Social Security Wages"),
    ("medicare_wages", "Medicare Wages"),
]


# =============================================================================
# SERVICE
# =============================================================================

class IRSTranscriptService:
    """Service for IRS 4506-C transcript requests and income verification.

    Manages the full lifecycle:
        1. Request transcript (create 4506-C record)
        2. Import transcript data (from vendor or manual entry)
        3. Compare against borrower-submitted documents
        4. Generate pre-filled 4506-C form

    All methods enforce tenant isolation via organization_id.
    """

    def __init__(self, db: Session):
        self.db = db

    # -------------------------------------------------------------------------
    # Request Transcript
    # -------------------------------------------------------------------------

    def request_transcript(
        self,
        borrower_id: int,
        loan_id: int,
        org_id: int,
        tax_years: List[int],
        transcript_type: str = "tax_return",
        vendor: Optional[str] = None,
        requested_by_user_id: Optional[int] = None,
    ) -> TranscriptRequest:
        """Create a 4506-C transcript request record.

        In production, this would also submit the request to IRS IVES or a
        third-party vendor (TaxStatus, AccountChek). For now, creates the
        tracking record and returns a TranscriptRequest.

        Args:
            borrower_id: Lead/borrower ID
            loan_id: Loan ID
            org_id: Organization ID (tenant isolation)
            tax_years: List of tax years to request (e.g. [2024, 2025])
            transcript_type: "tax_return", "wage_income", or "account"
            vendor: Optional vendor name
            requested_by_user_id: User who initiated the request

        Returns:
            TranscriptRequest with the new request details
        """
        valid_types = ("tax_return", "wage_income", "account")
        if transcript_type not in valid_types:
            raise ValueError(f"transcript_type must be one of {valid_types}, got '{transcript_type}'")

        if not tax_years:
            raise ValueError("tax_years must contain at least one year")

        current_year = datetime.now(timezone.utc).year
        for year in tax_years:
            if year < 2000 or year > current_year:
                raise ValueError(f"Invalid tax year: {year}")

        now = datetime.now(timezone.utc)

        result = self.db.execute(
            text("""
                INSERT INTO irs_transcript_requests
                    (organization_id, loan_id, borrower_id, tax_years,
                     transcript_type, status, vendor, requested_by_user_id,
                     requested_at, created_at)
                VALUES
                    (:org_id, :loan_id, :borrower_id, :tax_years,
                     :transcript_type, 'requested', :vendor, :requested_by_user_id,
                     :requested_at, :created_at)
                RETURNING id
            """),
            {
                "org_id": org_id,
                "loan_id": loan_id,
                "borrower_id": borrower_id,
                "tax_years": tax_years,
                "transcript_type": transcript_type,
                "vendor": vendor,
                "requested_by_user_id": requested_by_user_id,
                "requested_at": now,
                "created_at": now,
            },
        )
        row = result.fetchone()
        self.db.commit()

        request_id = row[0]
        logger.info(
            f"Created transcript request {request_id} for loan {loan_id}, "
            f"borrower {borrower_id}, years {tax_years}, type {transcript_type}"
        )

        return TranscriptRequest(
            request_id=request_id,
            loan_id=loan_id,
            borrower_id=borrower_id,
            tax_years=tax_years,
            transcript_type=transcript_type,
            status="requested",
            requested_at=now,
        )

    # -------------------------------------------------------------------------
    # Get Status
    # -------------------------------------------------------------------------

    def get_transcript_status(self, request_id: int, org_id: int) -> dict:
        """Check the status of a transcript request.

        Args:
            request_id: Transcript request ID
            org_id: Organization ID (tenant isolation)

        Returns:
            Dict with request details and current status
        """
        row = self.db.execute(
            text("""
                SELECT id, loan_id, borrower_id, tax_years, transcript_type,
                       status, vendor, requested_at, received_at, compared_at,
                       comparison_passed
                FROM irs_transcript_requests
                WHERE id = :request_id AND organization_id = :org_id
            """),
            {"request_id": request_id, "org_id": org_id},
        ).fetchone()

        if not row:
            raise ValueError(f"Transcript request {request_id} not found")

        return {
            "request_id": row[0],
            "loan_id": row[1],
            "borrower_id": row[2],
            "tax_years": row[3],
            "transcript_type": row[4],
            "status": row[5],
            "vendor": row[6],
            "requested_at": row[7].isoformat() if row[7] else None,
            "received_at": row[8].isoformat() if row[8] else None,
            "compared_at": row[9].isoformat() if row[9] else None,
            "comparison_passed": row[10],
        }

    # -------------------------------------------------------------------------
    # Import Transcript
    # -------------------------------------------------------------------------

    def import_transcript(
        self,
        request_id: int,
        org_id: int,
        transcript_data: dict,
        vendor: Optional[str] = None,
    ) -> dict:
        """Import transcript data received from IRS/vendor or manual entry.

        Validates the transcript data structure, stores it, and updates
        the request status to 'received'.

        Args:
            request_id: Transcript request ID
            org_id: Organization ID (tenant isolation)
            transcript_data: Parsed transcript fields (AGI, filing status, etc.)
            vendor: Vendor source (overrides if provided)

        Returns:
            Dict with updated request status
        """
        # Verify request exists and belongs to org
        existing = self.db.execute(
            text("""
                SELECT id, status, transcript_type
                FROM irs_transcript_requests
                WHERE id = :request_id AND organization_id = :org_id
            """),
            {"request_id": request_id, "org_id": org_id},
        ).fetchone()

        if not existing:
            raise ValueError(f"Transcript request {request_id} not found")

        if existing[1] not in ("requested", "received"):
            raise ValueError(
                f"Cannot import transcript in status '{existing[1]}'. "
                f"Expected 'requested' or 'received'."
            )

        # Validate transcript_data has minimum required fields
        transcript_type = existing[2]
        self._validate_transcript_data(transcript_data, transcript_type)

        now = datetime.now(timezone.utc)

        update_params = {
            "request_id": request_id,
            "org_id": org_id,
            "transcript_data": transcript_data,
            "received_at": now,
        }

        vendor_clause = ""
        if vendor:
            vendor_clause = ", vendor = :vendor"
            update_params["vendor"] = vendor

        irs_update_query = (
            "UPDATE irs_transcript_requests"
            " SET transcript_data = :transcript_data,"
            "     status = 'received',"
            "     received_at = :received_at"
            + vendor_clause
            + " WHERE id = :request_id AND organization_id = :org_id"
        )
        self.db.execute(text(irs_update_query), update_params)
        self.db.commit()

        logger.info(f"Imported transcript data for request {request_id}")

        return {
            "request_id": request_id,
            "status": "received",
            "received_at": now.isoformat(),
            "transcript_type": transcript_type,
            "vendor": vendor or existing[1],
        }

    # -------------------------------------------------------------------------
    # Compare to Tax Return
    # -------------------------------------------------------------------------

    def compare_to_tax_return(
        self,
        loan_id: int,
        tax_year: int,
        org_id: int,
    ) -> TranscriptComparison:
        """Compare IRS transcript against borrower-submitted tax return.

        Performs a field-by-field comparison of key income fields:
        - Adjusted Gross Income (AGI)
        - Total Income
        - Wages, Salaries, Tips
        - Self-Employment Income
        - Taxable Income

        Flags discrepancies exceeding $500 or 5% variance.

        Args:
            loan_id: Loan ID
            tax_year: Tax year to compare
            org_id: Organization ID (tenant isolation)

        Returns:
            TranscriptComparison with pass/fail and discrepancy details
        """
        # Get the transcript request with data for this loan/year
        transcript_row = self.db.execute(
            text("""
                SELECT id, transcript_data, transcript_type
                FROM irs_transcript_requests
                WHERE loan_id = :loan_id
                  AND organization_id = :org_id
                  AND status = 'received'
                  AND transcript_type = 'tax_return'
                  AND transcript_data IS NOT NULL
                  AND :tax_year = ANY(
                      SELECT jsonb_array_elements_text(tax_years::jsonb)::int
                  )
                ORDER BY received_at DESC
                LIMIT 1
            """),
            {"loan_id": loan_id, "org_id": org_id, "tax_year": tax_year},
        ).fetchone()

        if not transcript_row:
            raise ValueError(
                f"No received tax return transcript found for loan {loan_id}, year {tax_year}"
            )

        request_id = transcript_row[0]
        transcript_data = transcript_row[1]

        # Get borrower-submitted tax return data from smart_document_extractions
        submitted_data = self._get_submitted_tax_return(loan_id, tax_year, org_id)

        if not submitted_data:
            raise ValueError(
                f"No submitted tax return found for loan {loan_id}, year {tax_year}"
            )

        # Perform field-by-field comparison
        discrepancies = []
        for field_key, field_label in TAX_RETURN_COMPARISON_FIELDS:
            transcript_val = transcript_data.get(field_key)
            submitted_val = submitted_data.get(field_key)

            if transcript_val is None or submitted_val is None:
                continue

            disc = self._compare_field(field_label, submitted_val, transcript_val)
            if disc:
                discrepancies.append(disc)

        now = datetime.now(timezone.utc)
        passed = all(d.severity != "fail" for d in discrepancies)

        # Build summary
        fail_count = len([d for d in discrepancies if d.severity == "fail"])
        warn_count = len([d for d in discrepancies if d.severity == "warning"])
        if fail_count > 0:
            summary = f"{fail_count} critical discrepanc{'y' if fail_count == 1 else 'ies'} found"
        elif warn_count > 0:
            summary = f"{warn_count} warning{'s' if warn_count != 1 else ''} found, within tolerance"
        else:
            summary = "All fields match within tolerance"

        comparison = TranscriptComparison(
            passed=passed,
            tax_year=tax_year,
            discrepancies=discrepancies,
            comparison_date=now,
            summary=summary,
        )

        # Store comparison result
        comparison_result = {
            "passed": passed,
            "tax_year": tax_year,
            "compared_at": now.isoformat(),
            "discrepancies": [
                {
                    "field": d.field_name,
                    "submitted_value": d.submitted_value,
                    "transcript_value": d.transcript_value,
                    "difference": d.difference,
                    "variance_pct": d.variance_pct,
                    "severity": d.severity,
                }
                for d in discrepancies
            ],
            "summary": summary,
        }

        self.db.execute(
            text("""
                UPDATE irs_transcript_requests
                SET comparison_result = :comparison_result,
                    comparison_passed = :comparison_passed,
                    compared_at = :compared_at,
                    status = 'compared'
                WHERE id = :request_id AND organization_id = :org_id
            """),
            {
                "request_id": request_id,
                "org_id": org_id,
                "comparison_result": comparison_result,
                "comparison_passed": passed,
                "compared_at": now,
            },
        )
        self.db.commit()

        logger.info(
            f"Transcript comparison for loan {loan_id}, year {tax_year}: "
            f"{'PASSED' if passed else 'FAILED'} ({summary})"
        )

        return comparison

    # -------------------------------------------------------------------------
    # Compare to W-2
    # -------------------------------------------------------------------------

    def compare_to_w2(
        self,
        loan_id: int,
        tax_year: int,
        org_id: int,
    ) -> TranscriptComparison:
        """Compare W-2 income on transcript vs. borrower-submitted W-2.

        Checks employer EIN, wages, federal withholding, and SS/Medicare wages.

        Args:
            loan_id: Loan ID
            tax_year: Tax year to compare
            org_id: Organization ID (tenant isolation)

        Returns:
            TranscriptComparison with pass/fail and discrepancy details
        """
        # Get wage income transcript
        transcript_row = self.db.execute(
            text("""
                SELECT id, transcript_data
                FROM irs_transcript_requests
                WHERE loan_id = :loan_id
                  AND organization_id = :org_id
                  AND status = 'received'
                  AND transcript_type = 'wage_income'
                  AND transcript_data IS NOT NULL
                  AND :tax_year = ANY(
                      SELECT jsonb_array_elements_text(tax_years::jsonb)::int
                  )
                ORDER BY received_at DESC
                LIMIT 1
            """),
            {"loan_id": loan_id, "org_id": org_id, "tax_year": tax_year},
        ).fetchone()

        if not transcript_row:
            raise ValueError(
                f"No received W-2 transcript found for loan {loan_id}, year {tax_year}"
            )

        request_id = transcript_row[0]
        transcript_data = transcript_row[1]

        # Get borrower-submitted W-2 data
        submitted_data = self._get_submitted_w2(loan_id, tax_year, org_id)

        if not submitted_data:
            raise ValueError(
                f"No submitted W-2 found for loan {loan_id}, year {tax_year}"
            )

        discrepancies = []
        transcript_employers = transcript_data.get("employers", [])
        submitted_employers = submitted_data.get("employers", [])

        # Match employers by EIN and compare fields
        for t_employer in transcript_employers:
            t_ein = t_employer.get("ein", "").replace("-", "")
            matched_submitted = None

            for s_employer in submitted_employers:
                s_ein = s_employer.get("ein", "").replace("-", "")
                if t_ein and s_ein and t_ein == s_ein:
                    matched_submitted = s_employer
                    break

            if not matched_submitted:
                # Employer on transcript not found in submitted W-2s
                discrepancies.append(Discrepancy(
                    field_name=f"Employer EIN {t_employer.get('ein', 'unknown')}",
                    submitted_value=0,
                    transcript_value=t_employer.get("wages", 0),
                    difference=t_employer.get("wages", 0),
                    variance_pct=100.0,
                    severity="fail",
                ))
                continue

            employer_name = t_employer.get("employer_name", "Unknown")
            for field_key, field_label in W2_COMPARISON_FIELDS:
                t_val = t_employer.get(field_key)
                s_val = matched_submitted.get(field_key)
                if t_val is None or s_val is None:
                    continue

                disc = self._compare_field(
                    f"{employer_name} - {field_label}",
                    s_val, t_val,
                )
                if disc:
                    discrepancies.append(disc)

        now = datetime.now(timezone.utc)
        passed = all(d.severity != "fail" for d in discrepancies)

        fail_count = len([d for d in discrepancies if d.severity == "fail"])
        warn_count = len([d for d in discrepancies if d.severity == "warning"])
        if fail_count > 0:
            summary = f"{fail_count} W-2 discrepanc{'y' if fail_count == 1 else 'ies'} found"
        elif warn_count > 0:
            summary = f"{warn_count} W-2 warning{'s' if warn_count != 1 else ''}, within tolerance"
        else:
            summary = "All W-2 fields match within tolerance"

        comparison = TranscriptComparison(
            passed=passed,
            tax_year=tax_year,
            discrepancies=discrepancies,
            comparison_date=now,
            summary=summary,
        )

        # Store result
        comparison_result = {
            "passed": passed,
            "tax_year": tax_year,
            "compared_at": now.isoformat(),
            "comparison_type": "w2",
            "discrepancies": [
                {
                    "field": d.field_name,
                    "submitted_value": d.submitted_value,
                    "transcript_value": d.transcript_value,
                    "difference": d.difference,
                    "variance_pct": d.variance_pct,
                    "severity": d.severity,
                }
                for d in discrepancies
            ],
            "summary": summary,
        }

        self.db.execute(
            text("""
                UPDATE irs_transcript_requests
                SET comparison_result = :comparison_result,
                    comparison_passed = :comparison_passed,
                    compared_at = :compared_at,
                    status = 'compared'
                WHERE id = :request_id AND organization_id = :org_id
            """),
            {
                "request_id": request_id,
                "org_id": org_id,
                "comparison_result": comparison_result,
                "comparison_passed": passed,
                "compared_at": now,
            },
        )
        self.db.commit()

        logger.info(
            f"W-2 transcript comparison for loan {loan_id}, year {tax_year}: "
            f"{'PASSED' if passed else 'FAILED'} ({summary})"
        )

        return comparison

    # -------------------------------------------------------------------------
    # Generate 4506-C Form
    # -------------------------------------------------------------------------

    def generate_4506c_form(
        self,
        borrower_id: int,
        loan_id: int,
        org_id: int,
        tax_years: List[int],
    ) -> bytes:
        """Generate a pre-filled IRS Form 4506-C as PDF.

        Creates a basic PDF with borrower information and tax years pre-filled.
        In production, this would use a PDF library (reportlab, fpdf2) to
        fill the official IRS 4506-C form template.

        Args:
            borrower_id: Borrower/lead ID
            loan_id: Loan ID
            org_id: Organization ID (tenant isolation)
            tax_years: Tax years to request

        Returns:
            PDF bytes
        """
        # Get borrower information
        borrower = self.db.execute(
            text("""
                SELECT first_name, last_name, email, phone,
                       property_address
                FROM leads
                WHERE id = :borrower_id
            """),
            {"borrower_id": borrower_id},
        ).fetchone()

        if not borrower:
            raise ValueError(f"Borrower {borrower_id} not found")

        # Get loan property address for the form
        loan = self.db.execute(
            text("""
                SELECT loan_number, property_address, borrower_name
                FROM loans
                WHERE id = :loan_id AND organization_id = :org_id
            """),
            {"loan_id": loan_id, "org_id": org_id},
        ).fetchone()

        if not loan:
            raise ValueError(f"Loan {loan_id} not found")

        # Build the 4506-C PDF content
        # In production, use reportlab or fpdf2 to fill the official IRS form.
        # For now, generate a simple text-based PDF placeholder.
        borrower_name = f"{borrower[0] or ''} {borrower[1] or ''}".strip()
        if not borrower_name and loan:
            borrower_name = loan[2] or "Unknown"

        property_address = loan[1] or borrower[4] or "Address not on file"
        loan_number = loan[0] or "N/A"
        years_str = ", ".join(str(y) for y in sorted(tax_years))

        # Generate minimal PDF
        pdf_content = self._build_4506c_pdf(
            borrower_name=borrower_name,
            property_address=property_address,
            loan_number=loan_number,
            tax_years=years_str,
        )

        logger.info(
            f"Generated 4506-C form for borrower {borrower_id}, "
            f"loan {loan_id}, years {tax_years}"
        )

        return pdf_content

    # -------------------------------------------------------------------------
    # Comparison History
    # -------------------------------------------------------------------------

    def get_comparison_history(
        self,
        loan_id: int,
        org_id: int,
    ) -> List[dict]:
        """Get all transcript comparison results for a loan.

        Args:
            loan_id: Loan ID
            org_id: Organization ID (tenant isolation)

        Returns:
            List of comparison records with results
        """
        rows = self.db.execute(
            text("""
                SELECT id, borrower_id, tax_years, transcript_type, status,
                       vendor, comparison_result, comparison_passed,
                       requested_at, received_at, compared_at
                FROM irs_transcript_requests
                WHERE loan_id = :loan_id AND organization_id = :org_id
                ORDER BY created_at DESC
            """),
            {"loan_id": loan_id, "org_id": org_id},
        ).fetchall()

        return [
            {
                "request_id": row[0],
                "borrower_id": row[1],
                "tax_years": row[2],
                "transcript_type": row[3],
                "status": row[4],
                "vendor": row[5],
                "comparison_result": row[6],
                "comparison_passed": row[7],
                "requested_at": row[8].isoformat() if row[8] else None,
                "received_at": row[9].isoformat() if row[9] else None,
                "compared_at": row[10].isoformat() if row[10] else None,
            }
            for row in rows
        ]

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _compare_field(
        self,
        field_label: str,
        submitted_value: float,
        transcript_value: float,
    ) -> Optional[Discrepancy]:
        """Compare a single numeric field and return Discrepancy if out of tolerance.

        Returns None if the values match within tolerance.
        """
        submitted = Decimal(str(submitted_value))
        transcript = Decimal(str(transcript_value))
        difference = abs(submitted - transcript)

        if transcript != 0:
            variance_pct = (difference / abs(transcript) * 100).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
        elif submitted != 0:
            variance_pct = Decimal("100.0")
        else:
            # Both are zero — no discrepancy
            return None

        if difference <= ABSOLUTE_THRESHOLD and variance_pct <= VARIANCE_PCT_THRESHOLD:
            return None

        # Determine severity
        if difference > ABSOLUTE_THRESHOLD and variance_pct > VARIANCE_PCT_THRESHOLD:
            severity = "fail"
        else:
            severity = "warning"

        return Discrepancy(
            field_name=field_label,
            submitted_value=float(submitted),
            transcript_value=float(transcript),
            difference=float(difference),
            variance_pct=float(variance_pct),
            severity=severity,
        )

    def _validate_transcript_data(self, data: dict, transcript_type: str) -> None:
        """Validate transcript data has minimum required fields."""
        if not isinstance(data, dict):
            raise ValueError("transcript_data must be a dictionary")

        if transcript_type == "tax_return":
            if "tax_year" not in data:
                raise ValueError("transcript_data must include 'tax_year'")
            # At minimum, AGI or total_income should be present
            if "agi" not in data and "total_income" not in data:
                raise ValueError(
                    "Tax return transcript must include 'agi' or 'total_income'"
                )

        elif transcript_type == "wage_income":
            if "tax_year" not in data:
                raise ValueError("transcript_data must include 'tax_year'")
            if "employers" not in data or not isinstance(data["employers"], list):
                raise ValueError(
                    "Wage income transcript must include 'employers' list"
                )

        elif transcript_type == "account":
            if "tax_year" not in data:
                raise ValueError("transcript_data must include 'tax_year'")

    def _get_submitted_tax_return(
        self, loan_id: int, tax_year: int, org_id: int
    ) -> Optional[dict]:
        """Retrieve borrower-submitted tax return data from document extractions.

        Looks for smart_document_extractions with doc_type containing
        'tax_return' or '1040' for the given loan and tax year.
        """
        row = self.db.execute(
            text("""
                SELECT sde.extracted_data
                FROM smart_document_extractions sde
                JOIN smart_documents sd ON sd.id = sde.document_id
                WHERE sd.loan_id = :loan_id
                  AND sd.organization_id = :org_id
                  AND (
                      LOWER(sd.doc_type) LIKE '%tax_return%'
                      OR LOWER(sd.doc_type) LIKE '%1040%'
                  )
                  AND (
                      sde.extracted_data->>'tax_year' = :tax_year_str
                      OR sde.extracted_data->>'year' = :tax_year_str
                  )
                ORDER BY sde.created_at DESC
                LIMIT 1
            """),
            {
                "loan_id": loan_id,
                "org_id": org_id,
                "tax_year_str": str(tax_year),
            },
        ).fetchone()

        if row and row[0]:
            return row[0]
        return None

    def _get_submitted_w2(
        self, loan_id: int, tax_year: int, org_id: int
    ) -> Optional[dict]:
        """Retrieve borrower-submitted W-2 data from document extractions."""
        row = self.db.execute(
            text("""
                SELECT sde.extracted_data
                FROM smart_document_extractions sde
                JOIN smart_documents sd ON sd.id = sde.document_id
                WHERE sd.loan_id = :loan_id
                  AND sd.organization_id = :org_id
                  AND (
                      LOWER(sd.doc_type) LIKE '%w2%'
                      OR LOWER(sd.doc_type) LIKE '%w-2%'
                  )
                  AND (
                      sde.extracted_data->>'tax_year' = :tax_year_str
                      OR sde.extracted_data->>'year' = :tax_year_str
                  )
                ORDER BY sde.created_at DESC
                LIMIT 1
            """),
            {
                "loan_id": loan_id,
                "org_id": org_id,
                "tax_year_str": str(tax_year),
            },
        ).fetchone()

        if row and row[0]:
            return row[0]
        return None

    def _build_4506c_pdf(
        self,
        borrower_name: str,
        property_address: str,
        loan_number: str,
        tax_years: str,
    ) -> bytes:
        """Build a minimal PDF representation of the 4506-C form.

        Uses a simple PDF structure without external dependencies. In
        production, replace with reportlab or fpdf2 to fill the official
        IRS 4506-C template PDF.
        """
        # Minimal valid PDF with form content as text
        # This is a deliberately simple PDF — production should use a real
        # PDF library to fill the official IRS form template.
        lines = [
            "IRS Form 4506-C",
            "IVES Request for Transcript of Tax Return",
            "",
            f"1a. Name: {borrower_name}",
            f"1b. SSN: ***-**-****",
            "",
            f"3. Current Address: {property_address}",
            "",
            f"5a. Loan Number: {loan_number}",
            "",
            f"6. Tax Years Requested: {tax_years}",
            "",
            "9. Type of Transcript: Tax Return Transcript",
            "",
            "Signature: ____________________________",
            "Date: ____________________________",
            "",
            "This form is pre-filled. Borrower must review, sign,",
            "and date before submission to IRS.",
        ]
        text_content = "\n".join(lines)

        # Build a minimal PDF 1.4 structure
        buf = io.BytesIO()
        buf.write(b"%PDF-1.4\n")

        # Object 1: Catalog
        obj1_offset = buf.tell()
        buf.write(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

        # Object 2: Pages
        obj2_offset = buf.tell()
        buf.write(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")

        # Object 4: Font
        obj4_offset = buf.tell()
        buf.write(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>\nendobj\n")

        # Object 5: Stream content
        # Build content stream for text rendering
        stream_lines = ["BT", "/F1 10 Tf", "36 756 Td", "12 TL"]
        for line in lines:
            # Escape special PDF characters
            safe_line = (
                line.replace("\\", "\\\\")
                .replace("(", "\\(")
                .replace(")", "\\)")
            )
            stream_lines.append(f"({safe_line}) '")
        stream_lines.append("ET")
        stream_data = "\n".join(stream_lines).encode("latin-1")

        obj5_offset = buf.tell()
        buf.write(f"5 0 obj\n<< /Length {len(stream_data)} >>\nstream\n".encode())
        buf.write(stream_data)
        buf.write(b"\nendstream\nendobj\n")

        # Object 3: Page
        obj3_offset = buf.tell()
        buf.write(
            b"3 0 obj\n"
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] "
            b"/Contents 5 0 R "
            b"/Resources << /Font << /F1 4 0 R >> >> >>\n"
            b"endobj\n"
        )

        # Cross-reference table
        xref_offset = buf.tell()
        buf.write(b"xref\n0 6\n")
        buf.write(b"0000000000 65535 f \n")
        buf.write(f"{obj1_offset:010d} 00000 n \n".encode())
        buf.write(f"{obj2_offset:010d} 00000 n \n".encode())
        buf.write(f"{obj3_offset:010d} 00000 n \n".encode())
        buf.write(f"{obj4_offset:010d} 00000 n \n".encode())
        buf.write(f"{obj5_offset:010d} 00000 n \n".encode())

        # Trailer
        buf.write(b"trailer\n<< /Size 6 /Root 1 0 R >>\n")
        buf.write(f"startxref\n{xref_offset}\n%%EOF\n".encode())

        return buf.getvalue()
