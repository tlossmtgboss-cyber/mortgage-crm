"""
Advanced OCR Enhancement Service for Smart Docs V2

Multi-engine OCR pipeline with pre-processing, post-processing, structured
data extraction, table parsing, handwriting detection, multi-language support,
and result caching. Designed for high-volume mortgage document processing.

Architecture:
    Wraps and extends DocumentOCRService with:
    - Cloud OCR primary / Tesseract fallback engine orchestration
    - Image pre-processing pipeline (deskew, denoise, contrast, binarization)
    - Post-processing: spell correction, field validation, confidence scoring
    - Table extraction tuned for financial documents
    - Handwriting detection and specialized routing
    - Multi-language support (English + Spanish)
    - Hash-based result caching via DocumentCacheService
    - Structured extraction schemas for W-2, paystub, bank statement, tax return
    - Confidence thresholds: auto-accept > 0.95, review 0.7-0.95, reject < 0.7
    - Batch OCR for multi-page documents with page-level results

Integration points:
    - DocumentOCRService     (underlying OCR engines and pre-processing)
    - DocumentCacheService   (hash-based result caching, 30-day TTL)
    - DocumentDataExtractor  (downstream LLM-based structured extraction)
    - ai_resilience          (retry/circuit-breaker for cloud OCR calls)

Usage:
    from services.smart_docs.ocr_enhancement_service import (
        OCREnhancementService,
        get_ocr_enhancement_service,
    )

    service = OCREnhancementService(org_id=42)
    result = await service.process_document(
        file_bytes=raw_bytes,
        mime_type="application/pdf",
        document_type="w2",
    )

    # Batch processing
    batch_result = await service.process_batch(
        pages=[page1_bytes, page2_bytes],
        mime_type="image/png",
        document_type="bank_statement",
    )
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import statistics
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency imports (graceful degradation)
# ---------------------------------------------------------------------------
try:
    from PIL import Image, ImageFilter, ImageEnhance, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    from pdf2image import convert_from_bytes
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from middleware.upload_limits import (
    MAX_VISION_API_SIZE,
    MAX_IMAGE_DIMENSIONS,
    MAX_OCR_OUTPUT_CHARS,
    MAX_PDF_PAGES,
)


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class ConfidenceLevel(str, Enum):
    """OCR confidence classification tier."""
    AUTO_ACCEPT = "auto_accept"       # > 0.95 -- no human review needed
    MANUAL_REVIEW = "manual_review"   # 0.70 - 0.95 -- flag for LO/processor
    REJECT = "reject"                 # < 0.70 -- re-scan or manual entry

    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        if score > 0.95:
            return cls.AUTO_ACCEPT
        if score >= 0.70:
            return cls.MANUAL_REVIEW
        return cls.REJECT


class DocumentLanguage(str, Enum):
    """Supported document languages."""
    ENGLISH = "eng"
    SPANISH = "spa"
    ENGLISH_SPANISH = "eng+spa"


class MortgageDocType(str, Enum):
    """Mortgage document types with structured extraction support."""
    W2 = "w2"
    PAYSTUB = "paystub"
    BANK_STATEMENT = "bank_statement"
    TAX_RETURN = "tax_return"
    DRIVERS_LICENSE = "drivers_license"
    PURCHASE_CONTRACT = "purchase_contract"
    PROFIT_LOSS = "profit_loss"
    GENERIC = "generic"


# Cache type for OCR enhancement results (extends standard OCR cache)
CACHE_TYPE_OCR_ENHANCED = "ocr_enhanced"
DEFAULT_ENHANCED_OCR_TTL_HOURS = 720  # 30 days

# Confidence thresholds
CONFIDENCE_AUTO_ACCEPT = 0.95
CONFIDENCE_REVIEW_MIN = 0.70
CONFIDENCE_REJECT = 0.70

# Pre-processing defaults
DEFAULT_TARGET_DPI = 300
MIN_OCR_DPI = 200
MAX_UPSCALE_FACTOR = 4.0
BINARIZATION_THRESHOLD = 128

# Financial table detection heuristics
MIN_TABLE_ROWS = 3
MIN_TABLE_COLUMNS = 2
TABLE_COLUMN_CONSISTENCY_THRESHOLD = 0.6

# Spell correction: mortgage-specific terminology that OCR commonly mangles
MORTGAGE_SPELL_CORRECTIONS: Dict[str, str] = {
    "ernployer": "employer",
    "ernployee": "employee",
    "empioyee": "employee",
    "ernployment": "employment",
    "yearto-date": "year-to-date",
    "year to dale": "year-to-date",
    "year lo date": "year-to-date",
    "grosspay": "gross pay",
    "netpay": "net pay",
    "wilhholding": "withholding",
    "wilhholdings": "withholdings",
    "withhoiding": "withholding",
    "federaltax": "federal tax",
    "statetax": "state tax",
    "socialsecurity": "social security",
    "socia1 security": "social security",
    "medieare": "medicare",
    "medlcare": "medicare",
    "retlrement": "retirement",
    "relirement": "retirement",
    "401(k)": "401k",
    "4o1k": "401k",
    "4O1k": "401k",
    "agjusted": "adjusted",
    "flling": "filing",
    "fiIing": "filing",
    "lncome": "income",
    "lnterest": "interest",
    "inlerest": "interest",
    "rnortgage": "mortgage",
    "morigage": "mortgage",
    "principa1": "principal",
    "princial": "principal",
    "ba1ance": "balance",
    "baiance": "balance",
    "depos1t": "deposit",
    "deposlt": "deposit",
    "withdrawa1": "withdrawal",
    "wlthdrawal": "withdrawal",
    "stalement": "statement",
    "stalernent": "statement",
    "accounl": "account",
    "acccunt": "account",
    "accouni": "account",
    "compensa1ion": "compensation",
    "compensalion": "compensation",
    "wa9es": "wages",
    "llps": "tips",
    "reim6ursement": "reimbursement",
    "reimbursernenl": "reimbursement",
    "identifica1ion": "identification",
    "identlfication": "identification",
    "numero de seguro social": "social security number",
    "ingreso bruto": "gross income",
    "ingreso neto": "net income",
    "salario": "salary",
    "empleador": "employer",
    "empleado": "employee",
    "fecha de pago": "pay date",
    "periodo de pago": "pay period",
    "impuesto federal": "federal tax",
    "estado de cuenta": "bank statement",
    "declaracion de impuestos": "tax return",
}

# Spanish field label mappings for bilingual documents
SPANISH_FIELD_LABELS: Dict[str, str] = {
    "nombre del empleador": "employer_name",
    "nombre del empleado": "employee_name",
    "nombre completo": "full_name",
    "fecha de nacimiento": "date_of_birth",
    "direccion": "address",
    "numero de cuenta": "account_number",
    "saldo inicial": "beginning_balance",
    "saldo final": "ending_balance",
    "depositos totales": "total_deposits",
    "retiros totales": "total_withdrawals",
    "ingreso bruto": "gross_income",
    "ingreso neto": "net_income",
    "salario bruto": "gross_pay",
    "salario neto": "net_pay",
    "impuesto federal retenido": "federal_tax_withheld",
    "seguro social": "social_security",
    "numero de seguro social": "ssn",
    "periodo": "pay_period",
    "frecuencia de pago": "pay_frequency",
    "salarios propinas compensacion": "wages_tips_compensation",
    "ano fiscal": "tax_year",
    "estado civil": "filing_status",
    "ingreso bruto ajustado": "adjusted_gross_income",
}


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class PreprocessingMetrics:
    """Metrics from image pre-processing pipeline."""
    steps_applied: List[str] = field(default_factory=list)
    original_size: Tuple[int, int] = (0, 0)
    processed_size: Tuple[int, int] = (0, 0)
    deskew_angle: float = 0.0
    estimated_dpi: int = 0
    was_binarized: bool = False
    was_upscaled: bool = False
    was_denoised: bool = False
    processing_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps_applied": self.steps_applied,
            "original_size": list(self.original_size),
            "processed_size": list(self.processed_size),
            "deskew_angle": round(self.deskew_angle, 2),
            "estimated_dpi": self.estimated_dpi,
            "was_binarized": self.was_binarized,
            "was_upscaled": self.was_upscaled,
            "was_denoised": self.was_denoised,
            "processing_ms": self.processing_ms,
        }


@dataclass
class TableCell:
    """A single cell in an extracted table."""
    text: str
    row: int
    col: int
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "row": self.row,
            "col": self.col,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class ExtractedTable:
    """A table extracted from a financial document."""
    table_index: int
    page_number: int
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    row_count: int = 0
    col_count: int = 0
    confidence: float = 0.0
    table_type: str = "unknown"  # transaction, summary, deduction, earnings

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_index": self.table_index,
            "page_number": self.page_number,
            "headers": self.headers,
            "rows": self.rows,
            "row_count": self.row_count,
            "col_count": self.col_count,
            "confidence": round(self.confidence, 3),
            "table_type": self.table_type,
        }


@dataclass
class HandwritingDetection:
    """Result of handwriting detection analysis."""
    has_handwriting: bool = False
    confidence: float = 0.0
    regions: List[Dict[str, Any]] = field(default_factory=list)
    recommended_engine: str = "claude_vision"
    handwriting_percentage: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_handwriting": self.has_handwriting,
            "confidence": round(self.confidence, 3),
            "region_count": len(self.regions),
            "recommended_engine": self.recommended_engine,
            "handwriting_percentage": round(self.handwriting_percentage, 1),
        }


@dataclass
class StructuredField:
    """A single extracted and validated field from a mortgage document."""
    name: str
    value: Any
    raw_value: str
    confidence: float
    source_text: str = ""
    page_number: int = 0
    validated: bool = False
    validation_notes: str = ""
    needs_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "raw_value": self.raw_value,
            "confidence": round(self.confidence, 3),
            "page_number": self.page_number,
            "validated": self.validated,
            "validation_notes": self.validation_notes,
            "needs_review": self.needs_review,
        }


@dataclass
class PageEnhancedResult:
    """Enhanced OCR result for a single page."""
    page_number: int
    text: str
    corrected_text: str
    confidence: float
    word_count: int = 0
    corrections_applied: int = 0
    tables: List[ExtractedTable] = field(default_factory=list)
    handwriting: HandwritingDetection = field(default_factory=HandwritingDetection)
    preprocessing: PreprocessingMetrics = field(default_factory=PreprocessingMetrics)
    engine_used: str = ""
    language_detected: str = "eng"
    processing_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "text_length": len(self.text),
            "corrected_text_length": len(self.corrected_text),
            "confidence": round(self.confidence, 3),
            "word_count": self.word_count,
            "corrections_applied": self.corrections_applied,
            "tables": [t.to_dict() for t in self.tables],
            "handwriting": self.handwriting.to_dict(),
            "preprocessing": self.preprocessing.to_dict(),
            "engine_used": self.engine_used,
            "language_detected": self.language_detected,
            "processing_ms": self.processing_ms,
        }


@dataclass
class StructuredExtractionResult:
    """Result of structured data extraction from a mortgage document."""
    success: bool
    document_type: str
    fields: Dict[str, StructuredField] = field(default_factory=dict)
    overall_confidence: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.REJECT
    missing_required: List[str] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)
    tables: List[ExtractedTable] = field(default_factory=list)
    needs_review: bool = False
    review_reasons: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "document_type": self.document_type,
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "overall_confidence": round(self.overall_confidence, 3),
            "confidence_level": self.confidence_level.value,
            "missing_required": self.missing_required,
            "validation_errors": self.validation_errors,
            "tables": [t.to_dict() for t in self.tables],
            "needs_review": self.needs_review,
            "review_reasons": self.review_reasons,
            "error": self.error,
        }


@dataclass
class EnhancedOCRResult:
    """Complete enhanced OCR result across all pages."""
    success: bool
    document_id: str
    full_text: str
    corrected_text: str
    pages: List[PageEnhancedResult] = field(default_factory=list)
    page_count: int = 0
    overall_confidence: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.REJECT
    structured_data: Optional[StructuredExtractionResult] = None
    tables: List[ExtractedTable] = field(default_factory=list)
    handwriting_detected: bool = False
    language_detected: str = "eng"
    needs_review: bool = False
    review_reasons: List[str] = field(default_factory=list)
    total_corrections: int = 0
    engine_used: str = ""
    total_processing_ms: int = 0
    cached: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "document_id": self.document_id,
            "full_text_length": len(self.full_text),
            "corrected_text_length": len(self.corrected_text),
            "page_count": self.page_count,
            "overall_confidence": round(self.overall_confidence, 3),
            "confidence_level": self.confidence_level.value,
            "structured_data": self.structured_data.to_dict() if self.structured_data else None,
            "tables": [t.to_dict() for t in self.tables],
            "handwriting_detected": self.handwriting_detected,
            "language_detected": self.language_detected,
            "needs_review": self.needs_review,
            "review_reasons": self.review_reasons,
            "total_corrections": self.total_corrections,
            "engine_used": self.engine_used,
            "total_processing_ms": self.total_processing_ms,
            "cached": self.cached,
            "error": self.error,
        }


@dataclass
class BatchOCRResult:
    """Result of batch OCR processing across multiple pages/documents."""
    success: bool
    batch_id: str
    page_results: List[PageEnhancedResult] = field(default_factory=list)
    combined_text: str = ""
    combined_corrected_text: str = ""
    overall_confidence: float = 0.0
    confidence_level: ConfidenceLevel = ConfidenceLevel.REJECT
    structured_data: Optional[StructuredExtractionResult] = None
    total_pages: int = 0
    pages_succeeded: int = 0
    pages_failed: int = 0
    total_processing_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "batch_id": self.batch_id,
            "page_results": [p.to_dict() for p in self.page_results],
            "combined_text_length": len(self.combined_text),
            "overall_confidence": round(self.overall_confidence, 3),
            "confidence_level": self.confidence_level.value,
            "structured_data": self.structured_data.to_dict() if self.structured_data else None,
            "total_pages": self.total_pages,
            "pages_succeeded": self.pages_succeeded,
            "pages_failed": self.pages_failed,
            "total_processing_ms": self.total_processing_ms,
            "error": self.error,
        }


# ============================================================================
# STRUCTURED EXTRACTION SCHEMAS
# ============================================================================

# Required and optional fields per document type, with validation rules.
# These extend the patterns in document_ocr_service.py with cross-field
# validation and mortgage-specific business rules.

STRUCTURED_SCHEMAS: Dict[str, Dict[str, Any]] = {
    MortgageDocType.W2.value: {
        "description": "W-2 Wage and Tax Statement",
        "required_fields": [
            "employer_name", "employee_name", "wages_tips_compensation",
            "federal_tax_withheld", "tax_year",
        ],
        "optional_fields": [
            "employer_ein", "employee_ssn_last4", "social_security_wages",
            "social_security_tax", "medicare_wages", "medicare_tax",
            "state", "state_wages", "state_tax_withheld",
            "employer_address",
        ],
        "validations": {
            "wages_tips_compensation": {"type": "currency", "min": 0, "max": 10_000_000},
            "federal_tax_withheld": {"type": "currency", "min": 0, "max": 5_000_000},
            "tax_year": {"type": "integer", "min": 2018, "max": 2030},
            "employer_ein": {"type": "regex", "pattern": r"^\d{2}-?\d{7}$"},
        },
        "cross_validations": [
            {
                "rule": "federal_tax_lte_wages",
                "fields": ["federal_tax_withheld", "wages_tips_compensation"],
                "check": "lte",
                "message": "Federal tax withheld exceeds wages",
            },
            {
                "rule": "ss_wages_lte_limit",
                "fields": ["social_security_wages"],
                "check": "max_value",
                "max": 168_600,  # 2024 SS wage base
                "message": "Social security wages exceed annual cap",
            },
        ],
    },
    MortgageDocType.PAYSTUB.value: {
        "description": "Pay Stub / Earnings Statement",
        "required_fields": [
            "employer_name", "employee_name", "gross_pay", "net_pay",
            "pay_date",
        ],
        "optional_fields": [
            "pay_period_start", "pay_period_end", "pay_frequency",
            "hourly_rate", "hours_worked", "ytd_gross", "ytd_net",
            "federal_tax", "state_tax", "social_security", "medicare",
            "retirement_401k", "health_insurance", "overtime_earnings",
            "bonus", "commission",
        ],
        "validations": {
            "gross_pay": {"type": "currency", "min": 0, "max": 500_000},
            "net_pay": {"type": "currency", "min": 0, "max": 500_000},
            "hourly_rate": {"type": "currency", "min": 0, "max": 1_000},
            "hours_worked": {"type": "number", "min": 0, "max": 200},
        },
        "cross_validations": [
            {
                "rule": "net_lte_gross",
                "fields": ["net_pay", "gross_pay"],
                "check": "lte",
                "message": "Net pay exceeds gross pay",
            },
            {
                "rule": "ytd_gte_current",
                "fields": ["ytd_gross", "gross_pay"],
                "check": "gte",
                "message": "YTD gross is less than current period gross",
            },
        ],
    },
    MortgageDocType.BANK_STATEMENT.value: {
        "description": "Bank Account Statement",
        "required_fields": [
            "institution_name", "account_number_last4",
            "beginning_balance", "ending_balance",
        ],
        "optional_fields": [
            "account_holder_name", "account_type",
            "statement_start", "statement_end",
            "total_deposits", "total_withdrawals",
            "average_balance",
        ],
        "validations": {
            "beginning_balance": {"type": "currency", "min": -100_000, "max": 100_000_000},
            "ending_balance": {"type": "currency", "min": -100_000, "max": 100_000_000},
            "total_deposits": {"type": "currency", "min": 0, "max": 100_000_000},
            "total_withdrawals": {"type": "currency", "min": 0, "max": 100_000_000},
            "account_number_last4": {"type": "regex", "pattern": r"^\d{4}$"},
        },
        "cross_validations": [
            {
                "rule": "balance_reconciliation",
                "fields": [
                    "beginning_balance", "total_deposits",
                    "total_withdrawals", "ending_balance",
                ],
                "check": "balance_equation",
                "message": "Beginning balance + deposits - withdrawals != ending balance",
                "tolerance": 1.00,
            },
        ],
    },
    MortgageDocType.TAX_RETURN.value: {
        "description": "Personal Tax Return (Form 1040)",
        "required_fields": [
            "taxpayer_name", "tax_year", "adjusted_gross_income",
            "filing_status",
        ],
        "optional_fields": [
            "spouse_name", "total_income", "taxable_income",
            "total_tax", "refund_amount", "amount_owed",
            "schedule_c_income", "schedule_e_income",
        ],
        "validations": {
            "adjusted_gross_income": {"type": "currency", "min": -1_000_000, "max": 100_000_000},
            "tax_year": {"type": "integer", "min": 2018, "max": 2030},
            "filing_status": {
                "type": "enum",
                "values": [
                    "single", "married_filing_jointly",
                    "married_filing_separately",
                    "head_of_household", "qualifying_widow",
                    "qualifying_surviving_spouse",
                ],
            },
        },
        "cross_validations": [
            {
                "rule": "agi_lte_total_income",
                "fields": ["adjusted_gross_income", "total_income"],
                "check": "lte",
                "message": "AGI exceeds total income",
            },
            {
                "rule": "taxable_lte_agi",
                "fields": ["taxable_income", "adjusted_gross_income"],
                "check": "lte",
                "message": "Taxable income exceeds AGI",
            },
        ],
    },
}


# ============================================================================
# SPELL CORRECTION ENGINE
# ============================================================================

class SpellCorrector:
    """Mortgage-domain spell correction for OCR output.

    Uses a dictionary of common OCR misreads specific to mortgage documents.
    Does NOT apply general-purpose spell checking which would mangle proper
    nouns, addresses, and financial terms.
    """

    def __init__(
        self,
        corrections: Optional[Dict[str, str]] = None,
        spanish_labels: Optional[Dict[str, str]] = None,
    ):
        self._corrections = corrections or MORTGAGE_SPELL_CORRECTIONS
        self._spanish_labels = spanish_labels or SPANISH_FIELD_LABELS
        # Pre-compile patterns sorted by length (longest first) to avoid
        # partial matches corrupting longer terms
        sorted_keys = sorted(self._corrections.keys(), key=len, reverse=True)
        self._compiled = [
            (re.compile(re.escape(k), re.IGNORECASE), v)
            for k, v in ((k, self._corrections[k]) for k in sorted_keys)
        ]

    def correct(self, text: str) -> Tuple[str, int]:
        """Apply spell corrections to OCR text.

        Args:
            text: Raw OCR text.

        Returns:
            Tuple of (corrected_text, correction_count).
        """
        if not text:
            return text, 0

        corrected = text
        total_corrections = 0

        for pattern, replacement in self._compiled:
            new_text, count = pattern.subn(replacement, corrected)
            if count > 0:
                total_corrections += count
                corrected = new_text

        return corrected, total_corrections

    def detect_spanish(self, text: str) -> Tuple[bool, float]:
        """Detect if text contains Spanish content.

        Checks for common Spanish mortgage document terms. Returns
        (is_spanish, confidence) where confidence is based on the
        ratio of Spanish terms found.

        Args:
            text: OCR text to analyze.

        Returns:
            Tuple of (has_spanish, confidence_score).
        """
        if not text:
            return False, 0.0

        lower_text = text.lower()
        spanish_indicators = [
            "empleador", "empleado", "salario", "ingreso",
            "fecha de pago", "periodo de pago", "numero de cuenta",
            "saldo", "deposito", "retiro", "declaracion",
            "impuesto", "seguro social", "direccion",
            "nombre completo", "estado de cuenta", "ano fiscal",
        ]

        found = sum(1 for term in spanish_indicators if term in lower_text)
        total = len(spanish_indicators)
        ratio = found / total if total > 0 else 0.0

        has_spanish = found >= 2
        confidence = min(ratio * 3.0, 1.0)  # Scale up since finding 2+ is significant

        return has_spanish, confidence

    def map_spanish_labels(self, text: str) -> Dict[str, str]:
        """Find Spanish field labels in text and map to English field names.

        Args:
            text: OCR text that may contain Spanish labels.

        Returns:
            Dict mapping found Spanish labels to their English field equivalents.
        """
        if not text:
            return {}

        lower_text = text.lower()
        mapped = {}

        for spanish_label, english_field in self._spanish_labels.items():
            if spanish_label in lower_text:
                mapped[spanish_label] = english_field

        return mapped


# ============================================================================
# TABLE EXTRACTOR FOR FINANCIAL DOCUMENTS
# ============================================================================

class FinancialTableExtractor:
    """Extracts and classifies tables from financial documents.

    Tuned for mortgage documents: bank statement transaction tables,
    paystub earnings/deductions tables, tax return schedule tables.
    """

    # Table type detection keywords
    _TABLE_TYPE_KEYWORDS: Dict[str, List[str]] = {
        "transaction": [
            "date", "description", "amount", "debit", "credit",
            "withdrawal", "deposit", "check", "balance",
        ],
        "earnings": [
            "hours", "rate", "earnings", "current", "ytd",
            "regular", "overtime", "gross", "description",
        ],
        "deduction": [
            "deduction", "federal", "state", "fica", "medicare",
            "insurance", "401k", "retirement", "current", "ytd",
        ],
        "summary": [
            "beginning", "ending", "balance", "total", "deposits",
            "withdrawals", "average", "interest",
        ],
        "tax_schedule": [
            "line", "amount", "income", "expense", "depreciation",
            "deduction", "description", "adjustment",
        ],
    }

    def extract_tables_from_text(
        self,
        text: str,
        page_number: int = 1,
    ) -> List[ExtractedTable]:
        """Extract table structures from OCR text using delimiter analysis.

        Detects pipe-delimited tables (from Claude Vision) and
        whitespace-aligned columnar data.

        Args:
            text: OCR text that may contain tables.
            page_number: Page number for attribution.

        Returns:
            List of ExtractedTable objects.
        """
        if not text:
            return []

        tables: List[ExtractedTable] = []

        # Strategy 1: Pipe-delimited tables (from Claude Vision output)
        pipe_tables = self._extract_pipe_tables(text, page_number)
        tables.extend(pipe_tables)

        # Strategy 2: Whitespace-aligned columnar data
        if not pipe_tables:
            columnar_tables = self._extract_columnar_tables(text, page_number)
            tables.extend(columnar_tables)

        # Classify each table
        for table in tables:
            table.table_type = self._classify_table(table)

        return tables

    def extract_tables_from_pdfplumber(
        self,
        pdf_bytes: bytes,
        max_pages: int = 50,
    ) -> List[ExtractedTable]:
        """Extract tables from PDF using pdfplumber's table detection.

        Provides higher accuracy than text-based extraction for PDFs
        with native text layers.

        Args:
            pdf_bytes: Raw PDF content.
            max_pages: Maximum pages to process.

        Returns:
            List of ExtractedTable objects.
        """
        if not HAS_PDFPLUMBER:
            return []

        tables: List[ExtractedTable] = []
        table_idx = 0

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages[:max_pages], 1):
                    try:
                        raw_tables = page.extract_tables()
                        if not raw_tables:
                            continue

                        for raw_table in raw_tables:
                            if not raw_table or len(raw_table) < MIN_TABLE_ROWS:
                                continue

                            # Clean cells
                            cleaned_rows: List[List[str]] = []
                            for row in raw_table:
                                cleaned_row = [
                                    str(cell).strip() if cell else ""
                                    for cell in row
                                ]
                                cleaned_rows.append(cleaned_row)

                            # First row as headers if it looks like a header
                            headers: List[str] = []
                            data_rows = cleaned_rows
                            if cleaned_rows and self._looks_like_header(cleaned_rows[0]):
                                headers = cleaned_rows[0]
                                data_rows = cleaned_rows[1:]

                            if not data_rows:
                                continue

                            col_count = max(len(row) for row in data_rows) if data_rows else 0

                            table = ExtractedTable(
                                table_index=table_idx,
                                page_number=page_num,
                                headers=headers,
                                rows=data_rows,
                                row_count=len(data_rows),
                                col_count=col_count,
                                confidence=0.90,  # pdfplumber tables are high confidence
                            )
                            table.table_type = self._classify_table(table)
                            tables.append(table)
                            table_idx += 1

                    except Exception as e:
                        logger.debug(
                            "Table extraction failed on page %d: %s", page_num, e
                        )

        except Exception as e:
            logger.warning("PDF table extraction failed: %s", e)

        return tables

    def _extract_pipe_tables(
        self, text: str, page_number: int,
    ) -> List[ExtractedTable]:
        """Extract pipe-delimited tables from text."""
        tables: List[ExtractedTable] = []
        lines = text.split("\n")
        current_table_lines: List[str] = []
        table_idx = 0

        for line in lines:
            stripped = line.strip()
            if "|" in stripped and stripped.count("|") >= 1:
                current_table_lines.append(stripped)
            else:
                if len(current_table_lines) >= MIN_TABLE_ROWS:
                    table = self._parse_pipe_table(
                        current_table_lines, table_idx, page_number,
                    )
                    if table is not None:
                        tables.append(table)
                        table_idx += 1
                current_table_lines = []

        # Handle table at end of text
        if len(current_table_lines) >= MIN_TABLE_ROWS:
            table = self._parse_pipe_table(
                current_table_lines, table_idx, page_number,
            )
            if table is not None:
                tables.append(table)

        return tables

    def _parse_pipe_table(
        self,
        lines: List[str],
        table_index: int,
        page_number: int,
    ) -> Optional[ExtractedTable]:
        """Parse pipe-delimited lines into an ExtractedTable."""
        rows: List[List[str]] = []
        for line in lines:
            # Skip separator lines (e.g., ---|---|---)
            if re.match(r"^[\s|+\-=]+$", line):
                continue
            cells = [cell.strip() for cell in line.split("|")]
            # Remove empty leading/trailing cells from pipes at start/end
            if cells and not cells[0]:
                cells = cells[1:]
            if cells and not cells[-1]:
                cells = cells[:-1]
            if cells:
                rows.append(cells)

        if len(rows) < MIN_TABLE_ROWS:
            return None

        # Verify column consistency
        col_counts = [len(row) for row in rows]
        if not col_counts:
            return None
        median_cols = int(statistics.median(col_counts))
        if median_cols < MIN_TABLE_COLUMNS:
            return None
        consistent = sum(1 for c in col_counts if abs(c - median_cols) <= 1)
        if consistent / len(col_counts) < TABLE_COLUMN_CONSISTENCY_THRESHOLD:
            return None

        headers: List[str] = []
        data_rows = rows
        if rows and self._looks_like_header(rows[0]):
            headers = rows[0]
            data_rows = rows[1:]

        return ExtractedTable(
            table_index=table_index,
            page_number=page_number,
            headers=headers,
            rows=data_rows,
            row_count=len(data_rows),
            col_count=median_cols,
            confidence=0.80,
        )

    def _extract_columnar_tables(
        self, text: str, page_number: int,
    ) -> List[ExtractedTable]:
        """Extract whitespace-aligned columnar data.

        Uses column position analysis to detect aligned data that
        lacks explicit delimiters.
        """
        if not HAS_NUMPY:
            return []

        lines = text.split("\n")
        if len(lines) < MIN_TABLE_ROWS:
            return []

        tables: List[ExtractedTable] = []
        table_idx = 0

        # Find runs of lines with consistent spacing patterns
        current_run: List[str] = []
        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                if len(current_run) >= MIN_TABLE_ROWS:
                    table = self._analyze_column_alignment(
                        current_run, table_idx, page_number,
                    )
                    if table is not None:
                        tables.append(table)
                        table_idx += 1
                current_run = []
                continue

            # Lines with multiple whitespace gaps likely contain columnar data
            gap_count = len(re.findall(r"\s{2,}", stripped))
            if gap_count >= 1:
                current_run.append(stripped)
            else:
                if len(current_run) >= MIN_TABLE_ROWS:
                    table = self._analyze_column_alignment(
                        current_run, table_idx, page_number,
                    )
                    if table is not None:
                        tables.append(table)
                        table_idx += 1
                current_run = []

        # Handle trailing run
        if len(current_run) >= MIN_TABLE_ROWS:
            table = self._analyze_column_alignment(
                current_run, table_idx, page_number,
            )
            if table is not None:
                tables.append(table)

        return tables

    def _analyze_column_alignment(
        self,
        lines: List[str],
        table_index: int,
        page_number: int,
    ) -> Optional[ExtractedTable]:
        """Analyze whitespace positions to split lines into columns."""
        if not lines:
            return None

        # Find common whitespace positions across all lines
        max_len = max(len(line) for line in lines)
        if max_len < 10:
            return None

        # Build a "whitespace frequency" array
        ws_freq = np.zeros(max_len, dtype=int)
        for line in lines:
            padded = line.ljust(max_len)
            for i, ch in enumerate(padded):
                if ch == " ":
                    ws_freq[i] += 1

        # Column boundaries are positions where most lines have whitespace
        threshold = len(lines) * 0.6
        boundaries: List[int] = []
        in_gap = False
        gap_start = 0

        for i in range(max_len):
            if ws_freq[i] >= threshold:
                if not in_gap:
                    gap_start = i
                    in_gap = True
            else:
                if in_gap:
                    # Use the middle of the gap as the boundary
                    boundaries.append((gap_start + i) // 2)
                    in_gap = False

        if len(boundaries) < 1:
            return None

        # Split each line at the boundaries
        all_boundaries = [0] + boundaries + [max_len]
        rows: List[List[str]] = []

        for line in lines:
            padded = line.ljust(max_len)
            cells = []
            for j in range(len(all_boundaries) - 1):
                start = all_boundaries[j]
                end = all_boundaries[j + 1]
                cell = padded[start:end].strip()
                cells.append(cell)
            rows.append(cells)

        col_count = len(all_boundaries) - 1
        if col_count < MIN_TABLE_COLUMNS:
            return None

        headers: List[str] = []
        data_rows = rows
        if rows and self._looks_like_header(rows[0]):
            headers = rows[0]
            data_rows = rows[1:]

        if len(data_rows) < MIN_TABLE_ROWS - 1:
            return None

        return ExtractedTable(
            table_index=table_index,
            page_number=page_number,
            headers=headers,
            rows=data_rows,
            row_count=len(data_rows),
            col_count=col_count,
            confidence=0.65,  # Columnar detection is less certain
        )

    def _looks_like_header(self, row: List[str]) -> bool:
        """Heuristic: does this row look like a table header?"""
        if not row:
            return False

        non_empty = [cell for cell in row if cell.strip()]
        if not non_empty:
            return False

        # Headers tend to be text (not numbers), short, and non-currency
        numeric_count = 0
        for cell in non_empty:
            cleaned = cell.replace(",", "").replace("$", "").replace(".", "").strip()
            if cleaned.isdigit():
                numeric_count += 1

        # If most cells are non-numeric, it looks like a header
        return numeric_count / len(non_empty) < 0.5 if non_empty else False

    def _classify_table(self, table: ExtractedTable) -> str:
        """Classify a table's type based on its content."""
        # Combine headers and first few data rows for keyword matching
        sample_text = " ".join(table.headers).lower()
        for row in table.rows[:3]:
            sample_text += " " + " ".join(row).lower()

        best_type = "unknown"
        best_score = 0

        for table_type, keywords in self._TABLE_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in sample_text)
            if score > best_score:
                best_score = score
                best_type = table_type

        return best_type if best_score >= 2 else "unknown"


