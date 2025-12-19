"""
Smart Document Collection - Date Extractor

Extracts dates from documents using OCR and pattern matching.
Identifies key dates for mortgage documents:
- Pay dates and period end dates (paystubs)
- Statement dates and period end dates (bank statements)
- Tax year (tax returns)
- Document dates (general)
"""

import logging
import re
from datetime import datetime, date
from io import BytesIO
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Optional imports
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False


@dataclass
class ExtractedDate:
    """A single extracted date with context."""
    date: date
    date_type: str  # pay_date, period_start, period_end, statement_date, tax_year, etc.
    confidence: float
    source_text: str
    context: Optional[str] = None


@dataclass
class DateExtractionResult:
    """Result of date extraction from a document."""
    primary_date: Optional[date]
    primary_date_type: Optional[str]
    all_dates: List[ExtractedDate]
    confidence: float
    ocr_text: str
    extracted_data: Dict[str, Any]


class DateExtractor:
    """
    Extracts dates from mortgage-related documents using OCR and pattern matching.

    Specialized for:
    - Paystubs: Pay date, period start, period end
    - Bank statements: Statement date, period start, period end
    - Tax returns: Tax year
    - W-2s: Tax year
    - General documents: Any dates found
    """

    # Date patterns (regex)
    DATE_PATTERNS = [
        # MM/DD/YYYY or MM-DD-YYYY
        (r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", "mdy"),
        # YYYY-MM-DD (ISO format)
        (r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", "ymd"),
        # Month DD, YYYY
        (r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(20\d{2})\b", "text_mdy"),
        # DD Month YYYY
        (r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b", "text_dmy"),
        # Mon DD, YYYY (abbreviated)
        (r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d{2})\b", "text_mdy_abbrev"),
    ]

    # Context patterns for date types
    DATE_CONTEXT_PATTERNS = {
        "pay_date": [
            r"pay\s*date",
            r"check\s*date",
            r"payment\s*date",
            r"date\s*paid",
            r"paid\s*on",
        ],
        "period_end": [
            r"period\s*end",
            r"pay\s*period.*end",
            r"ending",
            r"through",
            r"thru",
            r"to\s*date",
        ],
        "period_start": [
            r"period\s*start",
            r"pay\s*period.*begin",
            r"beginning",
            r"from\s*date",
        ],
        "statement_date": [
            r"statement\s*date",
            r"statement\s*period",
            r"as\s*of",
            r"closing\s*date",
        ],
        "statement_end": [
            r"statement\s*period.*end",
            r"ending\s*balance",
            r"period.*through",
        ],
        "tax_year": [
            r"tax\s*year",
            r"form\s*w-?2",
            r"wages.*20\d{2}",
            r"20\d{2}\s*tax",
        ],
    }

    # Month name to number mapping
    MONTH_MAP = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }

    def __init__(self):
        """Initialize the date extractor."""
        if not TESSERACT_AVAILABLE:
            logger.warning("pytesseract not installed - OCR will not work")

    def extract(
        self,
        file_content: bytes,
        mime_type: str,
        doc_type: Optional[str] = None,
    ) -> DateExtractionResult:
        """
        Extract dates from a document.

        Args:
            file_content: Raw file bytes
            mime_type: MIME type of the file
            doc_type: Optional document type hint (PAYSTUB, BANK_STATEMENT, etc.)

        Returns:
            DateExtractionResult with all extracted dates
        """
        # Get OCR text
        ocr_text = self._get_ocr_text(file_content, mime_type)

        if not ocr_text:
            return DateExtractionResult(
                primary_date=None,
                primary_date_type=None,
                all_dates=[],
                confidence=0.0,
                ocr_text="",
                extracted_data={},
            )

        # Extract all dates
        all_dates = self._extract_all_dates(ocr_text)

        # Classify dates by context
        classified_dates = self._classify_dates(all_dates, ocr_text, doc_type)

        # Determine primary date based on document type
        primary_date, primary_type = self._get_primary_date(
            classified_dates, doc_type
        )

        # Calculate overall confidence
        confidence = self._calculate_confidence(classified_dates)

        # Build extracted data dict
        extracted_data = self._build_extracted_data(classified_dates, doc_type)

        return DateExtractionResult(
            primary_date=primary_date,
            primary_date_type=primary_type,
            all_dates=classified_dates,
            confidence=confidence,
            ocr_text=ocr_text,
            extracted_data=extracted_data,
        )

    def _get_ocr_text(self, file_content: bytes, mime_type: str) -> str:
        """Extract text from file using OCR."""
        if not TESSERACT_AVAILABLE:
            return ""

        try:
            if mime_type == "application/pdf":
                return self._ocr_pdf(file_content)
            elif mime_type.startswith("image/"):
                return self._ocr_image(file_content)
            else:
                logger.warning(f"Unsupported mime type for OCR: {mime_type}")
                return ""
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return ""

    def _ocr_pdf(self, file_content: bytes) -> str:
        """Extract text from PDF using OCR."""
        if not PDF2IMAGE_AVAILABLE:
            return ""

        try:
            # Convert PDF pages to images
            images = convert_from_bytes(file_content, dpi=200)

            # OCR each page and combine
            texts = []
            for i, image in enumerate(images[:5]):  # Limit to first 5 pages
                text = pytesseract.image_to_string(image)
                texts.append(text)

            return "\n\n".join(texts)

        except Exception as e:
            logger.error(f"PDF OCR failed: {e}")
            return ""

    def _ocr_image(self, file_content: bytes) -> str:
        """Extract text from image using OCR."""
        if not PIL_AVAILABLE:
            return ""

        try:
            image = Image.open(BytesIO(file_content))
            return pytesseract.image_to_string(image)
        except Exception as e:
            logger.error(f"Image OCR failed: {e}")
            return ""

    def _extract_all_dates(self, text: str) -> List[Tuple[date, str, float]]:
        """Extract all dates from text using patterns."""
        dates = []
        text_lower = text.lower()

        for pattern, format_type in self.DATE_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    parsed_date = self._parse_date_match(match, format_type)
                    if parsed_date and self._is_valid_date(parsed_date):
                        confidence = self._get_pattern_confidence(format_type)
                        dates.append((parsed_date, match.group(0), confidence))
                except Exception as e:
                    logger.debug(f"Failed to parse date match: {e}")
                    continue

        # Deduplicate by date
        unique_dates = {}
        for dt, source, conf in dates:
            if dt not in unique_dates or conf > unique_dates[dt][1]:
                unique_dates[dt] = (source, conf)

        return [(dt, source, conf) for dt, (source, conf) in unique_dates.items()]

    def _parse_date_match(
        self,
        match: re.Match,
        format_type: str
    ) -> Optional[date]:
        """Parse a regex match into a date object."""
        groups = match.groups()

        if format_type == "mdy":
            month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
        elif format_type == "ymd":
            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
        elif format_type in ["text_mdy", "text_mdy_abbrev"]:
            month_str, day, year = groups[0].lower(), int(groups[1]), int(groups[2])
            month = self.MONTH_MAP.get(month_str[:3], 0)
            if month == 0:
                return None
        elif format_type == "text_dmy":
            day, month_str, year = int(groups[0]), groups[1].lower(), int(groups[2])
            month = self.MONTH_MAP.get(month_str[:3], 0)
            if month == 0:
                return None
        else:
            return None

        return date(year, month, day)

    def _get_pattern_confidence(self, format_type: str) -> float:
        """Get confidence score based on date format."""
        # More explicit formats get higher confidence
        confidence_map = {
            "text_mdy": 0.9,
            "text_dmy": 0.9,
            "text_mdy_abbrev": 0.85,
            "ymd": 0.85,
            "mdy": 0.8,
        }
        return confidence_map.get(format_type, 0.7)

    def _is_valid_date(self, dt: date) -> bool:
        """Check if date is reasonable for a mortgage document."""
        today = date.today()

        # Dates should be within reasonable range
        # Not more than 5 years in the past (for historical docs)
        # Not in the future (except for a few days for pending statements)
        min_date = date(today.year - 5, 1, 1)
        max_date = date(today.year + 1, 12, 31)

        return min_date <= dt <= max_date

    def _classify_dates(
        self,
        dates: List[Tuple[date, str, float]],
        text: str,
        doc_type: Optional[str]
    ) -> List[ExtractedDate]:
        """Classify dates by their context/type."""
        classified = []
        text_lower = text.lower()

        for dt, source, confidence in dates:
            # Find the source text position
            pos = text_lower.find(source.lower())
            context_window = text_lower[max(0, pos-100):min(len(text_lower), pos+len(source)+50)]

            # Determine date type from context
            date_type = self._determine_date_type(context_window, doc_type)

            classified.append(ExtractedDate(
                date=dt,
                date_type=date_type,
                confidence=confidence,
                source_text=source,
                context=context_window[:100] if context_window else None,
            ))

        return classified

    def _determine_date_type(
        self,
        context: str,
        doc_type: Optional[str]
    ) -> str:
        """Determine the type of date based on surrounding context."""
        context_lower = context.lower()

        # Check each date type pattern
        for date_type, patterns in self.DATE_CONTEXT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, context_lower):
                    return date_type

        # Default based on document type
        if doc_type:
            doc_type_defaults = {
                "PAYSTUB": "pay_date",
                "BANK_STATEMENT": "statement_date",
                "W2": "tax_year",
                "TAX_RETURN": "tax_year",
            }
            return doc_type_defaults.get(doc_type, "document_date")

        return "document_date"

    def _get_primary_date(
        self,
        classified_dates: List[ExtractedDate],
        doc_type: Optional[str]
    ) -> Tuple[Optional[date], Optional[str]]:
        """Determine the primary date for freshness validation."""
        if not classified_dates:
            return None, None

        # Priority order based on document type
        priority_map = {
            "PAYSTUB": ["pay_date", "period_end"],
            "BANK_STATEMENT": ["statement_end", "statement_date", "period_end"],
            "W2": ["tax_year"],
            "TAX_RETURN": ["tax_year"],
            "INVESTMENT_STATEMENT": ["statement_date", "period_end"],
        }

        priority = priority_map.get(doc_type, [
            "statement_date", "pay_date", "period_end", "document_date"
        ])

        # Find highest priority date
        for date_type in priority:
            for dt in classified_dates:
                if dt.date_type == date_type:
                    return dt.date, dt.date_type

        # Fall back to most recent date
        sorted_dates = sorted(classified_dates, key=lambda x: x.date, reverse=True)
        return sorted_dates[0].date, sorted_dates[0].date_type

    def _calculate_confidence(
        self,
        classified_dates: List[ExtractedDate]
    ) -> float:
        """Calculate overall extraction confidence."""
        if not classified_dates:
            return 0.0

        # Average confidence, weighted by having expected date types
        base_confidence = sum(d.confidence for d in classified_dates) / len(classified_dates)

        # Boost if we found expected date types
        has_specific_types = any(
            d.date_type in ["pay_date", "statement_date", "period_end"]
            for d in classified_dates
        )

        if has_specific_types:
            base_confidence = min(base_confidence + 0.1, 1.0)

        return round(base_confidence, 3)

    def _build_extracted_data(
        self,
        classified_dates: List[ExtractedDate],
        doc_type: Optional[str]
    ) -> Dict[str, Any]:
        """Build structured extracted data dict."""
        data = {}

        for dt in classified_dates:
            key_map = {
                "pay_date": "payDate",
                "period_start": "periodStart",
                "period_end": "periodEnd",
                "statement_date": "statementDate",
                "statement_end": "statementEnd",
                "tax_year": "taxYear",
                "document_date": "documentDate",
            }

            key = key_map.get(dt.date_type, "otherDate")

            # Store the most confident/recent for each type
            if key not in data or dt.date > datetime.strptime(data[key], "%Y-%m-%d").date():
                data[key] = dt.date.isoformat()

        return data

    def result_to_dict(self, result: DateExtractionResult) -> Dict[str, Any]:
        """Convert result to dictionary for storage/API."""
        return {
            "primary_date": result.primary_date.isoformat() if result.primary_date else None,
            "primary_date_type": result.primary_date_type,
            "confidence": result.confidence,
            "extracted_data": result.extracted_data,
            "all_dates": [
                {
                    "date": d.date.isoformat(),
                    "type": d.date_type,
                    "confidence": d.confidence,
                    "source_text": d.source_text,
                }
                for d in result.all_dates
            ],
        }
