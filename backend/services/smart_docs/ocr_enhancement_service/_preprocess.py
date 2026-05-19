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


# AdvancedImagePreprocessor

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