# ============================================================================
# ADVANCED IMAGE PRE-PROCESSOR
# ============================================================================

class AdvancedImagePreprocessor:
    """Extended pre-processing pipeline for OCR quality improvement.

    Builds on the base ImagePreprocessor in document_ocr_service.py with
    additional stages: adaptive binarization, border removal, and
    multi-pass contrast optimization.
    """

    @staticmethod
    def preprocess(
        image_bytes: bytes,
        target_dpi: int = DEFAULT_TARGET_DPI,
        deskew: bool = True,
        denoise: bool = True,
        enhance_contrast: bool = True,
        binarize: bool = False,
        remove_borders: bool = True,
    ) -> Tuple[bytes, PreprocessingMetrics]:
        """Run the full advanced pre-processing pipeline.

        Args:
            image_bytes: Raw image bytes.
            target_dpi: Target DPI for upscaling.
            deskew: Correct document skew.
            denoise: Apply noise reduction.
            enhance_contrast: Apply contrast enhancement.
            binarize: Convert to binary (black/white).
            remove_borders: Remove dark borders from scans.

        Returns:
            Tuple of (processed_bytes, preprocessing_metrics).
        """
        if not HAS_PIL:
            return image_bytes, PreprocessingMetrics(
                steps_applied=["skipped_no_pil"],
            )

        start = time.monotonic()
        metrics = PreprocessingMetrics()

        try:
            image = Image.open(io.BytesIO(image_bytes))
            metrics.original_size = image.size

            # Estimate DPI
            dpi_info = image.info.get("dpi", (0, 0))
            current_dpi = max(dpi_info) if isinstance(dpi_info, (tuple, list)) else 0
            if current_dpi == 0:
                current_dpi = int(image.size[0] / 8.5) if image.size[0] > 0 else 72
            metrics.estimated_dpi = current_dpi

            # Step 1: Convert to grayscale
            if image.mode not in ("L", "1"):
                image = image.convert("L")
                metrics.steps_applied.append("grayscale_conversion")

            # Step 2: Remove dark borders (common in scanned documents)
            if remove_borders:
                image = AdvancedImagePreprocessor._remove_borders(image)
                if image.size != metrics.original_size:
                    metrics.steps_applied.append("border_removal")

            # Step 3: Upscale low-DPI images
            if current_dpi < target_dpi:
                scale = min(target_dpi / max(current_dpi, 1), MAX_UPSCALE_FACTOR)
                new_size = (int(image.size[0] * scale), int(image.size[1] * scale))
                image = image.resize(new_size, Image.LANCZOS)
                metrics.was_upscaled = True
                metrics.steps_applied.append(f"upscaled_{current_dpi}_to_{target_dpi}_dpi")

            # Step 4: Deskew
            if deskew and HAS_NUMPY:
                image, angle = AdvancedImagePreprocessor._deskew(image)
                metrics.deskew_angle = angle
                if abs(angle) > 0.3:
                    metrics.steps_applied.append(f"deskewed_{angle:.1f}_deg")

            # Step 5: Contrast enhancement
            if enhance_contrast:
                image = AdvancedImagePreprocessor._enhance_contrast(image)
                metrics.steps_applied.append("contrast_enhanced")

            # Step 6: Noise removal
            if denoise:
                image = AdvancedImagePreprocessor._denoise(image)
                metrics.was_denoised = True
                metrics.steps_applied.append("denoised")

            # Step 7: Adaptive binarization (optional, for very noisy scans)
            if binarize:
                image = AdvancedImagePreprocessor._adaptive_binarize(image)
                metrics.was_binarized = True
                metrics.steps_applied.append("adaptive_binarization")

            metrics.processed_size = image.size

            buf = io.BytesIO()
            image.save(buf, format="PNG")
            processed_bytes = buf.getvalue()

            metrics.processing_ms = int((time.monotonic() - start) * 1000)
            return processed_bytes, metrics

        except Exception as e:
            logger.warning("Advanced preprocessing failed: %s", e)
            metrics.processing_ms = int((time.monotonic() - start) * 1000)
            metrics.steps_applied.append(f"error: {str(e)[:100]}")
            return image_bytes, metrics

    @staticmethod
    def _remove_borders(image: "Image.Image") -> "Image.Image":
        """Remove dark borders from scanned documents.

        Scanned documents often have black or dark grey borders from the
        scanner lid. This finds the content region and crops to it.
        """
        if not HAS_NUMPY:
            return image

        try:
            arr = np.array(image)
            # Consider pixels above threshold as "content"
            threshold = 200
            content_mask = arr < threshold

            # Find rows/cols with content
            row_has_content = np.any(content_mask, axis=1)
            col_has_content = np.any(content_mask, axis=0)

            if not np.any(row_has_content) or not np.any(col_has_content):
                return image

            # Find bounding box with 5px margin
            rows = np.where(row_has_content)[0]
            cols = np.where(col_has_content)[0]

            top = max(0, rows[0] - 5)
            bottom = min(arr.shape[0], rows[-1] + 5)
            left = max(0, cols[0] - 5)
            right = min(arr.shape[1], cols[-1] + 5)

            # Only crop if we are removing a meaningful border (> 2% of image)
            original_area = arr.shape[0] * arr.shape[1]
            cropped_area = (bottom - top) * (right - left)
            if cropped_area < original_area * 0.95:
                return image.crop((left, top, right, bottom))

            return image

        except Exception as e:
            logger.debug("Border removal failed: %s", e)
            return image

    @staticmethod
    def _deskew(image: "Image.Image") -> Tuple["Image.Image", float]:
        """Correct document skew using projection profile analysis."""
        try:
            arr = np.array(image)
            # Binarize for analysis
            binary = (arr < BINARIZATION_THRESHOLD).astype(np.uint8)

            best_angle = 0.0
            best_variance = 0.0

            # Search in -5 to +5 degrees in 0.5 degree steps
            for angle_tenths in range(-50, 51, 5):
                angle = angle_tenths / 10.0
                rotated = image.rotate(
                    angle, resample=Image.BICUBIC, expand=False,
                    fillcolor=255,
                )
                rot_arr = np.array(rotated)
                row_sums = np.sum(rot_arr, axis=1)
                variance = float(np.var(row_sums))
                if variance > best_variance:
                    best_variance = variance
                    best_angle = angle

            if abs(best_angle) > 0.3:
                image = image.rotate(
                    best_angle, resample=Image.BICUBIC, expand=True,
                    fillcolor=255,
                )

            return image, best_angle

        except Exception as e:
            logger.debug("Deskew failed: %s", e)
            return image, 0.0

    @staticmethod
    def _enhance_contrast(image: "Image.Image") -> "Image.Image":
        """Multi-step contrast enhancement."""
        try:
            # Auto-contrast with clipping
            image = ImageOps.autocontrast(image, cutoff=2)

            # Adaptive sharpening
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.5)

            # Slight brightness boost for washed-out scans
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.2)

            return image
        except Exception as e:
            logger.debug("Contrast enhancement failed: %s", e)
            return image

    @staticmethod
    def _denoise(image: "Image.Image") -> "Image.Image":
        """Remove noise while preserving text edges."""
        try:
            # Median filter (better edge preservation than Gaussian)
            return image.filter(ImageFilter.MedianFilter(size=3))
        except Exception as e:
            logger.debug("Denoising failed: %s", e)
            return image

    @staticmethod
    def _adaptive_binarize(image: "Image.Image") -> "Image.Image":
        """Adaptive binarization for variable lighting conditions.

        Uses a local mean approach: each pixel is compared to the
        average of its neighborhood rather than a global threshold.
        """
        if not HAS_NUMPY:
            # Fall back to simple threshold
            return image.point(lambda p: 255 if p > BINARIZATION_THRESHOLD else 0)

        try:
            arr = np.array(image, dtype=np.float64)

            # Local mean using a block approach
            block_size = 31
            # Pad the array
            padded = np.pad(arr, block_size // 2, mode="reflect")

            # Compute cumulative sum for fast mean calculation
            cumsum = np.cumsum(np.cumsum(padded, axis=0), axis=1)

            # Compute local means
            h, w = arr.shape
            local_mean = np.zeros_like(arr)
            half = block_size // 2

            for y in range(h):
                for x in range(w):
                    y1 = y
                    y2 = y + block_size
                    x1 = x
                    x2 = x + block_size
                    area = block_size * block_size
                    total = (
                        cumsum[y2, x2]
                        - cumsum[y1, x2]
                        - cumsum[y2, x1]
                        + cumsum[y1, x1]
                    )
                    local_mean[y, x] = total / area

            # Binarize: pixel is black if it is below local mean minus offset
            offset = 10
            binary = np.where(arr < local_mean - offset, 0, 255).astype(np.uint8)

            return Image.fromarray(binary, mode="L")

        except Exception as e:
            logger.debug("Adaptive binarization failed, using global threshold: %s", e)
            return image.point(lambda p: 255 if p > BINARIZATION_THRESHOLD else 0)


# ============================================================================
# FIELD VALIDATOR
# ============================================================================

class FieldValidator:
    """Validates extracted fields against document-type-specific rules.

    Applies single-field validations (type, range, pattern) and
    cross-field validations (e.g., net_pay <= gross_pay).
    """

    @staticmethod
    def validate_field(
        field_name: str,
        value: Any,
        validation_rule: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Validate a single field value against its rule.

        Args:
            field_name: Name of the field.
            value: Extracted value.
            validation_rule: Validation specification from the schema.

        Returns:
            Tuple of (is_valid, validation_message).
        """
        if value is None:
            return True, ""  # Missing values are handled by required-field checks

        rule_type = validation_rule.get("type", "string")

        if rule_type == "currency":
            return FieldValidator._validate_currency(
                field_name, value,
                validation_rule.get("min"),
                validation_rule.get("max"),
            )

        if rule_type == "integer":
            return FieldValidator._validate_integer(
                field_name, value,
                validation_rule.get("min"),
                validation_rule.get("max"),
            )

        if rule_type == "number":
            return FieldValidator._validate_number(
                field_name, value,
                validation_rule.get("min"),
                validation_rule.get("max"),
            )

        if rule_type == "regex":
            pattern = validation_rule.get("pattern", "")
            return FieldValidator._validate_regex(field_name, value, pattern)

        if rule_type == "enum":
            allowed = validation_rule.get("values", [])
            return FieldValidator._validate_enum(field_name, value, allowed)

        return True, ""

    @staticmethod
    def validate_cross_fields(
        fields: Dict[str, Any],
        cross_validations: List[Dict[str, Any]],
    ) -> List[str]:
        """Run cross-field validations.

        Args:
            fields: Dict of field_name -> value.
            cross_validations: List of cross-validation rules from the schema.

        Returns:
            List of validation error messages (empty if all pass).
        """
        errors: List[str] = []

        for rule in cross_validations:
            check_type = rule.get("check", "")
            rule_fields = rule.get("fields", [])
            message = rule.get("message", "Cross-field validation failed")

            # Get field values
            values = []
            all_present = True
            for f in rule_fields:
                v = fields.get(f)
                if v is None:
                    all_present = False
                    break
                values.append(FieldValidator._to_float(v))

            if not all_present:
                continue  # Skip if any field is missing

            if any(v is None for v in values):
                continue

            if check_type == "lte" and len(values) >= 2:
                # First field should be <= second field
                if values[0] > values[1]:
                    errors.append(
                        f"{message}: {rule_fields[0]}={values[0]} > "
                        f"{rule_fields[1]}={values[1]}"
                    )

            elif check_type == "gte" and len(values) >= 2:
                if values[0] < values[1]:
                    errors.append(
                        f"{message}: {rule_fields[0]}={values[0]} < "
                        f"{rule_fields[1]}={values[1]}"
                    )

            elif check_type == "max_value":
                max_val = rule.get("max", float("inf"))
                for i, v in enumerate(values):
                    if v > max_val:
                        errors.append(f"{message}: {rule_fields[i]}={v}")

            elif check_type == "balance_equation" and len(values) >= 4:
                # beginning + deposits - withdrawals should equal ending
                beginning, deposits, withdrawals, ending = values[:4]
                tolerance = rule.get("tolerance", 1.0)
                calculated = beginning + deposits - withdrawals
                diff = abs(calculated - ending)
                if diff > tolerance:
                    errors.append(
                        f"{message}: calculated={calculated:.2f} vs "
                        f"ending={ending:.2f} (diff={diff:.2f})"
                    )

        return errors

    @staticmethod
    def _validate_currency(
        name: str, value: Any, min_val: Optional[float], max_val: Optional[float],
    ) -> Tuple[bool, str]:
        num = FieldValidator._to_float(value)
        if num is None:
            return False, f"{name}: not a valid currency value"
        if min_val is not None and num < min_val:
            return False, f"{name}: {num} below minimum {min_val}"
        if max_val is not None and num > max_val:
            return False, f"{name}: {num} exceeds maximum {max_val}"
        return True, ""

    @staticmethod
    def _validate_integer(
        name: str, value: Any, min_val: Optional[int], max_val: Optional[int],
    ) -> Tuple[bool, str]:
        try:
            num = int(value)
        except (ValueError, TypeError):
            return False, f"{name}: not a valid integer"
        if min_val is not None and num < min_val:
            return False, f"{name}: {num} below minimum {min_val}"
        if max_val is not None and num > max_val:
            return False, f"{name}: {num} exceeds maximum {max_val}"
        return True, ""

    @staticmethod
    def _validate_number(
        name: str, value: Any, min_val: Optional[float], max_val: Optional[float],
    ) -> Tuple[bool, str]:
        num = FieldValidator._to_float(value)
        if num is None:
            return False, f"{name}: not a valid number"
        if min_val is not None and num < min_val:
            return False, f"{name}: {num} below minimum {min_val}"
        if max_val is not None and num > max_val:
            return False, f"{name}: {num} exceeds maximum {max_val}"
        return True, ""

    @staticmethod
    def _validate_regex(name: str, value: Any, pattern: str) -> Tuple[bool, str]:
        val_str = str(value).strip()
        if not re.match(pattern, val_str):
            return False, f"{name}: '{val_str}' does not match pattern {pattern}"
        return True, ""

    @staticmethod
    def _validate_enum(
        name: str, value: Any, allowed: List[str],
    ) -> Tuple[bool, str]:
        val_str = str(value).strip().lower()
        allowed_lower = [a.lower() for a in allowed]
        if val_str not in allowed_lower:
            return False, f"{name}: '{val_str}' not in {allowed}"
        return True, ""

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").strip()
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None


# ============================================================================
# HANDWRITING DETECTOR
# ============================================================================

class HandwritingDetector:
    """Detect and analyze handwritten content in document images.

    Uses a combination of heuristics (stroke variance analysis) and
    Claude Vision API for definitive detection. Routes handwritten
    documents to specialized OCR handling.
    """

    def __init__(self):
        self._anthropic_client: Optional[Any] = None

    def _get_client(self) -> Optional[Any]:
        if self._anthropic_client is not None:
            return self._anthropic_client
        if not HAS_ANTHROPIC:
            return None
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        try:
            self._anthropic_client = Anthropic(api_key=api_key)
            return self._anthropic_client
        except Exception as e:
            logger.warning("Failed to create Anthropic client for handwriting detection: %s", e)
            return None

    def detect(
        self,
        image_bytes: bytes,
        use_heuristics: bool = True,
        use_vision_api: bool = True,
    ) -> HandwritingDetection:
        """Detect handwriting in an image.

        Two-phase detection:
        1. Fast heuristic analysis (stroke variance, edge density)
        2. Claude Vision API for confirmation (if heuristics are ambiguous)

        Args:
            image_bytes: Raw image bytes.
            use_heuristics: Whether to run heuristic analysis.
            use_vision_api: Whether to use Claude Vision for confirmation.

        Returns:
            HandwritingDetection result.
        """
        result = HandwritingDetection()

        # Phase 1: Heuristic detection
        heuristic_score = 0.0
        if use_heuristics and HAS_PIL and HAS_NUMPY:
            heuristic_score = self._heuristic_detect(image_bytes)

        # Phase 2: Vision API if heuristics are ambiguous (0.3-0.7)
        vision_score = 0.0
        if use_vision_api and (0.3 <= heuristic_score <= 0.7 or not use_heuristics):
            vision_result = self._vision_detect(image_bytes)
            if vision_result is not None:
                vision_score = vision_result

        # Combine scores
        if use_heuristics and use_vision_api and vision_score > 0:
            # Weighted average: vision API is more reliable
            combined = heuristic_score * 0.3 + vision_score * 0.7
        elif vision_score > 0:
            combined = vision_score
        else:
            combined = heuristic_score

        result.confidence = combined
        result.has_handwriting = combined >= 0.5
        result.handwriting_percentage = combined * 100

        if result.has_handwriting:
            result.recommended_engine = "claude_vision"
        else:
            result.recommended_engine = "tesseract"

        return result

    def _heuristic_detect(self, image_bytes: bytes) -> float:
        """Fast heuristic handwriting detection using image analysis.

        Analyzes stroke width variance, edge density patterns, and
        line regularity. Handwriting tends to have:
        - Higher stroke width variance than printed text
        - Less regular line spacing
        - More curved edges
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            if image.mode != "L":
                image = image.convert("L")

            arr = np.array(image)

            # Edge detection using simple gradient
            # Handwriting has more varied edge angles than printed text
            grad_x = np.abs(np.diff(arr.astype(np.float64), axis=1))
            grad_y = np.abs(np.diff(arr.astype(np.float64), axis=0))

            # Compute edge density
            total_pixels = arr.size
            edge_pixels_x = np.sum(grad_x > 30)
            edge_pixels_y = np.sum(grad_y > 30)
            edge_density = (edge_pixels_x + edge_pixels_y) / (2 * total_pixels)

            # Compute row-wise text density variance
            # Printed text has very regular line spacing; handwriting does not
            binary = (arr < BINARIZATION_THRESHOLD).astype(np.uint8)
            row_density = np.sum(binary, axis=1) / arr.shape[1]

            # Find text rows (non-empty rows)
            text_rows = row_density[row_density > 0.01]
            if len(text_rows) < 5:
                return 0.0

            density_variance = float(np.var(text_rows))

            # Handwriting indicators:
            # - Higher edge density variation (0.02-0.08 typical for handwriting)
            # - Higher row density variance (irregular line heights)
            score = 0.0

            if edge_density > 0.03:
                score += 0.3
            elif edge_density > 0.02:
                score += 0.15

            if density_variance > 0.005:
                score += 0.3
            elif density_variance > 0.002:
                score += 0.15

            # Check for diagonal edge predominance (curves in handwriting)
            if edge_pixels_x > 0 and edge_pixels_y > 0:
                ratio = min(edge_pixels_x, edge_pixels_y) / max(edge_pixels_x, edge_pixels_y)
                # Handwriting has more balanced x/y edges; printed text is more horizontal
                if ratio > 0.6:
                    score += 0.2

            return min(score, 1.0)

        except Exception as e:
            logger.debug("Heuristic handwriting detection failed: %s", e)
            return 0.0

    def _vision_detect(self, image_bytes: bytes) -> Optional[float]:
        """Use Claude Vision API to detect handwriting."""
        client = self._get_client()
        if client is None:
            return None

        if len(image_bytes) > MAX_VISION_API_SIZE:
            return None

        try:
            import base64
            from services.smart_docs.ai_resilience import resilient_ai_call

            b64_image = base64.b64encode(image_bytes).decode("utf-8")
            response = resilient_ai_call(
                client=client,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Analyze this document image for handwriting. "
                                "What percentage of text is handwritten vs machine-printed? "
                                "Reply ONLY in this format: HANDWRITING:<percentage 0-100>"
                            ),
                        },
                    ],
                }],
                model="claude-sonnet-4-20250514",
                max_tokens=50,
                operation_name="ocr_handwriting_detect",
                timeout=15.0,
            )

            if response is None:
                return None

            answer = response.content[0].text.strip() if response.content else ""
            match = re.search(r"HANDWRITING:\s*(\d+)", answer)
            if match:
                percentage = int(match.group(1))
                return percentage / 100.0

            return None

        except Exception as e:
            logger.debug("Vision handwriting detection failed: %s", e)
            return None


