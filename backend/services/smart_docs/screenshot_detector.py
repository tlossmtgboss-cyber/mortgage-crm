"""
Smart Document Collection - Screenshot Detector

Three-layer screenshot detection system:
1. Metadata Layer: Check EXIF/PDF metadata for screenshot indicators
2. Visual Heuristics: Analyze image dimensions, aspect ratios, UI elements
3. OCR/Semantic Layer: Detect UI text patterns (battery, wifi, time formats)

Each layer returns a confidence score; combined for final decision.
"""

import logging
import re
from io import BytesIO
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Optional imports - graceful degradation if not installed
try:
    from PIL import Image, ExifTags
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL not installed - image analysis disabled")

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract not installed - OCR disabled")

try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    logger.warning("pdf2image not installed - PDF to image disabled")


class DetectionLayer(str, Enum):
    """Detection layer identifiers."""
    METADATA = "metadata"
    VISUAL = "visual"
    OCR = "ocr"


@dataclass
class LayerResult:
    """Result from a single detection layer."""
    layer: DetectionLayer
    is_screenshot: bool
    confidence: float
    reasons: List[str]
    details: Dict[str, Any]


@dataclass
class ScreenshotDetectionResult:
    """Combined result from all detection layers."""
    is_screenshot: bool
    confidence: float
    reasons: List[str]
    layer_results: List[LayerResult]
    recommendation: str  # "accept", "reject", "needs_review"


