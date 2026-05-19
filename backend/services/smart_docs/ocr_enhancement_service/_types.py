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
