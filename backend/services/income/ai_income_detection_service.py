"""
AI Income Detection Service

Automatically detects income type from uploaded documents using:
1. Document classification (AI-powered)
2. Content extraction patterns
3. Document metadata analysis

Outputs:
- Detected income type (from 14 unified types)
- Confidence score (0-100)
- Extracted fields with per-field confidence
- Suggested calculation method
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .unified_income_calculator import (
    UnifiedIncomeType,
    ConfidenceLevel,
    PayFrequency,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DOCUMENT TYPES
# =============================================================================

class IncomeDocumentType(str, Enum):
    """Document types that contain income information."""
    # W-2 Related
    PAYSTUB = "PAYSTUB"
    W2 = "W2"
    OFFER_LETTER = "OFFER_LETTER"
    VOE_VERBAL = "VOE_VERBAL"
    VOE_WRITTEN = "VOE_WRITTEN"

    # Tax Documents
    TAX_RETURN_1040 = "TAX_RETURN_1040"
    SCHEDULE_C = "SCHEDULE_C"
    SCHEDULE_E = "SCHEDULE_E"
    SCHEDULE_K1_1065 = "SCHEDULE_K1_1065"
    SCHEDULE_K1_1120S = "SCHEDULE_K1_1120S"
    FORM_1120 = "FORM_1120"
    FORM_1099 = "FORM_1099"
    FORM_2106 = "FORM_2106"

    # Social Security
    SSA_1099 = "SSA_1099"
    SSA_AWARD_LETTER = "SSA_AWARD_LETTER"

    # Other Income
    PENSION_STATEMENT = "PENSION_STATEMENT"
    BANK_STATEMENT = "BANK_STATEMENT"
    PROFIT_LOSS_STATEMENT = "PROFIT_LOSS_STATEMENT"
    LEASE_AGREEMENT = "LEASE_AGREEMENT"
    CHILD_SUPPORT_ORDER = "CHILD_SUPPORT_ORDER"
    DISABILITY_AWARD = "DISABILITY_AWARD"

    # Unknown
    UNKNOWN = "UNKNOWN"


# =============================================================================
# DETECTION PATTERNS
# =============================================================================

# Patterns to identify document types from OCR text
DOCUMENT_PATTERNS = {
    IncomeDocumentType.PAYSTUB: [
        r"pay\s*stub|pay\s*statement|earnings\s*statement",
        r"gross\s*pay|net\s*pay|ytd\s*gross",
        r"federal\s*tax|fica|social\s*security",
        r"pay\s*period|pay\s*date",
    ],
    IncomeDocumentType.W2: [
        r"form\s*w-?2|wage\s*and\s*tax\s*statement",
        r"employer\'?s?\s*identification\s*number",
        r"box\s*1|wages,?\s*tips",
        r"employee\'?s?\s*social\s*security",
    ],
    IncomeDocumentType.TAX_RETURN_1040: [
        r"form\s*1040|u\.?s\.?\s*individual\s*income\s*tax\s*return",
        r"adjusted\s*gross\s*income",
        r"taxable\s*income",
        r"filing\s*status",
    ],
    IncomeDocumentType.SCHEDULE_C: [
        r"schedule\s*c|profit\s*or\s*loss\s*from\s*business",
        r"sole\s*proprietorship",
        r"principal\s*business\s*or\s*profession",
        r"gross\s*receipts|cost\s*of\s*goods\s*sold",
    ],
    IncomeDocumentType.SCHEDULE_E: [
        r"schedule\s*e|supplemental\s*income",
        r"rental\s*real\s*estate|royalties|partnerships",
        r"rents\s*received|rental\s*income",
        r"depreciation\s*expense|advertising|insurance",
    ],
    IncomeDocumentType.SCHEDULE_K1_1065: [
        r"schedule\s*k-?1.{0,20}form\s*1065|partner\'?s?\s*share",
        r"partnership",
        r"ordinary\s*business\s*income|guaranteed\s*payments",
        r"self-employment\s*earnings",
    ],
    IncomeDocumentType.SCHEDULE_K1_1120S: [
        r"schedule\s*k-?1.{0,20}form\s*1120s|shareholder\'?s?\s*share",
        r"s\s*corporation",
        r"ordinary\s*business\s*income",
        r"pro\s*rata\s*share",
    ],
    IncomeDocumentType.FORM_1120: [
        r"form\s*1120|u\.?s\.?\s*corporation\s*income\s*tax",
        r"taxable\s*income|total\s*deductions",
        r"gross\s*receipts\s*or\s*sales",
    ],
    IncomeDocumentType.SSA_1099: [
        r"ssa-?1099|social\s*security\s*benefit\s*statement",
        r"benefits\s*paid|medicare\s*premium",
    ],
    IncomeDocumentType.BANK_STATEMENT: [
        r"bank\s*statement|account\s*statement",
        r"beginning\s*balance|ending\s*balance",
        r"deposits|withdrawals|transactions",
    ],
    IncomeDocumentType.LEASE_AGREEMENT: [
        r"lease\s*agreement|rental\s*agreement",
        r"landlord|tenant|lessee|lessor",
        r"monthly\s*rent|security\s*deposit",
    ],
    IncomeDocumentType.FORM_2106: [
        r"form\s*2106|employee\s*business\s*expenses",
        r"unreimbursed\s*employee\s*expenses",
        r"vehicle\s*expenses|travel\s*expenses",
    ],
}

# Mapping from document type to income types
DOCUMENT_TO_INCOME_TYPE: Dict[IncomeDocumentType, List[UnifiedIncomeType]] = {
    IncomeDocumentType.PAYSTUB: [
        UnifiedIncomeType.W2_SALARY,
        UnifiedIncomeType.W2_HOURLY,
        UnifiedIncomeType.OT_BONUS,
        UnifiedIncomeType.COMMISSION,
    ],
    IncomeDocumentType.W2: [
        UnifiedIncomeType.W2_SALARY,
        UnifiedIncomeType.W2_HOURLY,
        UnifiedIncomeType.OT_BONUS,
        UnifiedIncomeType.COMMISSION,
    ],
    IncomeDocumentType.SCHEDULE_C: [
        UnifiedIncomeType.SELF_EMPLOYMENT_1084,
    ],
    IncomeDocumentType.SCHEDULE_E: [
        UnifiedIncomeType.RENTAL_SCHEDULE_E,
    ],
    IncomeDocumentType.SCHEDULE_K1_1065: [
        UnifiedIncomeType.SELF_EMPLOYMENT_1084,
    ],
    IncomeDocumentType.SCHEDULE_K1_1120S: [
        UnifiedIncomeType.SELF_EMPLOYMENT_1084,
    ],
    IncomeDocumentType.FORM_1120: [
        UnifiedIncomeType.SELF_EMPLOYMENT_1084,
    ],
    IncomeDocumentType.SSA_1099: [
        UnifiedIncomeType.NONTAX_SS,
    ],
    IncomeDocumentType.SSA_AWARD_LETTER: [
        UnifiedIncomeType.NONTAX_SS,
    ],
    IncomeDocumentType.BANK_STATEMENT: [
        UnifiedIncomeType.BANK_STATEMENT_PERSONAL,
        UnifiedIncomeType.BANK_STATEMENT_BUSINESS_M1,
        UnifiedIncomeType.BANK_STATEMENT_BUSINESS_M2,
        UnifiedIncomeType.BANK_STATEMENT_BUSINESS_M3,
    ],
    IncomeDocumentType.LEASE_AGREEMENT: [
        UnifiedIncomeType.RENTAL_SCHEDULE_E,
    ],
    IncomeDocumentType.FORM_2106: [
        UnifiedIncomeType.COMMISSION,  # 2106 expenses affect commission
    ],
    IncomeDocumentType.PENSION_STATEMENT: [
        UnifiedIncomeType.NONTAX_OTHER,
    ],
    IncomeDocumentType.CHILD_SUPPORT_ORDER: [
        UnifiedIncomeType.NONTAX_OTHER,
    ],
}


# =============================================================================
# FIELD EXTRACTION PATTERNS
# =============================================================================

# Regex patterns for extracting specific fields
FIELD_PATTERNS = {
    # Currency amounts
    "currency": r"\$?\s*[\d,]+\.?\d{0,2}",

    # Dates
    "date": r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+\s+\d{1,2},?\s+\d{4}",

    # Tax year
    "tax_year": r"(?:tax\s*year|for\s*year|20\d{2})\s*:?\s*(20\d{2})",

    # SSN (partial)
    "ssn_last4": r"xxx-?xx-?(\d{4})|(?:\*{3}-?\*{2}-?)(\d{4})",

    # Paystub fields
    "hourly_rate": r"(?:hourly|rate|per\s*hour)\s*:?\s*\$?\s*([\d.]+)",
    "hours_worked": r"(?:hours|hrs)\s*:?\s*([\d.]+)",
    "gross_pay": r"(?:gross\s*pay|gross\s*earnings|total\s*gross)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "net_pay": r"(?:net\s*pay|net\s*earnings|take\s*home)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "ytd_gross": r"(?:ytd\s*gross|ytd\s*earnings|year\s*to\s*date)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "federal_tax": r"(?:federal\s*tax|fed\s*w/h|fit)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "overtime_pay": r"(?:overtime|ot\s*pay|ot\s*earnings)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "bonus_pay": r"(?:bonus|incentive|award)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "commission_pay": r"(?:commission|comm)\s*:?\s*\$?\s*([\d,]+\.?\d*)",

    # W2 fields
    "w2_box1": r"(?:box\s*1|wages,?\s*tips)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "w2_box2": r"(?:box\s*2|federal\s*income\s*tax)\s*:?\s*\$?\s*([\d,]+\.?\d*)",

    # Schedule C
    "schedule_c_line31": r"(?:line\s*31|net\s*profit)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "schedule_c_depreciation": r"(?:line\s*13|depreciation)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "gross_receipts": r"(?:gross\s*receipts|line\s*1)\s*:?\s*\$?\s*([\d,]+\.?\d*)",

    # Schedule E
    "gross_rents": r"(?:rents\s*received|gross\s*rents|line\s*3)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "rental_expenses": r"(?:total\s*expenses|line\s*20)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "rental_depreciation": r"(?:depreciation|line\s*18)\s*:?\s*\$?\s*([\d,]+\.?\d*)",

    # K-1 Partnership
    "k1_ordinary_income": r"(?:ordinary\s*(?:business\s*)?income|line\s*1)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "k1_guaranteed_payments": r"(?:guaranteed\s*payments|line\s*4)\s*:?\s*\$?\s*([\d,]+\.?\d*)",

    # Social Security
    "ss_benefits": r"(?:benefits\s*paid|total\s*benefits)\s*:?\s*\$?\s*([\d,]+\.?\d*)",

    # Bank statement
    "ending_balance": r"(?:ending\s*balance|closing\s*balance)\s*:?\s*\$?\s*([\d,]+\.?\d*)",
    "total_deposits": r"(?:total\s*deposits|deposits)\s*:?\s*\$?\s*([\d,]+\.?\d*)",

    # Employer info
    "employer_name": r"(?:employer|company)\s*(?:name)?\s*:?\s*([A-Z][a-zA-Z\s&.,]+)",
    "employer_ein": r"(?:ein|employer\s*id|fein)\s*:?\s*(\d{2}-?\d{7})",
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ExtractedField:
    """A single extracted field with confidence."""
    field_name: str
    value: Any
    confidence: int  # 0-100
    source_text: str  # Original text that was matched
    pattern_used: str


@dataclass
class DocumentDetectionResult:
    """Result of document type detection."""
    document_type: IncomeDocumentType
    confidence: int  # 0-100
    possible_income_types: List[UnifiedIncomeType]
    suggested_income_type: UnifiedIncomeType
    extracted_fields: List[ExtractedField]
    tax_year: Optional[int] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_type": self.document_type.value,
            "confidence": self.confidence,
            "confidence_level": self._get_confidence_level().value,
            "possible_income_types": [t.value for t in self.possible_income_types],
            "suggested_income_type": self.suggested_income_type.value,
            "extracted_fields": [
                {
                    "field_name": f.field_name,
                    "value": str(f.value) if isinstance(f.value, Decimal) else f.value,
                    "confidence": f.confidence,
                }
                for f in self.extracted_fields
            ],
            "tax_year": self.tax_year,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "requires_review": self.confidence < 98,
            "auto_approve_eligible": self.confidence >= 98,
        }

    def _get_confidence_level(self) -> ConfidenceLevel:
        if self.confidence >= 95:
            return ConfidenceLevel.HIGH
        elif self.confidence >= 80:
            return ConfidenceLevel.MEDIUM
        elif self.confidence >= 60:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.MANUAL


# =============================================================================
# AI INCOME DETECTION SERVICE
# =============================================================================

class AIIncomeDetectionService:
    """
    Service for detecting income type from documents.

    Uses pattern matching and AI to:
    1. Identify document type (paystub, W2, Schedule C, etc.)
    2. Extract relevant fields
    3. Determine appropriate income type
    4. Calculate confidence scores
    """

    def __init__(self):
        pass

    def detect_from_text(self, text: str, filename: Optional[str] = None) -> DocumentDetectionResult:
        """
        Detect income document type from OCR text.

        Args:
            text: OCR or extracted text from document
            filename: Optional filename for additional hints

        Returns:
            DocumentDetectionResult with detected type and extracted fields
        """
        text_lower = text.lower()
        warnings = []

        # Step 1: Detect document type
        doc_type, doc_confidence = self._detect_document_type(text_lower, filename)

        # Step 2: Get possible income types for this document
        possible_income_types = DOCUMENT_TO_INCOME_TYPE.get(
            doc_type,
            [UnifiedIncomeType.OTHER_INCOME]
        )

        # Step 3: Extract fields based on document type
        extracted_fields = self._extract_fields(text, doc_type)

        # Step 4: Determine specific income type from extracted fields
        suggested_type, type_confidence = self._determine_income_type(
            doc_type, extracted_fields, possible_income_types
        )

        # Step 5: Extract tax year if available
        tax_year = self._extract_tax_year(text)

        # Step 6: Calculate overall confidence
        field_confidence = self._calculate_field_confidence(extracted_fields)
        overall_confidence = int((doc_confidence * 0.4) + (type_confidence * 0.3) + (field_confidence * 0.3))

        # Step 7: Generate warnings
        if overall_confidence < 80:
            warnings.append("Low confidence - manual review recommended")

        if not extracted_fields:
            warnings.append("No fields could be extracted - document may need OCR improvement")

        if doc_type == IncomeDocumentType.UNKNOWN:
            warnings.append("Could not determine document type")

        return DocumentDetectionResult(
            document_type=doc_type,
            confidence=overall_confidence,
            possible_income_types=possible_income_types,
            suggested_income_type=suggested_type,
            extracted_fields=extracted_fields,
            tax_year=tax_year,
            warnings=warnings,
            metadata={
                "doc_confidence": doc_confidence,
                "type_confidence": type_confidence,
                "field_confidence": field_confidence,
                "filename": filename,
            }
        )

    def _detect_document_type(
        self,
        text_lower: str,
        filename: Optional[str]
    ) -> Tuple[IncomeDocumentType, int]:
        """Detect document type using pattern matching."""
        scores: Dict[IncomeDocumentType, int] = {}

        # Check filename hints
        if filename:
            filename_lower = filename.lower()
            if "paystub" in filename_lower or "pay_stub" in filename_lower:
                scores[IncomeDocumentType.PAYSTUB] = 30
            elif "w2" in filename_lower or "w-2" in filename_lower:
                scores[IncomeDocumentType.W2] = 30
            elif "1040" in filename_lower:
                scores[IncomeDocumentType.TAX_RETURN_1040] = 30
            elif "schedule_c" in filename_lower or "sched_c" in filename_lower:
                scores[IncomeDocumentType.SCHEDULE_C] = 30
            elif "schedule_e" in filename_lower or "sched_e" in filename_lower:
                scores[IncomeDocumentType.SCHEDULE_E] = 30
            elif "k-1" in filename_lower or "k1" in filename_lower:
                if "1065" in filename_lower:
                    scores[IncomeDocumentType.SCHEDULE_K1_1065] = 30
                elif "1120s" in filename_lower:
                    scores[IncomeDocumentType.SCHEDULE_K1_1120S] = 30
            elif "bank" in filename_lower and "statement" in filename_lower:
                scores[IncomeDocumentType.BANK_STATEMENT] = 30
            elif "ssa" in filename_lower or "social_security" in filename_lower:
                scores[IncomeDocumentType.SSA_1099] = 30

        # Check content patterns
        for doc_type, patterns in DOCUMENT_PATTERNS.items():
            pattern_matches = 0
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    pattern_matches += 1

            if pattern_matches > 0:
                # Score based on percentage of patterns matched
                match_score = int((pattern_matches / len(patterns)) * 70)
                scores[doc_type] = scores.get(doc_type, 0) + match_score

        # Find best match
        if not scores:
            return IncomeDocumentType.UNKNOWN, 20

        best_type = max(scores, key=scores.get)
        best_score = min(scores[best_type], 100)

        return best_type, best_score

    def _extract_fields(
        self,
        text: str,
        doc_type: IncomeDocumentType
    ) -> List[ExtractedField]:
        """Extract relevant fields based on document type."""
        extracted = []

        # Determine which fields to extract based on document type
        fields_to_extract = self._get_fields_for_doc_type(doc_type)

        for field_name in fields_to_extract:
            if field_name not in FIELD_PATTERNS:
                continue

            pattern = FIELD_PATTERNS[field_name]
            matches = re.findall(pattern, text, re.IGNORECASE)

            if matches:
                # Take first match, clean value
                raw_value = matches[0] if isinstance(matches[0], str) else matches[0][0]
                cleaned_value = self._clean_value(raw_value, field_name)

                # Calculate confidence based on pattern specificity
                confidence = self._calculate_match_confidence(pattern, raw_value, text)

                extracted.append(ExtractedField(
                    field_name=field_name,
                    value=cleaned_value,
                    confidence=confidence,
                    source_text=raw_value,
                    pattern_used=field_name,
                ))

        return extracted

    def _get_fields_for_doc_type(self, doc_type: IncomeDocumentType) -> List[str]:
        """Get list of fields to extract for a document type."""
        field_map = {
            IncomeDocumentType.PAYSTUB: [
                "hourly_rate", "hours_worked", "gross_pay", "net_pay",
                "ytd_gross", "federal_tax", "overtime_pay", "bonus_pay",
                "commission_pay", "employer_name", "date",
            ],
            IncomeDocumentType.W2: [
                "w2_box1", "w2_box2", "employer_name", "employer_ein",
                "tax_year",
            ],
            IncomeDocumentType.SCHEDULE_C: [
                "schedule_c_line31", "schedule_c_depreciation",
                "gross_receipts", "tax_year",
            ],
            IncomeDocumentType.SCHEDULE_E: [
                "gross_rents", "rental_expenses", "rental_depreciation",
                "tax_year",
            ],
            IncomeDocumentType.SCHEDULE_K1_1065: [
                "k1_ordinary_income", "k1_guaranteed_payments", "tax_year",
            ],
            IncomeDocumentType.SCHEDULE_K1_1120S: [
                "k1_ordinary_income", "tax_year",
            ],
            IncomeDocumentType.SSA_1099: [
                "ss_benefits", "tax_year",
            ],
            IncomeDocumentType.BANK_STATEMENT: [
                "ending_balance", "total_deposits", "date",
            ],
        }
        return field_map.get(doc_type, ["currency", "date"])

    def _clean_value(self, raw_value: str, field_name: str) -> Any:
        """Clean and convert extracted value."""
        if not raw_value:
            return None

        # Remove common noise
        cleaned = raw_value.strip().replace(",", "").replace("$", "")

        # Convert to appropriate type
        if field_name in ["tax_year"]:
            try:
                return int(cleaned)
            except Exception as e:
                logger.error(f"Error converting tax_year value '{cleaned}' to int in _clean_value: {e}")
                return None

        if field_name in [
            "hourly_rate", "hours_worked", "gross_pay", "net_pay",
            "ytd_gross", "federal_tax", "overtime_pay", "bonus_pay",
            "commission_pay", "w2_box1", "w2_box2", "schedule_c_line31",
            "schedule_c_depreciation", "gross_receipts", "gross_rents",
            "rental_expenses", "rental_depreciation", "k1_ordinary_income",
            "k1_guaranteed_payments", "ss_benefits", "ending_balance",
            "total_deposits",
        ]:
            try:
                return Decimal(cleaned)
            except Exception as e:
                logger.error(f"Error converting '{field_name}' value '{cleaned}' to Decimal in _clean_value: {e}")
                return None

        return cleaned

    def _calculate_match_confidence(
        self,
        pattern: str,
        matched_value: str,
        full_text: str
    ) -> int:
        """Calculate confidence score for a pattern match."""
        base_confidence = 70

        # Boost for exact label matches
        if any(kw in full_text.lower() for kw in ["gross pay", "net pay", "ytd", "wages"]):
            base_confidence += 10

        # Boost for reasonable values
        try:
            value = Decimal(matched_value.replace(",", "").replace("$", ""))
            if Decimal("10") < value < Decimal("10000000"):
                base_confidence += 10
        except Exception as e:
            logger.error(f"Error parsing matched_value '{matched_value}' in _calculate_match_confidence: {e}")

        # Reduce for ambiguous matches
        if matched_value.count(".") > 1:
            base_confidence -= 20

        return min(max(base_confidence, 30), 95)

    def _determine_income_type(
        self,
        doc_type: IncomeDocumentType,
        extracted_fields: List[ExtractedField],
        possible_types: List[UnifiedIncomeType]
    ) -> Tuple[UnifiedIncomeType, int]:
        """Determine specific income type from extracted fields."""

        # If only one possible type, use it
        if len(possible_types) == 1:
            return possible_types[0], 90

        field_names = {f.field_name for f in extracted_fields}
        field_values = {f.field_name: f.value for f in extracted_fields}

        # Check for specific indicators
        if doc_type == IncomeDocumentType.PAYSTUB:
            # Check if hourly
            if "hourly_rate" in field_names or "hours_worked" in field_names:
                return UnifiedIncomeType.W2_HOURLY, 85

            # Check for overtime/bonus
            has_ot_bonus = (
                field_values.get("overtime_pay") or
                field_values.get("bonus_pay")
            )
            if has_ot_bonus:
                return UnifiedIncomeType.OT_BONUS, 80

            # Check for commission
            if field_values.get("commission_pay"):
                return UnifiedIncomeType.COMMISSION, 80

            # Default to salary
            return UnifiedIncomeType.W2_SALARY, 75

        if doc_type == IncomeDocumentType.BANK_STATEMENT:
            # Need more context to determine personal vs business
            # Default to personal with lower confidence
            return UnifiedIncomeType.BANK_STATEMENT_PERSONAL, 60

        # Return first possible type with medium confidence
        return possible_types[0] if possible_types else UnifiedIncomeType.OTHER_INCOME, 60

    def _extract_tax_year(self, text: str) -> Optional[int]:
        """Extract tax year from document text."""
        patterns = [
            r"(?:tax\s*year|for\s*year)\s*:?\s*(20\d{2})",
            r"(20\d{2})\s*(?:tax\s*return|w-?2|1099)",
            r"(?:year\s*ending|through)\s*\d{1,2}[-/]\d{1,2}[-/](20\d{2})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    year = int(match.group(1))
                    if 2000 <= year <= 2030:
                        return year
                except Exception as e:
                    logger.error(f"Error parsing tax year from match in _extract_tax_year: {e}")

        return None

    def _calculate_field_confidence(self, fields: List[ExtractedField]) -> int:
        """Calculate overall confidence from extracted fields."""
        if not fields:
            return 30

        # Average of field confidences, weighted by importance
        total_weight = 0
        weighted_sum = 0

        important_fields = {
            "gross_pay", "ytd_gross", "w2_box1", "schedule_c_line31",
            "gross_rents", "k1_ordinary_income", "ss_benefits",
        }

        for field in fields:
            weight = 2 if field.field_name in important_fields else 1
            weighted_sum += field.confidence * weight
            total_weight += weight

        return int(weighted_sum / total_weight) if total_weight > 0 else 30

    def batch_detect(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[DocumentDetectionResult]:
        """
        Process multiple documents and detect income types.

        Args:
            documents: List of dicts with 'text' and optional 'filename'

        Returns:
            List of detection results
        """
        results = []
        for doc in documents:
            text = doc.get("text", "")
            filename = doc.get("filename")
            result = self.detect_from_text(text, filename)
            results.append(result)
        return results

    def get_required_documents(
        self,
        income_type: UnifiedIncomeType
    ) -> List[str]:
        """Get list of required documents for an income type."""
        requirements = {
            UnifiedIncomeType.W2_HOURLY: [
                "Most recent paystub (with hours and rate)",
                "W-2 for most recent year",
                "W-2 for prior year (for 2-year average)",
            ],
            UnifiedIncomeType.W2_SALARY: [
                "Most recent paystub",
                "W-2 for most recent year",
            ],
            UnifiedIncomeType.OT_BONUS: [
                "2 years of paystubs showing OT/Bonus",
                "2 years of W-2s",
            ],
            UnifiedIncomeType.COMMISSION: [
                "2 years of paystubs showing commission",
                "2 years of W-2s",
                "2 years of tax returns with Form 2106 (if applicable)",
            ],
            UnifiedIncomeType.SELF_EMPLOYMENT_1084: [
                "2 years of personal tax returns (1040)",
                "2 years of business tax returns",
                "Schedule C, K-1, or 1120 as applicable",
                "YTD Profit & Loss statement",
            ],
            UnifiedIncomeType.RENTAL_SCHEDULE_E: [
                "2 years of tax returns with Schedule E",
                "Current lease agreement(s)",
                "Most recent 2 months rental deposits",
            ],
            UnifiedIncomeType.NONTAX_SS: [
                "SSA-1099 or Award Letter",
                "Tax return showing Social Security",
            ],
            UnifiedIncomeType.BANK_STATEMENT_PERSONAL: [
                "12 or 24 months of personal bank statements",
            ],
            UnifiedIncomeType.BANK_STATEMENT_BUSINESS_M1: [
                "12 or 24 months of business bank statements",
            ],
            UnifiedIncomeType.BANK_STATEMENT_BUSINESS_M2: [
                "12 or 24 months of business bank statements",
                "CPA letter confirming expense ratio",
            ],
            UnifiedIncomeType.BANK_STATEMENT_BUSINESS_M3: [
                "12 or 24 months of business bank statements",
                "YTD Profit & Loss statement",
            ],
        }
        return requirements.get(income_type, ["Income documentation required"])


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_detection_service: Optional[AIIncomeDetectionService] = None


def get_ai_income_detection_service() -> AIIncomeDetectionService:
    """Get singleton instance of AIIncomeDetectionService."""
    global _detection_service
    if _detection_service is None:
        _detection_service = AIIncomeDetectionService()
    return _detection_service
