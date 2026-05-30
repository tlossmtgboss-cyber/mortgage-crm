"""
Document OCR & Text Extraction Service

Comprehensive OCR pipeline for mortgage document processing. Provides
multi-format text extraction (PDF, images), mortgage-specific field parsing,
data normalization, confidence scoring, and image pre-processing.

Architecture:
    Uses an abstract OCREngine interface so the underlying OCR provider
    (Tesseract, Claude Vision, etc.) can be swapped without changing
    calling code.  A composite engine chains multiple providers and
    picks the highest-confidence result.

Integration points:
    - Claude Vision API  (primary for complex / handwritten docs)
    - Tesseract OCR      (local fallback for simple docs / privacy mode)
    - document_data_extractor.py  (downstream structured extraction)
    - ai_classifier_service.py    (upstream classification)

Usage:
    from services.smart_docs.document_ocr_service import (
        get_document_ocr_service,
        DocumentOCRService,
    )

    service = get_document_ocr_service()
    result = service.extract_text(file_bytes, "application/pdf")
    fields = service.extract_mortgage_fields(result, "paystub")
"""

from __future__ import annotations

import abc
import base64
import io
import logging
import math
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
    Protocol,
    Sequence,
    Tuple,
    Type,
    Union,
)

from middleware.upload_limits import (
    MAX_VISION_API_SIZE,
    MAX_IMAGE_DIMENSIONS,
    MAX_OCR_OUTPUT_CHARS,
    MAX_PDF_PAGES,
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

from services.smart_docs.ai_resilience import resilient_ai_call


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class DocumentFormat(str, Enum):
    """Supported input document formats."""
    PDF = "pdf"
    JPEG = "jpeg"
    PNG = "png"
    TIFF = "tiff"
    BMP = "bmp"
    WEBP = "webp"
    UNKNOWN = "unknown"


class OCRQuality(str, Enum):
    """Overall quality grade for an OCR extraction."""
    EXCELLENT = "excellent"   # >90% confidence
    GOOD = "good"             # 70-90%
    FAIR = "fair"             # 50-70%
    POOR = "poor"             # <50%


MIME_TO_FORMAT = {
    "application/pdf": DocumentFormat.PDF,
    "image/jpeg": DocumentFormat.JPEG,
    "image/jpg": DocumentFormat.JPEG,
    "image/png": DocumentFormat.PNG,
    "image/tiff": DocumentFormat.TIFF,
    "image/bmp": DocumentFormat.BMP,
    "image/webp": DocumentFormat.WEBP,
}

IMAGE_FORMATS = {
    DocumentFormat.JPEG,
    DocumentFormat.PNG,
    DocumentFormat.TIFF,
    DocumentFormat.BMP,
    DocumentFormat.WEBP,
}

# Minimum DPI for acceptable OCR quality
MIN_DPI = 200
TARGET_DPI = 300

# US state abbreviations for address normalization
STATE_ABBREVIATIONS: Dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}

# Street suffix normalization
STREET_SUFFIX_MAP: Dict[str, str] = {
    "avenue": "Ave", "ave": "Ave", "av": "Ave",
    "boulevard": "Blvd", "blvd": "Blvd",
    "circle": "Cir", "cir": "Cir",
    "court": "Ct", "ct": "Ct",
    "drive": "Dr", "dr": "Dr",
    "highway": "Hwy", "hwy": "Hwy",
    "lane": "Ln", "ln": "Ln",
    "parkway": "Pkwy", "pkwy": "Pkwy",
    "place": "Pl", "pl": "Pl",
    "road": "Rd", "rd": "Rd",
    "street": "St", "st": "St",
    "terrace": "Ter", "ter": "Ter",
    "trail": "Trl", "trl": "Trl",
    "way": "Way",
}


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class PageOCRResult:
    """OCR result for a single page."""
    page_number: int
    text: str
    confidence: float  # 0.0 - 1.0
    word_confidences: List[float] = field(default_factory=list)
    has_tables: bool = False
    has_handwriting: bool = False
    tables: List[Dict[str, Any]] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    dpi: int = 0
    engine_used: str = ""
    processing_ms: int = 0


@dataclass
class OCRExtractionResult:
    """Complete OCR extraction result across all pages."""
    success: bool
    full_text: str
    pages: List[PageOCRResult] = field(default_factory=list)
    page_count: int = 0
    overall_confidence: float = 0.0
    quality_grade: OCRQuality = OCRQuality.POOR
    document_format: DocumentFormat = DocumentFormat.UNKNOWN
    has_native_text: bool = False
    has_handwriting: bool = False
    has_tables: bool = False
    needs_manual_review: bool = False
    review_reasons: List[str] = field(default_factory=list)
    engine_used: str = ""
    total_processing_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "success": self.success,
            "full_text": self.full_text[:5000] if self.full_text else "",
            "page_count": self.page_count,
            "overall_confidence": round(self.overall_confidence, 3),
            "quality_grade": self.quality_grade.value,
            "document_format": self.document_format.value,
            "has_native_text": self.has_native_text,
            "has_handwriting": self.has_handwriting,
            "has_tables": self.has_tables,
            "needs_manual_review": self.needs_manual_review,
            "review_reasons": self.review_reasons,
            "engine_used": self.engine_used,
            "total_processing_ms": self.total_processing_ms,
            "error": self.error,
        }


@dataclass
class ExtractedField:
    """A single extracted field with confidence and provenance."""
    name: str
    value: Any
    raw_value: str  # original OCR text before normalization
    confidence: float  # 0.0 - 1.0
    source_text: str = ""  # surrounding context
    page_number: int = 0
    needs_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "raw_value": self.raw_value,
            "confidence": round(self.confidence, 3),
            "page_number": self.page_number,
            "needs_review": self.needs_review,
        }


@dataclass
class MortgageFieldExtractionResult:
    """Result of mortgage-specific field extraction."""
    success: bool
    document_type: str
    fields: Dict[str, ExtractedField] = field(default_factory=dict)
    overall_confidence: float = 0.0
    missing_required: List[str] = field(default_factory=list)
    needs_manual_review: bool = False
    review_reasons: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "document_type": self.document_type,
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "overall_confidence": round(self.overall_confidence, 3),
            "missing_required": self.missing_required,
            "needs_manual_review": self.needs_manual_review,
            "review_reasons": self.review_reasons,
            "error": self.error,
        }


# ============================================================================
# ABSTRACT OCR ENGINE
# ============================================================================

