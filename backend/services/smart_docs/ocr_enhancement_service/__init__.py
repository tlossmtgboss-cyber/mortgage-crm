"""
Advanced OCR Enhancement Service for Smart Docs V2

Decomposed sub-package. Mixins (`_CacheMixin`, `_ExtractMixin`,
`_EnrichMixin`) compose the public :class:`OCREnhancementService`.
Helper classes (`SpellCorrector`, `FinancialTableExtractor`,
`AdvancedImagePreprocessor`, `FieldValidator`, `HandwritingDetector`)
and all types/enums/dataclasses are exposed for backward compatibility.

Usage:
    from services.smart_docs.ocr_enhancement_service import (
        OCREnhancementService,
        get_ocr_enhancement_service,
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
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

# Optional dependency imports (graceful degradation) — re-imported here so
# legacy code that did `from ocr_enhancement_service import HAS_PIL` keeps working.
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

# Re-export types and helper classes; star-import ensures module-level
# constants (DEFAULT_TARGET_DPI, MIN_TABLE_ROWS, CACHE_TYPE_OCR_ENHANCED, ...) are in scope.
from ._types import *  # noqa: F401,F403
from ._types import (
    ConfidenceLevel,
    DocumentLanguage,
    MortgageDocType,
    PreprocessingMetrics,
    TableCell,
    ExtractedTable,
    HandwritingDetection,
    StructuredField,
    PageEnhancedResult,
    StructuredExtractionResult,
    EnhancedOCRResult,
    BatchOCRResult,
    STRUCTURED_SCHEMAS,
)
from ._spell import SpellCorrector
from ._tables import FinancialTableExtractor
from ._preprocess import AdvancedImagePreprocessor
from ._validation import FieldValidator
from ._handwriting import HandwritingDetector
from ._service_cache import _CacheMixin
from ._service_extract import _ExtractMixin
from ._service_enrich import _EnrichMixin


# ============================================================================
# MAIN SERVICE
# ============================================================================

class OCREnhancementService(_CacheMixin, _ExtractMixin, _EnrichMixin):
    """Advanced OCR enhancement service for mortgage document processing.

    Orchestrates the full enhanced pipeline:
      1. Cache lookup
      2. Format detection and image pre-processing
      3. Multi-engine OCR with intelligent fallback
      4. Handwriting detection and specialized routing
      5. Post-processing: spell correction, field validation
      6. Table extraction
      7. Structured data extraction with confidence scoring
      8. Cache storage
      9. Confidence-tier classification (auto-accept / review / reject)
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

    # ------------------------------------------------------------------
    # Public processing entry points
    # ------------------------------------------------------------------

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


__all__ = [
    "OCREnhancementService",
    "get_ocr_enhancement_service",
    "SpellCorrector",
    "FinancialTableExtractor",
    "AdvancedImagePreprocessor",
    "FieldValidator",
    "HandwritingDetector",
    "ConfidenceLevel",
    "DocumentLanguage",
    "MortgageDocType",
    "PreprocessingMetrics",
    "TableCell",
    "ExtractedTable",
    "HandwritingDetection",
    "StructuredField",
    "PageEnhancedResult",
    "StructuredExtractionResult",
    "EnhancedOCRResult",
    "BatchOCRResult",
    "STRUCTURED_SCHEMAS",
]
