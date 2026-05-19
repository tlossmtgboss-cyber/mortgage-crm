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


class _CacheMixin:

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
