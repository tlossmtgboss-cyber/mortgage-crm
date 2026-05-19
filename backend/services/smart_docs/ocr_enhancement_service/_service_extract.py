"""Auto-generated. See ocr_enhancement_service/__init__.py."""
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

# Optional dependency imports (graceful degradation)
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

# Pull all constants/enums/dataclasses (incl. DEFAULT_TARGET_DPI, MIN_TABLE_ROWS, etc.)
from ._types import *  # noqa: F401,F403

from ._spell import SpellCorrector
from ._tables import FinancialTableExtractor
from ._preprocess import AdvancedImagePreprocessor
from ._validation import FieldValidator
from ._handwriting import HandwritingDetector


class _ExtractMixin:

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
            except Exception as _exc:  # noqa: BLE001
                pass

        if mime_type and mime_type.startswith("image/") and HAS_TESSERACT and HAS_PIL:
            try:
                image = Image.open(io.BytesIO(file_bytes))
                text = pytesseract.image_to_string(image)
                return text[:2000]
            except Exception as _exc:  # noqa: BLE001
                pass

        return ""
