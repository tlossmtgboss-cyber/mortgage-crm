"""
Document Splitting / Separation Service for Smart Docs V2

Handles the common mortgage scenario where borrowers upload a single PDF
containing multiple document types (e.g., paystubs, W-2s, and bank
statements in one scan).

Capabilities:
    - AI-powered page classification within a multi-page PDF
    - Automatic document boundary detection
    - Split strategies: by doc type, by page count, by blank page, manual
    - Multi-month bank statement splitting by statement period
    - Borrower + co-borrower document separation
    - Front/back ID page merging
    - Preview mode (proposed splits before execution)
    - Undo split (re-merge previously split children)
    - Page rotation and reordering during split
    - Parent-child relationship tracking (original -> split children)
    - Post-split classification and OCR extraction

Integration points:
    - ai_classifier_service.py  (per-page classification)
    - document_ocr_service.py   (per-page and per-split OCR)
    - s3_storage_service.py     (storage of split PDFs)
    - document_review_pipeline.py (post-split processing)
    - service_registry.py       (org-context injection)

Usage:
    from services.smart_docs.document_splitting_service import (
        DocumentSplittingService,
        get_document_splitting_service,
    )

    service = get_document_splitting_service(db)

    # Analyze a document for splitting
    analysis = await service.analyze_document(doc_id=123, org_id=1)

    # Preview proposed splits
    previews = await service.preview_split(doc_id=123, split_plan=analysis.plan, org_id=1)

    # Execute the split
    new_ids = await service.execute_split(doc_id=123, split_plan=analysis.plan, org_id=1, user_id=7)

    # Auto-split and classify in one pass
    results = await service.auto_split_and_classify(doc_id=123, org_id=1, user_id=7)

    # Merge previously split documents back together
    merged_id = await service.merge_documents(doc_ids=[200, 201, 202], target_name="merged.pdf", org_id=1, user_id=7)
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency imports (graceful degradation)
# ---------------------------------------------------------------------------

_pdf_reader_class = None
_pdf_writer_class = None
_pdf_library: Optional[str] = None

try:
    from pypdf import PdfReader, PdfWriter, Transformation
    _pdf_reader_class = PdfReader
    _pdf_writer_class = PdfWriter
    _pdf_library = "pypdf"
except ImportError:
    try:
        from PyPDF2 import PdfReader, PdfWriter  # type: ignore[no-redef]
        _pdf_reader_class = PdfReader
        _pdf_writer_class = PdfWriter
        _pdf_library = "PyPDF2"
    except ImportError:
        logger.warning(
            "Neither pypdf nor PyPDF2 is available. "
            "Document splitting will be limited."
        )

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from pdf2image import convert_from_bytes
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False


# =============================================================================
# ENUMS
# =============================================================================

class SplitStrategy(str, Enum):
    """Strategy used to determine split points."""
    BY_DOC_TYPE = "BY_DOC_TYPE"
    BY_PAGE_COUNT = "BY_PAGE_COUNT"
    BY_BLANK_PAGE = "BY_BLANK_PAGE"
    MANUAL = "MANUAL"
    AI_AUTO = "AI_AUTO"


class PageClassificationConfidence(str, Enum):
    """Confidence level for page classification."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PageClassification:
    """Classification result for a single page."""
    page_number: int  # 1-based
    doc_type: str  # DocType value or "UNKNOWN"
    confidence: int  # 0-100
    confidence_level: PageClassificationConfidence
    is_blank: bool
    is_id_back: bool  # Detected as back side of an ID document
    detected_owner: Optional[str]  # "BORROWER", "CO_BORROWER", or None
    statement_period: Optional[str]  # e.g. "2025-01" for bank statements
    text_snippet: str  # First ~200 chars of extracted text
    features: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "doc_type": self.doc_type,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "is_blank": self.is_blank,
            "is_id_back": self.is_id_back,
            "detected_owner": self.detected_owner,
            "statement_period": self.statement_period,
            "text_snippet": self.text_snippet[:200],
            "features": self.features,
        }


@dataclass
class SplitSegment:
    """A segment of pages that should become one document after splitting."""
    pages: List[int]  # 1-based page numbers
    doc_type: str
    label: str  # Human-readable label, e.g. "Paystub - January 2025"
    owner: Optional[str]  # "BORROWER", "CO_BORROWER", or None
    confidence: int  # Average confidence across pages
    merge_reason: Optional[str] = None  # Why pages were grouped (e.g. "ID front+back")
    rotation: Dict[int, int] = field(default_factory=dict)  # page_number -> degrees CW

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pages": self.pages,
            "doc_type": self.doc_type,
            "label": self.label,
            "owner": self.owner,
            "confidence": self.confidence,
            "merge_reason": self.merge_reason,
            "rotation": self.rotation,
        }


@dataclass
class SplitPlan:
    """Complete plan for splitting a document."""
    source_doc_id: int
    strategy: SplitStrategy
    segments: List[SplitSegment]
    total_pages: int
    unassigned_pages: List[int]  # Pages not included in any segment

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_doc_id": self.source_doc_id,
            "strategy": self.strategy.value,
            "segments": [s.to_dict() for s in self.segments],
            "total_pages": self.total_pages,
            "unassigned_pages": self.unassigned_pages,
            "segment_count": len(self.segments),
        }


@dataclass
class SplitAnalysis:
    """Result of analyzing a document for splitting."""
    source_doc_id: int
    total_pages: int
    page_classifications: List[PageClassification]
    plan: SplitPlan
    needs_splitting: bool  # True if more than one document type detected
    detected_doc_types: List[str]
    detected_owners: List[str]
    analysis_duration_ms: int
    model_used: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_doc_id": self.source_doc_id,
            "total_pages": self.total_pages,
            "page_classifications": [p.to_dict() for p in self.page_classifications],
            "plan": self.plan.to_dict(),
            "needs_splitting": self.needs_splitting,
            "detected_doc_types": self.detected_doc_types,
            "detected_owners": self.detected_owners,
            "analysis_duration_ms": self.analysis_duration_ms,
            "model_used": self.model_used,
        }


@dataclass
class PagePreview:
    """Preview of a single page in a split segment."""
    page_number: int
    segment_index: int
    doc_type: str
    label: str
    thumbnail_base64: Optional[str]  # Base64-encoded JPEG thumbnail
    rotation: int  # Degrees CW
    width: int
    height: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "segment_index": self.segment_index,
            "doc_type": self.doc_type,
            "label": self.label,
            "has_thumbnail": self.thumbnail_base64 is not None,
            "thumbnail_base64": self.thumbnail_base64,
            "rotation": self.rotation,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class SplitResult:
    """Result of splitting one segment into a new document."""
    new_doc_id: int
    source_doc_id: int
    pages: List[int]
    doc_type: str
    label: str
    owner: Optional[str]
    page_count: int
    file_size: int
    storage_key: str
    classification_confidence: int
    classification_applied: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "new_doc_id": self.new_doc_id,
            "source_doc_id": self.source_doc_id,
            "pages": self.pages,
            "doc_type": self.doc_type,
            "label": self.label,
            "owner": self.owner,
            "page_count": self.page_count,
            "file_size": self.file_size,
            "storage_key": self.storage_key,
            "classification_confidence": self.classification_confidence,
            "classification_applied": self.classification_applied,
        }


# =============================================================================
# CONSTANTS
# =============================================================================

# Blank page detection: a page with fewer than this many non-whitespace
# characters is considered blank.
BLANK_PAGE_CHAR_THRESHOLD = 30

# Pages with text length below this are candidates for ID-back detection
ID_BACK_TEXT_THRESHOLD = 100

# Maximum pages we will send to AI for classification in a single request
MAX_PAGES_PER_AI_CALL = 10

# Thumbnail dimensions for preview
THUMBNAIL_MAX_WIDTH = 300
THUMBNAIL_MAX_HEIGHT = 400

# Document types that commonly appear as front+back pairs
ID_DOCUMENT_TYPES = {"DRIVERS_LICENSE", "PASSPORT", "SSN_CARD"}

# Document types where period-based splitting is relevant
PERIOD_SPLIT_TYPES = {"BANK_STATEMENT", "INVESTMENT_STATEMENT", "PAYSTUB"}

