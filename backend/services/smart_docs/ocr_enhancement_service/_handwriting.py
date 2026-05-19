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


# HandwritingDetector

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
