"""
Merge Intelligence Service for Smart Docs V2.

Handles intelligent document merging for loan submission packages with
investor-specific stacking orders, cover page generation, table of contents,
bookmarking, Bates numbering, watermarking, duplicate/missing detection,
merge validation, quality checks, and configurable org-level merge profiles.

Architecture:
    - Extends the existing PDFGenerationService for low-level PDF ops.
    - Uses SmartDocument + DocumentRequest models for doc metadata.
    - Org-isolated via OrgAwareService base class.
    - All public methods are async for non-blocking IO.

Usage:
    from services.smart_docs.merge_intelligence_service import (
        MergeIntelligenceService,
        get_merge_intelligence_service,
    )

    svc = get_merge_intelligence_service(db, org_id=42, user_id=7)
    result = await svc.create_submission_package(
        loan_id=100,
        investor_type="FANNIE_MAE_DU",
    )
"""

from __future__ import annotations

import enum
import hashlib
import io
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.smart_docs.service_registry import OrgAwareService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional PDF dependencies (mirroring pdf_generation_service.py pattern)
# ---------------------------------------------------------------------------

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas as rl_canvas

    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

try:
    from pypdf import PdfReader, PdfWriter, PdfMerger

    HAS_PYPDF = True
except ImportError:
    try:
        from PyPDF2 import PdfReader, PdfWriter, PdfMerger  # type: ignore[no-redef]

        HAS_PYPDF = True
    except ImportError:
        HAS_PYPDF = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PAGE_WIDTH, _PAGE_HEIGHT = 612, 792  # US Letter in points
_MARGIN = 72  # 1 inch

# Maximum merged file size (200 MB)
MAX_MERGE_FILE_SIZE = 200 * 1024 * 1024

# Maximum page count for a single merged package
MAX_MERGE_PAGE_COUNT = 2000


# =============================================================================
# Enums
# =============================================================================


class InvestorType(str, enum.Enum):
    """Supported investor stacking order types."""

    FANNIE_MAE_DU = "FANNIE_MAE_DU"
    FREDDIE_MAC_LPA = "FREDDIE_MAC_LPA"
    FHA = "FHA"
    VA = "VA"
    USDA = "USDA"
    JUMBO = "JUMBO"
    CUSTOM = "CUSTOM"


class WatermarkType(str, enum.Enum):
    """Supported watermark labels."""

    DRAFT = "DRAFT"
    COPY = "COPY"
    CONFIDENTIAL = "CONFIDENTIAL"


class ExportFormat(str, enum.Enum):
    """Supported export formats."""

    PDF = "PDF"
    PDF_A = "PDF_A"


# =============================================================================
# Data classes
# =============================================================================


@dataclass
class OrderedDoc:
    """A document positioned within the stacking order."""

    document_id: int
    doc_type: str
    display_name: str
    section_name: str
    section_index: int
    position_in_section: int
    page_count: int = 0
    start_page: int = 0
    storage_key: str = ""
    file_size: int = 0
    status: str = ""