# AI model used for page classification
AI_MODEL = os.getenv("SMART_DOCS_AI_MODEL", "claude-sonnet-4-20250514")

# Maximum file size for AI vision analysis (per page image)
MAX_PAGE_IMAGE_BYTES = 2_000_000  # 2 MB


# =============================================================================
# SERVICE
# =============================================================================

class DocumentSplittingService:
    """
    Service for splitting multi-document PDFs into individual documents.

    All public methods require org_id for tenant isolation. The service
    verifies that the target document belongs to the requesting org
    before any operation.
    """

    def __init__(self, db: Session):
        self.db = db
        self._anthropic: Optional[Any] = None
        self._s3_service = None
        self._classifier = None
        self._ocr_service = None

    # ------------------------------------------------------------------
    # Lazy service accessors
    # ------------------------------------------------------------------

    @property
    def anthropic(self):
        """Lazy-load Anthropic client."""
        if self._anthropic is None and HAS_ANTHROPIC:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                self._anthropic = Anthropic(api_key=api_key)
        return self._anthropic

    @property
    def s3_service(self):
        """Lazy-load S3 storage service."""
        if self._s3_service is None:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
            self._s3_service = get_smart_docs_s3_service()
        return self._s3_service

    @property
    def classifier(self):
        """Lazy-load AI classifier service."""
        if self._classifier is None:
            from services.smart_docs.ai_classifier_service import get_ai_classifier_service
            self._classifier = get_ai_classifier_service()
        return self._classifier

    @property
    def ocr_service(self):
        """Lazy-load OCR service."""
        if self._ocr_service is None:
            from services.smart_docs.document_ocr_service import get_document_ocr_service
            self._ocr_service = get_document_ocr_service()
        return self._ocr_service

    # ------------------------------------------------------------------
    # Tenant isolation
    # ------------------------------------------------------------------

    def _verify_document_org(self, doc_id: int, org_id: int) -> Dict[str, Any]:
        """Verify a smart_document belongs to the given org.

        Returns the document row dict on success.

        Raises:
            ValueError: If the document does not exist or belongs to
                another organization.
        """
        row = self.db.execute(
            text("""
                SELECT sd.id, sd.loan_id, sd.borrower_id, sd.storage_key,
                       sd.file_name, sd.mime_type, sd.page_count, sd.doc_type,
                       sd.status, l.organization_id
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE sd.id = :doc_id
            """),
            {"doc_id": doc_id},
        ).fetchone()

        if not row:
            raise ValueError(f"Document {doc_id} not found")

        if row.organization_id != org_id:
            logger.warning(
                "Tenant isolation: org %s attempted to access document %s "
                "belonging to org %s",
                org_id, doc_id, row.organization_id,
            )
            raise ValueError(f"Document {doc_id} not found")

        return {
            "id": row.id,
            "loan_id": row.loan_id,
            "borrower_id": row.borrower_id,
            "storage_key": row.storage_key,
            "file_name": row.file_name,
            "mime_type": row.mime_type,
            "page_count": row.page_count,
            "doc_type": row.doc_type,
            "status": row.status,
            "organization_id": row.organization_id,
        }

    def _fetch_document_bytes(self, storage_key: str) -> bytes:
        """Download document bytes from S3.

        Falls back to local filesystem if S3 is unavailable (dev mode).
        """
        if self.s3_service and self.s3_service._s3_available:
            return self.s3_service.download_file(storage_key)

        # Dev fallback: try reading from local path
        if os.path.isfile(storage_key):
            with open(storage_key, "rb") as f:
                return f.read()

        raise FileNotFoundError(
            f"Cannot retrieve document at storage_key={storage_key!r}. "
            "S3 is unavailable and the key is not a local file path."
        )

    # ------------------------------------------------------------------
    # PDF page utilities
    # ------------------------------------------------------------------

    def _get_pdf_reader(self, file_bytes: bytes):
        """Create a PdfReader from bytes. Returns None if no PDF library."""
        if _pdf_reader_class is None:
            raise RuntimeError(
                "No PDF library available. Install pypdf: pip install pypdf"
            )
        return _pdf_reader_class(io.BytesIO(file_bytes))

    def _extract_page_text(self, reader, page_index: int) -> str:
        """Extract text from a single PDF page (0-based index)."""
        try:
            page = reader.pages[page_index]
            text_content = page.extract_text() or ""
            return text_content.strip()
        except Exception as e:
            logger.warning("Failed to extract text from page %d: %s", page_index + 1, e)
            return ""

    def _is_blank_page(self, page_text: str) -> bool:
        """Determine if a page is blank based on text content."""
        non_ws = "".join(page_text.split())
        return len(non_ws) < BLANK_PAGE_CHAR_THRESHOLD

    def _page_to_image_bytes(
        self, file_bytes: bytes, page_number: int
    ) -> Optional[bytes]:
        """Convert a single PDF page to JPEG bytes for AI vision.

        Args:
            file_bytes: Full PDF bytes.
            page_number: 1-based page number.

        Returns:
            JPEG bytes or None if conversion is unavailable.
        """
        if not HAS_PDF2IMAGE:
            return None

        try:
            images = convert_from_bytes(
                file_bytes,
                first_page=page_number,
                last_page=page_number,
                dpi=150,
                fmt="jpeg",
            )
            if not images:
                return None

            buf = io.BytesIO()
            images[0].save(buf, format="JPEG", quality=80)
            img_bytes = buf.getvalue()

            # Resize if too large
            if len(img_bytes) > MAX_PAGE_IMAGE_BYTES and HAS_PIL:
                img = PILImage.open(io.BytesIO(img_bytes))
                ratio = (MAX_PAGE_IMAGE_BYTES / len(img_bytes)) ** 0.5
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, PILImage.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=70)
                img_bytes = buf.getvalue()

            return img_bytes
        except Exception as e:
            logger.warning("Failed to convert page %d to image: %s", page_number, e)
            return None

    def _build_page_from_reader(self, reader, page_index: int, rotation: int = 0) -> Any:
        """Extract a page object from reader, applying rotation."""
        page = reader.pages[page_index]
        if rotation:
            page = page.rotate(rotation)
        return page

    def _write_pages_to_bytes(self, pages: List[Any]) -> bytes:
        """Write a list of page objects to PDF bytes."""
        if _pdf_writer_class is None:
            raise RuntimeError("No PDF library available for writing")

        writer = _pdf_writer_class()
        for page in pages:
            writer.add_page(page)

        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()

    def _generate_thumbnail(
        self, file_bytes: bytes, page_number: int, rotation: int = 0
    ) -> Optional[str]:
        """Generate a base64-encoded JPEG thumbnail of a page.

        Returns None if image conversion is unavailable.
        """
        img_bytes = self._page_to_image_bytes(file_bytes, page_number)
        if img_bytes is None:
            return None

        if not HAS_PIL:
            return base64.b64encode(img_bytes).decode("ascii")

        try:
            img = PILImage.open(io.BytesIO(img_bytes))
            if rotation:
                # PIL rotation is counter-clockwise; PDF is clockwise
                img = img.rotate(-rotation, expand=True)
            img.thumbnail((THUMBNAIL_MAX_WIDTH, THUMBNAIL_MAX_HEIGHT))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception as e:
            logger.warning("Thumbnail generation failed for page %d: %s", page_number, e)
            return None

    # ------------------------------------------------------------------
    # AI page classification
    # ------------------------------------------------------------------

    def _classify_pages_with_ai(
        self,
        file_bytes: bytes,
        page_texts: List[str],
        total_pages: int,
    ) -> List[PageClassification]:
        """Classify each page using AI (Claude Vision + text analysis).

        Processes pages in batches of MAX_PAGES_PER_AI_CALL. Uses vision
        when pdf2image is available, falling back to text-only classification.
        """
        classifications: List[PageClassification] = []

        for batch_start in range(0, total_pages, MAX_PAGES_PER_AI_CALL):
            batch_end = min(batch_start + MAX_PAGES_PER_AI_CALL, total_pages)
            batch_classifications = self._classify_page_batch(
                file_bytes=file_bytes,
                page_texts=page_texts,
                start_page=batch_start,
                end_page=batch_end,
            )
            classifications.extend(batch_classifications)

        return classifications

    def _classify_page_batch(
        self,
        file_bytes: bytes,
        page_texts: List[str],
        start_page: int,
        end_page: int,
    ) -> List[PageClassification]:
        """Classify a batch of pages using AI.

        Args:
            file_bytes: Full PDF bytes (for image extraction).
            page_texts: Pre-extracted text for all pages (0-based index).
            start_page: Start page index (0-based, inclusive).
            end_page: End page index (0-based, exclusive).
        """
        results: List[PageClassification] = []

        # Try AI classification first
        if self.anthropic:
            ai_results = self._ai_classify_batch(
                file_bytes, page_texts, start_page, end_page
            )
            if ai_results:
                return ai_results

        # Fallback: rule-based classification per page
        for page_idx in range(start_page, end_page):
            page_text = page_texts[page_idx] if page_idx < len(page_texts) else ""
            classification = self._rule_based_classify_page(
                page_number=page_idx + 1,
                page_text=page_text,
            )
            results.append(classification)

        return results

    def _ai_classify_batch(
        self,
        file_bytes: bytes,
        page_texts: List[str],
        start_page: int,
        end_page: int,
    ) -> Optional[List[PageClassification]]:
        """Use Claude to classify a batch of pages.

        Constructs a multi-page prompt with text excerpts and optional
        page images for visual classification.
        """
        from services.smart_docs.ai_resilience import resilient_ai_call

        # Build content blocks
        content_blocks: List[Dict[str, Any]] = []

        page_descriptions = []
        for page_idx in range(start_page, end_page):
            page_num = page_idx + 1
            page_text = page_texts[page_idx] if page_idx < len(page_texts) else ""
            excerpt = page_text[:1500]
            page_descriptions.append(f"--- PAGE {page_num} ---\n{excerpt}")

            # Try to include page image for vision
            img_bytes = self._page_to_image_bytes(file_bytes, page_num)
            if img_bytes:
                content_blocks.append({
                    "type": "text",
                    "text": f"[Page {page_num} image follows]",
                })
                content_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.b64encode(img_bytes).decode("ascii"),
                    },
                })

        # Always include text excerpts
        all_text = "\n\n".join(page_descriptions)
        content_blocks.append({
            "type": "text",
            "text": f"""Analyze each page of this multi-page PDF and classify them.

For each page, determine:
1. doc_type: The mortgage document type. Use one of: DRIVERS_LICENSE, PAYSTUB, W2, TAX_RETURN, BUSINESS_TAX_RETURN, PROFIT_LOSS, BALANCE_SHEET, BANK_STATEMENT, INVESTMENT_STATEMENT, GIFT_LETTER, LOE, LEASE_AGREEMENT, FHA_CERT, VA_COE, DD214, BANKRUPTCY_DISCHARGE, PURCHASE_CONTRACT, APPRAISAL, TITLE_REPORT, HOMEOWNERS_INSURANCE, OTHER, UNKNOWN
2. confidence: 0-100 confidence in the classification
3. is_blank: true if the page is essentially blank (no meaningful content)
4. is_id_back: true if this appears to be the back of an ID/license
5. detected_owner: "BORROWER" or "CO_BORROWER" if you can determine whose document this is, otherwise null
6. statement_period: If this is a bank statement or paystub, the month in YYYY-MM format, otherwise null

Page texts:
{all_text}

Respond with a JSON array. One object per page, in order:
[{{"page": 1, "doc_type": "...", "confidence": 90, "is_blank": false, "is_id_back": false, "detected_owner": null, "statement_period": null}}, ...]

Return ONLY the JSON array, no other text.""",
        })

        try:
            response = resilient_ai_call(
                client=self.anthropic,
                messages=[{"role": "user", "content": content_blocks}],
                model=AI_MODEL,
                max_tokens=2048,
                operation_name="split_classify_pages",
                org_id=None,
            )

            if response is None:
                return None

            # Parse response
            response_text = response.content[0].text.strip()
            # Strip markdown fences if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(
                    lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
                )

            parsed = json.loads(response_text)
            if not isinstance(parsed, list):
                logger.warning("AI returned non-list response for page classification")
                return None

            classifications: List[PageClassification] = []
            for i, item in enumerate(parsed):
                page_idx = start_page + i
                page_num = page_idx + 1
                page_text = page_texts[page_idx] if page_idx < len(page_texts) else ""

                conf = int(item.get("confidence", 50))
                if conf >= 80:
                    conf_level = PageClassificationConfidence.HIGH
                elif conf >= 50:
                    conf_level = PageClassificationConfidence.MEDIUM
                else:
                    conf_level = PageClassificationConfidence.LOW

                classifications.append(PageClassification(
                    page_number=page_num,
                    doc_type=item.get("doc_type", "UNKNOWN"),
                    confidence=conf,
                    confidence_level=conf_level,
                    is_blank=bool(item.get("is_blank", False)),
                    is_id_back=bool(item.get("is_id_back", False)),
                    detected_owner=item.get("detected_owner"),
                    statement_period=item.get("statement_period"),
                    text_snippet=page_text[:200],
                ))

            return classifications

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse AI classification response: %s", e)
            return None
        except Exception as e:
            logger.exception("AI page classification failed: %s", e)
            return None

    def _rule_based_classify_page(
        self,
        page_number: int,
        page_text: str,
    ) -> PageClassification:
        """Classify a single page using keyword rules (fallback).

        Mirrors the keyword-scoring approach from ai_classifier_service.py
        but applied at the single-page level.
        """
        text_lower = page_text.lower()
        is_blank = self._is_blank_page(page_text)

        if is_blank:
            return PageClassification(
                page_number=page_number,
                doc_type="UNKNOWN",
                confidence=95,
                confidence_level=PageClassificationConfidence.HIGH,
                is_blank=True,
                is_id_back=False,
                detected_owner=None,
                statement_period=None,
                text_snippet="",
            )

        # Keyword scoring -- adapted from ai_classifier_service.py
        scores: Dict[str, int] = {}
        keyword_rules = _get_keyword_rules()

        for doc_type, keywords in keyword_rules.items():
            score = 0
            for keyword, weight in keywords:
                if keyword in text_lower:
                    score += weight
            if score > 0:
                scores[doc_type] = score

        if not scores:
            return PageClassification(
                page_number=page_number,
                doc_type="OTHER",
                confidence=20,
                confidence_level=PageClassificationConfidence.LOW,
                is_blank=False,
                is_id_back=False,
                detected_owner=self._detect_owner_from_text(text_lower),
                statement_period=self._detect_period_from_text(text_lower),
                text_snippet=page_text[:200],
            )

        best_type = max(scores, key=scores.get)  # type: ignore[arg-type]
        best_score = scores[best_type]

        # Normalize score to 0-100 confidence
        max_possible = 100  # Approximate max score for a strong match
        confidence = min(95, int((best_score / max_possible) * 100))

        if confidence >= 70:
            conf_level = PageClassificationConfidence.HIGH
        elif confidence >= 40:
            conf_level = PageClassificationConfidence.MEDIUM
        else:
            conf_level = PageClassificationConfidence.LOW

        # Check for ID back
        is_id_back = (
            best_type in ID_DOCUMENT_TYPES
            and len(page_text.strip()) < ID_BACK_TEXT_THRESHOLD
            and any(kw in text_lower for kw in ["organ donor", "restrictions", "class", "endorsements"])
        )

        return PageClassification(
            page_number=page_number,
            doc_type=best_type,
            confidence=confidence,
            confidence_level=conf_level,
            is_blank=False,
            is_id_back=is_id_back,
            detected_owner=self._detect_owner_from_text(text_lower),
            statement_period=self._detect_period_from_text(text_lower),
            text_snippet=page_text[:200],
        )

    def _detect_owner_from_text(self, text_lower: str) -> Optional[str]:
        """Try to detect if document belongs to borrower or co-borrower.

        Looks for explicit borrower/co-borrower labels, or for differing
        names when we have context. Returns None if indeterminate.
        """
        if "co-borrower" in text_lower or "co borrower" in text_lower:
            return "CO_BORROWER"
        # Cannot reliably distinguish borrower from co-borrower with text
        # alone without comparing to known names on the loan. Return None
        # and let the caller resolve using loan context.
        return None

    def _detect_period_from_text(self, text_lower: str) -> Optional[str]:
        """Detect statement period (YYYY-MM) from page text.

        Looks for common period/statement date patterns in bank statements
        and paystubs.
        """
        import re

        # "Statement Period: January 1, 2025 - January 31, 2025"
        # "Period Ending: 01/31/2025"
        # "Pay Period End: 2025-01-15"
        month_map = {
            "january": "01", "february": "02", "march": "03", "april": "04",
            "may": "05", "june": "06", "july": "07", "august": "08",
            "september": "09", "october": "10", "november": "11", "december": "12",
            "jan": "01", "feb": "02", "mar": "03", "apr": "04",
            "jun": "06", "jul": "07", "aug": "08", "sep": "09",
            "oct": "10", "nov": "11", "dec": "12",
        }

        # Try "Month DD, YYYY" pattern near period/ending/statement keywords
        for keyword in ["period", "ending", "statement", "through", "pay date"]:
            idx = text_lower.find(keyword)
            if idx == -1:
                continue
            context = text_lower[idx:idx + 80]
            for month_name, month_num in month_map.items():
                if month_name in context:
                    # Find a 4-digit year near the month
                    year_match = re.search(r"20[0-9]{2}", context)
                    if year_match:
                        return f"{year_match.group()}-{month_num}"

        # Try MM/DD/YYYY pattern
        date_match = re.search(
            r"(?:period|ending|statement|through|pay date)[^\d]*"
            r"(\d{1,2})[/\-](\d{1,2})[/\-](20\d{2})",
            text_lower,
        )
        if date_match:
            month = date_match.group(1).zfill(2)
            year = date_match.group(3)
            return f"{year}-{month}"

        return None

    # ------------------------------------------------------------------
    # Split plan generation
    # ------------------------------------------------------------------

    def _build_plan_by_doc_type(
        self,
        doc_id: int,
        classifications: List[PageClassification],
        total_pages: int,
    ) -> SplitPlan:
        """Build a split plan by grouping consecutive pages of the same type.

        Applies ID front+back merging and period-based grouping for
        statements.
        """
        if not classifications:
            return SplitPlan(
                source_doc_id=doc_id,
                strategy=SplitStrategy.BY_DOC_TYPE,
                segments=[],
                total_pages=total_pages,
                unassigned_pages=list(range(1, total_pages + 1)),
            )

        # Step 1: Merge ID front+back pairs
        merged = self._merge_id_pairs(classifications)

        # Step 2: Group consecutive pages by (doc_type, owner, statement_period)
        segments: List[SplitSegment] = []
        current_group: List[PageClassification] = [merged[0]]

        for cls in merged[1:]:
            prev = current_group[-1]
            same_type = cls.doc_type == prev.doc_type
            same_owner = cls.detected_owner == prev.detected_owner
            same_period = cls.statement_period == prev.statement_period
            cls_is_blank = cls.is_blank

            # Blank pages act as separators unless sandwiched between
            # pages of the same type
            if cls_is_blank:
                # Look ahead: if next non-blank page matches current group,
                # include the blank page in the current group
                current_group.append(cls)
                continue

            if same_type and same_owner and (same_period or cls.doc_type not in PERIOD_SPLIT_TYPES):
                current_group.append(cls)
            else:
                # Flush current group
                segment = self._group_to_segment(current_group)
                if segment:
                    segments.append(segment)
                current_group = [cls]

        # Flush last group
        segment = self._group_to_segment(current_group)
        if segment:
            segments.append(segment)

        # Determine unassigned pages
        assigned = set()
        for seg in segments:
            assigned.update(seg.pages)
        unassigned = [p for p in range(1, total_pages + 1) if p not in assigned]

        return SplitPlan(
            source_doc_id=doc_id,
            strategy=SplitStrategy.BY_DOC_TYPE,
            segments=segments,
            total_pages=total_pages,
            unassigned_pages=unassigned,
        )

    def _build_plan_by_page_count(
        self,
        doc_id: int,
        total_pages: int,
        pages_per_split: int,
    ) -> SplitPlan:
        """Build a split plan that divides pages into fixed-size chunks."""
        segments: List[SplitSegment] = []
        for i in range(0, total_pages, pages_per_split):
            pages = list(range(i + 1, min(i + pages_per_split, total_pages) + 1))
            segments.append(SplitSegment(
                pages=pages,
                doc_type="OTHER",
                label=f"Pages {pages[0]}-{pages[-1]}",
                owner=None,
                confidence=100,
            ))

        return SplitPlan(
            source_doc_id=doc_id,
            strategy=SplitStrategy.BY_PAGE_COUNT,
            segments=segments,
            total_pages=total_pages,
            unassigned_pages=[],
        )

    def _build_plan_by_blank_page(
        self,
        doc_id: int,
        page_texts: List[str],
        total_pages: int,
    ) -> SplitPlan:
        """Build a split plan using blank pages as separators."""
        segments: List[SplitSegment] = []
        current_pages: List[int] = []
        segment_idx = 0

        for page_idx in range(total_pages):
            page_num = page_idx + 1
            if self._is_blank_page(page_texts[page_idx]):
                # Flush current group
                if current_pages:
                    segment_idx += 1
                    segments.append(SplitSegment(
                        pages=list(current_pages),
                        doc_type="OTHER",
                        label=f"Section {segment_idx}",
                        owner=None,
                        confidence=80,
                    ))
                    current_pages = []
                # Skip the blank page itself
            else:
                current_pages.append(page_num)

        # Flush remaining
        if current_pages:
            segment_idx += 1
            segments.append(SplitSegment(
                pages=list(current_pages),
                doc_type="OTHER",
                label=f"Section {segment_idx}",
                owner=None,
                confidence=80,
            ))

        return SplitPlan(
            source_doc_id=doc_id,
            strategy=SplitStrategy.BY_BLANK_PAGE,
            segments=segments,
            total_pages=total_pages,
            unassigned_pages=[],
        )

    def _build_plan_manual(
        self,
        doc_id: int,
        total_pages: int,
        page_ranges: List[Dict[str, Any]],
    ) -> SplitPlan:
        """Build a split plan from user-specified page ranges.

        Args:
            page_ranges: List of dicts with keys:
                - pages: List[int] (1-based page numbers)
                - doc_type: Optional[str]
                - label: Optional[str]
                - owner: Optional[str]
                - rotation: Optional[Dict[int, int]]  page -> degrees
        """
        segments: List[SplitSegment] = []
        assigned: set = set()

        for i, spec in enumerate(page_ranges):
            pages = sorted(spec.get("pages", []))
            if not pages:
                continue

            # Validate page numbers
            invalid = [p for p in pages if p < 1 or p > total_pages]
            if invalid:
                raise ValueError(
                    f"Invalid page numbers {invalid} for document with {total_pages} pages"
                )

            overlap = assigned & set(pages)
            if overlap:
                raise ValueError(
                    f"Pages {sorted(overlap)} assigned to multiple segments"
                )
            assigned.update(pages)

            segments.append(SplitSegment(
                pages=pages,
                doc_type=spec.get("doc_type", "OTHER"),
                label=spec.get("label", f"Section {i + 1}"),
                owner=spec.get("owner"),
                confidence=100,  # User-specified
                rotation=spec.get("rotation", {}),
            ))

        unassigned = [p for p in range(1, total_pages + 1) if p not in assigned]

        return SplitPlan(
            source_doc_id=doc_id,
            strategy=SplitStrategy.MANUAL,
            segments=segments,
            total_pages=total_pages,
            unassigned_pages=unassigned,
        )

    # ------------------------------------------------------------------
    # Helper: ID pair merging
    # ------------------------------------------------------------------

    def _merge_id_pairs(
        self, classifications: List[PageClassification]
    ) -> List[PageClassification]:
        """Merge front+back ID page pairs into single classifications.

        When an ID-type page is followed by an is_id_back page, mark
        the back page with the same doc_type and a merge annotation.
        The plan builder will group them together.
        """
        if len(classifications) < 2:
            return classifications

        result: List[PageClassification] = []
        skip_next = False

        for i, cls in enumerate(classifications):
            if skip_next:
                skip_next = False
                continue

            # Check if next page is ID back for same doc type
            if (
                i + 1 < len(classifications)
                and cls.doc_type in ID_DOCUMENT_TYPES
                and classifications[i + 1].is_id_back
            ):
                # Keep front page as-is; mark back page with same type
                result.append(cls)
                back = classifications[i + 1]
                result.append(PageClassification(
                    page_number=back.page_number,
                    doc_type=cls.doc_type,
                    confidence=cls.confidence,
                    confidence_level=cls.confidence_level,
                    is_blank=False,
                    is_id_back=True,
                    detected_owner=cls.detected_owner,
                    statement_period=None,
                    text_snippet=back.text_snippet,
                    features={"merged_with_front": cls.page_number},
                ))
                skip_next = True
            else:
                result.append(cls)

        return result

    def _group_to_segment(
        self, group: List[PageClassification]
    ) -> Optional[SplitSegment]:
        """Convert a group of classified pages into a SplitSegment.

        Filters out groups that are entirely blank.
        """
        non_blank = [c for c in group if not c.is_blank]
        if not non_blank:
            return None

        pages = [c.page_number for c in group if not c.is_blank]
        doc_type = non_blank[0].doc_type
        avg_confidence = sum(c.confidence for c in non_blank) // len(non_blank)
        owner = non_blank[0].detected_owner
        period = non_blank[0].statement_period

        # Build label
        label = doc_type
        if period:
            label = f"{doc_type} - {period}"
        if owner:
            label = f"{label} ({owner})"

        has_id_back = any(c.is_id_back for c in group)
        merge_reason = "ID front+back" if has_id_back else None

        return SplitSegment(
            pages=pages,
            doc_type=doc_type,
            label=label,
            owner=owner,
            confidence=avg_confidence,
            merge_reason=merge_reason,
        )

    # ==================================================================
    # PUBLIC API
    # ==================================================================

    async def analyze_document(
        self,
        doc_id: int,
        org_id: int,
        strategy: SplitStrategy = SplitStrategy.AI_AUTO,
        pages_per_split: int = 1,
    ) -> SplitAnalysis:
        """Analyze a multi-page document and propose a split plan.

        Args:
            doc_id: SmartDocument ID to analyze.
            org_id: Organization ID for tenant isolation.
            strategy: Split strategy to apply. AI_AUTO uses AI
                classification to group by document type.
            pages_per_split: Only used with BY_PAGE_COUNT strategy.

        Returns:
            SplitAnalysis with page classifications and proposed plan.

        Raises:
            ValueError: If document not found or org mismatch.
            RuntimeError: If no PDF library is available.
        """
        start_time = time.time()

        # Verify access
        doc_info = self._verify_document_org(doc_id, org_id)

        if doc_info["mime_type"] != "application/pdf":
            raise ValueError(
                f"Document splitting requires PDF format. "
                f"Got: {doc_info['mime_type']}"
            )

        # Download file
        file_bytes = self._fetch_document_bytes(doc_info["storage_key"])
        reader = self._get_pdf_reader(file_bytes)
        total_pages = len(reader.pages)

        # Extract text from all pages
        page_texts = [
            self._extract_page_text(reader, i) for i in range(total_pages)
        ]

        # Classify pages
        if strategy in (SplitStrategy.AI_AUTO, SplitStrategy.BY_DOC_TYPE):
            classifications = self._classify_pages_with_ai(
                file_bytes, page_texts, total_pages
            )
            plan = self._build_plan_by_doc_type(doc_id, classifications, total_pages)
            plan.strategy = (
                SplitStrategy.AI_AUTO
                if strategy == SplitStrategy.AI_AUTO
                else SplitStrategy.BY_DOC_TYPE
            )
        elif strategy == SplitStrategy.BY_PAGE_COUNT:
            classifications = [
                self._rule_based_classify_page(i + 1, page_texts[i])
                for i in range(total_pages)
            ]
            plan = self._build_plan_by_page_count(doc_id, total_pages, pages_per_split)
        elif strategy == SplitStrategy.BY_BLANK_PAGE:
            classifications = [
                self._rule_based_classify_page(i + 1, page_texts[i])
                for i in range(total_pages)
            ]
            plan = self._build_plan_by_blank_page(doc_id, page_texts, total_pages)
        else:
            raise ValueError(f"Unsupported strategy for analysis: {strategy}")

        # Determine if splitting is needed
        detected_types = list({
            c.doc_type for c in classifications
            if not c.is_blank and c.doc_type != "UNKNOWN"
        })
        detected_owners = list({
            c.detected_owner for c in classifications
            if c.detected_owner is not None
        })
        needs_splitting = len(plan.segments) > 1

        duration_ms = int((time.time() - start_time) * 1000)
        model_used = AI_MODEL if self.anthropic else "rule_based"

        return SplitAnalysis(
            source_doc_id=doc_id,
            total_pages=total_pages,
            page_classifications=classifications,
            plan=plan,
            needs_splitting=needs_splitting,
            detected_doc_types=detected_types,
            detected_owners=detected_owners,
            analysis_duration_ms=duration_ms,
            model_used=model_used,
        )

    async def preview_split(
        self,
        doc_id: int,
        split_plan: SplitPlan,
        org_id: int,
    ) -> List[PagePreview]:
        """Generate page previews for a proposed split plan.

        Returns thumbnail images and metadata for each page in each
        segment so the user can visually verify the proposed splits.

        Args:
            doc_id: SmartDocument ID.
            split_plan: The split plan to preview.
            org_id: Organization ID for tenant isolation.

        Returns:
            List of PagePreview objects with thumbnails.
        """
        doc_info = self._verify_document_org(doc_id, org_id)
        file_bytes = self._fetch_document_bytes(doc_info["storage_key"])

        previews: List[PagePreview] = []

        for seg_idx, segment in enumerate(split_plan.segments):
            for page_num in segment.pages:
                rotation = segment.rotation.get(page_num, 0)
                thumbnail = self._generate_thumbnail(
                    file_bytes, page_num, rotation
                )

                # Get page dimensions
                width, height = 612, 792  # Default US Letter
                if _pdf_reader_class:
                    try:
                        reader = self._get_pdf_reader(file_bytes)
                        page = reader.pages[page_num - 1]
                        box = page.mediabox
                        width = int(float(box.width))
                        height = int(float(box.height))
                    except Exception:
                        pass

                previews.append(PagePreview(
                    page_number=page_num,
                    segment_index=seg_idx,
                    doc_type=segment.doc_type,
                    label=segment.label,
                    thumbnail_base64=thumbnail,
                    rotation=rotation,
                    width=width,
                    height=height,
                ))

        return previews

    async def execute_split(
        self,
        doc_id: int,
        split_plan: SplitPlan,
        org_id: int,
        user_id: Optional[int] = None,
    ) -> List[int]:
        """Execute a split plan, creating new SmartDocument records.

        For each segment in the plan:
        1. Extract the specified pages from the source PDF
        2. Apply any page rotations
        3. Write the new PDF to storage
        4. Create a new SmartDocument record linked to the parent
        5. Update the parent document status

        Args:
            doc_id: Source SmartDocument ID.
            split_plan: The plan to execute.
            org_id: Organization ID for tenant isolation.
            user_id: User performing the split (for audit).

        Returns:
            List of new SmartDocument IDs created.

        Raises:
            ValueError: If document not found or org mismatch.
            RuntimeError: If PDF library is unavailable.
        """
        doc_info = self._verify_document_org(doc_id, org_id)

        if not split_plan.segments:
            raise ValueError("Split plan has no segments")

        file_bytes = self._fetch_document_bytes(doc_info["storage_key"])
        reader = self._get_pdf_reader(file_bytes)

        new_doc_ids: List[int] = []

        for segment in split_plan.segments:
            new_id = self._create_split_document(
                reader=reader,
                file_bytes=file_bytes,
                segment=segment,
                source_doc=doc_info,
                org_id=org_id,
                user_id=user_id,
            )
            new_doc_ids.append(new_id)

        # Update parent document to mark as split
        self.db.execute(
            text("""
                UPDATE smart_documents
                SET status = 'SPLIT',
                    updated_at = :now
                WHERE id = :doc_id
            """),
            {"doc_id": doc_id, "now": datetime.now(timezone.utc)},
        )

        # Record parent-child relationships
        for child_id in new_doc_ids:
            self.db.execute(
                text("""
                    INSERT INTO smart_document_splits
                    (parent_doc_id, child_doc_id, split_strategy, created_at, created_by_user_id)
                    VALUES (:parent_id, :child_id, :strategy, :now, :user_id)
                """),
                {
                    "parent_id": doc_id,
                    "child_id": child_id,
                    "strategy": split_plan.strategy.value,
                    "now": datetime.now(timezone.utc),
                    "user_id": user_id,
                },
            )

        self.db.commit()

        logger.info(
            "Split document %d into %d new documents (org=%d, user=%s, strategy=%s)",
            doc_id, len(new_doc_ids), org_id, user_id, split_plan.strategy.value,
        )

        return new_doc_ids

    def _create_split_document(
        self,
        reader: Any,
        file_bytes: bytes,
        segment: SplitSegment,
        source_doc: Dict[str, Any],
        org_id: int,
        user_id: Optional[int],
    ) -> int:
        """Create a new SmartDocument from a split segment.

        Extracts the specified pages, applies rotations, writes to
        storage, and inserts the DB record.

        Returns the new SmartDocument ID.
        """
        # Extract and optionally rotate pages
        pages = []
        for page_num in segment.pages:
            rotation = segment.rotation.get(page_num, 0)
            page = self._build_page_from_reader(reader, page_num - 1, rotation)
            pages.append(page)

        # Write to PDF bytes
        new_pdf_bytes = self._write_pages_to_bytes(pages)
        file_size = len(new_pdf_bytes)
        sha256 = hashlib.sha256(new_pdf_bytes).hexdigest()

        # Generate storage key
        split_uuid = uuid.uuid4().hex[:12]
        base_name = source_doc["file_name"].rsplit(".", 1)[0] if source_doc["file_name"] else "split"
        page_label = (
            f"p{segment.pages[0]}"
            if len(segment.pages) == 1
            else f"p{segment.pages[0]}-{segment.pages[-1]}"
        )
        new_filename = f"{base_name}_{page_label}_{split_uuid}.pdf"
        storage_key = f"org-{org_id}/smart-docs/splits/{source_doc['loan_id']}/{new_filename}"

        # Upload to S3
        if self.s3_service and self.s3_service._s3_available:
            self.s3_service.upload_file(
                file_bytes=new_pdf_bytes,
                storage_key=storage_key,
                content_type="application/pdf",
                metadata={
                    "source_doc_id": str(source_doc["id"]),
                    "pages": json.dumps(segment.pages),
                    "doc_type": segment.doc_type,
                    "sha256": sha256,
                },
            )

        # Insert SmartDocument record
        result = self.db.execute(
            text("""
                INSERT INTO smart_documents (
                    loan_id, borrower_id, file_name, original_filename,
                    mime_type, file_size, storage_key, page_count,
                    doc_type, detected_doc_type, status,
                    assigned_owner, display_name,
                    upload_source, created_at, updated_at
                ) VALUES (
                    :loan_id, :borrower_id, :file_name, :original_filename,
                    'application/pdf', :file_size, :storage_key, :page_count,
                    :doc_type, :detected_doc_type, 'UPLOADED',
                    :assigned_owner, :display_name,
                    'SPLIT', :now, :now
                )
                RETURNING id
            """),
            {
                "loan_id": source_doc["loan_id"],
                "borrower_id": source_doc["borrower_id"],
                "file_name": new_filename,
                "original_filename": source_doc["file_name"],
                "file_size": file_size,
                "storage_key": storage_key,
                "page_count": len(segment.pages),
                "doc_type": segment.doc_type if segment.doc_type != "UNKNOWN" else None,
                "detected_doc_type": segment.doc_type,
                "assigned_owner": segment.owner,
                "display_name": segment.label,
                "now": datetime.now(timezone.utc),
            },
        )
        new_id = result.fetchone()[0]

        return new_id

    async def merge_documents(
        self,
        doc_ids: List[int],
        target_name: str,
        org_id: int,
        user_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        borrower_id: Optional[int] = None,
    ) -> int:
        """Merge multiple documents into a single PDF.

        Used to undo a previous split or combine related documents.

        Args:
            doc_ids: List of SmartDocument IDs to merge (order preserved).
            target_name: Filename for the merged document.
            org_id: Organization ID for tenant isolation.
            user_id: User performing the merge (for audit).
            loan_id: Override loan_id (defaults to first doc's loan_id).
            borrower_id: Override borrower_id (defaults to first doc's).

        Returns:
            New SmartDocument ID for the merged document.

        Raises:
            ValueError: If any document not found, org mismatch, or
                documents belong to different loans.
        """
        if len(doc_ids) < 2:
            raise ValueError("Need at least 2 documents to merge")

        if _pdf_writer_class is None:
            raise RuntimeError("No PDF library available for merging")

        # Verify all documents and collect info
        doc_infos: List[Dict[str, Any]] = []
        for did in doc_ids:
            info = self._verify_document_org(did, org_id)
            doc_infos.append(info)

        # Validate all docs belong to the same loan
        loan_ids = {d["loan_id"] for d in doc_infos}
        if len(loan_ids) > 1 and loan_id is None:
            raise ValueError(
                f"Documents belong to different loans: {loan_ids}. "
                "Specify loan_id to override."
            )

        resolved_loan_id = loan_id or doc_infos[0]["loan_id"]
        resolved_borrower_id = borrower_id or doc_infos[0]["borrower_id"]

        # Merge PDFs
        writer = _pdf_writer_class()
        total_pages = 0

        for doc_info in doc_infos:
            file_bytes = self._fetch_document_bytes(doc_info["storage_key"])
            reader = self._get_pdf_reader(file_bytes)
            for page in reader.pages:
                writer.add_page(page)
                total_pages += 1

        buf = io.BytesIO()
        writer.write(buf)
        merged_bytes = buf.getvalue()

        file_size = len(merged_bytes)
        sha256 = hashlib.sha256(merged_bytes).hexdigest()

        # Storage key
        merge_uuid = uuid.uuid4().hex[:12]
        if not target_name.endswith(".pdf"):
            target_name = f"{target_name}.pdf"
        storage_key = f"org-{org_id}/smart-docs/merged/{resolved_loan_id}/{merge_uuid}_{target_name}"

        # Upload
        if self.s3_service and self.s3_service._s3_available:
            self.s3_service.upload_file(
                file_bytes=merged_bytes,
                storage_key=storage_key,
                content_type="application/pdf",
                metadata={
                    "source_doc_ids": json.dumps(doc_ids),
                    "sha256": sha256,
                    "merge_operation": "true",
                },
            )

        # Insert merged document record
        result = self.db.execute(
            text("""
                INSERT INTO smart_documents (
                    loan_id, borrower_id, file_name, original_filename,
                    mime_type, file_size, storage_key, page_count,
                    status, upload_source, display_name,
                    created_at, updated_at
                ) VALUES (
                    :loan_id, :borrower_id, :file_name, :original_filename,
                    'application/pdf', :file_size, :storage_key, :page_count,
                    'UPLOADED', 'MERGE', :display_name,
                    :now, :now
                )
                RETURNING id
            """),
            {
                "loan_id": resolved_loan_id,
                "borrower_id": resolved_borrower_id,
                "file_name": target_name,
                "original_filename": target_name,
                "file_size": file_size,
                "storage_key": storage_key,
                "page_count": total_pages,
                "display_name": target_name.rsplit(".", 1)[0],
                "now": datetime.now(timezone.utc),
            },
        )
        merged_id = result.fetchone()[0]

        # Record merge relationships
        for source_id in doc_ids:
            self.db.execute(
                text("""
                    INSERT INTO smart_document_splits
                    (parent_doc_id, child_doc_id, split_strategy, created_at, created_by_user_id)
                    VALUES (:child_id, :merged_id, 'MERGE', :now, :user_id)
                """),
                {
                    "child_id": source_id,
                    "merged_id": merged_id,
                    "now": datetime.now(timezone.utc),
                    "user_id": user_id,
                },
            )

        # Mark source documents as merged
        for source_id in doc_ids:
            self.db.execute(
                text("""
                    UPDATE smart_documents
                    SET status = 'MERGED', updated_at = :now
                    WHERE id = :doc_id
                """),
                {"doc_id": source_id, "now": datetime.now(timezone.utc)},
            )

        self.db.commit()

        logger.info(
            "Merged %d documents into new document %d (org=%d, user=%s)",
            len(doc_ids), merged_id, org_id, user_id,
        )

        return merged_id

    async def auto_split_and_classify(
        self,
        doc_id: int,
        org_id: int,
        user_id: Optional[int] = None,
    ) -> List[SplitResult]:
        """Analyze, split, classify, and OCR a document in one pass.

        This is the primary entry point for fully automated splitting.
        If the document contains only one document type, no split is
        performed and a single result is returned with the classification
        applied to the original document.

        Args:
            doc_id: SmartDocument ID to process.
            org_id: Organization ID for tenant isolation.
            user_id: User ID for audit trail.

        Returns:
            List of SplitResult objects for each resulting document.
        """
        # Step 1: Analyze
        analysis = await self.analyze_document(
            doc_id=doc_id, org_id=org_id, strategy=SplitStrategy.AI_AUTO
        )

        results: List[SplitResult] = []

        if not analysis.needs_splitting:
            # Single document type -- apply classification to original
            # without splitting
            doc_info = self._verify_document_org(doc_id, org_id)
            primary_type = (
                analysis.detected_doc_types[0]
                if analysis.detected_doc_types
                else "OTHER"
            )
            avg_confidence = (
                sum(c.confidence for c in analysis.page_classifications)
                // len(analysis.page_classifications)
                if analysis.page_classifications
                else 0
            )

            # Update classification on original document
            self.db.execute(
                text("""
                    UPDATE smart_documents
                    SET doc_type = :doc_type,
                        detected_doc_type = :doc_type,
                        updated_at = :now
                    WHERE id = :doc_id
                """),
                {
                    "doc_id": doc_id,
                    "doc_type": primary_type,
                    "now": datetime.now(timezone.utc),
                },
            )
            self.db.commit()

            results.append(SplitResult(
                new_doc_id=doc_id,
                source_doc_id=doc_id,
                pages=list(range(1, analysis.total_pages + 1)),
                doc_type=primary_type,
                label=primary_type,
                owner=analysis.detected_owners[0] if analysis.detected_owners else None,
                page_count=analysis.total_pages,
                file_size=0,  # Original file, size unchanged
                storage_key=doc_info["storage_key"],
                classification_confidence=avg_confidence,
                classification_applied=True,
            ))

            return results

        # Step 2: Execute split
        new_ids = await self.execute_split(
            doc_id=doc_id,
            split_plan=analysis.plan,
            org_id=org_id,
            user_id=user_id,
        )

        # Step 3: Build results with classification info from the plan
        for new_id, segment in zip(new_ids, analysis.plan.segments):
            # Fetch the created document info
            row = self.db.execute(
                text("""
                    SELECT file_size, storage_key, page_count
                    FROM smart_documents WHERE id = :doc_id
                """),
                {"doc_id": new_id},
            ).fetchone()

            results.append(SplitResult(
                new_doc_id=new_id,
                source_doc_id=doc_id,
                pages=segment.pages,
                doc_type=segment.doc_type,
                label=segment.label,
                owner=segment.owner,
                page_count=row.page_count if row else len(segment.pages),
                file_size=row.file_size if row else 0,
                storage_key=row.storage_key if row else "",
                classification_confidence=segment.confidence,
                classification_applied=True,
            ))

        # Step 4: Queue post-split processing (OCR + review pipeline)
        # for each new document
        for new_id in new_ids:
            self._queue_post_split_processing(new_id, org_id)

        return results

    def _queue_post_split_processing(self, doc_id: int, org_id: int) -> None:
        """Queue a split child document for OCR and review processing.

        Inserts a processing queue record so the background worker picks
        up the document for the standard review pipeline (screenshot
        detection, OCR, freshness validation, etc.).
        """
        try:
            self.db.execute(
                text("""
                    INSERT INTO smart_docs_processing_queue
                    (document_id, organization_id, status, priority, created_at)
                    VALUES (:doc_id, :org_id, 'PENDING', 'NORMAL', :now)
                    ON CONFLICT (document_id) DO NOTHING
                """),
                {
                    "doc_id": doc_id,
                    "org_id": org_id,
                    "now": datetime.now(timezone.utc),
                },
            )
        except Exception as e:
            # Queue table may not exist yet -- log and continue.
            # The document can still be processed manually.
            logger.warning(
                "Could not queue document %d for post-split processing: %s",
                doc_id, e,
            )

    async def undo_split(
        self,
        parent_doc_id: int,
        org_id: int,
        user_id: Optional[int] = None,
    ) -> int:
        """Undo a previous split by re-merging child documents.

        Finds all child documents created from the given parent, merges
        them back in page order, and restores the parent document status.

        Args:
            parent_doc_id: The original document that was split.
            org_id: Organization ID for tenant isolation.
            user_id: User performing the undo (for audit).

        Returns:
            The parent document ID (restored).

        Raises:
            ValueError: If parent not found, not in SPLIT status, or
                no children found.
        """
        doc_info = self._verify_document_org(parent_doc_id, org_id)

        if doc_info["status"] != "SPLIT":
            raise ValueError(
                f"Document {parent_doc_id} is not in SPLIT status "
                f"(current: {doc_info['status']})"
            )

        # Find child documents
        children = self.db.execute(
            text("""
                SELECT child_doc_id
                FROM smart_document_splits
                WHERE parent_doc_id = :parent_id
                ORDER BY child_doc_id ASC
            """),
            {"parent_id": parent_doc_id},
        ).fetchall()

        if not children:
            raise ValueError(f"No split children found for document {parent_doc_id}")

        child_ids = [row.child_doc_id for row in children]

        # Mark children as archived
        for child_id in child_ids:
            self.db.execute(
                text("""
                    UPDATE smart_documents
                    SET status = 'ARCHIVED', updated_at = :now
                    WHERE id = :doc_id
                """),
                {"doc_id": child_id, "now": datetime.now(timezone.utc)},
            )

        # Restore parent document status
        self.db.execute(
            text("""
                UPDATE smart_documents
                SET status = 'UPLOADED', updated_at = :now
                WHERE id = :parent_id
            """),
            {"parent_id": parent_doc_id, "now": datetime.now(timezone.utc)},
        )

        # Clean up split records
        self.db.execute(
            text("""
                DELETE FROM smart_document_splits
                WHERE parent_doc_id = :parent_id
            """),
            {"parent_id": parent_doc_id},
        )

        self.db.commit()

        logger.info(
            "Undid split of document %d, archived %d children (org=%d, user=%s)",
            parent_doc_id, len(child_ids), org_id, user_id,
        )

        return parent_doc_id

    async def reorder_pages(
        self,
        doc_id: int,
        new_page_order: List[int],
        org_id: int,
        user_id: Optional[int] = None,
    ) -> int:
        """Reorder pages within a document (creates a new version).

        Args:
            doc_id: SmartDocument ID to reorder.
            new_page_order: List of 1-based page numbers in desired order.
                Must contain all pages exactly once.
            org_id: Organization ID for tenant isolation.
            user_id: User performing the reorder (for audit).

        Returns:
            The document ID (same document, updated in place).

        Raises:
            ValueError: If page list is invalid or incomplete.
        """
        doc_info = self._verify_document_org(doc_id, org_id)
        file_bytes = self._fetch_document_bytes(doc_info["storage_key"])
        reader = self._get_pdf_reader(file_bytes)
        total_pages = len(reader.pages)

        # Validate page order
        if sorted(new_page_order) != list(range(1, total_pages + 1)):
            raise ValueError(
                f"new_page_order must contain each page from 1 to {total_pages} exactly once. "
                f"Got: {new_page_order}"
            )

        # Build reordered PDF
        pages = [reader.pages[p - 1] for p in new_page_order]
        new_bytes = self._write_pages_to_bytes(pages)

        # Upload replacement
        storage_key = doc_info["storage_key"]
        if self.s3_service and self.s3_service._s3_available:
            self.s3_service.upload_file(
                file_bytes=new_bytes,
                storage_key=storage_key,
                content_type="application/pdf",
                metadata={"reordered": "true", "page_order": json.dumps(new_page_order)},
            )

        # Update file size
        self.db.execute(
            text("""
                UPDATE smart_documents
                SET file_size = :file_size, updated_at = :now
                WHERE id = :doc_id
            """),
            {
                "doc_id": doc_id,
                "file_size": len(new_bytes),
                "now": datetime.now(timezone.utc),
            },
        )
        self.db.commit()

        logger.info(
            "Reordered pages for document %d: %s (org=%d, user=%s)",
            doc_id, new_page_order, org_id, user_id,
        )

        return doc_id

    async def rotate_pages(
        self,
        doc_id: int,
        rotations: Dict[int, int],
        org_id: int,
        user_id: Optional[int] = None,
    ) -> int:
        """Rotate specific pages within a document.

        Args:
            doc_id: SmartDocument ID.
            rotations: Dict mapping 1-based page number to clockwise
                rotation degrees (must be multiple of 90).
            org_id: Organization ID for tenant isolation.
            user_id: User performing the rotation (for audit).

        Returns:
            The document ID.
        """
        doc_info = self._verify_document_org(doc_id, org_id)
        file_bytes = self._fetch_document_bytes(doc_info["storage_key"])
        reader = self._get_pdf_reader(file_bytes)
        total_pages = len(reader.pages)

        # Validate
        for page_num, degrees in rotations.items():
            if page_num < 1 or page_num > total_pages:
                raise ValueError(f"Invalid page number: {page_num}")
            if degrees % 90 != 0:
                raise ValueError(f"Rotation must be multiple of 90: {degrees}")

        # Build rotated PDF
        pages = []
        for i in range(total_pages):
            page = reader.pages[i]
            rotation = rotations.get(i + 1, 0)
            if rotation:
                page = page.rotate(rotation)
            pages.append(page)

        new_bytes = self._write_pages_to_bytes(pages)

        # Upload replacement
        storage_key = doc_info["storage_key"]
        if self.s3_service and self.s3_service._s3_available:
            self.s3_service.upload_file(
                file_bytes=new_bytes,
                storage_key=storage_key,
                content_type="application/pdf",
                metadata={"rotated_pages": json.dumps(rotations)},
            )

        self.db.execute(
            text("""
                UPDATE smart_documents
                SET file_size = :file_size, updated_at = :now
                WHERE id = :doc_id
            """),
            {
                "doc_id": doc_id,
                "file_size": len(new_bytes),
                "now": datetime.now(timezone.utc),
            },
        )
        self.db.commit()

        logger.info(
            "Rotated pages %s for document %d (org=%d)",
            rotations, doc_id, org_id,
        )

        return doc_id

    async def get_split_history(
        self,
        doc_id: int,
        org_id: int,
    ) -> Dict[str, Any]:
        """Get the split/merge history for a document.

        Returns the full tree: if doc_id was a parent that was split,
        returns all children. If doc_id was a child created by split,
        returns the parent and siblings.

        Args:
            doc_id: SmartDocument ID.
            org_id: Organization ID for tenant isolation.

        Returns:
            Dict with parent, children, and strategy information.
        """
        self._verify_document_org(doc_id, org_id)

        # Check if this document is a parent (was split)
        children = self.db.execute(
            text("""
                SELECT sds.child_doc_id, sds.split_strategy, sds.created_at,
                       sd.file_name, sd.doc_type, sd.status, sd.page_count
                FROM smart_document_splits sds
                JOIN smart_documents sd ON sd.id = sds.child_doc_id
                WHERE sds.parent_doc_id = :doc_id
                ORDER BY sds.child_doc_id
            """),
            {"doc_id": doc_id},
        ).fetchall()

        # Check if this document is a child (created by split)
        parent = self.db.execute(
            text("""
                SELECT sds.parent_doc_id, sds.split_strategy, sds.created_at,
                       sd.file_name, sd.doc_type, sd.status, sd.page_count
                FROM smart_document_splits sds
                JOIN smart_documents sd ON sd.id = sds.parent_doc_id
                WHERE sds.child_doc_id = :doc_id
            """),
            {"doc_id": doc_id},
        ).fetchone()

        result: Dict[str, Any] = {
            "doc_id": doc_id,
            "is_parent": len(children) > 0,
            "is_child": parent is not None,
            "children": [
                {
                    "doc_id": c.child_doc_id,
                    "file_name": c.file_name,
                    "doc_type": c.doc_type,
                    "status": c.status,
                    "page_count": c.page_count,
                    "strategy": c.split_strategy,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in children
            ],
            "parent": None,
        }

        if parent:
            result["parent"] = {
                "doc_id": parent.parent_doc_id,
                "file_name": parent.file_name,
                "doc_type": parent.doc_type,
                "status": parent.status,
                "page_count": parent.page_count,
                "strategy": parent.split_strategy,
                "created_at": parent.created_at.isoformat() if parent.created_at else None,
            }

            # Also fetch siblings
            siblings = self.db.execute(
                text("""
                    SELECT sds.child_doc_id, sd.file_name, sd.doc_type, sd.status, sd.page_count
                    FROM smart_document_splits sds
                    JOIN smart_documents sd ON sd.id = sds.child_doc_id
                    WHERE sds.parent_doc_id = :parent_id AND sds.child_doc_id != :doc_id
                    ORDER BY sds.child_doc_id
                """),
                {"parent_id": parent.parent_doc_id, "doc_id": doc_id},
            ).fetchall()

            result["siblings"] = [
                {
                    "doc_id": s.child_doc_id,
                    "file_name": s.file_name,
                    "doc_type": s.doc_type,
                    "status": s.status,
                    "page_count": s.page_count,
                }
                for s in siblings
            ]

        return result


# =============================================================================
# KEYWORD RULES (lazy loaded from ai_classifier_service to avoid import cycle)
# =============================================================================

_keyword_rules_cache: Optional[Dict[str, List[Tuple[str, int]]]] = None


def _get_keyword_rules() -> Dict[str, List[Tuple[str, int]]]:
    """Lazy-load keyword rules from ai_classifier_service.

    Falls back to a minimal built-in set if the import fails.
    """
    global _keyword_rules_cache
    if _keyword_rules_cache is not None:
        return _keyword_rules_cache

    try:
        from services.smart_docs.ai_classifier_service import KEYWORD_RULES
        _keyword_rules_cache = KEYWORD_RULES
    except ImportError:
        logger.warning(
            "Could not import KEYWORD_RULES from ai_classifier_service; "
            "using minimal built-in rules."
        )
        _keyword_rules_cache = {
            "PAYSTUB": [
                ("pay period", 15), ("gross pay", 15), ("net pay", 15),
                ("ytd", 12), ("earnings statement", 15), ("pay stub", 20),
                ("pay date", 12), ("deductions", 8),
            ],
            "W2": [
                ("wage and tax statement", 25), ("form w-2", 25),
                ("w-2", 20), ("employer identification number", 15),
            ],
            "TAX_RETURN": [
                ("form 1040", 25), ("adjusted gross income", 20),
                ("tax return", 18), ("taxable income", 12),
            ],
            "BANK_STATEMENT": [
                ("account summary", 15), ("beginning balance", 15),
                ("ending balance", 15), ("statement period", 15),
                ("checking", 10), ("savings", 10), ("deposits", 8),
                ("withdrawals", 8), ("account number", 10),
            ],
            "DRIVERS_LICENSE": [
                ("driver license", 25), ("driver's license", 25),
                ("date of birth", 10), ("dob", 8), ("exp", 5),
                ("class", 5), ("restrictions", 5),
            ],
            "PURCHASE_CONTRACT": [
                ("purchase agreement", 20), ("purchase contract", 20),
                ("buyer", 10), ("seller", 10), ("purchase price", 15),
                ("earnest money", 12), ("closing date", 10),
            ],
            "APPRAISAL": [
                ("appraisal", 20), ("appraised value", 25),
                ("market value", 15), ("comparable", 10),
                ("subject property", 12),
            ],
            "HOMEOWNERS_INSURANCE": [
                ("homeowners insurance", 25), ("insurance policy", 15),
                ("coverage", 10), ("premium", 10), ("dwelling", 8),
            ],
        }

    return _keyword_rules_cache


# =============================================================================
# FACTORY
# =============================================================================

def get_document_splitting_service(db: Session) -> DocumentSplittingService:
    """Factory function for DocumentSplittingService.

    Args:
        db: SQLAlchemy session.

    Returns:
        DocumentSplittingService instance.
    """
    return DocumentSplittingService(db=db)