class ScreenshotDetector:
    """
    Multi-layer screenshot detection for uploaded documents.

    Detects screenshots through three complementary approaches:
    1. Metadata analysis (EXIF, PDF producer)
    2. Visual heuristics (dimensions, aspect ratio)
    3. OCR semantic analysis (UI text patterns)
    """

    # Common screenshot software signatures
    SCREENSHOT_SOFTWARE = [
        "screenshot", "snipping", "snagit", "lightshot", "greenshot",
        "sharex", "gyazo", "monosnap", "skitch", "grab", "spectacle",
        "flameshot", "ksnip", "screenpresso", "snip & sketch",
    ]

    # Device screenshot patterns in metadata
    DEVICE_PATTERNS = [
        r"iphone", r"ipad", r"android", r"samsung", r"pixel",
        r"screenshot", r"screen capture", r"screen shot",
    ]

    # Common mobile screen resolutions (width x height)
    MOBILE_RESOLUTIONS = [
        (1170, 2532),  # iPhone 12/13
        (1284, 2778),  # iPhone 12/13 Pro Max
        (1125, 2436),  # iPhone X/XS/11 Pro
        (1242, 2688),  # iPhone XS Max/11 Pro Max
        (1080, 2340),  # Common Android
        (1440, 3200),  # Samsung Galaxy S21
        (1080, 1920),  # Common FHD
        (1440, 2560),  # Common QHD
        (750, 1334),   # iPhone 8
        (828, 1792),   # iPhone XR/11
    ]

    # Desktop screenshot aspect ratios
    DESKTOP_ASPECTS = [
        (16, 9),   # Common widescreen
        (16, 10),  # MacBook
        (4, 3),    # Old monitors
        (21, 9),   # Ultrawide
    ]

    # UI text patterns (indicates screenshot of app/website)
    UI_PATTERNS = [
        r"\b\d{1,2}:\d{2}\s*(AM|PM|am|pm)?\b",  # Time format
        r"\b\d{1,2}%\b",  # Battery percentage
        r"\bwi-?fi\b",
        r"\bsignal\b",
        r"\b(back|home|menu)\b",
        r"\b(settings|profile|account)\b",
        r"\b(log\s*out|sign\s*out|logout)\b",
        r"\b(download|upload|share)\b",
        r"@[a-zA-Z0-9_]+",  # Social handles
        r"https?://",  # URLs
        r"\bchrome\b|\bsafari\b|\bfirefox\b|\bedge\b",  # Browsers
    ]

    # Thresholds
    CONFIDENCE_THRESHOLD = 0.7  # Above this = reject
    REVIEW_THRESHOLD = 0.4  # Between this and confidence = review

    def __init__(self):
        """Initialize the screenshot detector."""
        self._check_dependencies()

    def _check_dependencies(self):
        """Check and log available dependencies."""
        deps = {
            "PIL": PIL_AVAILABLE,
            "pytesseract": TESSERACT_AVAILABLE,
            "pdf2image": PDF2IMAGE_AVAILABLE,
        }
        available = [k for k, v in deps.items() if v]
        missing = [k for k, v in deps.items() if not v]

        if missing:
            logger.warning(f"Screenshot detector missing deps: {missing}")
        logger.info(f"Screenshot detector initialized with: {available}")

    def detect(
        self,
        file_content: bytes,
        mime_type: str,
        filename: Optional[str] = None,
    ) -> ScreenshotDetectionResult:
        """
        Detect if the uploaded file is a screenshot.

        Args:
            file_content: Raw file bytes
            mime_type: MIME type of the file
            filename: Optional filename for additional hints

        Returns:
            ScreenshotDetectionResult with combined analysis
        """
        layer_results = []

        # Convert PDF to image if needed
        if mime_type == "application/pdf":
            image, pdf_metadata = self._extract_from_pdf(file_content)
            if pdf_metadata:
                # Check PDF metadata first
                pdf_result = self._analyze_pdf_metadata(pdf_metadata)
                layer_results.append(pdf_result)
        else:
            image = self._load_image(file_content)
            pdf_metadata = None

        if image:
            # Layer 1: Metadata analysis
            metadata_result = self._analyze_metadata(image, filename)
            layer_results.append(metadata_result)

            # Layer 2: Visual heuristics
            visual_result = self._analyze_visual(image)
            layer_results.append(visual_result)

            # Layer 3: OCR semantic analysis
            if TESSERACT_AVAILABLE:
                ocr_result = self._analyze_ocr(image)
                layer_results.append(ocr_result)

        # Combine results
        return self._combine_results(layer_results)

    def _load_image(self, file_content: bytes) -> Optional["Image.Image"]:
        """Load image from bytes."""
        if not PIL_AVAILABLE:
            return None

        try:
            return Image.open(BytesIO(file_content))
        except Exception as e:
            logger.warning(f"Failed to load image: {e}")
            return None

    def _extract_from_pdf(
        self,
        file_content: bytes
    ) -> Tuple[Optional["Image.Image"], Optional[Dict]]:
        """Extract first page image and metadata from PDF."""
        if not PDF2IMAGE_AVAILABLE:
            return None, None

        try:
            # Extract first page as image
            images = convert_from_bytes(file_content, first_page=1, last_page=1)
            image = images[0] if images else None

            # Try to extract PDF metadata
            metadata = {}
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(stream=file_content, filetype="pdf")
                metadata = doc.metadata
                doc.close()
            except ImportError:
                pass
            except Exception as e:
                logger.debug(f"Could not extract PDF metadata: {e}")

            return image, metadata

        except Exception as e:
            logger.warning(f"Failed to extract from PDF: {e}")
            return None, None

    def _analyze_pdf_metadata(self, metadata: Dict) -> LayerResult:
        """Analyze PDF metadata for screenshot indicators."""
        reasons = []
        confidence = 0.0

        producer = (metadata.get("producer") or "").lower()
        creator = (metadata.get("creator") or "").lower()
        title = (metadata.get("title") or "").lower()

        # Check for screenshot software
        for software in self.SCREENSHOT_SOFTWARE:
            if software in producer or software in creator:
                reasons.append(f"Created by screenshot software: {software}")
                confidence = max(confidence, 0.9)

        # Check for device patterns
        combined = f"{producer} {creator} {title}"
        for pattern in self.DEVICE_PATTERNS:
            if re.search(pattern, combined, re.IGNORECASE):
                reasons.append(f"Device screenshot pattern detected")
                confidence = max(confidence, 0.8)
                break

        return LayerResult(
            layer=DetectionLayer.METADATA,
            is_screenshot=confidence >= 0.5,
            confidence=confidence,
            reasons=reasons,
            details={"metadata": metadata},
        )

    def _analyze_metadata(
        self,
        image: "Image.Image",
        filename: Optional[str] = None
    ) -> LayerResult:
        """Analyze image metadata (EXIF) for screenshot indicators."""
        reasons = []
        confidence = 0.0

        # Check filename patterns
        if filename:
            filename_lower = filename.lower()
            if any(p in filename_lower for p in ["screenshot", "screen shot", "screen_shot"]):
                reasons.append("Filename contains 'screenshot'")
                confidence = max(confidence, 0.85)

            # Check for date-based screenshot naming (e.g., "Screenshot 2024-01-15")
            if re.search(r"screenshot.*\d{4}[-_]\d{2}[-_]\d{2}", filename_lower):
                reasons.append("Screenshot date pattern in filename")
                confidence = max(confidence, 0.9)

            # Check for iOS screenshot naming (IMG_xxxx)
            if re.match(r"img_\d{4}", filename_lower):
                reasons.append("iOS-style image naming")
                confidence = max(confidence, 0.4)

        # Check EXIF data
        try:
            exif = image._getexif()
            if exif:
                for tag_id, value in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    if isinstance(value, str):
                        value_lower = value.lower()
                        for pattern in self.DEVICE_PATTERNS:
                            if re.search(pattern, value_lower):
                                reasons.append(f"EXIF contains device pattern: {tag}")
                                confidence = max(confidence, 0.7)

                        for software in self.SCREENSHOT_SOFTWARE:
                            if software in value_lower:
                                reasons.append(f"EXIF shows screenshot software: {value}")
                                confidence = max(confidence, 0.85)
        except Exception as e:
            logger.debug(f"Could not read EXIF: {e}")

        return LayerResult(
            layer=DetectionLayer.METADATA,
            is_screenshot=confidence >= 0.5,
            confidence=confidence,
            reasons=reasons,
            details={"filename": filename},
        )

    def _analyze_visual(self, image: "Image.Image") -> LayerResult:
        """Analyze visual characteristics of the image."""
        reasons = []
        confidence = 0.0

        width, height = image.size

        # Check for exact mobile resolution match
        for mobile_res in self.MOBILE_RESOLUTIONS:
            if (width, height) == mobile_res or (height, width) == mobile_res:
                reasons.append(f"Matches mobile screen resolution: {mobile_res}")
                confidence = max(confidence, 0.75)
                break

        # Check aspect ratio for desktop screenshots
        if width > height:  # Landscape
            aspect = width / height
            for w, h in self.DESKTOP_ASPECTS:
                if abs(aspect - (w / h)) < 0.02:
                    reasons.append(f"Matches desktop aspect ratio: {w}:{h}")
                    confidence = max(confidence, 0.5)
                    break

        # Very wide aspect ratios are suspicious (likely cropped screenshot)
        aspect = width / height if height > 0 else 0
        if aspect > 3 or aspect < 0.3:
            reasons.append(f"Unusual aspect ratio: {aspect:.2f}")
            confidence = max(confidence, 0.4)

        # Check for status bar height (mobile screenshots often have 44-88px headers)
        # This would require more sophisticated analysis

        # Check color depth / mode
        if image.mode == "RGB" and self._has_solid_header(image):
            reasons.append("Solid color header detected (possible status bar)")
            confidence = max(confidence, 0.6)

        return LayerResult(
            layer=DetectionLayer.VISUAL,
            is_screenshot=confidence >= 0.5,
            confidence=confidence,
            reasons=reasons,
            details={"width": width, "height": height, "mode": image.mode},
        )

    def _has_solid_header(self, image: "Image.Image", header_height: int = 50) -> bool:
        """Check if image has a solid color header (like a status bar)."""
        try:
            # Get top pixels
            header = image.crop((0, 0, image.width, min(header_height, image.height)))

            # Sample pixels
            pixels = list(header.getdata())
            if not pixels:
                return False

            # Check if most pixels are similar (solid color)
            first_pixel = pixels[0]
            similar_count = sum(
                1 for p in pixels[:1000]  # Sample first 1000
                if self._colors_similar(p, first_pixel)
            )

            return similar_count / min(len(pixels), 1000) > 0.9

        except Exception as e:
            logger.debug(f"Header analysis failed: {e}")
            return False

    def _colors_similar(
        self,
        c1: Tuple,
        c2: Tuple,
        threshold: int = 10
    ) -> bool:
        """Check if two colors are similar."""
        if len(c1) != len(c2):
            return False
        return all(abs(a - b) <= threshold for a, b in zip(c1, c2))

    def _analyze_ocr(self, image: "Image.Image") -> LayerResult:
        """Use OCR to detect UI text patterns."""
        reasons = []
        confidence = 0.0
        detected_patterns = []

        try:
            # Run OCR
            text = pytesseract.image_to_string(image)

            # Check for UI patterns
            pattern_count = 0
            for pattern in self.UI_PATTERNS:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    pattern_count += 1
                    detected_patterns.append({
                        "pattern": pattern,
                        "matches": matches[:3],  # Limit stored matches
                    })

            # Multiple UI patterns strongly suggest screenshot
            if pattern_count >= 3:
                reasons.append(f"Multiple UI patterns detected ({pattern_count})")
                confidence = max(confidence, 0.8)
            elif pattern_count >= 2:
                reasons.append(f"UI patterns detected ({pattern_count})")
                confidence = max(confidence, 0.6)
            elif pattern_count >= 1:
                reasons.append(f"Possible UI pattern detected")
                confidence = max(confidence, 0.3)

            # Check for very short text (might be labels/buttons)
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            short_lines = [l for l in lines if len(l) < 20]
            if len(short_lines) > 5 and len(short_lines) / max(len(lines), 1) > 0.7:
                reasons.append("Many short text lines (UI-like)")
                confidence = max(confidence, 0.5)

        except Exception as e:
            logger.warning(f"OCR analysis failed: {e}")

        return LayerResult(
            layer=DetectionLayer.OCR,
            is_screenshot=confidence >= 0.5,
            confidence=confidence,
            reasons=reasons,
            details={"patterns_found": detected_patterns},
        )

    def _combine_results(
        self,
        layer_results: List[LayerResult]
    ) -> ScreenshotDetectionResult:
        """Combine results from all layers into final decision."""
        if not layer_results:
            return ScreenshotDetectionResult(
                is_screenshot=False,
                confidence=0.0,
                reasons=["No analysis could be performed"],
                layer_results=[],
                recommendation="needs_review",
            )

        # Weight the layers
        weights = {
            DetectionLayer.METADATA: 0.35,
            DetectionLayer.VISUAL: 0.25,
            DetectionLayer.OCR: 0.40,
        }

        total_weight = 0.0
        weighted_confidence = 0.0
        all_reasons = []

        for result in layer_results:
            weight = weights.get(result.layer, 0.25)
            total_weight += weight
            weighted_confidence += result.confidence * weight
            all_reasons.extend(result.reasons)

        # Normalize
        final_confidence = weighted_confidence / total_weight if total_weight > 0 else 0

        # Boost confidence if multiple layers agree
        agreeing_layers = sum(1 for r in layer_results if r.is_screenshot)
        if agreeing_layers >= 2:
            final_confidence = min(final_confidence * 1.2, 1.0)

        # Determine recommendation
        if final_confidence >= self.CONFIDENCE_THRESHOLD:
            recommendation = "reject"
        elif final_confidence >= self.REVIEW_THRESHOLD:
            recommendation = "needs_review"
        else:
            recommendation = "accept"

        return ScreenshotDetectionResult(
            is_screenshot=final_confidence >= self.CONFIDENCE_THRESHOLD,
            confidence=round(final_confidence, 3),
            reasons=all_reasons,
            layer_results=layer_results,
            recommendation=recommendation,
        )

    def result_to_dict(self, result: ScreenshotDetectionResult) -> Dict[str, Any]:
        """Convert result to dictionary for storage/API."""
        return {
            "is_screenshot": result.is_screenshot,
            "confidence": result.confidence,
            "reasons": result.reasons,
            "recommendation": result.recommendation,
            "layer_results": [
                {
                    "layer": lr.layer.value,
                    "is_screenshot": lr.is_screenshot,
                    "confidence": lr.confidence,
                    "reasons": lr.reasons,
                }
                for lr in result.layer_results
            ],
        }