@dataclass
class ValidationIssue:
    """A single validation finding (error or warning)."""

    severity: str  # "error", "warning", "info"
    code: str
    message: str
    document_id: Optional[int] = None
    doc_type: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of package completeness or merge validation."""

    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    missing_optional: List[str] = field(default_factory=list)
    duplicate_docs: List[Tuple[int, int, str]] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [
                {
                    "severity": i.severity,
                    "code": i.code,
                    "message": i.message,
                    "document_id": i.document_id,
                    "doc_type": i.doc_type,
                }
                for i in self.issues
            ],
            "missing_required": self.missing_required,
            "missing_optional": self.missing_optional,
            "duplicate_docs": [
                {"doc_id_1": d[0], "doc_id_2": d[1], "doc_type": d[2]}
                for d in self.duplicate_docs
            ],
        }


@dataclass
class QualityCheckResult:
    """Post-merge quality assessment."""

    passed: bool
    file_size_bytes: int
    file_size_mb: float
    page_count: int
    sha256_hash: str
    is_readable: bool
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "file_size_bytes": self.file_size_bytes,
            "file_size_mb": round(self.file_size_mb, 2),
            "page_count": self.page_count,
            "sha256_hash": self.sha256_hash,
            "is_readable": self.is_readable,
            "issues": self.issues,
        }


@dataclass
class MergeResult:
    """Result of a submission package merge operation."""

    success: bool
    merge_id: str
    loan_id: int
    investor_type: str
    content: bytes = b""
    page_count: int = 0
    file_size: int = 0
    sha256_hash: str = ""
    ordered_docs: List[OrderedDoc] = field(default_factory=list)
    validation: Optional[ValidationResult] = None
    quality_check: Optional[QualityCheckResult] = None
    table_of_contents: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "merge_id": self.merge_id,
            "loan_id": self.loan_id,
            "investor_type": self.investor_type,
            "page_count": self.page_count,
            "file_size": self.file_size,
            "file_size_mb": round(self.file_size / (1024 * 1024), 2) if self.file_size else 0,
            "sha256_hash": self.sha256_hash,
            "document_count": len(self.ordered_docs),
            "table_of_contents": self.table_of_contents,
            "validation": self.validation.to_dict() if self.validation else None,
            "quality_check": self.quality_check.to_dict() if self.quality_check else None,
            "error": self.error,
            "created_at": self.created_at,
        }


@dataclass
class MergeOptions:
    """Configurable options for a merge operation."""

    include_cover_page: bool = True
    include_table_of_contents: bool = True
    include_page_numbers: bool = True
    bates_prefix: str = ""
    bates_start: int = 1
    watermark: Optional[WatermarkType] = None
    watermark_opacity: float = 0.15
    export_format: ExportFormat = ExportFormat.PDF
    encrypt_password: Optional[str] = None
    skip_validation: bool = False
    include_expired: bool = False
    custom_stacking_order: Optional[List[str]] = None


# =============================================================================
# Investor Stacking Orders
# =============================================================================

# Each stacking order is a list of (section_name, [doc_types]) tuples.
# Documents within a section are ordered by their position in the doc_types list.
# Documents not matching any section are appended to a "Miscellaneous" section.

INVESTOR_STACKING_ORDERS: Dict[str, List[Tuple[str, List[str]]]] = {
    InvestorType.FANNIE_MAE_DU: [
        ("Uniform Residential Loan Application", [
            "URLA_1003",
            "URLA_SUPPLEMENTAL",
        ]),
        ("AUS Findings", [
            "DU_FINDINGS",
            "DU_CASEFILE_ID",
        ]),
        ("Credit Report", [
            "CREDIT_REPORT",
            "CREDIT_SUPPLEMENT",
            "CREDIT_EXPLANATION",
        ]),
        ("Income Documentation", [
            "PAYSTUB",
            "W2",
            "TAX_RETURN",
            "BUSINESS_TAX_RETURN",
            "PROFIT_LOSS",
            "BALANCE_SHEET",
            "EMPLOYMENT_VERIFICATION",
            "VERBAL_VOE",
            "SOCIAL_SECURITY_AWARD",
            "PENSION_STATEMENT",
            "RENTAL_INCOME",
        ]),
        ("Asset Documentation", [
            "BANK_STATEMENT",
            "INVESTMENT_STATEMENT",
            "RETIREMENT_STATEMENT",
            "GIFT_LETTER",
            "GIFT_TRANSFER_PROOF",
            "EARNEST_MONEY",
        ]),
        ("Property Documentation", [
            "PURCHASE_CONTRACT",
            "ADDENDUM",
            "APPRAISAL",
            "SECOND_APPRAISAL",
            "FLOOD_CERTIFICATION",
            "CONDO_QUESTIONNAIRE",
        ]),
        ("Title & Insurance", [
            "TITLE_REPORT",
            "TITLE_COMMITMENT",
            "HOMEOWNERS_INSURANCE",
            "FLOOD_INSURANCE",
        ]),
        ("Disclosures", [
            "INITIAL_DISCLOSURE",
            "LOAN_ESTIMATE",
            "CLOSING_DISCLOSURE",
            "BORROWER_CERTIFICATION",
            "PATRIOT_ACT",
        ]),
        ("Identity & Authorization", [
            "DRIVERS_LICENSE",
            "PASSPORT",
            "SSN_CARD",
            "AUTHORIZATION_FORM",
        ]),
        ("Compliance", [
            "HMDA_DATA",
            "FAIR_LENDING",
            "ECOA_NOTICE",
            "SERVICING_DISCLOSURE",
        ]),
        ("Miscellaneous", [
            "LOE",
            "BANKRUPTCY_DISCHARGE",
            "DIVORCE_DECREE",
            "CHILD_SUPPORT_ORDER",
            "OTHER",
        ]),
    ],

    InvestorType.FREDDIE_MAC_LPA: [
        ("Uniform Residential Loan Application", [
            "URLA_1003",
            "URLA_SUPPLEMENTAL",
        ]),
        ("AUS Findings", [
            "LPA_FINDINGS",
            "LPA_KEY_NUMBER",
        ]),
        ("Credit Report", [
            "CREDIT_REPORT",
            "CREDIT_SUPPLEMENT",
            "CREDIT_EXPLANATION",
        ]),
        ("Income Documentation", [
            "PAYSTUB",
            "W2",
            "TAX_RETURN",
            "BUSINESS_TAX_RETURN",
            "PROFIT_LOSS",
            "BALANCE_SHEET",
            "EMPLOYMENT_VERIFICATION",
            "VERBAL_VOE",
            "SOCIAL_SECURITY_AWARD",
            "PENSION_STATEMENT",
            "RENTAL_INCOME",
        ]),
        ("Asset Documentation", [
            "BANK_STATEMENT",
            "INVESTMENT_STATEMENT",
            "RETIREMENT_STATEMENT",
            "GIFT_LETTER",
            "GIFT_TRANSFER_PROOF",
            "EARNEST_MONEY",
        ]),
        ("Property Documentation", [
            "PURCHASE_CONTRACT",
            "ADDENDUM",
            "APPRAISAL",
            "SECOND_APPRAISAL",
            "FLOOD_CERTIFICATION",
            "CONDO_QUESTIONNAIRE",
        ]),
        ("Title & Insurance", [
            "TITLE_REPORT",
            "TITLE_COMMITMENT",
            "HOMEOWNERS_INSURANCE",
            "FLOOD_INSURANCE",
        ]),
        ("Disclosures", [
            "INITIAL_DISCLOSURE",
            "LOAN_ESTIMATE",
            "CLOSING_DISCLOSURE",
            "BORROWER_CERTIFICATION",
            "PATRIOT_ACT",
        ]),
        ("Identity & Authorization", [
            "DRIVERS_LICENSE",
            "PASSPORT",
            "SSN_CARD",
            "AUTHORIZATION_FORM",
        ]),
        ("Compliance", [
            "HMDA_DATA",
            "FAIR_LENDING",
            "ECOA_NOTICE",
            "SERVICING_DISCLOSURE",
        ]),
        ("Miscellaneous", [
            "LOE",
            "BANKRUPTCY_DISCHARGE",
            "DIVORCE_DECREE",
            "CHILD_SUPPORT_ORDER",
            "OTHER",
        ]),
    ],

    InvestorType.FHA: [
        ("FHA Case & AUS", [
            "FHA_CASE_NUMBER",
            "FHA_CERT",
            "DU_FINDINGS",
            "TOTAL_SCORECARD",
        ]),
        ("Uniform Residential Loan Application", [
            "URLA_1003",
            "URLA_SUPPLEMENTAL",
        ]),
        ("Credit Report", [
            "CREDIT_REPORT",
            "CREDIT_SUPPLEMENT",
            "CREDIT_EXPLANATION",
            "CAIVRS_CHECK",
        ]),
        ("Income Documentation", [
            "PAYSTUB",
            "W2",
            "TAX_RETURN",
            "BUSINESS_TAX_RETURN",
            "PROFIT_LOSS",
            "BALANCE_SHEET",
            "EMPLOYMENT_VERIFICATION",
            "VERBAL_VOE",
            "SOCIAL_SECURITY_AWARD",
            "PENSION_STATEMENT",
        ]),
        ("Asset Documentation", [
            "BANK_STATEMENT",
            "INVESTMENT_STATEMENT",
            "GIFT_LETTER",
            "GIFT_TRANSFER_PROOF",
            "EARNEST_MONEY",
        ]),
        ("Property Documentation", [
            "PURCHASE_CONTRACT",
            "ADDENDUM",
            "APPRAISAL",
            "FHA_APPRAISAL_LOG",
            "TERMITE_INSPECTION",
            "WELL_SEPTIC_REPORT",
            "FLOOD_CERTIFICATION",
        ]),
        ("Title & Insurance", [
            "TITLE_REPORT",
            "TITLE_COMMITMENT",
            "HOMEOWNERS_INSURANCE",
            "FLOOD_INSURANCE",
            "FHA_UFMIP",
        ]),
        ("FHA Disclosures", [
            "INITIAL_DISCLOSURE",
            "LOAN_ESTIMATE",
            "CLOSING_DISCLOSURE",
            "FHA_AMENDATORY_CLAUSE",
            "FHA_INFORMED_CONSUMER",
            "BORROWER_CERTIFICATION",
        ]),
        ("Identity & Authorization", [
            "DRIVERS_LICENSE",
            "PASSPORT",
            "SSN_CARD",
            "AUTHORIZATION_FORM",
        ]),
        ("Miscellaneous", [
            "LOE",
            "BANKRUPTCY_DISCHARGE",
            "OTHER",
        ]),
    ],

    InvestorType.VA: [
        ("VA Eligibility", [
            "VA_COE",
            "DD214",
            "VA_26_8937",
            "VA_STATEMENT_OF_SERVICE",
        ]),
        ("Uniform Residential Loan Application", [
            "URLA_1003",
            "URLA_SUPPLEMENTAL",
        ]),
        ("AUS Findings", [
            "DU_FINDINGS",
            "LPA_FINDINGS",
        ]),
        ("Credit Report", [
            "CREDIT_REPORT",
            "CREDIT_SUPPLEMENT",
            "CREDIT_EXPLANATION",
            "CAIVRS_CHECK",
        ]),
        ("Income Documentation", [
            "PAYSTUB",
            "W2",
            "TAX_RETURN",
            "BUSINESS_TAX_RETURN",
            "PROFIT_LOSS",
            "EMPLOYMENT_VERIFICATION",
            "VERBAL_VOE",
            "VA_DISABILITY_AWARD",
            "SOCIAL_SECURITY_AWARD",
            "PENSION_STATEMENT",
        ]),
        ("Asset Documentation", [
            "BANK_STATEMENT",
            "INVESTMENT_STATEMENT",
            "GIFT_LETTER",
            "GIFT_TRANSFER_PROOF",
            "EARNEST_MONEY",
        ]),
        ("Property Documentation", [
            "PURCHASE_CONTRACT",
            "ADDENDUM",
            "APPRAISAL",
            "VA_NOV",
            "TERMITE_INSPECTION",
            "WELL_SEPTIC_REPORT",
            "FLOOD_CERTIFICATION",
        ]),
        ("Title & Insurance", [
            "TITLE_REPORT",
            "TITLE_COMMITMENT",
            "HOMEOWNERS_INSURANCE",
            "FLOOD_INSURANCE",
            "VA_FUNDING_FEE",
        ]),
        ("Disclosures", [
            "INITIAL_DISCLOSURE",
            "LOAN_ESTIMATE",
            "CLOSING_DISCLOSURE",
            "VA_LOAN_SUMMARY",
            "BORROWER_CERTIFICATION",
        ]),
        ("Identity & Authorization", [
            "DRIVERS_LICENSE",
            "PASSPORT",
            "SSN_CARD",
            "AUTHORIZATION_FORM",
        ]),
        ("Miscellaneous", [
            "LOE",
            "BANKRUPTCY_DISCHARGE",
            "DIVORCE_DECREE",
            "OTHER",
        ]),
    ],

    InvestorType.USDA: [
        ("USDA Eligibility", [
            "USDA_ELIGIBILITY",
            "USDA_INCOME_WORKSHEET",
            "USDA_GUS_FINDINGS",
        ]),
        ("Uniform Residential Loan Application", [
            "URLA_1003",
            "URLA_SUPPLEMENTAL",
        ]),
        ("Credit Report", [
            "CREDIT_REPORT",
            "CREDIT_SUPPLEMENT",
            "CREDIT_EXPLANATION",
            "CAIVRS_CHECK",
        ]),
        ("Income Documentation", [
            "PAYSTUB",
            "W2",
            "TAX_RETURN",
            "BUSINESS_TAX_RETURN",
            "PROFIT_LOSS",
            "BALANCE_SHEET",
            "EMPLOYMENT_VERIFICATION",
            "VERBAL_VOE",
            "SOCIAL_SECURITY_AWARD",
            "PENSION_STATEMENT",
        ]),
        ("Asset Documentation", [
            "BANK_STATEMENT",
            "INVESTMENT_STATEMENT",
            "GIFT_LETTER",
            "GIFT_TRANSFER_PROOF",
            "EARNEST_MONEY",
        ]),
        ("Property Documentation", [
            "PURCHASE_CONTRACT",
            "ADDENDUM",
            "APPRAISAL",
            "TERMITE_INSPECTION",
            "WELL_SEPTIC_REPORT",
            "FLOOD_CERTIFICATION",
            "USDA_PROPERTY_ELIGIBILITY",
        ]),
        ("Title & Insurance", [
            "TITLE_REPORT",
            "TITLE_COMMITMENT",
            "HOMEOWNERS_INSURANCE",
            "FLOOD_INSURANCE",
            "USDA_GUARANTEE_FEE",
        ]),
        ("Disclosures", [
            "INITIAL_DISCLOSURE",
            "LOAN_ESTIMATE",
            "CLOSING_DISCLOSURE",
            "BORROWER_CERTIFICATION",
        ]),
        ("Identity & Authorization", [
            "DRIVERS_LICENSE",
            "PASSPORT",
            "SSN_CARD",
            "AUTHORIZATION_FORM",
        ]),
        ("Miscellaneous", [
            "LOE",
            "BANKRUPTCY_DISCHARGE",
            "OTHER",
        ]),
    ],

    InvestorType.JUMBO: [
        ("Uniform Residential Loan Application", [
            "URLA_1003",
            "URLA_SUPPLEMENTAL",
        ]),
        ("AUS / Investor Findings", [
            "DU_FINDINGS",
            "LPA_FINDINGS",
            "INVESTOR_APPROVAL",
        ]),
        ("Credit Report", [
            "CREDIT_REPORT",
            "CREDIT_SUPPLEMENT",
            "CREDIT_EXPLANATION",
        ]),
        ("Income Documentation", [
            "PAYSTUB",
            "W2",
            "TAX_RETURN",
            "BUSINESS_TAX_RETURN",
            "PROFIT_LOSS",
            "BALANCE_SHEET",
            "K1_SCHEDULE",
            "EMPLOYMENT_VERIFICATION",
            "VERBAL_VOE",
            "CPA_LETTER",
            "SOCIAL_SECURITY_AWARD",
            "PENSION_STATEMENT",
            "RENTAL_INCOME",
        ]),
        ("Asset Documentation", [
            "BANK_STATEMENT",
            "INVESTMENT_STATEMENT",
            "RETIREMENT_STATEMENT",
            "STOCK_OPTION_VESTING",
            "TRUST_AGREEMENT",
            "GIFT_LETTER",
            "GIFT_TRANSFER_PROOF",
            "EARNEST_MONEY",
        ]),
        ("Reserves Documentation", [
            "RESERVE_VERIFICATION",
            "ASSET_DEPLETION",
        ]),
        ("Property Documentation", [
            "PURCHASE_CONTRACT",
            "ADDENDUM",
            "APPRAISAL",
            "SECOND_APPRAISAL",
            "DESK_REVIEW",
            "FLOOD_CERTIFICATION",
            "CONDO_QUESTIONNAIRE",
        ]),
        ("Title & Insurance", [
            "TITLE_REPORT",
            "TITLE_COMMITMENT",
            "HOMEOWNERS_INSURANCE",
            "FLOOD_INSURANCE",
            "UMBRELLA_POLICY",
        ]),
        ("Disclosures", [
            "INITIAL_DISCLOSURE",
            "LOAN_ESTIMATE",
            "CLOSING_DISCLOSURE",
            "BORROWER_CERTIFICATION",
            "PATRIOT_ACT",
        ]),
        ("Identity & Authorization", [
            "DRIVERS_LICENSE",
            "PASSPORT",
            "SSN_CARD",
            "AUTHORIZATION_FORM",
        ]),
        ("Miscellaneous", [
            "LOE",
            "BANKRUPTCY_DISCHARGE",
            "DIVORCE_DECREE",
            "CHILD_SUPPORT_ORDER",
            "OTHER",
        ]),
    ],
}

# Required doc types by investor (minimum viable submission)
INVESTOR_REQUIRED_DOCS: Dict[str, List[str]] = {
    InvestorType.FANNIE_MAE_DU: [
        "URLA_1003", "DU_FINDINGS", "CREDIT_REPORT", "PAYSTUB", "W2",
        "BANK_STATEMENT", "APPRAISAL", "TITLE_REPORT", "HOMEOWNERS_INSURANCE",
        "DRIVERS_LICENSE", "INITIAL_DISCLOSURE",
    ],
    InvestorType.FREDDIE_MAC_LPA: [
        "URLA_1003", "LPA_FINDINGS", "CREDIT_REPORT", "PAYSTUB", "W2",
        "BANK_STATEMENT", "APPRAISAL", "TITLE_REPORT", "HOMEOWNERS_INSURANCE",
        "DRIVERS_LICENSE", "INITIAL_DISCLOSURE",
    ],
    InvestorType.FHA: [
        "URLA_1003", "FHA_CERT", "CREDIT_REPORT", "PAYSTUB", "W2",
        "BANK_STATEMENT", "APPRAISAL", "TITLE_REPORT", "HOMEOWNERS_INSURANCE",
        "FHA_UFMIP", "DRIVERS_LICENSE", "INITIAL_DISCLOSURE",
        "FHA_AMENDATORY_CLAUSE",
    ],
    InvestorType.VA: [
        "URLA_1003", "VA_COE", "DD214", "CREDIT_REPORT", "PAYSTUB", "W2",
        "BANK_STATEMENT", "APPRAISAL", "TITLE_REPORT", "HOMEOWNERS_INSURANCE",
        "DRIVERS_LICENSE", "INITIAL_DISCLOSURE",
    ],
    InvestorType.USDA: [
        "URLA_1003", "USDA_ELIGIBILITY", "USDA_GUS_FINDINGS", "CREDIT_REPORT",
        "PAYSTUB", "W2", "BANK_STATEMENT", "APPRAISAL", "TITLE_REPORT",
        "HOMEOWNERS_INSURANCE", "DRIVERS_LICENSE", "INITIAL_DISCLOSURE",
        "USDA_PROPERTY_ELIGIBILITY",
    ],
    InvestorType.JUMBO: [
        "URLA_1003", "CREDIT_REPORT", "PAYSTUB", "W2", "TAX_RETURN",
        "BANK_STATEMENT", "APPRAISAL", "TITLE_REPORT", "HOMEOWNERS_INSURANCE",
        "DRIVERS_LICENSE", "INITIAL_DISCLOSURE",
    ],
}


# =============================================================================
# Service
# =============================================================================


class MergeIntelligenceService(OrgAwareService):
    """
    Intelligent document merge service for loan submission packages.

    Handles:
    - Investor-specific stacking order application
    - Cover page and table of contents generation
    - Bookmarked PDF output with named destinations
    - Bates (sequential compliance) numbering
    - Watermarking (DRAFT, COPY, CONFIDENTIAL)
    - Duplicate and missing document detection
    - Pre-merge validation (ownership, status, expiration)
    - Post-merge quality checks
    - Configurable merge profiles per organization
    """

    def __init__(
        self,
        db: Session,
        org_id: int,
        user_id: Optional[int] = None,
    ):
        super().__init__(db=db, org_id=org_id, user_id=user_id)
        self._company_name = os.getenv("COMPANY_NAME", "The Tim Loss Team")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_submission_package(
        self,
        loan_id: int,
        investor_type: str,
        options: Optional[MergeOptions] = None,
    ) -> MergeResult:
        """Create a complete submission package for a loan.

        Orchestrates the full merge pipeline:
        1. Verify loan ownership (tenant isolation)
        2. Fetch loan metadata
        3. Fetch all approved/active documents for the loan
        4. Apply investor stacking order
        5. Validate completeness and document status
        6. Fetch document content from storage
        7. Generate cover page (optional)
        8. Generate table of contents (optional)
        9. Merge documents in order
        10. Add bookmarks / named destinations
        11. Apply Bates numbering (optional)
        12. Apply watermark (optional)
        13. Apply encryption (optional)
        14. Run post-merge quality check
        15. Return MergeResult

        Args:
            loan_id: Loan to build package for.
            investor_type: One of InvestorType values or "CUSTOM".
            options: Optional merge configuration overrides.

        Returns:
            MergeResult with the merged PDF and metadata.
        """
        opts = options or MergeOptions()
        merge_id = uuid.uuid4().hex[:12].upper()
        now = datetime.now(timezone.utc)

        # Step 1: verify tenant isolation
        try:
            self._verify_loan_ownership(loan_id)
        except Exception as e:
            logger.warning(
                "Merge %s rejected: loan %s access denied for org %s",
                merge_id, loan_id, self.org_id,
            )
            return MergeResult(
                success=False,
                merge_id=merge_id,
                loan_id=loan_id,
                investor_type=investor_type,
                error=str(e),
                created_at=now.isoformat(),
            )

        # Step 2: fetch loan metadata
        loan_data = self._fetch_loan_data(loan_id)
        if not loan_data:
            return MergeResult(
                success=False,
                merge_id=merge_id,
                loan_id=loan_id,
                investor_type=investor_type,
                error=f"Loan {loan_id} not found",
                created_at=now.isoformat(),
            )

        # Step 3: fetch documents
        documents = self._fetch_loan_documents(loan_id, include_expired=opts.include_expired)
        if not documents:
            return MergeResult(
                success=False,
                merge_id=merge_id,
                loan_id=loan_id,
                investor_type=investor_type,
                error="No approved/active documents found for this loan",
                created_at=now.isoformat(),
            )

        # Step 4: apply stacking order
        doc_ids = [d["id"] for d in documents]
        ordered = await self.apply_stacking_order(
            doc_ids, investor_type, custom_order=opts.custom_stacking_order
        )

        # Step 5: validation
        validation = ValidationResult(is_valid=True)
        if not opts.skip_validation:
            validation = await self.validate_package_completeness(
                loan_id, investor_type
            )
            # Also run merge-specific validation
            merge_validation = self._validate_merge_set(documents, opts)
            validation.issues.extend(merge_validation.issues)
            validation.duplicate_docs.extend(merge_validation.duplicate_docs)
            if merge_validation.errors:
                validation.is_valid = False

        # Even with validation errors, we proceed (caller decides whether to use it)
        # but log a warning
        if not validation.is_valid:
            logger.warning(
                "Merge %s: validation found %d errors, proceeding",
                merge_id, len(validation.errors),
            )

        # Step 6: Pre-check total document size BEFORE downloading
        # PERF FIX: Reject early if combined size exceeds MAX_MERGE_FILE_SIZE
        # to avoid downloading hundreds of MB into memory.
        total_estimated_size = sum(doc.file_size for doc in ordered if doc.file_size)
        if total_estimated_size > MAX_MERGE_FILE_SIZE:
            total_mb = total_estimated_size / (1024 * 1024)
            limit_mb = MAX_MERGE_FILE_SIZE / (1024 * 1024)
            logger.warning(
                "Merge %s rejected: estimated size %.1f MB exceeds limit %.0f MB",
                merge_id, total_mb, limit_mb,
            )
            return MergeResult(
                success=False,
                merge_id=merge_id,
                loan_id=loan_id,
                investor_type=investor_type,
                validation=validation,
                error=(
                    f"Total document size ({total_mb:.1f} MB) exceeds the "
                    f"{limit_mb:.0f} MB limit. Remove some documents or split "
                    f"into multiple packages."
                ),
                created_at=now.isoformat(),
            )

        # Fetch document content using temp files to avoid memory bloat
        doc_content_map = self._fetch_document_content(ordered)

        # Build documents list for merge: (content_bytes, display_name, doc_type)
        merge_docs: List[Tuple[bytes, str, str]] = []
        for doc in ordered:
            content = doc_content_map.get(doc.document_id, b"")
            if not content:
                logger.warning(
                    "Merge %s: skipping doc %d (%s) — no content available",
                    merge_id, doc.document_id, doc.display_name,
                )
                validation.issues.append(ValidationIssue(
                    severity="warning",
                    code="CONTENT_UNAVAILABLE",
                    message=f"Document content not available: {doc.display_name}",
                    document_id=doc.document_id,
                    doc_type=doc.doc_type,
                ))
                continue
            merge_docs.append((content, doc.display_name, doc.doc_type))

        if not merge_docs:
            return MergeResult(
                success=False,
                merge_id=merge_id,
                loan_id=loan_id,
                investor_type=investor_type,
                validation=validation,
                error="No document content could be retrieved for merging",
                created_at=now.isoformat(),
            )

        # Step 7-8: generate cover page and ToC (page counts needed first)
        # We need a first pass to calculate page counts before building ToC
        page_counts = self._calculate_page_counts(merge_docs)
        for i, doc in enumerate(ordered):
            if i < len(page_counts):
                doc.page_count = page_counts[i]

        # Build table of contents data
        toc_entries = self._build_toc_entries(ordered)

        # Cover page
        cover_page_content: Optional[bytes] = None
        cover_page_count = 0
        if opts.include_cover_page:
            cover_page_content = self._generate_cover_page(
                merge_id, loan_data, ordered, toc_entries,
            )
            if cover_page_content:
                cover_page_count = self._get_page_count(cover_page_content)

        # ToC page
        toc_content: Optional[bytes] = None
        toc_page_count = 0
        if opts.include_table_of_contents:
            # Adjust start pages for cover + ToC offset
            offset = cover_page_count + 1  # +1 for the ToC page itself (estimate)
            toc_content = self._generate_table_of_contents(
                loan_data, toc_entries, page_offset=offset,
            )
            if toc_content:
                toc_page_count = self._get_page_count(toc_content)
                # Re-adjust offsets now that we know actual ToC size
                offset = cover_page_count + toc_page_count

        # Calculate final start pages for each doc
        running_page = cover_page_count + toc_page_count + 1
        for doc in ordered:
            doc.start_page = running_page
            running_page += doc.page_count

        # Rebuild ToC with final page numbers
        toc_entries = self._build_toc_entries(ordered)

        # Step 9: merge
        if not HAS_PYPDF:
            return MergeResult(
                success=False,
                merge_id=merge_id,
                loan_id=loan_id,
                investor_type=investor_type,
                validation=validation,
                error="pypdf library is required for document merging",
                created_at=now.isoformat(),
            )

        try:
            merged_content = self._merge_pdfs(
                cover_page=cover_page_content,
                toc_page=toc_content,
                documents=merge_docs,
            )
        except Exception as e:
            logger.exception("Merge %s: PDF merge failed", merge_id)
            return MergeResult(
                success=False,
                merge_id=merge_id,
                loan_id=loan_id,
                investor_type=investor_type,
                validation=validation,
                error=f"PDF merge failed: {e}",
                created_at=now.isoformat(),
            )

        # Step 10: add bookmarks
        merged_content = self._add_bookmarks(merged_content, ordered, cover_page_count, toc_page_count)

        # Step 11: Bates numbering
        if opts.include_page_numbers or opts.bates_prefix:
            merged_content = self._apply_bates_numbering(
                merged_content,
                prefix=opts.bates_prefix,
                start=opts.bates_start,
            )

        # Step 12: watermark
        if opts.watermark:
            merged_content = self._apply_watermark(
                merged_content,
                watermark_text=opts.watermark.value,
                opacity=opts.watermark_opacity,
            )

        # Step 13: encryption
        if opts.encrypt_password:
            merged_content = self._apply_encryption(merged_content, opts.encrypt_password)

        # Step 14: quality check
        quality = self._run_quality_check(merged_content)

        total_pages = self._get_page_count(merged_content)
        file_hash = hashlib.sha256(merged_content).hexdigest()

        return MergeResult(
            success=True,
            merge_id=merge_id,
            loan_id=loan_id,
            investor_type=investor_type,
            content=merged_content,
            page_count=total_pages,
            file_size=len(merged_content),
            sha256_hash=file_hash,
            ordered_docs=ordered,
            validation=validation,
            quality_check=quality,
            table_of_contents=toc_entries,
            created_at=now.isoformat(),
        )

    async def validate_package_completeness(
        self,
        loan_id: int,
        investor_type: str,
    ) -> ValidationResult:
        """Validate whether a loan has all required documents for submission.

        Checks:
        - Required documents for the investor type are present and approved
        - No expired documents in the set
        - No duplicate documents

        Args:
            loan_id: Loan ID to check.
            investor_type: Investor type to check requirements against.

        Returns:
            ValidationResult with missing/duplicate/issue lists.
        """
        result = ValidationResult(is_valid=True)

        # Get documents on file
        documents = self._fetch_loan_documents(loan_id, include_expired=True)
        doc_types_on_file = set()
        doc_type_counts: Dict[str, List[int]] = {}

        for doc in documents:
            dtype = doc.get("doc_type") or doc.get("detected_doc_type") or ""
            dtype_upper = dtype.upper()
            doc_types_on_file.add(dtype_upper)
            doc_type_counts.setdefault(dtype_upper, []).append(doc["id"])

            # Check status
            status = (doc.get("status") or "").upper()
            if status == "REJECTED":
                result.issues.append(ValidationIssue(
                    severity="error",
                    code="REJECTED_DOCUMENT",
                    message=f"Document {doc['id']} ({dtype}) has been rejected",
                    document_id=doc["id"],
                    doc_type=dtype,
                ))

            if status == "EXPIRED" or doc.get("is_expired"):
                result.issues.append(ValidationIssue(
                    severity="warning",
                    code="EXPIRED_DOCUMENT",
                    message=f"Document {doc['id']} ({dtype}) is expired",
                    document_id=doc["id"],
                    doc_type=dtype,
                ))

        # Check required documents
        investor_key = investor_type.upper()
        required = INVESTOR_REQUIRED_DOCS.get(investor_key, [])
        for req_type in required:
            if req_type not in doc_types_on_file:
                result.missing_required.append(req_type)
                result.issues.append(ValidationIssue(
                    severity="error",
                    code="MISSING_REQUIRED",
                    message=f"Required document missing: {req_type}",
                    doc_type=req_type,
                ))

        # Check for optional docs not present (from stacking order)
        stacking = INVESTOR_STACKING_ORDERS.get(investor_key, [])
        all_stacking_types = set()
        for _, doc_types in stacking:
            all_stacking_types.update(doc_types)
        optional_missing = all_stacking_types - set(required) - doc_types_on_file
        result.missing_optional = sorted(optional_missing)

        # Check duplicates
        for dtype, doc_ids in doc_type_counts.items():
            if len(doc_ids) > 1:
                for i in range(len(doc_ids)):
                    for j in range(i + 1, len(doc_ids)):
                        result.duplicate_docs.append((doc_ids[i], doc_ids[j], dtype))
                result.issues.append(ValidationIssue(
                    severity="warning",
                    code="DUPLICATE_DOCUMENT",
                    message=f"Multiple {dtype} documents found (IDs: {doc_ids})",
                    doc_type=dtype,
                ))

        if result.missing_required or result.errors:
            result.is_valid = False

        return result

    async def apply_stacking_order(
        self,
        doc_ids: List[int],
        investor_type: str,
        custom_order: Optional[List[str]] = None,
    ) -> List[OrderedDoc]:
        """Apply investor-specific stacking order to a set of documents.

        Args:
            doc_ids: List of smart_document IDs to order.
            investor_type: Investor type for stacking order lookup.
            custom_order: Optional custom section order (list of doc type strings).

        Returns:
            List of OrderedDoc in the correct stacking order.
        """
        if not doc_ids:
            return []

        # Fetch document metadata
        placeholders = ", ".join(f":id_{i}" for i in range(len(doc_ids)))
        params: Dict[str, Any] = {f"id_{i}": did for i, did in enumerate(doc_ids)}
        docs = self._execute_query(
            f"""
            SELECT
                sd.id, sd.doc_type, sd.detected_doc_type,
                sd.display_name, sd.file_name, sd.storage_key,
                sd.file_size, sd.page_count, sd.status
            FROM smart_documents sd
            WHERE sd.id IN ({placeholders})
            """,
            params,
        )

        # Build lookup of doc_type -> sections from stacking order
        investor_key = investor_type.upper()

        if custom_order:
            # Custom order: treat each entry as its own section
            stacking_sections = [
                (dtype, [dtype]) for dtype in custom_order
            ]
        else:
            stacking_sections = INVESTOR_STACKING_ORDERS.get(investor_key, [])

        # Build a priority map: doc_type -> (section_index, position_in_section)
        priority_map: Dict[str, Tuple[int, int]] = {}
        section_names: Dict[str, str] = {}
        for section_idx, (section_name, doc_types) in enumerate(stacking_sections):
            for pos, dtype in enumerate(doc_types):
                priority_map[dtype] = (section_idx, pos)
                section_names[dtype] = section_name

        # Order documents
        ordered: List[OrderedDoc] = []
        unmatched: List[OrderedDoc] = []

        for doc in docs:
            dtype = (doc.get("doc_type") or doc.get("detected_doc_type") or "OTHER").upper()
            display = doc.get("display_name") or doc.get("file_name") or f"Document {doc['id']}"

            if dtype in priority_map:
                section_idx, pos = priority_map[dtype]
                section_name = section_names.get(dtype, "Miscellaneous")
            else:
                section_idx = len(stacking_sections)  # After all defined sections
                pos = 0
                section_name = "Miscellaneous"

            od = OrderedDoc(
                document_id=doc["id"],
                doc_type=dtype,
                display_name=display,
                section_name=section_name,
                section_index=section_idx,
                position_in_section=pos,
                page_count=doc.get("page_count") or 0,
                storage_key=doc.get("storage_key") or "",
                file_size=doc.get("file_size") or 0,
                status=doc.get("status") or "",
            )

            if dtype in priority_map:
                ordered.append(od)
            else:
                unmatched.append(od)

        # Sort by section index, then position within section
        ordered.sort(key=lambda d: (d.section_index, d.position_in_section))
        unmatched.sort(key=lambda d: d.doc_type)

        return ordered + unmatched

    async def add_cover_page(
        self,
        merge_id: str,
        loan_data: Dict[str, Any],
    ) -> Optional[bytes]:
        """Generate a standalone cover page for a merge package.

        This is a convenience method for generating just the cover page
        without running the full merge pipeline.

        Args:
            merge_id: Identifier for the merge operation.
            loan_data: Loan metadata dict (borrower_name, loan_number, etc.).

        Returns:
            PDF bytes for the cover page, or None on failure.
        """
        return self._generate_cover_page(merge_id, loan_data, [], [])

    # ------------------------------------------------------------------
    # Internal: Database Queries
    # ------------------------------------------------------------------

    def _execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Execute a SQL query and return results as list of dicts."""
        result = self.db.execute(text(query), params or {})
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def _execute_single(self, query: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Execute a query and return a single result."""
        results = self._execute_query(query, params)
        return results[0] if results else None

    def _verify_loan_ownership(self, loan_id: int) -> None:
        """Verify loan belongs to this org. Raises on mismatch."""
        row = self._execute_single(
            "SELECT organization_id FROM loans WHERE id = :loan_id",
            {"loan_id": loan_id},
        )
        if not row:
            raise ValueError(f"Loan {loan_id} not found")
        self._require_org_match(row["organization_id"])

    def _fetch_loan_data(self, loan_id: int) -> Optional[Dict[str, Any]]:
        """Fetch loan metadata for cover page and validation."""
        return self._execute_single(
            """
            SELECT
                l.id, l.loan_number, l.borrower_name, l.borrower_email,
                l.property_address, l.loan_type, l.amount, l.rate,
                l.stage, l.application_date, l.closing_date,
                l.organization_id,
                CONCAT(u.first_name, ' ', u.last_name) as lo_name
            FROM loans l
            LEFT JOIN users u ON u.id = l.loan_officer_id
            WHERE l.id = :loan_id
            """,
            {"loan_id": loan_id},
        )

    def _fetch_loan_documents(
        self,
        loan_id: int,
        include_expired: bool = False,
    ) -> List[Dict]:
        """Fetch all documents for a loan from smart_documents table.

        Only returns documents with APPROVED status unless include_expired
        is True, in which case EXPIRED docs are also included.
        """
        status_filter = "sd.status IN ('APPROVED')"
        if include_expired:
            status_filter = "sd.status IN ('APPROVED', 'EXPIRED')"

        return self._execute_query(
            f"""
            SELECT
                sd.id, sd.doc_type, sd.detected_doc_type,
                sd.display_name, sd.file_name, sd.storage_key,
                sd.file_size, sd.page_count, sd.status,
                sd.is_expired, sd.doc_expires_at,
                sd.borrower_id
            FROM smart_documents sd
            WHERE sd.loan_id = :loan_id
                AND {status_filter}
            ORDER BY sd.doc_type, sd.uploaded_at DESC
            """,
            {"loan_id": loan_id},
        )

    def _fetch_document_content(
        self,
        ordered_docs: List[OrderedDoc],
    ) -> Dict[int, bytes]:
        """Fetch actual file content for documents from S3 storage.

        PERF FIX: Uses temp files for downloads to avoid keeping all document
        bytes in memory simultaneously when building the map. Also enforces
        a running total size check to bail early if we exceed limits.

        Returns a mapping of document_id -> file_bytes.
        """
        content_map: Dict[int, bytes] = {}

        try:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
            s3_service = get_smart_docs_s3_service()
        except Exception as e:
            logger.error("Cannot initialize S3 service: %s", e)
            return content_map

        running_size = 0
        for doc in ordered_docs:
            if not doc.storage_key:
                continue
            try:
                # Download to a temp file first, then read into memory
                # only if cumulative size is within limits
                with tempfile.NamedTemporaryFile(delete=True) as tmp:
                    file_data = s3_service.download_file(doc.storage_key)
                    if file_data:
                        running_size += len(file_data)
                        if running_size > MAX_MERGE_FILE_SIZE:
                            logger.warning(
                                "Merge content fetch stopped: running total %d bytes "
                                "exceeds limit %d bytes at doc %d",
                                running_size, MAX_MERGE_FILE_SIZE, doc.document_id,
                            )
                            break
                        content_map[doc.document_id] = file_data
            except Exception as e:
                logger.warning(
                    "Failed to fetch document %d (key=%s): %s",
                    doc.document_id, doc.storage_key, e,
                )

        return content_map

    # ------------------------------------------------------------------
    # Internal: Merge Validation
    # ------------------------------------------------------------------

    def _validate_merge_set(
        self,
        documents: List[Dict],
        options: MergeOptions,
    ) -> ValidationResult:
        """Validate the document set for merge eligibility.

        Checks:
        - All documents belong to the same loan
        - All documents are in approved/active status
        - No expired documents (unless include_expired)
        - Duplicate detection via file hash or doc_type
        """
        result = ValidationResult(is_valid=True)

        loan_ids = set()
        seen_types: Dict[str, List[int]] = {}
        seen_hashes: Dict[str, List[int]] = {}

        for doc in documents:
            doc_id = doc["id"]
            loan_id = doc.get("loan_id")
            if loan_id:
                loan_ids.add(loan_id)

            # Status check
            status = (doc.get("status") or "").upper()
            if status not in ("APPROVED", "ACTIVE"):
                if status == "EXPIRED" and options.include_expired:
                    result.issues.append(ValidationIssue(
                        severity="info",
                        code="EXPIRED_INCLUDED",
                        message=f"Expired document included per options: {doc_id}",
                        document_id=doc_id,
                    ))
                elif status == "EXPIRED":
                    result.issues.append(ValidationIssue(
                        severity="error",
                        code="EXPIRED_DOCUMENT",
                        message=f"Document {doc_id} is expired",
                        document_id=doc_id,
                    ))
                    result.is_valid = False

            # Duplicate detection by doc_type
            dtype = (doc.get("doc_type") or doc.get("detected_doc_type") or "").upper()
            if dtype:
                seen_types.setdefault(dtype, []).append(doc_id)

        # Multi-loan check
        if len(loan_ids) > 1:
            result.issues.append(ValidationIssue(
                severity="error",
                code="MULTI_LOAN",
                message=f"Documents span multiple loans: {loan_ids}",
            ))
            result.is_valid = False

        # Duplicate reporting
        for dtype, ids in seen_types.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        result.duplicate_docs.append((ids[i], ids[j], dtype))
                result.issues.append(ValidationIssue(
                    severity="warning",
                    code="DUPLICATE_DOC_TYPE",
                    message=f"Duplicate {dtype}: document IDs {ids}",
                    doc_type=dtype,
                ))

        return result

    # ------------------------------------------------------------------
    # Internal: PDF Operations
    # ------------------------------------------------------------------

    def _merge_pdfs(
        self,
        cover_page: Optional[bytes],
        toc_page: Optional[bytes],
        documents: List[Tuple[bytes, str, str]],
    ) -> bytes:
        """Merge cover page, ToC, and documents into a single PDF.

        Args:
            cover_page: Optional cover page PDF bytes.
            toc_page: Optional table of contents PDF bytes.
            documents: List of (content_bytes, display_name, doc_type).

        Returns:
            Merged PDF bytes.
        """
        writer = PdfWriter()

        # Add cover page
        if cover_page:
            self._append_pdf_to_writer(writer, cover_page)

        # Add table of contents
        if toc_page:
            self._append_pdf_to_writer(writer, toc_page)

        # Add each document
        for content, display_name, doc_type in documents:
            if not content:
                continue
            # Convert images to PDF if needed
            lower_name = display_name.lower()
            if lower_name.endswith((".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp")):
                content = self._image_to_pdf(content)
                if not content:
                    logger.warning("Skipping non-convertible image: %s", display_name)
                    continue

            try:
                self._append_pdf_to_writer(writer, content)
            except Exception as e:
                logger.warning(
                    "Skipping unreadable document %s: %s", display_name, e
                )

        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()

    def _append_pdf_to_writer(self, writer: PdfWriter, pdf_content: bytes) -> None:
        """Append all pages from a PDF to the writer."""
        reader = PdfReader(io.BytesIO(pdf_content))
        for page in reader.pages:
            writer.add_page(page)

    def _add_bookmarks(
        self,
        pdf_content: bytes,
        ordered_docs: List[OrderedDoc],
        cover_pages: int,
        toc_pages: int,
    ) -> bytes:
        """Add PDF bookmarks (outlines) for each section and document.

        Creates a two-level bookmark tree:
        - Level 1: Section name (e.g., "Income Documentation")
        - Level 2: Individual document (e.g., "W2 - 2024")
        """
        if not HAS_PYPDF or not ordered_docs:
            return pdf_content

        try:
            reader = PdfReader(io.BytesIO(pdf_content))
            writer = PdfWriter()

            for page in reader.pages:
                writer.add_page(page)

            # Copy metadata
            if reader.metadata:
                writer.add_metadata(reader.metadata)

            prefix_pages = cover_pages + toc_pages
            current_section = None
            section_bookmark = None

            # Add cover page bookmark
            if cover_pages > 0:
                writer.add_outline_item("Cover Page", 0)

            # Add ToC bookmark
            if toc_pages > 0:
                writer.add_outline_item("Table of Contents", cover_pages)

            for doc in ordered_docs:
                page_idx = doc.start_page - 1  # 0-based
                if page_idx < 0 or page_idx >= len(writer.pages):
                    continue

                # Section-level bookmark
                if doc.section_name != current_section:
                    current_section = doc.section_name
                    section_bookmark = writer.add_outline_item(
                        current_section, page_idx
                    )

                # Document-level bookmark (child of section)
                writer.add_outline_item(
                    doc.display_name,
                    page_idx,
                    parent=section_bookmark,
                )

            buf = io.BytesIO()
            writer.write(buf)
            return buf.getvalue()

        except Exception as e:
            logger.warning("Failed to add bookmarks: %s", e)
            return pdf_content

    def _apply_bates_numbering(
        self,
        pdf_content: bytes,
        prefix: str = "",
        start: int = 1,
    ) -> bytes:
        """Apply Bates numbering (sequential page stamps) for compliance.

        Each page gets a stamp like "ABC-000001" in the bottom-right corner.
        If no prefix, uses standard "Page X of Y" format.
        """
        if not HAS_REPORTLAB or not HAS_PYPDF:
            return pdf_content

        try:
            reader = PdfReader(io.BytesIO(pdf_content))
            writer = PdfWriter()
            total_pages = len(reader.pages)

            for page_idx in range(total_pages):
                page = reader.pages[page_idx]
                page_w = float(page.mediabox.width)
                page_h = float(page.mediabox.height)
                bates_num = start + page_idx

                # Create overlay
                overlay_buf = io.BytesIO()
                c = rl_canvas.Canvas(overlay_buf, pagesize=(page_w, page_h))
                c.setFont("Courier", 8)
                c.setFillColor(colors.HexColor("#666666"))

                if prefix:
                    stamp = f"{prefix}-{bates_num:06d}"
                else:
                    stamp = f"Page {bates_num} of {total_pages + start - 1}"

                # Bottom-right corner
                c.drawRightString(page_w - 36, 20, stamp)
                c.save()

                overlay_reader = PdfReader(io.BytesIO(overlay_buf.getvalue()))
                page.merge_page(overlay_reader.pages[0])
                writer.add_page(page)

            buf = io.BytesIO()
            writer.write(buf)
            return buf.getvalue()

        except Exception as e:
            logger.warning("Failed to apply Bates numbering: %s", e)
            return pdf_content

    def _apply_watermark(
        self,
        pdf_content: bytes,
        watermark_text: str,
        opacity: float = 0.15,
    ) -> bytes:
        """Apply a diagonal watermark to every page."""
        if not HAS_REPORTLAB or not HAS_PYPDF:
            return pdf_content

        try:
            reader = PdfReader(io.BytesIO(pdf_content))
            writer = PdfWriter()

            # Build watermark from first page dimensions
            first_page = reader.pages[0]
            page_w = float(first_page.mediabox.width)
            page_h = float(first_page.mediabox.height)
            watermark_pdf = self._create_watermark_page(
                watermark_text, opacity, page_w, page_h,
            )
            watermark_reader = PdfReader(io.BytesIO(watermark_pdf))
            watermark_page = watermark_reader.pages[0]

            for page in reader.pages:
                page.merge_page(watermark_page)
                writer.add_page(page)

            buf = io.BytesIO()
            writer.write(buf)
            return buf.getvalue()

        except Exception as e:
            logger.warning("Failed to apply watermark: %s", e)
            return pdf_content

    def _create_watermark_page(
        self,
        text_value: str,
        opacity: float,
        page_width: float,
        page_height: float,
    ) -> bytes:
        """Create a single-page PDF with diagonal watermark text."""
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(page_width, page_height))
        c.saveState()
        c.setFillColor(colors.Color(0.5, 0.5, 0.5, alpha=opacity))
        c.setFont("Helvetica-Bold", 72)
        c.translate(page_width / 2, page_height / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, text_value)
        c.restoreState()
        c.save()
        return buf.getvalue()

    def _apply_encryption(
        self,
        pdf_content: bytes,
        password: str,
    ) -> bytes:
        """Encrypt the merged PDF with AES-256.

        Sets user password (required to open) and owner password (full permissions).
        """
        if not HAS_PYPDF:
            return pdf_content

        try:
            reader = PdfReader(io.BytesIO(pdf_content))
            writer = PdfWriter()

            for page in reader.pages:
                writer.add_page(page)

            # Copy metadata and bookmarks
            if reader.metadata:
                writer.add_metadata(reader.metadata)

            writer.encrypt(
                user_password=password,
                owner_password=password,
                use_128bit=True,  # AES-128 for broader compatibility
            )

            buf = io.BytesIO()
            writer.write(buf)
            return buf.getvalue()

        except Exception as e:
            logger.warning("Failed to encrypt PDF: %s", e)
            return pdf_content

    # ------------------------------------------------------------------
    # Internal: Cover Page & Table of Contents
    # ------------------------------------------------------------------

    def _generate_cover_page(
        self,
        merge_id: str,
        loan_data: Dict[str, Any],
        ordered_docs: List[OrderedDoc],
        toc_entries: List[Dict[str, Any]],
    ) -> Optional[bytes]:
        """Generate a professional cover page for the submission package."""
        if not HAS_REPORTLAB:
            return self._generate_cover_page_fallback(merge_id, loan_data, ordered_docs)

        try:
            buf = io.BytesIO()
            c = rl_canvas.Canvas(buf, pagesize=letter)
            width, height = letter

            # Header bar
            c.setFillColor(colors.HexColor("#1E3A5F"))
            c.rect(0, height - 110, width, 110, fill=True, stroke=False)

            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 22)
            c.drawCentredString(width / 2, height - 45, "Loan Submission Package")

            c.setFont("Helvetica", 12)
            c.drawCentredString(width / 2, height - 70, self._company_name)

            c.setFont("Helvetica", 10)
            c.drawCentredString(
                width / 2, height - 90,
                f"Package ID: {merge_id}",
            )

            # Loan details section
            y = height - 145
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(_MARGIN, y, "Loan Information")
            y -= 5
            c.setStrokeColor(colors.HexColor("#2563EB"))
            c.setLineWidth(1.5)
            c.line(_MARGIN, y, width - _MARGIN, y)
            y -= 22

            info_fields = [
                ("Borrower:", loan_data.get("borrower_name", "N/A")),
                ("Loan Number:", loan_data.get("loan_number", "N/A")),
                ("Property:", loan_data.get("property_address", "N/A")),
                ("Loan Type:", (loan_data.get("loan_type") or "N/A").upper()),
                ("Loan Amount:", f"${float(loan_data.get('amount') or 0):,.2f}"),
                ("Rate:", f"{float(loan_data.get('rate') or 0):.3f}%" if loan_data.get("rate") else "N/A"),
                ("Loan Officer:", loan_data.get("lo_name", "N/A")),
                ("Stage:", loan_data.get("stage", "N/A")),
            ]

            c.setFont("Helvetica", 11)
            for label, value in info_fields:
                c.setFont("Helvetica-Bold", 11)
                c.drawString(_MARGIN, y, label)
                c.setFont("Helvetica", 11)
                c.drawString(_MARGIN + 130, y, str(value))
                y -= 18

            # Package summary
            y -= 15
            c.setFont("Helvetica-Bold", 14)
            c.drawString(_MARGIN, y, "Package Summary")
            y -= 5
            c.setStrokeColor(colors.HexColor("#2563EB"))
            c.line(_MARGIN, y, width - _MARGIN, y)
            y -= 22

            total_pages = sum(d.page_count for d in ordered_docs)
            sections = set(d.section_name for d in ordered_docs)

            summary_items = [
                ("Documents:", str(len(ordered_docs))),
                ("Sections:", str(len(sections))),
                ("Total Pages:", str(total_pages)),
                ("Generated:", datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")),
            ]

            c.setFont("Helvetica", 11)
            for label, value in summary_items:
                c.setFont("Helvetica-Bold", 11)
                c.drawString(_MARGIN, y, label)
                c.setFont("Helvetica", 11)
                c.drawString(_MARGIN + 130, y, value)
                y -= 18

            # Footer
            c.setFont("Helvetica-Oblique", 8)
            c.setFillColor(colors.HexColor("#999999"))
            c.drawCentredString(
                width / 2, 40,
                f"Generated by {self._company_name} | Package {merge_id}",
            )
            c.drawCentredString(
                width / 2, 28,
                "This document is confidential and intended solely for the named recipient.",
            )

            c.save()
            return buf.getvalue()

        except Exception as e:
            logger.exception("Failed to generate cover page")
            return self._generate_cover_page_fallback(merge_id, loan_data, ordered_docs)

    def _generate_cover_page_fallback(
        self,
        merge_id: str,
        loan_data: Dict[str, Any],
        ordered_docs: List[OrderedDoc],
    ) -> Optional[bytes]:
        """Generate a plain-text cover page when reportlab is unavailable."""
        lines = [
            "LOAN SUBMISSION PACKAGE",
            self._company_name,
            f"Package ID: {merge_id}",
            "",
            "--- Loan Information ---",
            f"Borrower: {loan_data.get('borrower_name', 'N/A')}",
            f"Loan Number: {loan_data.get('loan_number', 'N/A')}",
            f"Property: {loan_data.get('property_address', 'N/A')}",
            f"Loan Type: {(loan_data.get('loan_type') or 'N/A').upper()}",
            "",
            f"--- Package Summary ---",
            f"Documents: {len(ordered_docs)}",
            f"Generated: {datetime.now(timezone.utc).strftime('%B %d, %Y')}",
        ]
        return self._create_simple_text_pdf("\n".join(lines))

    def _generate_table_of_contents(
        self,
        loan_data: Dict[str, Any],
        toc_entries: List[Dict[str, Any]],
        page_offset: int = 0,
    ) -> Optional[bytes]:
        """Generate a table of contents page."""
        if not HAS_REPORTLAB:
            return self._generate_toc_fallback(toc_entries, page_offset)

        try:
            buf = io.BytesIO()
            c = rl_canvas.Canvas(buf, pagesize=letter)
            width, height = letter

            # Title
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(width / 2, height - 50, "Table of Contents")
            c.setFont("Helvetica", 10)
            c.setFillColor(colors.HexColor("#555555"))
            c.drawCentredString(
                width / 2, height - 68,
                f"Loan #{loan_data.get('loan_number', 'N/A')} | {loan_data.get('borrower_name', 'N/A')}",
            )

            c.setStrokeColor(colors.HexColor("#2563EB"))
            c.setLineWidth(1.5)
            c.line(_MARGIN, height - 78, width - _MARGIN, height - 78)

            y = height - 105
            current_section = None

            for entry in toc_entries:
                if y < 60:
                    c.showPage()
                    y = height - 50

                section = entry.get("section", "")
                doc_name = entry.get("name", "")
                page_num = entry.get("start_page", 0) + page_offset

                # Section header
                if section != current_section:
                    current_section = section
                    y -= 8
                    c.setFillColor(colors.HexColor("#F1F5F9"))
                    c.rect(_MARGIN, y - 4, width - 2 * _MARGIN, 18, fill=True, stroke=False)
                    c.setFillColor(colors.HexColor("#1E3A5F"))
                    c.setFont("Helvetica-Bold", 11)
                    c.drawString(_MARGIN + 5, y, section)
                    y -= 22

                # Document entry with dot leaders
                c.setFillColor(colors.black)
                c.setFont("Helvetica", 10)

                # Truncate long names
                max_name_width = width - 2 * _MARGIN - 80
                displayed_name = doc_name
                while c.stringWidth(displayed_name, "Helvetica", 10) > max_name_width and len(displayed_name) > 10:
                    displayed_name = displayed_name[:-4] + "..."

                c.drawString(_MARGIN + 15, y, displayed_name)

                # Page number on the right
                page_text = str(page_num) if page_num > 0 else ""
                c.drawRightString(width - _MARGIN, y, page_text)

                # Dot leaders
                name_end = _MARGIN + 20 + c.stringWidth(displayed_name, "Helvetica", 10)
                page_start = width - _MARGIN - c.stringWidth(page_text, "Helvetica", 10) - 5
                if page_start - name_end > 20:
                    c.setFillColor(colors.HexColor("#CCCCCC"))
                    c.setFont("Helvetica", 8)
                    dots = " . " * int((page_start - name_end) / 12)
                    c.drawString(name_end + 5, y, dots)

                c.setFillColor(colors.black)
                y -= 16

            c.save()
            return buf.getvalue()

        except Exception as e:
            logger.exception("Failed to generate table of contents")
            return self._generate_toc_fallback(toc_entries, page_offset)

    def _generate_toc_fallback(
        self,
        toc_entries: List[Dict[str, Any]],
        page_offset: int = 0,
    ) -> Optional[bytes]:
        """Plain-text table of contents fallback."""
        lines = ["TABLE OF CONTENTS", ""]
        current_section = None
        for entry in toc_entries:
            section = entry.get("section", "")
            if section != current_section:
                current_section = section
                lines.append(f"\n{section}")
                lines.append("-" * len(section))
            page_num = entry.get("start_page", 0) + page_offset
            name = entry.get("name", "")
            lines.append(f"  {name} {'.' * max(1, 50 - len(name))} {page_num}")
        return self._create_simple_text_pdf("\n".join(lines))

    # ------------------------------------------------------------------
    # Internal: Helpers
    # ------------------------------------------------------------------

    def _build_toc_entries(
        self,
        ordered_docs: List[OrderedDoc],
    ) -> List[Dict[str, Any]]:
        """Build table of contents entries from ordered documents."""
        entries = []
        for doc in ordered_docs:
            entries.append({
                "section": doc.section_name,
                "name": doc.display_name,
                "doc_type": doc.doc_type,
                "start_page": doc.start_page,
                "page_count": doc.page_count,
                "document_id": doc.document_id,
            })
        return entries

    def _calculate_page_counts(
        self,
        documents: List[Tuple[bytes, str, str]],
    ) -> List[int]:
        """Calculate page count for each document in the list."""
        counts = []
        for content, name, _ in documents:
            counts.append(self._get_page_count(content))
        return counts

    def _get_page_count(self, pdf_content: bytes) -> int:
        """Get page count from PDF content."""
        if not pdf_content:
            return 0
        if not HAS_PYPDF:
            # Rough estimate
            count = pdf_content.count(b"/Type /Page")
            pages_count = pdf_content.count(b"/Type /Pages")
            return max(count - pages_count, 1)
        try:
            reader = PdfReader(io.BytesIO(pdf_content))
            return len(reader.pages)
        except Exception:
            return 0

    def _run_quality_check(self, pdf_content: bytes) -> QualityCheckResult:
        """Run post-merge quality assessment.

        Checks:
        - File is not empty
        - File size within limits
        - Page count within limits
        - PDF is readable (can be parsed)
        - Text can be extracted from at least one page
        """
        issues: List[str] = []
        file_size = len(pdf_content)
        file_size_mb = file_size / (1024 * 1024)

        if not pdf_content:
            return QualityCheckResult(
                passed=False,
                file_size_bytes=0,
                file_size_mb=0,
                page_count=0,
                sha256_hash="",
                is_readable=False,
                issues=["Merged PDF is empty"],
            )

        sha256 = hashlib.sha256(pdf_content).hexdigest()

        # Size check
        if file_size > MAX_MERGE_FILE_SIZE:
            issues.append(
                f"File size ({file_size_mb:.1f} MB) exceeds limit "
                f"({MAX_MERGE_FILE_SIZE / (1024*1024):.0f} MB)"
            )

        # Readability check
        page_count = 0
        is_readable = False
        if HAS_PYPDF:
            try:
                reader = PdfReader(io.BytesIO(pdf_content))
                page_count = len(reader.pages)
                is_readable = True

                # Try to extract text from first page
                if page_count > 0:
                    try:
                        first_page_text = reader.pages[0].extract_text()
                        if not first_page_text or len(first_page_text.strip()) == 0:
                            issues.append(
                                "First page has no extractable text (may be scanned/image)"
                            )
                    except Exception:
                        issues.append("Could not extract text from first page")

            except Exception as e:
                is_readable = False
                issues.append(f"PDF is not readable: {e}")
        else:
            page_count = self._get_page_count(pdf_content)

        # Page count check
        if page_count > MAX_MERGE_PAGE_COUNT:
            issues.append(
                f"Page count ({page_count}) exceeds limit ({MAX_MERGE_PAGE_COUNT})"
            )

        if page_count == 0:
            issues.append("Merged PDF has 0 pages")

        passed = is_readable and not any(
            "exceeds limit" in issue or "not readable" in issue or "0 pages" in issue
            for issue in issues
        )

        return QualityCheckResult(
            passed=passed,
            file_size_bytes=file_size,
            file_size_mb=file_size_mb,
            page_count=page_count,
            sha256_hash=sha256,
            is_readable=is_readable,
            issues=issues,
        )

    def _image_to_pdf(self, image_content: bytes) -> bytes:
        """Convert an image to a single-page PDF.

        Delegates to PDFGenerationService if available.
        """
        try:
            from services.smart_docs.pdf_generation_service import get_pdf_generation_service
            pdf_svc = get_pdf_generation_service()
            return pdf_svc.image_to_pdf(image_content, "image.jpg")
        except Exception as e:
            logger.warning("Image to PDF conversion failed: %s", e)
            return b""

    def _create_simple_text_pdf(self, text_content: str) -> Optional[bytes]:
        """Create a minimal text-only PDF."""
        try:
            from services.smart_docs.pdf_generation_service import get_pdf_generation_service
            pdf_svc = get_pdf_generation_service()
            return pdf_svc._create_simple_pdf(text_content, title="Submission Package")
        except Exception as e:
            logger.warning("Simple PDF creation failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Org Merge Profiles
    # ------------------------------------------------------------------

    def get_merge_profile(self, profile_name: Optional[str] = None) -> MergeOptions:
        """Load a configurable merge profile for this organization.

        Merge profiles are stored in the organization's settings JSON.
        Falls back to sensible defaults if no profile is configured.

        Args:
            profile_name: Optional named profile. None uses the org default.

        Returns:
            MergeOptions populated from the profile.
        """
        row = self._execute_single(
            """
            SELECT settings FROM organizations
            WHERE id = :org_id
            """,
            {"org_id": self.org_id},
        )

        defaults = MergeOptions()

        if not row or not row.get("settings"):
            return defaults

        settings = row["settings"]
        if not isinstance(settings, dict):
            return defaults

        profiles = settings.get("merge_profiles", {})
        profile_key = profile_name or settings.get("default_merge_profile", "default")
        profile = profiles.get(profile_key, {})

        if not profile:
            return defaults

        return MergeOptions(
            include_cover_page=profile.get("include_cover_page", defaults.include_cover_page),
            include_table_of_contents=profile.get("include_table_of_contents", defaults.include_table_of_contents),
            include_page_numbers=profile.get("include_page_numbers", defaults.include_page_numbers),
            bates_prefix=profile.get("bates_prefix", defaults.bates_prefix),
            bates_start=profile.get("bates_start", defaults.bates_start),
            watermark=WatermarkType(profile["watermark"]) if profile.get("watermark") else defaults.watermark,
            watermark_opacity=profile.get("watermark_opacity", defaults.watermark_opacity),
            export_format=ExportFormat(profile.get("export_format", defaults.export_format.value)),
            encrypt_password=profile.get("encrypt_password"),
            skip_validation=profile.get("skip_validation", defaults.skip_validation),
            include_expired=profile.get("include_expired", defaults.include_expired),
            custom_stacking_order=profile.get("custom_stacking_order"),
        )


# =============================================================================
# Factory
# =============================================================================

def get_merge_intelligence_service(
    db: Session,
    org_id: int,
    user_id: Optional[int] = None,
) -> MergeIntelligenceService:
    """Create a MergeIntelligenceService instance.

    This is NOT a singleton -- it is scoped to a request/session because
    it carries org_id context for tenant isolation.

    Args:
        db: SQLAlchemy session.
        org_id: Organization ID for tenant isolation.
        user_id: Authenticated user ID.

    Returns:
        MergeIntelligenceService instance.
    """
    return MergeIntelligenceService(db=db, org_id=org_id, user_id=user_id)