class OCREngine(abc.ABC):
    """Abstract base class for OCR engine implementations.

    Subclass this to integrate a new OCR provider. The composite engine
    will iterate registered engines and use the highest-confidence result.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable engine name."""
        ...

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Return True if this engine's dependencies are installed and configured."""
        ...

    @abc.abstractmethod
    def extract_from_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        language: str = "eng",
    ) -> PageOCRResult:
        """Extract text from a single image.

        Args:
            image_bytes: Raw image bytes.
            mime_type: MIME type of the image.
            language: ISO 639-3 language code for OCR.

        Returns:
            PageOCRResult with extracted text and confidence.
        """
        ...

    def extract_tables(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """Extract tables from an image. Override in subclasses that support it."""
        return []

    def detect_handwriting(self, image_bytes: bytes) -> Tuple[bool, float]:
        """Detect handwriting presence. Returns (has_handwriting, confidence).

        Override in subclasses with handwriting detection capability.
        """
        return False, 0.0


# ============================================================================
# TESSERACT OCR ENGINE
# ============================================================================

class TesseractOCREngine(OCREngine):
    """OCR engine backed by Tesseract via pytesseract.

    Best for clean, machine-printed documents. Fast and runs locally
    without API calls, making it suitable for privacy-sensitive documents.
    """

    @property
    def name(self) -> str:
        return "tesseract"

    def is_available(self) -> bool:
        return HAS_TESSERACT and HAS_PIL

    def extract_from_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        language: str = "eng",
    ) -> PageOCRResult:
        """Extract text from image using Tesseract."""
        if not self.is_available():
            return PageOCRResult(
                page_number=0, text="", confidence=0.0,
                engine_used=self.name,
            )

        start = time.monotonic()
        try:
            image = Image.open(io.BytesIO(image_bytes))
            width, height = image.size

            # Get detailed OCR data with per-word confidence
            ocr_data = pytesseract.image_to_data(
                image, lang=language, output_type=pytesseract.Output.DICT,
            )

            # Build full text from words
            words: List[str] = []
            word_confs: List[float] = []
            current_block = -1
            current_line = -1

            for i, word in enumerate(ocr_data["text"]):
                stripped = word.strip()
                if not stripped:
                    continue
                conf = int(ocr_data["conf"][i])
                if conf < 0:
                    continue

                block = ocr_data["block_num"][i]
                line = ocr_data["line_num"][i]

                if block != current_block and current_block != -1:
                    words.append("\n\n")
                elif line != current_line and current_line != -1:
                    words.append("\n")

                current_block = block
                current_line = line
                words.append(stripped)
                word_confs.append(conf / 100.0)

            text = " ".join(w for w in words if w.strip())
            # Clean up multiple newlines
            text = re.sub(r"\n{3,}", "\n\n", text)

            avg_conf = statistics.mean(word_confs) if word_confs else 0.0

            elapsed = int((time.monotonic() - start) * 1000)

            return PageOCRResult(
                page_number=0,
                text=text,
                confidence=avg_conf,
                word_confidences=word_confs,
                image_width=width,
                image_height=height,
                engine_used=self.name,
                processing_ms=elapsed,
            )

        except Exception as e:
            logger.exception("Tesseract OCR failed")
            elapsed = int((time.monotonic() - start) * 1000)
            return PageOCRResult(
                page_number=0, text="", confidence=0.0,
                engine_used=self.name, processing_ms=elapsed,
            )

    def extract_tables(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """Basic table extraction using Tesseract TSV output."""
        if not self.is_available():
            return []

        try:
            image = Image.open(io.BytesIO(image_bytes))
            tsv_data = pytesseract.image_to_data(
                image, output_type=pytesseract.Output.DICT,
            )

            # Group words by block and line to detect table structures
            blocks: Dict[int, Dict[int, List[str]]] = {}
            for i, word in enumerate(tsv_data["text"]):
                stripped = word.strip()
                if not stripped or int(tsv_data["conf"][i]) < 0:
                    continue
                block = tsv_data["block_num"][i]
                line = tsv_data["line_num"][i]
                blocks.setdefault(block, {}).setdefault(line, []).append(stripped)

            tables = []
            for block_num, lines in blocks.items():
                if len(lines) < 3:
                    continue
                # Heuristic: if most lines have similar word counts, it may be a table
                word_counts = [len(words) for words in lines.values()]
                if not word_counts:
                    continue
                median_count = statistics.median(word_counts)
                if median_count >= 2:
                    consistent = sum(
                        1 for c in word_counts
                        if abs(c - median_count) <= 1
                    )
                    if consistent / len(word_counts) >= 0.6:
                        rows = [
                            " | ".join(words)
                            for _, words in sorted(lines.items())
                        ]
                        tables.append({
                            "block": block_num,
                            "rows": rows,
                            "row_count": len(rows),
                            "detected_columns": int(median_count),
                        })

            return tables
        except Exception as e:
            logger.warning("Tesseract table extraction failed: %s", e)
            return []


# ============================================================================
# CLAUDE VISION OCR ENGINE
# ============================================================================

class ClaudeVisionOCREngine(OCREngine):
    """OCR engine using Anthropic Claude Vision API.

    Best for complex documents, handwritten content, and documents requiring
    contextual understanding. Requires an ANTHROPIC_API_KEY environment
    variable or explicit client injection.
    """

    def __init__(self, client: Optional[Any] = None):
        self._client = client

    def _get_client(self) -> Optional[Any]:
        """Get or create Anthropic client."""
        if self._client is not None:
            return self._client
        if not HAS_ANTHROPIC:
            return None
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        try:
            self._client = Anthropic(api_key=api_key)
            return self._client
        except Exception as e:
            logger.warning("Failed to create Anthropic client: %s", e)
            return None

    @property
    def name(self) -> str:
        return "claude_vision"

    def is_available(self) -> bool:
        return self._get_client() is not None

    def extract_from_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        language: str = "eng",
    ) -> PageOCRResult:
        """Extract text from image using Claude Vision."""
        client = self._get_client()
        if client is None:
            return PageOCRResult(
                page_number=0, text="", confidence=0.0,
                engine_used=self.name,
            )

        # --- File size check for Vision API ---
        if len(image_bytes) > MAX_VISION_API_SIZE:
            size_mb = len(image_bytes) / (1024 * 1024)
            limit_mb = MAX_VISION_API_SIZE / (1024 * 1024)
            logger.warning(
                "Image too large for Vision API (%.1f MB > %.0f MB limit), skipping",
                size_mb, limit_mb,
            )
            return PageOCRResult(
                page_number=0,
                text="",
                confidence=0.0,
                engine_used=self.name,
            )

        # --- Image dimension check before processing ---
        max_w, max_h = MAX_IMAGE_DIMENSIONS
        try:
            if HAS_PIL:
                img = Image.open(io.BytesIO(image_bytes))
                w, h = img.size
                img.close()
                if w > max_w or h > max_h:
                    logger.warning(
                        "Image dimensions %dx%d exceed limit %dx%d, skipping Vision API",
                        w, h, max_w, max_h,
                    )
                    return PageOCRResult(
                        page_number=0, text="", confidence=0.0,
                        engine_used=self.name,
                    )
        except Exception:
            pass  # If we cannot check, proceed anyway

        start = time.monotonic()
        try:
            b64_image = base64.b64encode(image_bytes).decode("utf-8")

            # Ensure valid media type for the API
            media_type = mime_type
            if media_type not in (
                "image/jpeg", "image/png", "image/gif", "image/webp",
            ):
                media_type = "image/png"

            response = resilient_ai_call(
                client=client,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Extract ALL text from this document image. "
                                "Preserve the layout as closely as possible. "
                                "For tables, use pipe-delimited format. "
                                "For handwritten text, prefix with [HANDWRITTEN]. "
                                "Include every visible character — do not summarize. "
                                "Output only the extracted text, no commentary."
                            ),
                        },
                    ],
                }],
                model="claude-sonnet-4-6",
                max_tokens=4096,
                operation_name="ocr_extract_text",
                timeout=45.0,
            )

            if response is None:
                # AI OCR failed -- fall back to empty result (Tesseract fallback
                # is handled by the composite engine layer above this engine)
                logger.warning(
                    "Claude Vision OCR unavailable after retries, returning empty result"
                )
                elapsed = int((time.monotonic() - start) * 1000)
                return PageOCRResult(
                    page_number=0, text="", confidence=0.0,
                    engine_used=self.name, processing_ms=elapsed,
                )

            text = response.content[0].text if response.content else ""
            has_handwriting = "[HANDWRITTEN]" in text
            has_tables = "|" in text and text.count("|") >= 4

            # Claude Vision gives high-quality results; assign high base
            # confidence, reduced if handwriting detected
            base_confidence = 0.92 if not has_handwriting else 0.75

            elapsed = int((time.monotonic() - start) * 1000)

            logger.info(
                "OCR extraction completed | engine=%s | "
                "duration_ms=%d | text_length=%d | "
                "has_handwriting=%s | has_tables=%s",
                self.name,
                elapsed,
                len(text),
                has_handwriting,
                has_tables,
            )

            return PageOCRResult(
                page_number=0,
                text=text,
                confidence=base_confidence,
                has_tables=has_tables,
                has_handwriting=has_handwriting,
                engine_used=self.name,
                processing_ms=elapsed,
            )

        except Exception as e:
            logger.exception("Claude Vision OCR failed")
            elapsed = int((time.monotonic() - start) * 1000)
            return PageOCRResult(
                page_number=0, text="", confidence=0.0,
                engine_used=self.name, processing_ms=elapsed,
            )

    def detect_handwriting(self, image_bytes: bytes) -> Tuple[bool, float]:
        """Use Claude Vision to detect handwriting presence."""
        client = self._get_client()
        if client is None:
            return False, 0.0

        # Skip if image is too large for the Vision API
        if len(image_bytes) > MAX_VISION_API_SIZE:
            logger.debug("Image too large for handwriting detection, skipping")
            return False, 0.0

        try:
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
                                "Does this document contain handwriting? "
                                "Reply only: YES <confidence 0-100> or NO <confidence 0-100>"
                            ),
                        },
                    ],
                }],
                model="claude-sonnet-4-6",
                max_tokens=100,
                operation_name="ocr_detect_handwriting",
                timeout=15.0,
            )

            if response is None:
                logger.warning("Handwriting detection unavailable after retries")
                return False, 0.0

            answer = response.content[0].text.strip().upper() if response.content else ""
            if answer.startswith("YES"):
                conf_match = re.search(r"(\d+)", answer)
                conf = int(conf_match.group(1)) / 100.0 if conf_match else 0.8
                return True, conf
            return False, 0.9
        except Exception as e:
            logger.warning("Handwriting detection failed: %s", e)
            return False, 0.0