# ============================================================================
# MAIN SERVICE
# ============================================================================

class OCREnhancementService:
    """Advanced OCR enhancement service for mortgage document processing.

    Orchestrates the full enhanced pipeline:
    1. Cache lookup (skip processing if identical document seen before)
    2. Format detection and image pre-processing
    3. Multi-engine OCR with intelligent fallback
    4. Handwriting detection and specialized routing
    5. Post-processing: spell correction, field validation
    6. Table extraction for financial documents
    7. Structured data extraction with confidence scoring
    8. Cache storage of results
    9. Confidence-tier classification (auto-accept / review / reject)

    Integrates with:
    - DocumentOCRService for core OCR engine orchestration
    - DocumentCacheService for hash-based result caching
    - FinancialTableExtractor for table parsing
    - SpellCorrector for domain-specific corrections
    - HandwritingDetector for handwriting analysis
    - FieldValidator for extracted field validation
    """

    def __init__(self, org_id: int):
        """Initialize the OCR enhancement service.

        Args:
            org_id: Organization ID for tenant-scoped caching and logging.
        """
        self.org_id = org_id
        self._spell_corrector = SpellCorrector()
        self._table_extractor = FinancialTableExtractor()
        self._handwriting_detector = HandwritingDetector()
        self._field_validator = FieldValidator()
        self._preprocessor = AdvancedImagePreprocessor()

        # Lazy-loaded services
        self._ocr_service = None
        self._cache_service = None

    def _get_ocr_service(self):
        """Lazy-load the base DocumentOCRService."""
        if self._ocr_service is None:
            from services.smart_docs.document_ocr_service import get_document_ocr_service
            self._ocr_service = get_document_ocr_service()
        return self._ocr_service

    def _get_cache_service(self):
        """Lazy-load the DocumentCacheService."""
        if self._cache_service is None:
            from services.smart_docs.document_cache_service import get_document_cache_service
            self._cache_service = get_document_cache_service()
        return self._cache_service

    # -----------------------------------------------------------------
    # Main processing entry point
    # -----------------------------------------------------------------

    async def process_document(
        self,
        file_bytes: bytes,
        mime_type: Optional[str] = None,
        filename: Optional[str] = None,
        document_type: Optional[str] = None,
        language: str = DocumentLanguage.ENGLISH.value,
        preprocess: bool = True,
        binarize: bool = False,
        extract_tables: bool = True,
        detect_handwriting: bool = True,
        max_pages: int = 50,
        db: Optional[Any] = None,
    ) -> EnhancedOCRResult:
        """Process a document through the enhanced OCR pipeline.

        Args:
            file_bytes: Raw document file bytes.
            mime_type: MIME type (auto-detected if not provided).
            filename: Original filename.
            document_type: Mortgage document type for structured extraction.
            language: OCR language code (eng, spa, eng+spa).
            preprocess: Whether to apply image pre-processing.
            binarize: Whether to apply binarization (useful for very noisy scans).
            extract_tables: Whether to extract table structures.
            detect_handwriting: Whether to detect handwriting.
            max_pages: Maximum pages to process.
            db: Optional SQLAlchemy session for cache operations.

        Returns:
            EnhancedOCRResult with full pipeline results.
        """
        overall_start = time.monotonic()
        document_id = str(uuid.uuid4())[:12]

        logger.info(
            "ocr_enhance START doc_id=%s org=%d mime=%s doc_type=%s lang=%s",
            document_id, self.org_id, mime_type, document_type, language,
        )

        # --- Step 1: Cache lookup ---
        doc_hash = None
        if db is not None and file_bytes:
            cached_result = self._check_cache(db, file_bytes)
            if cached_result is not None:
                cached_result.document_id = document_id
                cached_result.cached = True
                cached_result.total_processing_ms = int(
                    (time.monotonic() - overall_start) * 1000
                )
                logger.info(
                    "ocr_enhance CACHE_HIT doc_id=%s org=%d ms=%d",
                    document_id, self.org_id, cached_result.total_processing_ms,
                )
                return cached_result

            doc_hash = self._get_cache_service().get_or_compute_hash(file_bytes)

        # --- Step 2: Language detection ---
        detected_language = language
        if language == DocumentLanguage.ENGLISH.value:
            # Quick Spanish check on first few KB of any text we can pull
            sample_text = self._quick_text_sample(file_bytes, mime_type)
            is_spanish, spanish_conf = self._spell_corrector.detect_spanish(sample_text)
            if is_spanish:
                detected_language = DocumentLanguage.ENGLISH_SPANISH.value
                logger.info(
                    "ocr_enhance SPANISH_DETECTED doc_id=%s conf=%.2f",
                    document_id, spanish_conf,
                )

        # --- Step 3: Core OCR extraction ---
        ocr_service = self._get_ocr_service()
        ocr_result = ocr_service.extract_text(
            file_bytes=file_bytes,
            mime_type=mime_type,
            filename=filename,
            language=detected_language,
            preprocess=preprocess,
            max_pages=min(max_pages, MAX_PDF_PAGES),
            db=db,
            organization_id=self.org_id,
        )

        if not ocr_result.success:
            error_result = EnhancedOCRResult(
                success=False,
                document_id=document_id,
                full_text="",
                corrected_text="",
                error=ocr_result.error or "OCR extraction failed",
                total_processing_ms=int(
                    (time.monotonic() - overall_start) * 1000
                ),
            )
            return error_result

        # --- Step 4: Spell correction / post-processing ---
        corrected_text, correction_count = self._spell_corrector.correct(
            ocr_result.full_text,
        )

        # --- Step 5: Build page-level enhanced results ---
        page_results: List[PageEnhancedResult] = []
        for page in ocr_result.pages:
            page_corrected, page_corrections = self._spell_corrector.correct(page.text)
            page_result = PageEnhancedResult(
                page_number=page.page_number,
                text=page.text,
                corrected_text=page_corrected,
                confidence=page.confidence,
                word_count=len(page.text.split()) if page.text else 0,
                corrections_applied=page_corrections,
                engine_used=page.engine_used,
                language_detected=detected_language,
                processing_ms=page.processing_ms,
            )
            page_results.append(page_result)

        # --- Step 6: Handwriting detection ---
        handwriting_detected = ocr_result.has_handwriting
        if detect_handwriting and not handwriting_detected:
            # Run handwriting detection on first page image if available
            hw_result = self._detect_handwriting_on_pages(
                file_bytes, mime_type, ocr_result.pages,
            )
            handwriting_detected = hw_result.has_handwriting
            if page_results:
                page_results[0].handwriting = hw_result

        # --- Step 7: Table extraction ---
        all_tables: List[ExtractedTable] = []
        if extract_tables:
            all_tables = self._extract_tables(
                file_bytes, mime_type, corrected_text, ocr_result.pages,
            )
            # Attach tables to their pages
            for table in all_tables:
                for page_result in page_results:
                    if page_result.page_number == table.page_number:
                        page_result.tables.append(table)

        # --- Step 8: Structured data extraction ---
        structured_result = None
        if document_type:
            structured_result = self._extract_structured_data(
                corrected_text, document_type, all_tables,
                ocr_result.overall_confidence, ocr_result.pages,
            )

        # --- Step 9: Build final result ---
        overall_confidence = ocr_result.overall_confidence
        confidence_level = ConfidenceLevel.from_score(overall_confidence)

        review_reasons: List[str] = list(ocr_result.review_reasons)
        needs_review = ocr_result.needs_manual_review

        if handwriting_detected:
            review_reasons.append("Handwriting detected in document")
            needs_review = True

        if confidence_level == ConfidenceLevel.REJECT:
            review_reasons.append(
                f"OCR confidence {overall_confidence:.1%} below threshold "
                f"({CONFIDENCE_REJECT:.0%})"
            )
            needs_review = True
        elif confidence_level == ConfidenceLevel.MANUAL_REVIEW:
            review_reasons.append(
                f"OCR confidence {overall_confidence:.1%} requires review "
                f"(auto-accept threshold: {CONFIDENCE_AUTO_ACCEPT:.0%})"
            )
            needs_review = True

        if structured_result and structured_result.validation_errors:
            review_reasons.extend(structured_result.validation_errors)
            needs_review = True

        if correction_count > 0:
            logger.info(
                "ocr_enhance CORRECTIONS doc_id=%s count=%d",
                document_id, correction_count,
            )

        # Truncate output to prevent memory issues
        if len(corrected_text) > MAX_OCR_OUTPUT_CHARS:
            corrected_text = corrected_text[:MAX_OCR_OUTPUT_CHARS]
            review_reasons.append(
                f"Text truncated to {MAX_OCR_OUTPUT_CHARS:,} characters"
            )

        result = EnhancedOCRResult(
            success=True,
            document_id=document_id,
            full_text=ocr_result.full_text[:MAX_OCR_OUTPUT_CHARS],
            corrected_text=corrected_text,
            pages=page_results,
            page_count=len(page_results),
            overall_confidence=overall_confidence,
            confidence_level=confidence_level,
            structured_data=structured_result,
            tables=all_tables,
            handwriting_detected=handwriting_detected,
            language_detected=detected_language,
            needs_review=needs_review,
            review_reasons=review_reasons,
            total_corrections=correction_count,
            engine_used=ocr_result.engine_used,
            total_processing_ms=int(
                (time.monotonic() - overall_start) * 1000
            ),
        )

        # --- Step 10: Cache the result ---
        if db is not None and doc_hash:
            self._store_cache(db, doc_hash, result)

        logger.info(
            "ocr_enhance COMPLETE doc_id=%s org=%d pages=%d conf=%.3f "
            "level=%s tables=%d corrections=%d ms=%d",
            document_id, self.org_id, result.page_count,
            result.overall_confidence, result.confidence_level.value,
            len(all_tables), correction_count, result.total_processing_ms,
        )

        return result

    # -----------------------------------------------------------------
    # Batch processing
    # -----------------------------------------------------------------

    async def process_batch(
        self,
        pages: List[bytes],
        mime_type: str = "image/png",
        document_type: Optional[str] = None,
        language: str = DocumentLanguage.ENGLISH.value,
        preprocess: bool = True,
        extract_tables: bool = True,
        db: Optional[Any] = None,
    ) -> BatchOCRResult:
        """Process multiple pages as a single batch.

        Useful for multi-page documents that arrive as individual page
        images (e.g., scanned bank statements, multi-page tax returns).

        Args:
            pages: List of image bytes, one per page.
            mime_type: MIME type for all pages.
            document_type: Document type for structured extraction.
            language: OCR language code.
            preprocess: Whether to pre-process images.
            extract_tables: Whether to extract tables.
            db: Optional SQLAlchemy session for cache.

        Returns:
            BatchOCRResult with combined results across all pages.
        """
        batch_start = time.monotonic()
        batch_id = str(uuid.uuid4())[:12]

        logger.info(
            "ocr_enhance BATCH_START batch_id=%s org=%d pages=%d doc_type=%s",
            batch_id, self.org_id, len(pages), document_type,
        )

        page_results: List[PageEnhancedResult] = []
        pages_succeeded = 0
        pages_failed = 0
        all_texts: List[str] = []
        all_corrected_texts: List[str] = []
        all_confidences: List[float] = []

        ocr_service = self._get_ocr_service()

        for page_idx, page_bytes in enumerate(pages):
            page_start = time.monotonic()
            page_num = page_idx + 1

            try:
                # Pre-process
                processed_bytes = page_bytes
                preprocessing_metrics = PreprocessingMetrics()
                if preprocess:
                    processed_bytes, preprocessing_metrics = (
                        self._preprocessor.preprocess(
                            page_bytes,
                            deskew=True,
                            denoise=True,
                            enhance_contrast=True,
                        )
                    )

                # OCR the page
                page_ocr = ocr_service.extract_text(
                    file_bytes=processed_bytes,
                    mime_type=mime_type,
                    language=language,
                    preprocess=False,  # Already preprocessed
                    max_pages=1,
                )

                if not page_ocr.success:
                    pages_failed += 1
                    page_results.append(PageEnhancedResult(
                        page_number=page_num,
                        text="",
                        corrected_text="",
                        confidence=0.0,
                        preprocessing=preprocessing_metrics,
                        processing_ms=int((time.monotonic() - page_start) * 1000),
                    ))
                    continue

                # Spell correction
                corrected, corrections = self._spell_corrector.correct(
                    page_ocr.full_text,
                )

                # Table extraction for this page
                page_tables: List[ExtractedTable] = []
                if extract_tables:
                    page_tables = self._table_extractor.extract_tables_from_text(
                        corrected, page_num,
                    )

                page_result = PageEnhancedResult(
                    page_number=page_num,
                    text=page_ocr.full_text,
                    corrected_text=corrected,
                    confidence=page_ocr.overall_confidence,
                    word_count=len(page_ocr.full_text.split()) if page_ocr.full_text else 0,
                    corrections_applied=corrections,
                    tables=page_tables,
                    preprocessing=preprocessing_metrics,
                    engine_used=page_ocr.engine_used,
                    language_detected=language,
                    processing_ms=int((time.monotonic() - page_start) * 1000),
                )

                page_results.append(page_result)
                all_texts.append(page_ocr.full_text)
                all_corrected_texts.append(corrected)
                all_confidences.append(page_ocr.overall_confidence)
                pages_succeeded += 1

            except Exception as e:
                logger.warning(
                    "Batch page %d failed: %s", page_num, e,
                )
                pages_failed += 1
                page_results.append(PageEnhancedResult(
                    page_number=page_num,
                    text="",
                    corrected_text="",
                    confidence=0.0,
                    processing_ms=int((time.monotonic() - page_start) * 1000),
                ))

        # Combine results
        combined_text = "\n\n".join(all_texts)
        combined_corrected = "\n\n".join(all_corrected_texts)
        overall_confidence = (
            statistics.mean(all_confidences) if all_confidences else 0.0
        )
        confidence_level = ConfidenceLevel.from_score(overall_confidence)

        # Structured extraction on combined text
        structured_result = None
        if document_type and combined_corrected:
            all_tables = []
            for pr in page_results:
                all_tables.extend(pr.tables)
            structured_result = self._extract_structured_data(
                combined_corrected, document_type, all_tables,
                overall_confidence, [],
            )

        total_ms = int((time.monotonic() - batch_start) * 1000)

        result = BatchOCRResult(
            success=pages_succeeded > 0,
            batch_id=batch_id,
            page_results=page_results,
            combined_text=combined_text[:MAX_OCR_OUTPUT_CHARS],
            combined_corrected_text=combined_corrected[:MAX_OCR_OUTPUT_CHARS],
            overall_confidence=overall_confidence,
            confidence_level=confidence_level,
            structured_data=structured_result,
            total_pages=len(pages),
            pages_succeeded=pages_succeeded,
            pages_failed=pages_failed,
            total_processing_ms=total_ms,
        )

        logger.info(
            "ocr_enhance BATCH_COMPLETE batch_id=%s org=%d "
            "succeeded=%d failed=%d conf=%.3f ms=%d",
            batch_id, self.org_id, pages_succeeded, pages_failed,
            overall_confidence, total_ms,
        )

        return result

    # -----------------------------------------------------------------
    # Cache integration
    # -----------------------------------------------------------------

    def _check_cache(
        self, db: Any, file_bytes: bytes,
    ) -> Optional[EnhancedOCRResult]:
        """Check document cache for existing enhanced OCR result."""
        try:
            cache = self._get_cache_service()
            doc_hash = cache.get_or_compute_hash(file_bytes)
            cached = cache.get_cached_ocr(db, doc_hash, self.org_id)
            if cached is None:
                return None

            # Reconstruct EnhancedOCRResult from cached dict
            return EnhancedOCRResult(
                success=cached.get("success", True),
                document_id="",
                full_text=cached.get("full_text", ""),
                corrected_text=cached.get("corrected_text", ""),
                page_count=cached.get("page_count", 0),
                overall_confidence=cached.get("overall_confidence", 0.0),
                confidence_level=ConfidenceLevel(
                    cached.get("confidence_level", "reject")
                ),
                handwriting_detected=cached.get("handwriting_detected", False),
                language_detected=cached.get("language_detected", "eng"),
                needs_review=cached.get("needs_review", False),
                review_reasons=cached.get("review_reasons", []),
                total_corrections=cached.get("total_corrections", 0),
                engine_used=cached.get("engine_used", "cache"),
            )

        except Exception as e:
            logger.warning("Enhanced OCR cache lookup failed: %s", e)
            return None

    def _store_cache(
        self, db: Any, doc_hash: str, result: EnhancedOCRResult,
    ) -> None:
        """Store enhanced OCR result in document cache."""
        try:
            cache = self._get_cache_service()
            cache_data = {
                "success": result.success,
                "full_text": result.full_text,
                "corrected_text": result.corrected_text,
                "page_count": result.page_count,
                "overall_confidence": result.overall_confidence,
                "confidence_level": result.confidence_level.value,
                "handwriting_detected": result.handwriting_detected,
                "language_detected": result.language_detected,
                "needs_review": result.needs_review,
                "review_reasons": result.review_reasons,
                "total_corrections": result.total_corrections,
                "engine_used": result.engine_used,
            }

            # Store structured data summary (not full text to save cache space)
            if result.structured_data:
                cache_data["structured_summary"] = {
                    "document_type": result.structured_data.document_type,
                    "overall_confidence": result.structured_data.overall_confidence,
                    "field_count": len(result.structured_data.fields),
                    "missing_required": result.structured_data.missing_required,
                    "validation_errors": result.structured_data.validation_errors,
                }

            cache.cache_ocr(
                db, doc_hash, self.org_id, cache_data,
                ttl_hours=DEFAULT_ENHANCED_OCR_TTL_HOURS,
            )

        except Exception as e:
            logger.warning("Enhanced OCR cache store failed: %s", e)

    # -----------------------------------------------------------------
    # Handwriting detection helpers
    # -----------------------------------------------------------------

    def _detect_handwriting_on_pages(
        self,
        file_bytes: bytes,
        mime_type: Optional[str],
        pages: list,
    ) -> HandwritingDetection:
        """Run handwriting detection, choosing the right image source."""
        # For images, use the file directly
        if mime_type and mime_type.startswith("image/"):
            return self._handwriting_detector.detect(file_bytes)

        # For PDFs, convert first page to image for detection
        if mime_type == "application/pdf" and HAS_PDF2IMAGE:
            try:
                images = convert_from_bytes(
                    file_bytes, dpi=150, first_page=1, last_page=1,
                )
                if images:
                    buf = io.BytesIO()
                    images[0].save(buf, format="PNG")
                    return self._handwriting_detector.detect(buf.getvalue())
            except Exception as e:
                logger.debug("PDF handwriting detection failed: %s", e)

        return HandwritingDetection()

    # -----------------------------------------------------------------
    # Table extraction helpers
    # -----------------------------------------------------------------

    def _extract_tables(
        self,
        file_bytes: bytes,
        mime_type: Optional[str],
        corrected_text: str,
        pages: list,
    ) -> List[ExtractedTable]:
        """Extract tables using the best available method."""
        tables: List[ExtractedTable] = []

        # Method 1: PDF native table extraction (highest accuracy)
        if mime_type == "application/pdf" and HAS_PDFPLUMBER:
            pdf_tables = self._table_extractor.extract_tables_from_pdfplumber(
                file_bytes,
            )
            if pdf_tables:
                tables.extend(pdf_tables)
                return tables  # pdfplumber tables are best; skip text-based

        # Method 2: Text-based table extraction
        # Use per-page extraction from OCR pages
        for page in pages:
            page_text = page.text if hasattr(page, "text") else ""
            if page_text:
                page_num = page.page_number if hasattr(page, "page_number") else 1
                page_tables = self._table_extractor.extract_tables_from_text(
                    page_text, page_num,
                )
                tables.extend(page_tables)

        # Fall back to full-text extraction if no per-page tables found
        if not tables and corrected_text:
            tables = self._table_extractor.extract_tables_from_text(
                corrected_text, page_number=1,
            )

        return tables

    # -----------------------------------------------------------------
    # Structured data extraction
    # -----------------------------------------------------------------

    def _extract_structured_data(
        self,
        text: str,
        document_type: str,
        tables: List[ExtractedTable],
        base_confidence: float,
        pages: list,
    ) -> StructuredExtractionResult:
        """Extract and validate structured fields for a mortgage document type.

        Uses regex-based extraction from document_ocr_service patterns,
        enriched with table data and cross-field validation.
        """
        doc_type_lower = document_type.lower()
        schema = STRUCTURED_SCHEMAS.get(doc_type_lower)

        if schema is None:
            return StructuredExtractionResult(
                success=False,
                document_type=document_type,
                error=f"No structured schema for document type: {document_type}",
            )

        # Use the base OCR service for regex-based field extraction
        ocr_service = self._get_ocr_service()

        from services.smart_docs.document_ocr_service import OCRExtractionResult
        mock_ocr = OCRExtractionResult(
            success=True,
            full_text=text,
            overall_confidence=base_confidence,
        )
        field_result = ocr_service.extract_mortgage_fields(mock_ocr, doc_type_lower)

        # Convert to StructuredField objects with validation
        structured_fields: Dict[str, StructuredField] = {}
        validation_errors: List[str] = []
        missing_required: List[str] = []

        required_fields = set(schema.get("required_fields", []))
        validations = schema.get("validations", {})

        # Merge regex-extracted fields
        for field_name, extracted_field in field_result.fields.items():
            # Validate the field
            validation_rule = validations.get(field_name, {})
            is_valid, validation_msg = self._field_validator.validate_field(
                field_name, extracted_field.value, validation_rule,
            )

            needs_review = extracted_field.needs_review or not is_valid
            validation_notes = validation_msg if not is_valid else ""

            if not is_valid:
                validation_errors.append(validation_msg)

            structured_fields[field_name] = StructuredField(
                name=field_name,
                value=extracted_field.value,
                raw_value=extracted_field.raw_value,
                confidence=extracted_field.confidence,
                source_text=extracted_field.source_text,
                page_number=extracted_field.page_number,
                validated=is_valid,
                validation_notes=validation_notes,
                needs_review=needs_review,
            )

        # Check for missing required fields
        for req_field in required_fields:
            if req_field not in structured_fields:
                missing_required.append(req_field)

        # Enrich from tables if applicable
        table_enrichments = self._enrich_from_tables(
            doc_type_lower, structured_fields, tables,
        )
        for field_name, enriched_field in table_enrichments.items():
            if field_name not in structured_fields:
                structured_fields[field_name] = enriched_field
                if field_name in missing_required:
                    missing_required.remove(field_name)

        # Cross-field validation
        cross_validations = schema.get("cross_validations", [])
        field_values = {
            name: sf.value for name, sf in structured_fields.items()
        }
        cross_errors = self._field_validator.validate_cross_fields(
            field_values, cross_validations,
        )
        validation_errors.extend(cross_errors)

        # Calculate overall confidence for structured extraction
        if structured_fields:
            field_confs = [f.confidence for f in structured_fields.values()]
            overall_conf = statistics.mean(field_confs)
        else:
            overall_conf = 0.0

        # Reduce confidence if there are missing required fields or validation errors
        penalty = len(missing_required) * 0.05 + len(validation_errors) * 0.03
        overall_conf = max(0.0, overall_conf - penalty)

        confidence_level = ConfidenceLevel.from_score(overall_conf)
        needs_review = (
            confidence_level != ConfidenceLevel.AUTO_ACCEPT
            or bool(missing_required)
            or bool(validation_errors)
        )

        review_reasons: List[str] = []
        if missing_required:
            review_reasons.append(
                f"Missing required fields: {', '.join(missing_required)}"
            )
        if validation_errors:
            review_reasons.extend(validation_errors)
        if confidence_level == ConfidenceLevel.REJECT:
            review_reasons.append(
                f"Extraction confidence {overall_conf:.1%} below threshold"
            )

        return StructuredExtractionResult(
            success=True,
            document_type=document_type,
            fields=structured_fields,
            overall_confidence=overall_conf,
            confidence_level=confidence_level,
            missing_required=missing_required,
            validation_errors=validation_errors,
            tables=tables,
            needs_review=needs_review,
            review_reasons=review_reasons,
        )

    def _enrich_from_tables(
        self,
        document_type: str,
        existing_fields: Dict[str, StructuredField],
        tables: List[ExtractedTable],
    ) -> Dict[str, StructuredField]:
        """Attempt to fill missing fields from extracted table data.

        For bank statements, transaction tables provide deposit/withdrawal
        totals. For paystubs, earnings/deduction tables provide breakdowns.
        """
        enrichments: Dict[str, StructuredField] = {}

        if not tables:
            return enrichments

        if document_type == MortgageDocType.BANK_STATEMENT.value:
            enrichments.update(
                self._enrich_bank_statement_from_tables(existing_fields, tables),
            )
        elif document_type == MortgageDocType.PAYSTUB.value:
            enrichments.update(
                self._enrich_paystub_from_tables(existing_fields, tables),
            )

        return enrichments

    def _enrich_bank_statement_from_tables(
        self,
        existing: Dict[str, StructuredField],
        tables: List[ExtractedTable],
    ) -> Dict[str, StructuredField]:
        """Extract deposit/withdrawal totals from bank statement tables."""
        enrichments: Dict[str, StructuredField] = {}

        # Look for summary tables
        summary_tables = [t for t in tables if t.table_type == "summary"]
        transaction_tables = [t for t in tables if t.table_type == "transaction"]

        for table in summary_tables:
            for row in table.rows:
                row_text = " ".join(row).lower()

                if "total_deposits" not in existing and "total_deposits" not in enrichments:
                    if "deposit" in row_text or "credit" in row_text:
                        amount = self._extract_amount_from_row(row)
                        if amount is not None:
                            enrichments["total_deposits"] = StructuredField(
                                name="total_deposits",
                                value=amount,
                                raw_value=" | ".join(row),
                                confidence=table.confidence * 0.9,
                                page_number=table.page_number,
                                validated=True,
                                validation_notes="Extracted from summary table",
                            )

                if "total_withdrawals" not in existing and "total_withdrawals" not in enrichments:
                    if "withdrawal" in row_text or "debit" in row_text:
                        amount = self._extract_amount_from_row(row)
                        if amount is not None:
                            enrichments["total_withdrawals"] = StructuredField(
                                name="total_withdrawals",
                                value=amount,
                                raw_value=" | ".join(row),
                                confidence=table.confidence * 0.9,
                                page_number=table.page_number,
                                validated=True,
                                validation_notes="Extracted from summary table",
                            )

        # If we still lack totals, compute from transaction tables
        if transaction_tables and ("total_deposits" not in existing and "total_deposits" not in enrichments):
            deposits_sum = Decimal("0")
            withdrawals_sum = Decimal("0")
            transaction_count = 0

            for table in transaction_tables:
                for row in table.rows:
                    amounts = self._extract_all_amounts_from_row(row)
                    row_text = " ".join(row).lower()
                    for amount in amounts:
                        if amount > 0 and ("deposit" in row_text or "credit" in row_text):
                            deposits_sum += Decimal(str(amount))
                            transaction_count += 1
                        elif amount > 0 and ("withdrawal" in row_text or "debit" in row_text or "check" in row_text):
                            withdrawals_sum += Decimal(str(amount))
                            transaction_count += 1

            if transaction_count > 0:
                if "total_deposits" not in existing and "total_deposits" not in enrichments and deposits_sum > 0:
                    enrichments["total_deposits"] = StructuredField(
                        name="total_deposits",
                        value=float(deposits_sum),
                        raw_value=f"Computed from {transaction_count} transactions",
                        confidence=0.60,  # Lower confidence for computed values
                        validated=True,
                        validation_notes="Computed from transaction table rows",
                    )

                if "total_withdrawals" not in existing and "total_withdrawals" not in enrichments and withdrawals_sum > 0:
                    enrichments["total_withdrawals"] = StructuredField(
                        name="total_withdrawals",
                        value=float(withdrawals_sum),
                        raw_value=f"Computed from {transaction_count} transactions",
                        confidence=0.60,
                        validated=True,
                        validation_notes="Computed from transaction table rows",
                    )

        return enrichments

    def _enrich_paystub_from_tables(
        self,
        existing: Dict[str, StructuredField],
        tables: List[ExtractedTable],
    ) -> Dict[str, StructuredField]:
        """Extract earnings/deduction details from paystub tables."""
        enrichments: Dict[str, StructuredField] = {}

        earnings_tables = [t for t in tables if t.table_type == "earnings"]
        deduction_tables = [t for t in tables if t.table_type == "deduction"]

        # Map common table labels to field names
        earnings_field_map = {
            "regular": "regular_earnings",
            "overtime": "overtime_earnings",
            "bonus": "bonus",
            "commission": "commission",
        }

        deduction_field_map = {
            "federal": "federal_tax",
            "state": "state_tax",
            "social security": "social_security",
            "fica": "social_security",
            "medicare": "medicare",
            "401k": "retirement_401k",
            "retirement": "retirement_401k",
            "health": "health_insurance",
            "medical": "health_insurance",
        }

        for table in earnings_tables:
            for row in table.rows:
                row_text = " ".join(row).lower()
                for keyword, field_name in earnings_field_map.items():
                    if keyword in row_text and field_name not in existing and field_name not in enrichments:
                        amount = self._extract_amount_from_row(row)
                        if amount is not None:
                            enrichments[field_name] = StructuredField(
                                name=field_name,
                                value=amount,
                                raw_value=" | ".join(row),
                                confidence=table.confidence * 0.85,
                                page_number=table.page_number,
                                validated=True,
                                validation_notes="Extracted from earnings table",
                            )
                            break

        for table in deduction_tables:
            for row in table.rows:
                row_text = " ".join(row).lower()
                for keyword, field_name in deduction_field_map.items():
                    if keyword in row_text and field_name not in existing and field_name not in enrichments:
                        amount = self._extract_amount_from_row(row)
                        if amount is not None:
                            enrichments[field_name] = StructuredField(
                                name=field_name,
                                value=amount,
                                raw_value=" | ".join(row),
                                confidence=table.confidence * 0.85,
                                page_number=table.page_number,
                                validated=True,
                                validation_notes="Extracted from deduction table",
                            )
                            break

        return enrichments

    # -----------------------------------------------------------------
    # Utility methods
    # -----------------------------------------------------------------

    def _quick_text_sample(
        self, file_bytes: bytes, mime_type: Optional[str],
    ) -> str:
        """Get a quick text sample for language detection.

        Uses native PDF text or simple Tesseract for a fast sample,
        without full OCR processing.
        """
        if mime_type == "application/pdf" and HAS_PDFPLUMBER:
            try:
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    if pdf.pages:
                        text = pdf.pages[0].extract_text() or ""
                        return text[:2000]
            except Exception:
                pass

        if mime_type and mime_type.startswith("image/") and HAS_TESSERACT and HAS_PIL:
            try:
                image = Image.open(io.BytesIO(file_bytes))
                text = pytesseract.image_to_string(image)
                return text[:2000]
            except Exception:
                pass

        return ""

    @staticmethod
    def _extract_amount_from_row(row: List[str]) -> Optional[float]:
        """Extract the first currency amount from a table row."""
        currency_pattern = re.compile(
            r"\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
        )

        # Search from right to left (amounts are usually in rightmost columns)
        for cell in reversed(row):
            match = currency_pattern.search(cell)
            if match:
                try:
                    value = float(match.group(1).replace(",", ""))
                    if value > 0:
                        return value
                except ValueError:
                    continue

        return None

    @staticmethod
    def _extract_all_amounts_from_row(row: List[str]) -> List[float]:
        """Extract all currency amounts from a table row."""
        currency_pattern = re.compile(
            r"\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
        )
        amounts: List[float] = []

        for cell in row:
            for match in currency_pattern.finditer(cell):
                try:
                    value = float(match.group(1).replace(",", ""))
                    if value > 0:
                        amounts.append(value)
                except ValueError:
                    continue

        return amounts


# ============================================================================
# MODULE SINGLETON
# ============================================================================

_instances: Dict[int, OCREnhancementService] = {}


def get_ocr_enhancement_service(org_id: int) -> OCREnhancementService:
    """Get or create a per-org OCREnhancementService instance.

    Args:
        org_id: Organization ID for tenant-scoped operations.

    Returns:
        OCREnhancementService instance for the given org.
    """
    if org_id not in _instances:
        _instances[org_id] = OCREnhancementService(org_id=org_id)
    return _instances[org_id]
