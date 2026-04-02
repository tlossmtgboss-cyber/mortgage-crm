"""
Document Comparison Service

Compares two versions of the same document (or cross-source documents) to
identify changes, flag suspicious modifications, and generate compliance-ready
comparison reports. Core use cases:

1. Revised vs. original document comparison (e.g., corrected W-2, updated paystub)
2. Borrower-submitted vs. IRS transcript data validation
3. Financial field tolerance-based matching (rounding, minor formatting diffs OK)
4. Fraud detection: changed income, altered employer info, modified dates/fonts
5. Visual page-level PDF diff for manual review queues
6. Full audit trail of every comparison performed

Integrates with:
    - smart_documents / smart_document_extractions for extracted field data
    - pdf_forensics_service for structural PDF analysis
    - fraud_detection_service for shared risk scoring
    - document_ocr_service for text extraction when needed
    - s3_storage_service for file retrieval
    - decision_audit_service for audit logging
    - irs_transcript_service for transcript comparisons

Usage:
    from services.smart_docs.document_comparison_service import (
        DocumentComparisonService,
        get_document_comparison_service,
    )

    service = get_document_comparison_service(db)
    result = await service.compare_documents(
        doc_id_1=100, doc_id_2=101,
        comparison_type="revision",
        org_id=5, user_id=42,
    )
    if result.risk_score >= 70:
        # Flag for compliance review
        ...
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from exceptions import EntityNotFoundError, TenantIsolationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency imports (graceful degradation)
# ---------------------------------------------------------------------------

_pdf_forensics_mod = None
_ocr_service_mod = None
_s3_service_mod = None


def _get_pdf_forensics():
    global _pdf_forensics_mod
    if _pdf_forensics_mod is None:
        try:
            from services.smart_docs import pdf_forensics_service as mod
            _pdf_forensics_mod = mod
        except ImportError:
            logger.debug("pdf_forensics_service not available for comparison")
    return _pdf_forensics_mod


def _get_ocr_service():
    global _ocr_service_mod
    if _ocr_service_mod is None:
        try:
            from services.smart_docs.document_ocr_service import get_document_ocr_service
            _ocr_service_mod = get_document_ocr_service
        except ImportError:
            logger.debug("document_ocr_service not available for comparison")
    return _ocr_service_mod


def _get_s3_service():
    global _s3_service_mod
    if _s3_service_mod is None:
        try:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
            _s3_service_mod = get_smart_docs_s3_service
        except ImportError:
            logger.debug("s3_storage_service not available for comparison")
    return _s3_service_mod


# =============================================================================
# CONSTANTS
# =============================================================================

ZERO = Decimal("0.00")
TWO_PLACES = Decimal("0.01")

# Tolerance thresholds for financial comparisons (percentage)
DEFAULT_TOLERANCES: Dict[str, Decimal] = {
    "income": Decimal("1.0"),         # 1% for income fields (rounding)
    "assets": Decimal("0.5"),         # 0.5% for asset balances
    "tax_withholding": Decimal("5.0"),  # 5% for withholding (mid-year changes)
    "general": Decimal("2.0"),        # 2% general financial tolerance
}

# Absolute dollar tolerance (small amounts under this are always OK)
ABSOLUTE_DOLLAR_TOLERANCE = Decimal("1.00")

# Fields where changes are especially suspicious
HIGH_RISK_FIELDS = {
    "gross_pay", "net_pay", "ytd_gross", "ytd_net", "annual_income",
    "monthly_income", "base_salary", "total_income",
    "wages_tips_compensation", "social_security_wages",
    "employer_name", "employer_ein", "employee_name", "employee_ssn_last4",
    "account_balance", "ending_balance", "beginning_balance",
    "adjusted_gross_income", "taxable_income", "total_tax",
}

# Fields that should never change between versions of the same document
IMMUTABLE_FIELDS = {
    "employer_ein", "employee_ssn_last4", "pay_period_start", "pay_period_end",
    "tax_year", "account_number_last4",
}

# Severity weights for risk scoring
SEVERITY_WEIGHTS = {
    "CRITICAL": 30,
    "HIGH": 18,
    "MEDIUM": 8,
    "LOW": 3,
    "INFO": 0,
}

# Risk level thresholds
RISK_THRESHOLDS = {
    "CRITICAL": 70,
    "HIGH": 45,
    "MEDIUM": 20,
    "LOW": 0,
}


# =============================================================================
# ENUMS
# =============================================================================

class ComparisonType(str, Enum):
    """Type of document comparison being performed."""
    REVISION = "revision"                 # Revised doc vs. original
    CROSS_SOURCE = "cross_source"         # Borrower-submitted vs. third-party (IRS, etc.)
    DUPLICATE_CHECK = "duplicate_check"   # Check if two docs are substantially identical
    TEMPORAL = "temporal"                 # Same doc type across time periods


class ChangeSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ChangeCategory(str, Enum):
    INCOME_MODIFIED = "INCOME_MODIFIED"
    EMPLOYER_MODIFIED = "EMPLOYER_MODIFIED"
    IDENTITY_MODIFIED = "IDENTITY_MODIFIED"
    DATE_MODIFIED = "DATE_MODIFIED"
    ASSET_MODIFIED = "ASSET_MODIFIED"
    TAX_MODIFIED = "TAX_MODIFIED"
    TEXT_MODIFIED = "TEXT_MODIFIED"
    STRUCTURAL_CHANGE = "STRUCTURAL_CHANGE"
    FONT_INCONSISTENCY = "FONT_INCONSISTENCY"
    METADATA_ANOMALY = "METADATA_ANOMALY"


class ComparisonStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"       # Some comparisons failed but others succeeded
    FAILED = "failed"
    PENDING_REVIEW = "pending_review"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class FieldDifference:
    """A single field-level difference between two documents."""
    field_name: str
    value_1: Any                 # Value from document 1
    value_2: Any                 # Value from document 2
    category: str                # ChangeCategory value
    severity: str                # ChangeSeverity value
    description: str
    is_within_tolerance: bool
    tolerance_pct: Optional[float] = None
    variance_pct: Optional[float] = None
    variance_abs: Optional[float] = None
    confidence_1: Optional[int] = None   # Extraction confidence for doc 1 field
    confidence_2: Optional[int] = None   # Extraction confidence for doc 2 field


@dataclass
class SuspiciousChange:
    """A potentially fraudulent modification detected between documents."""
    change_id: str
    category: str              # ChangeCategory value
    severity: str              # ChangeSeverity value
    description: str
    evidence: str
    field_name: Optional[str] = None
    original_value: Any = None
    modified_value: Any = None
    risk_contribution: int = 0
    recommendation: str = ""


@dataclass
class TextDiffSegment:
    """A segment of a text diff."""
    operation: str             # "equal", "insert", "delete", "replace"
    text_1: str = ""
    text_2: str = ""
    line_number_1: Optional[int] = None
    line_number_2: Optional[int] = None


@dataclass
class PageComparison:
    """Page-level comparison result for PDF documents."""
    page_number: int
    similarity_score: float    # 0.0 to 1.0
    text_changes: int
    has_structural_changes: bool
    diff_segments: List[TextDiffSegment] = field(default_factory=list)


@dataclass
class FieldComparisonResult:
    """Result of comparing extracted fields between two documents."""
    total_fields_compared: int
    matching_fields: int
    differing_fields: int
    within_tolerance: int
    outside_tolerance: int
    missing_in_1: List[str] = field(default_factory=list)
    missing_in_2: List[str] = field(default_factory=list)
    differences: List[FieldDifference] = field(default_factory=list)
    match_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_fields_compared": self.total_fields_compared,
            "matching_fields": self.matching_fields,
            "differing_fields": self.differing_fields,
            "within_tolerance": self.within_tolerance,
            "outside_tolerance": self.outside_tolerance,
            "missing_in_doc_1": self.missing_in_1,
            "missing_in_doc_2": self.missing_in_2,
            "match_rate": round(self.match_rate, 2),
            "differences": [
                {
                    "field": d.field_name,
                    "value_1": _safe_serialize(d.value_1),
                    "value_2": _safe_serialize(d.value_2),
                    "category": d.category,
                    "severity": d.severity,
                    "description": d.description,
                    "within_tolerance": d.is_within_tolerance,
                    "variance_pct": d.variance_pct,
                }
                for d in self.differences
            ],
        }


@dataclass
class ComparisonResult:
    """Complete comparison result between two documents."""
    comparison_id: str
    doc_id_1: int
    doc_id_2: int
    comparison_type: str        # ComparisonType value
    status: str                 # ComparisonStatus value
    performed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    performed_by: Optional[int] = None   # user_id

    # Field comparison
    field_comparison: Optional[FieldComparisonResult] = None

    # Text diff
    text_similarity: float = 0.0
    page_comparisons: List[PageComparison] = field(default_factory=list)

    # Suspicious changes
    suspicious_changes: List[SuspiciousChange] = field(default_factory=list)

    # Risk assessment
    risk_score: int = 0          # 0-100
    risk_level: str = "LOW"      # LOW, MEDIUM, HIGH, CRITICAL

    # Metadata
    doc_1_info: Dict[str, Any] = field(default_factory=dict)
    doc_2_info: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    recommendations: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "doc_id_1": self.doc_id_1,
            "doc_id_2": self.doc_id_2,
            "comparison_type": self.comparison_type,
            "status": self.status,
            "performed_at": self.performed_at.isoformat() if self.performed_at else None,
            "performed_by": self.performed_by,
            "field_comparison": self.field_comparison.to_dict() if self.field_comparison else None,
            "text_similarity": round(self.text_similarity, 4),
            "page_comparisons": [
                {
                    "page": pc.page_number,
                    "similarity": round(pc.similarity_score, 4),
                    "text_changes": pc.text_changes,
                    "structural_changes": pc.has_structural_changes,
                }
                for pc in self.page_comparisons
            ],
            "suspicious_changes": [
                {
                    "change_id": sc.change_id,
                    "category": sc.category,
                    "severity": sc.severity,
                    "description": sc.description,
                    "evidence": sc.evidence,
                    "field_name": sc.field_name,
                    "original_value": _safe_serialize(sc.original_value),
                    "modified_value": _safe_serialize(sc.modified_value),
                    "risk_contribution": sc.risk_contribution,
                    "recommendation": sc.recommendation,
                }
                for sc in self.suspicious_changes
            ],
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "doc_1_info": self.doc_1_info,
            "doc_2_info": self.doc_2_info,
            "summary": self.summary,
            "recommendations": self.recommendations,
            "errors": self.errors,
        }


# =============================================================================
# HELPERS
# =============================================================================

def _safe_serialize(value: Any) -> Any:
    """Convert a value to a JSON-safe representation."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Attempt to convert a value to Decimal."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        cleaned = str(value).replace(",", "").replace("$", "").strip()
        if not cleaned:
            return None
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _normalize_string(value: Any) -> str:
    """Normalize a string for comparison (case-insensitive, whitespace-normalized)."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _classify_field(field_name: str) -> str:
    """Determine the ChangeCategory for a given field name."""
    field_lower = field_name.lower()

    income_keywords = {"pay", "wage", "salary", "income", "earnings", "bonus", "commission", "tips", "ytd"}
    employer_keywords = {"employer", "company", "ein", "business"}
    identity_keywords = {"name", "ssn", "employee", "borrower", "address"}
    date_keywords = {"date", "period", "year"}
    asset_keywords = {"balance", "account", "deposit", "withdrawal"}
    tax_keywords = {"tax", "withholding", "deduction", "fica", "medicare", "social_security"}

    if any(kw in field_lower for kw in income_keywords):
        return ChangeCategory.INCOME_MODIFIED.value
    if any(kw in field_lower for kw in employer_keywords):
        return ChangeCategory.EMPLOYER_MODIFIED.value
    if any(kw in field_lower for kw in identity_keywords):
        return ChangeCategory.IDENTITY_MODIFIED.value
    if any(kw in field_lower for kw in date_keywords):
        return ChangeCategory.DATE_MODIFIED.value
    if any(kw in field_lower for kw in asset_keywords):
        return ChangeCategory.ASSET_MODIFIED.value
    if any(kw in field_lower for kw in tax_keywords):
        return ChangeCategory.TAX_MODIFIED.value

    return ChangeCategory.TEXT_MODIFIED.value


def _determine_severity(
    field_name: str,
    category: str,
    variance_pct: Optional[float],
    is_immutable: bool,
) -> str:
    """Determine the severity of a field change."""
    if is_immutable:
        return ChangeSeverity.CRITICAL.value

    if field_name in HIGH_RISK_FIELDS:
        if variance_pct is not None and abs(variance_pct) > 10:
            return ChangeSeverity.CRITICAL.value
        if variance_pct is not None and abs(variance_pct) > 5:
            return ChangeSeverity.HIGH.value
        return ChangeSeverity.MEDIUM.value

    high_risk_categories = {
        ChangeCategory.INCOME_MODIFIED.value,
        ChangeCategory.EMPLOYER_MODIFIED.value,
        ChangeCategory.IDENTITY_MODIFIED.value,
    }
    if category in high_risk_categories:
        return ChangeSeverity.HIGH.value

    return ChangeSeverity.LOW.value


def _determine_tolerance(field_name: str) -> Decimal:
    """Get the tolerance percentage for a given field."""
    field_lower = field_name.lower()

    if any(kw in field_lower for kw in ("pay", "wage", "salary", "income", "earnings", "gross", "net", "ytd")):
        return DEFAULT_TOLERANCES["income"]
    if any(kw in field_lower for kw in ("balance", "deposit", "account")):
        return DEFAULT_TOLERANCES["assets"]
    if any(kw in field_lower for kw in ("tax", "withholding", "fica", "medicare")):
        return DEFAULT_TOLERANCES["tax_withholding"]

    return DEFAULT_TOLERANCES["general"]


def _calculate_risk_score(suspicious_changes: List[SuspiciousChange]) -> Tuple[int, str]:
    """Calculate overall risk score from suspicious changes."""
    if not suspicious_changes:
        return 0, "LOW"

    raw_score = sum(sc.risk_contribution for sc in suspicious_changes)
    # Cap at 100
    score = min(raw_score, 100)

    if score >= RISK_THRESHOLDS["CRITICAL"]:
        level = "CRITICAL"
    elif score >= RISK_THRESHOLDS["HIGH"]:
        level = "HIGH"
    elif score >= RISK_THRESHOLDS["MEDIUM"]:
        level = "MEDIUM"
    else:
        level = "LOW"

    return score, level


# =============================================================================
# SERVICE
# =============================================================================

class DocumentComparisonService:
    """
    Compares document versions, cross-source data, and generates risk-scored
    comparison reports with full audit trails.

    All methods enforce org_id isolation. Comparisons are persisted to the
    document_comparisons table for regulatory audit.
    """

    def __init__(self, db: Session):
        self.db = db

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    async def compare_documents(
        self,
        doc_id_1: int,
        doc_id_2: int,
        comparison_type: str = ComparisonType.REVISION.value,
        org_id: Optional[int] = None,
        user_id: Optional[int] = None,
        custom_tolerances: Optional[Dict[str, float]] = None,
    ) -> ComparisonResult:
        """
        Compare two documents and produce a comprehensive comparison result.

        Args:
            doc_id_1: ID of the first (original/baseline) document.
            doc_id_2: ID of the second (revised/comparison) document.
            comparison_type: One of ComparisonType values.
            org_id: Organization ID for tenant isolation.
            user_id: ID of the user performing the comparison.
            custom_tolerances: Override default tolerances {field_name: pct}.

        Returns:
            ComparisonResult with field diffs, text diffs, suspicious changes,
            and risk scoring.

        Raises:
            EntityNotFoundError: If either document is not found.
            TenantIsolationError: If documents belong to different organizations
                                 or do not match the provided org_id.
        """
        comparison_id = f"CMP-{uuid.uuid4().hex[:12].upper()}"

        logger.info(
            "Starting document comparison",
            extra={
                "comparison_id": comparison_id,
                "doc_id_1": doc_id_1,
                "doc_id_2": doc_id_2,
                "comparison_type": comparison_type,
                "org_id": org_id,
                "user_id": user_id,
            },
        )

        # 1. Load document metadata
        doc_1 = self._load_document(doc_id_1, org_id)
        doc_2 = self._load_document(doc_id_2, org_id)

        # 2. Verify tenant isolation
        if org_id is not None:
            self._verify_org_access(doc_1, doc_2, org_id)

        result = ComparisonResult(
            comparison_id=comparison_id,
            doc_id_1=doc_id_1,
            doc_id_2=doc_id_2,
            comparison_type=comparison_type,
            performed_by=user_id,
            doc_1_info=self._doc_summary(doc_1),
            doc_2_info=self._doc_summary(doc_2),
        )

        # 3. Load extractions for field comparison
        extraction_1 = self._load_extraction(doc_id_1)
        extraction_2 = self._load_extraction(doc_id_2)

        # 4. Field-level comparison
        if extraction_1 and extraction_2:
            fields_1 = extraction_1.get("extracted_fields") or {}
            fields_2 = extraction_2.get("extracted_fields") or {}
            confidences_1 = extraction_1.get("confidence_scores") or {}
            confidences_2 = extraction_2.get("confidence_scores") or {}

            tolerances = self._build_tolerances(custom_tolerances)
            result.field_comparison = self.compare_extracted_fields(
                fields_1, fields_2,
                tolerances=tolerances,
                confidences_1=confidences_1,
                confidences_2=confidences_2,
            )
        else:
            result.errors.append(
                "Field comparison skipped: extraction data not available for one or both documents"
            )

        # 5. Text diff
        text_1 = doc_1.get("ocr_text") or ""
        text_2 = doc_2.get("ocr_text") or ""
        if text_1 and text_2:
            result.text_similarity = self._compute_text_similarity(text_1, text_2)
            result.page_comparisons = self._compare_text_by_page(text_1, text_2)
        elif text_1 or text_2:
            result.errors.append("Text diff partial: OCR text missing for one document")

        # 6. Visual / structural PDF comparison
        await self._compare_pdf_structure(doc_1, doc_2, result)

        # 7. Flag suspicious changes
        suspicious = await self.flag_suspicious_changes(
            doc_id_1, doc_id_2,
            field_comparison=result.field_comparison,
            text_similarity=result.text_similarity,
            doc_1_info=doc_1,
            doc_2_info=doc_2,
        )
        result.suspicious_changes = suspicious

        # 8. Risk scoring
        result.risk_score, result.risk_level = _calculate_risk_score(suspicious)

        # 9. Generate summary and recommendations
        result.summary = self._generate_summary(result)
        result.recommendations = self._generate_recommendations(result)

        # 10. Determine status
        if result.errors and not result.field_comparison and not result.page_comparisons:
            result.status = ComparisonStatus.FAILED.value
        elif result.errors:
            result.status = ComparisonStatus.PARTIAL.value
        elif result.risk_score >= RISK_THRESHOLDS["HIGH"]:
            result.status = ComparisonStatus.PENDING_REVIEW.value
        else:
            result.status = ComparisonStatus.COMPLETED.value

        # 11. Persist audit trail
        self._save_comparison_audit(result, org_id)

        logger.info(
            "Document comparison completed",
            extra={
                "comparison_id": comparison_id,
                "risk_score": result.risk_score,
                "risk_level": result.risk_level,
                "status": result.status,
                "suspicious_count": len(suspicious),
            },
        )

        return result

    def compare_extracted_fields(
        self,
        fields_1: Dict[str, Any],
        fields_2: Dict[str, Any],
        tolerances: Optional[Dict[str, Decimal]] = None,
        confidences_1: Optional[Dict[str, int]] = None,
        confidences_2: Optional[Dict[str, int]] = None,
    ) -> FieldComparisonResult:
        """
        Compare two sets of extracted fields with tolerance-based matching.

        Args:
            fields_1: Extracted fields from document 1.
            fields_2: Extracted fields from document 2.
            tolerances: Field-specific tolerance percentages {field_name: pct}.
            confidences_1: Confidence scores for fields_1.
            confidences_2: Confidence scores for fields_2.

        Returns:
            FieldComparisonResult with detailed per-field diff.
        """
        if tolerances is None:
            tolerances = {}
        if confidences_1 is None:
            confidences_1 = {}
        if confidences_2 is None:
            confidences_2 = {}

        all_keys = set(fields_1.keys()) | set(fields_2.keys())
        missing_in_1 = sorted(set(fields_2.keys()) - set(fields_1.keys()))
        missing_in_2 = sorted(set(fields_1.keys()) - set(fields_2.keys()))
        common_keys = sorted(set(fields_1.keys()) & set(fields_2.keys()))

        differences: List[FieldDifference] = []
        matching = 0
        within_tol = 0
        outside_tol = 0

        for key in common_keys:
            val_1 = fields_1[key]
            val_2 = fields_2[key]

            # Try numeric comparison first
            dec_1 = _to_decimal(val_1)
            dec_2 = _to_decimal(val_2)

            if dec_1 is not None and dec_2 is not None:
                # Numeric comparison with tolerance
                tol_pct = tolerances.get(key, _determine_tolerance(key))
                is_match, variance_pct, variance_abs = self._compare_numeric(
                    dec_1, dec_2, tol_pct,
                )

                if is_match and variance_abs == ZERO:
                    matching += 1
                    continue

                is_immutable = key in IMMUTABLE_FIELDS
                category = _classify_field(key)
                severity = _determine_severity(
                    key, category, float(variance_pct) if variance_pct else None, is_immutable,
                )

                diff = FieldDifference(
                    field_name=key,
                    value_1=float(dec_1),
                    value_2=float(dec_2),
                    category=category,
                    severity=severity,
                    description=self._describe_numeric_diff(key, dec_1, dec_2, variance_pct),
                    is_within_tolerance=is_match,
                    tolerance_pct=float(tol_pct),
                    variance_pct=float(variance_pct) if variance_pct is not None else None,
                    variance_abs=float(variance_abs) if variance_abs is not None else None,
                    confidence_1=confidences_1.get(key),
                    confidence_2=confidences_2.get(key),
                )
                differences.append(diff)

                if is_match:
                    within_tol += 1
                else:
                    outside_tol += 1
            else:
                # String comparison
                norm_1 = _normalize_string(val_1)
                norm_2 = _normalize_string(val_2)

                if norm_1 == norm_2:
                    matching += 1
                    continue

                is_immutable = key in IMMUTABLE_FIELDS
                category = _classify_field(key)
                severity = _determine_severity(key, category, None, is_immutable)

                diff = FieldDifference(
                    field_name=key,
                    value_1=val_1,
                    value_2=val_2,
                    category=category,
                    severity=severity,
                    description=f"'{key}' changed from '{val_1}' to '{val_2}'",
                    is_within_tolerance=False,
                    confidence_1=confidences_1.get(key),
                    confidence_2=confidences_2.get(key),
                )
                differences.append(diff)
                outside_tol += 1

        total_compared = len(common_keys)
        differing = len(differences)
        match_rate = (matching / total_compared * 100.0) if total_compared > 0 else 0.0

        return FieldComparisonResult(
            total_fields_compared=total_compared,
            matching_fields=matching,
            differing_fields=differing,
            within_tolerance=within_tol,
            outside_tolerance=outside_tol,
            missing_in_1=missing_in_1,
            missing_in_2=missing_in_2,
            differences=differences,
            match_rate=match_rate,
        )

    async def generate_comparison_report(
        self,
        comparison_id: str,
        org_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate a detailed comparison report from a persisted comparison.

        Args:
            comparison_id: The comparison ID to retrieve.
            org_id: Organization ID for tenant isolation.

        Returns:
            Dictionary with full comparison report data.

        Raises:
            EntityNotFoundError: If comparison_id is not found.
        """
        row = self._load_comparison_audit(comparison_id, org_id)
        if not row:
            raise EntityNotFoundError("DocumentComparison", comparison_id)

        report = {
            "report_id": f"RPT-{comparison_id}",
            "comparison_id": comparison_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "comparison_data": row.get("comparison_data") or {},
            "doc_1_id": row.get("doc_id_1"),
            "doc_2_id": row.get("doc_id_2"),
            "comparison_type": row.get("comparison_type"),
            "risk_score": row.get("risk_score"),
            "risk_level": row.get("risk_level"),
            "status": row.get("status"),
            "performed_at": row.get("performed_at").isoformat() if row.get("performed_at") else None,
            "performed_by": row.get("performed_by"),
        }

        # Enrich with current document info (may have been updated since comparison)
        for doc_key, doc_id_key in [("doc_1_current", "doc_id_1"), ("doc_2_current", "doc_id_2")]:
            doc_id = row.get(doc_id_key)
            if doc_id:
                try:
                    doc = self._load_document(doc_id, org_id=None)  # No org check on report gen
                    report[doc_key] = self._doc_summary(doc)
                except Exception as e:
                    logger.warning(
                        "Could not load document for report enrichment",
                        extra={"doc_id": doc_id, "error": str(e)},
                    )

        return report

    async def flag_suspicious_changes(
        self,
        doc_id_1: int,
        doc_id_2: int,
        field_comparison: Optional[FieldComparisonResult] = None,
        text_similarity: float = 0.0,
        doc_1_info: Optional[Dict[str, Any]] = None,
        doc_2_info: Optional[Dict[str, Any]] = None,
    ) -> List[SuspiciousChange]:
        """
        Detect potentially fraudulent modifications between two documents.

        Checks:
            - Changed income amounts between versions
            - Modified employer information
            - Altered dates or periods
            - Font inconsistencies between original and revision
            - Immutable field changes (SSN, EIN, pay periods)
            - Substantial text changes with minor metadata changes

        Args:
            doc_id_1: ID of the original document.
            doc_id_2: ID of the revised document.
            field_comparison: Pre-computed field comparison result.
            text_similarity: Pre-computed text similarity score.
            doc_1_info: Document 1 metadata dict.
            doc_2_info: Document 2 metadata dict.

        Returns:
            List of SuspiciousChange objects, sorted by severity.
        """
        suspicious: List[SuspiciousChange] = []

        # --- Check 1: Field-level suspicious changes ---
        if field_comparison:
            for diff in field_comparison.differences:
                if diff.is_within_tolerance:
                    continue

                change = self._evaluate_field_suspicion(diff)
                if change:
                    suspicious.append(change)

        # --- Check 2: Immutable field modifications ---
        if field_comparison:
            for diff in field_comparison.differences:
                if diff.field_name in IMMUTABLE_FIELDS and not diff.is_within_tolerance:
                    suspicious.append(SuspiciousChange(
                        change_id=f"IMMUT-{uuid.uuid4().hex[:8]}",
                        category=ChangeCategory.IDENTITY_MODIFIED.value,
                        severity=ChangeSeverity.CRITICAL.value,
                        description=(
                            f"Immutable field '{diff.field_name}' was modified. "
                            f"This field should never change between document versions."
                        ),
                        evidence=(
                            f"Original: {_safe_serialize(diff.value_1)}, "
                            f"Modified: {_safe_serialize(diff.value_2)}"
                        ),
                        field_name=diff.field_name,
                        original_value=diff.value_1,
                        modified_value=diff.value_2,
                        risk_contribution=SEVERITY_WEIGHTS["CRITICAL"],
                        recommendation=(
                            "Investigate immediately. Request original document from issuing entity. "
                            "Consider filing SAR if modification appears intentional."
                        ),
                    ))

        # --- Check 3: Income manipulation patterns ---
        if field_comparison:
            income_diffs = [
                d for d in field_comparison.differences
                if d.category == ChangeCategory.INCOME_MODIFIED.value
                and not d.is_within_tolerance
                and d.variance_pct is not None
            ]
            upward_shifts = [d for d in income_diffs if d.variance_pct and d.variance_pct > 0]
            if len(upward_shifts) >= 2:
                total_shift = sum(d.variance_pct for d in upward_shifts if d.variance_pct)
                suspicious.append(SuspiciousChange(
                    change_id=f"INCPAT-{uuid.uuid4().hex[:8]}",
                    category=ChangeCategory.INCOME_MODIFIED.value,
                    severity=ChangeSeverity.HIGH.value,
                    description=(
                        f"Multiple income fields increased simultaneously: "
                        f"{len(upward_shifts)} fields shifted upward by avg "
                        f"{total_shift / len(upward_shifts):.1f}%"
                    ),
                    evidence=", ".join(
                        f"{d.field_name}: +{d.variance_pct:.1f}%" for d in upward_shifts
                    ),
                    risk_contribution=SEVERITY_WEIGHTS["HIGH"],
                    recommendation=(
                        "Pattern consistent with income inflation. Verify against "
                        "third-party sources (VOE, IRS transcript, bank statements)."
                    ),
                ))

        # --- Check 4: Font / structural inconsistencies via PDF forensics ---
        await self._check_font_inconsistencies(doc_1_info, doc_2_info, suspicious)

        # --- Check 5: Metadata anomalies ---
        self._check_metadata_anomalies(doc_1_info, doc_2_info, suspicious)

        # --- Check 6: Text similarity anomaly ---
        # Very low text similarity for a "revision" suggests replacement, not revision
        if text_similarity > 0 and text_similarity < 0.3:
            suspicious.append(SuspiciousChange(
                change_id=f"TXTSIM-{uuid.uuid4().hex[:8]}",
                category=ChangeCategory.STRUCTURAL_CHANGE.value,
                severity=ChangeSeverity.MEDIUM.value,
                description=(
                    f"Very low text similarity ({text_similarity:.1%}) between documents. "
                    f"These may not be versions of the same document."
                ),
                evidence=f"Text similarity: {text_similarity:.4f}",
                risk_contribution=SEVERITY_WEIGHTS["MEDIUM"],
                recommendation=(
                    "Verify both documents are intended versions of the same record. "
                    "If so, investigate why content differs so substantially."
                ),
            ))

        # Sort by severity (CRITICAL first)
        severity_order = {
            ChangeSeverity.CRITICAL.value: 0,
            ChangeSeverity.HIGH.value: 1,
            ChangeSeverity.MEDIUM.value: 2,
            ChangeSeverity.LOW.value: 3,
            ChangeSeverity.INFO.value: 4,
        }
        suspicious.sort(key=lambda sc: severity_order.get(sc.severity, 5))

        return suspicious

    async def compare_borrower_vs_transcript(
        self,
        loan_id: int,
        tax_year: int,
        org_id: int,
        user_id: Optional[int] = None,
    ) -> ComparisonResult:
        """
        Compare borrower-submitted tax documents against IRS transcript data.

        Retrieves the borrower's tax return extraction and the corresponding
        IRS transcript data, then performs a cross-source comparison with
        IRS-specific tolerance rules.

        Args:
            loan_id: Loan ID to look up documents for.
            tax_year: Tax year to compare.
            org_id: Organization ID for tenant isolation.
            user_id: User performing the comparison.

        Returns:
            ComparisonResult with cross-source analysis.
        """
        comparison_id = f"IRS-{uuid.uuid4().hex[:12].upper()}"

        logger.info(
            "Starting borrower vs IRS transcript comparison",
            extra={
                "comparison_id": comparison_id,
                "loan_id": loan_id,
                "tax_year": tax_year,
                "org_id": org_id,
            },
        )

        # Load borrower-submitted tax return extraction
        borrower_data = self._load_tax_return_extraction(loan_id, tax_year, org_id)

        # Load IRS transcript data
        transcript_data = self._load_irs_transcript_data(loan_id, tax_year, org_id)

        if not borrower_data and not transcript_data:
            result = ComparisonResult(
                comparison_id=comparison_id,
                doc_id_1=0,
                doc_id_2=0,
                comparison_type=ComparisonType.CROSS_SOURCE.value,
                status=ComparisonStatus.FAILED.value,
                performed_by=user_id,
            )
            result.errors.append(
                f"No borrower tax return or IRS transcript found for "
                f"loan {loan_id}, tax year {tax_year}"
            )
            return result

        if not borrower_data:
            result = ComparisonResult(
                comparison_id=comparison_id,
                doc_id_1=0,
                doc_id_2=0,
                comparison_type=ComparisonType.CROSS_SOURCE.value,
                status=ComparisonStatus.FAILED.value,
                performed_by=user_id,
            )
            result.errors.append(
                f"No borrower-submitted tax return found for loan {loan_id}, tax year {tax_year}"
            )
            return result

        if not transcript_data:
            result = ComparisonResult(
                comparison_id=comparison_id,
                doc_id_1=borrower_data.get("doc_id", 0),
                doc_id_2=0,
                comparison_type=ComparisonType.CROSS_SOURCE.value,
                status=ComparisonStatus.FAILED.value,
                performed_by=user_id,
            )
            result.errors.append(
                f"No IRS transcript data found for loan {loan_id}, tax year {tax_year}"
            )
            return result

        # IRS-specific tolerances (IRS transcripts may round differently)
        irs_tolerances = {
            "wages_tips_compensation": Decimal("1.0"),
            "adjusted_gross_income": Decimal("1.0"),
            "taxable_income": Decimal("1.0"),
            "total_tax": Decimal("2.0"),
            "self_employment_income": Decimal("1.0"),
            "social_security_wages": Decimal("1.0"),
            "interest_income": Decimal("5.0"),  # Aggregation differences
            "dividend_income": Decimal("5.0"),
        }

        borrower_fields = borrower_data.get("fields", {})
        transcript_fields = transcript_data.get("fields", {})

        field_comparison = self.compare_extracted_fields(
            fields_1=borrower_fields,
            fields_2=transcript_fields,
            tolerances=irs_tolerances,
        )

        suspicious = await self.flag_suspicious_changes(
            doc_id_1=borrower_data.get("doc_id", 0),
            doc_id_2=0,
            field_comparison=field_comparison,
        )

        risk_score, risk_level = _calculate_risk_score(suspicious)

        result = ComparisonResult(
            comparison_id=comparison_id,
            doc_id_1=borrower_data.get("doc_id", 0),
            doc_id_2=0,
            comparison_type=ComparisonType.CROSS_SOURCE.value,
            status=ComparisonStatus.PENDING_REVIEW.value if risk_score >= RISK_THRESHOLDS["HIGH"]
            else ComparisonStatus.COMPLETED.value,
            performed_by=user_id,
            field_comparison=field_comparison,
            suspicious_changes=suspicious,
            risk_score=risk_score,
            risk_level=risk_level,
            doc_1_info={"source": "borrower_submitted", "tax_year": tax_year, "loan_id": loan_id},
            doc_2_info={"source": "irs_transcript", "tax_year": tax_year, "loan_id": loan_id},
        )

        result.summary = self._generate_summary(result)
        result.recommendations = self._generate_recommendations(result)

        # Persist audit trail
        self._save_comparison_audit(result, org_id)

        return result

    def get_comparison_history(
        self,
        org_id: int,
        doc_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Get audit trail of comparisons performed, filtered by org and optionally
        by document or loan.

        Args:
            org_id: Organization ID (required for tenant isolation).
            doc_id: Optional document ID filter.
            loan_id: Optional loan ID filter.
            limit: Maximum results to return.
            offset: Pagination offset.

        Returns:
            Dictionary with comparisons list and total count.
        """
        params: Dict[str, Any] = {"org_id": org_id, "limit": limit, "offset": offset}
        filters = ["dc.organization_id = :org_id"]

        if doc_id is not None:
            filters.append("(dc.doc_id_1 = :doc_id OR dc.doc_id_2 = :doc_id)")
            params["doc_id"] = doc_id

        if loan_id is not None:
            filters.append("dc.loan_id = :loan_id")
            params["loan_id"] = loan_id

        where_sql = " AND ".join(filters)

        count_q = "SELECT COUNT(*) as cnt FROM document_comparisons dc WHERE " + where_sql
        count_row = self.db.execute(text(count_q), params).fetchone()
        total = count_row[0] if count_row else 0

        list_q = (
            "SELECT"
            " dc.comparison_id, dc.doc_id_1, dc.doc_id_2,"
            " dc.comparison_type, dc.risk_score, dc.risk_level,"
            " dc.status, dc.performed_at, dc.performed_by"
            " FROM document_comparisons dc"
            " WHERE " + where_sql
            + " ORDER BY dc.performed_at DESC"
            " LIMIT :limit OFFSET :offset"
        )
        rows = self.db.execute(text(list_q), params).fetchall()

        columns = [
            "comparison_id", "doc_id_1", "doc_id_2",
            "comparison_type", "risk_score", "risk_level",
            "status", "performed_at", "performed_by",
        ]

        comparisons = []
        for row in rows:
            entry = dict(zip(columns, row))
            if entry.get("performed_at"):
                entry["performed_at"] = entry["performed_at"].isoformat()
            comparisons.append(entry)

        return {
            "comparisons": comparisons,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    # -------------------------------------------------------------------------
    # INTERNAL: Document loading
    # -------------------------------------------------------------------------

    def _load_document(self, doc_id: int, org_id: Optional[int]) -> Dict[str, Any]:
        """Load document metadata from smart_documents table."""
        params: Dict[str, Any] = {"doc_id": doc_id}
        org_filter = ""
        if org_id is not None:
            # Smart documents do not have org_id directly; join via loan
            org_filter = """
                AND EXISTS (
                    SELECT 1 FROM loans l
                    WHERE l.id = sd.loan_id AND l.organization_id = :org_id
                )
            """
            params["org_id"] = org_id

        load_doc_query = (
            "SELECT"
            " sd.id, sd.loan_id, sd.borrower_id,"
            " sd.file_name, sd.original_filename, sd.mime_type,"
            " sd.file_size, sd.storage_key, sd.page_count,"
            " sd.doc_type, sd.detected_doc_type,"
            " sd.ocr_text, sd.extracted_dates, sd.extracted_names,"
            " sd.extracted_employer, sd.extracted_amount,"
            " sd.extraction_confidence,"
            " sd.doc_date, sd.status, sd.decision,"
            " sd.uploaded_at, sd.created_at, sd.updated_at"
            " FROM smart_documents sd"
            " WHERE sd.id = :doc_id " + org_filter
        )
        row = self.db.execute(text(load_doc_query), params).fetchone()

        if not row:
            raise EntityNotFoundError("SmartDocument", doc_id)

        columns = [
            "id", "loan_id", "borrower_id",
            "file_name", "original_filename", "mime_type",
            "file_size", "storage_key", "page_count",
            "doc_type", "detected_doc_type",
            "ocr_text", "extracted_dates", "extracted_names",
            "extracted_employer", "extracted_amount",
            "extraction_confidence",
            "doc_date", "status", "decision",
            "uploaded_at", "created_at", "updated_at",
        ]
        return dict(zip(columns, row))

    def _load_extraction(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """Load extraction data for a document."""
        row = self.db.execute(
            text("""
                SELECT
                    extracted_fields, confidence_scores, provenance,
                    overall_confidence, extraction_model
                FROM smart_document_extractions
                WHERE document_id = :doc_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"doc_id": doc_id},
        ).fetchone()

        if not row:
            return None

        columns = [
            "extracted_fields", "confidence_scores", "provenance",
            "overall_confidence", "extraction_model",
        ]
        return dict(zip(columns, row))

    def _load_tax_return_extraction(
        self, loan_id: int, tax_year: int, org_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Load borrower-submitted tax return extraction for comparison."""
        row = self.db.execute(
            text("""
                SELECT
                    sd.id as doc_id,
                    sde.extracted_fields,
                    sde.confidence_scores
                FROM smart_documents sd
                JOIN smart_document_extractions sde ON sde.document_id = sd.id
                JOIN loans l ON l.id = sd.loan_id
                WHERE sd.loan_id = :loan_id
                    AND l.organization_id = :org_id
                    AND sd.doc_type = 'TAX_RETURN'
                    AND sd.status NOT IN ('REJECTED', 'EXPIRED')
                    AND sde.extracted_fields IS NOT NULL
                ORDER BY sd.created_at DESC
                LIMIT 1
            """),
            {"loan_id": loan_id, "org_id": org_id},
        ).fetchone()

        if not row:
            return None

        return {
            "doc_id": row[0],
            "fields": row[1] or {},
            "confidences": row[2] or {},
        }

    def _load_irs_transcript_data(
        self, loan_id: int, tax_year: int, org_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Load IRS transcript data for comparison."""
        row = self.db.execute(
            text("""
                SELECT
                    itr.id,
                    itr.transcript_data,
                    itr.comparison_results
                FROM irs_transcript_requests itr
                WHERE itr.loan_id = :loan_id
                    AND itr.organization_id = :org_id
                    AND itr.tax_year = :tax_year
                    AND itr.status = 'received'
                    AND itr.transcript_data IS NOT NULL
                ORDER BY itr.received_at DESC NULLS LAST
                LIMIT 1
            """),
            {"loan_id": loan_id, "org_id": org_id, "tax_year": tax_year},
        ).fetchone()

        if not row:
            return None

        transcript_data = row[1] or {}
        # Extract the relevant income fields from IRS transcript format
        fields = {}
        if isinstance(transcript_data, dict):
            fields = transcript_data.get("income_fields", transcript_data)

        return {
            "transcript_id": row[0],
            "fields": fields,
        }

    # -------------------------------------------------------------------------
    # INTERNAL: Verification
    # -------------------------------------------------------------------------

    def _verify_org_access(
        self, doc_1: Dict[str, Any], doc_2: Dict[str, Any], org_id: int,
    ) -> None:
        """Verify both documents belong to the expected organization."""
        for doc, label in [(doc_1, "doc_1"), (doc_2, "doc_2")]:
            loan_id = doc.get("loan_id")
            if loan_id is None:
                continue

            row = self.db.execute(
                text("SELECT organization_id FROM loans WHERE id = :loan_id"),
                {"loan_id": loan_id},
            ).fetchone()

            if row and row[0] != org_id:
                raise TenantIsolationError(
                    message=(
                        f"Document {doc.get('id')} ({label}) belongs to org {row[0]}, "
                        f"not the requesting org {org_id}"
                    ),
                    requesting_org_id=org_id,
                    target_org_id=row[0],
                )

    # -------------------------------------------------------------------------
    # INTERNAL: Numeric comparison
    # -------------------------------------------------------------------------

    def _compare_numeric(
        self, val_1: Decimal, val_2: Decimal, tolerance_pct: Decimal,
    ) -> Tuple[bool, Decimal, Decimal]:
        """
        Compare two numeric values with tolerance.

        Returns:
            (is_within_tolerance, variance_pct, absolute_difference)
        """
        abs_diff = abs(val_2 - val_1)

        # If both are zero or difference is below absolute threshold
        if abs_diff <= ABSOLUTE_DOLLAR_TOLERANCE:
            return True, ZERO, abs_diff

        # Calculate percentage variance relative to the original (val_1)
        if val_1 == ZERO:
            # Original is zero but revised is not => infinite variance
            return False, Decimal("100.0"), abs_diff

        variance_pct = ((val_2 - val_1) / abs(val_1) * 100).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP,
        )
        is_within = abs(variance_pct) <= tolerance_pct

        return is_within, variance_pct, abs_diff

    def _describe_numeric_diff(
        self, field_name: str, val_1: Decimal, val_2: Decimal, variance_pct: Optional[Decimal],
    ) -> str:
        """Generate a human-readable description of a numeric difference."""
        direction = "increased" if val_2 > val_1 else "decreased"
        pct_str = f" ({variance_pct:+.2f}%)" if variance_pct is not None else ""
        return (
            f"'{field_name}' {direction} from "
            f"${val_1:,.2f} to ${val_2:,.2f}{pct_str}"
        )

    # -------------------------------------------------------------------------
    # INTERNAL: Text comparison
    # -------------------------------------------------------------------------

    def _compute_text_similarity(self, text_1: str, text_2: str) -> float:
        """Compute overall text similarity using SequenceMatcher."""
        if not text_1 and not text_2:
            return 1.0
        if not text_1 or not text_2:
            return 0.0
        return difflib.SequenceMatcher(None, text_1, text_2).ratio()

    def _compare_text_by_page(
        self, text_1: str, text_2: str,
    ) -> List[PageComparison]:
        """Compare text content page by page (split on form feed or page markers)."""
        # Split on form feed characters or common page break markers
        page_split_pattern = r"\f|--- ?Page \d+ ?---|\[Page \d+\]"
        pages_1 = re.split(page_split_pattern, text_1)
        pages_2 = re.split(page_split_pattern, text_2)

        # If no page breaks found, treat entire text as one page
        if len(pages_1) == 1 and len(pages_2) == 1:
            similarity = self._compute_text_similarity(text_1, text_2)
            diff_segments = self._generate_diff_segments(text_1, text_2)
            change_count = sum(1 for s in diff_segments if s.operation != "equal")
            return [PageComparison(
                page_number=1,
                similarity_score=similarity,
                text_changes=change_count,
                has_structural_changes=similarity < 0.8,
                diff_segments=diff_segments[:50],  # Cap segments for performance
            )]

        max_pages = max(len(pages_1), len(pages_2))
        comparisons = []

        for i in range(max_pages):
            p1 = pages_1[i].strip() if i < len(pages_1) else ""
            p2 = pages_2[i].strip() if i < len(pages_2) else ""

            similarity = self._compute_text_similarity(p1, p2)
            diff_segments = self._generate_diff_segments(p1, p2)
            change_count = sum(1 for s in diff_segments if s.operation != "equal")

            comparisons.append(PageComparison(
                page_number=i + 1,
                similarity_score=similarity,
                text_changes=change_count,
                has_structural_changes=similarity < 0.8,
                diff_segments=diff_segments[:30],  # Cap per page
            ))

        return comparisons

    def _generate_diff_segments(
        self, text_1: str, text_2: str,
    ) -> List[TextDiffSegment]:
        """Generate structured diff segments from two texts."""
        segments: List[TextDiffSegment] = []
        lines_1 = text_1.splitlines(keepends=True)
        lines_2 = text_2.splitlines(keepends=True)

        matcher = difflib.SequenceMatcher(None, lines_1, lines_2)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                segments.append(TextDiffSegment(
                    operation="equal",
                    text_1="".join(lines_1[i1:i2])[:500],
                    line_number_1=i1 + 1,
                    line_number_2=j1 + 1,
                ))
            elif tag == "replace":
                segments.append(TextDiffSegment(
                    operation="replace",
                    text_1="".join(lines_1[i1:i2])[:500],
                    text_2="".join(lines_2[j1:j2])[:500],
                    line_number_1=i1 + 1,
                    line_number_2=j1 + 1,
                ))
            elif tag == "insert":
                segments.append(TextDiffSegment(
                    operation="insert",
                    text_2="".join(lines_2[j1:j2])[:500],
                    line_number_2=j1 + 1,
                ))
            elif tag == "delete":
                segments.append(TextDiffSegment(
                    operation="delete",
                    text_1="".join(lines_1[i1:i2])[:500],
                    line_number_1=i1 + 1,
                ))

        return segments

    # -------------------------------------------------------------------------
    # INTERNAL: PDF structural comparison
    # -------------------------------------------------------------------------

    async def _compare_pdf_structure(
        self,
        doc_1: Dict[str, Any],
        doc_2: Dict[str, Any],
        result: ComparisonResult,
    ) -> None:
        """Compare PDF structure using forensics service if available."""
        forensics_mod = _get_pdf_forensics()
        if forensics_mod is None:
            return

        s3_getter = _get_s3_service()
        if s3_getter is None:
            return

        # Only compare PDFs
        if not (
            doc_1.get("mime_type", "").startswith("application/pdf")
            and doc_2.get("mime_type", "").startswith("application/pdf")
        ):
            return

        try:
            s3_service = s3_getter()
            key_1 = doc_1.get("storage_key")
            key_2 = doc_2.get("storage_key")

            if not key_1 or not key_2:
                return

            # Retrieve file bytes
            bytes_1 = s3_service.get_file(key_1)
            bytes_2 = s3_service.get_file(key_2)

            if not bytes_1 or not bytes_2:
                result.errors.append("Could not retrieve PDF files from storage for structural comparison")
                return

            service = forensics_mod.get_pdf_forensics_service()

            report_1 = service.generate_forensics_report(
                file_bytes=bytes_1,
                doc_type=doc_1.get("doc_type", ""),
            )
            report_2 = service.generate_forensics_report(
                file_bytes=bytes_2,
                doc_type=doc_2.get("doc_type", ""),
            )

            # Compare font profiles
            fonts_1 = set((report_1.fonts or {}).get("font_names", []))
            fonts_2 = set((report_2.fonts or {}).get("font_names", []))
            new_fonts = fonts_2 - fonts_1
            removed_fonts = fonts_1 - fonts_2

            if new_fonts:
                result.suspicious_changes.append(SuspiciousChange(
                    change_id=f"FONT-{uuid.uuid4().hex[:8]}",
                    category=ChangeCategory.FONT_INCONSISTENCY.value,
                    severity=ChangeSeverity.HIGH.value,
                    description=(
                        f"New fonts detected in revised document that were not in the original: "
                        f"{', '.join(sorted(new_fonts))}"
                    ),
                    evidence=f"Original fonts: {sorted(fonts_1)}, Revised fonts: {sorted(fonts_2)}",
                    risk_contribution=SEVERITY_WEIGHTS["HIGH"],
                    recommendation=(
                        "Font additions in a revised document may indicate sections were "
                        "edited with different software. Compare affected text regions."
                    ),
                ))

            # Compare producer/creator metadata
            producer_1 = (report_1.metadata or {}).get("producer", "")
            producer_2 = (report_2.metadata or {}).get("producer", "")
            if producer_1 and producer_2 and producer_1 != producer_2:
                result.suspicious_changes.append(SuspiciousChange(
                    change_id=f"META-{uuid.uuid4().hex[:8]}",
                    category=ChangeCategory.METADATA_ANOMALY.value,
                    severity=ChangeSeverity.MEDIUM.value,
                    description=(
                        f"PDF producer changed between versions: "
                        f"'{producer_1}' -> '{producer_2}'"
                    ),
                    evidence=f"Original producer: {producer_1}, Revised producer: {producer_2}",
                    risk_contribution=SEVERITY_WEIGHTS["MEDIUM"],
                    recommendation=(
                        "Different PDF producers may indicate the revised document was "
                        "regenerated or edited with different software."
                    ),
                ))

        except Exception as e:
            logger.warning(
                "PDF structural comparison failed",
                extra={"error": str(e), "doc_1_id": doc_1.get("id"), "doc_2_id": doc_2.get("id")},
            )
            result.errors.append(f"PDF structural comparison failed: {str(e)}")

    # -------------------------------------------------------------------------
    # INTERNAL: Suspicious change evaluation
    # -------------------------------------------------------------------------

    def _evaluate_field_suspicion(self, diff: FieldDifference) -> Optional[SuspiciousChange]:
        """Evaluate whether a field difference is suspicious enough to flag."""
        # Only flag non-trivial differences
        if diff.severity in (ChangeSeverity.INFO.value, ChangeSeverity.LOW.value):
            return None

        # Income fields with >5% increase are suspicious
        if (
            diff.category == ChangeCategory.INCOME_MODIFIED.value
            and diff.variance_pct is not None
            and diff.variance_pct > 5.0
        ):
            return SuspiciousChange(
                change_id=f"INC-{uuid.uuid4().hex[:8]}",
                category=ChangeCategory.INCOME_MODIFIED.value,
                severity=diff.severity,
                description=(
                    f"Income field '{diff.field_name}' increased by {diff.variance_pct:.1f}% "
                    f"in revised document"
                ),
                evidence=(
                    f"Original: ${diff.value_1:,.2f}, Revised: ${diff.value_2:,.2f} "
                    f"(+{diff.variance_pct:.1f}%)"
                ) if isinstance(diff.value_1, (int, float)) else str(diff.value_1),
                field_name=diff.field_name,
                original_value=diff.value_1,
                modified_value=diff.value_2,
                risk_contribution=SEVERITY_WEIGHTS.get(diff.severity, 0),
                recommendation=(
                    "Verify this income change against VOE, bank deposit history, "
                    "or IRS transcript."
                ),
            )

        # Employer changes are always suspicious
        if diff.category == ChangeCategory.EMPLOYER_MODIFIED.value:
            return SuspiciousChange(
                change_id=f"EMP-{uuid.uuid4().hex[:8]}",
                category=ChangeCategory.EMPLOYER_MODIFIED.value,
                severity=ChangeSeverity.HIGH.value,
                description=(
                    f"Employer information '{diff.field_name}' changed between document versions"
                ),
                evidence=f"Original: {diff.value_1}, Revised: {diff.value_2}",
                field_name=diff.field_name,
                original_value=diff.value_1,
                modified_value=diff.value_2,
                risk_contribution=SEVERITY_WEIGHTS["HIGH"],
                recommendation=(
                    "Employer changes between document versions are unusual. "
                    "Verify with direct employer contact or VOE."
                ),
            )

        # Date modifications
        if diff.category == ChangeCategory.DATE_MODIFIED.value:
            return SuspiciousChange(
                change_id=f"DATE-{uuid.uuid4().hex[:8]}",
                category=ChangeCategory.DATE_MODIFIED.value,
                severity=ChangeSeverity.MEDIUM.value,
                description=f"Date field '{diff.field_name}' modified between versions",
                evidence=f"Original: {diff.value_1}, Revised: {diff.value_2}",
                field_name=diff.field_name,
                original_value=diff.value_1,
                modified_value=diff.value_2,
                risk_contribution=SEVERITY_WEIGHTS["MEDIUM"],
                recommendation="Verify date change is legitimate with document issuer.",
            )

        return None

    async def _check_font_inconsistencies(
        self,
        doc_1_info: Optional[Dict[str, Any]],
        doc_2_info: Optional[Dict[str, Any]],
        suspicious: List[SuspiciousChange],
    ) -> None:
        """Check for font inconsistencies using PDF forensics if available."""
        # Font checks are handled in _compare_pdf_structure when both docs are PDFs.
        # This method handles the case where forensics data was pre-loaded on the
        # document info dict (e.g., from a previous analysis).
        if not doc_1_info or not doc_2_info:
            return

        # Check if forensics data is embedded in doc info (from prior analysis)
        forensics_1 = doc_1_info.get("forensics_report")
        forensics_2 = doc_2_info.get("forensics_report")

        if not forensics_1 or not forensics_2:
            return

        # Compare font counts
        font_count_1 = forensics_1.get("fonts", {}).get("total_fonts", 0)
        font_count_2 = forensics_2.get("fonts", {}).get("total_fonts", 0)

        if font_count_2 > font_count_1 + 2:
            suspicious.append(SuspiciousChange(
                change_id=f"FONTCNT-{uuid.uuid4().hex[:8]}",
                category=ChangeCategory.FONT_INCONSISTENCY.value,
                severity=ChangeSeverity.MEDIUM.value,
                description=(
                    f"Revised document uses significantly more fonts "
                    f"({font_count_2}) than original ({font_count_1})"
                ),
                evidence=f"Original: {font_count_1} fonts, Revised: {font_count_2} fonts",
                risk_contribution=SEVERITY_WEIGHTS["MEDIUM"],
                recommendation="Additional fonts may indicate edited sections.",
            ))

    def _check_metadata_anomalies(
        self,
        doc_1_info: Optional[Dict[str, Any]],
        doc_2_info: Optional[Dict[str, Any]],
        suspicious: List[SuspiciousChange],
    ) -> None:
        """Check for metadata anomalies between documents."""
        if not doc_1_info or not doc_2_info:
            return

        # Check page count changes
        pages_1 = doc_1_info.get("page_count")
        pages_2 = doc_2_info.get("page_count")

        if pages_1 is not None and pages_2 is not None and pages_1 != pages_2:
            suspicious.append(SuspiciousChange(
                change_id=f"PAGES-{uuid.uuid4().hex[:8]}",
                category=ChangeCategory.STRUCTURAL_CHANGE.value,
                severity=ChangeSeverity.LOW.value,
                description=(
                    f"Page count changed from {pages_1} to {pages_2} between versions"
                ),
                evidence=f"Original: {pages_1} pages, Revised: {pages_2} pages",
                risk_contribution=SEVERITY_WEIGHTS["LOW"],
                recommendation="Verify page count change is expected for this revision type.",
            ))

        # Check file size ratio (large discrepancies may indicate editing)
        size_1 = doc_1_info.get("file_size")
        size_2 = doc_2_info.get("file_size")

        if size_1 and size_2 and size_1 > 0:
            size_ratio = size_2 / size_1
            if size_ratio > 3.0 or size_ratio < 0.3:
                suspicious.append(SuspiciousChange(
                    change_id=f"SIZE-{uuid.uuid4().hex[:8]}",
                    category=ChangeCategory.STRUCTURAL_CHANGE.value,
                    severity=ChangeSeverity.LOW.value,
                    description=(
                        f"File size changed significantly: "
                        f"{size_1:,} bytes -> {size_2:,} bytes ({size_ratio:.1f}x)"
                    ),
                    evidence=f"Size ratio: {size_ratio:.2f}",
                    risk_contribution=SEVERITY_WEIGHTS["LOW"],
                    recommendation="Large file size changes may indicate document reconstruction.",
                ))

    # -------------------------------------------------------------------------
    # INTERNAL: Summary and recommendations
    # -------------------------------------------------------------------------

    def _generate_summary(self, result: ComparisonResult) -> str:
        """Generate a human-readable summary of the comparison."""
        parts = []

        if result.comparison_type == ComparisonType.CROSS_SOURCE.value:
            parts.append("Cross-source comparison (borrower vs. third-party)")
        elif result.comparison_type == ComparisonType.REVISION.value:
            parts.append("Document revision comparison")
        else:
            parts.append(f"Comparison type: {result.comparison_type}")

        if result.field_comparison:
            fc = result.field_comparison
            parts.append(
                f"{fc.total_fields_compared} fields compared: "
                f"{fc.matching_fields} match, {fc.differing_fields} differ "
                f"({fc.match_rate:.0f}% match rate)"
            )
            if fc.outside_tolerance > 0:
                parts.append(f"{fc.outside_tolerance} fields outside tolerance")

        if result.text_similarity > 0:
            parts.append(f"Text similarity: {result.text_similarity:.1%}")

        if result.suspicious_changes:
            critical = sum(
                1 for sc in result.suspicious_changes
                if sc.severity == ChangeSeverity.CRITICAL.value
            )
            high = sum(
                1 for sc in result.suspicious_changes
                if sc.severity == ChangeSeverity.HIGH.value
            )
            parts.append(
                f"{len(result.suspicious_changes)} suspicious changes "
                f"({critical} critical, {high} high)"
            )

        parts.append(f"Risk: {result.risk_level} ({result.risk_score}/100)")

        return ". ".join(parts) + "."

    def _generate_recommendations(self, result: ComparisonResult) -> List[str]:
        """Generate actionable recommendations based on comparison results."""
        recommendations: List[str] = []

        if result.risk_level == "CRITICAL":
            recommendations.append(
                "CRITICAL: Route to compliance officer for immediate review. "
                "Do not proceed with underwriting until discrepancies are resolved."
            )

        if result.risk_level in ("CRITICAL", "HIGH"):
            recommendations.append(
                "Request original documents directly from the issuing entity "
                "(employer, bank, IRS) to validate borrower-submitted copies."
            )

        # Check for specific patterns in suspicious changes
        categories = {sc.category for sc in result.suspicious_changes}

        if ChangeCategory.INCOME_MODIFIED.value in categories:
            recommendations.append(
                "Income discrepancies detected. Cross-reference with bank deposit "
                "history and/or IRS 4506-C transcript."
            )

        if ChangeCategory.EMPLOYER_MODIFIED.value in categories:
            recommendations.append(
                "Employer information was modified. Complete verbal or written VOE "
                "directly with the employer."
            )

        if ChangeCategory.FONT_INCONSISTENCY.value in categories:
            recommendations.append(
                "Font inconsistencies may indicate document editing. Review the "
                "PDF forensics report for editing traces."
            )

        if ChangeCategory.IDENTITY_MODIFIED.value in categories:
            recommendations.append(
                "Identity fields were modified. Verify borrower identity through "
                "an independent source."
            )

        if not recommendations and result.risk_level == "LOW":
            recommendations.append(
                "No significant discrepancies found. Document comparison passed."
            )

        return recommendations

    # -------------------------------------------------------------------------
    # INTERNAL: Document info helpers
    # -------------------------------------------------------------------------

    def _doc_summary(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Create a concise summary of document info for the result."""
        return {
            "id": doc.get("id"),
            "file_name": doc.get("file_name"),
            "doc_type": doc.get("doc_type"),
            "mime_type": doc.get("mime_type"),
            "file_size": doc.get("file_size"),
            "page_count": doc.get("page_count"),
            "status": doc.get("status"),
            "uploaded_at": doc.get("uploaded_at").isoformat()
            if doc.get("uploaded_at") else None,
        }

    def _build_tolerances(
        self, custom: Optional[Dict[str, float]],
    ) -> Dict[str, Decimal]:
        """Merge custom tolerances with defaults."""
        tolerances: Dict[str, Decimal] = {}
        if custom:
            for key, val in custom.items():
                try:
                    tolerances[key] = Decimal(str(val))
                except (InvalidOperation, ValueError):
                    logger.warning(
                        "Invalid custom tolerance value, skipping",
                        extra={"field": key, "value": val},
                    )
        return tolerances

    # -------------------------------------------------------------------------
    # INTERNAL: Audit trail persistence
    # -------------------------------------------------------------------------

    def _save_comparison_audit(
        self, result: ComparisonResult, org_id: Optional[int],
    ) -> None:
        """Persist comparison result to the document_comparisons table."""
        try:
            # Resolve loan_id from either document
            loan_id = result.doc_1_info.get("loan_id") if isinstance(result.doc_1_info, dict) else None

            import json
            comparison_data = json.dumps(result.to_dict(), default=str)

            self.db.execute(
                text("""
                    INSERT INTO document_comparisons (
                        comparison_id, organization_id, loan_id,
                        doc_id_1, doc_id_2, comparison_type,
                        risk_score, risk_level, status,
                        comparison_data, performed_by, performed_at
                    ) VALUES (
                        :comparison_id, :org_id, :loan_id,
                        :doc_id_1, :doc_id_2, :comparison_type,
                        :risk_score, :risk_level, :status,
                        :comparison_data, :performed_by, :performed_at
                    )
                """),
                {
                    "comparison_id": result.comparison_id,
                    "org_id": org_id,
                    "loan_id": loan_id,
                    "doc_id_1": result.doc_id_1,
                    "doc_id_2": result.doc_id_2,
                    "comparison_type": result.comparison_type,
                    "risk_score": result.risk_score,
                    "risk_level": result.risk_level,
                    "status": result.status,
                    "comparison_data": comparison_data,
                    "performed_by": result.performed_by,
                    "performed_at": result.performed_at,
                },
            )
            self.db.commit()

            logger.info(
                "Comparison audit record saved",
                extra={
                    "comparison_id": result.comparison_id,
                    "org_id": org_id,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to save comparison audit record",
                extra={
                    "comparison_id": result.comparison_id,
                    "error": str(e),
                },
            )
            # Do not re-raise: audit persistence failure should not block
            # the comparison result from being returned.

    def _load_comparison_audit(
        self, comparison_id: str, org_id: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        """Load a comparison audit record."""
        params: Dict[str, Any] = {"comparison_id": comparison_id}
        org_filter = ""
        if org_id is not None:
            org_filter = "AND dc.organization_id = :org_id"
            params["org_id"] = org_id

        detail_query = (
            "SELECT"
            " dc.comparison_id, dc.doc_id_1, dc.doc_id_2,"
            " dc.comparison_type, dc.risk_score, dc.risk_level,"
            " dc.status, dc.comparison_data, dc.performed_at,"
            " dc.performed_by"
            " FROM document_comparisons dc"
            " WHERE dc.comparison_id = :comparison_id " + org_filter
        )
        row = self.db.execute(text(detail_query), params).fetchone()

        if not row:
            return None

        columns = [
            "comparison_id", "doc_id_1", "doc_id_2",
            "comparison_type", "risk_score", "risk_level",
            "status", "comparison_data", "performed_at",
            "performed_by",
        ]
        result = dict(zip(columns, row))

        # Parse JSON comparison_data
        import json
        if result.get("comparison_data") and isinstance(result["comparison_data"], str):
            try:
                result["comparison_data"] = json.loads(result["comparison_data"])
            except (json.JSONDecodeError, TypeError):
                pass

        return result


# =============================================================================
# FACTORY
# =============================================================================

def get_document_comparison_service(db: Session) -> DocumentComparisonService:
    """Factory function for DocumentComparisonService.

    Usage:
        service = get_document_comparison_service(db)
        result = await service.compare_documents(100, 101, org_id=5)
    """
    return DocumentComparisonService(db)
