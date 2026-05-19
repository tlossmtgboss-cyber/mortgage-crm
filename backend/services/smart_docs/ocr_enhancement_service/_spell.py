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


# SpellCorrector

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