# ============================================================================
# IMAGE PRE-PROCESSING PIPELINE
# ============================================================================

class ImagePreprocessor:
    """Pre-processing pipeline for improving OCR quality on scanned documents.

    Applies deskewing, contrast enhancement, noise removal, and resolution
    upscaling as needed.  All methods are no-ops when PIL is unavailable.
    """

    @staticmethod
    def preprocess(
        image_bytes: bytes,
        target_dpi: int = TARGET_DPI,
        deskew: bool = True,
        enhance_contrast: bool = True,
        remove_noise: bool = True,
        upscale: bool = True,
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Run the full pre-processing pipeline on an image.

        Args:
            image_bytes: Raw image bytes.
            target_dpi: Target DPI for upscaling.
            deskew: Whether to attempt deskew correction.
            enhance_contrast: Whether to enhance contrast.
            remove_noise: Whether to apply noise removal.
            upscale: Whether to upscale low-resolution images.

        Returns:
            Tuple of (processed_image_bytes, metadata_dict).
        """
        if not HAS_PIL:
            return image_bytes, {"preprocessed": False, "reason": "PIL not available"}

        metadata: Dict[str, Any] = {"preprocessed": True, "steps": []}

        try:
            image = Image.open(io.BytesIO(image_bytes))
            original_size = image.size

            # Step 1: Convert to grayscale for OCR
            if image.mode not in ("L", "1"):
                image = image.convert("L")
                metadata["steps"].append("grayscale_conversion")

            # Step 2: Upscale low-DPI images
            if upscale:
                image, did_upscale = ImagePreprocessor._upscale_if_needed(
                    image, target_dpi,
                )
                if did_upscale:
                    metadata["steps"].append(
                        f"upscaled_to_{target_dpi}dpi"
                    )

            # Step 3: Deskew
            if deskew:
                image, angle = ImagePreprocessor._deskew(image)
                if abs(angle) > 0.5:
                    metadata["steps"].append(f"deskewed_{angle:.1f}_degrees")

            # Step 4: Contrast enhancement
            if enhance_contrast:
                image = ImagePreprocessor._enhance_contrast(image)
                metadata["steps"].append("contrast_enhanced")

            # Step 5: Noise removal
            if remove_noise:
                image = ImagePreprocessor._remove_noise(image)
                metadata["steps"].append("noise_removed")

            metadata["original_size"] = original_size
            metadata["processed_size"] = image.size

            buf = io.BytesIO()
            image.save(buf, format="PNG")
            return buf.getvalue(), metadata

        except Exception as e:
            logger.warning("Image preprocessing failed: %s", e)
            return image_bytes, {"preprocessed": False, "error": str(e)}

    @staticmethod
    def _upscale_if_needed(
        image: "Image.Image", target_dpi: int,
    ) -> Tuple["Image.Image", bool]:
        """Upscale image if resolution is below target DPI.

        Uses the image DPI metadata if available; otherwise estimates
        from pixel dimensions (assumes standard letter/A4 page).
        """
        dpi_info = image.info.get("dpi", (0, 0))
        current_dpi = max(dpi_info) if isinstance(dpi_info, (tuple, list)) else 0

        if current_dpi == 0:
            # Estimate: assume 8.5x11 page -> width ~2550px at 300dpi
            width = image.size[0]
            current_dpi = int(width / 8.5) if width > 0 else 72

        if current_dpi >= target_dpi:
            return image, False

        scale = target_dpi / max(current_dpi, 1)
        if scale > 4.0:
            scale = 4.0  # cap at 4x to avoid memory issues

        new_size = (int(image.size[0] * scale), int(image.size[1] * scale))
        image = image.resize(new_size, Image.LANCZOS)
        return image, True

    @staticmethod
    def _deskew(image: "Image.Image") -> Tuple["Image.Image", float]:
        """Detect and correct document skew.

        Uses a projection-profile approach: rotates the image in small
        increments and picks the angle that maximizes horizontal line
        variance (indicating text rows are aligned).
        """
        try:
            # Binarize for analysis
            threshold = 128
            binary = image.point(lambda p: 255 if p > threshold else 0)

            import numpy as np
            arr = np.array(binary)

            best_angle = 0.0
            best_variance = 0.0

            for angle_tenths in range(-50, 51, 5):  # -5.0 to +5.0 degrees
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

            if abs(best_angle) > 0.5:
                image = image.rotate(
                    best_angle, resample=Image.BICUBIC, expand=True,
                    fillcolor=255,
                )

            return image, best_angle

        except ImportError:
            # numpy not available; skip deskew
            return image, 0.0
        except Exception as e:
            logger.debug("Deskew failed (non-critical): %s", e)
            return image, 0.0

    @staticmethod
    def _enhance_contrast(image: "Image.Image") -> "Image.Image":
        """Enhance contrast using adaptive histogram equalization."""
        try:
            # Auto-contrast first
            image = ImageOps.autocontrast(image, cutoff=1)

            # Then sharpen slightly
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.5)

            return image
        except Exception as e:
            logger.debug("Contrast enhancement failed (non-critical): %s", e)
            return image

    @staticmethod
    def _remove_noise(image: "Image.Image") -> "Image.Image":
        """Remove noise using median filter (preserves edges better than Gaussian)."""
        try:
            return image.filter(ImageFilter.MedianFilter(size=3))
        except Exception as e:
            logger.debug("Noise removal failed (non-critical): %s", e)
            return image

    @staticmethod
    def detect_rotation(image_bytes: bytes) -> int:
        """Detect if the document needs 90/180/270 degree rotation.

        Returns the clockwise rotation angle needed (0, 90, 180, 270).
        Uses Tesseract OSD (Orientation and Script Detection) when available.
        """
        if not HAS_TESSERACT or not HAS_PIL:
            return 0

        try:
            image = Image.open(io.BytesIO(image_bytes))
            osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
            rotation = osd.get("rotate", 0)
            return int(rotation) if rotation in (0, 90, 180, 270) else 0
        except Exception as e:
            logger.debug("Rotation detection failed (non-critical): %s", e)
            return 0


# ============================================================================
# DATA NORMALIZATION UTILITIES
# ============================================================================

class DataNormalizer:
    """Normalizes raw OCR text into structured data types.

    Handles currency, dates, names, addresses, SSNs, and phone numbers
    with mortgage-industry-specific formatting rules.
    """

    # Currency patterns: $1,234.56 | 1234.56 | $1234 | 1,234
    _CURRENCY_PATTERN = re.compile(
        r"\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
    )

    # Date patterns (order matters: most specific first)
    _DATE_PATTERNS: List[Tuple[str, str]] = [
        # ISO: 2024-01-15
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", "%Y-%m-%d"),
        # US long: January 15, 2024
        (r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})", "month_name_long"),
        # US short: Jan 15, 2024
        (r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[.]?\s+(\d{1,2}),?\s+(\d{4})", "month_name_short"),
        # MM/DD/YYYY or MM-DD-YYYY
        (r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", "%m/%d/%Y"),
        # MM/DD/YY
        (r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})", "%m/%d/%y"),
    ]

    _MONTH_MAP: Dict[str, int] = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9,
        "oct": 10, "nov": 11, "dec": 12,
    }

    # SSN pattern: NNN-NN-NNNN or NNNNNNNNN
    _SSN_PATTERN = re.compile(r"(\d{3})-?(\d{2})-?(\d{4})")

    # Phone pattern: various US formats
    _PHONE_PATTERN = re.compile(
        r"(?:\+?1[-.\s]?)?\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})"
    )

    @classmethod
    def parse_currency(cls, text: str) -> Optional[Decimal]:
        """Parse a currency string into a Decimal value.

        Handles: $1,234.56, 1234.56, $1234, (1,234.56) for negatives.

        Returns:
            Decimal value or None if unparseable.
        """
        if not text:
            return None

        cleaned = text.strip()

        # Handle parentheses for negative values
        is_negative = cleaned.startswith("(") and cleaned.endswith(")")
        if is_negative:
            cleaned = cleaned[1:-1]

        # Handle negative sign
        if cleaned.startswith("-"):
            is_negative = True
            cleaned = cleaned[1:]

        match = cls._CURRENCY_PATTERN.search(cleaned)
        if not match:
            return None

        try:
            raw = match.group(1).replace(",", "")
            value = Decimal(raw)
            return -value if is_negative else value
        except (InvalidOperation, ValueError):
            return None

    @classmethod
    def parse_date(cls, text: str) -> Optional[date]:
        """Parse a date string into a date object.

        Supports: MM/DD/YYYY, YYYY-MM-DD, Month DD YYYY, Mon DD YYYY,
                  MM-DD-YYYY, MM/DD/YY.

        Returns:
            date object or None if unparseable.
        """
        if not text:
            return None

        cleaned = text.strip()

        for pattern, fmt in cls._DATE_PATTERNS:
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if not match:
                continue

            try:
                if fmt == "month_name_long" or fmt == "month_name_short":
                    month_str = match.group(1).lower().rstrip(".")
                    month = cls._MONTH_MAP.get(month_str)
                    if month is None:
                        continue
                    day = int(match.group(2))
                    year = int(match.group(3))
                    return date(year, month, day)
                elif fmt == "%m/%d/%y":
                    m, d, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    # 2-digit year: 00-49 -> 2000s, 50-99 -> 1900s
                    year = 2000 + y if y < 50 else 1900 + y
                    return date(year, m, d)
                elif fmt == "%Y-%m-%d":
                    return date(
                        int(match.group(1)),
                        int(match.group(2)),
                        int(match.group(3)),
                    )
                else:
                    # MM/DD/YYYY or MM-DD-YYYY
                    return date(
                        int(match.group(3)),
                        int(match.group(1)),
                        int(match.group(2)),
                    )
            except (ValueError, OverflowError):
                continue

        return None

    @classmethod
    def normalize_name(cls, text: str) -> str:
        """Normalize a person's name to 'First Last' format.

        Handles:
            - LAST, FIRST MIDDLE -> First Middle Last
            - ALL CAPS -> Title Case
            - Extra whitespace cleanup
        """
        if not text:
            return ""

        cleaned = text.strip()

        # Handle "LAST, FIRST" or "LAST, FIRST MIDDLE"
        if "," in cleaned:
            parts = cleaned.split(",", 1)
            last = parts[0].strip()
            first_middle = parts[1].strip() if len(parts) > 1 else ""
            cleaned = f"{first_middle} {last}".strip()

        # Title case if all caps
        if cleaned == cleaned.upper() and len(cleaned) > 1:
            cleaned = cleaned.title()

        # Collapse whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned

    @classmethod
    def normalize_address(cls, text: str) -> str:
        """Normalize a US street address.

        Applies standard abbreviations for street suffixes, directional
        prefixes, and unit designators.
        """
        if not text:
            return ""

        cleaned = text.strip()

        # Title case if all caps
        if cleaned == cleaned.upper() and len(cleaned) > 3:
            cleaned = cleaned.title()

        # Normalize street suffixes
        words = cleaned.split()
        normalized_words = []
        for word in words:
            lower = word.lower().rstrip(".,")
            if lower in STREET_SUFFIX_MAP:
                normalized_words.append(STREET_SUFFIX_MAP[lower])
            else:
                normalized_words.append(word)

        # Normalize directional abbreviations
        directional = {"north": "N", "south": "S", "east": "E", "west": "W",
                       "northeast": "NE", "northwest": "NW",
                       "southeast": "SE", "southwest": "SW"}
        final_words = []
        for word in normalized_words:
            lower = word.lower()
            if lower in directional:
                final_words.append(directional[lower])
            else:
                final_words.append(word)

        return " ".join(final_words)

    @classmethod
    def mask_ssn(cls, text: str) -> str:
        """Mask SSN to only show last 4 digits.

        Input:  '123-45-6789' or '123456789'
        Output: '***-**-6789'
        """
        if not text:
            return ""

        match = cls._SSN_PATTERN.search(text.strip())
        if not match:
            return ""

        return f"***-**-{match.group(3)}"

    @classmethod
    def extract_ssn_last4(cls, text: str) -> str:
        """Extract just the last 4 digits of an SSN."""
        if not text:
            return ""

        match = cls._SSN_PATTERN.search(text.strip())
        if not match:
            # Try just 4 digits
            four_digit = re.search(r"\b(\d{4})\b", text)
            return four_digit.group(1) if four_digit else ""

        return match.group(3)

    @classmethod
    def normalize_phone(cls, text: str) -> str:
        """Normalize US phone number to (NNN) NNN-NNNN format."""
        if not text:
            return ""

        match = cls._PHONE_PATTERN.search(text.strip())
        if not match:
            return ""

        return f"({match.group(1)}) {match.group(2)}-{match.group(3)}"

    @classmethod
    def normalize_state(cls, text: str) -> str:
        """Normalize state name/abbreviation to 2-letter code."""
        if not text:
            return ""

        cleaned = text.strip()

        # Already a 2-letter code
        if len(cleaned) == 2 and cleaned.upper() in STATE_ABBREVIATIONS.values():
            return cleaned.upper()

        # Full name lookup
        lower = cleaned.lower()
        if lower in STATE_ABBREVIATIONS:
            return STATE_ABBREVIATIONS[lower]

        return cleaned.upper()[:2] if len(cleaned) >= 2 else cleaned.upper()


# ============================================================================
# MORTGAGE FIELD EXTRACTION PATTERNS
# ============================================================================

# Regex patterns for extracting specific mortgage document fields.
# Each pattern maps a field name to one or more regex patterns and the
# expected data type for normalization.

PAYSTUB_PATTERNS: Dict[str, Dict[str, Any]] = {
    "employer_name": {
        "patterns": [
            r"(?:employer|company|employer name)[:\s]+(.+?)(?:\n|$)",
            r"^(.+?)\n.*(?:pay\s*(?:stub|slip|statement))",
        ],
        "type": "string",
        "required": True,
    },
    "employee_name": {
        "patterns": [
            r"(?:employee|employee name|name)[:\s]+(.+?)(?:\n|$)",
            r"(?:pay to|payee)[:\s]+(.+?)(?:\n|$)",
        ],
        "type": "name",
        "required": True,
    },
    "pay_period_start": {
        "patterns": [
            r"(?:period\s*(?:begin|start|from))[:\s]+(.+?)(?:\s+(?:to|through|-)|\n|$)",
            r"(?:from|begin)[:\s]+(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        ],
        "type": "date",
        "required": False,
    },
    "pay_period_end": {
        "patterns": [
            r"(?:period\s*(?:end|ending|to|through))[:\s]+(.+?)(?:\n|$)",
            r"(?:to|through|ending)[:\s]+(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        ],
        "type": "date",
        "required": False,
    },
    "pay_date": {
        "patterns": [
            r"(?:pay\s*date|check\s*date|date\s*paid)[:\s]+(.+?)(?:\n|$)",
        ],
        "type": "date",
        "required": True,
    },
    "gross_pay": {
        "patterns": [
            r"(?:gross\s*pay|gross\s*earnings|total\s*gross)[:\s]*\$?([\d,]+\.?\d*)",
            r"(?:gross)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": True,
    },
    "net_pay": {
        "patterns": [
            r"(?:net\s*pay|take\s*home|net\s*earnings|total\s*net)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": True,
    },
    "ytd_gross": {
        "patterns": [
            r"(?:ytd|year[\s-]*to[\s-]*date).*?(?:gross|total)[:\s]*\$?([\d,]+\.?\d*)",
            r"(?:gross|total).*?(?:ytd|year[\s-]*to[\s-]*date)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "hourly_rate": {
        "patterns": [
            r"(?:rate|hourly\s*rate|pay\s*rate)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "hours_worked": {
        "patterns": [
            r"(?:hours|regular\s*hours|hrs)[:\s]*([\d.]+)",
        ],
        "type": "number",
        "required": False,
    },
    "federal_tax": {
        "patterns": [
            r"(?:federal|fed|fit|federal\s*(?:tax|w/?h|withholding))[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "state_tax": {
        "patterns": [
            r"(?:state|sit|state\s*(?:tax|w/?h|withholding))[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "social_security": {
        "patterns": [
            r"(?:social\s*security|fica|ss|oasdi)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "medicare": {
        "patterns": [
            r"(?:medicare|med\s*tax)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "retirement_401k": {
        "patterns": [
            r"(?:401\s*k|retirement|pension|rsp)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
}

W2_PATTERNS: Dict[str, Dict[str, Any]] = {
    "employer_name": {
        "patterns": [r"(?:employer.?s?\s*name|box\s*c)[:\s]+(.+?)(?:\n|$)"],
        "type": "string",
        "required": True,
    },
    "employer_ein": {
        "patterns": [
            r"(?:employer.?s?\s*(?:identification|id|ein)|box\s*b)[:\s]*(\d{2}-?\d{7})",
        ],
        "type": "string",
        "required": True,
    },
    "employee_name": {
        "patterns": [r"(?:employee.?s?\s*name|box\s*e)[:\s]+(.+?)(?:\n|$)"],
        "type": "name",
        "required": True,
    },
    "employee_ssn_last4": {
        "patterns": [
            r"(?:employee.?s?\s*(?:social|ssn|ss\s*#)|box\s*a)[:\s]*[\dX*]{3}-?[\dX*]{2}-?(\d{4})",
            r"(?:ssn|social\s*security)[:\s]*.*?(\d{4})\s*$",
        ],
        "type": "ssn",
        "required": True,
    },
    "wages_tips_compensation": {
        "patterns": [
            r"(?:wages.*?tips.*?compensation|box\s*1\b)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": True,
    },
    "federal_tax_withheld": {
        "patterns": [
            r"(?:federal.*?tax.*?withheld|box\s*2\b)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": True,
    },
    "social_security_wages": {
        "patterns": [
            r"(?:social\s*security\s*wages|box\s*3\b)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "social_security_tax": {
        "patterns": [
            r"(?:social\s*security\s*tax|box\s*4\b)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "medicare_wages": {
        "patterns": [
            r"(?:medicare\s*wages|box\s*5\b)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "medicare_tax": {
        "patterns": [
            r"(?:medicare\s*tax|box\s*6\b)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "tax_year": {
        "patterns": [
            r"(?:tax\s*year|for\s*(?:the\s*)?year)[:\s]*(\d{4})",
            r"\b(20[12]\d)\b",
        ],
        "type": "integer",
        "required": True,
    },
    "state": {
        "patterns": [
            r"(?:state\b|box\s*15)[:\s]*([A-Z]{2})",
        ],
        "type": "state",
        "required": False,
    },
    "state_wages": {
        "patterns": [
            r"(?:state\s*wages|box\s*16\b)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "state_tax_withheld": {
        "patterns": [
            r"(?:state.*?tax.*?withheld|box\s*17\b)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
}

BANK_STATEMENT_PATTERNS: Dict[str, Dict[str, Any]] = {
    "institution_name": {
        "patterns": [
            r"^(.+?(?:bank|credit\s*union|financial|fcu|savings))",
        ],
        "type": "string",
        "required": True,
    },
    "account_holder_name": {
        "patterns": [
            r"(?:account\s*holder|account\s*name|primary\s*owner)[:\s]+(.+?)(?:\n|$)",
        ],
        "type": "name",
        "required": True,
    },
    "account_number_last4": {
        "patterns": [
            r"(?:account\s*(?:number|#|no))[:\s]*(?:[\dXx*]+[-\s])?(\d{4})\b",
        ],
        "type": "string",
        "required": True,
    },
    "statement_start": {
        "patterns": [
            r"(?:statement\s*period|period)[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s*(?:to|through|-)",
        ],
        "type": "date",
        "required": False,
    },
    "statement_end": {
        "patterns": [
            r"(?:to|through|-)\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
            r"(?:statement\s*(?:date|ending))[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
        ],
        "type": "date",
        "required": True,
    },
    "beginning_balance": {
        "patterns": [
            r"(?:beginning|opening|previous)\s*balance[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": True,
    },
    "ending_balance": {
        "patterns": [
            r"(?:ending|closing|current)\s*balance[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": True,
    },
    "total_deposits": {
        "patterns": [
            r"(?:total\s*deposits|deposits\s*total|total\s*credits)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "total_withdrawals": {
        "patterns": [
            r"(?:total\s*withdrawals|withdrawals\s*total|total\s*debits)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
}

TAX_RETURN_PATTERNS: Dict[str, Dict[str, Any]] = {
    "taxpayer_name": {
        "patterns": [
            r"(?:your\s*first\s*name.*?last\s*name|name\s*on\s*return)[:\s]+(.+?)(?:\n|$)",
        ],
        "type": "name",
        "required": True,
    },
    "filing_status": {
        "patterns": [
            r"(?:filing\s*status)[:\s]*(single|married\s*filing\s*jointly|married\s*filing\s*separately|head\s*of\s*household|qualifying\s*(?:widow|surviving))",
            r"\[?[xX]\]?\s*(single|married\s*filing\s*jointly|head\s*of\s*household)",
        ],
        "type": "string",
        "required": True,
    },
    "tax_year": {
        "patterns": [
            r"(?:form\s*1040|tax\s*year|for\s*(?:the\s*)?year)[:\s]*(\d{4})",
        ],
        "type": "integer",
        "required": True,
    },
    "adjusted_gross_income": {
        "patterns": [
            r"(?:adjusted\s*gross\s*income|agi|line\s*11\b)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": True,
    },
    "taxable_income": {
        "patterns": [
            r"(?:taxable\s*income|line\s*15\b)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": True,
    },
    "total_income": {
        "patterns": [
            r"(?:total\s*income|line\s*9\b)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "total_tax": {
        "patterns": [
            r"(?:total\s*tax|line\s*24\b)[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "schedule_c_income": {
        "patterns": [
            r"(?:schedule\s*c.*?(?:net\s*profit|line\s*31))[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
    "schedule_e_income": {
        "patterns": [
            r"(?:schedule\s*e.*?(?:total|income|line\s*26))[:\s]*\$?([\d,]+\.?\d*)",
        ],
        "type": "currency",
        "required": False,
    },
}

DRIVERS_LICENSE_PATTERNS: Dict[str, Dict[str, Any]] = {
    "full_name": {
        "patterns": [
            r"(?:name|nm)[:\s]+(.+?)(?:\n|$)",
            r"(?:ln|last\s*name)[:\s]+(.+?)(?:\n|$)",
        ],
        "type": "name",
        "required": True,
    },
    "date_of_birth": {
        "patterns": [
            r"(?:dob|date\s*of\s*birth|birth\s*date|db)[:\s]+(.+?)(?:\n|$)",
        ],
        "type": "date",
        "required": True,
    },
    "address": {
        "patterns": [
            r"(?:addr|address)[:\s]+(.+?)(?:\n|$)",
        ],
        "type": "address",
        "required": True,
    },
    "expiration_date": {
        "patterns": [
            r"(?:exp|expires|expiration)[:\s]+(.+?)(?:\n|$)",
        ],
        "type": "date",
        "required": True,
    },
    "license_number": {
        "patterns": [
            r"(?:dl|lic|license|licence|dl\s*no|id\s*no)[:\s#]*([A-Z0-9]+)",
        ],
        "type": "string",
        "required": True,
    },
}

PROPERTY_DOC_PATTERNS: Dict[str, Dict[str, Any]] = {
    "property_address": {
        "patterns": [
            r"(?:property\s*address|subject\s*property|located\s*at)[:\s]+(.+?)(?:\n|$)",
        ],
        "type": "address",
        "required": True,
    },
    "legal_description": {
        "patterns": [
            r"(?:legal\s*description|lot\s*\d+)[:\s]+(.+?)(?:\n\n|$)",
        ],
        "type": "string",
        "required": False,
    },
    "apn": {
        "patterns": [
            r"(?:apn|parcel\s*(?:number|id|#)|assessor.?s?\s*(?:parcel|number))[:\s#]*([A-Z0-9\-]+)",
        ],
        "type": "string",
        "required": False,
    },
}

# Master mapping from document type to its extraction patterns
DOCUMENT_FIELD_PATTERNS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "paystub": PAYSTUB_PATTERNS,
    "w2": W2_PATTERNS,
    "bank_statement": BANK_STATEMENT_PATTERNS,
    "tax_return": TAX_RETURN_PATTERNS,
    "drivers_license": DRIVERS_LICENSE_PATTERNS,
    "property": PROPERTY_DOC_PATTERNS,
    "purchase_contract": PROPERTY_DOC_PATTERNS,
    "appraisal": PROPERTY_DOC_PATTERNS,
    "title": PROPERTY_DOC_PATTERNS,
}


# ============================================================================
# MAIN SERVICE
# ============================================================================

class DocumentOCRService:
    """Comprehensive OCR and text extraction service for mortgage documents.

    Orchestrates the full pipeline: format detection -> pre-processing ->
    text extraction -> field parsing -> normalization -> confidence scoring.

    The service supports swappable OCR engines via the abstract OCREngine
    interface.  By default, it registers both Tesseract (local) and Claude
    Vision (API), and uses the best available result.
    """

    def __init__(
        self,
        engines: Optional[List[OCREngine]] = None,
        preprocessor: Optional[ImagePreprocessor] = None,
        normalizer: Optional[Type[DataNormalizer]] = None,
    ):
        """Initialize the OCR service.

        Args:
            engines: List of OCR engines to try (in priority order).
                     If None, auto-discovers available engines.
            preprocessor: Image pre-processor instance.
            normalizer: Data normalizer class (default: DataNormalizer).
        """
        self._preprocessor = preprocessor or ImagePreprocessor()
        self._normalizer = normalizer or DataNormalizer

        if engines is not None:
            self._engines = [e for e in engines if e.is_available()]
        else:
            self._engines = self._discover_engines()

        if not self._engines:
            logger.warning(
                "No OCR engines available. Install pytesseract or set "
                "ANTHROPIC_API_KEY for OCR functionality."
            )

    def _discover_engines(self) -> List[OCREngine]:
        """Auto-discover and register available OCR engines.

        Priority: Claude Vision first (higher quality), Tesseract as fallback.
        """
        engines: List[OCREngine] = []

        claude_engine = ClaudeVisionOCREngine()
        if claude_engine.is_available():
            engines.append(claude_engine)

        tesseract_engine = TesseractOCREngine()
        if tesseract_engine.is_available():
            engines.append(tesseract_engine)

        logger.info(
            "Discovered %d OCR engines: %s",
            len(engines),
            [e.name for e in engines],
        )
        return engines

    # -----------------------------------------------------------------
    # Format detection
    # -----------------------------------------------------------------

    @staticmethod
    def detect_format(
        file_bytes: bytes,
        mime_type: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> DocumentFormat:
        """Detect document format from MIME type, filename, or magic bytes.

        Args:
            file_bytes: Raw file bytes (used for magic byte detection).
            mime_type: Optional MIME type hint.
            filename: Optional filename hint.

        Returns:
            Detected DocumentFormat.
        """
        # Try MIME type first
        if mime_type and mime_type in MIME_TO_FORMAT:
            return MIME_TO_FORMAT[mime_type]

        # Try filename extension
        if filename:
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            ext_map = {
                "pdf": DocumentFormat.PDF,
                "jpg": DocumentFormat.JPEG,
                "jpeg": DocumentFormat.JPEG,
                "png": DocumentFormat.PNG,
                "tiff": DocumentFormat.TIFF,
                "tif": DocumentFormat.TIFF,
                "bmp": DocumentFormat.BMP,
                "webp": DocumentFormat.WEBP,
            }
            if ext in ext_map:
                return ext_map[ext]

        # Magic bytes detection
        if file_bytes[:4] == b"%PDF":
            return DocumentFormat.PDF
        if file_bytes[:2] == b"\xff\xd8":
            return DocumentFormat.JPEG
        if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            return DocumentFormat.PNG
        if file_bytes[:4] in (b"II*\x00", b"MM\x00*"):
            return DocumentFormat.TIFF
        if file_bytes[:2] == b"BM":
            return DocumentFormat.BMP
        if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
            return DocumentFormat.WEBP

        return DocumentFormat.UNKNOWN

    # -----------------------------------------------------------------
    # Core text extraction
    # -----------------------------------------------------------------

    def extract_text(
        self,
        file_bytes: bytes,
        mime_type: Optional[str] = None,
        filename: Optional[str] = None,
        language: str = "eng",
        preprocess: bool = True,
        max_pages: int = 50,
        db: Optional[Any] = None,
        organization_id: Optional[int] = None,
    ) -> OCRExtractionResult:
        """Extract text from a document file.

        This is the main entry point. Handles PDFs (native text + OCR
        fallback) and images.

        When db and organization_id are provided, results are cached by
        document hash to avoid re-processing identical documents.

        Args:
            file_bytes: Raw file content.
            mime_type: MIME type (auto-detected if not provided).
            filename: Original filename (used for format detection).
            language: OCR language code.
            preprocess: Whether to pre-process images before OCR.
            max_pages: Maximum pages to process (for large PDFs).
            db: Optional SQLAlchemy session for cache lookups.
            organization_id: Optional org ID for tenant-scoped caching.

        Returns:
            OCRExtractionResult with extracted text and metadata.
        """
        overall_start = time.monotonic()

        # --- Document cache lookup ---
        doc_hash = None
        cache_service = None
        if db is not None and organization_id is not None and file_bytes:
            try:
                from services.smart_docs.document_cache_service import get_document_cache_service
                cache_service = get_document_cache_service()
                doc_hash = cache_service.get_or_compute_hash(file_bytes)
                cached = cache_service.get_cached_ocr(db, doc_hash, organization_id)
                if cached is not None:
                    logger.info(
                        "doc_cache OCR_HIT hash=%s org=%s",
                        doc_hash[:12], organization_id,
                    )
                    return OCRExtractionResult(
                        success=cached.get("success", True),
                        full_text=cached.get("full_text", ""),
                        page_count=cached.get("page_count", 0),
                        overall_confidence=cached.get("overall_confidence", 0.0),
                        quality_grade=OCRQuality(cached.get("quality_grade", "poor")),
                        document_format=DocumentFormat(cached.get("document_format", "unknown")),
                        has_native_text=cached.get("has_native_text", False),
                        has_handwriting=cached.get("has_handwriting", False),
                        has_tables=cached.get("has_tables", False),
                        needs_manual_review=cached.get("needs_manual_review", False),
                        review_reasons=cached.get("review_reasons", []),
                        engine_used=cached.get("engine_used", "cache"),
                        total_processing_ms=int(
                            (time.monotonic() - overall_start) * 1000
                        ),
                    )
                else:
                    logger.info(
                        "doc_cache OCR_MISS hash=%s org=%s",
                        doc_hash[:12], organization_id,
                    )
            except Exception as e:
                logger.warning("doc_cache OCR lookup failed: %s", e)

        # Enforce page limit from upload_limits
        max_pages = min(max_pages, MAX_PDF_PAGES)

        # Check image dimensions before processing image files
        detected_mime = mime_type or ""
        if detected_mime.startswith("image/") and HAS_PIL:
            try:
                img = Image.open(io.BytesIO(file_bytes))
                w, h = img.size
                img.close()
                max_w, max_h = MAX_IMAGE_DIMENSIONS
                if w > max_w or h > max_h:
                    return OCRExtractionResult(
                        success=False,
                        full_text="",
                        error=(
                            f"Image dimensions {w}x{h} exceed maximum "
                            f"{max_w}x{max_h}. Resize before processing."
                        ),
                        total_processing_ms=int(
                            (time.monotonic() - overall_start) * 1000
                        ),
                    )
            except Exception:
                pass  # If check fails, proceed with processing

        doc_format = self.detect_format(file_bytes, mime_type, filename)
        if doc_format == DocumentFormat.UNKNOWN:
            return OCRExtractionResult(
                success=False,
                full_text="",
                document_format=doc_format,
                error="Unable to determine document format",
                total_processing_ms=int(
                    (time.monotonic() - overall_start) * 1000
                ),
            )

        try:
            if doc_format == DocumentFormat.PDF:
                result = self._extract_from_pdf(
                    file_bytes, language, preprocess, max_pages,
                )
            elif doc_format in IMAGE_FORMATS:
                result = self._extract_from_image(
                    file_bytes, mime_type or "image/png", language, preprocess,
                )
            else:
                return OCRExtractionResult(
                    success=False,
                    full_text="",
                    document_format=doc_format,
                    error=f"Unsupported format: {doc_format.value}",
                )

            result.document_format = doc_format
            result.total_processing_ms = int(
                (time.monotonic() - overall_start) * 1000
            )

            # Assess quality and flag for review
            result.quality_grade = self._assess_quality(result.overall_confidence)
            if result.quality_grade == OCRQuality.POOR:
                result.needs_manual_review = True
                result.review_reasons.append("Low OCR confidence")
            if result.has_handwriting:
                result.needs_manual_review = True
                result.review_reasons.append("Handwriting detected")

            # Truncate OCR output to prevent excessive memory/token usage
            if result.full_text and len(result.full_text) > MAX_OCR_OUTPUT_CHARS:
                original_len = len(result.full_text)
                result.full_text = result.full_text[:MAX_OCR_OUTPUT_CHARS]
                result.review_reasons.append(
                    f"OCR output truncated from {original_len:,} to "
                    f"{MAX_OCR_OUTPUT_CHARS:,} characters"
                )
                logger.info(
                    "OCR output truncated: %d -> %d chars",
                    original_len, MAX_OCR_OUTPUT_CHARS,
                )

            # --- Cache the successful OCR result ---
            if cache_service and doc_hash and db is not None and organization_id is not None:
                if result.success:
                    try:
                        cache_service.cache_ocr(db, doc_hash, organization_id, {
                            "success": result.success,
                            "full_text": result.full_text,
                            "page_count": result.page_count,
                            "overall_confidence": result.overall_confidence,
                            "quality_grade": result.quality_grade.value if hasattr(result.quality_grade, 'value') else str(result.quality_grade),
                            "document_format": result.document_format.value if hasattr(result.document_format, 'value') else str(result.document_format),
                            "has_native_text": result.has_native_text,
                            "has_handwriting": result.has_handwriting,
                            "has_tables": result.has_tables,
                            "needs_manual_review": result.needs_manual_review,
                            "review_reasons": result.review_reasons,
                            "engine_used": result.engine_used,
                        })
                    except Exception as e:
                        logger.warning("doc_cache OCR store failed: %s", e)

            return result

        except Exception as e:
            logger.exception("Text extraction failed for %s", doc_format.value)
            return OCRExtractionResult(
                success=False,
                full_text="",
                document_format=doc_format,
                error=str(e),
                total_processing_ms=int(
                    (time.monotonic() - overall_start) * 1000
                ),
            )

    def _extract_from_pdf(
        self,
        pdf_bytes: bytes,
        language: str,
        preprocess: bool,
        max_pages: int,
    ) -> OCRExtractionResult:
        """Extract text from a PDF, trying native text first, then OCR fallback.

        PERF FIX: pdf_bytes is read once and passed by reference to sub-methods.
        Previously the bytes could be re-read from scratch by each step.
        """
        pages: List[PageOCRResult] = []
        has_native_text = False

        # Step 1: Try native text extraction with pdfplumber
        if HAS_PDFPLUMBER:
            try:
                native_pages = self._extract_pdf_native_text(pdf_bytes, max_pages)
                total_chars = sum(len(p.text.strip()) for p in native_pages)
                if total_chars > 50:
                    has_native_text = True
                    pages = native_pages
            except Exception as e:
                logger.warning("PDF native text extraction failed: %s", e)

        # Step 2: If native text is sparse, fall back to OCR
        if not has_native_text or not pages:
            if HAS_PDF2IMAGE and self._engines:
                try:
                    ocr_pages = self._extract_pdf_via_ocr(
                        pdf_bytes, language, preprocess, max_pages,
                    )
                    if ocr_pages:
                        pages = ocr_pages
                except Exception as e:
                    logger.warning("PDF OCR extraction failed: %s", e)

        if not pages:
            return OCRExtractionResult(
                success=False,
                full_text="",
                error="No text could be extracted from PDF",
            )

        full_text = "\n\n".join(p.text for p in pages if p.text.strip())
        confidences = [p.confidence for p in pages if p.confidence > 0]
        avg_conf = statistics.mean(confidences) if confidences else 0.0
        has_handwriting = any(p.has_handwriting for p in pages)
        has_tables = any(p.has_tables for p in pages)

        return OCRExtractionResult(
            success=True,
            full_text=full_text,
            pages=pages,
            page_count=len(pages),
            overall_confidence=avg_conf,
            has_native_text=has_native_text,
            has_handwriting=has_handwriting,
            has_tables=has_tables,
            engine_used=pages[0].engine_used if pages else "",
        )

    def _extract_pdf_native_text(
        self, pdf_bytes: bytes, max_pages: int,
    ) -> List[PageOCRResult]:
        """Extract native text layer from PDF using pdfplumber."""
        pages: List[PageOCRResult] = []

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for i, page in enumerate(pdf.pages[:max_pages]):
                start = time.monotonic()
                text = page.extract_text() or ""

                # Try table extraction
                tables = []
                has_tables = False
                try:
                    raw_tables = page.extract_tables()
                    if raw_tables:
                        has_tables = True
                        for t_idx, table in enumerate(raw_tables):
                            rows = []
                            for row in table:
                                cleaned = [
                                    str(cell).strip() if cell else ""
                                    for cell in row
                                ]
                                rows.append(" | ".join(cleaned))
                            tables.append({
                                "table_index": t_idx,
                                "rows": rows,
                                "row_count": len(rows),
                            })
                except Exception as e:
                    logger.debug("Table extraction failed for page %d: %s", i, e)

                elapsed = int((time.monotonic() - start) * 1000)

                # Native PDF text gets high confidence when present
                confidence = 0.95 if len(text.strip()) > 20 else 0.3

                pages.append(PageOCRResult(
                    page_number=i + 1,
                    text=text,
                    confidence=confidence,
                    has_tables=has_tables,
                    tables=tables,
                    engine_used="pdfplumber_native",
                    processing_ms=elapsed,
                ))

        return pages

    def _extract_pdf_via_ocr(
        self,
        pdf_bytes: bytes,
        language: str,
        preprocess: bool,
        max_pages: int,
    ) -> List[PageOCRResult]:
        """Convert PDF pages to images and OCR each page."""
        try:
            images = convert_from_bytes(
                pdf_bytes, dpi=TARGET_DPI, first_page=1,
                last_page=max_pages,
            )
        except Exception as e:
            logger.warning("PDF to image conversion failed: %s", e)
            return []

        pages: List[PageOCRResult] = []
        for i, pil_image in enumerate(images):
            buf = io.BytesIO()
            pil_image.save(buf, format="PNG")
            img_bytes = buf.getvalue()

            page_result = self._ocr_single_image(
                img_bytes, "image/png", language, preprocess,
            )
            page_result.page_number = i + 1
            pages.append(page_result)

        return pages

    def _extract_from_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        language: str,
        preprocess: bool,
    ) -> OCRExtractionResult:
        """Extract text from a single image file."""
        page_result = self._ocr_single_image(
            image_bytes, mime_type, language, preprocess,
        )
        page_result.page_number = 1

        return OCRExtractionResult(
            success=bool(page_result.text.strip()),
            full_text=page_result.text,
            pages=[page_result],
            page_count=1,
            overall_confidence=page_result.confidence,
            has_handwriting=page_result.has_handwriting,
            has_tables=page_result.has_tables,
            engine_used=page_result.engine_used,
        )

    def _ocr_single_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        language: str,
        preprocess: bool,
    ) -> PageOCRResult:
        """OCR a single image using the best available engine.

        Tries engines in priority order. If pre-processing is enabled,
        the image is enhanced before OCR. If the first engine returns
        low confidence, falls back to the next engine.

        PERF FIX: The processed image bytes are computed once and reused
        across all engine calls (extract, table detection, handwriting
        detection). Previously each engine method re-opened the bytes
        independently via Image.open(), duplicating memory and CPU work.
        """
        processed_bytes = image_bytes
        preprocess_meta: Dict[str, Any] = {}

        if preprocess:
            processed_bytes, preprocess_meta = self._preprocessor.preprocess(
                image_bytes,
            )

        # Also detect and correct rotation -- do this once, not per-engine
        rotation = ImagePreprocessor.detect_rotation(processed_bytes)
        if rotation != 0 and HAS_PIL:
            try:
                img = Image.open(io.BytesIO(processed_bytes))
                img = img.rotate(-rotation, expand=True, fillcolor=255)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                processed_bytes = buf.getvalue()
            except Exception as e:
                logger.debug("Rotation correction failed: %s", e)

        best_result: Optional[PageOCRResult] = None

        # Track whether we already ran table/handwriting detection with any
        # engine so we don't redundantly call the Vision API for detection
        # after the primary engine already did text extraction.
        tables_checked = False
        handwriting_checked = False

        for engine in self._engines:
            try:
                result = engine.extract_from_image(
                    processed_bytes, mime_type, language,
                )

                # Check for tables only if not already found and not yet checked
                # by a higher-priority engine. Table/handwriting detection
                # re-opens the image bytes; avoid doing it more than once.
                if not result.has_tables and not tables_checked:
                    tables_checked = True
                    tables = engine.extract_tables(processed_bytes)
                    if tables:
                        result.has_tables = True
                        result.tables = tables

                if not result.has_handwriting and not handwriting_checked:
                    handwriting_checked = True
                    hw_detected, hw_conf = engine.detect_handwriting(
                        processed_bytes,
                    )
                    if hw_detected and hw_conf > 0.6:
                        result.has_handwriting = True

                if best_result is None or result.confidence > best_result.confidence:
                    best_result = result

                # If confidence is high enough, no need to try other engines
                if result.confidence >= 0.85:
                    break

            except Exception as e:
                logger.warning("Engine %s failed: %s", engine.name, e)
                continue

        if best_result is None:
            return PageOCRResult(
                page_number=0, text="", confidence=0.0,
                engine_used="none",
            )

        return best_result

    # -----------------------------------------------------------------
    # Mortgage field extraction
    # -----------------------------------------------------------------

    def extract_mortgage_fields(
        self,
        ocr_result: OCRExtractionResult,
        document_type: str,
    ) -> MortgageFieldExtractionResult:
        """Extract mortgage-specific fields from OCR text.

        Uses regex pattern matching with document-type-specific patterns,
        then normalizes each value according to its data type.

        Args:
            ocr_result: OCR extraction result from extract_text().
            document_type: Document type key (e.g. 'paystub', 'w2',
                          'bank_statement', 'tax_return', 'drivers_license').

        Returns:
            MortgageFieldExtractionResult with extracted and normalized fields.
        """
        patterns = DOCUMENT_FIELD_PATTERNS.get(document_type.lower())
        if patterns is None:
            return MortgageFieldExtractionResult(
                success=False,
                document_type=document_type,
                error=f"No extraction patterns for document type: {document_type}",
            )

        text = ocr_result.full_text
        if not text.strip():
            return MortgageFieldExtractionResult(
                success=False,
                document_type=document_type,
                error="No text available for field extraction",
            )

        fields: Dict[str, ExtractedField] = {}
        missing_required: List[str] = []
        review_reasons: List[str] = []

        for field_name, field_config in patterns.items():
            extracted = self._extract_field(
                text, field_name, field_config, ocr_result.overall_confidence,
            )

            if extracted is not None:
                fields[field_name] = extracted
                if extracted.needs_review:
                    review_reasons.append(
                        f"Low confidence on {field_name}: "
                        f"{extracted.confidence:.0%}"
                    )
            elif field_config.get("required", False):
                missing_required.append(field_name)

        # Calculate overall confidence
        if fields:
            field_confs = [f.confidence for f in fields.values()]
            overall_conf = statistics.mean(field_confs)
        else:
            overall_conf = 0.0

        needs_review = (
            bool(missing_required)
            or bool(review_reasons)
            or overall_conf < 0.6
            or ocr_result.has_handwriting
        )

        if missing_required:
            review_reasons.append(
                f"Missing required fields: {', '.join(missing_required)}"
            )

        return MortgageFieldExtractionResult(
            success=True,
            document_type=document_type,
            fields=fields,
            overall_confidence=overall_conf,
            missing_required=missing_required,
            needs_manual_review=needs_review,
            review_reasons=review_reasons,
        )

    def _extract_field(
        self,
        text: str,
        field_name: str,
        config: Dict[str, Any],
        base_confidence: float,
    ) -> Optional[ExtractedField]:
        """Extract a single field using its regex patterns and normalize the value."""
        field_type = config.get("type", "string")

        for pattern_str in config.get("patterns", []):
            try:
                match = re.search(pattern_str, text, re.IGNORECASE | re.MULTILINE)
                if not match:
                    continue

                raw_value = match.group(1).strip()
                if not raw_value:
                    continue

                # Get surrounding context (50 chars each side)
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]

                # Normalize based on type
                normalized = self._normalize_value(raw_value, field_type)
                if normalized is None:
                    continue

                # Calculate per-field confidence
                confidence = self._calculate_field_confidence(
                    raw_value, field_type, base_confidence,
                )

                return ExtractedField(
                    name=field_name,
                    value=normalized,
                    raw_value=raw_value,
                    confidence=confidence,
                    source_text=context,
                    needs_review=confidence < 0.6,
                )

            except re.error as e:
                logger.debug("Regex error for %s: %s", field_name, e)
                continue

        return None

    def _normalize_value(
        self, raw: str, field_type: str,
    ) -> Optional[Any]:
        """Normalize a raw OCR value based on its declared type."""
        if field_type == "currency":
            val = self._normalizer.parse_currency(raw)
            return float(val) if val is not None else None

        elif field_type == "date":
            return self._normalizer.parse_date(raw)

        elif field_type == "name":
            return self._normalizer.normalize_name(raw)

        elif field_type == "address":
            return self._normalizer.normalize_address(raw)

        elif field_type == "ssn":
            return self._normalizer.extract_ssn_last4(raw)

        elif field_type == "phone":
            return self._normalizer.normalize_phone(raw)

        elif field_type == "state":
            return self._normalizer.normalize_state(raw)

        elif field_type == "integer":
            try:
                return int(re.sub(r"[^\d]", "", raw))
            except ValueError:
                return None

        elif field_type == "number":
            try:
                return float(raw.replace(",", ""))
            except ValueError:
                return None

        else:
            # string type -- basic cleanup
            return raw.strip()

    def _calculate_field_confidence(
        self,
        raw_value: str,
        field_type: str,
        base_confidence: float,
    ) -> float:
        """Calculate confidence score for an extracted field.

        Factors in OCR base confidence, value plausibility, and
        type-specific heuristics.
        """
        confidence = base_confidence

        if field_type == "currency":
            val = self._normalizer.parse_currency(raw_value)
            if val is not None:
                # Reasonable mortgage amounts range
                if Decimal("0") <= val <= Decimal("10000000"):
                    confidence = min(confidence + 0.05, 1.0)
                else:
                    confidence *= 0.7  # unusually large/negative

        elif field_type == "date":
            parsed = self._normalizer.parse_date(raw_value)
            if parsed is not None:
                # Date in reasonable range (1920 - 2030)
                if 1920 <= parsed.year <= 2030:
                    confidence = min(confidence + 0.05, 1.0)
                else:
                    confidence *= 0.5
            else:
                confidence *= 0.4

        elif field_type == "ssn":
            # SSN should be exactly the right pattern
            if re.match(r"\d{3}-?\d{2}-?\d{4}", raw_value.strip()):
                confidence = min(confidence + 0.1, 1.0)
            else:
                confidence *= 0.5

        elif field_type == "integer":
            if raw_value.strip().isdigit():
                confidence = min(confidence + 0.05, 1.0)
            else:
                confidence *= 0.7

        # Short values are less trustworthy
        if len(raw_value.strip()) < 2:
            confidence *= 0.6

        return round(min(max(confidence, 0.0), 1.0), 3)

    # -----------------------------------------------------------------
    # Quality assessment
    # -----------------------------------------------------------------

    @staticmethod
    def _assess_quality(confidence: float) -> OCRQuality:
        """Map a confidence score to a quality grade."""
        if confidence >= 0.90:
            return OCRQuality.EXCELLENT
        if confidence >= 0.70:
            return OCRQuality.GOOD
        if confidence >= 0.50:
            return OCRQuality.FAIR
        return OCRQuality.POOR

    # -----------------------------------------------------------------
    # Convenience: full pipeline
    # -----------------------------------------------------------------

    def process_document(
        self,
        file_bytes: bytes,
        document_type: str,
        mime_type: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the full OCR + field extraction pipeline end-to-end.

        Convenience method that combines extract_text() and
        extract_mortgage_fields() into a single call.

        Args:
            file_bytes: Raw document file.
            document_type: Mortgage doc type (paystub, w2, etc.).
            mime_type: MIME type (auto-detected if omitted).
            filename: Original filename.

        Returns:
            Dictionary with 'ocr' and 'fields' results.
        """
        ocr_result = self.extract_text(
            file_bytes, mime_type=mime_type, filename=filename,
        )

        field_result = MortgageFieldExtractionResult(
            success=False,
            document_type=document_type,
            error="OCR extraction failed",
        )

        if ocr_result.success:
            field_result = self.extract_mortgage_fields(
                ocr_result, document_type,
            )

        return {
            "ocr": ocr_result.to_dict(),
            "fields": field_result.to_dict(),
            "needs_manual_review": (
                ocr_result.needs_manual_review
                or field_result.needs_manual_review
            ),
            "review_reasons": list(set(
                ocr_result.review_reasons + field_result.review_reasons
            )),
        }


# ============================================================================
# MODULE SINGLETON
# ============================================================================

_service_instance: Optional[DocumentOCRService] = None


def get_document_ocr_service(
    engines: Optional[List[OCREngine]] = None,
) -> DocumentOCRService:
    """Get or create the singleton DocumentOCRService.

    Args:
        engines: Optional list of OCR engines. If provided on first call,
                 they are used instead of auto-discovery.

    Returns:
        DocumentOCRService instance.
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = DocumentOCRService(engines=engines)
    return _service_instance
